"""Human-editable CSV conversion for neutral grouping-signal snapshots."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal, TypeAlias, cast

from pds_core.grouping_signals import (
    GROUPING_SIGNAL_RECORD_TYPE,
    GROUPING_SIGNAL_SCHEMA_VERSION,
    GroupingSignalDimension,
    GroupingSignalSet,
    GroupingSignalSource,
    GroupingSignalSourceKind,
    GroupingSignalStudentBand,
    GroupingSignalValidationError,
    validate_grouping_signal_set,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier

GROUPING_SIGNAL_CSV_CONTRACT_NAME: Final[str] = "grouping_signal_csv_v1"

GroupingSignalCsvRepresentationScope: TypeAlias = Literal[
    "complete_signal", "dimension_projection"
]
GROUPING_SIGNAL_CSV_REPRESENTATION_SCOPES: Final[frozenset[str]] = frozenset(
    {"complete_signal", "dimension_projection"}
)

_METADATA_ORDER: Final[tuple[str, ...]] = (
    "csv_contract",
    "schema_version",
    "record_type",
    "representation_scope",
    "signal_set_id",
    "class_id",
    "created_at",
    "source.kind",
    "source.module_id",
    "source.snapshot_id",
    "source.snapshot_digest_algorithm",
    "source.snapshot_digest",
    "dimension_id",
    "band_count",
)
_METADATA_KEYS: Final[frozenset[str]] = frozenset(_METADATA_ORDER)
_ROW_HEADER: Final[tuple[str, str]] = ("student_id", "band")
_DECIMAL_INTEGER_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9]+$")


class GroupingSignalCsvError(ValueError):
    """Raised when grouping-signal CSV parsing or conversion fails."""


@dataclass(frozen=True, slots=True)
class GroupingSignalCsvRow:
    """One parsed student-band row from a one-dimension CSV document."""

    student_id: str
    band: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "student_id", _identifier(self.student_id, "student_id")
        )
        object.__setattr__(self, "band", _positive_int(self.band, "band"))


@dataclass(frozen=True, slots=True)
class GroupingSignalCsvDocument:
    """Validated human-editable representation of one selected signal dimension."""

    csv_contract: str
    schema_version: str
    record_type: str
    representation_scope: GroupingSignalCsvRepresentationScope
    signal_set_id: str
    class_id: str
    created_at: datetime
    source: GroupingSignalSource
    dimension: GroupingSignalDimension
    rows: tuple[GroupingSignalCsvRow, ...]

    def __post_init__(self) -> None:
        if self.csv_contract != GROUPING_SIGNAL_CSV_CONTRACT_NAME:
            raise GroupingSignalCsvError(
                f'csv_contract must be "{GROUPING_SIGNAL_CSV_CONTRACT_NAME}".'
            )
        if self.schema_version != GROUPING_SIGNAL_SCHEMA_VERSION:
            raise GroupingSignalCsvError(
                f'schema_version must be "{GROUPING_SIGNAL_SCHEMA_VERSION}".'
            )
        if self.record_type != GROUPING_SIGNAL_RECORD_TYPE:
            raise GroupingSignalCsvError(
                f'record_type must be "{GROUPING_SIGNAL_RECORD_TYPE}".'
            )
        if self.representation_scope not in GROUPING_SIGNAL_CSV_REPRESENTATION_SCOPES:
            raise GroupingSignalCsvError(
                "representation_scope must be one of: "
                + ", ".join(sorted(GROUPING_SIGNAL_CSV_REPRESENTATION_SCOPES))
                + "."
            )
        object.__setattr__(
            self, "signal_set_id", _identifier(self.signal_set_id, "signal_set_id")
        )
        object.__setattr__(self, "class_id", _identifier(self.class_id, "class_id"))
        object.__setattr__(
            self, "created_at", _aware_datetime_utc(self.created_at, "created_at")
        )
        object.__setattr__(self, "source", _source(self.source))
        object.__setattr__(self, "dimension", _dimension(self.dimension))

        rows = _rows(self.rows)
        for index, row in enumerate(rows, start=1):
            if row.band > self.dimension.band_count:
                raise GroupingSignalCsvError(
                    f"data row {index} band must be between 1 and "
                    f"{self.dimension.band_count}."
                )
        object.__setattr__(self, "rows", rows)

    @property
    def requires_new_identity(self) -> bool:
        """Return whether standalone conversion must use a new signal identity."""
        return self.representation_scope == "dimension_projection"


def parse_grouping_signal_csv(data: str | bytes) -> GroupingSignalCsvDocument:
    """Parse and structurally validate one grouping-signal CSV document."""
    text = _csv_text(data)
    metadata, table_text = _split_metadata_and_table(text)
    _require_exact_metadata(metadata)

    source = _source_from_metadata(metadata)
    dimension = _dimension_from_metadata(metadata)
    rows = _parse_rows(table_text, dimension.band_count)

    return GroupingSignalCsvDocument(
        csv_contract=metadata["csv_contract"],
        schema_version=metadata["schema_version"],
        record_type=metadata["record_type"],
        representation_scope=cast(
            GroupingSignalCsvRepresentationScope, metadata["representation_scope"]
        ),
        signal_set_id=metadata["signal_set_id"],
        class_id=metadata["class_id"],
        created_at=_datetime_from_iso(metadata["created_at"], "metadata created_at"),
        source=source,
        dimension=dimension,
        rows=rows,
    )


def grouping_signal_csv_to_signal_set(
    document: GroupingSignalCsvDocument,
    *,
    new_signal_set_id: str | None = None,
    new_created_at: datetime | None = None,
) -> GroupingSignalSet:
    """Convert one validated CSV document into a canonical Core signal model."""
    csv_document = _document(document)
    has_new_id = new_signal_set_id is not None
    has_new_time = new_created_at is not None
    if has_new_id != has_new_time:
        raise GroupingSignalCsvError(
            "new_signal_set_id and new_created_at must be supplied together."
        )
    if csv_document.requires_new_identity and not has_new_id:
        raise GroupingSignalCsvError(
            "dimension_projection requires a new signal_set_id and created_at."
        )

    signal_set_id = csv_document.signal_set_id
    created_at = csv_document.created_at
    if has_new_id:
        assert new_signal_set_id is not None
        assert new_created_at is not None
        candidate_id = _identifier(new_signal_set_id, "new_signal_set_id")
        if candidate_id == csv_document.signal_set_id:
            raise GroupingSignalCsvError(
                "new_signal_set_id must differ from the CSV-declared signal_set_id."
            )
        signal_set_id = candidate_id
        created_at = _aware_datetime_utc(new_created_at, "new_created_at")

    try:
        return GroupingSignalSet(
            schema_version=csv_document.schema_version,
            record_type=csv_document.record_type,
            signal_set_id=signal_set_id,
            class_id=csv_document.class_id,
            created_at=created_at,
            source=csv_document.source,
            dimensions=(csv_document.dimension,),
            student_bands=tuple(
                GroupingSignalStudentBand(
                    student_id=row.student_id,
                    dimension_id=csv_document.dimension.dimension_id,
                    band=row.band,
                )
                for row in csv_document.rows
            ),
        )
    except GroupingSignalValidationError as error:
        raise GroupingSignalCsvError(
            f"CSV could not be converted to grouping_signal_set_v1: {error}"
        ) from error


def grouping_signal_set_from_csv(
    data: str | bytes,
    *,
    new_signal_set_id: str | None = None,
    new_created_at: datetime | None = None,
) -> GroupingSignalSet:
    """Parse and convert grouping-signal CSV in one operation."""
    return grouping_signal_csv_to_signal_set(
        parse_grouping_signal_csv(data),
        new_signal_set_id=new_signal_set_id,
        new_created_at=new_created_at,
    )


def grouping_signal_set_to_csv(
    value: GroupingSignalSet, dimension_id: str
) -> str:
    """Export one explicitly selected dimension as deterministic CSV text."""
    try:
        signal = validate_grouping_signal_set(value)
    except GroupingSignalValidationError as error:
        raise GroupingSignalCsvError(f"signal is invalid: {error}") from error

    selected_id = _identifier(dimension_id, "dimension_id")
    dimension = next(
        (item for item in signal.dimensions if item.dimension_id == selected_id), None
    )
    if dimension is None:
        raise GroupingSignalCsvError(
            f"dimension_id {selected_id!r} is not declared by the signal set."
        )

    scope = (
        "complete_signal" if len(signal.dimensions) == 1 else "dimension_projection"
    )
    metadata = {
        "csv_contract": GROUPING_SIGNAL_CSV_CONTRACT_NAME,
        "schema_version": signal.schema_version,
        "record_type": signal.record_type,
        "representation_scope": scope,
        "signal_set_id": signal.signal_set_id,
        "class_id": signal.class_id,
        "created_at": signal.created_at.isoformat(),
        "source.kind": signal.source.kind,
        "source.module_id": signal.source.module_id or "",
        "source.snapshot_id": signal.source.snapshot_id or "",
        "source.snapshot_digest_algorithm": signal.source.snapshot_digest_algorithm or "",
        "source.snapshot_digest": signal.source.snapshot_digest or "",
        "dimension_id": dimension.dimension_id,
        "band_count": str(dimension.band_count),
    }

    output = io.StringIO(newline="")
    for key in _METADATA_ORDER:
        output.write(f"# {key}={metadata[key]}\n")
    writer = csv.writer(
        output,
        delimiter=",",
        quotechar='"',
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
        strict=True,
    )
    writer.writerow(_ROW_HEADER)
    selected_rows = sorted(
        (item for item in signal.student_bands if item.dimension_id == selected_id),
        key=lambda item: item.student_id,
    )
    for row in selected_rows:
        writer.writerow((row.student_id, row.band))
    return output.getvalue()


def grouping_signal_set_to_csv_bytes(
    value: GroupingSignalSet, dimension_id: str
) -> bytes:
    """Export one selected dimension as deterministic UTF-8 CSV bytes."""
    return grouping_signal_set_to_csv(value, dimension_id).encode("utf-8")


def _csv_text(data: str | bytes) -> str:
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise GroupingSignalCsvError(
                "grouping-signal CSV bytes must be valid UTF-8."
            ) from error
    elif isinstance(data, str):
        text = data[1:] if data.startswith("\ufeff") else data
    else:
        raise GroupingSignalCsvError(
            "grouping-signal CSV must be a string or UTF-8 bytes."
        )
    if "\x00" in text:
        raise GroupingSignalCsvError("grouping-signal CSV must not contain NUL bytes.")
    if re.search(r"\r(?!\n)", text):
        raise GroupingSignalCsvError(
            "grouping-signal CSV line endings must be LF or CRLF."
        )
    return text.replace("\r\n", "\n")


def _split_metadata_and_table(text: str) -> tuple[dict[str, str], str]:
    lines = text.split("\n")
    if not lines or lines[0] == "":
        raise GroupingSignalCsvError(
            "first line must declare csv_contract=grouping_signal_csv_v1."
        )

    metadata: dict[str, str] = {}
    header_index: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("# "):
            key, value = _metadata_line(line, index + 1)
            if index == 0 and key != "csv_contract":
                raise GroupingSignalCsvError(
                    "first line must declare csv_contract=grouping_signal_csv_v1."
                )
            if key in metadata:
                raise GroupingSignalCsvError(
                    f"duplicate metadata key {key!r} at line {index + 1}."
                )
            if key not in _METADATA_KEYS:
                raise GroupingSignalCsvError(
                    f"unknown metadata key {key!r} at line {index + 1}."
                )
            metadata[key] = value
            continue
        header_index = index
        break

    if header_index is None:
        raise GroupingSignalCsvError("CSV data header is missing.")
    if header_index == 0:
        raise GroupingSignalCsvError(
            "first line must declare csv_contract=grouping_signal_csv_v1."
        )
    table_text = "\n".join(lines[header_index:])
    return metadata, table_text


def _metadata_line(line: str, line_number: int) -> tuple[str, str]:
    payload = line[2:]
    if "=" not in payload:
        raise GroupingSignalCsvError(
            f"metadata line {line_number} must use '# key=value'."
        )
    key, value = payload.split("=", 1)
    if not key or key != key.strip():
        raise GroupingSignalCsvError(
            f"metadata line {line_number} has an invalid key."
        )
    return key, value


def _require_exact_metadata(metadata: dict[str, str]) -> None:
    missing = sorted(_METADATA_KEYS - set(metadata))
    if missing:
        raise GroupingSignalCsvError(
            "CSV metadata is missing required key(s): " + ", ".join(missing) + "."
        )
    if metadata["csv_contract"] != GROUPING_SIGNAL_CSV_CONTRACT_NAME:
        raise GroupingSignalCsvError(
            f'metadata csv_contract must be "{GROUPING_SIGNAL_CSV_CONTRACT_NAME}".'
        )
    if metadata["schema_version"] != GROUPING_SIGNAL_SCHEMA_VERSION:
        raise GroupingSignalCsvError(
            f'metadata schema_version must be "{GROUPING_SIGNAL_SCHEMA_VERSION}".'
        )
    if metadata["record_type"] != GROUPING_SIGNAL_RECORD_TYPE:
        raise GroupingSignalCsvError(
            f'metadata record_type must be "{GROUPING_SIGNAL_RECORD_TYPE}".'
        )
    if metadata["representation_scope"] not in GROUPING_SIGNAL_CSV_REPRESENTATION_SCOPES:
        raise GroupingSignalCsvError(
            "metadata representation_scope must be one of: "
            + ", ".join(sorted(GROUPING_SIGNAL_CSV_REPRESENTATION_SCOPES))
            + "."
        )
    _identifier(metadata["signal_set_id"], "metadata signal_set_id")
    _identifier(metadata["class_id"], "metadata class_id")
    _datetime_from_iso(metadata["created_at"], "metadata created_at")


def _source_from_metadata(metadata: dict[str, str]) -> GroupingSignalSource:
    try:
        return GroupingSignalSource(
            kind=cast(GroupingSignalSourceKind, metadata["source.kind"]),
            module_id=_null_text(metadata["source.module_id"]),
            snapshot_id=_null_text(metadata["source.snapshot_id"]),
            snapshot_digest_algorithm=_null_text(
                metadata["source.snapshot_digest_algorithm"]
            ),
            snapshot_digest=_null_text(metadata["source.snapshot_digest"]),
        )
    except GroupingSignalValidationError as error:
        raise GroupingSignalCsvError(f"metadata source is invalid: {error}") from error


def _dimension_from_metadata(metadata: dict[str, str]) -> GroupingSignalDimension:
    dimension_id = _identifier(metadata["dimension_id"], "metadata dimension_id")
    band_count = _decimal_int(metadata["band_count"], "metadata band_count")
    try:
        return GroupingSignalDimension(
            dimension_id=dimension_id,
            band_count=band_count,
        )
    except GroupingSignalValidationError as error:
        raise GroupingSignalCsvError(f"metadata dimension is invalid: {error}") from error


def _parse_rows(table_text: str, band_count: int) -> tuple[GroupingSignalCsvRow, ...]:
    try:
        reader = csv.reader(
            io.StringIO(table_text, newline=""),
            delimiter=",",
            quotechar='"',
            skipinitialspace=False,
            strict=True,
        )
        header = next(reader, None)
        if header is None:
            raise GroupingSignalCsvError("CSV data header is missing.")
        if tuple(header) != _ROW_HEADER:
            raise GroupingSignalCsvError(
                'CSV header must be exactly "student_id,band".'
            )

        rows: list[GroupingSignalCsvRow] = []
        seen: dict[str, int] = {}
        for row_number, fields in enumerate(reader, start=1):
            if not fields:
                raise GroupingSignalCsvError(
                    f"data row {row_number} must not be blank."
                )
            if len(fields) != 2:
                raise GroupingSignalCsvError(
                    f"data row {row_number} must contain exactly student_id and band."
                )
            student_id = fields[0]
            try:
                student_id = _identifier(
                    student_id, f"data row {row_number} student_id"
                )
            except GroupingSignalCsvError:
                raise
            first = seen.get(student_id)
            if first is not None:
                raise GroupingSignalCsvError(
                    f"duplicate student_id at data row {row_number}; "
                    f"first occurrence was data row {first}."
                )
            band = _decimal_int(fields[1], f"data row {row_number} band")
            if band < 1 or band > band_count:
                raise GroupingSignalCsvError(
                    f"data row {row_number} band must be between 1 and {band_count}."
                )
            seen[student_id] = row_number
            rows.append(GroupingSignalCsvRow(student_id=student_id, band=band))
    except csv.Error as error:
        raise GroupingSignalCsvError(f"CSV row table is malformed: {error}") from error

    if not rows:
        raise GroupingSignalCsvError("CSV must contain at least one student data row.")
    return tuple(rows)


def _document(value: object) -> GroupingSignalCsvDocument:
    if not isinstance(value, GroupingSignalCsvDocument):
        raise GroupingSignalCsvError(
            "document must be a GroupingSignalCsvDocument."
        )
    return GroupingSignalCsvDocument(
        csv_contract=value.csv_contract,
        schema_version=value.schema_version,
        record_type=value.record_type,
        representation_scope=value.representation_scope,
        signal_set_id=value.signal_set_id,
        class_id=value.class_id,
        created_at=value.created_at,
        source=value.source,
        dimension=value.dimension,
        rows=value.rows,
    )


def _source(value: object) -> GroupingSignalSource:
    if not isinstance(value, GroupingSignalSource):
        raise GroupingSignalCsvError("source must be a GroupingSignalSource.")
    try:
        return GroupingSignalSource(
            kind=value.kind,
            module_id=value.module_id,
            snapshot_id=value.snapshot_id,
            snapshot_digest_algorithm=value.snapshot_digest_algorithm,
            snapshot_digest=value.snapshot_digest,
        )
    except GroupingSignalValidationError as error:
        raise GroupingSignalCsvError(f"source is invalid: {error}") from error


def _dimension(value: object) -> GroupingSignalDimension:
    if not isinstance(value, GroupingSignalDimension):
        raise GroupingSignalCsvError(
            "dimension must be a GroupingSignalDimension."
        )
    try:
        return GroupingSignalDimension(value.dimension_id, value.band_count)
    except GroupingSignalValidationError as error:
        raise GroupingSignalCsvError(f"dimension is invalid: {error}") from error


def _rows(value: object) -> tuple[GroupingSignalCsvRow, ...]:
    if isinstance(value, (str, bytes)):
        raise GroupingSignalCsvError(
            "rows must be an iterable of GroupingSignalCsvRow values."
        )
    try:
        items = tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise GroupingSignalCsvError(
            "rows must be an iterable of GroupingSignalCsvRow values."
        ) from error
    if not items:
        raise GroupingSignalCsvError("rows must not be empty.")

    rows: list[GroupingSignalCsvRow] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, GroupingSignalCsvRow):
            raise GroupingSignalCsvError(
                f"rows[{index - 1}] must be a GroupingSignalCsvRow."
            )
        row = GroupingSignalCsvRow(item.student_id, item.band)
        if row.student_id in seen:
            raise GroupingSignalCsvError(
                f"rows contains duplicate student_id at item {index}."
            )
        seen.add(row.student_id)
        rows.append(row)
    return tuple(rows)


def _identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(cast(str, value), field_name)
    except IdentifierValidationError as error:
        raise GroupingSignalCsvError(str(error)) from error


def _positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GroupingSignalCsvError(f"{field_name} must be an integer.")
    if value < 1:
        raise GroupingSignalCsvError(f"{field_name} must be greater than zero.")
    return value


def _decimal_int(value: str, field_name: str) -> int:
    if not _DECIMAL_INTEGER_RE.fullmatch(value):
        raise GroupingSignalCsvError(
            f"{field_name} must be unambiguous base-10 integer text."
        )
    return int(value, 10)


def _datetime_from_iso(value: str, field_name: str) -> datetime:
    if value == "":
        raise GroupingSignalCsvError(f"{field_name} must not be empty.")
    if value != value.strip():
        raise GroupingSignalCsvError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise GroupingSignalCsvError(
            f"{field_name} must be a valid ISO-8601 datetime."
        ) from error
    return _aware_datetime_utc(parsed, field_name)


def _aware_datetime_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise GroupingSignalCsvError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise GroupingSignalCsvError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _null_text(value: str) -> str | None:
    return None if value == "" else value
