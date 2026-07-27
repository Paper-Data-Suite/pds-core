"""Immutable Academic Work Registration models and conversion."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
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

ACADEMIC_WORK_REGISTRATION_SCHEMA_VERSION: Final[str] = "1"
ACADEMIC_WORK_REGISTRATION_RECORD_TYPE: Final[str] = "academic_work_registration"

AcademicWorkIntent: TypeAlias = Literal[
    "formative", "summative", "diagnostic", "practice", "feedback_only", "reporting_only"
]
AcademicWorkRegistrationLifecycle: TypeAlias = Literal[
    "planned", "active", "closed", "cancelled"
]

ACADEMIC_WORK_INTENTS: Final[frozenset[str]] = frozenset(
    {"formative", "summative", "diagnostic", "practice", "feedback_only", "reporting_only"}
)
ACADEMIC_WORK_REGISTRATION_LIFECYCLES: Final[frozenset[str]] = frozenset(
    {"planned", "active", "closed", "cancelled"}
)

_REGISTRATION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version", "record_type", "work", "registration_revision",
        "producer_contract_version", "title", "work_kind", "academic_intent",
        "lifecycle", "created_at", "updated_at", "source_records",
    }
)


class AcademicWorkRegistrationError(ValueError):
    """Base error for Academic Work Registration model failures."""


class AcademicWorkRegistrationValidationError(AcademicWorkRegistrationError):
    """Raised when a registration or transition is invalid."""


def is_academic_work_intent(value: object) -> bool:
    """Return whether *value* is an exact shared academic intent."""
    return isinstance(value, str) and value in ACADEMIC_WORK_INTENTS


def is_academic_work_registration_lifecycle(value: object) -> bool:
    """Return whether *value* is an exact registration lifecycle."""
    return isinstance(value, str) and value in ACADEMIC_WORK_REGISTRATION_LIFECYCLES


@dataclass(frozen=True, slots=True)
class AcademicWorkRegistration:
    """One immutable revision declaring academic intent for module-owned work."""

    schema_version: str
    record_type: str
    work: ModuleWorkRef
    registration_revision: int
    producer_contract_version: str
    title: str
    work_kind: str
    academic_intent: AcademicWorkIntent
    lifecycle: AcademicWorkRegistrationLifecycle
    created_at: datetime
    updated_at: datetime
    source_records: tuple[ModuleRecordRef, ...]

    def __post_init__(self) -> None:
        if self.schema_version != ACADEMIC_WORK_REGISTRATION_SCHEMA_VERSION:
            raise AcademicWorkRegistrationValidationError('schema_version must be "1".')
        if self.record_type != ACADEMIC_WORK_REGISTRATION_RECORD_TYPE:
            raise AcademicWorkRegistrationValidationError(
                'record_type must be "academic_work_registration".'
            )
        object.__setattr__(self, "work", _work_ref(self.work))
        object.__setattr__(
            self, "registration_revision",
            _positive_int(self.registration_revision, "registration_revision"),
        )
        object.__setattr__(
            self, "producer_contract_version",
            _identifier(self.producer_contract_version, "producer_contract_version"),
        )
        object.__setattr__(self, "title", _title(self.title))
        work_kind = _identifier(self.work_kind, "work_kind")
        if work_kind != work_kind.lower():
            raise AcademicWorkRegistrationValidationError("work_kind must be lowercase.")
        object.__setattr__(self, "work_kind", work_kind)
        if not is_academic_work_intent(self.academic_intent):
            raise AcademicWorkRegistrationValidationError(
                "academic_intent must be one of: " + ", ".join(sorted(ACADEMIC_WORK_INTENTS)) + "."
            )
        if not is_academic_work_registration_lifecycle(self.lifecycle):
            raise AcademicWorkRegistrationValidationError(
                "lifecycle must be one of: "
                + ", ".join(sorted(ACADEMIC_WORK_REGISTRATION_LIFECYCLES)) + "."
            )
        object.__setattr__(self, "created_at", _aware_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _aware_datetime(self.updated_at, "updated_at"))
        if self.updated_at < self.created_at:
            raise AcademicWorkRegistrationValidationError(
                "updated_at must not be earlier than created_at."
            )
        object.__setattr__(self, "source_records", _source_records(self.source_records, self.work))


def validate_academic_work_registration(
    value: AcademicWorkRegistration | Mapping[str, object],
) -> AcademicWorkRegistration:
    """Fully validate and return a fresh registration value."""
    if isinstance(value, AcademicWorkRegistration):
        return AcademicWorkRegistration(
            schema_version=value.schema_version,
            record_type=value.record_type,
            work=value.work,
            registration_revision=value.registration_revision,
            producer_contract_version=value.producer_contract_version,
            title=value.title,
            work_kind=value.work_kind,
            academic_intent=value.academic_intent,
            lifecycle=value.lifecycle,
            created_at=value.created_at,
            updated_at=value.updated_at,
            source_records=value.source_records,
        )
    return academic_work_registration_from_dict(value)


def academic_work_registration_to_dict(
    value: AcademicWorkRegistration,
) -> dict[str, object]:
    """Convert a validated registration to its exact JSON-native shape."""
    if not isinstance(value, AcademicWorkRegistration):
        raise AcademicWorkRegistrationValidationError(
            "registration must be an AcademicWorkRegistration."
        )
    registration = validate_academic_work_registration(value)
    return {
        "schema_version": registration.schema_version,
        "record_type": registration.record_type,
        "work": module_work_ref_to_dict(registration.work),
        "registration_revision": registration.registration_revision,
        "producer_contract_version": registration.producer_contract_version,
        "title": registration.title,
        "work_kind": registration.work_kind,
        "academic_intent": registration.academic_intent,
        "lifecycle": registration.lifecycle,
        "created_at": registration.created_at.isoformat(),
        "updated_at": registration.updated_at.isoformat(),
        "source_records": [module_record_ref_to_dict(item) for item in registration.source_records],
    }


def academic_work_registration_from_dict(data: object) -> AcademicWorkRegistration:
    """Parse an exact registration mapping."""
    mapping = _exact_mapping(data, _REGISTRATION_KEYS, "academic work registration")
    records_data = mapping["source_records"]
    if not isinstance(records_data, list):
        raise AcademicWorkRegistrationValidationError("source_records must be a list.")
    try:
        work = module_work_ref_from_dict(mapping["work"])
        records = tuple(module_record_ref_from_dict(item) for item in records_data)
    except RoutingModelError as error:
        raise AcademicWorkRegistrationValidationError(str(error)) from error
    return AcademicWorkRegistration(
        schema_version=_require_str(mapping["schema_version"], "schema_version"),
        record_type=_require_str(mapping["record_type"], "record_type"),
        work=work,
        registration_revision=_require_int(mapping["registration_revision"], "registration_revision"),
        producer_contract_version=_require_str(
            mapping["producer_contract_version"], "producer_contract_version"
        ),
        title=_require_str(mapping["title"], "title"),
        work_kind=_require_str(mapping["work_kind"], "work_kind"),
        academic_intent=cast(AcademicWorkIntent, _require_str(mapping["academic_intent"], "academic_intent")),
        lifecycle=cast(
            AcademicWorkRegistrationLifecycle, _require_str(mapping["lifecycle"], "lifecycle")
        ),
        created_at=_datetime_from_iso(mapping["created_at"], "created_at"),
        updated_at=_datetime_from_iso(mapping["updated_at"], "updated_at"),
        source_records=records,
    )


def validate_academic_work_registration_transition(
    previous: AcademicWorkRegistration,
    candidate: AcademicWorkRegistration,
) -> AcademicWorkRegistration:
    """Validate a pure transition between immutable registration revisions."""
    if not isinstance(previous, AcademicWorkRegistration):
        raise AcademicWorkRegistrationValidationError("previous registration is invalid.")
    if not isinstance(candidate, AcademicWorkRegistration):
        raise AcademicWorkRegistrationValidationError("candidate registration is invalid.")
    old = validate_academic_work_registration(previous)
    new = validate_academic_work_registration(candidate)
    if new.work != old.work:
        raise AcademicWorkRegistrationValidationError(
            "candidate work must match the previous registration work."
        )
    if new.registration_revision <= old.registration_revision:
        raise AcademicWorkRegistrationValidationError(
            "candidate registration_revision must be greater than the previous revision."
        )
    if new.created_at != old.created_at:
        raise AcademicWorkRegistrationValidationError(
            "candidate created_at must match the previous registration."
        )
    if new.updated_at < old.updated_at:
        raise AcademicWorkRegistrationValidationError(
            "candidate updated_at must not be earlier than the previous revision."
        )
    return new


def _work_ref(value: object) -> ModuleWorkRef:
    if not isinstance(value, ModuleWorkRef):
        raise AcademicWorkRegistrationValidationError("work must be a ModuleWorkRef.")
    try:
        return validate_module_work_ref(value)
    except RoutingModelError as error:
        raise AcademicWorkRegistrationValidationError(f"work is invalid: {error}") from error


def _source_records(value: object, work: ModuleWorkRef) -> tuple[ModuleRecordRef, ...]:
    if isinstance(value, (str, bytes)):
        raise AcademicWorkRegistrationValidationError(
            "source_records must be an iterable of ModuleRecordRef values."
        )
    try:
        items: tuple[object, ...] = tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise AcademicWorkRegistrationValidationError(
            "source_records must be an iterable of ModuleRecordRef values."
        ) from error
    validated: list[ModuleRecordRef] = []
    for index, item in enumerate(items):
        if not isinstance(item, ModuleRecordRef):
            raise AcademicWorkRegistrationValidationError(
                f"source_records[{index}] must be a ModuleRecordRef."
            )
        try:
            record = validate_module_record_ref(item)
        except RoutingModelError as error:
            raise AcademicWorkRegistrationValidationError(
                f"source_records[{index}] is invalid: {error}"
            ) from error
        if record.module_id != work.module_id:
            raise AcademicWorkRegistrationValidationError(
                f"source_records[{index}].module_id must match work.module_id."
            )
        validated.append(record)
    if len(set(validated)) != len(validated):
        raise AcademicWorkRegistrationValidationError(
            "source_records must not contain duplicate exact references."
        )
    return tuple(sorted(validated, key=lambda item: (
        item.record_kind, item.record_id, item.contract_version is not None,
        item.contract_version or "",
    )))


def _identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(cast(str, value), field_name)
    except IdentifierValidationError as error:
        raise AcademicWorkRegistrationValidationError(str(error)) from error


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise AcademicWorkRegistrationValidationError("title must be a string.")
    if not value.strip():
        raise AcademicWorkRegistrationValidationError("title must not be blank.")
    if value != value.strip():
        raise AcademicWorkRegistrationValidationError(
            "title must not contain leading or trailing whitespace."
        )
    if any(unicodedata.category(character) in {"Cc", "Zl", "Zp"} for character in value):
        raise AcademicWorkRegistrationValidationError(
            "title must be single-line and free of control characters."
        )
    return value


def _aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AcademicWorkRegistrationValidationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AcademicWorkRegistrationValidationError(f"{field_name} must be timezone-aware.")
    return value


def _positive_int(value: object, field_name: str) -> int:
    integer = _require_int(value, field_name)
    if integer <= 0:
        raise AcademicWorkRegistrationValidationError(f"{field_name} must be greater than zero.")
    return integer


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise AcademicWorkRegistrationValidationError(f"{field_name} must be a string.")
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AcademicWorkRegistrationValidationError(f"{field_name} must be an integer.")
    return value


def _datetime_from_iso(value: object, field_name: str) -> datetime:
    text = _require_str(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise AcademicWorkRegistrationValidationError(
            f"{field_name} must be a valid ISO datetime string."
        ) from error
    return _aware_datetime(parsed, field_name)


def _exact_mapping(
    data: object, required_keys: frozenset[str], description: str,
) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise AcademicWorkRegistrationValidationError(f"{description} must be an object.")
    if any(not isinstance(key, str) for key in data):
        raise AcademicWorkRegistrationValidationError(f"{description} keys must be strings.")
    mapping = cast(Mapping[str, object], data)
    keys = set(mapping)
    missing = sorted(required_keys - keys)
    if missing:
        raise AcademicWorkRegistrationValidationError(
            f"{description} is missing required key(s): {', '.join(missing)}."
        )
    unknown = sorted(keys - required_keys)
    if unknown:
        raise AcademicWorkRegistrationValidationError(
            f"{description} contains unknown key(s): {', '.join(unknown)}."
        )
    return mapping
