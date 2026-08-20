"""Tests for guarded full-roster import planning and commit."""

from __future__ import annotations

from pathlib import Path

import pytest

import pds_core.roster_imports as roster_imports
from pds_core._roster_write_lock import roster_write_lock_path
from pds_core.classes import ensure_class_folder, load_class_roster, write_class_roster
from pds_core.roster_imports import (
    RosterImportCandidateChangedError,
    RosterImportClassMismatchError,
    RosterImportConflictError,
    RosterImportRequestError,
    RosterImportWriteError,
    commit_roster_import,
    plan_roster_import,
)
from pds_core.rosters import (
    ROSTER_REQUIRED_COLUMNS,
    Roster,
    RosterValidationError,
    RosterWriteError,
    StudentRecord,
    create_roster,
    load_roster,
    write_roster,
)
from pds_core.routes import class_roster_path


def student(
    student_id: str,
    *,
    first_name: str,
    last_name: str,
    period: str = "2",
    **extra: str,
) -> dict[str, str]:
    return {
        "student_id": student_id,
        "first_name": first_name,
        "last_name": last_name,
        "period": period,
        **extra,
    }


def roster(
    class_id: str = "english9_p2",
    *,
    students: list[dict[str, str]] | None = None,
) -> Roster:
    rows = students or [student("1001", first_name="Jane", last_name="Doe")]
    return create_roster(class_id, rows)


