"""Core #242 C3B4 synthetic teacher year-menu acceptance."""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.classroom_menu_school_year as flow
import pds_core.classroom_school_year_commit as service
import pds_core.school_years as years
import pds_core.teacher_menus as menus
from pds_core.classroom_admin_preview import SchoolYearChange
from pds_core.classroom_school_year_commit import (
    SchoolYearCommitResult,
    commit_guarded_school_year_change,
)
from pds_core.classes import ensure_class_folder
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.teacher_menus import run_workspace_classroom_menu

YEAR = "2026-2027"
START = "2026-09-08T08:00:00-04:00"
END = "2027-06-30T12:00:00-04:00"
START_TIME = datetime(2026, 9, 8, 8, tzinfo=timezone.utc)
END_TIME = datetime(2027, 6, 30, 12, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "synthetic-workspace"
    workspace.mkdir()
    monkeypatch.setattr(menus, "_CLASSROOM_SCHOOL_YEAR_PREVIEW_TEST_ONLY", False)
    monkeypatch.setattr(menus, "_CLASSROOM_WORKSPACE_PREVIEW_TEST_ONLY", False)
    monkeypatch.setattr(menus, "_CLASSROOM_READONLY_PREVIEW_TEST_ONLY", False)
    return workspace


def _request(root: Path) -> SharedTeacherMenuRequest:
    return SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="opaque-year-return",
        context=TeacherContextHint(
            workspace_root=root,
            display_label="Synthetic Classroom",
        ),
    )


