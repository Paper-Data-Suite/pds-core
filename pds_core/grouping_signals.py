"""Typed models and canonical JSON for neutral grouping-signal snapshots."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal, NoReturn, TypeAlias, cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier

GROUPING_SIGNAL_CONTRACT_NAME: Final[str] = "grouping_signal_set_v1"
GROUPING_SIGNAL_SCHEMA_VERSION: Final[str] = "1"
GROUPING_SIGNAL_RECORD_TYPE: Final[str] = "grouping_signal_set"

GroupingSignalSourceKind: TypeAlias = Literal["teacher_authored", "module_generated"]
GROUPING_SIGNAL_SOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {"teacher_authored", "module_generated"}
)

_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "record_type",
        "signal_set_id",
        "class_id",
        "created_at",
        "source",
        "dimensions",
        "student_bands",
    }
)
_SOURCE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "kind",
        "module_id",
        "snapshot_id",
        "snapshot_digest_algorithm",
        "snapshot_digest",
    }
)
_DIMENSION_KEYS: Final[frozenset[str]] = frozenset({"dimension_id", "band_count"})
_STUDENT_BAND_KEYS: Final[frozenset[str]] = frozenset(
    {"student_id", "dimension_id", "band"}
)
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class GroupingSignalValidationError(ValueError):
    """Raised when a grouping-signal model or canonical wire value is invalid."""


class _DuplicateJsonKeyError(ValueError):
    pass


class _InvalidJsonConstantError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GroupingSignalSource:
    """Minimal provenance for one grouping-signal snapshot."""

    kind: GroupingSignalSourceKind
    module_id: str | None
    snapshot_id: str | None
    snapshot_digest_algorithm: str | None
    snapshot_digest: str | None

    def __post_init__(self) -> None:
        if not is_grouping_signal_source_kind(self.kind):
            raise GroupingSignalValidationError(
                "source.kind must be one of: "
                + ", ".join(sorted(GROUPING_SIGNAL_SOURCE_KINDS))
                + "."
            )
        if self.kind == "module_generated":
            module_id = _identifier(self.module_id, "source.module_id")
            if module_id != module_id.lower():
                raise GroupingSignalValidationError(
                    "source.module_id must be lowercase."
                )
            snapshot_id = _identifier(self.snapshot_id, "source.snapshot_id")
            algorithm = _digest_algorithm(
                self.snapshot_digest_algorithm, "source.snapshot_digest_algorithm"
            )
            digest = _sha256_digest(self.snapshot_digest, "source.snapshot_digest")
            object.__setattr__(self, "module_id", module_id)
            object.__setattr__(self, "snapshot_id", snapshot_id)
            object.__setattr__(self, "snapshot_digest_algorithm", algorithm)
            object.__setattr__(self, "snapshot_digest", digest)
            return

        if self.module_id is not None:
            raise GroupingSignalValidationError(
                "source.module_id must be null for teacher_authored signals."
            )
        provenance = (
            self.snapshot_id,
            self.snapshot_digest_algorithm,
            self.snapshot_digest,
        )
        populated = tuple(item is not None for item in provenance)
        if any(populated) and not all(populated):
            raise GroupingSignalValidationError(
                "teacher_authored source snapshot provenance must be all null or "
                "all populated."
            )
        if all(populated):
            snapshot_id = _identifier(self.snapshot_id, "source.snapshot_id")
            algorithm = _digest_algorithm(
                self.snapshot_digest_algorithm, "source.snapshot_digest_algorithm"
            )
            digest = _sha256_digest(self.snapshot_digest, "source.snapshot_digest")
            object.__setattr__(self, "snapshot_id", snapshot_id)
            object.__setattr__(self, "snapshot_digest_algorithm", algorithm)
            object.__setattr__(self, "snapshot_digest", digest)


@dataclass(frozen=True, slots=True)
class GroupingSignalDimension:
    """One ordinal grouping-signal dimension declaration."""

    dimension_id: str
    band_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dimension_id", _identifier(self.dimension_id, "dimension_id")
        )
        object.__setattr__(
            self, "band_count", _integer_at_least(self.band_count, "band_count", 2)
        )


@dataclass(frozen=True, slots=True)
class GroupingSignalStudentBand:
    """One student's contextual ordinal band in one declared dimension."""

    student_id: str
    dimension_id: str
    band: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "student_id", _identifier(self.student_id, "student_id")
        )
        object.__setattr__(
            self, "dimension_id", _identifier(self.dimension_id, "dimension_id")
        )
        object.__setattr__(self, "band", _integer_at_least(self.band, "band", 1))


