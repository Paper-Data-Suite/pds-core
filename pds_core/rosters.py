"""Shared roster models, validation, and student display helpers."""

from __future__ import annotations

import csv
import os
import tempfile
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


class RosterWriteError(RosterError):
    """Raised when a roster CSV cannot be written."""

    path: Path

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        super().__init__(f"Could not write roster CSV {self.path}: {message}")


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


def _student_to_csv_row(
    student: StudentRecord, columns: Sequence[str]
) -> dict[str, str]:
    required_values = {
        "class_id": student.class_id,
        "student_id": student.student_id,
        "last_name": student.last_name,
        "first_name": student.first_name,
        "period": student.period,
    }
    return {
        column: (
            required_values[column]
            if column in required_values
            else student.extra_fields.get(column, "")
        )
        for column in columns
    }


def _check_writable_roster(path: Path, roster: Roster) -> None:
    missing_columns = [
        column for column in ROSTER_REQUIRED_COLUMNS if column not in roster.columns
    ]
    if missing_columns:
        missing = ", ".join(repr(column) for column in missing_columns)
        raise RosterWriteError(path, f"required columns are missing: {missing}")

    required_fields = (
        "class_id",
        "student_id",
        "last_name",
        "first_name",
        "period",
    )
    for row_number, student in enumerate(roster.students, start=2):
        if student.class_id != roster.class_id:
            raise RosterWriteError(
                path,
                f"student row {row_number} has class_id {student.class_id!r}, "
                f"expected {roster.class_id!r}",
            )
        for field in required_fields:
            if not isinstance(getattr(student, field), str):
                raise RosterWriteError(
                    path,
                    f"student row {row_number} field {field!r} must be a string",
                )


def write_roster(
    path: str | Path,
    roster: Roster,
    *,
    overwrite: bool = False,
) -> None:
    """Atomically write a validated roster to a UTF-8 CSV file."""
    target_path = Path(path)
    target_dir = target_path.parent

    if not target_dir.exists():
        raise RosterWriteError(target_path, "parent directory does not exist")
    if not target_dir.is_dir():
        raise RosterWriteError(target_path, "parent path is not a directory")
    if target_path.exists() and not overwrite:
        raise RosterWriteError(target_path, "target file already exists")

    _check_writable_roster(target_path, roster)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=target_dir,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
        ) as roster_file:
            temp_path = Path(roster_file.name)
            writer = csv.DictWriter(roster_file, fieldnames=roster.columns)
            writer.writeheader()
            for student in roster.students:
                writer.writerow(_student_to_csv_row(student, roster.columns))
            roster_file.flush()
            os.fsync(roster_file.fileno())

        os.replace(temp_path, target_path)
        temp_path = None
    except (OSError, UnicodeError, csv.Error, TypeError, ValueError) as error:
        cleanup_error: OSError | None = None
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as caught_cleanup_error:
                cleanup_error = caught_cleanup_error

        message = str(error)
        if cleanup_error is not None:
            message = f"{message}; temporary file cleanup failed: {cleanup_error}"
        raise RosterWriteError(target_path, message) from error


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


def _roster_validation_error(
    code: str,
    message: str,
    *,
    row_number: int | None = None,
    column: str | None = None,
    value: str | None = None,
) -> RosterValidationError:
    return RosterValidationError(
        (
            RosterIssue(
                code=code,
                message=message,
                row_number=row_number,
                column=column,
                value=value,
            ),
        )
    )


def _unsupported_extra_fields(
    student: StudentRecord,
    columns: Sequence[str],
) -> tuple[str, ...]:
    return tuple(field for field in student.extra_fields if field not in columns)


def _validate_roster_instance(roster: Roster) -> Roster:
    if not isinstance(roster, Roster):
        raise _roster_validation_error(
            "invalid_roster",
            "roster must be a Roster.",
        )

    issues: list[RosterIssue] = []
    for row_number, student in enumerate(roster.students, start=2):
        if not isinstance(student, StudentRecord):
            issues.append(
                RosterIssue(
                    code="invalid_student_record",
                    message="roster.students must contain only StudentRecord values.",
                    row_number=row_number,
                    value=repr(student),
                )
            )
            continue

        unsupported_fields = _unsupported_extra_fields(student, roster.columns)
        for field in unsupported_fields:
            issues.append(
                RosterIssue(
                    code="unsupported_extra_field",
                    message=(
                        f"student_id {student.student_id!r} contains unsupported "
                        f"extra field {field!r}."
                    ),
                    row_number=row_number,
                    column=field,
                    value=student.student_id,
                )
            )

    if issues:
        raise RosterValidationError(issues)

    validated = validate_roster_rows(
        roster.columns,
        [_student_to_csv_row(student, roster.columns) for student in roster.students],
        source_path=roster.source_path,
    )
    if validated.class_id != roster.class_id:
        raise _roster_validation_error(
            "inconsistent_roster_class_id",
            (
                f"roster class_id {roster.class_id!r} does not match student "
                f"class_id {validated.class_id!r}."
            ),
            column="class_id",
            value=roster.class_id,
        )
    return validated


