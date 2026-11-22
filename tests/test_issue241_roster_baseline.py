"""Core #241 Slice A: protect existing canonical roster behavior before new services."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.classes import write_class_roster
from pds_core.rosters import (
    RosterValidationError,
    StudentRecord,
    add_student_record,
    create_roster,
    load_roster,
    remove_student_record,
    replace_student_record,
)


def _roster():
    return create_roster(
        "english12_p2",
        [
            {
                "student_id": "0007",
                "last_name": "Rivera",
                "first_name": "Ari",
                "period": "2",
                "preferred_name": "Ari",
            },
            {
                "student_id": "0011",
                "last_name": "Park",
                "first_name": "Casey",
                "period": "2",
                "preferred_name": "",
            },
        ],
    )


def test_pure_student_change_preserves_ids_optional_columns_and_order() -> None:
    original = _roster()
    first = original.students[0]
    updated = replace_student_record(
        original,
        StudentRecord(
            class_id=first.class_id,
            student_id=first.student_id,
            last_name=first.last_name,
            first_name=first.first_name,
            period="3",
            extra_fields=first.extra_fields,
        ),
    )

    assert [s.student_id for s in updated.students] == ["0007", "0011"]
    assert updated.columns == original.columns
    assert updated.students[1] == original.students[1]
    assert updated.students[0].extra_fields == first.extra_fields
    assert original.students[0].period == "2"
    assert updated.students[0].period == "3"


def test_existing_transformers_refuse_duplicate_and_final_removal() -> None:
    original = _roster()
    with pytest.raises(RosterValidationError):
        add_student_record(original, original.students[0])

    one_student = remove_student_record(original, "0011")
    assert [s.student_id for s in one_student.students] == ["0007"]
    with pytest.raises(RosterValidationError) as raised:
        remove_student_record(one_student, "0007")
    assert any(issue.code == "empty_roster" for issue in raised.value.issues)


def test_existing_canonical_writer_preserves_string_student_ids(tmp_path: Path) -> None:
    original = _roster()
    path = write_class_roster(tmp_path, original)
    loaded = load_roster(path)
    assert [s.student_id for s in loaded.students] == ["0007", "0011"]
    assert loaded.columns == original.columns