def write_candidate_csv(path: Path, candidate: Roster) -> None:
    rows = []
    for record in candidate.students:
        row = {
            "class_id": record.class_id,
            "student_id": record.student_id,
            "last_name": record.last_name,
            "first_name": record.first_name,
            "period": record.period,
            **dict(record.extra_fields),
        }
        rows.append(row)

    header = ",".join(candidate.columns)
    lines = [header]
    for row in rows:
        lines.append(",".join(row.get(column, "") for column in candidate.columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def test_preview_first_import_is_read_only_and_all_additions(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.csv"
    candidate = roster(
        students=[
            student("1002", first_name="Marcus", last_name="Smith"),
            student("1001", first_name="Jane", last_name="Doe"),
        ]
    )
    write_candidate_csv(candidate_path, candidate)
    workspace = tmp_path / "workspace"

    preview = plan_roster_import(workspace, "english9_p2", candidate_path)

    assert not workspace.exists()
    assert preview.class_id == "english9_p2"
    assert preview.current_roster_present is False
    assert preview.current_state_token.endswith(":absent")
    assert preview.addition_count == 2
    assert [record.student_id for record in preview.additions] == ["1001", "1002"]
    assert preview.change_count == 0
    assert preview.removal_count == 0
    assert preview.unchanged_count == 0


def test_preview_mixed_diff_is_deterministic_by_student_id(tmp_path: Path) -> None:
    current = roster(
        students=[
            student("3000", first_name="Three", last_name="Existing"),
            student("1000", first_name="One", last_name="Existing"),
            student("2000", first_name="Two", last_name="Existing"),
        ]
    )
    write_class_roster(tmp_path, current)
    candidate = roster(
        students=[
            student("4000", first_name="Four", last_name="New"),
            student("2000", first_name="TwoChanged", last_name="Existing"),
            student("1000", first_name="One", last_name="Existing"),
        ]
    )

    preview = plan_roster_import(tmp_path, "english9_p2", candidate)

    assert [record.student_id for record in preview.additions] == ["4000"]
    assert [change.student_id for change in preview.changes] == ["2000"]
    assert preview.changes[0].current.first_name == "Two"
    assert preview.changes[0].proposed.first_name == "TwoChanged"
    assert [record.student_id for record in preview.removals] == ["3000"]
    assert preview.unchanged_student_ids == ("1000",)



def test_preview_unchanged_roster_reports_only_unchanged_ids(tmp_path: Path) -> None:
    current = roster(
        students=[
            student("2000", first_name="Marcus", last_name="Smith"),
            student("1000", first_name="Jane", last_name="Doe"),
        ]
    )
    write_class_roster(tmp_path, current)

    preview = plan_roster_import(tmp_path, "english9_p2", current)

    assert preview.addition_count == 0
    assert preview.change_count == 0
    assert preview.removal_count == 0
    assert preview.unchanged_student_ids == ("1000", "2000")


def test_preview_propagates_malformed_candidate_csv(tmp_path: Path) -> None:
    candidate_path = tmp_path / "malformed.csv"
    candidate_path.write_text(
        "class_id,student_id,last_name,first_name,period\n"
        "english9_p2,1001,Doe,Jane,2,EXTRA\n",
        encoding="utf-8",
        newline="",
    )

    with pytest.raises(RosterValidationError) as raised:
        plan_roster_import(tmp_path / "workspace", "english9_p2", candidate_path)

    assert any(issue.code == "malformed_row" for issue in raised.value.issues)
    assert not (tmp_path / "workspace").exists()

def test_preview_treats_extra_field_change_as_record_change(tmp_path: Path) -> None:
    current = roster(
        students=[
            student(
                "1001",
                first_name="Jane",
                last_name="Doe",
                email="old@example.test",
            )
        ]
    )
    candidate = roster(
        students=[
            student(
                "1001",
                first_name="Jane",
                last_name="Doe",
                email="new@example.test",
            )
        ]
    )
    write_class_roster(tmp_path, current)

    preview = plan_roster_import(tmp_path, "english9_p2", candidate)

    assert preview.change_count == 1
    assert dict(preview.changes[0].current.extra_fields) == {
        "email": "old@example.test"
    }
    assert dict(preview.changes[0].proposed.extra_fields) == {
        "email": "new@example.test"
    }


def test_preview_candidate_class_mismatch_is_typed(tmp_path: Path) -> None:
    with pytest.raises(RosterImportClassMismatchError) as raised:
        plan_roster_import(tmp_path, "english9_p2", roster("english9_p3"))

    assert raised.value.expected_class_id == "english9_p2"
    assert raised.value.actual_class_id == "english9_p3"
    assert not tmp_path.joinpath("classes").exists()


def test_preview_invalid_candidate_roster_is_revalidated(tmp_path: Path) -> None:
    invalid = Roster(
        class_id="english9_p2",
        students=(
            StudentRecord(
                class_id="english9_p2",
                student_id="1001",
                last_name="Doe",
                first_name="Jane",
                period="2",
                extra_fields={},
            ),
            StudentRecord(
                class_id="english9_p2",
                student_id="1001",
                last_name="Smith",
                first_name="Marcus",
                period="2",
                extra_fields={},
            ),
        ),
        columns=ROSTER_REQUIRED_COLUMNS,
    )

    with pytest.raises(RosterValidationError) as raised:
        plan_roster_import(tmp_path, "english9_p2", invalid)

    assert any(issue.code == "duplicate_student_id" for issue in raised.value.issues)


def test_preview_rejects_empty_candidate_instead_of_removing_final_student(
    tmp_path: Path,
) -> None:
    write_class_roster(tmp_path, roster())
    candidate_path = tmp_path / "empty.csv"
    candidate_path.write_text(
        "class_id,student_id,last_name,first_name,period\n",
        encoding="utf-8",
        newline="",
    )

    with pytest.raises(RosterValidationError) as raised:
        plan_roster_import(tmp_path, "english9_p2", candidate_path)

    assert [issue.code for issue in raised.value.issues] == ["empty_roster"]


def test_preview_rejects_invalid_current_canonical_roster(tmp_path: Path) -> None:
    folder = ensure_class_folder(tmp_path, "english9_p2")
    folder.roster_path.write_text(
        "class_id,student_id,last_name,first_name,period\n"
        "english9_p3,1001,Doe,Jane,2\n",
        encoding="utf-8",
        newline="",
    )

    with pytest.raises(RosterValidationError) as raised:
        plan_roster_import(tmp_path, "english9_p2", roster())

    assert [issue.code for issue in raised.value.issues] == ["class_id_mismatch"]


def test_state_tokens_are_deterministic_for_equivalent_validated_rosters(
    tmp_path: Path,
) -> None:
    candidate = roster(
        students=[
            student(
                "1001",
                first_name="Jane",
                last_name="Doe",
                email="jane@example.test",
            )
        ]
    )
    candidate_path = tmp_path / "candidate.csv"
    write_candidate_csv(candidate_path, candidate)

    direct_preview = plan_roster_import(tmp_path / "w1", "english9_p2", candidate)
    file_preview = plan_roster_import(tmp_path / "w2", "english9_p2", candidate_path)

    assert direct_preview.candidate_state_token == file_preview.candidate_state_token


def test_commit_first_import_writes_exact_reviewed_candidate(tmp_path: Path) -> None:
    candidate = roster(
        students=[
            student("2000", first_name="Marcus", last_name="Smith"),
            student("1000", first_name="Jane", last_name="Doe"),
        ]
    )
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)

    result = commit_roster_import(
        tmp_path,
        preview.class_id,
        preview.candidate,
        expected_current_state_token=preview.current_state_token,
        expected_candidate_state_token=preview.candidate_state_token,
    )

    assert result.previous_state_token == preview.current_state_token
    assert result.committed_state_token == preview.candidate_state_token
    assert result.roster_path == class_roster_path(tmp_path, "english9_p2")
    assert result.roster.source_path == result.roster_path
    assert load_class_roster(tmp_path, "english9_p2").students == candidate.students
    assert not roster_write_lock_path(result.roster_path).exists()


def test_commit_replaces_existing_roster_after_review(tmp_path: Path) -> None:
    write_class_roster(tmp_path, roster())
    candidate = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)

    commit_roster_import(
        tmp_path,
        preview.class_id,
        candidate,
        expected_current_state_token=preview.current_state_token,
        expected_candidate_state_token=preview.candidate_state_token,
    )

    loaded = load_class_roster(tmp_path, "english9_p2")
    assert [record.student_id for record in loaded.students] == ["2000"]


def test_commit_rejects_stale_preview_after_canonical_change(tmp_path: Path) -> None:
    original = roster()
    write_class_roster(tmp_path, original)
    candidate = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)
    intervening = roster(
        students=[student("3000", first_name="Alyssa", last_name="Brown")]
    )
    write_class_roster(tmp_path, intervening, overwrite=True)

    with pytest.raises(RosterImportConflictError) as raised:
        commit_roster_import(
            tmp_path,
            preview.class_id,
            candidate,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
        )

    assert raised.value.expected_state_token == preview.current_state_token
    assert raised.value.actual_state_token != preview.current_state_token
    assert load_class_roster(tmp_path, "english9_p2").students == intervening.students


