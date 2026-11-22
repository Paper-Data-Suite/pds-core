"""Core #241 Slice B: guarded per-student service safety and data fidelity."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.roster_edits as edits
from pds_core._roster_write_lock import roster_write_lock_path
from pds_core.class_metadata import (
    create_class_metadata,
    write_class_metadata_for_class,
)
from pds_core.classes import write_class_roster
from pds_core.roster_imports import plan_roster_import
from pds_core.rosters import RosterWriteError, create_roster, load_roster
from pds_core.routes import class_roster_path

CLASS = "english12_p2"


def _change(
    operation: edits.RosterEditOperation, student_id: str, **fields: str
) -> edits.StudentRosterChange:
    return edits.StudentRosterChange(
        operation=operation, student_id=student_id, fields=fields
    )


def _two_students(root: Path) -> Path:
    roster = create_roster(
        CLASS,
        [
            {
                "student_id": "0007",
                "first_name": "Ari",
                "last_name": "Rivera",
                "period": "2",
                "preferred_name": "Ari",
            },
            {
                "student_id": "0011",
                "first_name": "Casey",
                "last_name": "Park",
                "period": "2",
                "preferred_name": "",
            },
        ],
    )
    return write_class_roster(root, roster)


def _commit(
    root: Path,
    change: edits.StudentRosterChange,
) -> edits.StudentRosterEditCommitResult:
    preview = edits.plan_student_roster_edit(root, CLASS, change)
    return edits.commit_student_roster_edit(
        root,
        CLASS,
        change,
        expected_current_state_token=preview.current_state_token,
        expected_candidate_state_token=preview.candidate_state_token,
        confirmed=True,
    )


def _class_metadata(root: Path) -> None:
    write_class_metadata_for_class(
        root,
        create_class_metadata(
            CLASS,
            "2026-2027",
            created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        ),
    )


def test_update_preserves_other_students_and_legacy_metadata_absence(
    tmp_path: Path,
) -> None:
    path = _two_students(tmp_path)
    original = load_roster(path)
    change = _change("update", "0007", period="3", preferred_name="")
    result = _commit(tmp_path, change)
    revised = load_roster(path)
    assert result.outcome == "committed"
    assert revised.students[0].period == "3"
    assert revised.students[0].extra_fields["preferred_name"] == ""
    assert revised.students[1] == original.students[1]
    assert revised.columns == original.columns


def test_add_to_existing_preserves_columns_and_other_records(tmp_path: Path) -> None:
    path = _two_students(tmp_path)
    change = _change(
        "add", "0025", first_name="Robin", last_name="Stone", period="2"
    )
    preview = edits.plan_student_roster_edit(tmp_path, CLASS, change)
    assert preview.current_count == 2
    assert preview.proposed_count == 3
    assert preview.current_record is None
    assert preview.proposed_record is not None
    assert preview.proposed_record.extra_fields["preferred_name"] == ""
    _commit(tmp_path, change)
    roster = load_roster(path)
    assert [r.student_id for r in roster.students] == ["0007", "0011", "0025"]
    assert roster.columns[-1] == "preferred_name"


def test_remove_one_student_does_not_modify_other_files(tmp_path: Path) -> None:
    path = _two_students(tmp_path)
    other_file = path.parent / "unrelated.bin"
    other_file.write_bytes(b"PRODUCER_WORK_PRESERVED")
    result = _commit(tmp_path, _change("remove", "0007"))
    assert result.outcome == "committed"
    assert [r.student_id for r in load_roster(path).students] == ["0011"]
    assert other_file.read_bytes() == b"PRODUCER_WORK_PRESERVED"


def test_first_student_requires_valid_existing_class_metadata(tmp_path: Path) -> None:
    _class_metadata(tmp_path)
    path = class_roster_path(tmp_path, CLASS)
    change = _change(
        "add", "0007", first_name="Ari", last_name="Rivera", period="2",
        z_column="last", a_column="first",
    )
    preview = edits.plan_student_roster_edit(tmp_path, CLASS, change)
    assert not path.exists()
    assert preview.current_state_token == "roster-state-v1:absent"
    assert preview.current_count == 0
    result = _commit(tmp_path, change)
    roster = load_roster(path)
    assert result.outcome == "committed"
    assert roster.columns == (
        "class_id", "student_id", "last_name", "first_name", "period",
        "a_column", "z_column",
    )
    assert roster.students[0].student_id == "0007"


def test_bare_class_dir_without_metadata_cannot_start_roster(tmp_path: Path) -> None:
    folder = tmp_path / "classes" / CLASS
    folder.mkdir(parents=True)
    before = set(folder.iterdir())
    change = _change(
        "add", "0007", first_name="Ari", last_name="Rivera", period="2"
    )
    with pytest.raises(edits.StudentRosterEditClassNotFoundError) as caught:
        edits.plan_student_roster_edit(tmp_path, CLASS, change)
    assert caught.value.reason == "missing_class_metadata"
    assert set(folder.iterdir()) == before


def test_change_fields_are_immutable_and_snapshot_independent() -> None:
    fields = {"period": "3"}
    change = edits.StudentRosterChange("update", "0007", fields)
    fields["period"] = "5"
    assert change.fields["period"] == "3"
    with pytest.raises(TypeError):
        change.fields["period"] = "6"  # type: ignore[index]


@pytest.mark.parametrize(
    ("operation", "student_id", "fields", "expected"),
    [
        ("add", "0007", {"first_name": "A", "last_name": "B", "period": "2"},
         "duplicate_student"),
        ("update", "missing", {"period": "3"}, "missing_student"),
        ("remove", "missing", {}, "missing_student"),
        ("update", "0007", {"unknown_column": "x"}, "unsupported_field"),
        ("update", "0007", {"first_name": ""}, "invalid_student"),
    ],
)
def test_invalid_mutations_refuse_without_writes(
    tmp_path: Path,
    operation: edits.RosterEditOperation,
    student_id: str,
    fields: dict[str, str],
    expected: str,
) -> None:
    path = _two_students(tmp_path)
    before = path.read_bytes()
    with pytest.raises(edits.StudentRosterEditValidationError) as caught:
        edits.plan_student_roster_edit(
            tmp_path,
            CLASS,
            edits.StudentRosterChange(operation, student_id, fields),
        )
    assert caught.value.reason == expected
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("operation", "student_id", "fields"),
    [
        ("unknown", "0007", {}),
        ("update", "0007", {}),
        ("remove", "0007", {"period": "3"}),
        ("update", "0007", {"student_id": "9999"}),
        ("update", "0007", {"class_id": CLASS}),
        ("update", "0007", {"period": 3}),
        ("update", "../bad", {"period": "3"}),
    ],
)
def test_invalid_request_is_bounded(
    operation: str, student_id: str, fields: dict[str, object]
) -> None:
    with pytest.raises(edits.StudentRosterEditRequestError):
        edits.StudentRosterChange(
            operation,  # type: ignore[arg-type]
            student_id,
            fields,  # type: ignore[arg-type]
        )


def test_noop_update_does_not_rewrite_roster(tmp_path: Path) -> None:
    path = _two_students(tmp_path)
    before = path.read_bytes()
    change = _change("update", "0007", period="2")
    preview = edits.plan_student_roster_edit(tmp_path, CLASS, change)
    assert preview.no_change and preview.changed_fields == ()
    result = _commit(tmp_path, change)
    assert result.outcome == "no_change"
    assert path.read_bytes() == before


def test_stale_candidate_and_current_tokens_are_distinct(tmp_path: Path) -> None:
    path = _two_students(tmp_path)
    change = _change("update", "0007", period="3")
    preview = edits.plan_student_roster_edit(tmp_path, CLASS, change)
    before = path.read_bytes()
    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        edits.commit_student_roster_edit(
            tmp_path,
            CLASS,
            _change("update", "0007", period="4"),
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=True,
        )
    assert caught.value.reason == "candidate_changed"
    assert path.read_bytes() == before

    fresh = create_roster(
        CLASS,
        [
            {"student_id": "0007", "first_name": "Ari",
             "last_name": "Rivera", "period": "2", "preferred_name": "Ari"},
            {"student_id": "0011", "first_name": "Casey",
             "last_name": "Park", "period": "4", "preferred_name": ""},
        ],
    )
    write_class_roster(tmp_path, fresh, overwrite=True)
    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        edits.commit_student_roster_edit(
            tmp_path,
            CLASS,
            change,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=True,
        )
    assert caught.value.reason == "current_state_changed"


def test_shared_lock_conflict_preserves_original_roster(tmp_path: Path) -> None:
    path = _two_students(tmp_path)
    before = path.read_bytes()
    change = _change("update", "0007", period="3")
    preview = edits.plan_student_roster_edit(tmp_path, CLASS, change)
    lock = roster_write_lock_path(path)
    lock.write_text("occupied", encoding="utf-8")
    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        edits.commit_student_roster_edit(
            tmp_path,
            CLASS,
            change,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=True,
        )
    assert caught.value.reason == "write_conflict"
    assert path.read_bytes() == before
    assert lock.read_text(encoding="utf-8") == "occupied"


def test_injected_write_error_does_not_claim_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _two_students(tmp_path)
    before = path.read_bytes()
    change = _change("update", "0007", period="3")
    preview = edits.plan_student_roster_edit(tmp_path, CLASS, change)

    def broken_write(
        roster_path: str | Path, _roster: object, *, overwrite: bool = False
    ) -> None:
        raise RosterWriteError(roster_path, "PRIVATE_DATA")

    monkeypatch.setattr(edits, "_write_roster_unlocked", broken_write)
    with pytest.raises(edits.StudentRosterEditWriteError) as caught:
        edits.commit_student_roster_edit(
            tmp_path,
            CLASS,
            change,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=True,
        )
    assert caught.value.reason == "write_failed"
    assert "PRIVATE_DATA" not in str(caught.value)
    assert path.read_bytes() == before


def test_full_import_and_single_edit_share_current_tokens(tmp_path: Path) -> None:
    _two_students(tmp_path)
    change = _change("update", "0007", period="3")
    preview = edits.plan_student_roster_edit(tmp_path, CLASS, change)
    imported = plan_roster_import(
        tmp_path,
        CLASS,
        create_roster(
            CLASS,
            [
                {
                    "student_id": "0007",
                    "first_name": "Ari",
                    "last_name": "Rivera",
                    "period": "3",
                    "preferred_name": "Ari",
                },
                {
                    "student_id": "0011",
                    "first_name": "Casey",
                    "last_name": "Park",
                    "period": "2",
                    "preferred_name": "",
                },
            ],
        ),
    )
    assert imported.current_state_token == preview.current_state_token
    assert imported.candidate_state_token == preview.candidate_state_token