@dataclass(frozen=True, slots=True)
class GroupingSignalSet:
    """One immutable contextual grouping-signal snapshot for one Core class."""

    schema_version: str
    record_type: str
    signal_set_id: str
    class_id: str
    created_at: datetime
    source: GroupingSignalSource
    dimensions: tuple[GroupingSignalDimension, ...]
    student_bands: tuple[GroupingSignalStudentBand, ...]

    def __post_init__(self) -> None:
        if self.schema_version != GROUPING_SIGNAL_SCHEMA_VERSION:
            raise GroupingSignalValidationError('schema_version must be "1".')
        if self.record_type != GROUPING_SIGNAL_RECORD_TYPE:
            raise GroupingSignalValidationError(
                'record_type must be "grouping_signal_set".'
            )
        object.__setattr__(
            self,
            "signal_set_id",
            _identifier(self.signal_set_id, "signal_set_id"),
        )
        object.__setattr__(self, "class_id", _identifier(self.class_id, "class_id"))
        object.__setattr__(
            self, "created_at", _aware_datetime_utc(self.created_at, "created_at")
        )
        object.__setattr__(self, "source", _source(self.source))

        dimensions = _dimensions(self.dimensions)
        dimension_by_id = {item.dimension_id: item for item in dimensions}
        student_bands = _student_bands(self.student_bands)
        for index, entry in enumerate(student_bands):
            dimension = dimension_by_id.get(entry.dimension_id)
            if dimension is None:
                raise GroupingSignalValidationError(
                    f"student_bands[{index}].dimension_id references an undeclared "
                    "dimension."
                )
            if entry.band > dimension.band_count:
                raise GroupingSignalValidationError(
                    f"student_bands[{index}].band must be between 1 and "
                    f"{dimension.band_count}."
                )

        represented = {item.dimension_id for item in student_bands}
        missing_dimensions = [
            item.dimension_id
            for item in dimensions
            if item.dimension_id not in represented
        ]
        if missing_dimensions:
            raise GroupingSignalValidationError(
                "Every declared dimension must have at least one student_bands "
                "entry; missing: "
                + ", ".join(missing_dimensions)
                + "."
            )

        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "student_bands", student_bands)


def is_grouping_signal_source_kind(value: object) -> bool:
    """Return whether *value* is an exact version-1 source kind."""
    return isinstance(value, str) and value in GROUPING_SIGNAL_SOURCE_KINDS


def validate_grouping_signal_set(
    value: GroupingSignalSet | Mapping[str, object],
) -> GroupingSignalSet:
    """Fully validate and return a fresh grouping-signal value."""
    if isinstance(value, GroupingSignalSet):
        return GroupingSignalSet(
            schema_version=value.schema_version,
            record_type=value.record_type,
            signal_set_id=value.signal_set_id,
            class_id=value.class_id,
            created_at=value.created_at,
            source=value.source,
            dimensions=value.dimensions,
            student_bands=value.student_bands,
        )
    return grouping_signal_set_from_dict(value)


