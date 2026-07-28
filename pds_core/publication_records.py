"""Immutable typed Publication Records and pure validation helpers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Final, Literal, TypeAlias, cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.routing_models import (
    ModuleRecordRef,
    ModuleWorkRef,
    RoutingModelError,
    module_record_ref_from_dict,
    module_record_ref_to_dict,
    module_work_ref_from_dict,
    module_work_ref_to_dict,
    validate_module_record_ref,
    validate_module_work_ref,
)

PUBLICATION_RECORD_SCHEMA_VERSION: Final[str] = "1"
PUBLICATION_RECORD_TYPE: Final[str] = "publication_record"
PUBLICATION_WITHDRAWAL_SCHEMA_VERSION: Final[str] = "1"
PUBLICATION_WITHDRAWAL_RECORD_TYPE: Final[str] = "publication_withdrawal"

PublicationKind: TypeAlias = Literal[
    "academic_result_set", "intervention_record_set"
]
PublicationCapability: TypeAlias = Literal[
    "points",
    "question_evidence",
    "multiple_attempts",
    "standards_ratings",
    "criterion_scores",
    "moderated_scores",
    "intervention_history",
    "intervention_status",
    "intervention_outcomes",
]
ManifestDigestAlgorithm: TypeAlias = Literal["sha256"]

PUBLICATION_KINDS: Final[frozenset[str]] = frozenset(
    {"academic_result_set", "intervention_record_set"}
)
ACADEMIC_RESULT_CAPABILITIES: Final[frozenset[str]] = frozenset(
    {
        "points",
        "question_evidence",
        "multiple_attempts",
        "standards_ratings",
        "criterion_scores",
        "moderated_scores",
    }
)
INTERVENTION_CAPABILITIES: Final[frozenset[str]] = frozenset(
    {"intervention_history", "intervention_status", "intervention_outcomes"}
)
PUBLICATION_CAPABILITIES: Final[frozenset[str]] = (
    ACADEMIC_RESULT_CAPABILITIES | INTERVENTION_CAPABILITIES
)

_PUBLICATION_ID = re.compile(r"^pub_[0-9a-f]{32}$")
_MANIFEST_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PUBLICATION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "record_type",
        "publication_id",
        "work",
        "source_record",
        "publication_kind",
        "capabilities",
        "record_set_id",
        "record_set_revision",
        "manifest_contract_version",
        "manifest_path",
        "manifest_digest_algorithm",
        "manifest_digest",
        "published_at",
        "academic_work_registration_revision",
        "supersedes_publication_id",
    }
)
_WITHDRAWAL_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "record_type", "publication_id", "withdrawn_at", "reason"}
)


class PublicationRecordError(ValueError):
    """Base error for Publication Record model failures."""


class PublicationRecordValidationError(PublicationRecordError):
    """Raised when a publication, withdrawal, or series is invalid."""


def is_publication_kind(value: object) -> bool:
    """Return whether *value* is an exact supported publication kind."""
    return isinstance(value, str) and value in PUBLICATION_KINDS


def is_publication_capability(value: object) -> bool:
    """Return whether *value* is an exact supported shared capability."""
    return isinstance(value, str) and value in PUBLICATION_CAPABILITIES


@dataclass(frozen=True, slots=True)
class PublicationRecord:
    """One immutable binding to an exact producer-owned manifest revision."""

    schema_version: str
    record_type: str
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
    supersedes_publication_id: str | None

    def __post_init__(self) -> None:
        _validate_publication_fields(self)


@dataclass(frozen=True, slots=True)
class PublicationWithdrawal:
    """One immutable withdrawal of a canonical Publication Record."""

    schema_version: str
    record_type: str
    publication_id: str
    withdrawn_at: datetime
    reason: str

    def __post_init__(self) -> None:
        _validate_withdrawal_fields(self)


def validate_publication_manifest_path(
    work: ModuleWorkRef, manifest_path: str
) -> str:
    """Validate a canonical workspace-relative manifest path lexically."""
    validated_work = _work(work)
    if not isinstance(manifest_path, str):
        raise PublicationRecordValidationError("manifest_path must be a string.")
    if not manifest_path:
        raise PublicationRecordValidationError("manifest_path must not be empty.")
    if manifest_path != manifest_path.strip():
        raise PublicationRecordValidationError(
            "manifest_path must not contain surrounding whitespace."
        )
    if "\x00" in manifest_path:
        raise PublicationRecordValidationError("manifest_path must not contain NUL.")
    if "\\" in manifest_path:
        raise PublicationRecordValidationError(
            "manifest_path must use forward slashes only."
        )
    windows_path = PureWindowsPath(manifest_path)
    if manifest_path.startswith("/") or windows_path.is_absolute() or windows_path.drive:
        raise PublicationRecordValidationError(
            "manifest_path must be workspace-relative."
        )
    components = manifest_path.split("/")
    if any(component == "" for component in components):
        raise PublicationRecordValidationError(
            "manifest_path must not contain empty components."
        )
    if any(component in {".", ".."} for component in components):
        raise PublicationRecordValidationError(
            "manifest_path must not contain dot or traversal components."
        )
    prefix = [
        "classes",
        validated_work.class_id,
        "modules",
        validated_work.module_id,
        "work",
        validated_work.work_id,
    ]
    if components[: len(prefix)] != prefix or len(components) <= len(prefix):
        raise PublicationRecordValidationError(
            "manifest_path must identify a descendant of the referenced module work root."
        )
    if not components[-1].endswith(".json"):
        raise PublicationRecordValidationError("manifest_path must end with .json.")
    return manifest_path


def validate_publication_record(
    value: PublicationRecord | Mapping[str, object],
) -> PublicationRecord:
    """Fully validate and return a fresh Publication Record."""
    if not isinstance(value, PublicationRecord):
        return publication_record_from_dict(value)
    return PublicationRecord(
        schema_version=value.schema_version,
        record_type=value.record_type,
        publication_id=value.publication_id,
        work=value.work,
        source_record=value.source_record,
        publication_kind=value.publication_kind,
        capabilities=value.capabilities,
        record_set_id=value.record_set_id,
        record_set_revision=value.record_set_revision,
        manifest_contract_version=value.manifest_contract_version,
        manifest_path=value.manifest_path,
        manifest_digest_algorithm=value.manifest_digest_algorithm,
        manifest_digest=value.manifest_digest,
        published_at=value.published_at,
        academic_work_registration_revision=value.academic_work_registration_revision,
        supersedes_publication_id=value.supersedes_publication_id,
    )


def publication_record_to_dict(value: PublicationRecord) -> dict[str, object]:
    """Convert a validated publication to its exact JSON-native shape."""
    if not isinstance(value, PublicationRecord):
        raise PublicationRecordValidationError(
            "publication must be a PublicationRecord."
        )
    publication = validate_publication_record(value)
    return {
        "schema_version": publication.schema_version,
        "record_type": publication.record_type,
        "publication_id": publication.publication_id,
        "work": module_work_ref_to_dict(publication.work),
        "source_record": (
            module_record_ref_to_dict(publication.source_record)
            if publication.source_record is not None
            else None
        ),
        "publication_kind": publication.publication_kind,
        "capabilities": list(publication.capabilities),
        "record_set_id": publication.record_set_id,
        "record_set_revision": publication.record_set_revision,
        "manifest_contract_version": publication.manifest_contract_version,
        "manifest_path": publication.manifest_path,
        "manifest_digest_algorithm": publication.manifest_digest_algorithm,
        "manifest_digest": publication.manifest_digest,
        "published_at": publication.published_at.isoformat(),
        "academic_work_registration_revision": (
            publication.academic_work_registration_revision
        ),
        "supersedes_publication_id": publication.supersedes_publication_id,
    }


def publication_record_from_dict(data: object) -> PublicationRecord:
    """Parse one exact Publication Record mapping."""
    mapping = _exact_mapping(data, _PUBLICATION_KEYS, "publication record")
    capabilities = mapping["capabilities"]
    if not isinstance(capabilities, list):
        raise PublicationRecordValidationError("capabilities must be a list.")
    try:
        work = module_work_ref_from_dict(mapping["work"])
        source_data = mapping["source_record"]
        source = (
            module_record_ref_from_dict(source_data)
            if source_data is not None
            else None
        )
    except RoutingModelError as error:
        raise PublicationRecordValidationError(str(error)) from error
    registration_revision = mapping["academic_work_registration_revision"]
    if registration_revision is not None:
        registration_revision = _require_int(
            registration_revision, "academic_work_registration_revision"
        )
    supersedes = mapping["supersedes_publication_id"]
    if supersedes is not None:
        supersedes = _require_str(supersedes, "supersedes_publication_id")
    return PublicationRecord(
        schema_version=_require_str(mapping["schema_version"], "schema_version"),
        record_type=_require_str(mapping["record_type"], "record_type"),
        publication_id=_require_str(mapping["publication_id"], "publication_id"),
        work=work,
        source_record=source,
        publication_kind=cast(
            PublicationKind,
            _require_str(mapping["publication_kind"], "publication_kind"),
        ),
        capabilities=cast(tuple[PublicationCapability, ...], tuple(capabilities)),
        record_set_id=_require_str(mapping["record_set_id"], "record_set_id"),
        record_set_revision=_require_int(
            mapping["record_set_revision"], "record_set_revision"
        ),
        manifest_contract_version=_require_str(
            mapping["manifest_contract_version"], "manifest_contract_version"
        ),
        manifest_path=_require_str(mapping["manifest_path"], "manifest_path"),
        manifest_digest_algorithm=cast(
            ManifestDigestAlgorithm,
            _require_str(
                mapping["manifest_digest_algorithm"],
                "manifest_digest_algorithm",
            ),
        ),
        manifest_digest=_require_str(mapping["manifest_digest"], "manifest_digest"),
        published_at=_datetime_from_iso(mapping["published_at"], "published_at"),
        academic_work_registration_revision=registration_revision,
        supersedes_publication_id=supersedes,
    )


def validate_publication_withdrawal(
    value: PublicationWithdrawal | Mapping[str, object],
) -> PublicationWithdrawal:
    """Fully validate and return a fresh Publication Withdrawal."""
    if not isinstance(value, PublicationWithdrawal):
        return publication_withdrawal_from_dict(value)
    return PublicationWithdrawal(
        schema_version=value.schema_version,
        record_type=value.record_type,
        publication_id=value.publication_id,
        withdrawn_at=value.withdrawn_at,
        reason=value.reason,
    )


def publication_withdrawal_to_dict(
    value: PublicationWithdrawal,
) -> dict[str, object]:
    """Convert a validated withdrawal to its exact JSON-native shape."""
    if not isinstance(value, PublicationWithdrawal):
        raise PublicationRecordValidationError(
            "withdrawal must be a PublicationWithdrawal."
        )
    withdrawal = validate_publication_withdrawal(value)
    return {
        "schema_version": withdrawal.schema_version,
        "record_type": withdrawal.record_type,
        "publication_id": withdrawal.publication_id,
        "withdrawn_at": withdrawal.withdrawn_at.isoformat(),
        "reason": withdrawal.reason,
    }


def publication_withdrawal_from_dict(data: object) -> PublicationWithdrawal:
    """Parse one exact Publication Withdrawal mapping."""
    mapping = _exact_mapping(data, _WITHDRAWAL_KEYS, "publication withdrawal")
    return PublicationWithdrawal(
        schema_version=_require_str(mapping["schema_version"], "schema_version"),
        record_type=_require_str(mapping["record_type"], "record_type"),
        publication_id=_require_str(mapping["publication_id"], "publication_id"),
        withdrawn_at=_datetime_from_iso(mapping["withdrawn_at"], "withdrawn_at"),
        reason=_require_str(mapping["reason"], "reason"),
    )


def validate_publication_supersession(
    previous: PublicationRecord, candidate: PublicationRecord
) -> PublicationRecord:
    """Validate one explicit append-preserving supersession transition."""
    if not isinstance(previous, PublicationRecord):
        raise PublicationRecordValidationError("previous publication is invalid.")
    if not isinstance(candidate, PublicationRecord):
        raise PublicationRecordValidationError("candidate publication is invalid.")
    old = validate_publication_record(previous)
    new = validate_publication_record(candidate)
    if new.supersedes_publication_id != old.publication_id:
        raise PublicationRecordValidationError(
            "candidate must supersede the previous publication ID."
        )
    if new.work != old.work:
        raise PublicationRecordValidationError("candidate work must match previous work.")
    if new.publication_kind != old.publication_kind:
        raise PublicationRecordValidationError(
            "candidate publication_kind must match the previous publication."
        )
    if new.record_set_id != old.record_set_id:
        raise PublicationRecordValidationError(
            "candidate record_set_id must match the previous publication."
        )
    if new.record_set_revision <= old.record_set_revision:
        raise PublicationRecordValidationError(
            "candidate record_set_revision must be greater than the previous revision."
        )
    if new.published_at < old.published_at:
        raise PublicationRecordValidationError(
            "candidate published_at must not be earlier than the previous publication."
        )
    return new


def validate_publication_record_series(
    records: Iterable[PublicationRecord],
) -> tuple[PublicationRecord, ...]:
    """Validate that records form one unbranched append-preserving chain."""
    if isinstance(records, (str, bytes)):
        raise PublicationRecordValidationError(
            "records must be an iterable of PublicationRecord values."
        )
    try:
        raw_records = tuple(records)
    except TypeError as error:
        raise PublicationRecordValidationError(
            "records must be an iterable of PublicationRecord values."
        ) from error
    validated: list[PublicationRecord] = []
    for index, item in enumerate(raw_records):
        if not isinstance(item, PublicationRecord):
            raise PublicationRecordValidationError(
                f"records[{index}] must be a PublicationRecord."
            )
        validated.append(validate_publication_record(item))
    if not validated:
        return ()
    identity = _series_identity(validated[0])
    if any(_series_identity(item) != identity for item in validated[1:]):
        raise PublicationRecordValidationError(
            "all records must share one publication-series identity."
        )
    by_id: dict[str, PublicationRecord] = {}
    revisions: set[int] = set()
    for item in validated:
        if item.publication_id in by_id:
            raise PublicationRecordValidationError("duplicate publication IDs are invalid.")
        if item.record_set_revision in revisions:
            raise PublicationRecordValidationError(
                "duplicate record-set revisions are invalid."
            )
        by_id[item.publication_id] = item
        revisions.add(item.record_set_revision)
    roots = [item for item in validated if item.supersedes_publication_id is None]
    if len(roots) != 1:
        raise PublicationRecordValidationError(
            "a nonempty publication series must have exactly one root."
        )
    successors: dict[str, PublicationRecord] = {}
    for item in validated:
        predecessor_id = item.supersedes_publication_id
        if predecessor_id is None:
            continue
        predecessor = by_id.get(predecessor_id)
        if predecessor is None:
            raise PublicationRecordValidationError(
                f"missing predecessor publication: {predecessor_id}."
            )
        if predecessor_id in successors:
            raise PublicationRecordValidationError(
                "branching publication successors are invalid."
            )
        validate_publication_supersession(predecessor, item)
        successors[predecessor_id] = item
    heads = [item for item in validated if item.publication_id not in successors]
    if len(heads) != 1:
        raise PublicationRecordValidationError(
            "a publication series must have exactly one unsuperseded head."
        )
    visited: set[str] = set()
    current = roots[0]
    while True:
        if current.publication_id in visited:
            raise PublicationRecordValidationError("publication series contains a cycle.")
        visited.add(current.publication_id)
        successor = successors.get(current.publication_id)
        if successor is None:
            break
        current = successor
    if len(visited) != len(validated):
        raise PublicationRecordValidationError(
            "publication series is disconnected or cyclic."
        )
    return tuple(sorted(validated, key=lambda item: (item.record_set_revision, item.publication_id)))


def validate_publication_withdrawal_relationship(
    publication: PublicationRecord, withdrawal: PublicationWithdrawal
) -> PublicationWithdrawal:
    """Validate an immutable withdrawal against its exact publication."""
    if not isinstance(publication, PublicationRecord):
        raise PublicationRecordValidationError("publication is invalid.")
    if not isinstance(withdrawal, PublicationWithdrawal):
        raise PublicationRecordValidationError("withdrawal is invalid.")
    record = validate_publication_record(publication)
    result = validate_publication_withdrawal(withdrawal)
    if result.publication_id != record.publication_id:
        raise PublicationRecordValidationError(
            "withdrawal publication_id must match the publication."
        )
    if result.withdrawn_at < record.published_at:
        raise PublicationRecordValidationError(
            "withdrawn_at must not be earlier than published_at."
        )
    return result


def _validate_publication_fields(value: PublicationRecord) -> None:
    if value.schema_version != PUBLICATION_RECORD_SCHEMA_VERSION:
        raise PublicationRecordValidationError('schema_version must be "1".')
    if value.record_type != PUBLICATION_RECORD_TYPE:
        raise PublicationRecordValidationError(
            'record_type must be "publication_record".'
        )
    _publication_id(value.publication_id, "publication_id")
    validated_work = _work(value.work)
    if value.source_record is not None:
        if not isinstance(value.source_record, ModuleRecordRef):
            raise PublicationRecordValidationError(
                "source_record must be a ModuleRecordRef or None."
            )
        try:
            source = validate_module_record_ref(value.source_record)
        except RoutingModelError as error:
            raise PublicationRecordValidationError(
                f"source_record is invalid: {error}"
            ) from error
        if source.module_id != validated_work.module_id:
            raise PublicationRecordValidationError(
                "source_record.module_id must match work.module_id."
            )
    if not is_publication_kind(value.publication_kind):
        raise PublicationRecordValidationError(
            "publication_kind must be one of: "
            + ", ".join(sorted(PUBLICATION_KINDS))
            + "."
        )
    capabilities = _capabilities(value.capabilities)
    object.__setattr__(value, "capabilities", capabilities)
    if value.publication_kind == "academic_result_set":
        forbidden = set(capabilities) & INTERVENTION_CAPABILITIES
        if forbidden:
            raise PublicationRecordValidationError(
                "academic-result publications cannot claim intervention capabilities."
            )
    else:
        forbidden = set(capabilities) & ACADEMIC_RESULT_CAPABILITIES
        if forbidden:
            raise PublicationRecordValidationError(
                "intervention publications cannot claim academic capabilities."
            )
    record_set_id = _identifier(value.record_set_id, "record_set_id")
    if record_set_id != record_set_id.lower():
        raise PublicationRecordValidationError("record_set_id must be lowercase.")
    _positive_int(value.record_set_revision, "record_set_revision")
    _identifier(value.manifest_contract_version, "manifest_contract_version")
    validate_publication_manifest_path(validated_work, value.manifest_path)
    if value.manifest_digest_algorithm != "sha256":
        raise PublicationRecordValidationError(
            'manifest_digest_algorithm must be "sha256".'
        )
    if not isinstance(value.manifest_digest, str) or not _MANIFEST_DIGEST.fullmatch(
        value.manifest_digest
    ):
        raise PublicationRecordValidationError(
            "manifest_digest must be exactly 64 lowercase hexadecimal characters."
        )
    _aware_datetime(value.published_at, "published_at")
    if value.publication_kind == "academic_result_set":
        _positive_int(
            value.academic_work_registration_revision,
            "academic_work_registration_revision",
        )
    elif value.academic_work_registration_revision is not None:
        raise PublicationRecordValidationError(
            "intervention publications must not reference an Academic Work Registration."
        )
    if value.supersedes_publication_id is not None:
        _publication_id(value.supersedes_publication_id, "supersedes_publication_id")
        if value.supersedes_publication_id == value.publication_id:
            raise PublicationRecordValidationError(
                "a publication must not supersede itself."
            )


def _validate_withdrawal_fields(value: PublicationWithdrawal) -> None:
    if value.schema_version != PUBLICATION_WITHDRAWAL_SCHEMA_VERSION:
        raise PublicationRecordValidationError('schema_version must be "1".')
    if value.record_type != PUBLICATION_WITHDRAWAL_RECORD_TYPE:
        raise PublicationRecordValidationError(
            'record_type must be "publication_withdrawal".'
        )
    _publication_id(value.publication_id, "publication_id")
    _aware_datetime(value.withdrawn_at, "withdrawn_at")
    if not isinstance(value.reason, str):
        raise PublicationRecordValidationError("reason must be a string.")
    if not value.reason.strip():
        raise PublicationRecordValidationError("reason must not be blank.")
    if value.reason != value.reason.strip():
        raise PublicationRecordValidationError(
            "reason must not contain leading or trailing whitespace."
        )
    if any(
        unicodedata.category(character) in {"Cc", "Zl", "Zp"}
        for character in value.reason
    ):
        raise PublicationRecordValidationError(
            "reason must be single-line and free of control characters."
        )


def _work(value: object) -> ModuleWorkRef:
    if not isinstance(value, ModuleWorkRef):
        raise PublicationRecordValidationError("work must be a ModuleWorkRef.")
    try:
        return validate_module_work_ref(value)
    except RoutingModelError as error:
        raise PublicationRecordValidationError(f"work is invalid: {error}") from error


def _capabilities(value: object) -> tuple[PublicationCapability, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        raise PublicationRecordValidationError(
            "capabilities must be an iterable of supported capability strings."
        )
    try:
        items = tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise PublicationRecordValidationError(
            "capabilities must be an iterable of supported capability strings."
        ) from error
    for index, item in enumerate(items):
        if not is_publication_capability(item):
            raise PublicationRecordValidationError(
                f"capabilities[{index}] is not a supported publication capability."
            )
    if len(set(items)) != len(items):
        raise PublicationRecordValidationError("capabilities must not contain duplicates.")
    return cast(tuple[PublicationCapability, ...], tuple(sorted(items)))


def _publication_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _PUBLICATION_ID.fullmatch(value):
        raise PublicationRecordValidationError(
            f"{field_name} must use the format pub_<32 lowercase hexadecimal characters>."
        )
    return value


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PublicationRecordValidationError(f"{field_name} must be a string.")
    try:
        return validate_identifier(value, field_name)
    except IdentifierValidationError as error:
        raise PublicationRecordValidationError(str(error)) from error


def _positive_int(value: object, field_name: str) -> int:
    integer = _require_int(value, field_name)
    if integer <= 0:
        raise PublicationRecordValidationError(
            f"{field_name} must be greater than zero."
        )
    return integer


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PublicationRecordValidationError(f"{field_name} must be a string.")
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PublicationRecordValidationError(f"{field_name} must be an integer.")
    return value


def _aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise PublicationRecordValidationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise PublicationRecordValidationError(
            f"{field_name} must be timezone-aware."
        )
    return value


def _datetime_from_iso(value: object, field_name: str) -> datetime:
    text = _require_str(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise PublicationRecordValidationError(
            f"{field_name} must be a valid ISO datetime string."
        ) from error
    return _aware_datetime(parsed, field_name)


def _exact_mapping(
    data: object, expected_keys: frozenset[str], description: str
) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise PublicationRecordValidationError(f"{description} must be an object.")
    if any(not isinstance(key, str) for key in data):
        raise PublicationRecordValidationError(f"{description} keys must be strings.")
    mapping = cast(Mapping[str, object], data)
    keys = set(mapping)
    missing = sorted(expected_keys - keys)
    if missing:
        raise PublicationRecordValidationError(
            f"{description} is missing required key(s): {', '.join(missing)}."
        )
    unknown = sorted(keys - expected_keys)
    if unknown:
        raise PublicationRecordValidationError(
            f"{description} contains unknown key(s): {', '.join(unknown)}."
        )
    return mapping


def _series_identity(
    publication: PublicationRecord,
) -> tuple[ModuleWorkRef, PublicationKind, str]:
    return (
        publication.work,
        publication.publication_kind,
        publication.record_set_id,
    )
