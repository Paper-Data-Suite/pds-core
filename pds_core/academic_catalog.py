"""Disposable SQLite discovery projection of canonical academic registry records.

The catalog is derived state.  Canonical JSON remains authoritative and this
module never reads producer manifests or recursively crawls producer work trees.

The aggregate source digest is SHA-256 over the sorted inventory.  Each item is
encoded as UTF-8 ``relative_path + NUL + decimal_size + NUL + sha256 + LF``.
NUL cannot occur in a canonical relative path, making the encoding unambiguous.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Final, Literal, TypeAlias, cast

from pds_core.academic_period_storage import (
    academic_period_current_path,
    academic_period_revision_path,
    academic_periods_dir,
)
from pds_core.academic_periods import (
    ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
    AcademicPeriod,
    AcademicPeriodCalendar,
    AcademicPeriodLifecycle,
    AcademicPeriodType,
    academic_period_calendar_from_dict,
    is_academic_period_lifecycle,
    is_academic_period_type,
    validate_academic_period,
    validate_academic_period_calendar_transition,
)
from pds_core.academic_work_registrations import (
    AcademicWorkIntent,
    AcademicWorkRegistration,
    AcademicWorkRegistrationLifecycle,
    academic_work_registration_from_dict,
    is_academic_work_intent,
    is_academic_work_registration_lifecycle,
    validate_academic_work_registration_transition,
)
from pds_core.class_metadata import (
    class_metadata_path,
    load_class_metadata_for_class,
    validate_class_metadata,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.publication_records import (
    PUBLICATION_CAPABILITIES,
    ManifestDigestAlgorithm,
    PublicationCapability,
    PublicationKind,
    PublicationRecord,
    PublicationWithdrawal,
    is_publication_capability,
    is_publication_kind,
    publication_record_from_dict,
    publication_withdrawal_from_dict,
    validate_publication_record_series,
    validate_publication_withdrawal_relationship,
)
from pds_core.registry_paths import (
    academic_catalog_lock_path,
    academic_catalog_path,
    academic_work_registration_current_path,
    academic_work_registration_revision_path,
    academic_work_registrations_dir,
    publication_record_path,
    publication_withdrawal_path,
    publication_withdrawals_dir,
    publications_dir,
)
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef
from pds_core.school_years import SchoolYearValidationError, validate_school_year
from pds_core.workspace import WorkspaceRootError, _normalize_workspace_root

ACADEMIC_CATALOG_SCHEMA_VERSION: Final[int] = 1
# ASCII "PDSA".  This stable, nonzero value identifies only this catalog format.
ACADEMIC_CATALOG_APPLICATION_ID: Final[int] = 0x50445341

PublicationCatalogState: TypeAlias = Literal[
    "current", "series_heads", "historical", "withdrawn", "all"
]

_STATES: Final[frozenset[str]] = frozenset(
    {"current", "series_heads", "historical", "withdrawn", "all"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PUBLICATION_FILE = re.compile(r"^(pub_[0-9a-f]{32})\.json$")
_REVISION_FILE = re.compile(r"^([1-9][0-9]*)\.json$")


class AcademicCatalogError(RuntimeError):
    """Base error for derived academic-catalog operations."""


class AcademicCatalogValidationError(AcademicCatalogError, ValueError):
    """Raised when a catalog request or query is invalid."""


class AcademicCatalogNotFoundError(AcademicCatalogError):
    """Raised when the derived catalog does not exist."""


class AcademicCatalogConflictError(AcademicCatalogError):
    """Raised for concurrent rebuilds or a changing source snapshot."""


class AcademicCatalogSourceError(AcademicCatalogError):
    """Raised when canonical source state cannot be projected safely."""


class AcademicCatalogReadError(AcademicCatalogError):
    """Raised when the SQLite catalog cannot be read operationally."""


class AcademicCatalogIntegrityError(AcademicCatalogError):
    """Raised when catalog contents or relationships are contradictory."""


class AcademicCatalogCompatibilityError(AcademicCatalogError):
    """Raised for an unsupported catalog application or schema version."""


class AcademicCatalogBuildError(AcademicCatalogError):
    """Raised when a replacement catalog cannot be built or installed."""


def _nonnegative(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AcademicCatalogValidationError(f"{name} must be a nonnegative integer.")
    return value


def _positive_limit(value: object, name: str = "limit") -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AcademicCatalogValidationError(f"{name} must be a positive integer.")
    return value


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise AcademicCatalogValidationError(f"{name} must be a string.")
    try:
        return validate_identifier(value, name)
    except IdentifierValidationError as error:
        raise AcademicCatalogValidationError(str(error)) from error


def _optional_identifier(value: object, name: str) -> str | None:
    return None if value is None else _identifier(value, name)


def _module_identifier(value: object, name: str = "module_id") -> str:
    result = _identifier(value, name)
    if result != result.lower():
        raise AcademicCatalogValidationError(f"{name} must be lowercase.")
    return result


def _school_year(value: object) -> str:
    try:
        return validate_school_year(value)
    except SchoolYearValidationError as error:
        raise AcademicCatalogValidationError(str(error)) from error


def _utc_text(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AcademicCatalogValidationError("datetime values must be timezone-aware.")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _parse_utc_text(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise AcademicCatalogIntegrityError(f"{name} is not a timestamp string.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise AcademicCatalogIntegrityError(
            f"{name} is not a valid timestamp."
        ) from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or _utc_text(parsed) != value
    ):
        raise AcademicCatalogIntegrityError(f"{name} is not normalized UTC.")
    return parsed


def _db_bool(value: object, name: str) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise AcademicCatalogIntegrityError(f"{name} is not a SQLite boolean.")
    return bool(value)


@dataclass(frozen=True, slots=True)
class AcademicCatalogMetadata:
    schema_version: int
    built_at_utc: datetime
    source_snapshot_sha256: str
    source_file_count: int
    class_count: int
    calendar_revision_count: int
    period_count: int
    registration_revision_count: int
    registration_source_count: int
    publication_count: int
    publication_capability_count: int
    withdrawal_count: int

    def __post_init__(self) -> None:
        if self.schema_version != ACADEMIC_CATALOG_SCHEMA_VERSION:
            raise AcademicCatalogValidationError("schema_version must equal 1.")
        object.__setattr__(
            self,
            "built_at_utc",
            _parse_model_datetime(self.built_at_utc, "built_at_utc"),
        )
        if (
            not isinstance(self.source_snapshot_sha256, str)
            or _SHA256.fullmatch(self.source_snapshot_sha256) is None
        ):
            raise AcademicCatalogValidationError(
                "source_snapshot_sha256 must be lowercase SHA-256."
            )
        for name in (
            "source_file_count",
            "class_count",
            "calendar_revision_count",
            "period_count",
            "registration_revision_count",
            "registration_source_count",
            "publication_count",
            "publication_capability_count",
            "withdrawal_count",
        ):
            _nonnegative(getattr(self, name), name)


def _parse_model_datetime(value: object, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AcademicCatalogValidationError(f"{name} must be timezone-aware.")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class AcademicCatalogBuildResult:
    catalog_path: Path
    metadata: AcademicCatalogMetadata
    replaced_existing_catalog: bool

    def __post_init__(self) -> None:
        if not isinstance(self.catalog_path, Path):
            raise AcademicCatalogValidationError("catalog_path must be a Path.")
        if not isinstance(self.metadata, AcademicCatalogMetadata):
            raise AcademicCatalogValidationError("metadata is invalid.")
        if not isinstance(self.replaced_existing_catalog, bool):
            raise AcademicCatalogValidationError(
                "replaced_existing_catalog must be boolean."
            )


@dataclass(frozen=True, slots=True)
class CatalogAcademicPeriod:
    school_year: str
    calendar_revision: int
    schema_version: str
    calendar_created_at: datetime
    calendar_updated_at: datetime
    is_current_calendar: bool
    period: AcademicPeriod

    def __post_init__(self) -> None:
        try:
            school_year = _school_year(self.school_year)
            if (
                isinstance(self.calendar_revision, bool)
                or not isinstance(self.calendar_revision, int)
                or self.calendar_revision <= 0
            ):
                raise AcademicCatalogValidationError(
                    "calendar_revision must be a positive integer."
                )
            if self.schema_version != ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION:
                raise AcademicCatalogValidationError(
                    "schema_version must equal the Academic Period Calendar schema version."
                )
            created = _parse_model_datetime(
                self.calendar_created_at, "calendar_created_at"
            )
            updated = _parse_model_datetime(
                self.calendar_updated_at, "calendar_updated_at"
            )
            if updated < created:
                raise AcademicCatalogValidationError(
                    "calendar_updated_at must not precede calendar_created_at."
                )
            if not isinstance(self.is_current_calendar, bool):
                raise AcademicCatalogValidationError(
                    "is_current_calendar must be boolean."
                )
            period = validate_academic_period(self.period)
        except AcademicCatalogValidationError:
            raise
        except (ValueError, TypeError) as error:
            raise AcademicCatalogValidationError(
                f"catalog academic period is invalid: {error}"
            ) from error
        object.__setattr__(self, "school_year", school_year)
        object.__setattr__(self, "calendar_created_at", created)
        object.__setattr__(self, "calendar_updated_at", updated)
        object.__setattr__(self, "period", period)

    @property
    def period_id(self) -> str:
        return self.period.period_id

    @property
    def period_type(self) -> AcademicPeriodType:
        return self.period.period_type

    @property
    def lifecycle(self) -> AcademicPeriodLifecycle:
        return self.period.lifecycle

    @property
    def label(self) -> str:
        return self.period.label

    @property
    def start_date(self) -> date:
        return self.period.start_date

    @property
    def end_date(self) -> date:
        return self.period.end_date

    @property
    def parent_period_id(self) -> str | None:
        return self.period.parent_period_id

    @property
    def sequence(self) -> int:
        return self.period.sequence


@dataclass(frozen=True, slots=True)
class CatalogAcademicWorkRegistration:
    school_year: str | None
    work: ModuleWorkRef
    registration_revision: int
    schema_version: str
    producer_contract_version: str
    title: str
    work_kind: str
    academic_intent: AcademicWorkIntent
    lifecycle: AcademicWorkRegistrationLifecycle
    created_at: datetime
    updated_at: datetime
    is_current_registration: bool
    source_records: tuple[ModuleRecordRef, ...]

    def __post_init__(self) -> None:
        try:
            school_year = (
                None if self.school_year is None else _school_year(self.school_year)
            )
            validated = AcademicWorkRegistration(
                schema_version=self.schema_version,
                record_type="academic_work_registration",
                work=self.work,
                registration_revision=self.registration_revision,
                producer_contract_version=self.producer_contract_version,
                title=self.title,
                work_kind=self.work_kind,
                academic_intent=self.academic_intent,
                lifecycle=self.lifecycle,
                created_at=self.created_at,
                updated_at=self.updated_at,
                source_records=self.source_records,
            )
            if not isinstance(self.is_current_registration, bool):
                raise AcademicCatalogValidationError(
                    "is_current_registration must be boolean."
                )
        except AcademicCatalogValidationError:
            raise
        except (ValueError, TypeError) as error:
            raise AcademicCatalogValidationError(
                f"catalog registration is invalid: {error}"
            ) from error
        object.__setattr__(self, "school_year", school_year)
        object.__setattr__(self, "work", validated.work)
        object.__setattr__(
            self, "registration_revision", validated.registration_revision
        )
        object.__setattr__(self, "schema_version", validated.schema_version)
        object.__setattr__(
            self, "producer_contract_version", validated.producer_contract_version
        )
        object.__setattr__(self, "title", validated.title)
        object.__setattr__(self, "work_kind", validated.work_kind)
        object.__setattr__(self, "academic_intent", validated.academic_intent)
        object.__setattr__(self, "lifecycle", validated.lifecycle)
        object.__setattr__(self, "created_at", validated.created_at.astimezone(UTC))
        object.__setattr__(self, "updated_at", validated.updated_at.astimezone(UTC))
        object.__setattr__(self, "source_records", validated.source_records)

    @property
    def class_id(self) -> str:
        return self.work.class_id

    @property
    def module_id(self) -> str:
        return self.work.module_id

    @property
    def work_id(self) -> str:
        return self.work.work_id


@dataclass(frozen=True, slots=True)
class CatalogPublication:
    school_year: str | None
    publication_id: str
    work: ModuleWorkRef
    source_record: ModuleRecordRef | None
    publication_kind: PublicationKind
    capabilities: tuple[PublicationCapability, ...]
    record_set_id: str
    record_set_revision: int
    manifest_contract_version: str
    manifest_path: str
    manifest_digest_algorithm: ManifestDigestAlgorithm
    manifest_digest: str
    published_at: datetime
    academic_work_registration_revision: int | None
    referenced_registration_lifecycle: AcademicWorkRegistrationLifecycle | None
    current_registration_revision: int | None
    current_registration_lifecycle: AcademicWorkRegistrationLifecycle | None
    supersedes_publication_id: str | None
    is_series_head: bool
    is_withdrawn: bool
    withdrawn_at: datetime | None
    is_current_selectable: bool

    def __post_init__(self) -> None:
        try:
            school_year = (
                None if self.school_year is None else _school_year(self.school_year)
            )
            validated = PublicationRecord(
                schema_version="1",
                record_type="publication_record",
                publication_id=self.publication_id,
                work=self.work,
                source_record=self.source_record,
                publication_kind=self.publication_kind,
                capabilities=self.capabilities,
                record_set_id=self.record_set_id,
                record_set_revision=self.record_set_revision,
                manifest_contract_version=self.manifest_contract_version,
                manifest_path=self.manifest_path,
                manifest_digest_algorithm=self.manifest_digest_algorithm,
                manifest_digest=self.manifest_digest,
                published_at=self.published_at,
                academic_work_registration_revision=self.academic_work_registration_revision,
                supersedes_publication_id=self.supersedes_publication_id,
            )
            for name in ("is_series_head", "is_withdrawn", "is_current_selectable"):
                if not isinstance(getattr(self, name), bool):
                    raise AcademicCatalogValidationError(f"{name} must be boolean.")
            if (self.withdrawn_at is None) == self.is_withdrawn:
                raise AcademicCatalogValidationError(
                    "withdrawn_at and is_withdrawn disagree."
                )
            withdrawn_at = (
                None
                if self.withdrawn_at is None
                else _parse_model_datetime(self.withdrawn_at, "withdrawn_at")
            )
            if withdrawn_at is not None and withdrawn_at < validated.published_at:
                raise AcademicCatalogValidationError(
                    "withdrawn_at must not precede published_at."
                )
            if self.is_current_selectable != (
                self.is_series_head and not self.is_withdrawn
            ):
                raise AcademicCatalogValidationError(
                    "current-selectable state is contradictory."
                )
            referenced_lifecycle = self.referenced_registration_lifecycle
            if validated.publication_kind == "academic_result_set":
                if not is_academic_work_registration_lifecycle(referenced_lifecycle):
                    raise AcademicCatalogValidationError(
                        "academic publications require a referenced registration lifecycle."
                    )
            elif referenced_lifecycle is not None:
                raise AcademicCatalogValidationError(
                    "intervention publications cannot have a referenced registration lifecycle."
                )
            current_revision = self.current_registration_revision
            current_lifecycle = self.current_registration_lifecycle
            if (current_revision is None) != (current_lifecycle is None):
                raise AcademicCatalogValidationError(
                    "current registration revision and lifecycle must appear together."
                )
            if current_revision is not None and (
                isinstance(current_revision, bool)
                or not isinstance(current_revision, int)
                or current_revision <= 0
            ):
                raise AcademicCatalogValidationError(
                    "current_registration_revision must be a positive integer."
                )
            if (
                current_lifecycle is not None
                and not is_academic_work_registration_lifecycle(current_lifecycle)
            ):
                raise AcademicCatalogValidationError(
                    "current_registration_lifecycle is invalid."
                )
        except AcademicCatalogValidationError:
            raise
        except (ValueError, TypeError) as error:
            raise AcademicCatalogValidationError(
                f"catalog publication is invalid: {error}"
            ) from error
        object.__setattr__(self, "school_year", school_year)
        object.__setattr__(self, "publication_id", validated.publication_id)
        object.__setattr__(self, "work", validated.work)
        object.__setattr__(self, "source_record", validated.source_record)
        object.__setattr__(self, "publication_kind", validated.publication_kind)
        object.__setattr__(self, "capabilities", validated.capabilities)
        object.__setattr__(self, "record_set_id", validated.record_set_id)
        object.__setattr__(self, "record_set_revision", validated.record_set_revision)
        object.__setattr__(
            self, "manifest_contract_version", validated.manifest_contract_version
        )
        object.__setattr__(self, "manifest_path", validated.manifest_path)
        object.__setattr__(
            self, "manifest_digest_algorithm", validated.manifest_digest_algorithm
        )
        object.__setattr__(self, "manifest_digest", validated.manifest_digest)
        object.__setattr__(self, "published_at", validated.published_at.astimezone(UTC))
        object.__setattr__(
            self,
            "academic_work_registration_revision",
            validated.academic_work_registration_revision,
        )
        object.__setattr__(
            self, "supersedes_publication_id", validated.supersedes_publication_id
        )
        object.__setattr__(self, "withdrawn_at", withdrawn_at)

    @property
    def class_id(self) -> str:
        return self.work.class_id

    @property
    def module_id(self) -> str:
        return self.work.module_id

    @property
    def work_id(self) -> str:
        return self.work.work_id


@dataclass(frozen=True, slots=True)
class AcademicPeriodCatalogQuery:
    school_year: str | None = None
    period_type: AcademicPeriodType | None = None
    lifecycle: AcademicPeriodLifecycle | None = None
    current_calendar_only: bool = True
    active_on: date | None = None
    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        if self.school_year is not None:
            object.__setattr__(self, "school_year", _school_year(self.school_year))
        if self.period_type is not None and not is_academic_period_type(
            self.period_type
        ):
            raise AcademicCatalogValidationError("period_type is invalid.")
        if self.lifecycle is not None and not is_academic_period_lifecycle(
            self.lifecycle
        ):
            raise AcademicCatalogValidationError("lifecycle is invalid.")
        if not isinstance(self.current_calendar_only, bool):
            raise AcademicCatalogValidationError(
                "current_calendar_only must be boolean."
            )
        if self.active_on is not None and (
            not isinstance(self.active_on, date) or isinstance(self.active_on, datetime)
        ):
            raise AcademicCatalogValidationError("active_on must be a date.")
        _positive_limit(self.limit)
        _nonnegative(self.offset, "offset")


@dataclass(frozen=True, slots=True)
class AcademicWorkRegistrationCatalogQuery:
    school_year: str | None = None
    class_id: str | None = None
    module_id: str | None = None
    work_id: str | None = None
    producer_contract_version: str | None = None
    academic_intent: AcademicWorkIntent | None = None
    lifecycle: AcademicWorkRegistrationLifecycle | None = None
    current_only: bool = True
    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        if self.school_year is not None:
            object.__setattr__(self, "school_year", _school_year(self.school_year))
        for name in ("class_id", "work_id", "producer_contract_version"):
            object.__setattr__(
                self, name, _optional_identifier(getattr(self, name), name)
            )
        if self.module_id is not None:
            object.__setattr__(self, "module_id", _module_identifier(self.module_id))
        if self.academic_intent is not None and not is_academic_work_intent(
            self.academic_intent
        ):
            raise AcademicCatalogValidationError("academic_intent is invalid.")
        if self.lifecycle is not None and not is_academic_work_registration_lifecycle(
            self.lifecycle
        ):
            raise AcademicCatalogValidationError("lifecycle is invalid.")
        if not isinstance(self.current_only, bool):
            raise AcademicCatalogValidationError("current_only must be boolean.")
        _positive_limit(self.limit)
        _nonnegative(self.offset, "offset")


@dataclass(frozen=True, slots=True)
class PublicationCatalogQuery:
    school_year: str | None = None
    class_id: str | None = None
    module_id: str | None = None
    work_id: str | None = None
    publication_kind: PublicationKind | None = None
    required_capabilities: tuple[PublicationCapability, ...] = ()
    producer_contract_version: str | None = None
    manifest_contract_version: str | None = None
    source_contract_version: str | None = None
    referenced_registration_lifecycle: AcademicWorkRegistrationLifecycle | None = None
    current_registration_lifecycle: AcademicWorkRegistrationLifecycle | None = None
    record_set_id: str | None = None
    minimum_record_set_revision: int | None = None
    published_at_or_after: datetime | None = None
    published_before: datetime | None = None
    state: PublicationCatalogState = "current"
    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        if self.school_year is not None:
            object.__setattr__(self, "school_year", _school_year(self.school_year))
        for name in (
            "class_id",
            "work_id",
            "producer_contract_version",
            "manifest_contract_version",
            "source_contract_version",
            "record_set_id",
        ):
            object.__setattr__(
                self, name, _optional_identifier(getattr(self, name), name)
            )
        if self.module_id is not None:
            object.__setattr__(self, "module_id", _module_identifier(self.module_id))
        if self.publication_kind is not None and not is_publication_kind(
            self.publication_kind
        ):
            raise AcademicCatalogValidationError("publication_kind is invalid.")
        if isinstance(self.required_capabilities, (str, bytes, Mapping)):
            raise AcademicCatalogValidationError(
                "required_capabilities must be a tuple-like iterable of capabilities."
            )
        try:
            capabilities = tuple(sorted(set(self.required_capabilities)))
        except TypeError as error:
            raise AcademicCatalogValidationError(
                "required_capabilities must be iterable strings."
            ) from error
        if any(not is_publication_capability(value) for value in capabilities):
            raise AcademicCatalogValidationError(
                "required_capabilities contains an invalid capability."
            )
        object.__setattr__(
            self,
            "required_capabilities",
            capabilities,
        )
        for name in (
            "referenced_registration_lifecycle",
            "current_registration_lifecycle",
        ):
            value = getattr(self, name)
            if value is not None and not is_academic_work_registration_lifecycle(value):
                raise AcademicCatalogValidationError(f"{name} is invalid.")
        if self.minimum_record_set_revision is not None:
            if (
                isinstance(self.minimum_record_set_revision, bool)
                or not isinstance(self.minimum_record_set_revision, int)
                or self.minimum_record_set_revision <= 0
            ):
                raise AcademicCatalogValidationError(
                    "minimum_record_set_revision must be positive."
                )
        lower = (
            None
            if self.published_at_or_after is None
            else _parse_model_datetime(
                self.published_at_or_after, "published_at_or_after"
            )
        )
        upper = (
            None
            if self.published_before is None
            else _parse_model_datetime(self.published_before, "published_before")
        )
        object.__setattr__(self, "published_at_or_after", lower)
        object.__setattr__(self, "published_before", upper)
        if lower is not None and upper is not None and upper <= lower:
            raise AcademicCatalogValidationError(
                "published_before must be later than published_at_or_after."
            )
        if not isinstance(self.state, str) or self.state not in _STATES:
            raise AcademicCatalogValidationError("state is invalid.")
        _positive_limit(self.limit)
        _nonnegative(self.offset, "offset")


@dataclass(frozen=True, slots=True)
class _Source:
    relative_path: str
    size_bytes: int
    sha256: str
    content: bytes


@dataclass(frozen=True, slots=True)
class _Projection:
    sources: tuple[_Source, ...]
    snapshot_sha256: str
    classes: tuple[tuple[str, str | None, int, str | None, str | None], ...]
    calendars: tuple[tuple[AcademicPeriodCalendar, bool], ...]
    registrations: tuple[tuple[AcademicWorkRegistration, bool], ...]
    publications: tuple[PublicationRecord, ...]
    withdrawals: tuple[PublicationWithdrawal, ...]
    heads: frozenset[str]


def _workspace_root(value: str | Path) -> Path:
    try:
        return _normalize_workspace_root(value)
    except (WorkspaceRootError, OSError, TypeError) as error:
        raise AcademicCatalogValidationError(
            f"workspace_root is invalid: {error}"
        ) from error


def _visible(path: Path) -> tuple[Path, ...]:
    try:
        entries = tuple(path.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise AcademicCatalogSourceError(
            f"Could not enumerate canonical source {path}: {error}"
        ) from error
    return tuple(
        sorted(
            (item for item in entries if not item.name.startswith(".")),
            key=lambda item: item.name,
        )
    )


def _all_collection_entries(path: Path) -> tuple[Path, ...]:
    try:
        return tuple(sorted(path.iterdir(), key=lambda item: item.name))
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise AcademicCatalogSourceError(
            f"Could not enumerate canonical collection {path}: {error}"
        ) from error


def _require_dir(path: Path, description: str) -> None:
    try:
        valid = path.is_dir()
    except OSError as error:
        raise AcademicCatalogSourceError(
            f"Could not inspect {description} {path}: {error}"
        ) from error
    if not valid:
        raise AcademicCatalogSourceError(f"Expected {description} directory: {path}")


def _discover_base_paths(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    period_root = academic_periods_dir(root)
    for year_dir in _visible(period_root):
        _require_dir(year_dir, "school-year")
        try:
            year = validate_school_year(year_dir.name)
        except ValueError as error:
            raise AcademicCatalogSourceError(
                f"Invalid school-year directory {year_dir}."
            ) from error
        allowed = {"current.json", "revisions"}
        entries = _visible(year_dir)
        if any(item.name not in allowed for item in entries):
            raise AcademicCatalogSourceError(
                f"Unexpected Academic Period entry in {year_dir}."
            )
        revision_dir = year_dir / "revisions"
        revisions = _visible(revision_dir)
        if revisions:
            _require_dir(revision_dir, "revision")
        for item in revisions:
            if not item.is_file() or _REVISION_FILE.fullmatch(item.name) is None:
                raise AcademicCatalogSourceError(
                    f"Malformed Academic Period revision: {item}"
                )
            paths.append(academic_period_revision_path(root, year, int(item.stem)))
        current = academic_period_current_path(root, year)
        if current.exists():
            if not current.is_file():
                raise AcademicCatalogSourceError(
                    f"Academic Period pointer is not a file: {current}"
                )
            paths.append(current)
            if not revisions:
                raise AcademicCatalogSourceError(
                    f"Academic Period pointer has no revisions: {year_dir}"
                )
        elif revisions:
            raise AcademicCatalogSourceError(
                f"Academic Period revisions have no current pointer: {year_dir}"
            )

    registration_root = academic_work_registrations_dir(root)
    for class_dir in _visible(registration_root):
        _require_dir(class_dir, "registration class")
        class_id = _source_identifier(class_dir.name, "class_id", lowercase=False)
        for module_dir in _visible(class_dir):
            _require_dir(module_dir, "registration module")
            module_id = _source_identifier(module_dir.name, "module_id", lowercase=True)
            for work_dir in _visible(module_dir):
                _require_dir(work_dir, "registration work")
                work_id = _source_identifier(work_dir.name, "work_id", lowercase=False)
                work = ModuleWorkRef(
                    module_id=module_id, class_id=class_id, work_id=work_id
                )
                entries = _visible(work_dir)
                if any(
                    item.name not in {"current.json", "revisions"} for item in entries
                ):
                    raise AcademicCatalogSourceError(
                        f"Unexpected registration entry in {work_dir}."
                    )
                revision_dir = work_dir / "revisions"
                revisions = _visible(revision_dir)
                for item in revisions:
                    if (
                        not item.is_file()
                        or _REVISION_FILE.fullmatch(item.name) is None
                    ):
                        raise AcademicCatalogSourceError(
                            f"Malformed registration revision: {item}"
                        )
                    paths.append(
                        academic_work_registration_revision_path(
                            root, work, int(item.stem)
                        )
                    )
                current = academic_work_registration_current_path(root, work)
                if current.exists():
                    if not current.is_file():
                        raise AcademicCatalogSourceError(
                            f"Registration pointer is not a file: {current}"
                        )
                    paths.append(current)
                    if not revisions:
                        raise AcademicCatalogSourceError(
                            f"Registration pointer has no revisions: {work_dir}"
                        )
                elif revisions:
                    raise AcademicCatalogSourceError(
                        f"Registration revisions have no current pointer: {work_dir}"
                    )

    for directory, withdrawal in (
        (publications_dir(root), False),
        (publication_withdrawals_dir(root), True),
    ):
        for item in _all_collection_entries(directory):
            try:
                is_file = item.is_file()
            except OSError as error:
                raise AcademicCatalogSourceError(
                    f"Could not inspect canonical collection entry {item}: {error}"
                ) from error
            if not is_file:
                raise AcademicCatalogSourceError(
                    f"Unexpected canonical collection entry: {item}"
                )
            match = _PUBLICATION_FILE.fullmatch(item.name)
            if match is None:
                raise AcademicCatalogSourceError(
                    f"Malformed canonical publication filename: {item}"
                )
            publication_id = match.group(1)
            paths.append(
                publication_withdrawal_path(root, publication_id)
                if withdrawal
                else publication_record_path(root, publication_id)
            )
    return tuple(sorted(set(paths), key=lambda item: item.relative_to(root).as_posix()))


def _source_identifier(value: str, name: str, *, lowercase: bool) -> str:
    try:
        result = validate_identifier(value, name)
    except IdentifierValidationError as error:
        raise AcademicCatalogSourceError(str(error)) from error
    if lowercase and result != result.lower():
        raise AcademicCatalogSourceError(f"{name} must be lowercase.")
    return result


def _read_sources(root: Path, paths: Iterable[Path]) -> tuple[_Source, ...]:
    sources: list[_Source] = []
    for path in sorted(set(paths), key=lambda item: item.relative_to(root).as_posix()):
        try:
            content = path.read_bytes()
        except OSError as error:
            raise AcademicCatalogSourceError(
                f"Could not read canonical source {path}: {error}"
            ) from error
        relative = path.relative_to(root).as_posix()
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            raise AcademicCatalogSourceError(
                f"Canonical source path is unsafe: {relative}"
            )
        sources.append(
            _Source(
                relative, len(content), hashlib.sha256(content).hexdigest(), content
            )
        )
    return tuple(sources)


def _snapshot(sources: Sequence[_Source]) -> str:
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda item: item.relative_path):
        digest.update(source.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(source.size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(source.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _json(source: _Source) -> object:
    def reject_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant {value}")

    try:
        return json.loads(
            source.content.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise AcademicCatalogSourceError(
            f"Malformed canonical JSON {source.relative_path}: {error}"
        ) from error


def _pointer(
    data: object, keys: frozenset[str], expected: Mapping[str, object], path: str
) -> int:
    if not isinstance(data, dict) or frozenset(data) != keys:
        raise AcademicCatalogSourceError(f"Malformed current pointer {path}.")
    for key, value in expected.items():
        if data.get(key) != value:
            raise AcademicCatalogSourceError(
                f"Current pointer identity disagrees at {path}."
            )
    revision = data.get(next(key for key in keys if key.endswith("revision")))
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise AcademicCatalogSourceError(
            f"Current pointer revision is invalid at {path}."
        )
    return revision


def _load_projection(root: Path) -> _Projection:
    base = _read_sources(root, _discover_base_paths(root))
    by_path = {source.relative_path: source for source in base}
    calendars: list[tuple[AcademicPeriodCalendar, bool]] = []
    registrations: list[tuple[AcademicWorkRegistration, bool]] = []
    publications: list[PublicationRecord] = []
    withdrawals: list[PublicationWithdrawal] = []
    referenced_classes: set[str] = set()

    period_groups: dict[str, list[AcademicPeriodCalendar]] = {}
    for path, source in by_path.items():
        if path.startswith("settings/academic_periods/") and "/revisions/" in path:
            try:
                calendar = academic_period_calendar_from_dict(_json(source))
            except ValueError as error:
                raise AcademicCatalogSourceError(
                    f"Invalid Academic Period Calendar {path}: {error}"
                ) from error
            parts = PurePosixPath(path).parts
            if (
                calendar.school_year != parts[2]
                or f"{calendar.calendar_revision}.json" != parts[-1]
            ):
                raise AcademicCatalogSourceError(
                    f"Academic Period identity disagrees with path {path}."
                )
            period_groups.setdefault(calendar.school_year, []).append(calendar)
    for year, period_values in sorted(period_groups.items()):
        ordered_calendars = sorted(
            period_values, key=lambda item: item.calendar_revision
        )
        for prior_calendar, candidate_calendar in zip(
            ordered_calendars, ordered_calendars[1:], strict=False
        ):
            try:
                validate_academic_period_calendar_transition(
                    prior_calendar, candidate_calendar
                )
            except ValueError as error:
                raise AcademicCatalogSourceError(
                    f"Invalid Academic Period history for {year}: {error}"
                ) from error
        pointer_path = f"settings/academic_periods/{year}/current.json"
        period_pointer_source = by_path.get(pointer_path)
        if period_pointer_source is None:
            raise AcademicCatalogSourceError(
                f"Academic Period history has no pointer for {year}."
            )
        current = _pointer(
            _json(period_pointer_source),
            frozenset(
                {"schema_version", "record_type", "school_year", "calendar_revision"}
            ),
            {
                "schema_version": "1",
                "record_type": "academic_period_calendar_current",
                "school_year": year,
            },
            pointer_path,
        )
        if current != ordered_calendars[-1].calendar_revision:
            raise AcademicCatalogSourceError(
                f"Academic Period pointer does not select latest valid transition for {year}."
            )
        calendars.extend(
            (item, item.calendar_revision == current) for item in ordered_calendars
        )

    reg_groups: dict[ModuleWorkRef, list[AcademicWorkRegistration]] = {}
    for path, source in by_path.items():
        if path.startswith("registry/work/") and "/revisions/" in path:
            try:
                registration = academic_work_registration_from_dict(_json(source))
            except ValueError as error:
                raise AcademicCatalogSourceError(
                    f"Invalid Academic Work Registration {path}: {error}"
                ) from error
            parts = PurePosixPath(path).parts
            expected = (parts[2], parts[3], parts[4], parts[-1])
            actual = (
                registration.work.class_id,
                registration.work.module_id,
                registration.work.work_id,
                f"{registration.registration_revision}.json",
            )
            if actual != expected:
                raise AcademicCatalogSourceError(
                    f"Registration identity disagrees with path {path}."
                )
            reg_groups.setdefault(registration.work, []).append(registration)
            referenced_classes.add(registration.work.class_id)
    exact_registrations: dict[tuple[ModuleWorkRef, int], AcademicWorkRegistration] = {}
    for work, registration_values in sorted(
        reg_groups.items(),
        key=lambda item: (item[0].class_id, item[0].module_id, item[0].work_id),
    ):
        ordered_registrations = sorted(
            registration_values, key=lambda item: item.registration_revision
        )
        for prior_registration, candidate_registration in zip(
            ordered_registrations, ordered_registrations[1:], strict=False
        ):
            try:
                validate_academic_work_registration_transition(
                    prior_registration, candidate_registration
                )
            except ValueError as error:
                raise AcademicCatalogSourceError(
                    f"Invalid registration history for {work}: {error}"
                ) from error
        pointer_path = f"registry/work/{work.class_id}/{work.module_id}/{work.work_id}/current.json"
        registration_pointer_source = by_path.get(pointer_path)
        if registration_pointer_source is None:
            raise AcademicCatalogSourceError(
                f"Registration history has no pointer for {work}."
            )
        current = _pointer(
            _json(registration_pointer_source),
            frozenset(
                {"schema_version", "record_type", "work", "registration_revision"}
            ),
            {
                "schema_version": "1",
                "record_type": "academic_work_registration_current",
                "work": {
                    "module_id": work.module_id,
                    "class_id": work.class_id,
                    "work_id": work.work_id,
                },
            },
            pointer_path,
        )
        if current != ordered_registrations[-1].registration_revision:
            raise AcademicCatalogSourceError(
                f"Registration pointer does not select latest valid transition for {work}."
            )
        for item in ordered_registrations:
            exact_registrations[(work, item.registration_revision)] = item
            registrations.append((item, item.registration_revision == current))

    for path, source in by_path.items():
        if path.startswith("registry/publications/"):
            try:
                publication = publication_record_from_dict(_json(source))
            except ValueError as error:
                raise AcademicCatalogSourceError(
                    f"Invalid Publication Record {path}: {error}"
                ) from error
            if PurePosixPath(path).name != f"{publication.publication_id}.json":
                raise AcademicCatalogSourceError(
                    f"Publication identity disagrees with path {path}."
                )
            publications.append(publication)
            referenced_classes.add(publication.work.class_id)
        elif path.startswith("registry/withdrawals/"):
            try:
                withdrawal = publication_withdrawal_from_dict(_json(source))
            except ValueError as error:
                raise AcademicCatalogSourceError(
                    f"Invalid Publication Withdrawal {path}: {error}"
                ) from error
            if PurePosixPath(path).name != f"{withdrawal.publication_id}.json":
                raise AcademicCatalogSourceError(
                    f"Withdrawal identity disagrees with path {path}."
                )
            withdrawals.append(withdrawal)

    series: dict[tuple[ModuleWorkRef, str, str], list[PublicationRecord]] = {}
    logical_revisions: set[tuple[str, str, str, str, str, int]] = set()
    for publication in publications:
        logical = (
            publication.work.class_id,
            publication.work.module_id,
            publication.work.work_id,
            publication.publication_kind,
            publication.record_set_id,
            publication.record_set_revision,
        )
        if logical in logical_revisions:
            raise AcademicCatalogSourceError("Duplicate logical publication revision.")
        logical_revisions.add(logical)
        series.setdefault(
            (publication.work, publication.publication_kind, publication.record_set_id),
            [],
        ).append(publication)
        if publication.publication_kind == "academic_result_set":
            revision = cast(int, publication.academic_work_registration_revision)
            if (publication.work, revision) not in exact_registrations:
                raise AcademicCatalogSourceError(
                    f"Publication {publication.publication_id} references a missing registration revision."
                )
    heads: set[str] = set()
    for identity, series_values in series.items():
        try:
            validated = validate_publication_record_series(series_values)
        except ValueError as error:
            raise AcademicCatalogSourceError(
                f"Invalid publication series {identity}: {error}"
            ) from error
        superseded = {
            item.supersedes_publication_id
            for item in validated
            if item.supersedes_publication_id is not None
        }
        heads.update(
            item.publication_id
            for item in validated
            if item.publication_id not in superseded
        )

    publication_by_id = {item.publication_id: item for item in publications}
    seen_withdrawals: set[str] = set()
    for withdrawal in withdrawals:
        exact_publication = publication_by_id.get(withdrawal.publication_id)
        if exact_publication is None:
            raise AcademicCatalogSourceError(
                f"Orphan withdrawal {withdrawal.publication_id}."
            )
        try:
            validate_publication_withdrawal_relationship(exact_publication, withdrawal)
        except ValueError as error:
            raise AcademicCatalogSourceError(
                f"Invalid withdrawal {withdrawal.publication_id}: {error}"
            ) from error
        if withdrawal.publication_id in seen_withdrawals:
            raise AcademicCatalogSourceError(
                f"Duplicate withdrawal {withdrawal.publication_id}."
            )
        seen_withdrawals.add(withdrawal.publication_id)

    class_paths = [
        class_metadata_path(root, class_id)
        for class_id in sorted(referenced_classes)
        if class_metadata_path(root, class_id).exists()
    ]
    class_sources = _read_sources(root, class_paths)
    classes: list[tuple[str, str | None, int, str | None, str | None]] = []
    class_by_path = {source.relative_path: source for source in class_sources}
    for class_id in sorted(referenced_classes):
        relative = class_metadata_path(root, class_id).relative_to(root).as_posix()
        class_source = class_by_path.get(relative)
        if class_source is None:
            classes.append((class_id, None, 0, None, None))
            continue
        data = _json(class_source)
        if not isinstance(data, Mapping):
            raise AcademicCatalogSourceError(
                f"Class metadata is not an object at {relative}."
            )
        try:
            metadata = validate_class_metadata(cast(Mapping[str, object], data))
            loaded_metadata = load_class_metadata_for_class(root, class_id)
        except ValueError as error:
            raise AcademicCatalogSourceError(
                f"Invalid class metadata {relative}: {error}"
            ) from error
        if loaded_metadata != metadata:
            raise AcademicCatalogSourceError(
                f"Class metadata changed while it was loaded at {relative}."
            )
        if metadata.class_id != class_id:
            raise AcademicCatalogSourceError(
                f"Class metadata identity disagrees at {relative}."
            )
        classes.append(
            (
                class_id,
                metadata.school_year,
                1,
                _utc_text(metadata.created_at),
                _utc_text(metadata.updated_at),
            )
        )

    all_sources = tuple(
        sorted((*base, *class_sources), key=lambda item: item.relative_path)
    )
    return _Projection(
        all_sources,
        _snapshot(all_sources),
        tuple(classes),
        tuple(calendars),
        tuple(registrations),
        tuple(sorted(publications, key=lambda item: item.publication_id)),
        tuple(sorted(withdrawals, key=lambda item: item.publication_id)),
        frozenset(heads),
    )


_SCHEMA: Final[str] = """
CREATE TABLE catalog_metadata (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL CHECK(schema_version=1),
 built_at_utc TEXT NOT NULL, source_snapshot_sha256 TEXT NOT NULL CHECK(length(source_snapshot_sha256)=64 AND source_snapshot_sha256=lower(source_snapshot_sha256) AND source_snapshot_sha256 NOT GLOB '*[^0-9a-f]*'),
 source_file_count INTEGER NOT NULL CHECK(source_file_count>=0), class_count INTEGER NOT NULL CHECK(class_count>=0),
 calendar_revision_count INTEGER NOT NULL CHECK(calendar_revision_count>=0), period_count INTEGER NOT NULL CHECK(period_count>=0),
 registration_revision_count INTEGER NOT NULL CHECK(registration_revision_count>=0), registration_source_count INTEGER NOT NULL CHECK(registration_source_count>=0),
 publication_count INTEGER NOT NULL CHECK(publication_count>=0), publication_capability_count INTEGER NOT NULL CHECK(publication_capability_count>=0),
 withdrawal_count INTEGER NOT NULL CHECK(withdrawal_count>=0));
