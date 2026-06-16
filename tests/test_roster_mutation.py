"""Tests for in-memory roster mutation helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from pds_core.rosters import (
    ROSTER_REQUIRED_COLUMNS,
    Roster,
    RosterValidationError,
    StudentRecord,
    add_student_record,
    load_roster,
    remove_student_record,
    replace_student_record,
    student_lookup,
    upsert_student_record,
    validate_roster_rows,
    write_roster,
)


StudentMutationHelper = Callable[[Roster, StudentRecord], Roster]


def roster_row(**overrides: str) -> dict[str, str]:
    row = {
        "class_id": "english9_p2",
        "student_id": "1001",
        "last_name": "Doe",
        "first_name": "Jane",
        "period": "2",
        "preferred_name": "Janie",
        "email": "jane@example.test",
    }
    row.update(overrides)
    return row


def make_roster() -> Roster:
    return validate_roster_rows(
        (*ROSTER_REQUIRED_COLUMNS, "preferred_name", "email"),
        [
            roster_row(),
            roster_row(
                student_id="1002",
                last_name="Smith",
                first_name="Marcus",
                preferred_name="",
                email="marcus@example.test",
            ),
            roster_row(
                student_id="1003",
                last_name="Brown",
                first_name="Alyssa",
                preferred_name="Lyss",
                email="alyssa@example.test",
            ),
        ],
        source_path=Path("classes/english9_p2/roster.csv"),
    )


def make_student(
    student_id: str,
    last_name: str = "Nguyen",
    first_name: str = "Linh",
    *,
    class_id: str = "english9_p2",
    period: str = "2",
    extra_fields: dict[str, str] | None = None,
) -> StudentRecord:
    return StudentRecord(
        class_id=class_id,
        student_id=student_id,
        last_name=last_name,
        first_name=first_name,
        period=period,
        extra_fields=extra_fields
        or {
            "preferred_name": first_name,
            "email": f"{first_name.lower()}@example.test",
        },
    )


def row_from_student(student: StudentRecord, columns: tuple[str, ...]) -> dict[str, str]:
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


def student_ids(roster: Roster) -> tuple[str, ...]:
    return tuple(student.student_id for student in roster.students)


def assert_roster_metadata_preserved(original: Roster, updated: Roster) -> None:
    assert updated.class_id == original.class_id
    assert updated.columns == original.columns
    assert updated.source_path == original.source_path


def assert_existing_validation_accepts(roster: Roster) -> None:
    validated = validate_roster_rows(
        roster.columns,
        [row_from_student(student, roster.columns) for student in roster.students],
        source_path=roster.source_path,
    )

    assert validated == roster


def issue_codes(error: RosterValidationError) -> tuple[str, ...]:
    return tuple(issue.code for issue in error.issues)


def test_add_student_record_appends_and_preserves_metadata_and_extra_fields() -> None:
    roster = make_roster()
    original_students = roster.students
    student = make_student("1004", extra_fields={"preferred_name": "Lin", "email": ""})

    updated = add_student_record(roster, student)

    assert student_ids(updated) == ("1001", "1002", "1003", "1004")
    assert updated.students[:3] == original_students
    assert dict(updated.students[-1].extra_fields) == {
        "preferred_name": "Lin",
        "email": "",
    }
    assert_roster_metadata_preserved(roster, updated)
    assert roster.students == original_students
    assert_existing_validation_accepts(updated)


def test_add_student_record_rejects_duplicate_student_id() -> None:
    with pytest.raises(RosterValidationError, match="duplicate student_id") as raised:
        add_student_record(make_roster(), make_student("1002"))

    assert issue_codes(raised.value) == ("duplicate_student_id",)


@pytest.mark.parametrize(
    "helper",
    [
        add_student_record,
        replace_student_record,
        upsert_student_record,
    ],
)
def test_student_mutation_helpers_reject_mismatched_class_id(
    helper: StudentMutationHelper,
) -> None:
    with pytest.raises(RosterValidationError, match="class_id") as raised:
        helper(make_roster(), make_student("1004", class_id="english9_p3"))

    assert issue_codes(raised.value) == ("mismatched_class_id",)


@pytest.mark.parametrize(
    "helper",
    [
        add_student_record,
        replace_student_record,
        upsert_student_record,
    ],
)
def test_student_mutation_helpers_reject_unsupported_extra_fields(
    helper: StudentMutationHelper,
) -> None:
    student_id = "1002" if helper is replace_student_record else "1004"
    student = make_student(
        student_id,
        extra_fields={
            "preferred_name": "Lin",
            "email": "linh@example.test",
            "locker": "A12",
        },
    )

    with pytest.raises(RosterValidationError, match="unsupported extra field"):
        helper(make_roster(), student)


@pytest.mark.parametrize(
    "helper",
    [
        add_student_record,
        replace_student_record,
        upsert_student_record,
    ],
)
def test_student_mutation_helpers_reject_non_roster_values(
    helper: StudentMutationHelper,
) -> None:
    with pytest.raises(RosterValidationError, match="roster"):
        helper(cast(Any, "not a roster"), make_student("1004"))


@pytest.mark.parametrize(
    "helper",
    [
        add_student_record,
        replace_student_record,
        upsert_student_record,
    ],
)
def test_student_mutation_helpers_reject_non_student_values(
    helper: StudentMutationHelper,
) -> None:
    with pytest.raises(RosterValidationError, match="student"):
        helper(make_roster(), cast(Any, "not a student"))


def test_replace_student_record_replaces_existing_student_in_place() -> None:
    roster = make_roster()
    original_students = roster.students
    replacement = make_student(
        "1002",
        last_name="Santos",
        first_name="Mateo",
        extra_fields={"preferred_name": "Teo", "email": "mateo@example.test"},
    )

    updated = replace_student_record(roster, replacement)

    assert student_ids(updated) == ("1001", "1002", "1003")
    assert updated.students[0] == original_students[0]
    assert updated.students[1] == replacement
    assert updated.students[2] == original_students[2]
    assert dict(updated.students[1].extra_fields) == {
        "preferred_name": "Teo",
        "email": "mateo@example.test",
    }
    assert_roster_metadata_preserved(roster, updated)
    assert roster.students == original_students
    assert_existing_validation_accepts(updated)


def test_replace_student_record_rejects_missing_student_id() -> None:
    with pytest.raises(RosterValidationError, match="missing student_id") as raised:
        replace_student_record(make_roster(), make_student("1004"))

    assert issue_codes(raised.value) == ("missing_student_id",)


def test_upsert_student_record_replaces_existing_student_in_place() -> None:
    roster = make_roster()
    original_students = roster.students
    replacement = make_student("1002", last_name="Santos", first_name="Mateo")

    updated = upsert_student_record(roster, replacement)

    assert student_ids(updated) == ("1001", "1002", "1003")
    assert updated.students[1] == replacement
    assert_roster_metadata_preserved(roster, updated)
    assert roster.students == original_students
    assert_existing_validation_accepts(updated)


def test_upsert_student_record_appends_new_student() -> None:
    roster = make_roster()
    original_students = roster.students
    student = make_student("1004")

    updated = upsert_student_record(roster, student)

    assert student_ids(updated) == ("1001", "1002", "1003", "1004")
    assert updated.students[-1] == student
    assert_roster_metadata_preserved(roster, updated)
    assert roster.students == original_students
    assert_existing_validation_accepts(updated)


def test_remove_student_record_removes_existing_student_and_preserves_order() -> None:
    roster = make_roster()
    original_students = roster.students

    updated = remove_student_record(roster, "1002")

    assert student_ids(updated) == ("1001", "1003")
    assert updated.students == (original_students[0], original_students[2])
    assert_roster_metadata_preserved(roster, updated)
    assert roster.students == original_students
    assert_existing_validation_accepts(updated)


def test_remove_student_record_rejects_missing_student_id() -> None:
    with pytest.raises(RosterValidationError, match="missing student_id") as raised:
        remove_student_record(make_roster(), "9999")

    assert issue_codes(raised.value) == ("missing_student_id",)


def test_remove_student_record_rejects_removing_final_student() -> None:
    roster = validate_roster_rows(
        ROSTER_REQUIRED_COLUMNS,
        [roster_row()],
        source_path=Path("classes/english9_p2/roster.csv"),
    )

    with pytest.raises(RosterValidationError, match="final student") as raised:
        remove_student_record(roster, "1001")

    assert issue_codes(raised.value) == ("empty_roster",)


def test_remove_student_record_rejects_non_roster_values() -> None:
    with pytest.raises(RosterValidationError, match="roster"):
        remove_student_record(cast(Any, "not a roster"), "1001")


def test_mutated_roster_round_trips_through_csv_and_supports_lookup(
    tmp_path: Path,
) -> None:
    roster = add_student_record(make_roster(), make_student("1004"))
    path = tmp_path / "roster.csv"

    write_roster(path, roster)
    loaded = load_roster(path)
    lookup = student_lookup(roster)

    assert loaded.columns == roster.columns
    assert loaded.students == roster.students
    assert lookup["1004"].first_name == "Linh"

