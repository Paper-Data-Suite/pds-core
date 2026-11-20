"""Guarded local writes for Notes in the selected PDS workspace.

The lock serializes writers on one computer. File sync is not a distributed
transaction: a later conflict copy requires manual review.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from pds_core.notes_records import (
    MAX_SERIALIZED_BYTES,
    NoteCategory,
    NoteContext,
    NoteRecord,
    NoteValidationError,
    decode_note,
    encode_note,
    new_note,
)
from pds_core.notes_storage import (
    NotesConflictError,
    NotesReadError,
    _CANONICAL_FILE,
    _notes_collection,
    get_note,
    list_notes,
    notes_dir,
)
from pds_core.workspace import resolve_workspace_root


class NotesWriteError(RuntimeError):
    """A Note could not be committed; inspect the workspace and retry safely."""


class StaleNoteError(NotesWriteError):
    """The Note changed since it was read; reload before editing."""


class NoteAlreadyExistsError(NotesWriteError):
    """The new Note ID already exists; its contents were preserved."""


@contextmanager
def _local_write_lock(directory: Path) -> Iterator[None]:
    """Serialize local processes without placing a lock file in the sync tree."""
    digest = hashlib.sha256(os.fsencode(directory)).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"pds-core-notes-{digest}.lock"
    try:
        with lock_path.open("a+b") as stream:
            if os.name == "nt":
                msvcrt = importlib.import_module("msvcrt")

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise NotesWriteError("Cannot lock Notes for a local save.") from exc


def _ensure_directory(workspace_root: str | Path | None) -> Path:
    directory = _notes_collection(workspace_root)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise NotesWriteError(
            "Cannot create Notes directory in selected workspace."
        ) from exc
    return _notes_collection(workspace_root)


def _check_inventory(directory: Path, own_temp: Path | None = None) -> None:
    """Refuse ambiguous sync evidence, including a different writer's temp."""
    try:
        for entry in directory.iterdir():
            if own_temp is not None and entry == own_temp:
                continue
            if entry.is_symlink() or not entry.is_file():
                raise NotesConflictError("Notes directory needs manual review.")
            if _CANONICAL_FILE.fullmatch(entry.name) is None:
                raise NotesConflictError("Notes directory needs manual review.")
    except OSError as exc:
        raise NotesReadError("Cannot inspect workspace Notes.") from exc


def _bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_SERIALIZED_BYTES + 1)
    except OSError as exc:
        raise NotesReadError("Cannot recheck workspace Note before save.") from exc
    if len(raw) > MAX_SERIALIZED_BYTES:
        raise NotesReadError("Workspace Note exceeds its file-size limit.")
    return raw


def _stage(directory: Path, note: NoteRecord) -> Path:
    raw = encode_note(note).encode("utf-8")
    staged: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".note-", suffix=".tmp", dir=directory
        )
        staged = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None  # The stream now owns and closes the descriptor.
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return staged
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if staged is not None:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                pass
        raise NotesWriteError("Cannot stage Note in selected workspace.") from exc


def _commit(
    note: NoteRecord,
    workspace_root: str | Path | None,
    *,
    expected_revision: int | None,
    expected_bytes: bytes | None = None,
) -> NoteRecord:
    directory = notes_dir(workspace_root)
    with _local_write_lock(directory):
        if expected_revision is None:
            # A read cannot initialize any directory. Check the existing tree
            # before the first commit, then create only inside this save path.
            list_notes(workspace_root, include_archived=True)
            directory = _ensure_directory(workspace_root)
        else:
            directory = _notes_collection(workspace_root)
        list_notes(workspace_root, include_archived=True)
        target = directory / f"{note.note_id}.json"
        original: bytes | None = None
        if expected_revision is None:
            if target.exists() or target.is_symlink():
                raise NoteAlreadyExistsError("Note ID already exists; retry creation.")
        else:
            current = get_note(note.note_id, workspace_root)
            if current.revision != expected_revision:
                raise StaleNoteError("Note changed; reload before saving.")
            original = _bytes(target)
            if original != expected_bytes:
                raise StaleNoteError("Note bytes changed; reload before saving.")
        staged = _stage(directory, note)
        try:
            _check_inventory(directory, staged)
            if expected_revision is None:
                try:
                    os.link(staged, target)
                except FileExistsError as exc:
                    raise NoteAlreadyExistsError(
                        "Note ID already exists; retry creation."
                    ) from exc
            else:
                if _bytes(target) != original:
                    raise StaleNoteError("Note changed; reload before saving.")
                os.replace(staged, target)
        except OSError as exc:
            raise NotesWriteError(
                "Cannot commit Note; inspect workspace and retry."
            ) from exc
        finally:
            staged.unlink(missing_ok=True)
    return note


def create_note(
    category: NoteCategory,
    text: str,
    *,
    context: NoteContext | None = None,
    workspace_root: str | Path | None = None,
) -> NoteRecord:
    """Create one new Note; never overwrite an existing ID."""
    root = resolve_workspace_root(workspace_root)
    return _commit(
        new_note(category, text, context=context),
        root,
        expected_revision=None,
    )


def _change(
    note_id: str,
    expected_revision: int,
    workspace_root: str | Path | None,
    *,
    text: str | None = None,
    completed: bool | None = None,
    archived: bool | None = None,
) -> NoteRecord:
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError("expected_revision must be a positive integer")
    workspace_root = resolve_workspace_root(workspace_root)
    # Read under the lock in _commit as well; this preliminary read only forms
    # the candidate and cannot authorize a write.
    old = get_note(note_id, workspace_root)
    if old.revision != expected_revision:
        raise StaleNoteError("Note changed; reload before saving.")
    original = _bytes(notes_dir(workspace_root) / f"{note_id}.json")
    # The preliminary record and byte snapshot must describe the same state.
    # A sync client can replace an unchanged-revision record between reads.
    try:
        snapshot = decode_note(original.decode("utf-8"))
    except (UnicodeError, NoteValidationError) as exc:
        raise NotesReadError("Note changed or became invalid before saving.") from exc
    if snapshot != old:
        raise StaleNoteError("Note changed between reads; reload before saving.")
    if completed is not None and old.category != "task":
        raise NotesWriteError("Only a Task can be completed or reopened.")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate = replace(
        old,
        text=old.text if text is None else text,
        completed=old.completed if completed is None else completed,
        archived=old.archived if archived is None else archived,
        revision=old.revision + 1,
        updated_at=max(stamp, old.updated_at),
    )
    return _commit(
        candidate,
        workspace_root,
        expected_revision=expected_revision,
        expected_bytes=original,
    )


def edit_note(
    note_id: str,
    text: str,
    *,
    expected_revision: int,
    workspace_root: str | Path | None = None,
) -> NoteRecord:
    """Replace Note text after an explicit revision check."""
    return _change(note_id, expected_revision, workspace_root, text=text)


def set_task_completed(
    note_id: str,
    completed: bool,
    *,
    expected_revision: int,
    workspace_root: str | Path | None = None,
) -> NoteRecord:
    """Complete or reopen a Task."""
    if type(completed) is not bool:
        raise TypeError("completed must be bool")
    return _change(note_id, expected_revision, workspace_root, completed=completed)


def set_archived(
    note_id: str,
    archived: bool,
    *,
    expected_revision: int,
    workspace_root: str | Path | None = None,
) -> NoteRecord:
    """Archive or unarchive a Note without deleting it."""
    if type(archived) is not bool:
        raise TypeError("archived must be bool")
    return _change(note_id, expected_revision, workspace_root, archived=archived)
