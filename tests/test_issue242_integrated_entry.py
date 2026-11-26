"""E: synthetic entrypoint and caller-owned resumption qualification."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable

import pytest

from pds_core import teacher_experience
from pds_core.class_metadata import create_class_metadata, write_class_metadata_for_class
from pds_core.classes import load_class_roster, write_class_roster
from pds_core.classroom_discovery import (
    ClassroomDiscoveryError,
    inspect_classroom_overview,
    inspect_classroom_roster,
)
from pds_core.cli import _run as run_cli
from pds_core.core_menu import _run as run_core
from pds_core.rosters import create_roster
from pds_core.roster_imports import _roster_state_token
from pds_core.school_years import close_school_year, open_school_year
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_menus import run_workspace_classroom_menu

YEAR = "2026-2027"
CLASS = "english12_p2"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = datetime(2027, 6, 30, tzinfo=timezone.utc)
TOKEN = "synthetic-caller-continuation"


def _rows() -> list[dict[str, str]]:
    return [
        {"student_id": "0007", "first_name": "Ari", "last_name": "Rivera", "period": "2"},
        {"student_id": "0011", "first_name": "Ari", "last_name": "Rivera", "period": "2"},
    ]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "workspace"
    folder.mkdir()
    open_school_year(folder, YEAR, opened_at=START)
    write_class_metadata_for_class(folder, create_class_metadata(CLASS, YEAR, created_at=START))
    write_class_roster(folder, create_roster(CLASS, _rows()))
    return folder


@pytest.fixture
def qualified(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real build still lacks classroom.menu.v1. Simulate the final
    # capability gate only; all storage, controller and mutations are real.
    monkeypatch.setattr(
        teacher_experience, "get_teacher_experience_capabilities",
        lambda: frozenset({"classroom.menu.v1", "classroom.roster_edits.v1"}),
    )


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_core_main_menu_default_unavailable(root: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = run_core(["--workspace", str(root)], stdin=io.StringIO("6\n\n4\n"), stdout=out, stderr=err)
    assert code == 0
    assert "6. Workspace & Classroom Management (not yet available)" in out.getvalue()
    assert "not qualified" in out.getvalue()
    assert "Classes and rosters" not in out.getvalue()
    assert err.getvalue() == ""


def test_core_option_six_uses_integrated_controller(
    root: Path, qualified: None,
) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = run_core(["--workspace", str(root)], stdin=io.StringIO("6\n2\n1\n2\nR\nC\n\n4\n"), stdout=out, stderr=err)
    assert code == 0
    transcript = out.getvalue()
    assert "6. Workspace & Classroom Management" in transcript
    assert "5. Notes & Tasks  (:notes)" in transcript
    assert "Ari Rivera (ID: 0011)" in transcript
    assert "Enrollment change committed." in transcript
    assert transcript.count("Main Menu") >= 2
    assert [student.student_id for student in load_class_roster(root, CLASS).students] == ["0007"]
    assert err.getvalue() == ""


@pytest.mark.parametrize("choice", ["B", "M", "Q"])
def test_core_navigation(root: Path, qualified: None, choice: str) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = run_core(["--workspace", str(root)], stdin=io.StringIO(f"6\n{choice}\n4\n"), stdout=out, stderr=err)
    assert code == 0 and err.getvalue() == ""
    assert "Classes and rosters" in out.getvalue()


def test_cli_noninteractive_never_resolves_workspace(
    tmp_path: Path, qualified: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoRead(io.StringIO):
        def readline(self, size: int | None = -1) -> str:
            raise AssertionError("Redirected menu must not read input")

    def no_access(*args: object, **kwargs: object) -> None:
        raise AssertionError("Redirected menu must not resolve workspace")

    monkeypatch.setattr("sys.stdin", NoRead())
    monkeypatch.setattr("pds_core.cli.resolve_workspace_root", no_access)
    monkeypatch.setattr("pds_core.classroom_menu_readonly.inspect_classroom_overview", no_access)
    missing = tmp_path / "missing"
    out, err = io.StringIO(), io.StringIO()
    assert run_cli(["--workspace", str(missing), "workspace", "menu"], stdout=out, stderr=err) == 5
    assert out.getvalue() == ""
    assert "interactive session" in err.getvalue()
    assert not missing.exists()


def test_cli_interactive_gate_and_route(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", Terminal("2\n1\nB\nB\nB\n"))
    out, err = Terminal(), io.StringIO()
    assert run_cli(["--workspace", str(root), "workspace", "menu"], stdout=out, stderr=err) == 5
    assert out.getvalue() == "" and "not qualified" in err.getvalue()
    monkeypatch.setattr(
        teacher_experience, "get_teacher_experience_capabilities",
        lambda: frozenset({"classroom.menu.v1", "classroom.roster_edits.v1"}),
    )
    out, err = Terminal(), io.StringIO()
    assert run_cli(["--workspace", str(root), "workspace", "menu"], stdout=out, stderr=err) == 0
    assert "Ari Rivera (ID: 0007)" in out.getvalue()
    assert "Revalidate workspace" in out.getvalue()
    assert err.getvalue() == ""


def test_missing_guarded_edit_capability_refuses(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(teacher_experience, "get_teacher_experience_capabilities", lambda: frozenset({"classroom.menu.v1"}))
    def no_input() -> str:
        raise AssertionError("Incomplete capability set must not prompt")
    result = run_workspace_classroom_menu(
        SharedTeacherMenuRequest("Synthetic", TOKEN, TeacherContextHint(workspace_root=root)),
        read_line=no_input, output=io.StringIO(), interactive=True,
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE


@dataclass(frozen=True)
class Selection:
    workspace: Path
    year: str
    class_id: str
    roster_token: str
    student_id: str
    work_revision: bytes
    allowed: bool


class SyntheticProducer:
    """Fictional caller; its work and permissions are never passed to Core."""

    def __init__(self, root: Path, work: Path) -> None:
        self.root = root
        self.work = work
        self.allowed = True
        self.student_id = "0011"
        self.refreshes = 0
        self.selected = self.reload()
        assert self.selected is not None

    def reload(self) -> Selection | None:
        self.refreshes += 1
        try:
            overview = inspect_classroom_overview(self.root)
            selected = next((c for c in overview.classes if c.class_id == CLASS), None)
            if (
                overview.active_school_year != YEAR or selected is None
                or selected.school_year != YEAR
            ):
                return None
            roster = inspect_classroom_roster(overview.workspace.root, CLASS)
            if self.student_id not in {s.student_id for s in roster.students}:
                return None
            token = _roster_state_token(load_class_roster(overview.workspace.root, CLASS))
            revision = self.work.read_bytes()
        except (OSError, ClassroomDiscoveryError):
            return None
        return Selection(overview.workspace.root, YEAR, CLASS, token, self.student_id, revision, self.allowed)

    def visit(
        self, choices: list[str], *, before: Callable[[], None] | None = None,
        interactive: bool = True,
    ) -> SharedTeacherMenuResult:
        iterator = iter(choices)
        out = io.StringIO()

        def read() -> str:
            choice = next(iterator)
            if before is not None and choice == "B":
                before()
            return choice

        receipt = run_workspace_classroom_menu(
            SharedTeacherMenuRequest("Synthetic ScoreForm", TOKEN, TeacherContextHint(workspace_root=self.root, class_id=CLASS)),
            read_line=read, output=out, interactive=interactive,
        )
        assert TOKEN not in out.getvalue()
        return receipt

    def resume(self, receipt: SharedTeacherMenuResult) -> str:
        if receipt.return_token != TOKEN:
            return "invalid-session"
        fresh = self.reload()
        if fresh is None or fresh != self.selected or not fresh.allowed:
            return "refresh-or-reselect"
        if receipt.durability in (TeacherDurability.PARTIAL, TeacherDurability.INDETERMINATE):
            return "inspect-before-retry"
        if receipt.exit is TeacherMenuExit.QUIT:
            return "caller-quit"
        if receipt.exit is TeacherMenuExit.MAIN_MENU:
            return "caller-main-menu"
        if receipt.exit in (TeacherMenuExit.FAILED, TeacherMenuExit.UNAVAILABLE):
            return "safe-return"
        return "resume-current"


def _producer(root: Path) -> SyntheticProducer:
    work = root.parent / "synthetic-work-revision.txt"
    work.write_bytes(b"revision-1")
    return SyntheticProducer(root, work)


@pytest.mark.parametrize("mutation", ["roster", "year", "workspace", "work", "permission", "student"])
def test_caller_revalidates_even_no_change(
    root: Path, qualified: None, mutation: str,
) -> None:
    producer = _producer(root)
    def interfere() -> None:
        if mutation == "roster":
            changed = _rows()
            changed[0]["period"] = "3"
            write_class_roster(root, create_roster(CLASS, changed), overwrite=True)
        elif mutation == "student":
            write_class_roster(root, create_roster(CLASS, _rows()[:1]), overwrite=True)
        elif mutation == "year":
            close_school_year(root, closed_at=END)
        elif mutation == "workspace":
            producer.root = root.parent / "another-workspace"
        elif mutation == "work":
            producer.work.write_bytes(b"revision-2")
        else:
            producer.allowed = False
    receipt = producer.visit(["B"], before=interfere)
    assert receipt.durability is TeacherDurability.NO_CHANGE
    assert not receipt.change_scopes
    assert producer.resume(receipt) == "refresh-or-reselect"
    assert producer.refreshes == 2
    assert producer.work.read_bytes() == (b"revision-2" if mutation == "work" else b"revision-1")


def test_committed_removal_refuses_stale_caller_selection(root: Path, qualified: None) -> None:
    producer = _producer(root)
    receipt = producer.visit(["2", "1", "2", "R", "C"])
    assert receipt.durability is TeacherDurability.COMMITTED
    assert receipt.change_scopes == frozenset({TeacherChangeScope.ROSTER})
    assert producer.resume(receipt) == "refresh-or-reselect"
    assert producer.work.read_bytes() == b"revision-1"


def test_unavailable_return_also_requires_refresh(root: Path) -> None:
    producer = _producer(root)
    receipt = producer.visit([], interactive=False)
    producer.allowed = False
    assert receipt.exit is TeacherMenuExit.UNAVAILABLE
    assert producer.resume(receipt) == "refresh-or-reselect"
    assert producer.refreshes == 2


@pytest.mark.parametrize("choice, expected", [("B", "resume-current"), ("M", "caller-main-menu"), ("Q", "caller-quit")])
def test_fresh_caller_navigation(root: Path, qualified: None, choice: str, expected: str) -> None:
    producer = _producer(root)
    assert producer.resume(producer.visit([choice])) == expected
    assert producer.refreshes == 2
    assert producer.work.read_bytes() == b"revision-1"