def grouping_signal_set_to_dict(value: GroupingSignalSet) -> dict[str, object]:
    """Convert a validated signal set to its exact canonical JSON-native shape."""
    if not isinstance(value, GroupingSignalSet):
        raise GroupingSignalValidationError(
            "signal must be a GroupingSignalSet."
        )
    signal = validate_grouping_signal_set(value)
    return {
        "schema_version": signal.schema_version,
        "record_type": signal.record_type,
        "signal_set_id": signal.signal_set_id,
        "class_id": signal.class_id,
        "created_at": signal.created_at.isoformat(),
        "source": {
            "kind": signal.source.kind,
            "module_id": signal.source.module_id,
            "snapshot_id": signal.source.snapshot_id,
            "snapshot_digest_algorithm": signal.source.snapshot_digest_algorithm,
            "snapshot_digest": signal.source.snapshot_digest,
        },
        "dimensions": [
            {
                "dimension_id": item.dimension_id,
                "band_count": item.band_count,
            }
            for item in signal.dimensions
        ],
        "student_bands": [
            {
                "student_id": item.student_id,
                "dimension_id": item.dimension_id,
                "band": item.band,
            }
            for item in signal.student_bands
        ],
    }


def grouping_signal_set_from_dict(data: object) -> GroupingSignalSet:
    """Parse an exact canonical version-1 JSON-native mapping."""
    mapping = _exact_mapping(data, _TOP_LEVEL_KEYS, "grouping signal set")
    source_mapping = _exact_mapping(mapping["source"], _SOURCE_KEYS, "source")
    dimensions_data = _require_list(mapping["dimensions"], "dimensions")
    student_bands_data = _require_list(mapping["student_bands"], "student_bands")

    source = GroupingSignalSource(
        kind=cast(
            GroupingSignalSourceKind,
            _require_str(source_mapping["kind"], "source.kind"),
        ),
        module_id=_optional_str(source_mapping["module_id"], "source.module_id"),
        snapshot_id=_optional_str(
            source_mapping["snapshot_id"], "source.snapshot_id"
        ),
        snapshot_digest_algorithm=_optional_str(
            source_mapping["snapshot_digest_algorithm"],
            "source.snapshot_digest_algorithm",
        ),
        snapshot_digest=_optional_str(
            source_mapping["snapshot_digest"], "source.snapshot_digest"
        ),
    )

    dimensions: list[GroupingSignalDimension] = []
    for index, item in enumerate(dimensions_data):
        item_mapping = _exact_mapping(
            item, _DIMENSION_KEYS, f"dimensions[{index}]"
        )
        try:
            dimension = GroupingSignalDimension(
                dimension_id=_require_str(
                    item_mapping["dimension_id"],
                    f"dimensions[{index}].dimension_id",
                ),
                band_count=_require_int(
                    item_mapping["band_count"], f"dimensions[{index}].band_count"
                ),
            )
        except GroupingSignalValidationError as error:
            raise GroupingSignalValidationError(
                f"dimensions[{index}] is invalid: {error}"
            ) from error
        dimensions.append(dimension)
    _require_canonical_dimension_order(dimensions)

    student_bands: list[GroupingSignalStudentBand] = []
    for index, item in enumerate(student_bands_data):
        item_mapping = _exact_mapping(
            item, _STUDENT_BAND_KEYS, f"student_bands[{index}]"
        )
        try:
            entry = GroupingSignalStudentBand(
                student_id=_require_str(
                    item_mapping["student_id"], f"student_bands[{index}].student_id"
                ),
                dimension_id=_require_str(
                    item_mapping["dimension_id"],
                    f"student_bands[{index}].dimension_id",
                ),
                band=_require_int(
                    item_mapping["band"], f"student_bands[{index}].band"
                ),
            )
        except GroupingSignalValidationError as error:
            raise GroupingSignalValidationError(
                f"student_bands[{index}] is invalid: {error}"
            ) from error
        student_bands.append(entry)
    _require_canonical_student_band_order(student_bands)

    return GroupingSignalSet(
        schema_version=_require_str(mapping["schema_version"], "schema_version"),
        record_type=_require_str(mapping["record_type"], "record_type"),
        signal_set_id=_require_str(mapping["signal_set_id"], "signal_set_id"),
        class_id=_require_str(mapping["class_id"], "class_id"),
        created_at=_canonical_datetime_from_iso(mapping["created_at"], "created_at"),
        source=source,
        dimensions=tuple(dimensions),
        student_bands=tuple(student_bands),
    )


