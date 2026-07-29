"""Bounded, non-mutating inspection of Core's academic registry."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import stat
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field as dataclass_field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias, cast

from pds_core import academic_catalog
from pds_core.academic_period_storage import (
    academic_periods_dir,
    load_academic_period_calendar_revision,
    load_current_academic_period_calendar,
)
from pds_core.academic_periods import (
    AcademicPeriodCalendar,
    AcademicPeriodValidationError,
    validate_academic_period_calendar_transition,
)
from pds_core.academic_work_registration_storage import (
    load_academic_work_registration_revision,
    load_current_academic_work_registration,
)
from pds_core.academic_work_registrations import (
    AcademicWorkRegistration,
    AcademicWorkRegistrationValidationError,
    validate_academic_work_registration_transition,
)
from pds_core.class_metadata import load_class_metadata_for_class
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.publication_compatibility import (
    PublicationCompatibilityError,
    PublicationProducerProfile,
    build_publication_producer_registry,
    evaluate_publication_compatibility,
)
from pds_core.publication_records import (
    PublicationRecord,
    PublicationRecordValidationError,
    PublicationWithdrawal,
    validate_publication_record_series,
    validate_publication_withdrawal_relationship,
)
from pds_core.publication_storage import (
    PublicationManifestError,
    PublicationManifestIntegrityError,
    PublicationManifestNotFoundError,
    load_publication_record,
    load_publication_withdrawal,
    resolve_publication_manifest_path,
    verify_publication_manifest,
)
from pds_core.registry_paths import (
    academic_catalog_lock_path,
    academic_catalog_path,
    academic_work_registration_dir,
    academic_work_registration_revision_path,
    academic_work_registrations_dir,
    publication_withdrawals_dir,
    publications_dir,
    registry_dir,
)
from pds_core.routes import module_work_dir
from pds_core.routing_models import ModuleWorkRef
from pds_core.school_years import SchoolYearValidationError, validate_school_year
from pds_core.workspace import WorkspaceRootError, _normalize_workspace_root

REGISTRY_AUDIT_SCHEMA_VERSION: Final[str] = "1"
AuditSeverity: TypeAlias = Literal["info", "warning", "error"]
AuditDomain: TypeAlias = Literal[
    "workspace", "academic_periods", "registrations", "publications",
    "manifests", "contracts", "catalog", "locks",
]
AuditRepairKind: TypeAlias = Literal[
    "none", "rebuild_catalog", "clear_lock", "producer_action",
    "manual_canonical_review",
]
RegistryAuditScope: TypeAlias = Literal[
    "academic_periods", "registrations", "publications", "manifests",
    "contracts", "catalog", "locks",
]

_SEVERITIES = frozenset({"info", "warning", "error"})
_DOMAINS = frozenset({"workspace", "academic_periods", "registrations", "publications", "manifests", "contracts", "catalog", "locks"})
_REPAIRS = frozenset({"none", "rebuild_catalog", "clear_lock", "producer_action", "manual_canonical_review"})
_SCOPES: tuple[RegistryAuditScope, ...] = ("academic_periods", "registrations", "publications", "manifests", "contracts", "catalog", "locks")
_CODE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_PUB_NAME = re.compile(r"^(pub_[0-9a-f]{32})\.json$")
_REVISION_NAME = re.compile(r"^([1-9]\d*)\.json$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


class RegistryAuditError(RuntimeError):
    """Base error for registry inspection and maintenance."""


class RegistryAuditValidationError(RegistryAuditError, ValueError):
    """Raised when an audit request is invalid."""


class RegistryAuditReadError(RegistryAuditError):
    """Raised when inspection cannot read required filesystem state."""


class RegistryAuditCompatibilityError(RegistryAuditError):
    """Raised when optional compatibility metadata cannot be used safely."""


class RegistryAuditRepairError(RegistryAuditError):
    """Raised when requested maintenance cannot complete safely."""


class RegistryAuditConflictError(RegistryAuditError):
    """Raised when inspected state changes during a guarded repair."""


def _single_line(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise RegistryAuditValidationError(f"{name} must be a nonempty single-line string.")
    return value


def _relative_path(value: str | None) -> str | None:
    if value is None:
        return None
    result = _single_line(value, "path").replace("\\", "/")
    if result.startswith("/") or re.match(r"^[A-Za-z]:", result) or any(part in {"", ".", ".."} for part in result.split("/")):
        raise RegistryAuditValidationError("path must be a normalized workspace-relative POSIX path.")
    return result


@dataclass(frozen=True, slots=True)
class RegistryAuditFinding:
    severity: AuditSeverity
    domain: AuditDomain
    code: str
    message: str
    path: str | None = None
    related_paths: tuple[str, ...] = ()
    identity: tuple[tuple[str, str], ...] = ()
    repair: AuditRepairKind = "none"

    def __post_init__(self) -> None:
        if self.severity not in _SEVERITIES:
            raise RegistryAuditValidationError("severity is invalid.")
        if self.domain not in _DOMAINS:
            raise RegistryAuditValidationError("domain is invalid.")
        if not isinstance(self.code, str) or _CODE.fullmatch(self.code) is None:
            raise RegistryAuditValidationError("code must be a lowercase dotted identifier.")
        if not self.code.startswith(f"{self.domain}."):
            raise RegistryAuditValidationError("code must begin with its domain.")
        object.__setattr__(self, "message", _single_line(self.message, "message"))
        object.__setattr__(self, "path", _relative_path(self.path))
        if isinstance(self.related_paths, (str, bytes, Mapping)):
            raise RegistryAuditValidationError(
                "related_paths must be an iterable of relative paths."
            )
        try:
            raw_related_paths = tuple(self.related_paths)
        except TypeError as error:
            raise RegistryAuditValidationError(
                "related_paths must be iterable."
            ) from error
        if any(not isinstance(value, str) for value in raw_related_paths):
            raise RegistryAuditValidationError(
                "related_paths must contain only relative path strings."
            )
        object.__setattr__(
            self,
            "related_paths",
            tuple(cast(str, _relative_path(value)) for value in raw_related_paths),
        )
        if isinstance(self.identity, (str, bytes, Mapping)):
            raise RegistryAuditValidationError(
                "identity must be an iterable of string pairs."
            )
        try:
            identity = tuple(sorted((_single_line(key, "identity key"), _single_line(value, "identity value")) for key, value in self.identity))
        except (TypeError, ValueError) as error:
            raise RegistryAuditValidationError("identity must contain string pairs.") from error
        if len({key for key, _ in identity}) != len(identity):
            raise RegistryAuditValidationError("identity keys must be unique.")
        object.__setattr__(self, "identity", identity)
        if self.repair not in _REPAIRS:
            raise RegistryAuditValidationError("repair is invalid.")


@dataclass(frozen=True, slots=True)
class RegistryAuditCounts:
    school_years: int = 0
    calendar_revisions: int = 0
    periods: int = 0
    registration_works: int = 0
    registration_revisions: int = 0
    publication_records: int = 0
    publication_series: int = 0
    withdrawals: int = 0
    verified_manifests: int = 0
    catalog_source_files: int = 0
    locks: int = 0
    info_findings: int = 0
    warning_findings: int = 0
    error_findings: int = 0

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RegistryAuditValidationError(f"{field.name} must be a nonnegative integer.")


@dataclass(frozen=True, slots=True)
class RegistryAuditOptions:
    scopes: tuple[RegistryAuditScope, ...] = _SCOPES
    school_year: str | None = None
    class_id: str | None = None
    module_id: str | None = None
    work_id: str | None = None
    publication_id: str | None = None
    require_catalog: bool = False
    require_producer_profiles: bool = False
    discover_installed_producer_profiles: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.scopes, (str, bytes, Mapping)):
            raise RegistryAuditValidationError("scopes must be an iterable of scopes.")
        try:
            requested = frozenset(self.scopes)
        except TypeError as error:
            raise RegistryAuditValidationError("scopes must be iterable.") from error
        if not requested or not requested.issubset(_SCOPES):
            raise RegistryAuditValidationError("scopes contains an unsupported scope.")
        object.__setattr__(self, "scopes", tuple(scope for scope in _SCOPES if scope in requested))
        if self.school_year is not None:
            if not isinstance(self.school_year, str):
                raise RegistryAuditValidationError(
                    "school_year must be a string or None."
                )
            try:
                object.__setattr__(self, "school_year", validate_school_year(self.school_year))
            except (SchoolYearValidationError, TypeError) as error:
                raise RegistryAuditValidationError(f"school_year is invalid: {error}") from error
        for name in ("class_id", "module_id", "work_id"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, str):
                    raise RegistryAuditValidationError(
                        f"{name} must be a string or None."
                    )
                try:
                    validated = validate_identifier(value, name)
                except IdentifierValidationError as error:
                    raise RegistryAuditValidationError(str(error)) from error
                if name == "module_id" and validated != validated.lower():
                    raise RegistryAuditValidationError("module_id must be lowercase.")
                object.__setattr__(self, name, validated)
        if self.publication_id is not None:
            if not isinstance(self.publication_id, str):
                raise RegistryAuditValidationError(
                    "publication_id must be a string or None."
                )
            if re.fullmatch(r"pub_[0-9a-f]{32}", self.publication_id) is None:
                raise RegistryAuditValidationError("publication_id is invalid.")
        for name in ("require_catalog", "require_producer_profiles", "discover_installed_producer_profiles"):
            if not isinstance(getattr(self, name), bool):
                raise RegistryAuditValidationError(f"{name} must be boolean.")


@dataclass(frozen=True, slots=True)
class RegistryAuditReport:
    schema_version: str
    generated_at: datetime
    workspace_root: Path
    scopes: tuple[RegistryAuditScope, ...]
    canonical_valid: bool
    manifests_valid: bool | None
    contracts_compatible: bool | None
    catalog_ready: bool | None
    counts: RegistryAuditCounts
    findings: tuple[RegistryAuditFinding, ...]

    def __post_init__(self) -> None:
        if self.schema_version != REGISTRY_AUDIT_SCHEMA_VERSION:
            raise RegistryAuditValidationError('schema_version must be "1".')
        if not isinstance(self.generated_at, datetime) or self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise RegistryAuditValidationError("generated_at must be timezone-aware.")
        if not isinstance(self.workspace_root, Path) or not self.workspace_root.is_absolute():
            raise RegistryAuditValidationError("workspace_root must be an absolute Path.")
        options = RegistryAuditOptions(scopes=self.scopes)
        object.__setattr__(self, "scopes", options.scopes)
        if not isinstance(self.canonical_valid, bool):
            raise RegistryAuditValidationError("canonical_valid must be boolean.")
        for name in ("manifests_valid", "contracts_compatible", "catalog_ready"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), bool):
                raise RegistryAuditValidationError(f"{name} must be boolean or None.")
        if not isinstance(self.counts, RegistryAuditCounts):
            raise RegistryAuditValidationError("counts must be RegistryAuditCounts.")
        if isinstance(self.findings, (str, bytes, Mapping)):
            raise RegistryAuditValidationError("findings must be an iterable of findings.")
        try:
            raw_findings = tuple(self.findings)
        except TypeError as error:
            raise RegistryAuditValidationError("findings must be iterable.") from error
        if any(not isinstance(value, RegistryAuditFinding) for value in raw_findings):
            raise RegistryAuditValidationError("findings contains an invalid value.")
        ordered = tuple(sorted(raw_findings, key=_finding_key))
        object.__setattr__(self, "findings", ordered)
        scope_states = {
            "manifests": self.manifests_valid,
            "contracts": self.contracts_compatible,
            "catalog": self.catalog_ready,
        }
        for scope, value in scope_states.items():
            if (scope in self.scopes) != (value is not None):
                raise RegistryAuditValidationError(
                    f"{scope} scope and its validity value disagree."
                )
        expected = Counter(finding.severity for finding in ordered)
        if (
            self.counts.info_findings != expected["info"]
            or self.counts.warning_findings != expected["warning"]
            or self.counts.error_findings != expected["error"]
        ):
            raise RegistryAuditValidationError(
                "finding counts disagree with findings."
            )
        canonical_error = any(
            finding.severity == "error"
            and finding.domain in {"academic_periods", "registrations", "publications"}
            for finding in ordered
        )
        if self.canonical_valid == canonical_error:
            raise RegistryAuditValidationError(
                "canonical_valid disagrees with canonical findings."
            )
        for scope, domain, value in (
            ("manifests", "manifests", self.manifests_valid),
            ("contracts", "contracts", self.contracts_compatible),
            ("catalog", "catalog", self.catalog_ready),
        ):
            if scope in self.scopes:
                has_error = any(
                    finding.severity == "error" and finding.domain == domain
                    for finding in ordered
                )
                if value == has_error:
                    raise RegistryAuditValidationError(
                        f"{scope} validity disagrees with findings."
                    )

    @property
    def ok(self) -> bool:
        return self.canonical_valid and all(value is not False for value in (self.manifests_valid, self.contracts_compatible, self.catalog_ready)) and not any(finding.severity == "error" and finding.domain == "locks" for finding in self.findings)


@dataclass(frozen=True, slots=True)
class RegistryLockObservation:
    lock_id: str
    lock_kind: str
    relative_path: str
    size_bytes: int
    sha256: str
    modified_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "lock_id", _single_line(self.lock_id, "lock_id"))
        object.__setattr__(self, "lock_kind", _single_line(self.lock_kind, "lock_kind"))
        kind, expected_path = _lock_identity(self.lock_id)
        if self.lock_kind != kind:
            raise RegistryAuditValidationError("lock_id and lock_kind disagree.")
        relative_path = _relative_path(self.relative_path)
        if relative_path != expected_path:
            raise RegistryAuditValidationError("relative_path disagrees with lock_id.")
        object.__setattr__(self, "relative_path", relative_path)
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise RegistryAuditValidationError("size_bytes must be nonnegative.")
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            raise RegistryAuditValidationError("sha256 must be lowercase hexadecimal.")
        if not isinstance(self.modified_at, datetime) or self.modified_at.tzinfo is None:
            raise RegistryAuditValidationError("modified_at must be timezone-aware.")


def _lock_identity(lock_id: str) -> tuple[str, str]:
    if not isinstance(lock_id, str):
        raise RegistryAuditValidationError("lock_id must be a string.")
    if lock_id == "catalog":
        return "catalog", "registry/.locks/catalog.lock"
    if lock_id.startswith("period:"):
        try:
            year = validate_school_year(lock_id[7:])
        except (SchoolYearValidationError, TypeError) as error:
            raise RegistryAuditValidationError(f"period lock ID is invalid: {error}") from error
        return "period", f"settings/academic_periods/{year}/.write.lock"
    if lock_id.startswith("registration:"):
        parts = lock_id[13:].split("/")
        if len(parts) != 3:
            raise RegistryAuditValidationError("registration lock ID is invalid.")
        try:
            work = ModuleWorkRef(parts[1], parts[0], parts[2])
        except ValueError as error:
            raise RegistryAuditValidationError(f"registration lock ID is invalid: {error}") from error
        return "registration", f"registry/work/{work.class_id}/{work.module_id}/{work.work_id}/.write.lock"
    if lock_id.startswith("publication:"):
        parts = lock_id[12:].split("/")
        if len(parts) != 5 or parts[3] not in {"academic_result_set", "intervention_record_set"}:
            raise RegistryAuditValidationError("publication lock ID is invalid.")
        try:
            work = ModuleWorkRef(parts[1], parts[0], parts[2])
            record_set_id = validate_identifier(parts[4], "record_set_id")
        except (ValueError, IdentifierValidationError) as error:
            raise RegistryAuditValidationError(f"publication lock ID is invalid: {error}") from error
        return "publication", f"registry/.locks/publications/{work.class_id}/{work.module_id}/{work.work_id}/{parts[3]}/{record_set_id}.lock"
    raise RegistryAuditValidationError("lock_id is not a supported stable lock ID.")


@dataclass(frozen=True, slots=True)
class RegistryStatus:
    workspace_root: Path
    counts: RegistryAuditCounts
    canonical_valid: bool
    manifests_valid: bool | None
    contracts_compatible: bool | None
    catalog_path: Path
    catalog_state: str
    catalog_built_at: datetime | None
    catalog_source_snapshot_sha256: str | None
    catalog_sources_current: bool | None
    lock_count: int
    temporary_artifact_count: int
    findings: tuple[RegistryAuditFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_root, Path) or not self.workspace_root.is_absolute():
            raise RegistryAuditValidationError("workspace_root must be an absolute Path.")
        if not isinstance(self.counts, RegistryAuditCounts):
            raise RegistryAuditValidationError("counts must be RegistryAuditCounts.")
        if not isinstance(self.canonical_valid, bool):
            raise RegistryAuditValidationError("canonical_valid must be boolean.")
        for name in ("manifests_valid", "contracts_compatible", "catalog_sources_current"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise RegistryAuditValidationError(f"{name} must be boolean or None.")
        if not isinstance(self.catalog_path, Path) or not self.catalog_path.is_absolute():
            raise RegistryAuditValidationError("catalog_path must be an absolute Path.")
        object.__setattr__(self, "catalog_state", _single_line(self.catalog_state, "catalog_state"))
        if self.catalog_built_at is not None and (
            not isinstance(self.catalog_built_at, datetime)
            or self.catalog_built_at.tzinfo is None
            or self.catalog_built_at.utcoffset() is None
        ):
            raise RegistryAuditValidationError(
                "catalog_built_at must be timezone-aware or None."
            )
        if self.catalog_source_snapshot_sha256 is not None and (
            not isinstance(self.catalog_source_snapshot_sha256, str)
            or _SHA256.fullmatch(self.catalog_source_snapshot_sha256) is None
        ):
            raise RegistryAuditValidationError(
                "catalog_source_snapshot_sha256 must be SHA-256 or None."
            )
        for name in ("lock_count", "temporary_artifact_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RegistryAuditValidationError(f"{name} must be nonnegative.")
        if isinstance(self.findings, (str, bytes, Mapping)):
            raise RegistryAuditValidationError("findings must be an iterable of findings.")
        try:
            raw_findings = tuple(self.findings)
        except TypeError as error:
            raise RegistryAuditValidationError("findings must be iterable.") from error
        if any(not isinstance(value, RegistryAuditFinding) for value in raw_findings):
            raise RegistryAuditValidationError("findings contains an invalid value.")
        object.__setattr__(self, "findings", tuple(sorted(raw_findings, key=_finding_key)))
        expected = Counter(finding.severity for finding in raw_findings)
        if (
            self.counts.info_findings != expected["info"]
            or self.counts.warning_findings != expected["warning"]
            or self.counts.error_findings != expected["error"]
        ):
            raise RegistryAuditValidationError(
                "finding counts disagree with findings."
            )

    @property
    def ok(self) -> bool:
        return (
            self.canonical_valid
            and all(
                value is not False
                for value in (self.manifests_valid, self.contracts_compatible)
            )
            and not any(finding.severity == "error" for finding in self.findings)
        )


@dataclass(frozen=True, slots=True)
class RegistryLockClearResult:
    lock: RegistryLockObservation
    dry_run: bool
    removed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.lock, RegistryLockObservation):
            raise RegistryAuditValidationError(
                "lock must be a RegistryLockObservation."
            )
        if not isinstance(self.dry_run, bool) or not isinstance(self.removed, bool):
            raise RegistryAuditValidationError(
                "dry_run and removed must be boolean."
            )
        if self.dry_run == self.removed:
            raise RegistryAuditValidationError(
                "dry_run and removed state is contradictory."
            )


@dataclass(frozen=True, slots=True)
class _LockFingerprint:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    sha256: str


@dataclass
class _State:
    findings: list[RegistryAuditFinding]
    calendars: list[AcademicPeriodCalendar]
    registrations: list[AcademicWorkRegistration]
    publications: list[PublicationRecord]
    withdrawals: list[PublicationWithdrawal]
    locks: list[RegistryLockObservation]
    relationship_fingerprints: dict[
        Path, tuple[int, int, int, int, int, int]
    ] = dataclass_field(default_factory=dict)
    manifest_fingerprints: dict[Path, tuple[int, int, int, int, int, int]] = dataclass_field(
        default_factory=dict
    )
    manifest_paths: dict[str, Path] = dataclass_field(default_factory=dict)
    manifest_lexical_fingerprints: dict[
        str, tuple[tuple[Path, int, int, int, int, int, int], ...]
    ] = dataclass_field(default_factory=dict)
    verified_manifests: int = 0
    catalog_source_files: int = 0
    catalog_state: str = "missing"
    catalog_built_at: datetime | None = None
    catalog_source_snapshot_sha256: str | None = None
    catalog_sources_current: bool | None = None


def _finding_key(value: RegistryAuditFinding) -> tuple[object, ...]:
    return (_SEVERITY_RANK[value.severity], value.domain, value.code, value.path is None, value.path or "", value.identity, value.message)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _add(state: _State, severity: AuditSeverity, domain: AuditDomain, code: str, message: str, root: Path, path: Path | None = None, *, repair: AuditRepairKind = "none", identity: tuple[tuple[str, str], ...] = ()) -> None:
    state.findings.append(RegistryAuditFinding(severity, domain, code, " ".join(str(message).splitlines()), None if path is None else _rel(root, path), identity=identity, repair=repair))


def _publication_finding_identity(
    root: Path,
    path: Path,
    publication_id: str,
) -> tuple[tuple[str, str], ...]:
    """Recover only validated primitive identity fields from an invalid envelope."""
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        if len({key for key, _value in pairs}) != len(pairs):
            raise ValueError("duplicate JSON key")
        return dict(pairs)

    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=unique_object
        )
        if not isinstance(raw, dict) or raw.get("publication_id") != publication_id:
            return ()
        work = raw.get("work")
        if not isinstance(work, dict):
            return ()
        raw_class_id = work.get("class_id")
        raw_module_id = work.get("module_id")
        raw_work_id = work.get("work_id")
        publication_kind = raw.get("publication_kind")
        raw_record_set_id = raw.get("record_set_id")
        if not all(
            isinstance(value, str)
            for value in (
                raw_class_id,
                raw_module_id,
                raw_work_id,
                raw_record_set_id,
            )
        ):
            return ()
        class_id = validate_identifier(cast(str, raw_class_id), "class_id")
        module_id = validate_identifier(cast(str, raw_module_id), "module_id")
        work_id = validate_identifier(cast(str, raw_work_id), "work_id")
        record_set_id = validate_identifier(
            cast(str, raw_record_set_id), "record_set_id"
        )
        if (
            module_id != module_id.lower()
            or publication_kind
            not in {"academic_result_set", "intervention_record_set"}
        ):
            return ()
        try:
            school_year = load_class_metadata_for_class(root, class_id).school_year
        except (FileNotFoundError, ValueError):
            school_year = ""
        return tuple(
            (key, value)
            for key, value in (
                ("publication_id", publication_id),
                ("class_id", class_id),
                ("module_id", module_id),
                ("work_id", work_id),
                ("school_year", school_year),
                ("publication_kind", cast(str, publication_kind)),
                ("record_set_id", record_set_id),
            )
            if value
        )
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return ()


def _valid_publication_identity(
    root: Path, record: PublicationRecord
) -> tuple[tuple[str, str], ...]:
    try:
        school_year = load_class_metadata_for_class(
            root, record.work.class_id
        ).school_year
    except (FileNotFoundError, ValueError):
        school_year = ""
    return tuple(
        (key, value)
        for key, value in (
            ("publication_id", record.publication_id),
            ("class_id", record.work.class_id),
            ("module_id", record.work.module_id),
            ("work_id", record.work.work_id),
            ("school_year", school_year),
            ("publication_kind", record.publication_kind),
            ("record_set_id", record.record_set_id),
        )
        if value
    )


def _entries(path: Path, domain: AuditDomain) -> tuple[Path, ...]:
    try:
        return tuple(sorted(path.iterdir(), key=lambda value: value.name))
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise RegistryAuditReadError(f"Could not enumerate required {domain} namespace {path}: {error}") from error


def _nested_entries(
    root: Path,
    path: Path,
    state: _State,
    domain: AuditDomain,
    code: str,
) -> tuple[Path, ...]:
    """Enumerate one nested subtree without aborting independent inspection."""
    try:
        status = path.lstat()
        if not stat.S_ISDIR(status.st_mode) or path.is_symlink():
            _add(
                state,
                "error",
                domain,
                code,
                "Canonical namespace is not a nonsymlink directory.",
                root,
                path,
                repair="manual_canonical_review",
            )
            return ()
        return tuple(sorted(path.iterdir(), key=lambda value: value.name))
    except FileNotFoundError:
        return ()
    except OSError as error:
        _add(
            state,
            "error",
            domain,
            code,
            f"Could not enumerate nested namespace: {error}",
            root,
            path,
            repair="manual_canonical_review",
        )
        return ()


def _regular_entry(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(status.st_mode) and not path.is_symlink()


def _directory_entry(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(status.st_mode) and not path.is_symlink()


def _path_fingerprint(path: Path) -> tuple[int, int, int, int, int, int]:
    status = path.lstat()
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _path_changed(path: Path, before: tuple[int, int, int, int, int, int]) -> bool:
    try:
        return _path_fingerprint(path) != before
    except OSError:
        return True


def _manifest_lexical_fingerprint(
    root: Path, publication: PublicationRecord
) -> tuple[tuple[Path, int, int, int, int, int, int], ...]:
    """Capture every lexical manifest component without following it for identity."""
    current = root
    result: list[tuple[Path, int, int, int, int, int, int]] = []
    for part in publication.manifest_path.split("/"):
        current = current / part
        status = current.lstat()
        result.append(
            (
                current,
                status.st_dev,
                status.st_ino,
                status.st_mode,
                status.st_size,
                status.st_mtime_ns,
                status.st_ctime_ns,
            )
        )
    return tuple(result)


def _scan_periods(root: Path, state: _State, options: RegistryAuditOptions) -> None:
    base = academic_periods_dir(root)
    for school_dir in _nested_entries(root, base, state, "academic_periods", "academic_periods.unreadable"):
        if school_dir.name.startswith("."):
            _add(state, "warning", "academic_periods", "academic_periods.hidden_artifact", "Hidden artifact requires review.", root, school_dir, repair="manual_canonical_review")
            continue
        try:
            school_year = validate_school_year(school_dir.name)
        except (SchoolYearValidationError, TypeError) as error:
            _add(state, "error", "academic_periods", "academic_periods.unexpected_entry", f"Invalid school-year entry: {error}", root, school_dir, repair="manual_canonical_review")
            continue
        if not _directory_entry(school_dir):
            _add(state, "error", "academic_periods", "academic_periods.unexpected_entry", "School-year entry is not a directory.", root, school_dir, repair="manual_canonical_review")
            continue
        for child in _nested_entries(root, school_dir, state, "academic_periods", "academic_periods.unreadable"):
            known = (
                (child.name == "revisions" and _directory_entry(child))
                or (child.name == "current.json" and _regular_entry(child))
                or child.name == ".write.lock"
            )
            if known:
                continue
            if child.name.startswith("."):
                _add(state, "warning", "academic_periods", "academic_periods.hidden_artifact", "Hidden Academic Period artifact requires review.", root, child, repair="manual_canonical_review")
            else:
                _add(state, "error", "academic_periods", "academic_periods.unexpected_entry", "Unexpected entry in school-year calendar directory.", root, child, repair="manual_canonical_review")
        revisions_dir = school_dir / "revisions"
        valid: list[AcademicPeriodCalendar] = []
        for entry in _nested_entries(root, revisions_dir, state, "academic_periods", "academic_periods.unreadable"):
            if entry.name.startswith("."):
                _add(state, "warning", "academic_periods", "academic_periods.hidden_artifact", "Hidden revision artifact requires review.", root, entry, repair="manual_canonical_review")
                continue
            match = _REVISION_NAME.fullmatch(entry.name)
            if match is None or not _regular_entry(entry):
                _add(state, "error", "academic_periods", "academic_periods.unexpected_entry", "Revision entry is not a canonical positive-integer JSON file.", root, entry, repair="manual_canonical_review")
                continue
            revision = int(match.group(1))
            try:
                before = _path_fingerprint(entry)
                calendar = load_academic_period_calendar_revision(root, school_year, revision)
                if _path_changed(entry, before):
                    _add(state, "error", "academic_periods", "academic_periods.changed_during_audit", "Academic Period revision changed during audit.", root, entry, repair="manual_canonical_review")
                    continue
                valid.append(calendar)
            except FileNotFoundError:
                _add(state, "error", "academic_periods", "academic_periods.changed_during_audit", "Academic Period revision disappeared during audit.", root, entry, repair="manual_canonical_review")
            except Exception as error:
                code = "academic_periods.changed_during_audit" if not entry.exists() else "academic_periods.revision_invalid"
                _add(state, "error", "academic_periods", code, f"Academic Period revision is invalid or changed: {error}", root, entry, repair="manual_canonical_review")
        valid.sort(key=lambda value: value.calendar_revision)
        for previous, candidate in zip(valid, valid[1:]):
            try:
                validate_academic_period_calendar_transition(previous, candidate)
            except AcademicPeriodValidationError as error:
                _add(state, "error", "academic_periods", "academic_periods.transition_invalid", f"Academic Period transition is invalid: {error}", root, revisions_dir / f"{candidate.calendar_revision}.json", repair="manual_canonical_review")
        pointer = school_dir / "current.json"
        pointer_before = None
        try:
            try:
                pointer_status = pointer.lstat()
            except FileNotFoundError:
                pointer_status = None
            if pointer_status is not None and (
                not stat.S_ISREG(pointer_status.st_mode) or pointer.is_symlink()
            ):
                raise ValueError("Current Academic Period pointer is not a nonsymlink regular file.")
            pointer_before = (
                _path_fingerprint(pointer) if pointer_status is not None else None
            )
            current = load_current_academic_period_calendar(root, school_year)
            if pointer_before is not None and _path_changed(pointer, pointer_before):
                _add(state, "error", "academic_periods", "academic_periods.changed_during_audit", "Academic Period pointer changed during audit.", root, pointer, repair="manual_canonical_review")
                current = None
        except Exception as error:
            code = "academic_periods.changed_during_audit" if pointer_before is not None and not pointer.exists() else ("academic_periods.pointer_missing" if isinstance(error, FileNotFoundError) else "academic_periods.pointer_invalid")
            _add(state, "error", "academic_periods", code, f"Current Academic Period pointer is invalid: {error}", root, pointer, repair="manual_canonical_review")
            current = None
        if valid and pointer_before is None:
            _add(state, "error", "academic_periods", "academic_periods.pointer_missing", "Calendar revisions exist without a current pointer.", root, pointer, repair="manual_canonical_review")
            _add(state, "error", "academic_periods", "academic_periods.orphan_revision", "Calendar revisions are orphaned because no current pointer exists.", root, revisions_dir, repair="manual_canonical_review")
        if current is not None and valid and current.calendar_revision != valid[-1].calendar_revision:
            _add(state, "error", "academic_periods", "academic_periods.pointer_invalid", "Current pointer does not select the final valid transition.", root, pointer, repair="manual_canonical_review")
            _add(state, "error", "academic_periods", "academic_periods.orphan_revision", "Current pointer does not select the final valid revision.", root, pointer, repair="manual_canonical_review")
        if options.school_year is None or options.school_year == school_year:
            state.calendars.extend(valid)


def _valid_work_path(root: Path, state: _State) -> list[tuple[ModuleWorkRef, Path]]:
    result: list[tuple[ModuleWorkRef, Path]] = []
    base = academic_work_registrations_dir(root)
    for class_dir in _nested_entries(root, base, state, "registrations", "registrations.unreadable"):
        if class_dir.name.startswith(".") or not _directory_entry(class_dir):
            _add(state, "warning" if class_dir.name.startswith(".") else "error", "registrations", "registrations.hidden_artifact" if class_dir.name.startswith(".") else "registrations.unexpected_entry", "Unexpected registration class entry.", root, class_dir, repair="manual_canonical_review")
            continue
        try:
            class_id = validate_identifier(class_dir.name, "class_id")
        except IdentifierValidationError as error:
            _add(state, "error", "registrations", "registrations.unexpected_entry", str(error), root, class_dir, repair="manual_canonical_review")
            continue
        for module_dir in _nested_entries(root, class_dir, state, "registrations", "registrations.unreadable"):
            try:
                module_id = validate_identifier(module_dir.name, "module_id")
                if module_id != module_id.lower() or not _directory_entry(module_dir):
                    raise ValueError("module_id must be lowercase and identify a directory.")
            except (IdentifierValidationError, ValueError) as error:
                if module_dir.name.startswith("."):
                    _add(state, "warning", "registrations", "registrations.hidden_artifact", "Hidden registration module artifact requires review.", root, module_dir, repair="manual_canonical_review")
                    continue
                _add(state, "error", "registrations", "registrations.unexpected_entry", str(error), root, module_dir, repair="manual_canonical_review")
                continue
            for work_dir in _nested_entries(root, module_dir, state, "registrations", "registrations.unreadable"):
                try:
                    work_id = validate_identifier(work_dir.name, "work_id")
                    if not _directory_entry(work_dir):
                        raise ValueError("work entry is not a directory.")
                    result.append((ModuleWorkRef(module_id, class_id, work_id), work_dir))
                except (IdentifierValidationError, ValueError) as error:
                    if work_dir.name.startswith("."):
                        _add(state, "warning", "registrations", "registrations.hidden_artifact", "Hidden registration work artifact requires review.", root, work_dir, repair="manual_canonical_review")
                        continue
                    _add(state, "error", "registrations", "registrations.unexpected_entry", str(error), root, work_dir, repair="manual_canonical_review")
    return result


def _scan_registrations(root: Path, state: _State, options: RegistryAuditOptions) -> None:
    for work, work_dir in _valid_work_path(root, state):
        try:
            school_year = load_class_metadata_for_class(
                root, work.class_id
            ).school_year
        except (FileNotFoundError, ValueError):
            school_year = None
        selected = (
            options.class_id in (None, work.class_id)
            and options.module_id in (None, work.module_id)
            and options.work_id in (None, work.work_id)
            and options.school_year in (None, school_year)
        )
        if not selected:
            continue
        for child in _nested_entries(root, work_dir, state, "registrations", "registrations.unreadable"):
            known = (
                (child.name == "revisions" and _directory_entry(child))
                or (child.name == "current.json" and _regular_entry(child))
                or child.name == ".write.lock"
            )
            if known:
                continue
            if child.name.startswith("."):
                _add(state, "warning", "registrations", "registrations.hidden_artifact", "Hidden registration artifact requires review.", root, child, repair="manual_canonical_review")
            else:
                _add(state, "error", "registrations", "registrations.unexpected_entry", "Unexpected entry in registration work directory.", root, child, repair="manual_canonical_review")
        valid: list[AcademicWorkRegistration] = []
        revisions_dir = work_dir / "revisions"
        for entry in _nested_entries(root, revisions_dir, state, "registrations", "registrations.unreadable"):
            if entry.name.startswith("."):
                _add(state, "warning", "registrations", "registrations.hidden_artifact", "Hidden registration artifact requires review.", root, entry, repair="manual_canonical_review")
                continue
            match = _REVISION_NAME.fullmatch(entry.name)
            if match is None or not _regular_entry(entry):
                _add(state, "error", "registrations", "registrations.unexpected_entry", "Revision entry is not a canonical positive-integer JSON file.", root, entry, repair="manual_canonical_review")
                continue
            try:
                before = _path_fingerprint(entry)
                registration = load_academic_work_registration_revision(root, work, int(match.group(1)))
                if _path_changed(entry, before):
                    _add(state, "error", "registrations", "registrations.changed_during_audit", "Registration revision changed during audit.", root, entry, repair="manual_canonical_review")
                    continue
                valid.append(registration)
            except FileNotFoundError:
                _add(state, "error", "registrations", "registrations.changed_during_audit", "Registration revision disappeared during audit.", root, entry, repair="manual_canonical_review")
            except Exception as error:
                code = "registrations.changed_during_audit" if not entry.exists() else "registrations.revision_invalid"
                _add(state, "error", "registrations", code, f"Registration revision is invalid or changed: {error}", root, entry, repair="manual_canonical_review")
        valid.sort(key=lambda value: value.registration_revision)
        for previous, candidate in zip(valid, valid[1:]):
            try:
                validate_academic_work_registration_transition(previous, candidate)
            except AcademicWorkRegistrationValidationError as error:
                _add(state, "error", "registrations", "registrations.transition_invalid", f"Registration transition is invalid: {error}", root, revisions_dir / f"{candidate.registration_revision}.json", repair="manual_canonical_review")
        pointer = work_dir / "current.json"
        pointer_before = None
        try:
            try:
                pointer_status = pointer.lstat()
            except FileNotFoundError:
                pointer_status = None
            if pointer_status is not None and (
                not stat.S_ISREG(pointer_status.st_mode) or pointer.is_symlink()
            ):
                raise ValueError("Current registration pointer is not a nonsymlink regular file.")
            pointer_before = (
                _path_fingerprint(pointer) if pointer_status is not None else None
            )
            current = load_current_academic_work_registration(root, work)
            if pointer_before is not None and _path_changed(pointer, pointer_before):
                _add(state, "error", "registrations", "registrations.changed_during_audit", "Registration pointer changed during audit.", root, pointer, repair="manual_canonical_review")
                current = None
        except Exception as error:
            code = "registrations.changed_during_audit" if pointer_before is not None and not pointer.exists() else "registrations.pointer_invalid"
            _add(state, "error", "registrations", code, f"Current registration pointer is invalid or changed: {error}", root, pointer, repair="manual_canonical_review")
            current = None
        if valid and pointer_before is None:
            _add(state, "error", "registrations", "registrations.pointer_missing", "Registration revisions exist without a current pointer.", root, pointer, repair="manual_canonical_review")
            _add(state, "error", "registrations", "registrations.orphan_revision", "Registration revisions are orphaned because no current pointer exists.", root, revisions_dir, repair="manual_canonical_review")
        if current is not None and valid and current.registration_revision != valid[-1].registration_revision:
            _add(state, "error", "registrations", "registrations.pointer_invalid", "Current pointer does not select the final valid transition.", root, pointer, repair="manual_canonical_review")
            _add(state, "error", "registrations", "registrations.orphan_revision", "Current pointer does not select the final valid revision.", root, pointer, repair="manual_canonical_review")
        producer_root = module_work_dir(root, work)
        if not _directory_entry(producer_root):
            _add(state, "error", "registrations", "registrations.producer_work_missing", "Producer work root is missing or is not a directory.", root, producer_root, repair="producer_action")
        state.registrations.extend(valid)


def _scan_publications(root: Path, state: _State, options: RegistryAuditOptions) -> None:
    all_publications: list[PublicationRecord] = []
    for entry in _nested_entries(root, publications_dir(root), state, "publications", "publications.unreadable"):
        match = _PUB_NAME.fullmatch(entry.name)
        if match is None or not _regular_entry(entry):
            _add(state, "error", "publications", "publications.unexpected_entry", "Publication entry is not a canonical publication JSON file.", root, entry, repair="manual_canonical_review")
            continue
        try:
            before = _path_fingerprint(entry)
            record = load_publication_record(root, match.group(1))
            if _path_changed(entry, before):
                _add(state, "error", "publications", "publications.changed_during_audit", "Publication Record changed during audit.", root, entry, repair="manual_canonical_review")
                continue
            all_publications.append(record)
        except Exception as error:
            code = "publications.changed_during_audit" if not entry.exists() else "publications.record_invalid"
            identity = _publication_finding_identity(root, entry, match.group(1))
            _add(state, "error", "publications", code, f"Publication Record is invalid or changed: {error}", root, entry, repair="manual_canonical_review", identity=identity)
    selected = [
        record for record in all_publications
        if options.class_id in (None, record.work.class_id)
        and options.module_id in (None, record.work.module_id)
        and options.work_id in (None, record.work.work_id)
    ]
    if options.school_year is not None:
        school_selected: list[PublicationRecord] = []
        for record in selected:
            try:
                year = load_class_metadata_for_class(
                    root, record.work.class_id
                ).school_year
            except (FileNotFoundError, ValueError):
                year = None
            if year == options.school_year:
                school_selected.append(record)
        selected = school_selected
    if options.publication_id is not None:
        target = next(
            (record for record in all_publications if record.publication_id == options.publication_id),
            None,
        )
        if target is not None and target in selected:
            selected = [
                record for record in all_publications
                if (record.work, record.publication_kind, record.record_set_id)
                == (target.work, target.publication_kind, target.record_set_id)
            ]
        else:
            selected = []
        target_path = publications_dir(root) / f"{options.publication_id}.json"
        target_has_finding = any(
            finding.path == _rel(root, target_path)
            and finding.code
            in {
                "publications.record_invalid",
                "publications.changed_during_audit",
                "publications.unexpected_entry",
            }
            for finding in state.findings
        )
        if target is None and not target_has_finding:
            _add(
                state,
                "error",
                "publications",
                "publications.not_found",
                f"Publication Record does not exist: {options.publication_id}",
                root,
                publications_dir(root) / f"{options.publication_id}.json",
                repair="manual_canonical_review",
            )
    state.publications.extend(selected)
    observed_relationships = {
        (registration.work, registration.registration_revision)
        for registration in state.registrations
    }
    for record in state.publications:
        if record.publication_kind != "academic_result_set":
            continue
        revision = record.academic_work_registration_revision
        path = (
            publications_dir(root) / f"{record.publication_id}.json"
            if revision is None
            else academic_work_registration_revision_path(
                root, record.work, revision
            )
        )
        if revision is None:
            _add(state, "error", "publications", "publications.registration_missing", "Academic publication does not identify its required registration revision.", root, path, repair="manual_canonical_review")
            continue
        relationship_identity = (record.work, revision)
        if relationship_identity in observed_relationships:
            continue
        try:
            before = _path_fingerprint(path)
            registration = load_academic_work_registration_revision(
                root, record.work, revision
            )
            if (
                registration.work != record.work
                or registration.registration_revision != revision
            ):
                raise ValueError("Referenced registration identity is contradictory.")
            if _path_changed(path, before):
                raise FileNotFoundError("Referenced registration changed during inspection.")
            state.relationship_fingerprints[path] = before
            state.registrations.append(registration)
            observed_relationships.add(relationship_identity)
        except Exception:
            _add(state, "error", "publications", "publications.registration_missing", "Referenced Academic Work Registration revision is missing, invalid, or changed.", root, path, repair="manual_canonical_review", identity=_valid_publication_identity(root, record))
    identities: dict[tuple[object, ...], list[PublicationRecord]] = {}
    series: dict[tuple[object, ...], list[PublicationRecord]] = {}
    for record in state.publications:
        logical = (record.work, record.publication_kind, record.record_set_id, record.record_set_revision)
        identities.setdefault(logical, []).append(record)
        series.setdefault((record.work, record.publication_kind, record.record_set_id), []).append(record)
    for records in identities.values():
        if len(records) > 1:
            for record in records:
                _add(state, "error", "publications", "publications.logical_revision_duplicate", "Duplicate logical publication revision.", root, publications_dir(root) / f"{record.publication_id}.json", repair="manual_canonical_review")
    for records in series.values():
        try:
            validate_publication_record_series(records)
        except PublicationRecordValidationError as error:
            for record in records:
                _add(state, "error", "publications", "publications.series_invalid", f"Publication series is invalid: {error}", root, publications_dir(root) / f"{record.publication_id}.json", repair="manual_canonical_review")
        predecessors = {record.supersedes_publication_id for record in records if record.supersedes_publication_id is not None}
        heads = [record for record in records if record.publication_id not in predecessors]
        if len(heads) > 1:
            for record in heads:
                _add(state, "error", "publications", "publications.competing_head", "Publication series has competing heads.", root, publications_dir(root) / f"{record.publication_id}.json", repair="manual_canonical_review")
    for entry in _nested_entries(root, publication_withdrawals_dir(root), state, "publications", "publications.unreadable"):
        match = _PUB_NAME.fullmatch(entry.name)
        if match is None or not _regular_entry(entry):
            _add(state, "error", "publications", "publications.withdrawal_invalid", "Withdrawal entry is not a canonical JSON file.", root, entry, repair="manual_canonical_review")
            continue
        publication = next(
            (
                record
                for record in all_publications
                if match is not None and record.publication_id == match.group(1)
            ),
            None,
        )
        try:
            before = _path_fingerprint(entry)
            withdrawal = load_publication_withdrawal(root, match.group(1))
            if _path_changed(entry, before):
                _add(state, "error", "publications", "publications.changed_during_audit", "Publication withdrawal changed during audit.", root, entry, repair="manual_canonical_review")
                continue
            if withdrawal is None:
                continue
            publication = next((record for record in all_publications if record.publication_id == withdrawal.publication_id), None)
            if publication is None:
                _add(state, "error", "publications", "publications.withdrawal_orphan", "Withdrawal has no valid Publication Record.", root, entry, repair="manual_canonical_review")
            else:
                validate_publication_withdrawal_relationship(publication, withdrawal)
            if publication is None or publication in state.publications:
                state.withdrawals.append(withdrawal)
        except PublicationRecordValidationError as error:
            code = "publications.changed_during_audit" if not entry.exists() else "publications.withdrawal_chronology_invalid"
            identity = () if publication is None else _valid_publication_identity(root, publication)
            _add(state, "error", "publications", code, f"Withdrawal relationship is invalid or changed: {error}", root, entry, repair="manual_canonical_review", identity=identity)
        except Exception as error:
            code = "publications.changed_during_audit" if not entry.exists() else "publications.withdrawal_invalid"
            identity = () if publication is None else _valid_publication_identity(root, publication)
            _add(state, "error", "publications", code, f"Withdrawal is invalid or changed: {error}", root, entry, repair="manual_canonical_review", identity=identity)


def _scan_manifests(root: Path, state: _State) -> None:
    successful: dict[
        tuple[str, str], tuple[int, int, int, int, int, int]
    ] = {}
    for publication in state.publications:
        candidate = root.joinpath(*publication.manifest_path.split("/"))
        try:
            resolved = resolve_publication_manifest_path(root, publication)
            state.manifest_lexical_fingerprints[publication.publication_id] = (
                _manifest_lexical_fingerprint(root, publication)
            )
        except PublicationManifestNotFoundError as error:
            try:
                candidate_status = candidate.lstat()
            except FileNotFoundError:
                code = "manifests.missing"
            except OSError:
                code = "manifests.unreadable"
            else:
                code = (
                    "manifests.not_regular_file"
                    if not stat.S_ISREG(candidate_status.st_mode)
                    else "manifests.missing"
                )
            _add(state, "error", "manifests", code, str(error), root, candidate, repair="producer_action")
            continue
        except PublicationManifestIntegrityError as error:
            _add(state, "error", "manifests", "manifests.path_escape", str(error), root, candidate, repair="producer_action")
            continue
        except (PublicationManifestError, OSError) as error:
            _add(state, "error", "manifests", "manifests.unreadable", str(error), root, candidate, repair="producer_action")
            continue
        key = (resolved.as_posix(), publication.manifest_digest)
        if key in successful:
            state.manifest_paths[publication.publication_id] = resolved
            state.manifest_fingerprints[resolved] = successful[key]
            state.verified_manifests += 1
            continue
        before: tuple[int, int, int, int, int, int] | None = None
        try:
            before = _path_fingerprint(resolved)
            state.manifest_paths[publication.publication_id] = resolved
            state.manifest_fingerprints[resolved] = before
            verified = verify_publication_manifest(root, publication)
            if verified != resolved or _path_changed(resolved, before):
                _add(state, "error", "manifests", "manifests.changed_during_audit", "Publication manifest changed during verification.", root, candidate, repair="producer_action")
                continue
        except PublicationManifestIntegrityError as error:
            code = (
                "manifests.changed_during_audit"
                if before is not None and _path_changed(resolved, before)
                else "manifests.digest_mismatch"
            )
            _add(state, "error", "manifests", code, str(error), root, candidate, repair="producer_action")
            continue
        except (PublicationManifestNotFoundError, FileNotFoundError) as error:
            _add(state, "error", "manifests", "manifests.changed_during_audit", str(error), root, candidate, repair="producer_action")
            continue
        except (PublicationManifestError, OSError) as error:
            _add(state, "error", "manifests", "manifests.unreadable", str(error), root, candidate, repair="producer_action")
            continue
        successful[key] = before
        state.verified_manifests += 1


def _scan_contracts(root: Path, state: _State, options: RegistryAuditOptions, profiles: Iterable[PublicationProducerProfile]) -> None:
    try:
        registry = build_publication_producer_registry(explicit_profiles=profiles, discover_installed=options.discover_installed_producer_profiles)
    except PublicationCompatibilityError as error:
        _add(state, "error", "contracts", "contracts.profile_discovery_failed", f"Producer profile discovery failed: {error}", root, repair="producer_action")
        return
    for publication in state.publications:
        profile = registry.get(publication.work.module_id)
        path = publications_dir(root) / f"{publication.publication_id}.json"
        if profile is None:
            _add(state, "error" if options.require_producer_profiles else "info", "contracts", "contracts.profile_unavailable", "No producer compatibility profile is available; the shared envelope remains valid.", root, path, repair="producer_action" if options.require_producer_profiles else "none")
            continue
        registration = next(
            (
                item
                for item in state.registrations
                if item.work == publication.work
                and item.registration_revision
                == publication.academic_work_registration_revision
            ),
            None,
        )
        result = evaluate_publication_compatibility(publication, profile, registration)
        for code in result.codes:
            _add(state, "error", "contracts", code, "Publication metadata is incompatible with the installed producer profile.", root, path, repair="producer_action")


def _scan_catalog(root: Path, state: _State, options: RegistryAuditOptions) -> None:
    path = academic_catalog_path(root)
    try:
        catalog_status = path.lstat()
    except FileNotFoundError:
        _add(state, "error" if options.require_catalog else "warning", "catalog", "catalog.missing", "Derived academic catalog is absent; canonical records remain authoritative.", root, path, repair="rebuild_catalog")
        return
    except OSError as error:
        _add(state, "error", "catalog", "catalog.unreadable", str(error), root, path, repair="rebuild_catalog")
        return
    if not stat.S_ISREG(catalog_status.st_mode) or path.is_symlink():
        _add(state, "error", "catalog", "catalog.incompatible", "Catalog must be a nonsymlink regular file.", root, path, repair="rebuild_catalog")
        return
    state.catalog_state = "invalid"
    state.catalog_sources_current = False
    try:
        catalog_before = _path_fingerprint(path)
    except FileNotFoundError:
        _add(state, "error", "catalog", "catalog.changed_during_audit", "Catalog disappeared during audit.", root, path, repair="rebuild_catalog")
        return
    except OSError as error:
        _add(state, "error", "catalog", "catalog.unreadable", str(error), root, path, repair="rebuild_catalog")
        return
    try:
        metadata = academic_catalog.load_academic_catalog_metadata(root)
    except academic_catalog.AcademicCatalogCompatibilityError as error:
        _add(state, "error", "catalog", "catalog.incompatible", str(error), root, path, repair="rebuild_catalog")
        return
    except academic_catalog.AcademicCatalogIntegrityError as error:
        _add(state, "error", "catalog", "catalog.integrity_invalid", str(error), root, path, repair="rebuild_catalog")
        return
    except Exception as error:
        _add(state, "error", "catalog", "catalog.unreadable", str(error), root, path, repair="rebuild_catalog")
        return
    state.catalog_source_files = metadata.source_file_count
    state.catalog_built_at = metadata.built_at_utc
    state.catalog_source_snapshot_sha256 = metadata.source_snapshot_sha256
    try:
        projection = academic_catalog._load_projection(root)
        current_metadata = academic_catalog._metadata(projection, metadata.built_at_utc)
        current_sources = {
            source.relative_path: (source.size_bytes, source.sha256)
            for source in projection.sources
        }
        connection = academic_catalog._read_connection(path)
        try:
            stored_sources = {
                str(row[0]): (int(row[1]), str(row[2]))
                for row in connection.execute(
                    "SELECT relative_path,size_bytes,sha256 "
                    "FROM catalog_sources ORDER BY relative_path"
                )
            }
            stored_publications = {
                str(row[0])
                for row in connection.execute(
                    "SELECT publication_id FROM publications"
                )
            }
            stored_registrations = {
                (str(row[0]), str(row[1]), str(row[2]), int(row[3]))
                for row in connection.execute(
                    "SELECT class_id,module_id,work_id,registration_revision "
                    "FROM academic_work_registrations"
                )
            }
            stored_calendars = {
                (str(row[0]), int(row[1]))
                for row in connection.execute(
                    "SELECT school_year,calendar_revision "
                    "FROM academic_period_calendars"
                )
            }
        finally:
            connection.close()
        for relative in sorted(current_sources.keys() - stored_sources.keys()):
            _add(state, "error", "catalog", "catalog.source_missing", "Canonical source is absent from catalog inventory.", root, root / relative, repair="rebuild_catalog")
        for relative in sorted(stored_sources.keys() - current_sources.keys()):
            _add(state, "error", "catalog", "catalog.source_extra", "Catalog source is absent from canonical state.", root, root / relative, repair="rebuild_catalog")
        for relative in sorted(current_sources.keys() & stored_sources.keys()):
            if current_sources[relative] != stored_sources[relative]:
                _add(state, "error", "catalog", "catalog.source_changed", "Canonical source size or digest differs from catalog inventory.", root, root / relative, repair="rebuild_catalog")
        canonical_publications = {record.publication_id for record in projection.publications}
        canonical_registrations = {(record.work.class_id, record.work.module_id, record.work.work_id, record.registration_revision) for record, _ in projection.registrations}
        canonical_calendars = {(calendar.school_year, calendar.calendar_revision) for calendar, _ in projection.calendars}
        if canonical_publications - stored_publications or canonical_registrations - stored_registrations or canonical_calendars - stored_calendars:
            _add(state, "error", "catalog", "catalog.canonical_entity_missing", "One or more canonical entities are absent from catalog rows.", root, path, repair="rebuild_catalog")
        if stored_publications - canonical_publications or stored_registrations - canonical_registrations or stored_calendars - canonical_calendars:
            _add(state, "error", "catalog", "catalog.orphan_entity", "One or more catalog rows are absent from canonical state.", root, path, repair="rebuild_catalog")
        class_years = {class_id: school_year for class_id, school_year, _, _, _ in projection.classes}
        expected_periods = tuple(sorted((
            academic_catalog.CatalogAcademicPeriod(
                calendar.school_year,
                calendar.calendar_revision,
                calendar.schema_version,
                calendar.created_at,
                calendar.updated_at,
                is_current,
                period,
            )
            for calendar, is_current in projection.calendars
            for period in calendar.periods
        ), key=lambda value: (value.school_year, value.calendar_revision, value.sequence, value.period_id)))
        actual_periods = tuple(sorted(
            academic_catalog.query_academic_period_catalog(
                root,
                academic_catalog.AcademicPeriodCatalogQuery(current_calendar_only=False),
            ),
            key=lambda value: (value.school_year, value.calendar_revision, value.sequence, value.period_id),
        ))
        registration_by_key = {
            (registration.work, registration.registration_revision): registration
            for registration, _ in projection.registrations
        }
        current_registration = {
            registration.work: registration
            for registration, is_current in projection.registrations
            if is_current
        }
        expected_registrations = tuple(sorted((
            academic_catalog.CatalogAcademicWorkRegistration(
                class_years.get(registration.work.class_id),
                registration.work,
                registration.registration_revision,
                registration.schema_version,
                registration.producer_contract_version,
                registration.title,
                registration.work_kind,
                registration.academic_intent,
                registration.lifecycle,
                registration.created_at,
                registration.updated_at,
                is_current,
                registration.source_records,
            )
            for registration, is_current in projection.registrations
        ), key=lambda value: (value.class_id, value.module_id, value.work_id, value.registration_revision)))
        actual_registrations = tuple(sorted(
            academic_catalog.query_academic_work_registration_catalog(
                root,
                academic_catalog.AcademicWorkRegistrationCatalogQuery(current_only=False),
            ),
            key=lambda value: (value.class_id, value.module_id, value.work_id, value.registration_revision),
        ))
        withdrawal_by_id = {value.publication_id: value for value in projection.withdrawals}
        expected_publications = []
        for publication in projection.publications:
            referenced = None
            if publication.academic_work_registration_revision is not None:
                referenced = registration_by_key.get((publication.work, publication.academic_work_registration_revision))
            current = current_registration.get(publication.work)
            withdrawal = withdrawal_by_id.get(publication.publication_id)
            is_head = publication.publication_id in projection.heads
            expected_publications.append(
                academic_catalog.CatalogPublication(
                    class_years.get(publication.work.class_id),
                    publication.publication_id,
                    publication.work,
                    publication.source_record,
                    publication.publication_kind,
                    publication.capabilities,
                    publication.record_set_id,
                    publication.record_set_revision,
                    publication.manifest_contract_version,
                    publication.manifest_path,
                    publication.manifest_digest_algorithm,
                    publication.manifest_digest,
                    publication.published_at,
                    publication.academic_work_registration_revision,
                    None if referenced is None else referenced.lifecycle,
                    None if current is None else current.registration_revision,
                    None if current is None else current.lifecycle,
                    publication.supersedes_publication_id,
                    is_head,
                    withdrawal is not None,
                    None if withdrawal is None else withdrawal.withdrawn_at,
                    is_head and withdrawal is None,
                )
            )
        expected_publication_rows = tuple(sorted(expected_publications, key=lambda value: value.publication_id))
        actual_publications = tuple(sorted(
            academic_catalog.query_publication_catalog(
                root,
                academic_catalog.PublicationCatalogQuery(state="all"),
            ),
            key=lambda value: value.publication_id,
        ))
        if expected_periods != actual_periods or expected_registrations != actual_registrations or expected_publication_rows != actual_publications:
            _add(state, "error", "catalog", "catalog.snapshot_mismatch", "Catalog entity rows disagree with the canonical projection.", root, path, repair="rebuild_catalog")
        if metadata.source_snapshot_sha256 != current_metadata.source_snapshot_sha256:
            _add(state, "error", "catalog", "catalog.snapshot_mismatch", "Catalog source snapshot differs from current canonical bytes.", root, path, repair="rebuild_catalog")
        if metadata.source_file_count != current_metadata.source_file_count:
            _add(state, "error", "catalog", "catalog.source_changed", "Catalog source-file count differs from canonical state.", root, path, repair="rebuild_catalog")
        for name in ("calendar_revision_count", "period_count", "registration_revision_count", "publication_count", "withdrawal_count"):
            if getattr(metadata, name) != getattr(current_metadata, name):
                _add(state, "error", "catalog", "catalog.canonical_entity_missing", f"Catalog {name} differs from canonical state.", root, path, repair="rebuild_catalog")
        if _path_changed(path, catalog_before):
            _add(state, "error", "catalog", "catalog.changed_during_audit", "Catalog changed during audit.", root, path, repair="rebuild_catalog")
    except Exception as error:
        code = "catalog.changed_during_audit" if _path_changed(path, catalog_before) else "catalog.source_changed"
        _add(state, "error", "catalog", code, f"Could not compare catalog with canonical state: {error}", root, path, repair="rebuild_catalog")
    catalog_has_error = any(
        finding.severity == "error" and finding.domain == "catalog"
        for finding in state.findings
    )
    state.catalog_state = "invalid" if catalog_has_error else "ready"
    state.catalog_sources_current = not catalog_has_error


def _observe_lock(root: Path, state: _State, lock_id: str, lock_kind: str, path: Path) -> None:
    if any(item.lock_id == lock_id for item in state.locks):
        return
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or path.is_symlink():
            raise OSError("lock is not a regular file")
        content = path.read_bytes()
        after = path.lstat()
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity or len(content) != after.st_size:
            _add(state, "error", "locks", "locks.changed", "Lock changed during inspection.", root, path, repair="clear_lock")
            return
        observed = RegistryLockObservation(lock_id, lock_kind, _rel(root, path), len(content), hashlib.sha256(content).hexdigest(), datetime.fromtimestamp(after.st_mtime, UTC))
        state.locks.append(observed)
        _add(state, "warning", "locks", "locks.present", f"Coordination lock is present: {lock_id}; Core cannot prove it is stale.", root, path, repair="clear_lock")
    except FileNotFoundError:
        _add(state, "error", "locks", "locks.changed", "Lock disappeared during inspection.", root, path, repair="clear_lock")
    except OSError as error:
        _add(state, "error", "locks", "locks.unreadable", f"Could not inspect coordination lock: {error}", root, path, repair="manual_canonical_review")


def _unexpected_lock(root: Path, state: _State, path: Path, message: str) -> None:
    _add(
        state,
        "error",
        "locks",
        "locks.unexpected_entry",
        message,
        root,
        path,
        repair="manual_canonical_review",
    )


def _scan_period_locks(root: Path, state: _State) -> None:
    base = academic_periods_dir(root)
    for year_entry in _nested_entries(root, base, state, "locks", "locks.unreadable"):
        if year_entry.name.startswith("."):
            _unexpected_lock(root, state, year_entry, "Hidden entry in Academic Period lock namespace.")
            continue
        try:
            year = validate_school_year(year_entry.name)
        except (SchoolYearValidationError, TypeError):
            _unexpected_lock(root, state, year_entry, "Invalid school-year directory in lock namespace.")
            continue
        if not _directory_entry(year_entry):
            _unexpected_lock(root, state, year_entry, "School-year lock parent must be a regular directory, not a file or symlink.")
            continue
        for entry in _nested_entries(root, year_entry, state, "locks", "locks.unreadable"):
            if entry.name == ".write.lock":
                _observe_lock(root, state, f"period:{year}", "period", entry)
            elif entry.name in {"current.json", "revisions"}:
                continue
            elif entry.name.startswith("."):
                _unexpected_lock(root, state, entry, "Unexpected hidden entry beside an Academic Period lock.")
            else:
                _unexpected_lock(root, state, entry, "Unexpected visible entry beside an Academic Period lock.")


def _scan_registration_locks(root: Path, state: _State) -> None:
    base = academic_work_registrations_dir(root)
    for class_entry in _nested_entries(root, base, state, "locks", "locks.unreadable"):
        try:
            class_id = validate_identifier(class_entry.name, "class_id")
        except IdentifierValidationError:
            _unexpected_lock(root, state, class_entry, "Invalid class directory in registration lock namespace.")
            continue
        if class_entry.name.startswith(".") or not _directory_entry(class_entry):
            _unexpected_lock(root, state, class_entry, "Registration lock class entry must be a visible regular directory.")
            continue
        for module_entry in _nested_entries(root, class_entry, state, "locks", "locks.unreadable"):
            try:
                module_id = validate_identifier(module_entry.name, "module_id")
                if module_id != module_id.lower():
                    raise ValueError
            except (IdentifierValidationError, ValueError):
                _unexpected_lock(root, state, module_entry, "Invalid or uppercase module directory in registration lock namespace.")
                continue
            if not _directory_entry(module_entry):
                _unexpected_lock(root, state, module_entry, "Registration lock module entry must be a regular directory.")
                continue
            for work_entry in _nested_entries(root, module_entry, state, "locks", "locks.unreadable"):
                try:
                    work_id = validate_identifier(work_entry.name, "work_id")
                except IdentifierValidationError:
                    _unexpected_lock(root, state, work_entry, "Invalid work directory in registration lock namespace.")
                    continue
                if work_entry.name.startswith(".") or not _directory_entry(work_entry):
                    _unexpected_lock(root, state, work_entry, "Registration lock work entry must be a visible regular directory.")
                    continue
                for entry in _nested_entries(root, work_entry, state, "locks", "locks.unreadable"):
                    if entry.name == ".write.lock":
                        lock_id = f"registration:{class_id}/{module_id}/{work_id}"
                        _observe_lock(root, state, lock_id, "registration", entry)
                    elif entry.name in {"current.json", "revisions"}:
                        continue
                    elif entry.name.startswith("."):
                        _unexpected_lock(root, state, entry, "Unexpected hidden entry beside a registration lock.")
                    else:
                        _unexpected_lock(root, state, entry, "Unexpected visible entry beside a registration lock.")


def _scan_publication_locks(root: Path, state: _State) -> None:
    base = registry_dir(root) / ".locks" / "publications"
    levels: list[tuple[Path, tuple[str, ...]]] = [(base, ())]
    validators = ("class_id", "module_id", "work_id", "publication_kind")
    for depth, name in enumerate(validators):
        next_levels: list[tuple[Path, tuple[str, ...]]] = []
        for parent, parts in levels:
            for entry in _nested_entries(root, parent, state, "locks", "locks.unreadable"):
                if entry.name.startswith("."):
                    _unexpected_lock(root, state, entry, "Hidden entry in publication lock namespace.")
                    continue
                if not _directory_entry(entry):
                    _unexpected_lock(root, state, entry, f"Publication lock {name} entry must be a regular directory.")
                    continue
                try:
                    if name == "publication_kind":
                        if entry.name not in {"academic_result_set", "intervention_record_set"}:
                            raise ValueError
                    else:
                        validate_identifier(entry.name, name)
                        if name == "module_id" and entry.name != entry.name.lower():
                            raise ValueError
                except (IdentifierValidationError, ValueError):
                    _unexpected_lock(root, state, entry, f"Invalid publication lock {name} directory.")
                    continue
                next_levels.append((entry, (*parts, entry.name)))
        levels = next_levels
    for parent, parts in levels:
        for entry in _nested_entries(root, parent, state, "locks", "locks.unreadable"):
            if entry.name.startswith("."):
                _unexpected_lock(root, state, entry, "Hidden publication lock entry.")
                continue
            if not _regular_entry(entry):
                _unexpected_lock(root, state, entry, "Publication lock leaf must be a regular file, not a directory, symlink, or nonregular entry.")
                continue
            if not entry.name.endswith(".lock"):
                _unexpected_lock(root, state, entry, "Publication lock file has the wrong suffix.")
                continue
            record_set_id = entry.name[:-5]
            try:
                validate_identifier(record_set_id, "record_set_id")
            except IdentifierValidationError:
                _unexpected_lock(root, state, entry, "Publication lock filename has an invalid record-set ID.")
                continue
            class_id, module_id, work_id, kind = parts
            lock_id = f"publication:{class_id}/{module_id}/{work_id}/{kind}/{record_set_id}"
            _observe_lock(root, state, lock_id, "publication", entry)


def _scan_locks(root: Path, state: _State) -> None:
    lock_root = registry_dir(root) / ".locks"
    for entry in _nested_entries(root, lock_root, state, "locks", "locks.unreadable"):
        if entry.name == "catalog.lock" or entry.name == "publications":
            continue
        _unexpected_lock(root, state, entry, "Unexpected entry in the Core registry lock namespace.")
    catalog_lock = academic_catalog_lock_path(root)
    try:
        catalog_present = catalog_lock.lstat() is not None
    except FileNotFoundError:
        catalog_present = False
    except OSError as error:
        _add(state, "error", "locks", "locks.unreadable", f"Could not inspect catalog lock: {error}", root, catalog_lock, repair="manual_canonical_review")
        catalog_present = False
    if catalog_present:
        _observe_lock(root, state, "catalog", "catalog", catalog_lock)
    _scan_period_locks(root, state)
    _scan_registration_locks(root, state)
    _scan_publication_locks(root, state)
    catalog = academic_catalog_path(root)
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(catalog) + suffix)
        if sidecar.exists():
            _add(state, "warning", "catalog", "catalog.sqlite_sidecar", "SQLite sidecar requires attention.", root, sidecar, repair="rebuild_catalog")
    catalog_dir = catalog.parent
    if catalog_dir.exists():
        for candidate in sorted(catalog_dir.glob(".catalog.sqlite.*.tmp"), key=lambda item: item.name):
            _add(state, "warning", "catalog", "catalog.temporary_candidate", "Interrupted catalog candidate requires attention.", root, candidate, repair="rebuild_catalog")


def _narrow_findings(
    root: Path,
    findings: list[RegistryAuditFinding],
    options: RegistryAuditOptions,
) -> list[RegistryAuditFinding]:
    """Narrow entity-local findings while retaining namespace blockers."""
    narrowed: list[RegistryAuditFinding] = []
    for finding in findings:
        path = finding.path or ""
        parts = path.split("/") if path else []
        if options.school_year is not None and (
            finding.domain == "academic_periods"
            or (finding.domain == "locks" and path.startswith("settings/academic_periods/"))
        ):
            if len(parts) >= 3 and parts[:2] == ["settings", "academic_periods"]:
                if parts[2] != options.school_year:
                    continue
        if finding.domain == "registrations" or (
            finding.domain == "locks"
            and (
                path.startswith("registry/work/")
                or path.startswith("registry/.locks/publications/")
            )
        ):
            identity: tuple[str | None, str | None, str | None] | None = None
            if len(parts) >= 5 and parts[:2] == ["registry", "work"]:
                identity = (parts[2], parts[3], parts[4])
            elif len(parts) >= 7 and parts[:3] == ["registry", ".locks", "publications"]:
                identity = (parts[3], parts[4], parts[5])
            elif len(parts) >= 6 and parts[0] == "classes" and parts[2] == "modules" and parts[4] == "work":
                identity = (parts[1], parts[3], parts[5])
            if identity is not None:
                class_id, module_id, work_id = identity
                if options.class_id not in (None, class_id) or options.module_id not in (None, module_id) or options.work_id not in (None, work_id):
                    continue
                if options.school_year is not None and class_id is not None:
                    try:
                        resolved_year = load_class_metadata_for_class(
                            root, class_id
                        ).school_year
                    except (FileNotFoundError, ValueError):
                        resolved_year = None
                    if resolved_year != options.school_year:
                        continue
        if finding.domain == "publications" and options.publication_id is not None:
            if path.startswith("registry/publications/") or path.startswith("registry/withdrawals/"):
                assignable_invalid = bool(finding.identity)
                if (
                    Path(path).stem != options.publication_id
                    and finding.code not in {
                        "publications.series_invalid",
                        "publications.competing_head",
                        "publications.logical_revision_duplicate",
                    }
                    and assignable_invalid
                ):
                    continue
        if finding.domain == "publications" and options.publication_id is None and any(
            value is not None
            for value in (
                options.school_year,
                options.class_id,
                options.module_id,
                options.work_id,
            )
        ):
            publication_identity = dict(finding.identity)
            if publication_identity:
                if (
                    options.school_year not in (None, publication_identity.get("school_year"))
                    or options.class_id not in (None, publication_identity.get("class_id"))
                    or options.module_id not in (None, publication_identity.get("module_id"))
                    or options.work_id not in (None, publication_identity.get("work_id"))
                ):
                    continue
        narrowed.append(finding)
    return narrowed


def _filter_locks(
    root: Path,
    locks: list[RegistryLockObservation],
    options: RegistryAuditOptions,
) -> list[RegistryLockObservation]:
    if not any(
        value is not None
        for value in (
            options.school_year,
            options.class_id,
            options.module_id,
            options.work_id,
            options.publication_id,
        )
    ):
        return locks
    selected: list[RegistryLockObservation] = []
    for lock in locks:
        if lock.lock_kind == "period":
            if (
                options.school_year in (None, lock.lock_id.removeprefix("period:"))
                and options.class_id is None
                and options.module_id is None
                and options.work_id is None
                and options.publication_id is None
            ):
                selected.append(lock)
            continue
        if lock.lock_kind not in {"registration", "publication"}:
            continue
        identity = lock.lock_id.split(":", 1)[1].split("/")
        class_id, module_id, work_id = identity[:3]
        if (
            options.publication_id is not None
            or options.class_id not in (None, class_id)
            or options.module_id not in (None, module_id)
            or options.work_id not in (None, work_id)
        ):
            continue
        if options.school_year is not None:
            try:
                year = load_class_metadata_for_class(root, class_id).school_year
            except (FileNotFoundError, ValueError):
                year = None
            if year != options.school_year:
                continue
        selected.append(lock)
    return selected


def list_registry_locks(
    workspace_root: str | Path,
) -> tuple[RegistryLockObservation, ...]:
    """List every valid known coordination lock in stable kind/ID order."""
    try:
        root = _normalize_workspace_root(workspace_root)
    except WorkspaceRootError as error:
        raise RegistryAuditValidationError(str(error)) from error
    if not root.is_dir():
        raise RegistryAuditReadError(
            f"Workspace root is not an accessible directory: {root}"
        )
    state = _State([], [], [], [], [], [])
    _scan_locks(root, state)
    errors = tuple(
        finding for finding in state.findings if finding.severity == "error"
    )
    if errors:
        raise RegistryAuditReadError(errors[0].message)
    return tuple(
        sorted(state.locks, key=lambda value: (value.lock_kind, value.lock_id))
    )


def get_registry_lock(
    workspace_root: str | Path,
    lock_id: str,
) -> RegistryLockObservation:
    """Return one exact current lock observation by stable lock ID."""
    try:
        root = _normalize_workspace_root(workspace_root)
    except WorkspaceRootError as error:
        raise RegistryAuditValidationError(str(error)) from error
    kind, path = _lock_path(root, lock_id)
    try:
        path.lstat()
    except FileNotFoundError as error:
        raise RegistryAuditReadError(f"Lock does not exist: {lock_id}") from error
    except OSError as error:
        raise RegistryAuditReadError(
            f"Could not inspect lock {lock_id}: {error}"
        ) from error
    try:
        observation, _fingerprint = _guarded_lock_observation(
            root, lock_id, kind, path
        )
    except (RegistryAuditRepairError, RegistryAuditConflictError) as error:
        raise RegistryAuditReadError(str(error)) from error
    return observation


def _audit_academic_registry_observation(
    workspace_root: str | Path,
    *,
    options: RegistryAuditOptions,
    producer_profiles: Iterable[PublicationProducerProfile],
) -> tuple[RegistryAuditReport, _State]:
    if not isinstance(options, RegistryAuditOptions):
        raise RegistryAuditValidationError("options must be RegistryAuditOptions.")
    try:
        root = _normalize_workspace_root(workspace_root)
    except WorkspaceRootError as error:
        raise RegistryAuditValidationError(str(error)) from error
    if not root.is_dir():
        raise RegistryAuditReadError(f"Workspace root is not an accessible directory: {root}")
    state = _State([], [], [], [], [], [])
    if "academic_periods" in options.scopes:
        _scan_periods(root, state, options)
    if "registrations" in options.scopes:
        _scan_registrations(root, state, options)
    if "publications" in options.scopes or "manifests" in options.scopes or "contracts" in options.scopes:
        _scan_publications(root, state, options)
    if "manifests" in options.scopes:
        _scan_manifests(root, state)
    if "contracts" in options.scopes:
        _scan_contracts(root, state, options, producer_profiles)
    if "catalog" in options.scopes:
        _scan_catalog(root, state, options)
    if "locks" in options.scopes:
        _scan_locks(root, state)
    state.locks = _filter_locks(root, state.locks, options)
    state.findings = _narrow_findings(root, state.findings, options)
    severity = Counter(finding.severity for finding in state.findings)
    canonical_domains = {"academic_periods", "registrations", "publications"}
    counts = RegistryAuditCounts(
        school_years=len({calendar.school_year for calendar in state.calendars}),
        calendar_revisions=len(state.calendars), periods=sum(len(calendar.periods) for calendar in state.calendars),
        registration_works=len({registration.work for registration in state.registrations}), registration_revisions=len(state.registrations),
        publication_records=len(state.publications), publication_series=len({(record.work, record.publication_kind, record.record_set_id) for record in state.publications}),
        withdrawals=len(state.withdrawals), verified_manifests=state.verified_manifests, catalog_source_files=state.catalog_source_files,
        locks=len(state.locks), info_findings=severity["info"], warning_findings=severity["warning"], error_findings=severity["error"],
    )
    def has_error(domains: Collection[str]) -> bool:
        return any(
            finding.severity == "error" and finding.domain in domains
            for finding in state.findings
        )
    report = RegistryAuditReport(
        REGISTRY_AUDIT_SCHEMA_VERSION, datetime.now(UTC), root, options.scopes,
        not has_error(canonical_domains), None if "manifests" not in options.scopes else not has_error({"manifests"}),
        None if "contracts" not in options.scopes else not has_error({"contracts"}),
        None if "catalog" not in options.scopes else not has_error({"catalog"}), counts, tuple(state.findings),
    )
    return report, state


def audit_academic_registry(workspace_root: str | Path, *, options: RegistryAuditOptions = RegistryAuditOptions(), producer_profiles: Iterable[PublicationProducerProfile] = ()) -> RegistryAuditReport:
    report, _state = _audit_academic_registry_observation(
        workspace_root,
        options=options,
        producer_profiles=producer_profiles,
    )
    return report


def get_academic_registry_status(workspace_root: str | Path, *, verify_manifests: bool = False, producer_profiles: Iterable[PublicationProducerProfile] = ()) -> RegistryStatus:
    if not isinstance(verify_manifests, bool):
        raise RegistryAuditValidationError("verify_manifests must be boolean.")
    scopes = tuple(scope for scope in _SCOPES if verify_manifests or scope != "manifests")
    report, state = _audit_academic_registry_observation(
        workspace_root,
        options=RegistryAuditOptions(scopes=scopes),
        producer_profiles=producer_profiles,
    )
    path = academic_catalog_path(report.workspace_root)
    temporary = sum(finding.code in {"catalog.temporary_candidate", "catalog.sqlite_sidecar"} for finding in report.findings)
    return RegistryStatus(
        report.workspace_root,
        report.counts,
        report.canonical_valid,
        report.manifests_valid,
        report.contracts_compatible,
        path,
        state.catalog_state,
        state.catalog_built_at,
        state.catalog_source_snapshot_sha256,
        state.catalog_sources_current,
        report.counts.locks,
        temporary,
        report.findings,
    )


def _lock_path(root: Path, lock_id: str) -> tuple[str, Path]:
    _lock_identity(lock_id)
    if lock_id == "catalog":
        return "catalog", academic_catalog_lock_path(root)
    if lock_id.startswith("period:"):
        year = validate_school_year(lock_id[7:])
        return "period", academic_periods_dir(root) / year / ".write.lock"
    if lock_id.startswith("registration:"):
        parts = lock_id[13:].split("/")
        if len(parts) != 3:
            raise RegistryAuditValidationError("registration lock ID is invalid.")
        work = ModuleWorkRef(parts[1], parts[0], parts[2])
        return "registration", academic_work_registration_dir(root, work) / ".write.lock"
    if lock_id.startswith("publication:"):
        parts = lock_id[12:].split("/")
        if len(parts) != 5 or parts[3] not in {"academic_result_set", "intervention_record_set"}:
            raise RegistryAuditValidationError("publication lock ID is invalid.")
        for name, value in zip(("class_id", "module_id", "work_id", "kind", "record_set_id"), parts):
            validate_identifier(value, name)
        if parts[1] != parts[1].lower():
            raise RegistryAuditValidationError("module_id must be lowercase.")
        path = registry_dir(root) / ".locks" / "publications" / parts[0] / parts[1] / parts[2] / parts[3] / f"{parts[4]}.lock"
        return "publication", path
    raise RegistryAuditValidationError("lock_id is not a supported stable lock ID.")


def _stat_identity(value: object) -> tuple[int, int, int, int, int, int]:
    status = cast(Any, value)
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _guarded_lock_observation(
    root: Path,
    lock_id: str,
    kind: str,
    path: Path,
) -> tuple[RegistryLockObservation, _LockFingerprint]:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or path.is_symlink():
            raise RegistryAuditRepairError(f"Lock is not a regular file: {path}")
        content = path.read_bytes()
        after = path.lstat()
    except FileNotFoundError as error:
        raise RegistryAuditRepairError(f"Lock does not exist: {lock_id}") from error
    except RegistryAuditError:
        raise
    except OSError as error:
        raise RegistryAuditRepairError(
            f"Could not inspect lock {lock_id}: {error}"
        ) from error
    if _stat_identity(before) != _stat_identity(after) or len(content) != after.st_size:
        raise RegistryAuditConflictError("Lock changed during fingerprint inspection.")
    digest = hashlib.sha256(content).hexdigest()
    fingerprint = _LockFingerprint(*_stat_identity(after), digest)
    observation = RegistryLockObservation(
        lock_id,
        kind,
        _rel(root, path),
        len(content),
        digest,
        datetime.fromtimestamp(after.st_mtime, UTC),
    )
    return observation, fingerprint


def clear_registry_lock(workspace_root: str | Path, lock_id: str, *, expected_sha256: str, force: bool = False, dry_run: bool = False) -> RegistryLockClearResult:
    if not isinstance(lock_id, str):
        raise RegistryAuditValidationError("lock_id must be a string.")
    if not isinstance(expected_sha256, str) or _SHA256.fullmatch(expected_sha256) is None:
        raise RegistryAuditValidationError("expected_sha256 must be 64 lowercase hexadecimal characters.")
    if not isinstance(force, bool) or not isinstance(dry_run, bool):
        raise RegistryAuditValidationError("force and dry_run must be boolean.")
    if not force and not dry_run:
        raise RegistryAuditValidationError("force is required unless dry_run is selected.")
    root = _normalize_workspace_root(workspace_root)
    try:
        kind, path = _lock_path(root, lock_id)
        observed, guarded = _guarded_lock_observation(root, lock_id, kind, path)
    except (ValueError, IdentifierValidationError) as error:
        raise RegistryAuditValidationError(f"lock_id is invalid: {error}") from error
    except RegistryAuditReadError as error:
        raise RegistryAuditRepairError(str(error)) from error
    if not hmac.compare_digest(guarded.sha256, expected_sha256):
        raise RegistryAuditConflictError("Lock SHA-256 does not match expected_sha256.")
    if dry_run:
        return RegistryLockClearResult(observed, True, False)
    try:
        final = path.lstat()
        if not stat.S_ISREG(final.st_mode) or path.is_symlink():
            raise RegistryAuditConflictError("Lock type changed before removal.")
        if _stat_identity(final) != (
            guarded.device,
            guarded.inode,
            guarded.mode,
            guarded.size,
            guarded.mtime_ns,
            guarded.ctime_ns,
        ):
            raise RegistryAuditConflictError("Lock changed before removal.")
        path.unlink()
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise RegistryAuditRepairError("Lock remains or was replaced after removal.")
    except RegistryAuditError:
        raise
    except OSError as error:
        raise RegistryAuditRepairError(f"Could not remove lock {lock_id}: {error}") from error
    return RegistryLockClearResult(observed, False, True)
