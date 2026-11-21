"""Core #240-D: real menu entry, safe return, and script CLI parity."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from pds_core import cli, core_menu
from pds_core.notes_service import create_note
from pds_core.notes_storage import get_note, list_notes, notes_dir
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    TeacherChangeScope,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_menus import run_notes_tasks_menu


def _core(root: Path, commands: str) -> tuple[int, str, str]:
    output, errors = io.StringIO(), io.StringIO()
    code = core_menu._run(
        ["--workspace", str(root)],
        stdin=io.StringIO(commands),
        stdout=output,
        stderr=errors,
    )
    return code, output.getvalue(), errors.getvalue()


def test_core_menu_preserves_old_exit_and_adds_notes_without_writing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    code, output, errors = _core(root, "4\n")
    assert code == 0 and errors == ""
    assert "1. Standards Management" in output
    assert "2. Workspace Settings" in output
    assert "3. Help" in output
    assert "4. Exit" in output
    assert "5. Notes & Tasks" in output
    assert not notes_dir(root).exists()


@pytest.mark.parametrize("invocation", ["5", " :NoTeS "])
def test_enter_notes_and_return_to_exact_core_main_menu(
    tmp_path: Path, invocation: str
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    code, output, errors = _core(root, f"{invocation}\nB\n4\n")
    assert code == 0 and errors == ""
    assert "Notes & Tasks" in output
    assert output.count("Main Menu") >= 2
    assert not notes_dir(root).exists()
    assert "\x1b[" not in output


def test_core_capture_preserves_literal_commands_and_returns(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    code, output, errors = _core(
        root,
        "5\n1\n1\nPlan fictional discussion\n:notes\nB\n:save\nB\n4\n",
    )
    assert code == 0 and errors == ""
    notes = list_notes(root)
    assert len(notes) == 1
    assert notes[0].text == "Plan fictional discussion\n:notes\nB"
    assert "Saved." in output
    assert "core-main-menu-notes" not in output


def test_core_notes_main_menu_disposition_returns_to_core_menu(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    code, output, errors = _core(root, "5\nM\n4\n")
    assert code == 0 and errors == ""
    assert output.count("Main Menu") >= 2
    assert not notes_dir(root).exists()


def test_core_notes_quit_returns_without_requiring_extra_input(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    code, output, errors = _core(root, "5\nQ\n")
    assert code == 0 and errors == ""
    assert "Notes & Tasks" in output
    assert not notes_dir(root).exists()


def test_core_conflicted_workspace_is_not_called_empty(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = create_note("task", "Fictional Task", workspace_root=root)
    original = notes_dir(root) / f"{note.note_id}.json"
    conflict = notes_dir(root) / f"{note.note_id} (PC conflicted copy).json"
    conflict.write_bytes(original.read_bytes())
    code, output, errors = _core(root, "5\n\n4\n")
    assert code == 0 and errors == ""
    assert "sync-conflicted" in output
    assert "No Notes yet" not in output
    assert original.exists() and conflict.exists()


def test_synthetic_caller_round_trip_reports_durable_task_without_private_token(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    out = io.StringIO()
    stream = iter(["1", "2", "synthetic follow-up", ":save", "B"])
    result = run_notes_tasks_menu(
        SharedTeacherMenuRequest(
            caller_application="Fictional Producer",
            return_token="caller-owned-screen-17",
            context=TeacherContextHint(workspace_root=root),
        ),
        read_line=lambda: next(stream),
        output=out,
        interactive=True,
    )
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.NOTES})
    assert result.return_token == "caller-owned-screen-17"
    assert "caller-owned-screen-17" not in out.getvalue()
    notes = list_notes(root)
    assert len(notes) == 1 and notes[0].category == "task"


def test_cli_archived_task_never_appears_as_open_even_with_include_archived(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = create_note("task", "Fictional hidden task", workspace_root=root)
    from pds_core.notes_service import set_archived

    set_archived(
        note.note_id, True, expected_revision=note.revision, workspace_root=root
    )
    output, errors = io.StringIO(), io.StringIO()
    status = cli._run(
        [
            "--workspace",
            str(root),
            "notes",
            "list",
            "--status",
            "open",
            "--include-archived",
            "--format",
            "json",
        ],
        stdout=output,
        stderr=errors,
    )
    assert status == 0 and errors.getvalue() == ""
    result: object = json.loads(output.getvalue())
    assert isinstance(result, dict)
    assert result.get("count") == 0
    assert get_note(note.note_id, root).archived


def test_core_to_notes_clear_and_back_render_only_current_menu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pds_core.cli_support import screen

    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(screen, "clear_screen", lambda stream: stream.write("\f"))
    code, transcript, errors = _core(root, "5\n1\n1\nSynthetic note\n:save\nB\n4\n")
    screens = [part for part in transcript.split("\f") if part.strip()]
    titles = []
    for part in screens:
        lines = part.splitlines()
        titles.append(lines[2] if lines[1] == "" else lines[1])
    assert titles == [
        "Main Menu",
        "Notes & Tasks",
        "Quick Capture",
        "New Idea",
        "Notes & Tasks",
        "Main Menu",
    ]
    assert "Saved. Find it" in screens[4]
    assert "Quick Capture" not in screens[-1]
    assert errors == "" and code == 0
