"""Script-safe, noninteractive Notes CLI; Core #240-C.

All records and writes are delegated to the guarded #239 workspace service.
No global input interception, interactive prompts, or workspace preference edits.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.notes_records import (
    MAX_SERIALIZED_BYTES,
    NoteContext,
    NoteRecord,
    NoteValidationError,
)
from pds_core.notes_service import (
    NotesWriteError,
    StaleNoteError,
    create_note,
    edit_note,
    set_archived,
    set_task_completed,
)
from pds_core.notes_storage import (
    NoteNotFoundError,
    NotesConflictError,
    NotesReadError,
    get_note,
    list_notes,
    search_notes,
)
from pds_core.standards import StandardsLibrary
from pds_core.workspace import WorkspaceRootError

# Stable script exit codes: success, bad input, missing, stale, unsafe, write.
EXIT_OK, EXIT_INPUT, EXIT_NOT_FOUND, EXIT_STALE, EXIT_STORAGE, EXIT_WRITE = (
    0,
    2,
    3,
    4,
    5,
    6,
)


class _BadInput(ValueError):
    """User-supplied Note content was not a valid bounded UTF-8 document."""


def _identifier(value: str) -> str:
    try:
        return validate_identifier(value, "Notes context")
    except IdentifierValidationError as exc:
        raise argparse.ArgumentTypeError("Invalid Notes context identifier") from exc


def _module_id(value: str) -> str:
    result = _identifier(value)
    if result != result.lower():
        raise argparse.ArgumentTypeError("Module ID must be lowercase")
    return result


def _note_id(value: str) -> str:
    if re.fullmatch(r"note_[0-9a-f]{32}", value) is None:
        raise argparse.ArgumentTypeError("Invalid Note identifier")
    return value


def _revision(value: str) -> int:
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Revision must be a positive integer") from exc
    if n < 1:
        raise argparse.ArgumentTypeError("Revision must be a positive integer")
    return n


def _text_from_file(name: str) -> str:
    try:
        if name == "-":
            if sys.stdin.isatty():
                raise _BadInput(
                    "Redirect stdin or supply a file; no prompt is available."
                )
            stream = getattr(sys.stdin, "buffer", None)
            if stream is not None:
                raw: bytes = stream.read(MAX_SERIALIZED_BYTES + 1)
            else:
                raw = sys.stdin.read(MAX_SERIALIZED_BYTES + 1).encode("utf-8")
        else:
            with Path(name).open("rb") as stream:
                raw = stream.read(MAX_SERIALIZED_BYTES + 1)
    except (OSError, UnicodeError) as exc:
        raise _BadInput(
            "Unable to read UTF-8 Note text from the supplied source."
        ) from exc
    if len(raw) > MAX_SERIALIZED_BYTES:
        raise _BadInput("Note text exceeds the supported size.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise _BadInput("Note text must be UTF-8.") from exc


def _safe(text: str) -> str:
    return "".join(
        ch
        if ch in ("\n", "\t")
        or (
            not unicodedata.category(ch).startswith("C")
            and unicodedata.category(ch) not in ("Zl", "Zp")
        )
        else "\ufffd"
        for ch in text
    )


def _status(note: NoteRecord) -> str:
    if note.archived:
        return "archived"
    if note.category == "task":
        return "completed" if note.completed else "open"
    return "active"


def _emit_record(note: NoteRecord, output: TextIO, *, fmt: str, summary: bool) -> None:
    if fmt == "json":
        print(json.dumps(asdict(note), ensure_ascii=False, sort_keys=True), file=output)
    elif summary:
        print(
            f"Saved {note.category}: {note.note_id} (revision {note.revision}; {_status(note)}).",
            file=output,
        )
    else:
        print(
            f"ID: {note.note_id}\nCategory: {note.category}\nStatus: {_status(note)}",
            file=output,
        )
        print(
            f"Revision: {note.revision}\nUpdated (UTC): {note.updated_at}\nText:",
            file=output,
        )
        print(_safe(note.text), file=output)


def _filtered(
    notes: tuple[NoteRecord, ...], args: argparse.Namespace
) -> tuple[NoteRecord, ...]:
    matches: list[NoteRecord] = []
    for note in notes:
        if args.category is not None and note.category != args.category:
            continue
        if args.status == "open" and (note.category != "task" or note.completed):
            continue
        if args.status == "completed" and (
            note.category != "task" or not note.completed
        ):
            continue
        if args.status == "archived" and not note.archived:
            continue
        ctx = note.context
        if any(
            value is not None and (ctx is None or getattr(ctx, name) != value)
            for name, value in (
                ("class_id", args.class_id),
                ("module_id", args.module_id),
                ("work_id", args.work_id),
            )
        ):
            continue
        matches.append(note)
    return tuple(
        sorted(matches, key=lambda item: (item.updated_at, item.note_id), reverse=True)
    )


def _emit_list(notes: tuple[NoteRecord, ...], output: TextIO, fmt: str) -> None:
    if fmt == "json":
        print(
            json.dumps(
                {"count": len(notes), "notes": [asdict(n) for n in notes]},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=output,
        )
    elif not notes:
        print("No matching Notes. Use 'notes create' to capture one.", file=output)
    else:
        for note in notes:
            snippet = " ".join(_safe(note.text).split())
            if len(snippet) > 96:
                snippet = snippet[:95] + "…"
            print(
                f"{note.note_id} | {note.category} | {_status(note)} | "
                f"revision {note.revision} | {snippet}",
                file=output,
            )


def handle_notes(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Return stable status codes; do not copy private raw exceptions to stderr."""
    try:
        root: Path = args.workspace_root
        action: str = args.notes_action
        fmt: str = args.format
        if action == "create":
            ctx = (
                NoteContext(args.module_id, args.class_id, args.work_id)
                if any((args.module_id, args.class_id, args.work_id))
                else None
            )
            note = create_note(
                args.category,
                _text_from_file(args.text_file),
                context=ctx,
                workspace_root=root,
            )
            _emit_record(note, stdout, fmt=fmt, summary=True)
        elif action in ("list", "search"):
            archived: bool = args.include_archived or args.status == "archived"
            notes = (
                list_notes(root, include_archived=archived)
                if action == "list"
                else search_notes(args.query, root, include_archived=archived)
            )
            _emit_list(_filtered(notes, args), stdout, fmt)
        elif action == "show":
            _emit_record(get_note(args.note_id, root), stdout, fmt=fmt, summary=False)
        elif action == "edit":
            note = edit_note(
                args.note_id,
                _text_from_file(args.text_file),
                expected_revision=args.expected_revision,
                workspace_root=root,
            )
            _emit_record(note, stdout, fmt=fmt, summary=True)
        elif action in ("complete", "reopen"):
            note = set_task_completed(
                args.note_id,
                action == "complete",
                expected_revision=args.expected_revision,
                workspace_root=root,
            )
            _emit_record(note, stdout, fmt=fmt, summary=True)
        elif action in ("archive", "unarchive"):
            note = set_archived(
                args.note_id,
                action == "archive",
                expected_revision=args.expected_revision,
                workspace_root=root,
            )
            _emit_record(note, stdout, fmt=fmt, summary=True)
        else:
            raise _BadInput("Unsupported Notes command.")
        return EXIT_OK
    except _BadInput as exc:
        print(f"Notes input: {exc}", file=stderr)
        return EXIT_INPUT
    except (NoteValidationError, ValueError, TypeError):
        print("Invalid Note input. Review the requested value.", file=stderr)
        return EXIT_INPUT
    except NoteNotFoundError:
        print("Note not found in the selected workspace.", file=stderr)
        return EXIT_NOT_FOUND
    except StaleNoteError:
        print("Note changed; reload the revision before editing.", file=stderr)
        return EXIT_STALE
    except NotesConflictError:
        print(
            "Notes have conflicted files; preserve and compare both copies before retrying.",
            file=stderr,
        )
        return EXIT_STORAGE
    except (NotesReadError, WorkspaceRootError):
        print(
            "Selected workspace Notes are unavailable or unsafe to read.", file=stderr
        )
        return EXIT_STORAGE
    except (NotesWriteError, OSError):
        print(
            "Save failed; inspect the selected workspace before retrying.", file=stderr
        )
        return EXIT_WRITE


