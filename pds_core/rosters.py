"""Shared roster models, validation, and student display helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping, Sequence

from pds_core.identifiers import IdentifierValidationError, validate_identifier

ROSTER_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "class_id",
    "student_id",
    "last_name",
    "first_name",
    "period",
)


@dataclass(frozen=True, slots=True)
class StudentRecord:
    """An immutable validated roster row."""

    class_id: str
    student_id: str
    last_name: str
    first_name: str
    period: str
    extra_fields: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "extra_fields", MappingProxyType(dict(self.extra_fields))
        )


@dataclass(frozen=True, slots=True)
class Roster:
    """An immutable collection of students from one class."""

    class_id: str
    students: tuple[StudentRecord, ...]
    columns: tuple[str, ...]
    source_path: Path | None = None


@dataclass(frozen=True, slots=True)
class RosterIssue:
    """A structured roster validation diagnostic.

    Row numbers follow CSV conventions: row 1 is the header and the first data
    row is row 2.
    """

    code: str
    message: str
    row_number: int | None = None
    column: str | None = None
    value: str | None = None


class RosterError(Exception):
    """Base exception for shared roster operations."""


class RosterReadError(RosterError):
    """Raised when a roster CSV cannot be read."""

    path: Path

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        super().__init__(f"Could not read roster CSV {self.path}: {message}")


class RosterValidationError(RosterError):
    """Raised when roster data fails validation."""

    issues: tuple[RosterIssue, ...]

    def __init__(self, issues: Sequence[RosterIssue]) -> None:
        self.issues = tuple(issues)
        if not self.issues:
            raise ValueError("RosterValidationError requires at least one issue.")

        count = len(self.issues)
        summary = self.issues[0].message
        if count > 1:
            summary = f"{summary} ({count} validation issues total)"
        super().__init__(summary)


def _validate_columns(columns: Sequence[str]) -> tuple[tuple[str, ...], list[str]]:
    normalized: list[str] = []
    raw_columns: list[str] = []
    issues: list[RosterIssue] = []
    seen: set[str] = set()

    for column_index, column in enumerate(columns, start=1):
        if not isinstance(column, str):
            issues.append(
                RosterIssue(
                    code="invalid_header",
                    message=f"Header {column_index} must be a string.",
                    row_number=1,
                    value=repr(column),
                )
            )
            continue

        trimmed = column.strip()
        raw_columns.append(column)
        normalized.append(trimmed)
        if not trimmed:
            issues.append(
                RosterIssue(
                    code="blank_header",
                    message=f"Header {column_index} must not be blank.",
                    row_number=1,
                    value=column,
                )
            )
        elif trimmed in seen:
            issues.append(
                RosterIssue(
                    code="duplicate_header",
                    message=f"Header {trimmed!r} appears more than once.",
                    row_number=1,
                    column=trimmed,
                    value=trimmed,
                )
            )
        seen.add(trimmed)

    for required_column in ROSTER_REQUIRED_COLUMNS:
        if required_column not in seen:
            issues.append(
                RosterIssue(
                    code="missing_required_column",
                    message=f"Required column {required_column!r} is missing.",
                    row_number=1,
                    column=required_column,
                )
            )

    if issues:
        raise RosterValidationError(issues)

    return tuple(normalized), raw_columns


def _row_value(
    row: Mapping[str, str], raw_column: str, normalized_column: str
) -> tuple[bool, object]:
    if raw_column in row:
        return True, row[raw_column]
    if normalized_column != raw_column and normalized_column in row:
        return True, row[normalized_column]
    return False, ""


def validate_roster_rows(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    *,
    source_path: Path | None = None,
) -> Roster:
    """Validate in-memory roster rows and return an immutable roster.

    Input headers and values are stripped of surrounding whitespace. Runtime
    values must be strings; identifiers are never inferred or coerced.
    """
    normalized_columns, raw_columns = _validate_columns(columns)
    if not rows:
        raise RosterValidationError(
            (
                RosterIssue(
                    code="empty_roster",
                    message="A roster must contain at least one student row.",
                ),
            )
        )

    issues: list[RosterIssue] = []
    students: list[StudentRecord] = []
    expected_class_id: str | None = None
    seen_student_ids: set[str] = set()

    for row_index, row in enumerate(rows, start=2):
        values: dict[str, str] = {}
        invalid_columns: set[str] = set()

        for raw_column, column in zip(raw_columns, normalized_columns, strict=True):
            present, value = _row_value(row, raw_column, column)
            if not present and column in ROSTER_REQUIRED_COLUMNS:
                issues.append(
                    RosterIssue(
                        code="missing_required_field",
                        message=f"Required field {column!r} is missing.",
                        row_number=row_index,
                        column=column,
                    )
                )
                invalid_columns.add(column)
                continue

            if not isinstance(value, str):
                issues.append(
                    RosterIssue(
                        code="non_string_value",
                        message=f"Field {column!r} must be a string.",
                        row_number=row_index,
                        column=column,
                        value=repr(value),
                    )
                )
                invalid_columns.add(column)
                continue

            values[column] = value.strip()

        for required_column in ROSTER_REQUIRED_COLUMNS:
            if required_column not in invalid_columns and not values.get(
                required_column, ""
            ):
                issues.append(
                    RosterIssue(
                        code="blank_required_value",
                        message=f"Required field {required_column!r} must not be blank.",
                        row_number=row_index,
                        column=required_column,
                        value=values.get(required_column, ""),
                    )
                )
                invalid_columns.add(required_column)

        class_id = values.get("class_id", "")
        if class_id and "class_id" not in invalid_columns:
            try:
                validate_identifier(class_id, "class_id")
            except IdentifierValidationError as error:
                issues.append(
                    RosterIssue(
                        code="invalid_class_id",
                        message=str(error),
                        row_number=row_index,
                        column="class_id",
                        value=class_id,
                    )
                )
                invalid_columns.add("class_id")
            else:
                if expected_class_id is None:
                    expected_class_id = class_id
                elif class_id != expected_class_id:
                    issues.append(
                        RosterIssue(
                            code="inconsistent_class_id",
                            message=(
                                f"Expected class_id {expected_class_id!r}, "
                                f"but found {class_id!r}."
                            ),
                            row_number=row_index,
                            column="class_id",
                            value=class_id,
                        )
                    )
                    invalid_columns.add("class_id")

        student_id = values.get("student_id", "")
        if student_id and "student_id" not in invalid_columns:
            try:
                validate_identifier(student_id, "student_id")
            except IdentifierValidationError as error:
                issues.append(
                    RosterIssue(
                        code="invalid_student_id",
                        message=str(error),
                        row_number=row_index,
                        column="student_id",
                        value=student_id,
                    )
                )
                invalid_columns.add("student_id")
            else:
                if student_id in seen_student_ids:
                    issues.append(
                        RosterIssue(
                            code="duplicate_student_id",
                            message=f"student_id {student_id!r} appears more than once.",
                            row_number=row_index,
                            column="student_id",
                            value=student_id,
                        )
                    )
                    invalid_columns.add("student_id")
                seen_student_ids.add(student_id)

        if invalid_columns:
            continue

        extra_fields = {
            column: values[column]
            for column in normalized_columns
            if column not in ROSTER_REQUIRED_COLUMNS
        }
        students.append(
            StudentRecord(
                class_id=class_id,
                student_id=student_id,
                last_name=values["last_name"],
                first_name=values["first_name"],
                period=values["period"],
                extra_fields=extra_fields,
            )
        )

    if issues:
        raise RosterValidationError(issues)

    if expected_class_id is None:
        raise RosterValidationError(
            (
                RosterIssue(
                    code="empty_roster",
                    message="A roster must contain at least one valid student row.",
                ),
            )
        )

    return Roster(
        class_id=expected_class_id,
        students=tuple(students),
        columns=normalized_columns,
        source_path=source_path,
    )


def load_roster(path: str | Path) -> Roster:
    """Load and validate a roster from a UTF-8 CSV file."""
    source_path = Path(path)

    try:
        with source_path.open(encoding="utf-8-sig", newline="") as roster_file:
            reader = csv.DictReader(roster_file, restval="", strict=True)
            columns = reader.fieldnames
            if columns is None:
                raise RosterValidationError(
                    (
                        RosterIssue(
                            code="missing_header",
                            message="Roster CSV is missing a header row.",
                            row_number=1,
                        ),
                    )
                )

            rows: list[Mapping[str, str]] = []
            malformed_issues: list[RosterIssue] = []
            for row in reader:
                extra_values = row.pop(None, None)
                if extra_values is not None:
                    malformed_issues.append(
                        RosterIssue(
                            code="malformed_row",
                            message="Roster CSV row has more values than headers.",
                            row_number=reader.line_num,
                            value=repr(extra_values),
                        )
                    )
                rows.append(row)
    except RosterValidationError:
        raise
    except (OSError, UnicodeError, csv.Error) as error:
        raise RosterReadError(source_path, str(error)) from error

    if malformed_issues:
        raise RosterValidationError(malformed_issues)

    return validate_roster_rows(columns, rows, source_path=source_path)


def _infer_roster_columns(
    students: Sequence[Mapping[str, str]],
) -> tuple[str, ...]:
    columns = list(ROSTER_REQUIRED_COLUMNS)
    seen = set(columns)
    for student in students:
        for key in student:
            column = key.strip()
            if column == "class_id" or column in seen:
                continue
            columns.append(column)
            seen.add(column)
    return tuple(columns)


def create_roster(
    class_id: str,
    students: Sequence[Mapping[str, str]],
    *,
    columns: Sequence[str] | None = None,
    source_path: Path | None = None,
) -> Roster:
    """Create a roster with one explicit class ID.

    When columns are omitted, optional columns are inferred in first-seen order.
    """
    roster_columns = _infer_roster_columns(students) if columns is None else columns
    rows: list[dict[str, str]] = []
    for student in students:
        row: dict[str, str] = {}
        for key, value in student.items():
            row.setdefault(key.strip(), value)
        row["class_id"] = class_id
        rows.append(row)
    return validate_roster_rows(roster_columns, rows, source_path=source_path)


def student_display_name(student: StudentRecord) -> str:
    """Return a student's teacher-facing display name."""
    preferred_name = student.extra_fields.get("preferred_name", "").strip()
    first_name = preferred_name or student.first_name
    return f"{first_name} {student.last_name}"


def student_sort_name(student: StudentRecord) -> str:
    """Return a student's name in last-name-first sort form."""
    return f"{student.last_name}, {student.first_name}"


def student_lookup(roster: Roster) -> Mapping[str, StudentRecord]:
    """Return an immutable student-ID lookup for a roster."""
    return MappingProxyType(
        {student.student_id: student for student in roster.students}
    )