CREATE TABLE catalog_sources (relative_path TEXT PRIMARY KEY CHECK(relative_path != '' AND relative_path NOT LIKE '/%' AND relative_path NOT LIKE '%\\%' AND relative_path NOT LIKE '../%' AND relative_path NOT LIKE '%/../%'), size_bytes INTEGER NOT NULL CHECK(size_bytes>=0), sha256 TEXT NOT NULL CHECK(length(sha256)=64 AND sha256=lower(sha256) AND sha256 NOT GLOB '*[^0-9a-f]*'));
CREATE TABLE class_context (class_id TEXT PRIMARY KEY, school_year TEXT, metadata_present INTEGER NOT NULL CHECK(metadata_present IN (0,1)), created_at_utc TEXT, updated_at_utc TEXT,
 CHECK((metadata_present=0 AND school_year IS NULL AND created_at_utc IS NULL AND updated_at_utc IS NULL) OR (metadata_present=1 AND school_year IS NOT NULL AND created_at_utc IS NOT NULL AND updated_at_utc IS NOT NULL)));
CREATE TABLE academic_period_calendars (school_year TEXT NOT NULL, calendar_revision INTEGER NOT NULL CHECK(calendar_revision>0), schema_version TEXT NOT NULL, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, is_current INTEGER NOT NULL CHECK(is_current IN (0,1)), PRIMARY KEY(school_year, calendar_revision));
CREATE TABLE academic_periods (school_year TEXT NOT NULL, calendar_revision INTEGER NOT NULL, period_id TEXT NOT NULL, period_type TEXT NOT NULL CHECK(period_type IN ('marking_period','semester','quarter','trimester','progress_window','custom')), label TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, parent_period_id TEXT, sequence INTEGER NOT NULL CHECK(sequence>0), lifecycle TEXT NOT NULL CHECK(lifecycle IN ('planned','active','closed','cancelled')),
 PRIMARY KEY(school_year, calendar_revision, period_id), FOREIGN KEY(school_year,calendar_revision) REFERENCES academic_period_calendars(school_year,calendar_revision), FOREIGN KEY(school_year,calendar_revision,parent_period_id) REFERENCES academic_periods(school_year,calendar_revision,period_id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE academic_work_registrations (class_id TEXT NOT NULL, module_id TEXT NOT NULL, work_id TEXT NOT NULL, registration_revision INTEGER NOT NULL CHECK(registration_revision>0), schema_version TEXT NOT NULL, producer_contract_version TEXT NOT NULL, title TEXT NOT NULL, work_kind TEXT NOT NULL, academic_intent TEXT NOT NULL CHECK(academic_intent IN ('formative','summative','diagnostic','practice','feedback_only','reporting_only')), lifecycle TEXT NOT NULL CHECK(lifecycle IN ('planned','active','closed','cancelled')), created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, is_current INTEGER NOT NULL CHECK(is_current IN (0,1)), PRIMARY KEY(class_id,module_id,work_id,registration_revision), FOREIGN KEY(class_id) REFERENCES class_context(class_id));
CREATE TABLE academic_work_registration_sources (class_id TEXT NOT NULL, module_id TEXT NOT NULL, work_id TEXT NOT NULL, registration_revision INTEGER NOT NULL, position INTEGER NOT NULL CHECK(position>=0), source_module_id TEXT NOT NULL, source_record_kind TEXT NOT NULL, source_record_id TEXT NOT NULL, source_contract_version TEXT, PRIMARY KEY(class_id,module_id,work_id,registration_revision,position), FOREIGN KEY(class_id,module_id,work_id,registration_revision) REFERENCES academic_work_registrations(class_id,module_id,work_id,registration_revision));
CREATE TABLE publications (publication_id TEXT PRIMARY KEY, class_id TEXT NOT NULL, module_id TEXT NOT NULL, work_id TEXT NOT NULL, source_module_id TEXT, source_record_kind TEXT, source_record_id TEXT, source_contract_version TEXT, publication_kind TEXT NOT NULL CHECK(publication_kind IN ('academic_result_set','intervention_record_set')), record_set_id TEXT NOT NULL, record_set_revision INTEGER NOT NULL CHECK(record_set_revision>0), manifest_contract_version TEXT NOT NULL, manifest_path TEXT NOT NULL, manifest_digest_algorithm TEXT NOT NULL CHECK(manifest_digest_algorithm='sha256'), manifest_digest TEXT NOT NULL CHECK(length(manifest_digest)=64 AND manifest_digest=lower(manifest_digest) AND manifest_digest NOT GLOB '*[^0-9a-f]*'), published_at_utc TEXT NOT NULL, academic_work_registration_revision INTEGER, supersedes_publication_id TEXT UNIQUE, is_series_head INTEGER NOT NULL CHECK(is_series_head IN (0,1)), is_withdrawn INTEGER NOT NULL CHECK(is_withdrawn IN (0,1)), withdrawn_at_utc TEXT, is_current_selectable INTEGER NOT NULL CHECK(is_current_selectable IN (0,1)),
 UNIQUE(class_id,module_id,work_id,publication_kind,record_set_id,record_set_revision), FOREIGN KEY(class_id) REFERENCES class_context(class_id), FOREIGN KEY(supersedes_publication_id) REFERENCES publications(publication_id) DEFERRABLE INITIALLY DEFERRED, FOREIGN KEY(class_id,module_id,work_id,academic_work_registration_revision) REFERENCES academic_work_registrations(class_id,module_id,work_id,registration_revision),
 CHECK((source_module_id IS NULL AND source_record_kind IS NULL AND source_record_id IS NULL AND source_contract_version IS NULL) OR (source_module_id IS NOT NULL AND source_record_kind IS NOT NULL AND source_record_id IS NOT NULL)), CHECK((publication_kind='academic_result_set' AND academic_work_registration_revision IS NOT NULL) OR (publication_kind='intervention_record_set' AND academic_work_registration_revision IS NULL)), CHECK((is_withdrawn=0 AND withdrawn_at_utc IS NULL) OR (is_withdrawn=1 AND withdrawn_at_utc IS NOT NULL)), CHECK(is_current_selectable = CASE WHEN is_series_head=1 AND is_withdrawn=0 THEN 1 ELSE 0 END));
CREATE TABLE publication_capabilities (publication_id TEXT NOT NULL, capability TEXT NOT NULL CHECK(capability IN ('points','question_evidence','multiple_attempts','standards_ratings','criterion_scores','moderated_scores','intervention_history','intervention_status','intervention_outcomes')), PRIMARY KEY(publication_id,capability), FOREIGN KEY(publication_id) REFERENCES publications(publication_id));
CREATE INDEX idx_class_context_school_year ON class_context(school_year,class_id);
CREATE INDEX idx_period_calendars_current ON academic_period_calendars(school_year,is_current);
CREATE INDEX idx_periods_lifecycle_type ON academic_periods(school_year,lifecycle,period_type);
CREATE INDEX idx_periods_dates ON academic_periods(school_year,start_date,end_date);
CREATE INDEX idx_registrations_work_current ON academic_work_registrations(class_id,module_id,work_id,is_current);
CREATE INDEX idx_registrations_discovery ON academic_work_registrations(lifecycle,academic_intent,producer_contract_version);
CREATE INDEX idx_publications_work_kind ON publications(class_id,module_id,work_id,publication_kind);
CREATE INDEX idx_publications_manifest_time ON publications(manifest_contract_version,published_at_utc);
CREATE INDEX idx_publications_current_kind_time ON publications(is_current_selectable,publication_kind,published_at_utc);
CREATE INDEX idx_publications_record_set ON publications(record_set_id,record_set_revision);
CREATE INDEX idx_publication_capabilities_lookup ON publication_capabilities(capability,publication_id);
"""

_REQUIRED_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "catalog_metadata": (
        "singleton",
        "schema_version",
        "built_at_utc",
        "source_snapshot_sha256",
        "source_file_count",
        "class_count",
        "calendar_revision_count",
        "period_count",
        "registration_revision_count",
        "registration_source_count",
        "publication_count",
        "publication_capability_count",
        "withdrawal_count",
    ),
    "catalog_sources": ("relative_path", "size_bytes", "sha256"),
    "class_context": (
        "class_id",
        "school_year",
        "metadata_present",
        "created_at_utc",
        "updated_at_utc",
    ),
    "academic_period_calendars": (
        "school_year",
        "calendar_revision",
        "schema_version",
        "created_at_utc",
        "updated_at_utc",
        "is_current",
    ),
    "academic_periods": (
        "school_year",
        "calendar_revision",
        "period_id",
        "period_type",
        "label",
        "start_date",
        "end_date",
        "parent_period_id",
        "sequence",
        "lifecycle",
    ),
    "academic_work_registrations": (
        "class_id",
        "module_id",
        "work_id",
        "registration_revision",
        "schema_version",
        "producer_contract_version",
        "title",
        "work_kind",
        "academic_intent",
        "lifecycle",
        "created_at_utc",
        "updated_at_utc",
        "is_current",
    ),
    "academic_work_registration_sources": (
        "class_id",
        "module_id",
        "work_id",
        "registration_revision",
        "position",
        "source_module_id",
        "source_record_kind",
        "source_record_id",
        "source_contract_version",
    ),
    "publications": (
        "publication_id",
        "class_id",
        "module_id",
        "work_id",
        "source_module_id",
        "source_record_kind",
        "source_record_id",
        "source_contract_version",
        "publication_kind",
        "record_set_id",
        "record_set_revision",
        "manifest_contract_version",
        "manifest_path",
        "manifest_digest_algorithm",
        "manifest_digest",
        "published_at_utc",
        "academic_work_registration_revision",
        "supersedes_publication_id",
        "is_series_head",
        "is_withdrawn",
        "withdrawn_at_utc",
        "is_current_selectable",
    ),
    "publication_capabilities": ("publication_id", "capability"),
}
_REQUIRED_INDEXES: Final[frozenset[str]] = frozenset(
    {
        "idx_class_context_school_year",
        "idx_period_calendars_current",
        "idx_periods_lifecycle_type",
        "idx_periods_dates",
        "idx_registrations_work_current",
        "idx_registrations_discovery",
        "idx_publications_work_kind",
        "idx_publications_manifest_time",
        "idx_publications_current_kind_time",
        "idx_publications_record_set",
        "idx_publication_capabilities_lookup",
    }
)


_SCHEMA_TOKEN = re.compile(
    r"'(?:''|[^'])*'|[A-Za-z_][A-Za-z0-9_]*|[0-9]+|!=|<=|>=|<>|[-+*/%=(),.]"
)


def _normalized_schema_sql(value: str) -> tuple[str, ...]:
    """Return a whitespace-independent token signature for SQLite DDL."""
    return tuple(_SCHEMA_TOKEN.findall(value.lower()))


def _schema_signature(
    connection: sqlite3.Connection,
) -> tuple[
    tuple[tuple[str, str, str, tuple[str, ...]], ...],
    tuple[tuple[str, tuple[tuple[object, ...], ...]], ...],
]:
    declarations = tuple(
        (
            cast(str, row[0]),
            cast(str, row[1]),
            cast(str, row[2]),
            _normalized_schema_sql(cast(str, row[3])),
        )
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE type IN ('table','index') AND sql IS NOT NULL "
            "ORDER BY type,name"
        )
    )
    tables = tuple(
        (
            table,
            tuple(
                tuple(item)
                for item in connection.execute(
                    f"PRAGMA table_info({_quoted_identifier(table)})"
                )
            ),
        )
        for table in sorted(_REQUIRED_COLUMNS)
        if connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )
    return declarations, tables


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


@lru_cache(maxsize=1)
def _required_schema_signature() -> tuple[
    tuple[tuple[str, str, str, tuple[str, ...]], ...],
    tuple[tuple[str, tuple[tuple[object, ...], ...]], ...],
]:
    expected = sqlite3.connect(":memory:", isolation_level=None)
    try:
        expected.execute("PRAGMA foreign_keys=ON")
        expected.executescript(_SCHEMA)
        return _schema_signature(expected)
    finally:
        expected.close()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _metadata(projection: _Projection, built_at: datetime) -> AcademicCatalogMetadata:
    return AcademicCatalogMetadata(
        ACADEMIC_CATALOG_SCHEMA_VERSION,
        built_at,
        projection.snapshot_sha256,
        len(projection.sources),
        len(projection.classes),
        len(projection.calendars),
        sum(len(calendar.periods) for calendar, _ in projection.calendars),
        len(projection.registrations),
        sum(len(reg.source_records) for reg, _ in projection.registrations),
        len(projection.publications),
        sum(len(pub.capabilities) for pub in projection.publications),
        len(projection.withdrawals),
    )


def _insert_projection(
    connection: sqlite3.Connection,
    projection: _Projection,
    metadata: AcademicCatalogMetadata,
) -> None:
    connection.execute(
        "INSERT INTO catalog_metadata VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            metadata.schema_version,
            _utc_text(metadata.built_at_utc),
            metadata.source_snapshot_sha256,
            metadata.source_file_count,
            metadata.class_count,
            metadata.calendar_revision_count,
            metadata.period_count,
            metadata.registration_revision_count,
            metadata.registration_source_count,
            metadata.publication_count,
            metadata.publication_capability_count,
            metadata.withdrawal_count,
        ),
    )
    connection.executemany(
        "INSERT INTO catalog_sources VALUES (?,?,?)",
        (
            (item.relative_path, item.size_bytes, item.sha256)
            for item in projection.sources
        ),
    )
    connection.executemany(
        "INSERT INTO class_context VALUES (?,?,?,?,?)", projection.classes
    )
    for calendar, current in projection.calendars:
        connection.execute(
            "INSERT INTO academic_period_calendars VALUES (?,?,?,?,?,?)",
            (
                calendar.school_year,
                calendar.calendar_revision,
                calendar.schema_version,
                _utc_text(calendar.created_at),
                _utc_text(calendar.updated_at),
                int(current),
            ),
        )
        connection.executemany(
            "INSERT INTO academic_periods VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    calendar.school_year,
                    calendar.calendar_revision,
                    p.period_id,
                    p.period_type,
                    p.label,
                    p.start_date.isoformat(),
                    p.end_date.isoformat(),
                    p.parent_period_id,
                    p.sequence,
                    p.lifecycle,
                )
                for p in calendar.periods
            ),
        )
    for registration, current in projection.registrations:
        work = registration.work
        connection.execute(
            "INSERT INTO academic_work_registrations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                work.class_id,
                work.module_id,
                work.work_id,
                registration.registration_revision,
                registration.schema_version,
                registration.producer_contract_version,
                registration.title,
                registration.work_kind,
                registration.academic_intent,
                registration.lifecycle,
                _utc_text(registration.created_at),
                _utc_text(registration.updated_at),
                int(current),
            ),
        )
        connection.executemany(
            "INSERT INTO academic_work_registration_sources VALUES (?,?,?,?,?,?,?,?,?)",
            (
                (
                    work.class_id,
                    work.module_id,
                    work.work_id,
                    registration.registration_revision,
                    index,
                    source.module_id,
                    source.record_kind,
                    source.record_id,
                    source.contract_version,
                )
                for index, source in enumerate(registration.source_records)
            ),
        )
    withdrawals = {item.publication_id: item for item in projection.withdrawals}
    for publication in projection.publications:
        work, source = publication.work, publication.source_record
        withdrawal = withdrawals.get(publication.publication_id)
        head = publication.publication_id in projection.heads
        connection.execute(
            "INSERT INTO publications VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                publication.publication_id,
                work.class_id,
                work.module_id,
                work.work_id,
                None if source is None else source.module_id,
                None if source is None else source.record_kind,
                None if source is None else source.record_id,
                None if source is None else source.contract_version,
                publication.publication_kind,
                publication.record_set_id,
                publication.record_set_revision,
                publication.manifest_contract_version,
                publication.manifest_path,
                publication.manifest_digest_algorithm,
                publication.manifest_digest,
                _utc_text(publication.published_at),
                publication.academic_work_registration_revision,
                publication.supersedes_publication_id,
                int(head),
                int(withdrawal is not None),
                None if withdrawal is None else _utc_text(withdrawal.withdrawn_at),
                int(head and withdrawal is None),
            ),
        )
        connection.executemany(
            "INSERT INTO publication_capabilities VALUES (?,?)",
            (
                (publication.publication_id, capability)
                for capability in publication.capabilities
            ),
        )


def _check_candidate_integrity(connection: sqlite3.Connection) -> None:
    if tuple(connection.execute("PRAGMA foreign_key_check")):
        raise AcademicCatalogIntegrityError("Candidate foreign-key check failed.")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise AcademicCatalogIntegrityError("Candidate integrity check failed.")


def _commit_candidate(connection: sqlite3.Connection) -> None:
    connection.commit()


def _read_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise AcademicCatalogNotFoundError(f"Academic catalog does not exist: {path}")
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection
    except sqlite3.Error as error:
        raise AcademicCatalogReadError(
            f"Could not open academic catalog {path}: {error}"
        ) from error
    except OSError as error:
        raise AcademicCatalogReadError(
            f"Could not resolve academic catalog {path}: {error}"
        ) from error


def _catalog_sidecars(path: Path) -> tuple[Path, Path, Path]:
    return (
        Path(f"{path}-journal"),
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
    )


def _cleanup_paths(paths: Sequence[Path]) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    failures: list[str] = []
    for cleanup_path in paths:
        try:
            cleanup_path.unlink(missing_ok=True)
        except OSError as error:
            failures.append(f"unlink {cleanup_path}: {error}")
    remaining: list[Path] = []
    for cleanup_path in paths:
        try:
            if cleanup_path.exists():
                remaining.append(cleanup_path)
        except OSError as error:
            failures.append(f"inspect {cleanup_path}: {error}")
    return tuple(failures), tuple(remaining)


def _remove_catalog_sidecars(path: Path, *, action: str) -> None:
    failures, remaining = _cleanup_paths(_catalog_sidecars(path))
    if failures or remaining:
        raise AcademicCatalogBuildError(
            f"Academic catalog sidecar cleanup during {action} failed; the catalog "
            f"is preserved at {path}; remaining paths: "
            f"{', '.join(map(str, remaining)) or 'none'}; failures: "
            f"{' | '.join(failures) or 'post-cleanup absence verification failed'}."
        )


def _read_catalog_application_id(path: Path) -> int:
    try:
        uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.execute("PRAGMA query_only=ON")
    except (sqlite3.Error, OSError) as error:
        raise AcademicCatalogReadError(
            f"Could not open academic catalog for identity validation {path}: {error}"
        ) from error
    try:
        try:
            row = connection.execute("PRAGMA application_id").fetchone()
        except sqlite3.DatabaseError as error:
            raise AcademicCatalogReadError(
                f"Could not establish SQLite identity for {path}: {error}"
            ) from error
        if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
            raise AcademicCatalogCompatibilityError(
                f"Could not establish academic catalog identity for {path}."
            )
        return row[0]
    finally:
        connection.close()


_CLASS_SOURCE = re.compile(r"^classes/([^/]+)/class\.json$")
_CALENDAR_CURRENT_SOURCE = re.compile(
    r"^settings/academic_periods/([^/]+)/current\.json$"
)
_CALENDAR_REVISION_SOURCE = re.compile(
    r"^settings/academic_periods/([^/]+)/revisions/([1-9][0-9]*)\.json$"
)
_REGISTRATION_CURRENT_SOURCE = re.compile(
    r"^registry/work/([^/]+)/([^/]+)/([^/]+)/current\.json$"
)
_REGISTRATION_REVISION_SOURCE = re.compile(
    r"^registry/work/([^/]+)/([^/]+)/([^/]+)/revisions/([1-9][0-9]*)\.json$"
)
_PUBLICATION_SOURCE = re.compile(
    r"^registry/publications/(pub_[0-9a-f]{32})\.json$"
)
_WITHDRAWAL_SOURCE = re.compile(
    r"^registry/withdrawals/(pub_[0-9a-f]{32})\.json$"
)


def _validate_source_namespaces(
    connection: sqlite3.Connection, inventory: Sequence[_Source]
) -> frozenset[str]:
    classes: set[str] = set()
    calendar_current: set[str] = set()
    calendar_revisions: set[tuple[str, int]] = set()
    registration_current: set[tuple[str, str, str]] = set()
    registration_revisions: set[tuple[str, str, str, int]] = set()
    publications: set[str] = set()
    withdrawals: set[str] = set()
    try:
        for source in inventory:
            path = source.relative_path
            if match := _CLASS_SOURCE.fullmatch(path):
                classes.add(_source_identifier(match.group(1), "class_id", lowercase=False))
            elif match := _CALENDAR_CURRENT_SOURCE.fullmatch(path):
                calendar_current.add(validate_school_year(match.group(1)))
            elif match := _CALENDAR_REVISION_SOURCE.fullmatch(path):
                calendar_revisions.add(
                    (validate_school_year(match.group(1)), int(match.group(2)))
                )
            elif match := _REGISTRATION_CURRENT_SOURCE.fullmatch(path):
                work = ModuleWorkRef(match.group(2), match.group(1), match.group(3))
                registration_current.add(
                    (work.class_id, work.module_id, work.work_id)
                )
            elif match := _REGISTRATION_REVISION_SOURCE.fullmatch(path):
                work = ModuleWorkRef(match.group(2), match.group(1), match.group(3))
                registration_revisions.add(
                    (work.class_id, work.module_id, work.work_id, int(match.group(4)))
                )
            elif match := _PUBLICATION_SOURCE.fullmatch(path):
                publications.add(match.group(1))
            elif match := _WITHDRAWAL_SOURCE.fullmatch(path):
                withdrawals.add(match.group(1))
            else:
                raise AcademicCatalogIntegrityError(
                    f"Catalog source path is outside supported namespaces: {path}."
                )
    except (ValueError, TypeError) as error:
        raise AcademicCatalogIntegrityError(
            f"Catalog source inventory contains a malformed identity: {error}"
        ) from error

    expected_classes = {
        cast(str, row[0])
        for row in connection.execute(
            "SELECT class_id FROM class_context WHERE metadata_present=1"
        )
    }
    expected_calendar_revisions = {
        (cast(str, row[0]), cast(int, row[1]))
        for row in connection.execute(
            "SELECT school_year,calendar_revision FROM academic_period_calendars"
        )
    }
    expected_calendar_current = {item[0] for item in expected_calendar_revisions}
    expected_registration_revisions = {
        (cast(str, row[0]), cast(str, row[1]), cast(str, row[2]), cast(int, row[3]))
        for row in connection.execute(
            "SELECT class_id,module_id,work_id,registration_revision "
            "FROM academic_work_registrations"
        )
    }
    expected_registration_current = {
        item[:3] for item in expected_registration_revisions
    }
    expected_publications = {
        cast(str, row[0])
        for row in connection.execute("SELECT publication_id FROM publications")
    }
    expected_withdrawals = {
        cast(str, row[0])
        for row in connection.execute(
            "SELECT publication_id FROM publications WHERE is_withdrawn=1"
        )
    }
    comparisons = (
        ("class metadata", classes, expected_classes),
        ("calendar pointers", calendar_current, expected_calendar_current),
        ("calendar revisions", calendar_revisions, expected_calendar_revisions),
        ("registration pointers", registration_current, expected_registration_current),
        (
            "registration revisions",
            registration_revisions,
            expected_registration_revisions,
        ),
        ("publication records", publications, expected_publications),
        ("publication withdrawals", withdrawals, expected_withdrawals),
    )
    for description, actual, expected in comparisons:
        if actual != expected:
            raise AcademicCatalogIntegrityError(
                f"Catalog source {description} do not correspond exactly to projected rows."
            )
    return frozenset(withdrawals)


def _verify_semantic_histories(connection: sqlite3.Connection) -> None:
    try:
        calendars: dict[str, list[tuple[AcademicPeriodCalendar, bool]]] = {}
        for calendar_row in connection.execute(
            "SELECT * FROM academic_period_calendars "
            "ORDER BY school_year,calendar_revision"
        ):
            periods = tuple(
                AcademicPeriod(
                    row["period_id"],
                    row["period_type"],
                    row["label"],
                    date.fromisoformat(row["start_date"]),
                    date.fromisoformat(row["end_date"]),
                    row["parent_period_id"],
                    row["sequence"],
                    row["lifecycle"],
                )
                for row in connection.execute(
                    "SELECT * FROM academic_periods WHERE school_year=? "
                    "AND calendar_revision=? ORDER BY sequence,period_id",
                    (
                        calendar_row["school_year"],
                        calendar_row["calendar_revision"],
                    ),
                )
            )
            calendar = AcademicPeriodCalendar(
                calendar_row["schema_version"],
                "academic_period_calendar",
                calendar_row["school_year"],
                calendar_row["calendar_revision"],
                _parse_utc_text(calendar_row["created_at_utc"], "created_at_utc"),
                _parse_utc_text(calendar_row["updated_at_utc"], "updated_at_utc"),
                periods,
            )
            calendars.setdefault(calendar.school_year, []).append(
                (calendar, _db_bool(calendar_row["is_current"], "is_current"))
            )
        for calendar_history in calendars.values():
            for previous, candidate in zip(
                calendar_history, calendar_history[1:], strict=False
            ):
                validate_academic_period_calendar_transition(
                    previous[0], candidate[0]
                )
            if (
                sum(current for _, current in calendar_history) != 1
                or not calendar_history[-1][1]
            ):
                raise ValueError("calendar current revision is not the final revision")

        registrations: dict[
            tuple[str, str, str], list[tuple[AcademicWorkRegistration, bool]]
        ] = {}
        for row in connection.execute(
            "SELECT r.*,c.school_year FROM academic_work_registrations r "
            "JOIN class_context c USING(class_id) "
            "ORDER BY r.class_id,r.module_id,r.work_id,r.registration_revision"
        ):
            registration_item = _registration_row(connection, row)
            registration = AcademicWorkRegistration(
                registration_item.schema_version,
                "academic_work_registration",
                registration_item.work,
                registration_item.registration_revision,
                registration_item.producer_contract_version,
                registration_item.title,
                registration_item.work_kind,
                registration_item.academic_intent,
                registration_item.lifecycle,
                registration_item.created_at,
                registration_item.updated_at,
                registration_item.source_records,
            )
            registration_identity = (
                registration_item.class_id,
                registration_item.module_id,
                registration_item.work_id,
            )
            registrations.setdefault(registration_identity, []).append(
                (registration, registration_item.is_current_registration)
            )
        for registration_history in registrations.values():
            for registration_previous, registration_candidate in zip(
                registration_history, registration_history[1:], strict=False
            ):
                validate_academic_work_registration_transition(
                    registration_previous[0], registration_candidate[0]
                )
            if (
                sum(current for _, current in registration_history) != 1
                or not registration_history[-1][1]
            ):
                raise ValueError("registration current revision is not the final revision")

        publication_rows = connection.execute(
            "SELECT p.*,c.school_year,rr.lifecycle AS referenced_lifecycle,"
            "cr.registration_revision AS current_revision,"
            "cr.lifecycle AS current_lifecycle FROM publications p "
            "JOIN class_context c USING(class_id) "
            "LEFT JOIN academic_work_registrations rr ON rr.class_id=p.class_id "
            "AND rr.module_id=p.module_id AND rr.work_id=p.work_id "
            "AND rr.registration_revision=p.academic_work_registration_revision "
            "LEFT JOIN academic_work_registrations cr ON cr.class_id=p.class_id "
            "AND cr.module_id=p.module_id AND cr.work_id=p.work_id AND cr.is_current=1 "
            "ORDER BY p.publication_id"
        ).fetchall()
        series: dict[
            tuple[str, str, str, str, str], list[tuple[PublicationRecord, bool]]
        ] = {}
        for row in publication_rows:
            publication_item = _publication_row(connection, row)
            record = PublicationRecord(
                "1",
                "publication_record",
                publication_item.publication_id,
                publication_item.work,
                publication_item.source_record,
                publication_item.publication_kind,
                publication_item.capabilities,
                publication_item.record_set_id,
                publication_item.record_set_revision,
                publication_item.manifest_contract_version,
                publication_item.manifest_path,
                publication_item.manifest_digest_algorithm,
                publication_item.manifest_digest,
                publication_item.published_at,
                publication_item.academic_work_registration_revision,
                publication_item.supersedes_publication_id,
            )
            publication_identity = (
                publication_item.class_id,
                publication_item.module_id,
                publication_item.work_id,
                publication_item.publication_kind,
                publication_item.record_set_id,
            )
            series.setdefault(publication_identity, []).append(
                (record, publication_item.is_series_head)
            )
        for publication_history in series.values():
            validated = validate_publication_record_series(
                record for record, _ in publication_history
            )
            predecessor_ids = {
                item.supersedes_publication_id
                for item in validated
                if item.supersedes_publication_id is not None
            }
            head = next(
                item.publication_id
                for item in validated
                if item.publication_id not in predecessor_ids
            )
            stored_heads = {
                record.publication_id
                for record, is_head in publication_history
                if is_head
            }
            if stored_heads != {head}:
                raise ValueError("publication head flags disagree with validated series")
    except AcademicCatalogIntegrityError:
        raise
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise AcademicCatalogIntegrityError(
            f"Academic catalog semantic history is invalid: {error}"
        ) from error


def _verify(connection: sqlite3.Connection) -> AcademicCatalogMetadata:
    try:
        application_id = cast(
            int, connection.execute("PRAGMA application_id").fetchone()[0]
        )
        user_version = cast(
            int, connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if application_id != ACADEMIC_CATALOG_APPLICATION_ID:
            raise AcademicCatalogCompatibilityError(
                f"Wrong academic catalog application ID: {application_id}."
            )
        if user_version != ACADEMIC_CATALOG_SCHEMA_VERSION:
            raise AcademicCatalogCompatibilityError(
                f"Unsupported academic catalog schema version: {user_version}."
            )
        if _schema_signature(connection) != _required_schema_signature():
            raise AcademicCatalogCompatibilityError(
                "Academic catalog runtime schema signature is incompatible."
            )
        foreign = tuple(connection.execute("PRAGMA foreign_key_check"))
        if foreign:
            raise AcademicCatalogIntegrityError(
                "Academic catalog foreign-key check failed."
            )
        integrity = cast(
            str, connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        if integrity != "ok":
            raise AcademicCatalogIntegrityError(
                f"Academic catalog integrity check failed: {integrity}"
            )
        row = connection.execute(
            "SELECT * FROM catalog_metadata WHERE singleton=1"
        ).fetchone()
        if (
            row is None
            or connection.execute("SELECT count(*) FROM catalog_metadata").fetchone()[0]
            != 1
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog metadata row is missing or duplicated."
            )
        metadata = _metadata_from_row(row)
        inventory: list[_Source] = []
        for source_row in connection.execute(
            "SELECT relative_path,size_bytes,sha256 "
            "FROM catalog_sources ORDER BY relative_path"
        ):
            relative_path = source_row["relative_path"]
            size_bytes = source_row["size_bytes"]
            sha256 = source_row["sha256"]
            if not isinstance(relative_path, str):
                raise AcademicCatalogIntegrityError("Catalog source path is invalid.")
            pure = PurePosixPath(relative_path)
            if (
                not relative_path
                or "\\" in relative_path
                or pure.is_absolute()
                or ".." in pure.parts
                or pure.as_posix() != relative_path
            ):
                raise AcademicCatalogIntegrityError(
                    f"Catalog source path is unsafe: {relative_path!r}."
                )
            if (
                isinstance(size_bytes, bool)
                or not isinstance(size_bytes, int)
                or size_bytes < 0
                or not isinstance(sha256, str)
                or _SHA256.fullmatch(sha256) is None
            ):
                raise AcademicCatalogIntegrityError(
                    f"Catalog source inventory row is invalid: {relative_path}."
                )
            inventory.append(_Source(relative_path, size_bytes, sha256, b""))
        if _snapshot(inventory) != metadata.source_snapshot_sha256:
            raise AcademicCatalogIntegrityError(
                "Catalog source snapshot digest does not match its inventory."
            )
        withdrawal_source_ids = _validate_source_namespaces(connection, inventory)
        count_queries = {
            "source_file_count": "catalog_sources",
            "class_count": "class_context",
            "calendar_revision_count": "academic_period_calendars",
            "period_count": "academic_periods",
            "registration_revision_count": "academic_work_registrations",
            "registration_source_count": "academic_work_registration_sources",
            "publication_count": "publications",
            "publication_capability_count": "publication_capabilities",
        }
        for field, table in count_queries.items():
            if (
                getattr(metadata, field)
                != connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            ):
                raise AcademicCatalogIntegrityError(
                    f"Academic catalog {field} does not match projected rows."
                )
        if (
            metadata.withdrawal_count
            != connection.execute(
                "SELECT count(*) FROM publications WHERE is_withdrawn=1"
            ).fetchone()[0]
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog withdrawal_count does not match projected rows."
            )
        invalid_state_checks = (
            "SELECT 1 FROM class_context WHERE metadata_present NOT IN (0,1) "
            "OR (metadata_present=0 AND NOT (school_year IS NULL AND created_at_utc IS NULL AND updated_at_utc IS NULL)) "
            "OR (metadata_present=1 AND (school_year IS NULL OR created_at_utc IS NULL OR updated_at_utc IS NULL)) LIMIT 1",
            "SELECT 1 FROM academic_period_calendars WHERE is_current NOT IN (0,1) LIMIT 1",
            "SELECT 1 FROM academic_work_registrations WHERE is_current NOT IN (0,1) LIMIT 1",
            "SELECT 1 FROM publications WHERE is_series_head NOT IN (0,1) "
            "OR is_withdrawn NOT IN (0,1) OR is_current_selectable NOT IN (0,1) "
            "OR (is_withdrawn=1) != (withdrawn_at_utc IS NOT NULL) "
            "OR is_current_selectable != CASE WHEN is_series_head=1 AND is_withdrawn=0 THEN 1 ELSE 0 END LIMIT 1",
        )
        if any(
            connection.execute(statement).fetchone() is not None
            for statement in invalid_state_checks
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog contains an invalid derived state value."
            )
        if (
            connection.execute(
                "SELECT 1 FROM academic_period_calendars GROUP BY school_year "
                "HAVING sum(is_current) != 1 OR "
                "max(CASE WHEN is_current=1 THEN calendar_revision END) != "
                "max(calendar_revision) LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog has contradictory current calendar state."
            )
        if (
            connection.execute(
                "SELECT 1 FROM academic_work_registrations "
                "GROUP BY class_id,module_id,work_id HAVING sum(is_current) != 1 OR "
                "max(CASE WHEN is_current=1 THEN registration_revision END) != "
                "max(registration_revision) LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog has contradictory current registration state."
            )
        if (
            connection.execute(
                "SELECT 1 FROM publications GROUP BY class_id,module_id,work_id,"
                "publication_kind,record_set_id HAVING sum(is_series_head) != 1 LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog has contradictory publication head state."
            )
        if (
            connection.execute(
                "SELECT 1 FROM publications p WHERE p.is_series_head != "
                "CASE WHEN NOT EXISTS (SELECT 1 FROM publications successor "
                "WHERE successor.class_id=p.class_id AND successor.module_id=p.module_id "
                "AND successor.work_id=p.work_id AND successor.publication_kind=p.publication_kind "
                "AND successor.record_set_id=p.record_set_id "
                "AND successor.supersedes_publication_id=p.publication_id) "
                "THEN 1 ELSE 0 END LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog publication head flags disagree with supersession relationships."
            )
        if (
            connection.execute(
                "SELECT 1 FROM publications successor JOIN publications predecessor "
                "ON predecessor.publication_id=successor.supersedes_publication_id "
                "WHERE (successor.class_id,successor.module_id,successor.work_id,"
                "successor.publication_kind,successor.record_set_id) != "
                "(predecessor.class_id,predecessor.module_id,predecessor.work_id,"
                "predecessor.publication_kind,predecessor.record_set_id) LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog contains a cross-series supersession relationship."
            )
        withdrawn_ids = {
            cast(str, item[0])
            for item in connection.execute(
                "SELECT publication_id FROM publications WHERE is_withdrawn=1"
            )
        }
        publication_ids = {
            cast(str, item[0])
            for item in connection.execute("SELECT publication_id FROM publications")
        }
        if (
            withdrawal_source_ids != withdrawn_ids
            or not withdrawal_source_ids <= publication_ids
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog withdrawal flags disagree with canonical withdrawal sources."
            )
        if (
            connection.execute(
                "SELECT 1 FROM academic_work_registration_sources "
                "GROUP BY class_id,module_id,work_id,registration_revision "
                "HAVING min(position) != 0 OR max(position) != count(*)-1 "
                "OR count(DISTINCT position) != count(*) LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise AcademicCatalogIntegrityError(
                "Academic catalog registration source positions are not zero-based and contiguous."
            )
        capabilities = {
            cast(str, item[0])
            for item in connection.execute(
                "SELECT DISTINCT capability FROM publication_capabilities"
            )
        }
        if not capabilities <= PUBLICATION_CAPABILITIES:
            raise AcademicCatalogIntegrityError(
                "Academic catalog contains an unsupported publication capability."
            )
        _verify_semantic_histories(connection)
        return metadata
    except (AcademicCatalogCompatibilityError, AcademicCatalogIntegrityError):
        raise
    except sqlite3.DatabaseError as error:
        raise AcademicCatalogReadError(
            f"Could not read academic catalog: {error}"
        ) from error


def _metadata_from_row(row: sqlite3.Row) -> AcademicCatalogMetadata:
    try:
        return AcademicCatalogMetadata(
            schema_version=row["schema_version"],
            built_at_utc=_parse_utc_text(row["built_at_utc"], "built_at_utc"),
            source_snapshot_sha256=row["source_snapshot_sha256"],
            source_file_count=row["source_file_count"],
            class_count=row["class_count"],
            calendar_revision_count=row["calendar_revision_count"],
            period_count=row["period_count"],
            registration_revision_count=row["registration_revision_count"],
            registration_source_count=row["registration_source_count"],
            publication_count=row["publication_count"],
            publication_capability_count=row["publication_capability_count"],
            withdrawal_count=row["withdrawal_count"],
        )
    except (KeyError, IndexError, AcademicCatalogValidationError) as error:
        raise AcademicCatalogIntegrityError(
            f"Academic catalog metadata is invalid: {error}"
        ) from error


def rebuild_academic_catalog(workspace_root: str | Path) -> AcademicCatalogBuildResult:
    root = _workspace_root(workspace_root)
    target = academic_catalog_path(root)
    lock = academic_catalog_lock_path(root)
    temp_path: Path | None = None
    lock_created = False
    replaced = False
    try:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            lock.parent.mkdir(parents=True, exist_ok=True)
            with lock.open("x", encoding="utf-8"):
                pass
            lock_created = True
        except FileExistsError as error:
            raise AcademicCatalogConflictError(
                f"Academic catalog rebuild lock already exists: {lock}"
            ) from error
        except OSError as error:
            raise AcademicCatalogBuildError(
                f"Could not acquire academic catalog rebuild lock {lock}: {error}"
            ) from error
        projection = _load_projection(root)
        metadata = _metadata(projection, _utc_now())
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=".catalog.sqlite.", suffix=".tmp", dir=target.parent
            )
            temp_path = Path(name)
            os.close(descriptor)
            connection = sqlite3.connect(temp_path, isolation_level=None)
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    f"PRAGMA application_id={ACADEMIC_CATALOG_APPLICATION_ID}"
                )
                connection.execute(
                    f"PRAGMA user_version={ACADEMIC_CATALOG_SCHEMA_VERSION}"
                )
                connection.executescript("BEGIN IMMEDIATE;" + _SCHEMA)
                _insert_projection(connection, projection, metadata)
                _check_candidate_integrity(connection)
                _commit_candidate(connection)
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
            with temp_path.open("r+b") as database_file:
                os.fsync(database_file.fileno())
            check = _read_connection(temp_path)
            try:
                verified = _verify(check)
            finally:
                check.close()
            if verified != metadata:
                raise AcademicCatalogIntegrityError(
                    "Candidate catalog metadata changed during verification."
                )
        except (AcademicCatalogError, sqlite3.Error, OSError) as error:
            if isinstance(error, AcademicCatalogError):
                raise
            raise AcademicCatalogBuildError(
                f"Could not build candidate academic catalog: {error}"
            ) from error

        try:
            second = _read_sources(
                root, [root / source.relative_path for source in projection.sources]
            )
            current_paths = _discover_base_paths(root)
        except AcademicCatalogSourceError as error:
            raise AcademicCatalogConflictError(
                "Canonical source snapshot changed during catalog rebuild."
            ) from error
        expected_base = {
            source.relative_path
            for source in projection.sources
            if not source.relative_path.startswith("classes/")
        }
        actual_base = {path.relative_to(root).as_posix() for path in current_paths}
        missing_class_state_changed = any(
            metadata_present == 0 and class_metadata_path(root, class_id).exists()
            for class_id, _, metadata_present, _, _ in projection.classes
        )
        if (
            expected_base != actual_base
            or _snapshot(second) != projection.snapshot_sha256
            or missing_class_state_changed
        ):
            raise AcademicCatalogConflictError(
                "Canonical source snapshot changed during catalog rebuild."
            )
        replaced_existing = target.exists()
        try:
            os.replace(temp_path, target)
            temp_path = None
            replaced = True
        except OSError as error:
            raise AcademicCatalogBuildError(
                f"Could not install academic catalog {target}: {error}"
            ) from error
        _remove_catalog_sidecars(target, action="rebuild")
        installed = _read_connection(target)
        try:
            installed_metadata = _verify(installed)
        finally:
            installed.close()
        if installed_metadata != metadata:
            raise AcademicCatalogBuildError(
                f"Installed academic catalog failed final verification: {target}"
            )
        _fsync_directory(target.parent)
        return AcademicCatalogBuildResult(target, metadata, replaced_existing)
    except (
        AcademicCatalogConflictError,
        AcademicCatalogSourceError,
        AcademicCatalogBuildError,
    ):
        raise
    except AcademicCatalogError as error:
        if replaced:
            raise AcademicCatalogBuildError(
                f"Installed academic catalog failed verification and was preserved at {target}: {error}"
            ) from error
        raise AcademicCatalogBuildError(
            f"Academic catalog rebuild failed: {error}"
        ) from error
    except (OSError, sqlite3.Error) as error:
        if replaced:
            raise AcademicCatalogBuildError(
                f"Installed academic catalog failed verification and was preserved at {target}: {error}"
            ) from error
        raise AcademicCatalogBuildError(
            f"Academic catalog rebuild failed: {error}"
        ) from error
    finally:
        primary_error = sys.exception()
        cleanup_failures: list[str] = []
        remaining_paths: list[Path] = []
        if temp_path is not None:
            candidate_paths = (
                temp_path,
                Path(f"{temp_path}-journal"),
                Path(f"{temp_path}-wal"),
                Path(f"{temp_path}-shm"),
            )
            failures, remaining = _cleanup_paths(candidate_paths)
            cleanup_failures.extend(failures)
            remaining_paths.extend(remaining)
        if lock_created:
            failures, remaining = _cleanup_paths((lock,))
            cleanup_failures.extend(failures)
            remaining_paths.extend(remaining)
        if cleanup_failures or remaining_paths:
            try:
                catalog_exists = target.exists()
            except OSError as error:
                catalog_exists = False
                cleanup_failures.append(f"inspect {target}: {error}")
            state = (
                f"the installed catalog is preserved at {target}"
                if replaced
                else (
                    f"the previous catalog remains installed at {target}"
                    if catalog_exists
                    else f"no previous catalog remains installed at {target}"
                )
            )
            cleanup_error = AcademicCatalogBuildError(
                "Academic catalog rebuild cleanup failed; "
                f"{state}; remaining paths: "
                f"{', '.join(map(str, remaining_paths)) or 'none'}; failures: "
                f"{' | '.join(cleanup_failures) or 'absence verification failed'}."
            )
            if primary_error is not None:
                raise cleanup_error from primary_error
            raise cleanup_error


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def load_academic_catalog_metadata(
    workspace_root: str | Path,
) -> AcademicCatalogMetadata:
    path = academic_catalog_path(_workspace_root(workspace_root))
    connection = _read_connection(path)
    try:
        return _verify(connection)
    finally:
        connection.close()


def _limit(
    sql: str, parameters: list[object], limit: int | None, offset: int
) -> tuple[str, list[object]]:
    if limit is not None:
        return sql + " LIMIT ? OFFSET ?", [*parameters, limit, offset]
    if offset:
        return sql + " LIMIT -1 OFFSET ?", [*parameters, offset]
    return sql, parameters


def query_academic_period_catalog(
    workspace_root: str | Path,
    query: AcademicPeriodCatalogQuery = AcademicPeriodCatalogQuery(),
) -> tuple[CatalogAcademicPeriod, ...]:
    if not isinstance(query, AcademicPeriodCatalogQuery):
        raise AcademicCatalogValidationError(
            "query must be an AcademicPeriodCatalogQuery."
        )
    connection = _read_connection(
        academic_catalog_path(_workspace_root(workspace_root))
    )
    try:
        _verify(connection)
        conditions: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("p.school_year", query.school_year),
            ("p.period_type", query.period_type),
            ("p.lifecycle", query.lifecycle),
        ):
            if value is not None:
                conditions.append(f"{column}=?")
                parameters.append(value)
        if query.current_calendar_only:
            conditions.append("c.is_current=1")
        if query.active_on is not None:
            conditions.extend(("p.start_date<=?", "p.end_date>=?"))
            parameters.extend(
                (query.active_on.isoformat(), query.active_on.isoformat())
            )
        sql = "SELECT p.*,c.schema_version,c.created_at_utc,c.updated_at_utc,c.is_current FROM academic_periods p JOIN academic_period_calendars c USING(school_year,calendar_revision)"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY p.school_year,p.calendar_revision,p.sequence,p.period_id"
        sql, parameters = _limit(sql, parameters, query.limit, query.offset)
        rows = connection.execute(sql, parameters).fetchall()
        return tuple(_period_row(row) for row in rows)
    except sqlite3.Error as error:
        raise AcademicCatalogReadError(
            f"Could not query academic-period catalog: {error}"
        ) from error
    finally:
        connection.close()


def _period_row(row: sqlite3.Row) -> CatalogAcademicPeriod:
    try:
        period = AcademicPeriod(
            row["period_id"],
            row["period_type"],
            row["label"],
            date.fromisoformat(row["start_date"]),
            date.fromisoformat(row["end_date"]),
            row["parent_period_id"],
            row["sequence"],
            row["lifecycle"],
        )
        return CatalogAcademicPeriod(
            row["school_year"],
            row["calendar_revision"],
            row["schema_version"],
            _parse_utc_text(row["created_at_utc"], "created_at_utc"),
            _parse_utc_text(row["updated_at_utc"], "updated_at_utc"),
            _db_bool(row["is_current"], "is_current"),
            period,
        )
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise AcademicCatalogIntegrityError(
            f"Invalid catalog academic-period row: {error}"
        ) from error


def query_academic_work_registration_catalog(
    workspace_root: str | Path,
    query: AcademicWorkRegistrationCatalogQuery = AcademicWorkRegistrationCatalogQuery(),
) -> tuple[CatalogAcademicWorkRegistration, ...]:
    if not isinstance(query, AcademicWorkRegistrationCatalogQuery):
        raise AcademicCatalogValidationError(
            "query must be an AcademicWorkRegistrationCatalogQuery."
        )
    connection = _read_connection(
        academic_catalog_path(_workspace_root(workspace_root))
    )
    try:
        _verify(connection)
        conditions: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("c.school_year", query.school_year),
            ("r.class_id", query.class_id),
            ("r.module_id", query.module_id),
            ("r.work_id", query.work_id),
            ("r.producer_contract_version", query.producer_contract_version),
            ("r.academic_intent", query.academic_intent),
            ("r.lifecycle", query.lifecycle),
        ):
            if value is not None:
                conditions.append(f"{column}=?")
                parameters.append(value)
        if query.current_only:
            conditions.append("r.is_current=1")
        sql = "SELECT r.*,c.school_year FROM academic_work_registrations r JOIN class_context c USING(class_id)"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY c.school_year IS NULL,c.school_year,r.class_id,r.module_id,r.work_id,r.registration_revision"
        sql, parameters = _limit(sql, parameters, query.limit, query.offset)
        rows = connection.execute(sql, parameters).fetchall()
        return tuple(_registration_row(connection, row) for row in rows)
    except sqlite3.Error as error:
        raise AcademicCatalogReadError(
            f"Could not query registration catalog: {error}"
        ) from error
    finally:
        connection.close()


def _registration_row(
    connection: sqlite3.Connection, row: sqlite3.Row
) -> CatalogAcademicWorkRegistration:
    try:
        source_rows = connection.execute(
            "SELECT * FROM academic_work_registration_sources WHERE class_id=? AND module_id=? AND work_id=? AND registration_revision=? ORDER BY position",
            (
                row["class_id"],
                row["module_id"],
                row["work_id"],
                row["registration_revision"],
            ),
        ).fetchall()
        sources = tuple(
            ModuleRecordRef(
                item["source_module_id"],
                item["source_record_kind"],
                item["source_record_id"],
                item["source_contract_version"],
            )
            for item in source_rows
        )
        return CatalogAcademicWorkRegistration(
            row["school_year"],
            ModuleWorkRef(row["module_id"], row["class_id"], row["work_id"]),
            row["registration_revision"],
            row["schema_version"],
            row["producer_contract_version"],
            row["title"],
            row["work_kind"],
            row["academic_intent"],
            row["lifecycle"],
            _parse_utc_text(row["created_at_utc"], "created_at_utc"),
            _parse_utc_text(row["updated_at_utc"], "updated_at_utc"),
            _db_bool(row["is_current"], "is_current"),
            sources,
        )
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise AcademicCatalogIntegrityError(
            f"Invalid catalog registration row: {error}"
        ) from error


def query_publication_catalog(
    workspace_root: str | Path,
    query: PublicationCatalogQuery = PublicationCatalogQuery(),
) -> tuple[CatalogPublication, ...]:
    if not isinstance(query, PublicationCatalogQuery):
        raise AcademicCatalogValidationError("query must be a PublicationCatalogQuery.")
    connection = _read_connection(
        academic_catalog_path(_workspace_root(workspace_root))
    )
    try:
        _verify(connection)
        conditions = []
        parameters: list[object] = []
        for column, value in (
            ("c.school_year", query.school_year),
            ("p.class_id", query.class_id),
            ("p.module_id", query.module_id),
            ("p.work_id", query.work_id),
            ("p.publication_kind", query.publication_kind),
            ("p.manifest_contract_version", query.manifest_contract_version),
            ("p.source_contract_version", query.source_contract_version),
            ("rr.producer_contract_version", query.producer_contract_version),
            ("rr.lifecycle", query.referenced_registration_lifecycle),
            ("cr.lifecycle", query.current_registration_lifecycle),
            ("p.record_set_id", query.record_set_id),
        ):
            if value is not None:
                conditions.append(f"{column}=?")
                parameters.append(value)
        if query.minimum_record_set_revision is not None:
            conditions.append("p.record_set_revision>=?")
            parameters.append(query.minimum_record_set_revision)
        if query.published_at_or_after is not None:
            conditions.append("p.published_at_utc>=?")
            parameters.append(_utc_text(query.published_at_or_after))
        if query.published_before is not None:
            conditions.append("p.published_at_utc<?")
            parameters.append(_utc_text(query.published_before))
        state = {
            "current": "p.is_current_selectable=1",
            "series_heads": "p.is_series_head=1",
            "historical": "p.is_series_head=0",
            "withdrawn": "p.is_withdrawn=1",
            "all": None,
        }[query.state]
        if state:
            conditions.append(state)
        for capability in query.required_capabilities:
            conditions.append(
                "EXISTS (SELECT 1 FROM publication_capabilities pc WHERE pc.publication_id=p.publication_id AND pc.capability=?)"
            )
            parameters.append(capability)
        sql = "SELECT p.*,c.school_year,rr.lifecycle AS referenced_lifecycle,cr.registration_revision AS current_revision,cr.lifecycle AS current_lifecycle FROM publications p JOIN class_context c USING(class_id) LEFT JOIN academic_work_registrations rr ON rr.class_id=p.class_id AND rr.module_id=p.module_id AND rr.work_id=p.work_id AND rr.registration_revision=p.academic_work_registration_revision LEFT JOIN academic_work_registrations cr ON cr.class_id=p.class_id AND cr.module_id=p.module_id AND cr.work_id=p.work_id AND cr.is_current=1"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY p.published_at_utc DESC,p.publication_id"
        sql, parameters = _limit(sql, parameters, query.limit, query.offset)
        return tuple(
            _publication_row(connection, row)
            for row in connection.execute(sql, parameters).fetchall()
        )
    except sqlite3.Error as error:
        raise AcademicCatalogReadError(
            f"Could not query publication catalog: {error}"
        ) from error
    finally:
        connection.close()


def _publication_row(
    connection: sqlite3.Connection, row: sqlite3.Row
) -> CatalogPublication:
    try:
        capabilities = tuple(
            cast(PublicationCapability, item[0])
            for item in connection.execute(
                "SELECT capability FROM publication_capabilities WHERE publication_id=? ORDER BY capability",
                (row["publication_id"],),
            )
        )
        source = (
            None
            if row["source_module_id"] is None
            else ModuleRecordRef(
                row["source_module_id"],
                row["source_record_kind"],
                row["source_record_id"],
                row["source_contract_version"],
            )
        )
        return CatalogPublication(
            row["school_year"],
            row["publication_id"],
            ModuleWorkRef(row["module_id"], row["class_id"], row["work_id"]),
            source,
            row["publication_kind"],
            capabilities,
            row["record_set_id"],
            row["record_set_revision"],
            row["manifest_contract_version"],
            row["manifest_path"],
            row["manifest_digest_algorithm"],
            row["manifest_digest"],
            _parse_utc_text(row["published_at_utc"], "published_at_utc"),
            row["academic_work_registration_revision"],
            row["referenced_lifecycle"],
            row["current_revision"],
            row["current_lifecycle"],
            row["supersedes_publication_id"],
            _db_bool(row["is_series_head"], "is_series_head"),
            _db_bool(row["is_withdrawn"], "is_withdrawn"),
            None
            if row["withdrawn_at_utc"] is None
            else _parse_utc_text(row["withdrawn_at_utc"], "withdrawn_at_utc"),
            _db_bool(row["is_current_selectable"], "is_current_selectable"),
        )
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise AcademicCatalogIntegrityError(
            f"Invalid catalog publication row: {error}"
        ) from error


def remove_academic_catalog(workspace_root: str | Path) -> bool:
    root = _workspace_root(workspace_root)
    path = academic_catalog_path(root)
    lock = academic_catalog_lock_path(root)
    try:
        exists = path.exists()
    except OSError as error:
        raise AcademicCatalogReadError(
            f"Could not inspect academic catalog path {path}: {error}"
        ) from error
    if not exists:
        return False
    lock_created = False
    removal_completed = False
    try:
        try:
            lock.parent.mkdir(parents=True, exist_ok=True)
            with lock.open("x", encoding="utf-8"):
                pass
            lock_created = True
        except FileExistsError as error:
            raise AcademicCatalogConflictError(
                f"Academic catalog operation lock already exists: {lock}"
            ) from error
        except OSError as error:
            raise AcademicCatalogBuildError(
                f"Could not acquire academic catalog removal lock {lock}: {error}"
            ) from error
        application_id = _read_catalog_application_id(path)
        if application_id != ACADEMIC_CATALOG_APPLICATION_ID:
            raise AcademicCatalogCompatibilityError(
                f"Refusing to remove database with application ID {application_id} "
                f"from the academic catalog path {path}."
            )
        _remove_catalog_sidecars(path, action="removal")
        try:
            path.unlink()
        except OSError as error:
            raise AcademicCatalogBuildError(
                f"Could not remove academic catalog {path}: {error}"
            ) from error
        removal_completed = True
        return True
    finally:
        primary_error = sys.exception()
        if lock_created:
            failures, remaining = _cleanup_paths((lock,))
            if failures or remaining:
                state = (
                    f"catalog removal completed for {path}"
                    if removal_completed
                    else f"the catalog is preserved at {path}"
                )
                cleanup_error = AcademicCatalogBuildError(
                    f"Academic catalog removal cleanup failed; {state}; "
                    f"remaining paths: {', '.join(map(str, remaining)) or 'none'}; "
                    f"failures: {' | '.join(failures) or 'absence verification failed'}."
                )
                if primary_error is not None:
                    raise cleanup_error from primary_error
                raise cleanup_error