def grouping_signal_set_to_json(value: GroupingSignalSet) -> str:
    """Serialize a grouping signal to canonical version-1 JSON text."""
    return json.dumps(
        grouping_signal_set_to_dict(value),
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"


def grouping_signal_set_to_json_bytes(value: GroupingSignalSet) -> bytes:
    """Serialize a grouping signal to canonical UTF-8 JSON bytes."""
    return grouping_signal_set_to_json(value).encode("utf-8")


def grouping_signal_set_from_json(data: str | bytes) -> GroupingSignalSet:
    """Load and require exact canonical version-1 JSON text or UTF-8 bytes."""
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GroupingSignalValidationError(
                "grouping signal JSON bytes must be valid UTF-8."
            ) from error
    elif isinstance(data, str):
        text = data
    else:
        raise GroupingSignalValidationError(
            "grouping signal JSON must be a string or UTF-8 bytes."
        )

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_invalid_constant,
        )
    except (
        json.JSONDecodeError,
        _DuplicateJsonKeyError,
        _InvalidJsonConstantError,
    ) as error:
        raise GroupingSignalValidationError(
            f"grouping signal JSON is invalid: {error}"
        ) from error

    signal = grouping_signal_set_from_dict(decoded)
    if text != grouping_signal_set_to_json(signal):
        raise GroupingSignalValidationError(
            "grouping signal JSON is valid but not in canonical version-1 form."
        )
    return signal


def _source(value: object) -> GroupingSignalSource:
    if not isinstance(value, GroupingSignalSource):
        raise GroupingSignalValidationError(
            "source must be a GroupingSignalSource."
        )
    return GroupingSignalSource(
        kind=value.kind,
        module_id=value.module_id,
        snapshot_id=value.snapshot_id,
        snapshot_digest_algorithm=value.snapshot_digest_algorithm,
        snapshot_digest=value.snapshot_digest,
    )


def _dimensions(value: object) -> tuple[GroupingSignalDimension, ...]:
    items = _iterable_items(value, "dimensions", "GroupingSignalDimension")
    if not items:
        raise GroupingSignalValidationError("dimensions must not be empty.")
    validated: list[GroupingSignalDimension] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, GroupingSignalDimension):
            raise GroupingSignalValidationError(
                f"dimensions[{index}] must be a GroupingSignalDimension."
            )
        try:
            dimension = GroupingSignalDimension(
                dimension_id=item.dimension_id, band_count=item.band_count
            )
        except GroupingSignalValidationError as error:
            raise GroupingSignalValidationError(
                f"dimensions[{index}] is invalid: {error}"
            ) from error
        if dimension.dimension_id in seen:
            raise GroupingSignalValidationError(
                f"dimensions contains duplicate dimension_id "
                f"{dimension.dimension_id!r}."
            )
        seen.add(dimension.dimension_id)
        validated.append(dimension)
    return tuple(sorted(validated, key=lambda item: item.dimension_id))


def _student_bands(value: object) -> tuple[GroupingSignalStudentBand, ...]:
    items = _iterable_items(value, "student_bands", "GroupingSignalStudentBand")
    if not items:
        raise GroupingSignalValidationError("student_bands must not be empty.")
    validated: list[GroupingSignalStudentBand] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        if not isinstance(item, GroupingSignalStudentBand):
            raise GroupingSignalValidationError(
                f"student_bands[{index}] must be a GroupingSignalStudentBand."
            )
        try:
            entry = GroupingSignalStudentBand(
                student_id=item.student_id,
                dimension_id=item.dimension_id,
                band=item.band,
            )
        except GroupingSignalValidationError as error:
            raise GroupingSignalValidationError(
                f"student_bands[{index}] is invalid: {error}"
            ) from error
        key = (entry.student_id, entry.dimension_id)
        if key in seen:
            raise GroupingSignalValidationError(
                "student_bands contains duplicate (student_id, dimension_id) pair."
            )
        seen.add(key)
        validated.append(entry)
    return tuple(
        sorted(validated, key=lambda item: (item.dimension_id, item.student_id))
    )


