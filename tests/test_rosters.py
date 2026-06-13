"""Tests for shared roster models and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pds_core.rosters import (
    ROSTER_REQUIRED_COLUMNS,
    Roster,
    RosterReadError,
    RosterValidationError,
    RosterWriteError,
    StudentRecord,
    create_roster,
    load_roster,
    student_display_name,
    student_lookup,
    student_sort_name,
    validate_roster_rows,
    write_roster,
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


def write_roster_csv(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.write_text(content, encoding=encoding, newline="")


def test_load_roster_accepts_valid_csv_and_sets_source_path(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(
        path,
        "class_id,student_id,last_name,first_name,period\n"
        "english9_p2,1001,Doe,Jane,2\n"
        "english9_p2,1002,Smith,Marcus,2\n",
    )

    roster = load_roster(path)

    assert isinstance(roster, Roster)
    assert roster.class_id == "english9_p2"
    assert roster.source_path == path
    assert [student.student_id for student in roster.students] == ["1001", "1002"]


def test_load_roster_preserves_optional_columns(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(
        path,
        "class_id,student_id,last_name,first_name,period,preferred_name,email\n"
        "english9_p2,1001,Doe,Jane,2, Janie , jane@example.test \n"
        "english9_p2,1002,Smith,Marcus,2,,\n",
    )

    roster = load_roster(path)

    assert roster.columns == (*ROSTER_REQUIRED_COLUMNS, "preferred_name", "email")
    assert dict(roster.students[0].extra_fields) == {
        "preferred_name": "Janie",
        "email": "jane@example.test",
    }
    assert dict(roster.students[1].extra_fields) == {
        "preferred_name": "",
        "email": "",
    }


def test_load_roster_preserves_leading_zero_student_ids(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(
        path,
        "class_id,student_id,last_name,first_name,period\n"
        "english9_p2,0012,Doe,Jane,2\n",
    )

    roster = load_roster(path)

    assert roster.students[0].student_id == "0012"


def test_load_roster_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(
        path,
        "\ufeffclass_id,student_id,last_name,first_name,period\n"
        "english9_p2,1001,Doe,Jane,2\n",
        encoding="utf-8",
    )

    roster = load_roster(path)

    assert roster.columns[0] == "class_id"


def test_load_roster_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(path, "")

    with pytest.raises(RosterValidationError) as raised:
        load_roster(path)

    assert issue_for(raised.value, "missing_header") == (1, None, None)


@pytest.mark.parametrize(
    ("header", "row", "code", "column"),
    [
        (
            "class_id,student_id,last_name,first_name",
            "english9_p2,1001,Doe,Jane",
            "missing_required_column",
            "period",
        ),
        (
            "class_id,student_id,last_name,first_name,period,student_id",
            "english9_p2,1001,Doe,Jane,2",
            "duplicate_header",
            "student_id",
        ),
        (
            "class_id,student_id,last_name,first_name,period, ",
            "english9_p2,1001,Doe,Jane,2",
            "blank_header",
            None,
        ),
    ],
)
def test_load_roster_rejects_invalid_headers(
    tmp_path: Path, header: str, row: str, code: str, column: str | None
) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(path, f"{header}\n{row}\n")

    with pytest.raises(RosterValidationError) as raised:
        load_roster(path)

    row_number, issue_column, _ = issue_for(raised.value, code)
    assert row_number == 1
    assert issue_column == column


def test_load_roster_rejects_header_only_file(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(path, "class_id,student_id,last_name,first_name,period\n")

    with pytest.raises(RosterValidationError) as raised:
        load_roster(path)

    assert [issue.code for issue in raised.value.issues] == ["empty_roster"]


@pytest.mark.parametrize(
    ("row", "code"),
    [
        ("english9_p2,1001,Doe,,2", "blank_required_value"),
        ("bad class,1001,Doe,Jane,2", "invalid_class_id"),
        ("english9_p2,bad.id,Doe,Jane,2", "invalid_student_id"),
        (
            "english9_p2,1001,Doe,Jane,2\nenglish9_p3,1002,Smith,Marcus,2",
            "inconsistent_class_id",
        ),
        (
            "english9_p2,1001,Doe,Jane,2\nenglish9_p2,1001,Smith,Marcus,2",
            "duplicate_student_id",
        ),
    ],
)
def test_load_roster_rejects_invalid_rows(tmp_path: Path, row: str, code: str) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(
        path,
        f"class_id,student_id,last_name,first_name,period\n{row}\n",
    )

    with pytest.raises(RosterValidationError) as raised:
        load_roster(path)

    assert any(issue.code == code for issue in raised.value.issues)


def test_load_roster_rejects_rows_with_extra_cells(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    write_roster_csv(
        path,
        "class_id,student_id,last_name,first_name,period\n"
        "english9_p2,1001,Doe,Jane,2,EXTRA\n",
    )

    with pytest.raises(RosterValidationError) as raised:
        load_roster(path)

    assert issue_for(raised.value, "malformed_row") == (2, None, "['EXTRA']")


def test_load_roster_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"

    with pytest.raises(RosterReadError) as raised:
        load_roster(path)

    assert raised.value.path == path


def test_write_roster_writes_valid_minimal_csv(tmp_path: Path) -> None:
    roster = create_roster("english9_p2", [roster_row()])
    path = tmp_path / "roster.csv"

    write_roster(path, roster)

    assert path.read_text(encoding="utf-8").splitlines()[0] == (
        "class_id,student_id,last_name,first_name,period"
    )
    loaded = load_roster(path)
    assert loaded.class_id == roster.class_id
    assert loaded.columns == roster.columns
    assert loaded.students == roster.students


def test_write_roster_round_trips_optional_and_blank_fields(tmp_path: Path) -> None:
    roster = create_roster(
        "english9_p2",
        [
            roster_row(preferred_name="Janie", email="jane@example.test"),
            roster_row(
                student_id="1002",
                first_name="Marcus",
                last_name="Smith",
                preferred_name="",
                email="",
            ),
        ],
    )
    path = tmp_path / "roster.csv"

    write_roster(path, roster)

    loaded = load_roster(path)
    assert loaded.columns == roster.columns
    assert dict(loaded.students[0].extra_fields) == {
        "preferred_name": "Janie",
        "email": "jane@example.test",
    }
    assert dict(loaded.students[1].extra_fields) == {
        "preferred_name": "",
        "email": "",
    }


def test_write_roster_preserves_leading_zero_student_ids(tmp_path: Path) -> None:
    roster = create_roster(
        "english9_p2", [roster_row(student_id="0012", first_name="Jane")]
    )
    path = tmp_path / "roster.csv"

    write_roster(path, roster)

    assert load_roster(path).students[0].student_id == "0012"


def test_write_roster_refuses_existing_file_by_default(tmp_path: Path) -> None:
    roster = create_roster("english9_p2", [roster_row()])
    path = tmp_path / "roster.csv"
    write_roster(path, roster)

    with pytest.raises(RosterWriteError) as raised:
        write_roster(path, roster)

    assert raised.value.path == path


def test_write_roster_overwrites_existing_file_when_requested(
    tmp_path: Path,
) -> None:
    first_roster = create_roster("english9_p2", [roster_row()])
    second_roster = create_roster(
        "english9_p2",
        [roster_row(student_id="2002", first_name="Marcus", last_name="Smith")],
    )
    path = tmp_path / "roster.csv"
    write_roster(path, first_roster)

    write_roster(path, second_roster, overwrite=True)

    loaded = load_roster(path)
    assert [student.student_id for student in loaded.students] == ["2002"]


def test_write_roster_rejects_missing_parent_directory(tmp_path: Path) -> None:
    roster = create_roster("english9_p2", [roster_row()])
    path = tmp_path / "missing" / "roster.csv"

    with pytest.raises(RosterWriteError) as raised:
        write_roster(path, roster)

    assert raised.value.path == path


def test_write_roster_rejects_parent_path_that_is_not_directory(
    tmp_path: Path,
) -> None:
    roster = create_roster("english9_p2", [roster_row()])
    parent = tmp_path / "not-a-directory"
    parent.write_text("content", encoding="utf-8")

    with pytest.raises(RosterWriteError):
        write_roster(parent / "roster.csv", roster)


def test_write_roster_uses_roster_column_order(tmp_path: Path) -> None:
    columns = ("period", "student_id", "class_id", "first_name", "last_name")
    roster = validate_roster_rows(columns, [roster_row()])
    path = tmp_path / "roster.csv"

    write_roster(path, roster)

    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(columns)


def test_write_roster_omits_optional_fields_not_in_columns(tmp_path: Path) -> None:
    student = StudentRecord(
        class_id="english9_p2",
        student_id="1001",
        last_name="Doe",
        first_name="Jane",
        period="2",
        extra_fields={"email": "jane@example.test"},
    )
    roster = Roster(
        class_id="english9_p2",
        students=(student,),
        columns=ROSTER_REQUIRED_COLUMNS,
    )
    path = tmp_path / "roster.csv"

    write_roster(path, roster)

    content = path.read_text(encoding="utf-8")
    assert "email" not in content
    assert "jane@example.test" not in content


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