def test_commit_rejects_roster_created_after_absent_preview(tmp_path: Path) -> None:
    candidate = roster()
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)
    intervening = roster(
        students=[student("3000", first_name="Alyssa", last_name="Brown")]
    )
    write_class_roster(tmp_path, intervening)

    with pytest.raises(RosterImportConflictError):
        commit_roster_import(
            tmp_path,
            preview.class_id,
            candidate,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
        )

    assert load_class_roster(tmp_path, "english9_p2").students == intervening.students


def test_commit_rejects_removed_current_roster_after_preview(tmp_path: Path) -> None:
    write_class_roster(tmp_path, roster())
    candidate = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)
    class_roster_path(tmp_path, "english9_p2").unlink()

    with pytest.raises(RosterImportConflictError) as raised:
        commit_roster_import(
            tmp_path,
            preview.class_id,
            candidate,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
        )

    assert raised.value.actual_state_token is not None
    assert raised.value.actual_state_token.endswith(":absent")
    assert not class_roster_path(tmp_path, "english9_p2").exists()


def test_commit_rejects_candidate_changed_after_preview(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.csv"
    first = roster()
    write_candidate_csv(candidate_path, first)
    preview = plan_roster_import(tmp_path / "workspace", "english9_p2", candidate_path)
    second = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )
    write_candidate_csv(candidate_path, second)

    with pytest.raises(RosterImportCandidateChangedError) as raised:
        commit_roster_import(
            tmp_path / "workspace",
            preview.class_id,
            candidate_path,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
        )

    assert raised.value.expected_state_token == preview.candidate_state_token
    assert raised.value.actual_state_token != preview.candidate_state_token
    assert not (tmp_path / "workspace").exists()


