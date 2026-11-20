"""Workspace-native Notes write service tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import pds_core.notes_service as service
import pds_core.workspace as workspace
from pds_core.notes_records import MAX_SERIALIZED_BYTES, encode_note, new_note
from pds_core.notes_storage import (
    NotesConflictError,
    NotesReadError,
    get_note,
    list_notes,
    notes_dir,
)


def test_resolver_precedence_and_switching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    default = tmp_path / "default"
    saved = tmp_path / "saved"
    env = tmp_path / "env"
    explicit = tmp_path / "explicit"
    for root in (saved, env, explicit):
        root.mkdir()
    config = tmp_path / "workspace-config.json"
    config.write_text(json.dumps({"workspace_root": str(saved)}), encoding="utf-8")
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config)
    monkeypatch.setattr(workspace, "get_default_workspace_root", lambda: default)
    monkeypatch.delenv("PDS_WORKSPACE_ROOT", raising=False)
    first = service.create_note("idea", "Saved")
    assert get_note(first.note_id).text == "Saved"
    monkeypatch.setenv("PDS_WORKSPACE_ROOT", str(env))
    assert list_notes() == ()
    second = service.create_note("task", "Environment")
    assert get_note(second.note_id).text == "Environment"
    third = service.create_note("reflection", "Explicit", workspace_root=explicit)
    assert get_note(third.note_id, explicit).text == "Explicit"
    assert list_notes(saved) == (first,)
    assert list_notes(env) == (second,)
    assert not default.exists()


def test_directory_only_created_on_commit(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert list_notes(root) == ()
    assert not (root / ".pds").exists()
    with pytest.raises(ValueError):
        service.create_note("idea", " ", workspace_root=root)
    assert not (root / ".pds").exists()
    note = service.create_note("idea", "Ready", workspace_root=root)
    assert notes_dir(root).is_dir()
    assert get_note(note.note_id, root) == note


def test_missing_default_workspace_is_never_initialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "default"
    config = tmp_path / "absent-config.json"
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config)
    monkeypatch.setattr(workspace, "get_default_workspace_root", lambda: missing)
    monkeypatch.delenv("PDS_WORKSPACE_ROOT", raising=False)
    with pytest.raises(NotesReadError):
        service.create_note("idea", "No selected workspace")
    assert not missing.exists()


def test_task_revision_lifecycle_and_archive(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    task = service.create_note("task", "Plan", workspace_root=root)
    task = service.edit_note(
        task.note_id, "Plan lesson", expected_revision=1, workspace_root=root
    )
    assert task.revision == 2
    task = service.set_task_completed(
        task.note_id, True, expected_revision=2, workspace_root=root
    )
    assert task.completed and task.revision == 3
    task = service.set_task_completed(
        task.note_id, False, expected_revision=3, workspace_root=root
    )
    assert not task.completed
    task = service.set_archived(
        task.note_id, True, expected_revision=4, workspace_root=root
    )
    assert list_notes(root) == ()
    assert list_notes(root, include_archived=True) == (task,)
    task = service.set_archived(
        task.note_id, False, expected_revision=5, workspace_root=root
    )
    assert list_notes(root) == (task,)
    with pytest.raises(service.StaleNoteError):
        service.edit_note(
            task.note_id, "Stale", expected_revision=1, workspace_root=root
        )
    assert get_note(task.note_id, root) == task
    idea = service.create_note("idea", "Thought", workspace_root=root)
    with pytest.raises(service.NotesWriteError):
        service.set_task_completed(
            idea.note_id, True, expected_revision=1, workspace_root=root
        )


def test_create_collision_does_not_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    first = service.create_note("idea", "Original", workspace_root=root)
    original = (notes_dir(root) / f"{first.note_id}.json").read_bytes()
    monkeypatch.setattr(service, "new_note", lambda *args, **kwargs: first)
    with pytest.raises(service.NoteAlreadyExistsError):
        service.create_note("idea", "Different", workspace_root=root)
    assert (notes_dir(root) / f"{first.note_id}.json").read_bytes() == original


def test_replace_failure_keeps_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    first = service.create_note("task", "Original", workspace_root=root)
    target = notes_dir(root) / f"{first.note_id}.json"
    original = target.read_bytes()

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(service.os, "replace", fail_replace)
    with pytest.raises(service.NotesWriteError):
        service.edit_note(
            first.note_id, "Revised", expected_revision=1, workspace_root=root
        )
    assert target.read_bytes() == original
    assert get_note(first.note_id, root) == first


def test_sync_conflict_and_malformed_bytes_refuse_writes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    first = service.create_note("task", "Original", workspace_root=root)
    target = notes_dir(root) / f"{first.note_id}.json"
    conflict = notes_dir(root) / f"{first.note_id} (PC conflicted copy).json"
    conflict.write_bytes(target.read_bytes())
    with pytest.raises(NotesConflictError):
        service.edit_note(
            first.note_id, "Revised", expected_revision=1, workspace_root=root
        )
    assert conflict.is_file()
    conflict.unlink()
    target.write_bytes(b"x" * (MAX_SERIALIZED_BYTES + 1))
    with pytest.raises(NotesReadError):
        service.edit_note(
            first.note_id, "Revised", expected_revision=1, workspace_root=root
        )
    assert target.stat().st_size == MAX_SERIALIZED_BYTES + 1
    other = new_note("idea", "Other")
    target.write_text(encode_note(other), encoding="utf-8")
    with pytest.raises(NotesReadError):
        service.create_note("task", "New", workspace_root=root)
    assert target.read_text(encoding="utf-8") == encode_note(other)


def test_same_revision_changed_bytes_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    first = service.create_note("task", "Original", workspace_root=root)
    target = notes_dir(root) / f"{first.note_id}.json"
    old_bytes = target.read_bytes()
    original_lock = service._local_write_lock

    from contextlib import contextmanager
    from typing import Iterator

    @contextmanager
    def changed_lock(directory: Path) -> Iterator[None]:
        with original_lock(directory):
            obj = json.loads(old_bytes)
            obj["text"] = "Other computer"
            target.write_text(json.dumps(obj), encoding="utf-8")
            yield

    monkeypatch.setattr(service, "_local_write_lock", changed_lock)
    with pytest.raises(service.StaleNoteError):
        service.edit_note(
            first.note_id, "My edit", expected_revision=1, workspace_root=root
        )
    assert get_note(first.note_id, root).text == "Other computer"


def test_link_escape_refused(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".pds" / "notes").mkdir(parents=True)
    try:
        (root / ".pds" / "notes" / "v1").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(NotesReadError):
        service.create_note("idea", "No escape", workspace_root=root)
    assert tuple(outside.iterdir()) == ()


@pytest.mark.skipif(os.name != "nt", reason="Windows-only create collision behavior")
def test_windows_hardlink_create_is_exclusive(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = service.create_note("idea", "Windows", workspace_root=root)
    assert get_note(note.note_id, root) == note


def test_same_revision_sync_change_between_preliminary_reads_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Do not lose a change arriving after the first record read."""
    from dataclasses import replace

    root = tmp_path / "workspace"
    root.mkdir()
    note = service.create_note("task", "Original", workspace_root=root)
    target = notes_dir(root) / f"{note.note_id}.json"
    underlying_get_note = service.get_note
    first = True

    def read_then_sync(note_id: str, workspace_root: Path) -> object:
        nonlocal first
        result = underlying_get_note(note_id, workspace_root)
        if first:
            first = False
            target.write_text(
                encode_note(replace(result, text="Another computer")),
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(service, "get_note", read_then_sync)
    with pytest.raises(service.StaleNoteError):
        service.edit_note(
            note.note_id, "My edit", expected_revision=1, workspace_root=root
        )
    assert underlying_get_note(note.note_id, root).text == "Another computer"


def test_failed_stage_flush_removes_own_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A handled failure must not leave a temp file that blocks all Notes."""
    root = tmp_path / "workspace"
    root.mkdir()

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("simulated flush failure")

    monkeypatch.setattr(service.os, "fsync", fail_fsync)
    with pytest.raises(service.NotesWriteError):
        service.create_note("idea", "First note", workspace_root=root)

    assert tuple(notes_dir(root).iterdir()) == ()
    assert list_notes(root) == ()
