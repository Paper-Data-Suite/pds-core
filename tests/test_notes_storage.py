"""Nonmutating workspace-native Notes reader tests (Core #239)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pds_core.notes_records import encode_note, new_note
from pds_core.notes_storage import (
    NoteNotFoundError,
    NotesConflictError,
    NotesReadError,
    get_note,
    list_notes,
    notes_dir,
    search_notes,
)


def test_resolves_existing_selected_workspace_without_creating_anything(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected = tmp_path / "OneDrive - School" / "PDS"
    selected.mkdir(parents=True)
    monkeypatch.setenv("PDS_WORKSPACE_ROOT", str(selected))
    before = tuple(selected.rglob("*"))
    assert notes_dir() == selected.resolve() / ".pds" / "notes" / "v1"
    assert list_notes() == ()
    assert tuple(selected.rglob("*")) == before


def test_missing_workspace_is_error_not_empty(tmp_path: Path) -> None:
    with pytest.raises(NotesReadError):
        list_notes(tmp_path / "missing")


def _write_note(workspace: Path, text: str = "Review lessons") -> str:
    note = new_note("task", text)
    dest = notes_dir(workspace)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{note.note_id}.json").write_text(encode_note(note), encoding="utf-8")
    return note.note_id


def test_same_record_visible_from_two_consumers(tmp_path: Path) -> None:
    workspace_root = tmp_path / "PDS shared workspace"
    workspace_root.mkdir()
    note_id = _write_note(workspace_root)
    from_first = list_notes(workspace_root)
    from_second = get_note(note_id, workspace_root)
    assert len(from_first) == 1
    assert from_first[0] == from_second
    assert search_notes("LESSONS", workspace_root) == (from_second,)


def test_preserves_real_note_and_blocks_a_conflict_copy(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note_id = _write_note(root)
    conflict = notes_dir(root) / f"{note_id} (Laptop's conflicted copy).json"
    conflict.write_text("This is important, preserve it", encoding="utf-8")
    with pytest.raises(NotesConflictError):
        list_notes(root)
    with pytest.raises(NotesConflictError):
        get_note(note_id, root)
    assert conflict.exists()
    assert len(tuple(notes_dir(root).iterdir())) == 2


def test_corrupt_json_or_mismatched_filename_is_not_empty(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note_id = _write_note(root)
    file = notes_dir(root) / f"{note_id}.json"
    obj = json.loads(file.read_text(encoding="utf-8"))
    obj["note_id"] = new_note("idea", "Somewhere else").note_id
    file.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(NotesReadError):
        list_notes(root)
    file.write_text("{not JSON", encoding="utf-8")
    with pytest.raises(NotesReadError):
        get_note(note_id, root)


def test_archived_note_hidden_by_default(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note_id = _write_note(root)
    note = get_note(note_id, root)
    file = notes_dir(root) / f"{note_id}.json"
    file.write_text(encode_note(replace(note, archived=True)), encoding="utf-8")
    assert list_notes(root) == ()
    assert len(list_notes(root, include_archived=True)) == 1


def test_rejects_linked_notes_dir(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    (root / ".pds" / "notes").mkdir(parents=True)
    try:
        (root / ".pds" / "notes" / "v1").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable to this account")
    with pytest.raises(NotesReadError):
        list_notes(root)


def test_unexpected_directory_and_missing_note(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note_id = _write_note(root)
    with pytest.raises(NoteNotFoundError):
        get_note(new_note("idea", "Other").note_id, root)
    (notes_dir(root) / "unexpected-folder").mkdir()
    with pytest.raises(NotesReadError):
        list_notes(root)
    assert (notes_dir(root) / f"{note_id}.json").exists()