def _iterable_items(
    value: object, field_name: str, item_type_name: str
) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)):
        raise GroupingSignalValidationError(
            f"{field_name} must be an iterable of {item_type_name} values."
        )
    try:
        return tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise GroupingSignalValidationError(
            f"{field_name} must be an iterable of {item_type_name} values."
        ) from error


def _identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(cast(str, value), field_name)
    except IdentifierValidationError as error:
        raise GroupingSignalValidationError(str(error)) from error


def _integer_at_least(value: object, field_name: str, minimum: int) -> int:
    integer = _require_int(value, field_name)
    if integer < minimum:
        raise GroupingSignalValidationError(
            f"{field_name} must be greater than or equal to {minimum}."
        )
    return integer


def _digest_algorithm(value: object, field_name: str) -> str:
    text = _require_str(value, field_name)
    if text != "sha256":
        raise GroupingSignalValidationError(f'{field_name} must be "sha256".')
    return text


def _sha256_digest(value: object, field_name: str) -> str:
    text = _require_str(value, field_name)
    if not _SHA256_RE.fullmatch(text):
        raise GroupingSignalValidationError(
            f"{field_name} must be exactly 64 lowercase hexadecimal characters."
        )
    return text


def _aware_datetime_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise GroupingSignalValidationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise GroupingSignalValidationError(
            f"{field_name} must be timezone-aware."
        )
    return value.astimezone(UTC)


def _canonical_datetime_from_iso(value: object, field_name: str) -> datetime:
    text = _require_str(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise GroupingSignalValidationError(
            f"{field_name} must be a valid ISO datetime string."
        ) from error
    normalized = _aware_datetime_utc(parsed, field_name)
    if text != normalized.isoformat():
        raise GroupingSignalValidationError(
            f"{field_name} must use canonical UTC ISO-8601 form with +00:00."
        )
    return normalized


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise GroupingSignalValidationError(f"{field_name} must be a string.")
    return value


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GroupingSignalValidationError(f"{field_name} must be an integer.")
    return value


def _require_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise GroupingSignalValidationError(f"{field_name} must be a list.")
    return cast(list[object], value)


def _exact_mapping(
    data: object, required_keys: frozenset[str], description: str
) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise GroupingSignalValidationError(f"{description} must be an object.")
    if any(not isinstance(key, str) for key in data):
        raise GroupingSignalValidationError(
            f"{description} keys must be strings."
        )
    mapping = cast(Mapping[str, object], data)
    keys = set(mapping)
    missing = sorted(required_keys - keys)
    if missing:
        raise GroupingSignalValidationError(
            f"{description} is missing required key(s): {', '.join(missing)}."
        )
    unknown = sorted(keys - required_keys)
    if unknown:
        raise GroupingSignalValidationError(
            f"{description} contains unknown key(s): {', '.join(unknown)}."
        )
    return mapping


def _require_canonical_dimension_order(
    dimensions: list[GroupingSignalDimension],
) -> None:
    keys = [item.dimension_id for item in dimensions]
    if keys != sorted(keys):
        raise GroupingSignalValidationError(
            "dimensions must use canonical ascending dimension_id order."
        )


def _require_canonical_student_band_order(
    student_bands: list[GroupingSignalStudentBand],
) -> None:
    keys = [(item.dimension_id, item.student_id) for item in student_bands]
    if keys != sorted(keys):
        raise GroupingSignalValidationError(
            "student_bands must use canonical (dimension_id, student_id) order."
        )


def _reject_duplicate_keys(
    pairs: Iterable[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_invalid_constant(value: str) -> NoReturn:
    raise _InvalidJsonConstantError(f"invalid JSON numeric constant: {value}")