def _run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    inputs: list[str],
    *,
    enabled: bool = True,
    interactive: bool = True,
) -> tuple[SharedTeacherMenuResult, str, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_SCHOOL_YEAR_PREVIEW_TEST_ONLY", enabled)
    out, err = io.StringIO(), io.StringIO()
    iterator = iter(inputs)
    result = run_workspace_classroom_menu(
        _request(root),
        read_line=lambda: next(iterator),
        output=out,
        error_output=err,
        interactive=interactive,
    )
    assert result.return_token == "opaque-year-return"
    assert "Revalidate workspace" in result.message
    assert "opaque-year-return" not in out.getvalue() + err.getvalue()
    return result, out.getvalue(), err.getvalue()


def test_public_gate_remains_unavailable(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, output, error = _run(
        root, monkeypatch, ["5", "1", YEAR, START, "C"], enabled=False
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()
    assert not years.school_year_state_path(root).exists()
    assert output == error == ""


def test_noninteractive_remains_unavailable(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, out, error = _run(root, monkeypatch, [], interactive=False)
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.change_scopes == frozenset()
    assert out == error == ""
    assert not years.school_year_state_path(root).exists()


def test_review_confirm_first_year_returns_committed_scope(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, out, error = _run(root, monkeypatch, ["5", "1", YEAR, START, "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.SCHOOL_YEAR})
    assert "Previous record: missing" in out
    assert f"Active year after: {YEAR}" in out
    assert f"Effective timestamp: {START}" in out
    assert "PREVIEW ONLY" in out
    assert re.search(r"\b[0-9a-f]{64}\b", out) is None
    assert "School-year transition committed." in out
    state = years.load_school_year_state(root)
    assert state is not None
    assert state.opened_at.isoformat() == START
    assert state.active_school_year == YEAR
    assert state.closed_at is None
    assert not (root / ".school-year.write.lock").exists()
    assert error == ""


def test_same_year_noop_never_rewrites(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    years.open_school_year(
        root, YEAR, opened_at=datetime.fromisoformat(START)
    )
    file = years.school_year_state_path(root)
    before = file.read_bytes()
    result, output, error = _run(root, monkeypatch, ["5", "1", YEAR, END, "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert "No-op:" in output
    assert file.read_bytes() == before
    assert not (root / ".school-year.write.lock").exists()
    assert error == ""


def test_close_preserves_classroom_data_and_reports_year_scope(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    years.open_school_year(root, YEAR, opened_at=datetime.fromisoformat(START))
    class_folder = ensure_class_folder(root, "english12_p2")
    artifact = class_folder.class_dir / "synthetic-producer-owned.txt"
    artifact.write_text("preserved", encoding="utf-8")
    result, output, error = _run(root, monkeypatch, ["5", "2", END, "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.SCHOOL_YEAR})
    assert "Active year after: (none)" in output
    state = years.load_school_year_state(root)
    assert state is not None
    assert state.closed_at.isoformat() == END
    assert artifact.read_text(encoding="utf-8") == "preserved"
    assert error == ""


@pytest.mark.parametrize(
    "inputs",
    [
        ["5", "1", "B", "B", "B"],
        ["5", "1", YEAR, "B", "B", "B"],
        ["5", "1", YEAR, START, "B", "B", "B"],
        ["5", "1", YEAR, START, "no", "B", "B"],
        ["5", "1", "invalid year", "B", "B"],
        ["5", "1", YEAR, "2026-09-08T08:00:00", "B", "B"],
    ],
)
def test_cancel_and_invalid_inputs_do_not_write(
    root: Path, monkeypatch: pytest.MonkeyPatch, inputs: list[str]
) -> None:
    result, _out, error = _run(root, monkeypatch, inputs)
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert not years.school_year_state_path(root).exists()
    assert error == ""


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        (["5", "M"], TeacherMenuExit.MAIN_MENU),
        (["5", "Q"], TeacherMenuExit.QUIT),
        (["5", "1", YEAR, START, "M"], TeacherMenuExit.MAIN_MENU),
        (["5", "2", END, "Q"], TeacherMenuExit.FAILED),
        (["5", "1", YEAR], TeacherMenuExit.CANCELLED),
    ],
)
def test_navigation_never_saves(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    inputs: list[str],
    expected: TeacherMenuExit,
) -> None:
    result, _out, _error = _run(root, monkeypatch, inputs)
    assert result.exit is expected
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not years.school_year_state_path(root).exists()


def test_stale_context_refused_before_confirmation(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = service.plan_guarded_school_year_change

    def intervening(
        location: str | Path,
        change: SchoolYearChange,
        *,
        effective_at: datetime,
    ) -> service.GuardedSchoolYearReview:
        years.open_school_year(
            root, YEAR, opened_at=datetime.fromisoformat(START)
        )
        return real(location, change, effective_at=effective_at)

    monkeypatch.setattr(flow, "plan_guarded_school_year_change", intervening)
    result, _out, error = _run(root, monkeypatch, ["5", "1", YEAR, START])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "Active year changed" in error
    assert years.get_active_school_year(root) == YEAR


def test_stale_after_preview_refuses_commit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = commit_guarded_school_year_change

    def interposed(
        location: str | Path,
        change: SchoolYearChange,
        *,
        effective_at: datetime,
        expected_current_state_token: str,
        expected_candidate_state_token: str,
        confirmed: bool,
    ) -> SchoolYearCommitResult:
        years.open_school_year(
            root, "2027-2028", opened_at=datetime.fromisoformat(START)
        )
        return real(
            location,
            change,
            effective_at=effective_at,
            expected_current_state_token=expected_current_state_token,
            expected_candidate_state_token=expected_candidate_state_token,
            confirmed=confirmed,
        )

    monkeypatch.setattr(flow, "commit_guarded_school_year_change", interposed)
    result, _out, error = _run(root, monkeypatch, ["5", "1", YEAR, START, "C"])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert "review again" in error
    assert years.get_active_school_year(root) == "2027-2028"


def test_uncertain_after_canonical_write_is_not_false_no_change(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual = years.open_school_year

    def replace_then_raise(
        location: str | Path,
        year: str,
        *,
        opened_at: datetime,
        overwrite: bool = False,
    ) -> years.SchoolYearState:
        actual(location, year, opened_at=opened_at, overwrite=overwrite)
        raise years.SchoolYearStateError("synthetic postwrite failure")

    monkeypatch.setattr(service, "open_school_year", replace_then_raise)
    result, _out, error = _run(root, monkeypatch, ["5", "1", YEAR, START, "C"])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.INDETERMINATE
    assert result.change_scopes == frozenset({TeacherChangeScope.SCHOOL_YEAR})
    assert "outcome uncertain" in error
    assert years.get_active_school_year(root) == YEAR


def test_closed_year_rollover_stays_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    years.open_school_year(root, YEAR, opened_at=datetime.fromisoformat(START))
    years.close_school_year(root, closed_at=datetime.fromisoformat(END))
    old = years.school_year_state_path(root).read_bytes()
    result, _out, error = _run(
        root, monkeypatch, ["5", "1", "2027-2028", END, "C"]
    )
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "refused safely" in error
    assert years.school_year_state_path(root).read_bytes() == old


def test_read_only_browsing_and_workspace_preference_retained(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, output, error = _run(root, monkeypatch, ["2", "B", "5", "B", "B"])
    assert result.exit is TeacherMenuExit.BACK
    assert "Classes found:" in output
    assert "Manage school year" in output
    assert "Manage saved workspace preference" in output
    assert not years.school_year_state_path(root).exists()
    assert error == ""
