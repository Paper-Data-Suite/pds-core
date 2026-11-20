"""Core #240-B: teacher-facing Notes workflows over the real #239 service."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

import pds_core.notes_menu_controller as controller
import pds_core.teacher_menus as menus
from pds_core.notes_service import NotesWriteError, StaleNoteError, create_note
from pds_core.notes_storage import get_note, list_notes, notes_dir
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
    TeacherWorkReference,
)


def _call(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    choices: list[str],
    *,
    context: TeacherContextHint | None = None,
) -> tuple[SharedTeacherMenuResult, str]:
    monkeypatch.setattr(menus, "_NOTES_MENU_QUALIFIED", True)
    output = io.StringIO()
    values = iter(choices)
    request = SharedTeacherMenuRequest(
        "Quillan", "opaque-caller-token", context or TeacherContextHint(root)
    )
    result = menus.run_notes_tasks_menu(
        request,
        read_line=lambda: next(values),
        output=output,
        interactive=True,
    )
    assert result.return_token == "opaque-caller-token"
    assert "opaque-caller-token" not in output.getvalue()
    return result, output.getvalue()


def test_empty_root_is_failure_not_empty_notebook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "not-a-workspace"
    result, text = _call(monkeypatch, missing, [])
    assert result.exit is TeacherMenuExit.FAILED
    assert "workspace" in text.lower()
    assert not missing.exists()


def test_opening_and_back_do_not_create_note_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    result, output = _call(monkeypatch, root, ["B\n"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "Quick Capture" in output
    assert not notes_dir(root).exists()


def test_quick_capture_preserves_literal_nav_and_colon_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    result, output = _call(
        monkeypatch,
        root,
        ["1\n", "1\n", "Planning", ":notes\n", "B\n", "M\n", "Q\n", ":save\n", "B\n"],
    )
    records = list_notes(root)
    assert len(records) == 1
    assert records[0].category == "idea"
    assert records[0].text == "Planning\n:notes\nB\nM\nQ"
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.NOTES})
    assert "Saved." in output


def test_quick_capture_cancel_does_not_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    result, _ = _call(monkeypatch, root, ["1", "3", "unfinished", ":cancel", "B"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not notes_dir(root).exists()


def test_attach_explicit_nonstudent_context_and_complete_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    hint = TeacherContextHint(
        workspace_root=root,
        class_id="English12_P2",
        work=TeacherWorkReference("quillan", "assignment", "Essay1"),
        display_label="English 12 work",
    )
    result, _ = _call(
        monkeypatch,
        root,
        ["1", "2", "y", "Revise model essay", ":save", "2", "1", "2", "B", "B", "B"],
        context=hint,
    )
    task = list_notes(root)[0]
    assert task.completed is True
    assert task.revision == 2
    assert task.context is not None
    assert task.context.module_id == "quillan"
    assert task.context.class_id == "English12_P2"
    assert task.context.work_id == "Essay1"
    assert result.durability is TeacherDurability.COMMITTED


def test_back_from_context_confirmation_returns_to_category(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    hint = TeacherContextHint(workspace_root=root, class_id="English12")
    result, transcript = _call(
        monkeypatch, root, ["1", "1", "B", "B", "B"], context=hint
    )
    assert result.exit is TeacherMenuExit.BACK
    assert transcript.count("Quick Capture") >= 2
    assert not notes_dir(root).exists()


def test_edit_archive_and_unarchive_are_revision_guarded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    original = create_note("reflection", "Original", workspace_root=root)
    result, _ = _call(
        monkeypatch,
        root,
        [
            "3",
            "1",
            "1",
            "Revised",
            ":save",
            "3",
            "y",
            "B",
            "B",
            "5",
            "1",
            "3",
            "y",
            "B",
            "B",
            "B",
        ],
    )
    saved = get_note(original.note_id, root)
    assert saved.text == "Revised"
    assert saved.archived is False
    assert saved.revision == 4
    assert result.durability is TeacherDurability.COMMITTED


def test_search_and_category_context_filters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    create_note("idea", "shared phrase", workspace_root=root)
    create_note("reflection", "shared phrase", workspace_root=root)
    result, transcript = _call(
        monkeypatch,
        root,
        [
            "4",
            "shared phrase",
            "F",
            "reflection",
            "all",
            "*",
            "*",
            "*",
            "1",
            "B",
            "B",
            "B",
        ],
    )
    assert result.exit is TeacherMenuExit.BACK
    assert "Reflection Detail" in transcript
    assert "Idea Detail" not in transcript


def test_stale_update_refuses_without_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = create_note("reflection", "Original", workspace_root=root)

    def stale(*_args: object, **_kwargs: object) -> object:
        raise StaleNoteError("confidential internal error")

    monkeypatch.setattr(controller, "edit_note", stale)
    result, transcript = _call(
        monkeypatch, root, ["3", "1", "1", "Revised", ":save", "B", "B"]
    )
    assert get_note(note.note_id, root).text == "Original"
    assert "confidential internal error" not in transcript
    assert "changed elsewhere" in transcript
    assert result.durability is TeacherDurability.NO_CHANGE


def test_sync_conflict_preserved_and_teacher_warned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = create_note("task", "Work", workspace_root=root)
    conflict = notes_dir(root) / f"{note.note_id} (PC conflicted copy).json"
    conflict.write_bytes((notes_dir(root) / f"{note.note_id}.json").read_bytes())
    result, transcript = _call(monkeypatch, root, [])
    assert result.exit is TeacherMenuExit.FAILED
    assert "sync-conflicted" in transcript
    assert conflict.exists()


@pytest.mark.parametrize(
    "choice,expected", [("M", TeacherMenuExit.MAIN_MENU), ("Q", TeacherMenuExit.QUIT)]
)
def test_exit_disposition_from_nested_menu_choice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    choice: str,
    expected: TeacherMenuExit,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    result, _ = _call(monkeypatch, root, ["1", choice])
    assert result.exit is expected


def test_eof_after_confirmed_save_reports_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    result, _ = _call(monkeypatch, root, ["1", "1", "Saved idea", ":save"])
    assert result.exit is TeacherMenuExit.CANCELLED
    assert result.durability is TeacherDurability.COMMITTED
    assert len(list_notes(root)) == 1


def test_noninteractive_never_reads_even_with_test_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(menus, "_NOTES_MENU_QUALIFIED", True)
    root = tmp_path / "workspace"
    root.mkdir()
    result = menus.run_notes_tasks_menu(
        SharedTeacherMenuRequest("Core", "token", TeacherContextHint(root)),
        read_line=lambda: (_ for _ in ()).throw(AssertionError("read")),
        output=io.StringIO(),
        interactive=False,
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert not notes_dir(root).exists()


def test_reopen_completed_task_from_archived_completed_view(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    task = create_note("task", "File quiz handouts", workspace_root=root)
    first, _ = _call(monkeypatch, root, ["2", "1", "2", "B", "B", "B"])
    assert first.durability is TeacherDurability.COMMITTED
    second, _ = _call(monkeypatch, root, ["5", "1", "2", "B", "B", "B"])
    assert second.durability is TeacherDurability.COMMITTED
    assert get_note(task.note_id, root).completed is False


def test_failed_save_retains_visible_draft_and_no_false_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise NotesWriteError("sensitive internal detail")

    monkeypatch.setattr(controller, "create_note", unavailable)
    result, transcript = _call(
        monkeypatch, root, ["1", "1", "Teacher draft to recover", ":save", "B"]
    )
    assert result.durability is TeacherDurability.INDETERMINATE
    assert "Teacher draft to recover" in transcript
    assert "sensitive internal detail" not in transcript
    assert not (notes_dir(root) / "missing.json").exists()


def test_notes_with_terminal_controls_are_sanitized_in_display(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    create_note("idea", "Line with ESC:\x1b[31mred and text", workspace_root=root)
    result, transcript = _call(monkeypatch, root, ["3", "1", "B", "B", "B"])
    assert result.exit is TeacherMenuExit.BACK
    assert "\x1b[" not in transcript
    assert "red and text" in transcript
