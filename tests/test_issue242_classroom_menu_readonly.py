"""Core #242 B2: staged read-only menus with real synthetic classroom data."""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.classroom_menu_readonly as reader
import pds_core.teacher_menus as menus
from pds_core.classes import ensure_class_folder, write_class_roster
from pds_core.classroom_discovery import (
    ClassroomOverview,
    ClassroomRosterView,
    inspect_classroom_overview,
    inspect_classroom_roster,
)
from pds_core.rosters import create_roster
from pds_core.school_years import open_school_year
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.teacher_menus import run_workspace_classroom_menu

pytestmark = pytest.mark.usefixtures("classroom_capability_disabled")


@pytest.fixture(autouse=True)
def _keep_public_menu_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menus, "_CLASSROOM_READONLY_PREVIEW_TEST_ONLY", False)


def _request(root: Path) -> SharedTeacherMenuRequest:
    return SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="opaque-q-review-42",
        context=TeacherContextHint(
            workspace_root=root,
            class_id="english12_p2",
            display_label="Synthetic English 12 Review",
        ),
    )


def _seed(root: Path, *, count: int = 2) -> Path:
    students = [
        {
            "student_id": f"{number:04}",
            "first_name": "Ari",
            "last_name": "Rivera",
            "period": "2",
        }
        for number in range(7, 7 + count)
    ]
    path = write_class_roster(root, create_roster("english12_p2", students))
    open_school_year(
        root,
        "2026-2027",
        opened_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    return path


def _invoke(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    responses: list[str],
) -> tuple[TeacherMenuExit, str, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_READONLY_PREVIEW_TEST_ONLY", True)
    out = io.StringIO()
    errors = io.StringIO()
    values = iter(responses)
    result = run_workspace_classroom_menu(
        _request(root),
        read_line=lambda: next(values),
        output=out,
        error_output=errors,
        interactive=True,
    )
    assert result.return_token == "opaque-q-review-42"
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert "Revalidate workspace, school year, class, roster and work" in result.message
    assert "opaque-q-review-42" not in out.getvalue()
    assert "opaque-q-review-42" not in errors.getvalue()
    return result.exit, out.getvalue(), errors.getvalue()


def test_public_boundary_stays_unavailable_and_does_not_read(tmp_path: Path) -> None:
    root = tmp_path / "missing"

    def fail() -> str:
        raise AssertionError("Unqualified public menu cannot read input")

    result = run_workspace_classroom_menu(
        _request(root), read_line=fail, output=io.StringIO(), interactive=True
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()
    assert not root.exists()


def test_noninteractive_gate_precedes_staged_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(menus, "_CLASSROOM_READONLY_PREVIEW_TEST_ONLY", True)

    def fail() -> str:
        raise AssertionError("Noninteractive menu cannot read input")

    root = tmp_path / "missing"
    result = run_workspace_classroom_menu(
        _request(root), read_line=fail, output=io.StringIO(), interactive=False
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert not root.exists()


def test_workspace_class_student_navigation_and_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    roster = _seed(root)
    before = roster.read_bytes()
    exit_kind, transcript, errors = _invoke(
        root, monkeypatch, ["1", "B", "2", "1", "1", "B", "B", "B", "B"]
    )
    assert exit_kind is TeacherMenuExit.BACK
    assert "Resolution source: explicit" in transcript
    assert "Active school year: 2026-2027" in transcript
    assert "english12 p2 [ID: english12_p2]" in transcript
    assert "Students enrolled: 2" in transcript
    assert "Ari Rivera (ID: 0007)" in transcript
    assert "Ari Rivera (ID: 0008)" in transcript
    assert "Student enrollment — Read-only" in transcript
    assert "Editing is not enabled in this preview." in transcript
    assert errors == ""
    assert roster.read_bytes() == before


@pytest.mark.parametrize(
    ("choices", "expected"),
    [
        (["B"], TeacherMenuExit.BACK),
        (["m"], TeacherMenuExit.MAIN_MENU),
        (["Q"], TeacherMenuExit.QUIT),
        (["2", "1", "M"], TeacherMenuExit.MAIN_MENU),
        (["2", "1", "Q"], TeacherMenuExit.QUIT),
        ([], TeacherMenuExit.CANCELLED),
        ([""], TeacherMenuExit.CANCELLED),
    ],
)
def test_b_m_q_and_eof_return_to_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    choices: list[str],
    expected: TeacherMenuExit,
) -> None:
    root = tmp_path / "workspace"
    roster = _seed(root)
    before = roster.read_bytes()
    exit_kind, transcript, errors = _invoke(root, monkeypatch, choices)
    assert exit_kind is expected
    assert "Read-only classroom preview" in transcript
    assert errors == ""
    assert roster.read_bytes() == before


def test_missing_workspace_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "missing"
    exit_kind, transcript, errors = _invoke(
        root, monkeypatch, ["1", "B", "2", "B", "B"]
    )
    assert exit_kind is TeacherMenuExit.BACK
    assert "Workspace state: not present" in transcript
    assert "No class folders found." in transcript
    assert errors == ""
    assert not root.exists()


def test_invalid_inputs_and_planned_standards_do_not_mutate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    roster = _seed(root)
    before = roster.read_bytes()
    exit_kind, transcript, errors = _invoke(
        root, monkeypatch, ["N", "W", ":notes", "0", "3", "B", "B"]
    )
    assert exit_kind is TeacherMenuExit.BACK
    assert "Choose a listed option" in transcript
    assert "Standards integration belongs to a later slice." in transcript
    assert errors == ""
    assert roster.read_bytes() == before


def test_class_pagination_reaches_last_stable_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    for n in range(13):
        ensure_class_folder(root, f"class_{n:02}")
    exit_kind, transcript, errors = _invoke(
        root, monkeypatch, ["2", ">", "1", "B", "<", "B", "B"]
    )
    assert exit_kind is TeacherMenuExit.BACK
    assert "Classes found: 13" in transcript
    assert "Class ID: class_12" in transcript
    assert errors == ""


def test_roster_pagination_preserves_leading_zero_student_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    roster = _seed(root, count=13)
    before = roster.read_bytes()
    exit_kind, transcript, errors = _invoke(
        root, monkeypatch, ["2", "1", ">", "1", "B", "B", "B", "B"]
    )
    assert exit_kind is TeacherMenuExit.BACK
    assert "Students enrolled: 13" in transcript
    assert "Student: Ari Rivera (ID: 0019)" in transcript
    assert errors == ""
    assert roster.read_bytes() == before


def test_invalid_school_year_fails_closed_without_path_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    path = root / "settings" / "school_year.json"
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    exit_kind, transcript, errors = _invoke(root, monkeypatch, ["B"])
    assert exit_kind is TeacherMenuExit.FAILED
    assert "Canonical" not in transcript
    assert "Classroom inspection refused" in errors
    assert str(root) not in errors
    assert path.read_bytes() == b"{"


def test_changed_school_year_during_visit_refuses_stale_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    _seed(root)
    original = inspect_classroom_overview
    calls = 0

    def shifting(root_hint: Path | None) -> ClassroomOverview:
        nonlocal calls
        calls += 1
        found = original(root_hint)
        if calls > 1:
            return replace(found, active_school_year="2027-2028")
        return found

    monkeypatch.setattr(reader, "inspect_classroom_overview", shifting)
    exit_kind, _transcript, errors = _invoke(root, monkeypatch, ["2", "1"])
    assert exit_kind is TeacherMenuExit.FAILED
    assert "Workspace or active school year changed" in errors
    assert calls == 2


def test_removed_selected_student_is_not_silently_reassigned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    _seed(root)
    original = inspect_classroom_roster
    calls = 0

    def shifting(root_hint: str | Path | None, class_id: str) -> ClassroomRosterView:
        nonlocal calls
        calls += 1
        result = original(root_hint, class_id)
        return replace(result, students=()) if calls > 1 else result

    monkeypatch.setattr(reader, "inspect_classroom_roster", shifting)
    exit_kind, transcript, errors = _invoke(root, monkeypatch, ["2", "1", "1"])
    assert exit_kind is TeacherMenuExit.FAILED
    assert "Previously selected student is no longer enrolled" in errors
    assert "Student enrollment — Read-only" in transcript


def test_oversized_numeric_choice_is_rejected_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    _seed(root)
    exit_kind, transcript, errors = _invoke(root, monkeypatch, ["9" * 5000, "B"])
    assert exit_kind is TeacherMenuExit.BACK
    assert "Choose a listed option" in transcript
    assert errors == ""


def test_deleted_class_selection_refuses_instead_of_switching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    _seed(root)
    original = inspect_classroom_overview
    calls = 0

    def shifting(root_hint: Path | None) -> ClassroomOverview:
        nonlocal calls
        calls += 1
        found = original(root_hint)
        if calls > 2:
            return replace(found, classes=())
        return found

    monkeypatch.setattr(reader, "inspect_classroom_overview", shifting)
    exit_kind, _transcript, errors = _invoke(root, monkeypatch, ["2", "1"])
    assert exit_kind is TeacherMenuExit.FAILED
    assert "Previously selected class is no longer available" in errors
    assert calls == 3
