"""Final review: terminal failure must not erase a canonical mutation receipt."""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.roster_imports as imports
import pds_core.workspace as workspace
from pds_core.class_metadata import (
    create_class_metadata,
    load_class_metadata_for_class,
    write_class_metadata_for_class,
)
from pds_core.classes import load_class_roster, write_class_roster
from pds_core.rosters import Roster, RosterWriteError, _write_roster_unlocked, create_roster, write_roster
from pds_core.routes import class_dir, class_roster_path
from pds_core.school_years import load_school_year_state, open_school_year
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    load_standards_library,
    standards_library_path,
    write_standards_library,
)
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
START = datetime(2026, 9, 8, 8, tzinfo=timezone.utc)
CLASS = "english12_p2"
NEW_CLASS = "english12_p3"
TOKEN = "synthetic-output-failure-token"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: tmp_path / "config" / "config.json")
    monkeypatch.setattr(workspace, "get_default_workspace_root", lambda: tmp_path / "default")
    monkeypatch.delenv(workspace.WORKSPACE_ROOT_ENV_VAR, raising=False)
    folder = tmp_path / "workspace"
    folder.mkdir()
    return folder


def _row(student_id: str) -> dict[str, str]:
    return {"student_id": student_id, "first_name": "Ari", "last_name": "Rivera", "period": "2"}


def _seed_class(root: Path) -> None:
    open_school_year(root, YEAR, opened_at=START)
    write_class_metadata_for_class(root, create_class_metadata(CLASS, YEAR, created_at=START))


def _candidate(root: Path) -> Path:
    path = root.parent / "candidate.csv"
    write_roster(path, create_roster(CLASS, [_row("0007")]))
    return path


def _invoke(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    failure: type[BaseException],
) -> SharedTeacherMenuResult:
    out, err = io.StringIO(), io.StringIO()
    iterator = iter(answers)

    def fail(*args: object, **kwargs: object) -> int:
        raise failure("synthetic terminal failure")

    def read() -> str:
        answer = next(iterator)
        if answer == "C":
            # All review output succeeded; only post-confirmation output fails.
            monkeypatch.setattr(out, "write", fail)
            monkeypatch.setattr(err, "write", fail)
        return answer

    receipt = run_workspace_classroom_menu(
        SharedTeacherMenuRequest("Synthetic", TOKEN, TeacherContextHint(workspace_root=root)),
        read_line=read, output=out, error_output=err, interactive=True,
    )
    assert receipt.return_token == TOKEN
    assert TOKEN not in out.getvalue() + err.getvalue()
    assert "Revalidate workspace" in receipt.message
    return receipt


@pytest.mark.parametrize("failure", [OSError, ValueError, KeyboardInterrupt])
@pytest.mark.parametrize("operation", ["workspace", "year", "class", "standards", "import", "student"])
def test_successful_write_receipt_survives_terminal_failure(
    root: Path, monkeypatch: pytest.MonkeyPatch, operation: str, failure: type[BaseException],
) -> None:
    target = root.parent / "new-workspace"
    if operation == "workspace":
        answers = ["4", "1", str(target), "C"]
        scope = TeacherChangeScope.WORKSPACE
    elif operation == "year":
        answers = ["5", "1", YEAR, START.isoformat(), "C"]
        scope = TeacherChangeScope.SCHOOL_YEAR
    elif operation == "class":
        _seed_class(root)
        answers = ["6", NEW_CLASS, START.isoformat(), "C"]
        scope = TeacherChangeScope.CLASS
    elif operation == "standards":
        write_standards_library(
            standards_library_path(root),
            StandardsLibrary(
                standards=(
                    StandardDefinition("synthetic:one", "ONE", "Synthetic", "One", "First standard"),
                    StandardDefinition("synthetic:two", "TWO", "Synthetic", "Two", "Second standard"),
                ),
                profiles=(StandardsProfile("english12", ("synthetic:one",), title="English 12"),),
            ),
        )
        answers = ["3", "3", "1", "english12", "synthetic:two", "C"]
        scope = TeacherChangeScope.STANDARDS
    elif operation == "import":
        _seed_class(root)
        answers = ["2", "1", "I", str(_candidate(root)), "C"]
        scope = TeacherChangeScope.ROSTER
    else:
        _seed_class(root)
        write_class_roster(root, create_roster(CLASS, [_row("0007")]))
        answers = ["2", "1", "1", "E", "period", "3", "DONE", "C"]
        scope = TeacherChangeScope.ROSTER

    receipt = _invoke(root, monkeypatch, answers, failure)
    assert receipt.exit is TeacherMenuExit.BACK
    assert receipt.durability is TeacherDurability.COMMITTED
    assert receipt.change_scopes == frozenset({scope})

    if operation == "workspace":
        assert workspace.load_workspace_config().workspace_root == target.resolve()
        assert (target / ".pds" / "workspace.json").is_file()
    elif operation == "year":
        state = load_school_year_state(root)
        assert state is not None and state.opened_at == START
    elif operation == "class":
        assert load_class_metadata_for_class(root, NEW_CLASS).created_at == START
        assert not class_roster_path(root, NEW_CLASS).exists()
    elif operation == "standards":
        assert load_standards_library(standards_library_path(root)).profiles[0].standards == ("synthetic:one", "synthetic:two")
    elif operation == "import":
        assert load_class_roster(root, CLASS).students[0].student_id == "0007"
    else:
        assert load_class_roster(root, CLASS).students[0].period == "3"


def test_uncertain_roster_receipt_survives_failed_error_stream(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_class(root)
    candidate = _candidate(root)

    def write_then_fail(path: str | Path, roster: Roster, *, overwrite: bool = False) -> None:
        _write_roster_unlocked(path, roster, overwrite=overwrite)
        raise RosterWriteError(path, "private injected detail")

    monkeypatch.setattr(imports, "_write_roster_unlocked", write_then_fail)
    receipt = _invoke(root, monkeypatch, ["2", "1", "I", str(candidate), "C"], OSError)
    assert receipt.exit is TeacherMenuExit.FAILED
    assert receipt.durability is TeacherDurability.INDETERMINATE
    assert receipt.change_scopes == frozenset({TeacherChangeScope.ROSTER})
    assert load_class_roster(root, CLASS).students[0].student_id == "0007"


def test_partial_class_receipt_survives_failed_error_stream(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_class(root)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("private injected failure")

    monkeypatch.setattr(os, "link", fail)
    receipt = _invoke(root, monkeypatch, ["6", NEW_CLASS, START.isoformat(), "C"], OSError)
    assert receipt.exit is TeacherMenuExit.FAILED
    assert receipt.durability is TeacherDurability.PARTIAL
    assert receipt.change_scopes == frozenset({TeacherChangeScope.CLASS})
    assert class_dir(root, NEW_CLASS).is_dir()
