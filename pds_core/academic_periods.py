"""Validated in-memory academic-period models and dictionary conversion."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal, TypeAlias, cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.school_years import SchoolYearValidationError, validate_school_year

ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION: Final[str] = "1"
ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE: Final[str] = "academic_period_calendar"

AcademicPeriodType: TypeAlias = Literal[
    "marking_period",
    "semester",
    "quarter",
    "trimester",
    "progress_window",
    "custom",
]
AcademicPeriodLifecycle: TypeAlias = Literal[
    "planned",
    "active",
    "closed",
    "cancelled",
]

ACADEMIC_PERIOD_TYPES: Final[frozenset[str]] = frozenset(
    {
        "marking_period",
        "semester",
        "quarter",
        "trimester",
        "progress_window",
        "custom",
    }
)
ACADEMIC_PERIOD_LIFECYCLES: Final[frozenset[str]] = frozenset(
    {"planned", "active", "closed", "cancelled"}
)

_REF_KEYS: Final[frozenset[str]] = frozenset({"school_year", "period_id"})
_PERIOD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "period_id",
        "period_type",
        "label",
        "start_date",
        "end_date",
        "parent_period_id",
        "sequence",
        "lifecycle",
    }
)
_CALENDAR_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "record_type",
        "school_year",
        "calendar_revision",
        "created_at",
        "updated_at",
        "periods",
    }
)


class AcademicPeriodError(ValueError):
    """Base exception for academic-period model and conversion failures."""


class AcademicPeriodValidationError(AcademicPeriodError):
    """Raised when an academic-period value or calendar is invalid."""


def is_academic_period_type(value: object) -> bool:
    """Return whether *value* is an exact shared academic-period type."""
    return isinstance(value, str) and value in ACADEMIC_PERIOD_TYPES


def is_academic_period_lifecycle(value: object) -> bool:
    """Return whether *value* is an exact shared academic-period lifecycle."""
    return isinstance(value, str) and value in ACADEMIC_PERIOD_LIFECYCLES


@dataclass(frozen=True, slots=True)
class AcademicPeriodRef:
    """A school-year-qualified reference to one academic period."""

    school_year: str
    period_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "school_year", _school_year(self.school_year))
        object.__setattr__(self, "period_id", _identifier(self.period_id, "period_id"))


@dataclass(frozen=True, slots=True)
class AcademicPeriod:
    """One calendar-scoped academic period with inclusive date boundaries."""

    period_id: str
    period_type: AcademicPeriodType
    label: str
    start_date: date
    end_date: date
    parent_period_id: str | None
    sequence: int
    lifecycle: AcademicPeriodLifecycle

    def __post_init__(self) -> None:
        object.__setattr__(self, "period_id", _identifier(self.period_id, "period_id"))
        object.__setattr__(self, "period_type", _period_type(self.period_type))
        object.__setattr__(self, "label", _label(self.label))
        object.__setattr__(self, "start_date", _calendar_date(self.start_date, "start_date"))
        object.__setattr__(self, "end_date", _calendar_date(self.end_date, "end_date"))
        if self.start_date > self.end_date:
            raise AcademicPeriodValidationError(
                f"period {self.period_id!r}: start_date must not be later than end_date."
            )
        if self.parent_period_id is not None:
            object.__setattr__(
                self,
                "parent_period_id",
                _identifier(self.parent_period_id, "parent_period_id"),
            )
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "sequence"))
        object.__setattr__(self, "lifecycle", _lifecycle(self.lifecycle))


@dataclass(frozen=True, slots=True)
class AcademicPeriodCalendar:
    """One immutable, validated revision of a school-year period calendar."""

    schema_version: str
    record_type: str
    school_year: str
    calendar_revision: int
    created_at: datetime
    updated_at: datetime
    periods: tuple[AcademicPeriod, ...]

    def __post_init__(self) -> None:
        if self.schema_version != ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION:
            raise AcademicPeriodValidationError('schema_version must be "1".')
        if self.record_type != ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE:
            raise AcademicPeriodValidationError(
                'record_type must be "academic_period_calendar".'
            )
        object.__setattr__(self, "school_year", _school_year(self.school_year))
        object.__setattr__(
            self,
            "calendar_revision",
            _positive_int(self.calendar_revision, "calendar_revision"),
        )
        object.__setattr__(self, "created_at", _aware_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _aware_datetime(self.updated_at, "updated_at"))
        if self.updated_at < self.created_at:
            raise AcademicPeriodValidationError(
                "updated_at must not be earlier than created_at."
            )
        periods = validate_academic_period_hierarchy(
            self.school_year,
            self.periods,
        )
        object.__setattr__(self, "periods", periods)


def validate_academic_period_ref(
    value: AcademicPeriodRef | Mapping[str, object],
) -> AcademicPeriodRef:
    """Validate and return a fresh academic-period reference."""
    if isinstance(value, AcademicPeriodRef):
        return AcademicPeriodRef(value.school_year, value.period_id)
    return academic_period_ref_from_dict(value)


def academic_period_ref_to_dict(value: AcademicPeriodRef) -> dict[str, object]:
    """Convert a validated reference to its exact JSON-shaped mapping."""
    if not isinstance(value, AcademicPeriodRef):
        raise AcademicPeriodValidationError("academic period reference is invalid.")
    validated = validate_academic_period_ref(value)
    return {"school_year": validated.school_year, "period_id": validated.period_id}


def academic_period_ref_from_dict(data: object) -> AcademicPeriodRef:
    """Parse an exact academic-period reference mapping."""
    mapping = _exact_mapping(data, _REF_KEYS, "academic period reference")
    return AcademicPeriodRef(
        school_year=_require_str(mapping["school_year"], "school_year"),
        period_id=_require_str(mapping["period_id"], "period_id"),
    )


def validate_academic_period(
    value: AcademicPeriod | Mapping[str, object],
) -> AcademicPeriod:
    """Validate and return a fresh academic-period value."""
    if isinstance(value, AcademicPeriod):
        return AcademicPeriod(
            period_id=value.period_id,
            period_type=value.period_type,
            label=value.label,
            start_date=value.start_date,
            end_date=value.end_date,
            parent_period_id=value.parent_period_id,
            sequence=value.sequence,
            lifecycle=value.lifecycle,
        )
    return academic_period_from_dict(value)


def academic_period_to_dict(value: AcademicPeriod) -> dict[str, object]:
    """Convert a validated period to its exact JSON-shaped mapping."""
    if not isinstance(value, AcademicPeriod):
        raise AcademicPeriodValidationError("academic period is invalid.")
    period = validate_academic_period(value)
    return {
        "period_id": period.period_id,
        "period_type": period.period_type,
        "label": period.label,
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "parent_period_id": period.parent_period_id,
        "sequence": period.sequence,
        "lifecycle": period.lifecycle,
    }


def academic_period_from_dict(data: object) -> AcademicPeriod:
    """Parse an exact academic-period mapping."""
    mapping = _exact_mapping(data, _PERIOD_KEYS, "academic period")
    parent_value = mapping["parent_period_id"]
    if parent_value is not None and not isinstance(parent_value, str):
        raise AcademicPeriodValidationError(
            "parent_period_id must be a string or null."
        )
    return AcademicPeriod(
        period_id=_require_str(mapping["period_id"], "period_id"),
        period_type=cast(
            AcademicPeriodType, _require_str(mapping["period_type"], "period_type")
        ),
        label=_require_str(mapping["label"], "label"),
        start_date=_date_from_iso(mapping["start_date"], "start_date"),
        end_date=_date_from_iso(mapping["end_date"], "end_date"),
        parent_period_id=parent_value,
        sequence=_require_int(mapping["sequence"], "sequence"),
        lifecycle=cast(
            AcademicPeriodLifecycle,
            _require_str(mapping["lifecycle"], "lifecycle"),
        ),
    )


def validate_academic_period_hierarchy(
    school_year: str,
    periods: Iterable[AcademicPeriod],
) -> tuple[AcademicPeriod, ...]:
    """Validate a complete same-school-year hierarchy and return canonical order."""
    validated_school_year = _school_year(school_year)

    try:
        period_iterator = iter(periods)
    except TypeError as error:
        raise AcademicPeriodValidationError(
            "periods must be an iterable of AcademicPeriod values."
        ) from error

    collected: list[AcademicPeriod] = []
    for index, value in enumerate(period_iterator):
        if not isinstance(value, AcademicPeriod):
            raise AcademicPeriodValidationError(
                f"periods[{index}] must be an AcademicPeriod."
            )
        collected.append(validate_academic_period(value))

    by_id: dict[str, AcademicPeriod] = {}
    for period in collected:
        if period.period_id in by_id:
            raise AcademicPeriodValidationError(
                f"duplicate period_id {period.period_id!r}."
            )
        by_id[period.period_id] = period

    start_year_text, end_year_text = validated_school_year.split("-", maxsplit=1)
    allowed_years = {int(start_year_text), int(end_year_text)}
    for period in collected:
        if period.start_date.year not in allowed_years:
            raise AcademicPeriodValidationError(
                f"period {period.period_id!r}: start_date is outside school_year "
                f"{validated_school_year!r}."
            )
        if period.end_date.year not in allowed_years:
            raise AcademicPeriodValidationError(
                f"period {period.period_id!r}: end_date is outside school_year "
                f"{validated_school_year!r}."
            )
        parent_id = period.parent_period_id
        if parent_id == period.period_id:
            raise AcademicPeriodValidationError(
                f"period {period.period_id!r} must not be its own parent."
            )
        if parent_id is not None and parent_id not in by_id:
            raise AcademicPeriodValidationError(
                f"period {period.period_id!r} has missing parent {parent_id!r}."
            )

    _validate_no_cycles(by_id)

    sibling_sequences: dict[str | None, dict[int, str]] = {}
    for period in collected:
        parent_id = period.parent_period_id
        if parent_id is not None:
            parent = by_id[parent_id]
            if period.start_date < parent.start_date or period.end_date > parent.end_date:
                raise AcademicPeriodValidationError(
                    f"period {period.period_id!r} dates must be contained by parent "
                    f"{parent_id!r}."
                )
        sequences = sibling_sequences.setdefault(parent_id, {})
        prior_id = sequences.get(period.sequence)
        if prior_id is not None:
            parent_description = "root" if parent_id is None else f"parent {parent_id!r}"
            raise AcademicPeriodValidationError(
                f"duplicate sibling sequence {period.sequence} for periods "
                f"{prior_id!r} and {period.period_id!r} under {parent_description}."
            )
        sequences[period.sequence] = period.period_id

    return tuple(sorted(collected, key=lambda period: period.period_id))


def validate_academic_period_calendar(
    value: AcademicPeriodCalendar | Mapping[str, object],
) -> AcademicPeriodCalendar:
    """Fully validate and return a fresh academic-period calendar revision."""
    if isinstance(value, AcademicPeriodCalendar):
        return AcademicPeriodCalendar(
            schema_version=value.schema_version,
            record_type=value.record_type,
            school_year=value.school_year,
            calendar_revision=value.calendar_revision,
            created_at=value.created_at,
            updated_at=value.updated_at,
            periods=value.periods,
        )
    return academic_period_calendar_from_dict(value)


def academic_period_calendar_to_dict(
    value: AcademicPeriodCalendar,
) -> dict[str, object]:
    """Convert a validated calendar to its exact JSON-shaped mapping."""
    if not isinstance(value, AcademicPeriodCalendar):
        raise AcademicPeriodValidationError("academic period calendar is invalid.")
    calendar = validate_academic_period_calendar(value)
    return {
        "schema_version": calendar.schema_version,
        "record_type": calendar.record_type,
        "school_year": calendar.school_year,
        "calendar_revision": calendar.calendar_revision,
        "created_at": calendar.created_at.isoformat(),
        "updated_at": calendar.updated_at.isoformat(),
        "periods": [academic_period_to_dict(period) for period in calendar.periods],
    }


def academic_period_calendar_from_dict(data: object) -> AcademicPeriodCalendar:
    """Parse an exact academic-period calendar mapping.

    Duplicate JSON object keys cannot be detected here once a normal JSON parser
    has discarded them; that check belongs to the future persistence reader.
    """
    mapping = _exact_mapping(data, _CALENDAR_KEYS, "academic period calendar")
    periods_value = mapping["periods"]
    if not isinstance(periods_value, list):
        raise AcademicPeriodValidationError("periods must be a list.")
    periods = tuple(
        academic_period_from_dict(period_data) for period_data in periods_value
    )
    return AcademicPeriodCalendar(
        schema_version=_require_str(mapping["schema_version"], "schema_version"),
        record_type=_require_str(mapping["record_type"], "record_type"),
        school_year=_require_str(mapping["school_year"], "school_year"),
        calendar_revision=_require_int(
            mapping["calendar_revision"], "calendar_revision"
        ),
        created_at=_datetime_from_iso(mapping["created_at"], "created_at"),
        updated_at=_datetime_from_iso(mapping["updated_at"], "updated_at"),
        periods=periods,
    )


def validate_academic_period_calendar_transition(
    previous: AcademicPeriodCalendar,
    candidate: AcademicPeriodCalendar,
) -> AcademicPeriodCalendar:
    """Validate a pure transition between two immutable calendar revisions."""
    if not isinstance(previous, AcademicPeriodCalendar):
        raise AcademicPeriodValidationError("previous calendar is invalid.")
    if not isinstance(candidate, AcademicPeriodCalendar):
        raise AcademicPeriodValidationError("candidate calendar is invalid.")
    previous_validated = validate_academic_period_calendar(previous)
    candidate_validated = validate_academic_period_calendar(candidate)

    if candidate_validated.school_year != previous_validated.school_year:
        raise AcademicPeriodValidationError(
            "candidate school_year must match the previous calendar."
        )
    if candidate_validated.calendar_revision <= previous_validated.calendar_revision:
        raise AcademicPeriodValidationError(
            "candidate calendar_revision must be greater than the previous revision."
        )
    if candidate_validated.created_at != previous_validated.created_at:
        raise AcademicPeriodValidationError(
            "candidate created_at must match the previous calendar."
        )
    if candidate_validated.updated_at < previous_validated.updated_at:
        raise AcademicPeriodValidationError(
            "candidate updated_at must not be earlier than the previous revision."
        )

    previous_by_id = {period.period_id: period for period in previous_validated.periods}
    candidate_by_id = {
        period.period_id: period for period in candidate_validated.periods
    }
    missing_ids = sorted(previous_by_id.keys() - candidate_by_id.keys())
    if missing_ids:
        raise AcademicPeriodValidationError(
            "candidate calendar removes existing period_id(s): "
            + ", ".join(missing_ids)
            + "."
        )
    for period_id, previous_period in previous_by_id.items():
        candidate_period = candidate_by_id[period_id]
        if candidate_period.period_type != previous_period.period_type:
            raise AcademicPeriodValidationError(
                f"period {period_id!r} must preserve period_type "
                f"{previous_period.period_type!r}."
            )
    return candidate_validated


def _school_year(value: object) -> str:
    try:
        return validate_school_year(value)
    except SchoolYearValidationError as error:
        raise AcademicPeriodValidationError(str(error)) from error


def _identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(cast(str, value), field_name)
    except IdentifierValidationError as error:
        raise AcademicPeriodValidationError(str(error)) from error


def _period_type(value: object) -> AcademicPeriodType:
    if not is_academic_period_type(value):
        raise AcademicPeriodValidationError(
            "period_type must be one of: " + ", ".join(sorted(ACADEMIC_PERIOD_TYPES)) + "."
        )
    return cast(AcademicPeriodType, value)


def _lifecycle(value: object) -> AcademicPeriodLifecycle:
    if not is_academic_period_lifecycle(value):
        raise AcademicPeriodValidationError(
            "lifecycle must be one of: "
            + ", ".join(sorted(ACADEMIC_PERIOD_LIFECYCLES))
            + "."
        )
    return cast(AcademicPeriodLifecycle, value)


def _label(value: object) -> str:
    if not isinstance(value, str):
        raise AcademicPeriodValidationError("label must be a string.")
    if not value.strip():
        raise AcademicPeriodValidationError("label must not be blank.")
    if value != value.strip():
        raise AcademicPeriodValidationError(
            "label must not contain leading or trailing whitespace."
        )
    if any(unicodedata.category(character) in {"Cc", "Zl", "Zp"} for character in value):
        raise AcademicPeriodValidationError(
            "label must be single-line and free of control characters."
        )
    return value


def _calendar_date(value: object, field_name: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise AcademicPeriodValidationError(f"{field_name} must be a date.")
    return value


def _positive_int(value: object, field_name: str) -> int:
    integer = _require_int(value, field_name)
    if integer <= 0:
        raise AcademicPeriodValidationError(f"{field_name} must be greater than zero.")
    return integer


def _aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AcademicPeriodValidationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AcademicPeriodValidationError(f"{field_name} must be timezone-aware.")
    return value


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise AcademicPeriodValidationError(f"{field_name} must be a string.")
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AcademicPeriodValidationError(f"{field_name} must be an integer.")
    return value


def _date_from_iso(value: object, field_name: str) -> date:
    text = _require_str(value, field_name)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise AcademicPeriodValidationError(
            f"{field_name} must be a valid ISO date string."
        ) from error
    # date.fromisoformat is strict today; this guards the serialized contract too.
    if parsed.isoformat() != text:
        raise AcademicPeriodValidationError(
            f"{field_name} must use YYYY-MM-DD format."
        )
    return parsed


def _datetime_from_iso(value: object, field_name: str) -> datetime:
    text = _require_str(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise AcademicPeriodValidationError(
            f"{field_name} must be a valid ISO datetime string."
        ) from error
    return _aware_datetime(parsed, field_name)


def _exact_mapping(
    data: object,
    required_keys: frozenset[str],
    description: str,
) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise AcademicPeriodValidationError(f"{description} must be an object.")
    if any(not isinstance(key, str) for key in data):
        raise AcademicPeriodValidationError(f"{description} keys must be strings.")
    mapping = cast(Mapping[str, object], data)
    keys = set(mapping)
    missing = sorted(required_keys - keys)
    if missing:
        raise AcademicPeriodValidationError(
            f"{description} is missing required key(s): {', '.join(missing)}."
        )
    unknown = sorted(keys - required_keys)
    if unknown:
        raise AcademicPeriodValidationError(
            f"{description} contains unknown key(s): {', '.join(unknown)}."
        )
    return mapping


def _validate_no_cycles(by_id: Mapping[str, AcademicPeriod]) -> None:
    complete: set[str] = set()
    for start_id in sorted(by_id):
        if start_id in complete:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current_id: str | None = start_id
        while current_id is not None and current_id not in complete:
            if current_id in positions:
                cycle = path[positions[current_id] :] + [current_id]
                raise AcademicPeriodValidationError(
                    "academic period hierarchy contains a cycle: "
                    + " -> ".join(cycle)
                    + "."
                )
            positions[current_id] = len(path)
            path.append(current_id)
            current_id = by_id[current_id].parent_period_id
        complete.update(path)
