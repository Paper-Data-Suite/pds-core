"""Read access to Notes in the existing selected Core workspace."""

from __future__ import annotations

import re
from pathlib import Path

from pds_core.notes_records import (
    MAX_SERIALIZED_BYTES,
    NoteRecord,
    NoteValidationError,
    decode_note,
)
from pds_core.workspace import resolve_workspace_root

_CANONICAL_FILE = re.compile(r"^note_[0-9a-f]{32}\.json$")


class NotesReadError(RuntimeError):
    """Workspace Notes cannot be read safely (not equivalent to empty)."""


class NotesConflictError(NotesReadError):
    """A noncanonical/sync-conflicted Notes item needs human review."""


class NoteNotFoundError(NotesReadError):
    """An explicitly requested note does not exist."""


def notes_dir(workspace_root: str | Path | None = None) -> Path:
    """Pure Notes path selection using the canonical Core workspace resolver."""
    root = resolve_workspace_root(workspace_root)
    return root / ".pds" / "notes" / "v1"


def _notes_collection(workspace_root: str | Path | None) -> Path:
    path = notes_dir(workspace_root)
    root = path.parents[2]  # <workspace>/.pds/notes/v1 -> <workspace>
    if not root.is_dir():
        raise NotesReadError("Selected PDS workspace is unavailable.")
    for component in (root / ".pds", root / ".pds" / "notes", path):
        if component.is_symlink():
            raise NotesReadError("Notes directory links are not supported.")
        if component.exists() and not component.is_dir():
            raise NotesReadError("Notes directory has an unexpected file.")
    return path


def _inventory(workspace_root: str | Path | None) -> tuple[Path, ...]:
    """Observe a collection without creating or deleting anything."""
    directory = _notes_collection(workspace_root)
    if not directory.exists():
        return ()
    try:
        entries = tuple(sorted(directory.iterdir(), key=lambda p: p.name))
    except OSError as exc:
        raise NotesReadError("Cannot list workspace Notes.") from exc
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise NotesReadError("Notes directory contains an unsupported entry.")
        if _CANONICAL_FILE.fullmatch(entry.name) is None:
            # Both OneDrive conflicted copies and interrupted temp files are
            # preserved for explicit review; neither is silently discarded.
            raise NotesConflictError(
                "Notes directory contains an unexpected or conflicted file."
            )
    return entries


def _read_exact(path: Path) -> NoteRecord:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_SERIALIZED_BYTES + 1)
    except OSError as exc:
        raise NotesReadError("Cannot read workspace Note.") from exc
    if len(raw) > MAX_SERIALIZED_BYTES:
        raise NotesReadError("Workspace Note exceeds its file-size limit.")
    try:
        note = decode_note(raw.decode("utf-8"))
    except (UnicodeError, NoteValidationError) as exc:
        raise NotesReadError("Workspace Note is malformed or unsupported.") from exc
    if path.name != f"{note.note_id}.json":
        raise NotesReadError("Workspace Note filename and record ID disagree.")
    return note


def list_notes(
    workspace_root: str | Path | None = None,
    *,
    include_archived: bool = False,
) -> tuple[NoteRecord, ...]:
    """List records in the selected shared workspace, without mutations."""
    if type(include_archived) is not bool:
        raise TypeError("include_archived must be bool")
    notes = tuple(_read_exact(path) for path in _inventory(workspace_root))
    visible = notes if include_archived else tuple(n for n in notes if not n.archived)
    return tuple(sorted(visible, key=lambda n: (n.created_at, n.note_id)))


def get_note(
    note_id: str,
    workspace_root: str | Path | None = None,
) -> NoteRecord:
    """Read one note, but refuse when the collection inventory is ambiguous."""
    if type(note_id) is not str or _CANONICAL_FILE.fullmatch(f"{note_id}.json") is None:
        raise NotesReadError("Invalid Notes identifier.")
    entries = _inventory(workspace_root)
    path = next((entry for entry in entries if entry.name == f"{note_id}.json"), None)
    if path is None:
        raise NoteNotFoundError("Note does not exist in the selected workspace.")
    return _read_exact(path)


def search_notes(
    query: str,
    workspace_root: str | Path | None = None,
    *,
    include_archived: bool = False,
) -> tuple[NoteRecord, ...]:
    """Simple case-insensitive substring search; no index or extra database."""
    if type(query) is not str or not query.strip() or len(query) > 256:
        raise ValueError("Search query must be nonblank and at most 256 chars.")
    term = query.casefold()
    return tuple(
        note
        for note in list_notes(workspace_root, include_archived=include_archived)
        if term in note.text.casefold()
    )