def test_commit_rejects_malformed_state_tokens_before_writing(tmp_path: Path) -> None:
    candidate = roster()

    with pytest.raises(RosterImportRequestError):
        commit_roster_import(
            tmp_path,
            "english9_p2",
            candidate,
            expected_current_state_token="not-a-token",
            expected_candidate_state_token="also-not-a-token",
        )

    assert not tmp_path.joinpath("classes").exists()


def test_commit_reports_existing_write_lock_as_conflict(tmp_path: Path) -> None:
    current = roster()
    write_class_roster(tmp_path, current)
    candidate = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)
    lock_path = roster_write_lock_path(class_roster_path(tmp_path, "english9_p2"))
    lock_path.write_text("", encoding="utf-8")

    with pytest.raises(RosterImportConflictError):
        commit_roster_import(
            tmp_path,
            preview.class_id,
            candidate,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
        )

    assert load_class_roster(tmp_path, "english9_p2").students == current.students


def test_write_class_roster_participates_in_same_exclusive_lock(tmp_path: Path) -> None:
    current = roster()
    write_class_roster(tmp_path, current)
    path = class_roster_path(tmp_path, "english9_p2")
    lock_path = roster_write_lock_path(path)
    lock_path.write_text("", encoding="utf-8")
    replacement = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )

    with pytest.raises(RosterWriteError):
        write_class_roster(tmp_path, replacement, overwrite=True)

    assert load_roster(path).students == current.students


def test_write_roster_participates_in_same_exclusive_lock(tmp_path: Path) -> None:
    current = roster()
    path = write_class_roster(tmp_path, current)
    lock_path = roster_write_lock_path(path)
    lock_path.write_text("", encoding="utf-8")
    replacement = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )

    with pytest.raises(RosterWriteError):
        write_roster(path, replacement, overwrite=True)

    assert load_roster(path).students == current.students


def test_write_class_roster_removes_lock_after_normal_write_failure(
    tmp_path: Path,
) -> None:
    current = roster()
    path = write_class_roster(tmp_path, current)

    with pytest.raises(RosterWriteError):
        write_class_roster(tmp_path, current, overwrite=False)

    assert not roster_write_lock_path(path).exists()


def test_commit_write_failure_preserves_prior_roster(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = roster()
    path = write_class_roster(tmp_path, current)
    candidate = roster(
        students=[student("2000", first_name="Marcus", last_name="Smith")]
    )
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)

    def fail_write(*args: object, **kwargs: object) -> None:
        raise RosterWriteError(path, "synthetic write failure")

    monkeypatch.setattr(roster_imports, "_write_roster_unlocked", fail_write)

    with pytest.raises(RosterWriteError):
        commit_roster_import(
            tmp_path,
            preview.class_id,
            candidate,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
        )

    assert load_class_roster(tmp_path, "english9_p2").students == current.students
    assert not roster_write_lock_path(path).exists()


def test_commit_lock_management_failure_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = roster()
    preview = plan_roster_import(tmp_path, "english9_p2", candidate)
    path = class_roster_path(tmp_path, "english9_p2")

    class BrokenLock:
        def __enter__(self) -> None:
            from pds_core._roster_write_lock import RosterWriteLockError

            raise RosterWriteLockError("synthetic lock failure")

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        roster_imports,
        "acquire_roster_write_lock",
        lambda _path, **_kwargs: BrokenLock(),
    )

    with pytest.raises(RosterImportWriteError) as raised:
        commit_roster_import(
            tmp_path,
            preview.class_id,
            candidate,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
        )

    assert raised.value.path == path
