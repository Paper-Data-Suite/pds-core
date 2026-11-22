"""Core #241 deferred service vectors: activate automatically when Slice B exists.

Skipping before Slice B is intentional and is NOT a claim of functional qualification.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from pds_core.classes import write_class_roster
from pds_core.rosters import create_roster, load_roster
from pds_core.routes import class_roster_path


@pytest.fixture
def edits() -> ModuleType:
    if importlib.util.find_spec("pds_core.roster_edits") is None:
        pytest.skip("Core #241 Slice B service not implemented; future acceptance vector")
    return importlib.import_module("pds_core.roster_edits")


def _seed(workspace: Path) -> Path:
    roster = create_roster(
        "english12_p2",
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
    return write_class_roster(workspace, roster)


def _change(edits: ModuleType, operation: str, student_id: str, **fields: str):
    constructor = getattr(edits, "StudentRosterChange")
    return constructor(operation=operation, student_id=student_id, fields=fields)


def test_read_only_preview_does_not_touch_roster_or_create_lock(
    tmp_path: Path, edits: ModuleType
) -> None:
    path = _seed(tmp_path)
    before = path.read_bytes()
    change = _change(edits, "update", "0007", period="3")
    plan = getattr(edits, "plan_student_roster_edit")
    preview = plan(tmp_path, "english12_p2", change)

    assert path.read_bytes() == before
    assert preview.current_state_token.startswith("roster-state-v1:sha256:")
    assert preview.current_record.student_id == "0007"
    assert preview.proposed_record.period == "3"
    assert preview.changed_fields == ("period",)
    assert not (path.parent / ".roster.write.lock").exists()


def test_confirmed_commit_only_changes_selected_record(
    tmp_path: Path, edits: ModuleType
) -> None:
    _seed(tmp_path)
    change = _change(edits, "update", "0007", period="3")
    preview = edits.plan_student_roster_edit(tmp_path, "english12_p2", change)
    result = edits.commit_student_roster_edit(
        tmp_path,
        "english12_p2",
        change,
        expected_current_state_token=preview.current_state_token,
        expected_candidate_state_token=preview.candidate_state_token,
        confirmed=True,
    )

    updated = load_roster(class_roster_path(tmp_path, "english12_p2"))
    assert result.outcome == "committed"
    assert updated.students[0].period == "3"
    assert updated.students[0].student_id == "0007"
    assert updated.students[0].extra_fields["preferred_name"] == "Ari"
    assert updated.students[1].first_name == "Casey"
    assert updated.columns[-1] == "preferred_name"


def test_missing_explicit_confirmation_is_nonmutating(
    tmp_path: Path, edits: ModuleType
) -> None:
    path = _seed(tmp_path)
    before = path.read_bytes()
    change = _change(edits, "update", "0007", period="3")
    preview = edits.plan_student_roster_edit(tmp_path, "english12_p2", change)

    with pytest.raises(edits.StudentRosterEditRequestError):
        edits.commit_student_roster_edit(
            tmp_path,
            "english12_p2",
            change,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=False,
        )
    assert path.read_bytes() == before


def test_stale_current_roster_refuses_commit_without_overwrite(
    tmp_path: Path, edits: ModuleType
) -> None:
    path = _seed(tmp_path)
    change = _change(edits, "update", "0007", period="3")
    preview = edits.plan_student_roster_edit(tmp_path, "english12_p2", change)
    newer = create_roster(
        "english12_p2",
        [
            {"student_id": "0007", "first_name": "Ari", "last_name": "Rivera",
             "period": "2", "preferred_name": "Ari"},
            {"student_id": "0011", "first_name": "Casey", "last_name": "Park",
             "period": "4", "preferred_name": ""},
        ],
    )
    write_class_roster(tmp_path, newer, overwrite=True)
    before = path.read_bytes()

    with pytest.raises(edits.StudentRosterEditConflictError):
        edits.commit_student_roster_edit(
            tmp_path,
            "english12_p2",
            change,
            expected_current_state_token=preview.current_state_token,
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=True,
        )
    assert path.read_bytes() == before


def test_removing_final_student_is_refused(
    tmp_path: Path, edits: ModuleType
) -> None:
    write_class_roster(
        tmp_path,
        create_roster(
            "english12_p2",
            [{"student_id": "0007", "first_name": "Ari",
              "last_name": "Rivera", "period": "2"}],
        ),
    )
    path = class_roster_path(tmp_path, "english12_p2")
    before = path.read_bytes()

    with pytest.raises(edits.StudentRosterEditValidationError):
        edits.plan_student_roster_edit(
            tmp_path, "english12_p2", _change(edits, "remove", "0007")
        )
    assert path.read_bytes() == before


def test_unknown_class_does_not_create_directories(
    tmp_path: Path, edits: ModuleType
) -> None:
    assert not (tmp_path / "classes").exists()
    with pytest.raises(edits.StudentRosterEditClassNotFoundError):
        edits.plan_student_roster_edit(
            tmp_path,
            "invented_class",
            _change(
                edits, "add", "0007",
                first_name="Ari", last_name="Rivera", period="2",
            ),
        )
    assert not (tmp_path / "classes").exists()