def _format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("text", "json"), default="text")


def _filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--category", choices=("idea", "task", "reflection"))
    parser.add_argument(
        "--status", choices=("all", "open", "completed", "archived"), default="all"
    )
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--module-id", type=_module_id)
    parser.add_argument("--class-id", type=_identifier)
    parser.add_argument("--work-id", type=_identifier)
    _format(parser)


def add_notes_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    """Register one Notes command family, without modifying other Core routes."""
    notes = subparsers.add_parser("notes", help="Manage workspace-native Notes & Tasks")
    actions = notes.add_subparsers(dest="notes_action", required=True)
    create = actions.add_parser("create", help="Capture Idea, Task, or Reflection")
    create.add_argument(
        "--category", required=True, choices=("idea", "task", "reflection")
    )
    create.add_argument("--text-file", required=True, metavar="FILE|-")
    create.add_argument("--module-id", type=_module_id)
    create.add_argument("--class-id", type=_identifier)
    create.add_argument("--work-id", type=_identifier)
    _format(create)
    create.set_defaults(handler=handle_notes, load_workspace_library=False)
    for name in ("list", "search"):
        parser = actions.add_parser(name, help="Find Notes without modifying them")
        if name == "search":
            parser.add_argument("query")
        _filters(parser)
        parser.set_defaults(handler=handle_notes, load_workspace_library=False)
    show = actions.add_parser("show", help="Read a Note and its revision")
    show.add_argument("note_id", type=_note_id)
    _format(show)
    show.set_defaults(handler=handle_notes, load_workspace_library=False)
    for name in ("edit", "complete", "reopen", "archive", "unarchive"):
        parser = actions.add_parser(name, help="Revision-guarded Note update")
        parser.add_argument("note_id", type=_note_id)
        parser.add_argument("--expected-revision", type=_revision, required=True)
        if name == "edit":
            parser.add_argument("--text-file", metavar="FILE|-", required=True)
        _format(parser)
        parser.set_defaults(handler=handle_notes, load_workspace_library=False)