def _validate_mutation_student(roster: Roster, student: StudentRecord) -> StudentRecord:
    if not isinstance(student, StudentRecord):
        raise _roster_validation_error(
            "invalid_student_record",
            "student must be a StudentRecord.",
        )

    if student.class_id != roster.class_id:
        raise _roster_validation_error(
            "mismatched_class_id",
            (
                f"student_id {student.student_id!r} has class_id "
                f"{student.class_id!r}, expected {roster.class_id!r}."
            ),
            column="class_id",
            value=student.class_id,
        )

    unsupported_fields = _unsupported_extra_fields(student, roster.columns)
    if unsupported_fields:
        fields = ", ".join(repr(field) for field in unsupported_fields)
        raise _roster_validation_error(
            "unsupported_extra_field",
            (
                f"student_id {student.student_id!r} contains unsupported "
                f"extra field(s): {fields}."
            ),
            value=student.student_id,
        )

    return student


def _validated_roster_with_students(
    roster: Roster,
    students: Sequence[StudentRecord],
) -> Roster:
    return validate_roster_rows(
        roster.columns,
        [_student_to_csv_row(student, roster.columns) for student in students],
        source_path=roster.source_path,
    )


def add_student_record(
    roster: Roster,
    student: StudentRecord,
) -> Roster:
    """Return a new roster with student appended."""
    validated_roster = _validate_roster_instance(roster)
    validated_student = _validate_mutation_student(validated_roster, student)

    if any(
        existing.student_id == validated_student.student_id
        for existing in validated_roster.students
    ):
        raise _roster_validation_error(
            "duplicate_student_id",
            (
                "add_student_record cannot add duplicate student_id "
                f"{validated_student.student_id!r}."
            ),
            column="student_id",
            value=validated_student.student_id,
        )

    return _validated_roster_with_students(
        validated_roster,
        (*validated_roster.students, validated_student),
    )


def replace_student_record(
    roster: Roster,
    student: StudentRecord,
) -> Roster:
    """Return a new roster with an existing student replaced by student_id."""
    validated_roster = _validate_roster_instance(roster)
    validated_student = _validate_mutation_student(validated_roster, student)

    replaced = False
    students: list[StudentRecord] = []
    for existing in validated_roster.students:
        if existing.student_id == validated_student.student_id:
            students.append(validated_student)
            replaced = True
        else:
            students.append(existing)

    if not replaced:
        raise _roster_validation_error(
            "missing_student_id",
            (
                "replace_student_record cannot replace missing student_id "
                f"{validated_student.student_id!r}."
            ),
            column="student_id",
            value=validated_student.student_id,
        )

    return _validated_roster_with_students(validated_roster, students)


def upsert_student_record(
    roster: Roster,
    student: StudentRecord,
) -> Roster:
    """Return a new roster with student added or replaced by student_id."""
    validated_roster = _validate_roster_instance(roster)
    validated_student = _validate_mutation_student(validated_roster, student)

    replaced = False
    students: list[StudentRecord] = []
    for existing in validated_roster.students:
        if existing.student_id == validated_student.student_id:
            students.append(validated_student)
            replaced = True
        else:
            students.append(existing)

    if not replaced:
        students.append(validated_student)

    return _validated_roster_with_students(validated_roster, students)


def remove_student_record(
    roster: Roster,
    student_id: str,
) -> Roster:
    """Return a new roster without the student_id."""
    validated_roster = _validate_roster_instance(roster)

    students = [
        student
        for student in validated_roster.students
        if student.student_id != student_id
    ]
    if len(students) == len(validated_roster.students):
        raise _roster_validation_error(
            "missing_student_id",
            f"remove_student_record cannot remove missing student_id {student_id!r}.",
            column="student_id",
            value=student_id,
        )

    if not students:
        raise _roster_validation_error(
            "empty_roster",
            (
                "remove_student_record cannot remove the final student from "
                "a roster."
            ),
            column="student_id",
            value=student_id,
        )

    return _validated_roster_with_students(validated_roster, students)


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
