"""Tests for shared roster models and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pds_core.rosters import (
    ROSTER_REQUIRED_COLUMNS,
    RosterValidationError,
    create_roster,
    student_display_name,
    student_lookup,
    student_sort_name,
    validate_roster_rows,
)


def roster_row(**overrides: str) -> dict[str, str]:
    row = {
        "class_id": "english9_p2",
        "student_id": "1001",
        "last_name": "Doe",
        "first_name": "Jane",
        "period": "2",
    }
    row.update(overrides)
    return row


def issue_for(
    error: RosterValidationError, code: str
) -> tuple[int | None, str | None, str | None]:
    issue = next(issue for issue in error.issues if issue.code == code)
    return issue.row_number, issue.column, issue.value


def test_valid_minimal_roster() -> None:
    roster = validate_roster_rows(ROSTER_REQUIRED_COLUMNS, [roster_row()])

    assert roster.class_id == "english9_p2"
    assert roster.columns == ROSTER_REQUIRED_COLUMNS
    assert roster.source_path is None
    assert roster.students[0].student_id == "1001"
    assert dict(roster.students[0].extra_fields) == {}


def test_optional_columns_and_trimmed_values_are_preserved() -> None:
    columns = (*ROSTER_REQUIRED_COLUMNS, " preferred_name ", "email")
    row = roster_row(preferred_name=" Janie ", email=" jane@example.test ")

    roster = validate_roster_rows(columns, [row], source_path=Path("roster.csv"))

    assert roster.columns == (*ROSTER_REQUIRED_COLUMNS, "preferred_name", "email")
    assert dict(roster.students[0].extra_fields) == {
        "preferred_name": "Janie",
        "email": "jane@example.test",
    }
    assert roster.source_path == Path("roster.csv")


def test_blank_and_missing_optional_values_are_allowed() -> None:
    columns = (*ROSTER_REQUIRED_COLUMNS, "email", "notes")
    row = roster_row(email="   ")

    roster = validate_roster_rows(columns, [row])

    assert dict(roster.students[0].extra_fields) == {"email": "", "notes": ""}


@pytest.mark.parametrize(
    ("columns", "code", "column"),
    [
        (
            ("class_id", "student_id", "last_name", "first_name"),
            "missing_required_column",
            "period",
        ),
        (
            (*ROSTER_REQUIRED_COLUMNS, "   "),
            "blank_header",
            None,
        ),
        (
            (*ROSTER_REQUIRED_COLUMNS, " student_id "),
            "duplicate_header",
            "student_id",
        ),
    ],
)
def test_invalid_headers_are_rejected(
    columns: tuple[str, ...], code: str, column: str | None
) -> None:
    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(columns, [roster_row()])

    row_number, issue_column, _ = issue_for(raised.value, code)
    assert row_number == 1
    assert issue_column == column


def test_missing_required_row_field_is_rejected() -> None:
    row = roster_row()
    del row["period"]

    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(ROSTER_REQUIRED_COLUMNS, [row])

    assert issue_for(raised.value, "missing_required_field") == (2, "period", None)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("first_name", "  ", "blank_required_value"),
        ("class_id", "English 9", "invalid_class_id"),
        ("student_id", "student.1", "invalid_student_id"),
    ],
)
def test_invalid_required_values_are_rejected(
    field: str, value: str, code: str
) -> None:
    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(
            ROSTER_REQUIRED_COLUMNS,
            [roster_row(**{field: value})],
        )

    assert issue_for(raised.value, code) == (
        2,
        field,
        value.strip(),
    )


def test_inconsistent_class_ids_are_rejected() -> None:
    rows = [roster_row(), roster_row(class_id="english9_p3", student_id="1002")]

    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(ROSTER_REQUIRED_COLUMNS, rows)

    assert issue_for(raised.value, "inconsistent_class_id") == (
        3,
        "class_id",
        "english9_p3",
    )


def test_duplicate_student_ids_are_rejected() -> None:
    rows = [roster_row(), roster_row(first_name="John")]

    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(ROSTER_REQUIRED_COLUMNS, rows)

    assert issue_for(raised.value, "duplicate_student_id") == (
        3,
        "student_id",
        "1001",
    )


def test_empty_roster_is_rejected() -> None:
    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(ROSTER_REQUIRED_COLUMNS, [])

    assert [issue.code for issue in raised.value.issues] == ["empty_roster"]


def test_row_and_column_order_and_leading_zeros_are_preserved() -> None:
    columns = ("period", "student_id", "class_id", "first_name", "last_name")
    rows = [
        roster_row(student_id="0012"),
        roster_row(student_id="0003", first_name="Alyssa", last_name="Brown"),
    ]

    roster = validate_roster_rows(columns, rows)

    assert roster.columns == columns
    assert [student.student_id for student in roster.students] == ["0012", "0003"]
    assert [student.last_name for student in roster.students] == ["Doe", "Brown"]


def test_create_roster_supplies_class_id_and_trims_values() -> None:
    student = roster_row(student_id=" 0012 ", first_name=" Jane ")
    del student["class_id"]

    roster = create_roster("english9_p2", [student])

    assert roster.class_id == "english9_p2"
    assert roster.students[0].student_id == "0012"
    assert roster.students[0].first_name == "Jane"


def test_create_roster_supplied_class_id_overrides_student_class_id() -> None:
    student = roster_row(class_id="english9_p3")

    roster = create_roster("english9_p2", [student])

    assert roster.class_id == "english9_p2"
    assert roster.students[0].class_id == "english9_p2"


def test_create_roster_infers_optional_columns_by_default() -> None:
    students = [
        roster_row(preferred_name=" Janie "),
        roster_row(
            student_id="1002",
            first_name="Marcus",
            last_name="Smith",
            email=" msmith@example.test ",
        ),
    ]

    roster = create_roster("english9_p2", students)

    assert roster.columns == (
        *ROSTER_REQUIRED_COLUMNS,
        "preferred_name",
        "email",
    )
    assert dict(roster.students[0].extra_fields) == {
        "preferred_name": "Janie",
        "email": "",
    }
    assert dict(roster.students[1].extra_fields) == {
        "preferred_name": "",
        "email": "msmith@example.test",
    }


def test_create_roster_explicit_columns_control_optional_fields() -> None:
    columns = (*ROSTER_REQUIRED_COLUMNS, "preferred_name")
    student = roster_row(preferred_name="Janie", email="jane@example.test")

    roster = create_roster("english9_p2", [student], columns=columns)

    assert roster.columns == columns
    assert dict(roster.students[0].extra_fields) == {"preferred_name": "Janie"}


def test_create_roster_trims_inferred_optional_keys() -> None:
    student = roster_row()
    student[" preferred_name "] = " Janie "

    roster = create_roster("english9_p2", [student])

    assert roster.columns == (*ROSTER_REQUIRED_COLUMNS, "preferred_name")
    assert dict(roster.students[0].extra_fields) == {"preferred_name": "Janie"}


def test_create_roster_rejects_blank_inferred_optional_key() -> None:
    student = roster_row()
    student["   "] = "some value"

    with pytest.raises(RosterValidationError) as raised:
        create_roster("english9_p2", [student])

    assert issue_for(raised.value, "blank_header") == (1, None, "")


def test_invalid_identifiers_do_not_create_cascading_diagnostics() -> None:
    rows = [
        roster_row(class_id="bad class", student_id="bad student"),
        roster_row(class_id="english9_p2", student_id="bad student"),
    ]

    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(ROSTER_REQUIRED_COLUMNS, rows)

    assert [issue.code for issue in raised.value.issues] == [
        "invalid_class_id",
        "invalid_student_id",
        "invalid_student_id",
    ]


def test_student_name_helpers_use_canonical_and_preferred_names() -> None:
    columns = (*ROSTER_REQUIRED_COLUMNS, "preferred_name")
    student = validate_roster_rows(
        columns, [roster_row(preferred_name="Janie")]
    ).students[0]

    assert student_display_name(student) == "Janie Doe"
    assert student_sort_name(student) == "Doe, Jane"
    assert student.student_id == "1001"


def test_blank_preferred_name_falls_back_to_first_name() -> None:
    columns = (*ROSTER_REQUIRED_COLUMNS, "preferred_name")
    student = validate_roster_rows(columns, [roster_row(preferred_name="  ")]).students[
        0
    ]

    assert student_display_name(student) == "Jane Doe"


def test_student_lookup_is_immutable_and_keyed_by_student_id() -> None:
    roster = validate_roster_rows(
        ROSTER_REQUIRED_COLUMNS,
        [roster_row(), roster_row(student_id="1002", first_name="John")],
    )

    lookup = student_lookup(roster)

    assert lookup["1002"].first_name == "John"
    with pytest.raises(TypeError):
        lookup["1003"] = roster.students[0]  # type: ignore[index]


def test_student_extra_fields_are_an_immutable_snapshot() -> None:
    extra_fields = {"preferred_name": "Janie"}
    row = roster_row(**extra_fields)
    roster = validate_roster_rows((*ROSTER_REQUIRED_COLUMNS, "preferred_name"), [row])
    student = roster.students[0]
    extra_fields["preferred_name"] = "Changed"

    assert student.extra_fields["preferred_name"] == "Janie"
    with pytest.raises(TypeError):
        student.extra_fields["preferred_name"] = "Changed"  # type: ignore[index]


def test_validation_error_exposes_multiple_structured_issues() -> None:
    rows: list[dict[str, Any]] = [
        roster_row(first_name=" "),
        {**roster_row(student_id="bad id"), "period": 2},
    ]

    with pytest.raises(RosterValidationError) as raised:
        validate_roster_rows(ROSTER_REQUIRED_COLUMNS, rows)

    assert {issue.code for issue in raised.value.issues} == {
        "blank_required_value",
        "invalid_student_id",
        "non_string_value",
    }
    assert "3 validation issues total" in str(raised.value)
