"""Teacher-facing Notes & Tasks controller over Core #239 services.

All I/O is caller-injected. No producer imports, global input interception,
workspace configuration changes, or storage writes before an explicit Save.
Source-only controller in #240-B; advertising/adopting it is a later gate.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pds_core.notes_records import (
    MAX_NOTE_TEXT_LENGTH,
    NoteCategory,
    NoteContext,
    NoteRecord,
    NoteValidationError,
)
from pds_core.notes_service import (
    NoteAlreadyExistsError,
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
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_ui import TeacherScreenHeader, print_teacher_header
from pds_core.workspace import WorkspaceRootError, resolve_workspace_root


class _GoBack(Exception):
    """Return from a prompt without saving a new Note."""


class _ExitMenu(Exception):
    def __init__(self, exit_kind: TeacherMenuExit) -> None:
        self.exit_kind = exit_kind


def _safe_text(value: str) -> str:
    """Display note content without passing terminal controls or bidi marks."""
    return "".join(
        char
        if char in ("\n", "\t")
        or (
            not unicodedata.category(char).startswith("C")
            and unicodedata.category(char) not in ("Zl", "Zp")
        )
        else "�"
        for char in value
    )


class _InputEnded(Exception):
    """The owner closed the injected input stream or cancelled the session."""


class _WorkspaceSelectionChanged(NotesReadError):
    """The selected default workspace changed during this Notes session."""


@dataclass(slots=True)
class _Filters:
    category: NoteCategory | None = None
    status: str = "all"
    class_id: str | None = None
    module_id: str | None = None
    work_id: str | None = None

    def matches(self, note: NoteRecord) -> bool:
        if self.category is not None and note.category != self.category:
            return False
        if self.status == "open" and (
            note.category != "task" or note.completed or note.archived
        ):
            return False
        if self.status == "completed" and (
            note.category != "task" or not note.completed
        ):
            return False
        if self.status == "archived" and not note.archived:
            return False
        for key in ("class_id", "module_id", "work_id"):
            requested = getattr(self, key)
            if requested is not None and (
                note.context is None or getattr(note.context, key) != requested
            ):
                return False
        return True


class _NotesController:
    def __init__(
        self,
        request: SharedTeacherMenuRequest,
        *,
        read_line: Callable[[], str],
        output: TextIO,
        error_output: TextIO | None,
    ) -> None:
        self.request = request
        self.read_line = read_line
        self.output = output
        self.errors = output if error_output is None else error_output
        self.root: Path | None = None
        self.confirmed = False
        self.failed_after_save = False
        self.uncertain = False
        self.filters = _Filters()

    def _result(
        self, exit_kind: TeacherMenuExit, message: str
    ) -> SharedTeacherMenuResult:
        if self.uncertain:
            durability = TeacherDurability.INDETERMINATE
        elif self.confirmed and self.failed_after_save:
            durability = TeacherDurability.PARTIAL
        elif self.confirmed:
            durability = TeacherDurability.COMMITTED
        else:
            durability = TeacherDurability.NO_CHANGE
        changes: frozenset[TeacherChangeScope] = (
            frozenset({TeacherChangeScope.NOTES})
            if durability is not TeacherDurability.NO_CHANGE
            else frozenset()
        )
        return SharedTeacherMenuResult(
            return_token=self.request.return_token,
            exit=exit_kind,
            durability=durability,
            change_scopes=changes,
            message=message,
        )

    def _header(self, title: str) -> None:
        print_teacher_header(
            TeacherScreenHeader("PDS Core", title, self.request.context.display_label),
            output=self.output,
        )

    def _ask(self, prompt: str) -> str:
        print(prompt, end="", file=self.output, flush=True)
        try:
            raw = self.read_line()
        except (EOFError, KeyboardInterrupt, StopIteration) as exc:
            raise _InputEnded from exc
        if type(raw) is not str or raw == "":
            raise _InputEnded
        return raw.rstrip("\r\n")

    def _choice(self, prompt: str) -> str:
        value = self._ask(prompt).strip().casefold()
        if value == "m":
            raise _ExitMenu(TeacherMenuExit.MAIN_MENU)
        if value == "q":
            raise _ExitMenu(TeacherMenuExit.QUIT)
        return value

    def _note_error(self, exc: Exception, *, writing: bool = False) -> None:
        """Print only fixed teacher-safe diagnostics, never raw exception text."""
        if isinstance(exc, _WorkspaceSelectionChanged):
            message = (
                "The selected workspace changed while Notes was open. "
                "Return to the caller and reopen Notes before saving. "
                "Nothing was changed by this action."
            )
        elif isinstance(exc, StaleNoteError):
            message = "This note changed elsewhere. Reload it before editing."
        elif isinstance(exc, NotesConflictError):
            message = (
                "A sync-conflicted Notes file needs review. Preserve both versions "
                "and compare them before writing again."
            )
        elif isinstance(exc, NoteNotFoundError):
            message = "This note is no longer available. Return to the list to refresh."
        elif isinstance(exc, (NotesReadError, WorkspaceRootError)):
            message = (
                "Notes could not be read in the selected workspace. "
                "Check workspace availability; nothing was changed by this action."
            )
        elif isinstance(exc, NoteValidationError):
            message = "Note text is invalid or too long. Revise and try again."
        elif isinstance(exc, NoteAlreadyExistsError):
            message = "That note already exists. No existing note was overwritten."
        else:
            message = "Save could not be confirmed. Inspect Notes before retrying."
            if writing:
                self.uncertain = True
        if writing and self.confirmed:
            self.failed_after_save = True
        print(message, file=self.errors)

    def _workspace(self) -> Path:
        if self.root is None:
            raise RuntimeError("Workspace was not resolved")
        if self.request.context.workspace_root is None:
            # An unpinned menu follows the saved/default workspace selection.
            # Never continue reading or saving against an earlier selection
            # if the teacher switches workspaces while Notes remains open.
            try:
                selected = resolve_workspace_root()
            except WorkspaceRootError as exc:
                raise _WorkspaceSelectionChanged from exc
            if selected != self.root:
                raise _WorkspaceSelectionChanged
        # A caller's explicit override is intentionally fixed for this call.
        return self.root

    def run(self) -> SharedTeacherMenuResult:
        try:
            self.root = resolve_workspace_root(self.request.context.workspace_root)
            # A missing/unsafe workspace must not appear as an empty notebook.
            list_notes(self.root, include_archived=True)
        except (NotesReadError, WorkspaceRootError) as exc:
            self._note_error(exc)
            return self._result(
                TeacherMenuExit.FAILED,
                "Notes unavailable in the selected workspace. Check it before retrying.",
            )

        try:
            while True:
                self._header("Notes & Tasks")
                print("1. Quick Capture", file=self.output)
                print("2. Open Tasks", file=self.output)
                print("3. Recent Notes", file=self.output)
                print("4. Search and Filter", file=self.output)
                print("5. Archived / Completed", file=self.output)
                print("B. Back   M. Main Menu   Q. Quit", file=self.output)
                choice = self._choice("Choose an option: ")
                if choice == "b":
                    return self._result(TeacherMenuExit.BACK, "Returned to the caller.")
                if choice == "1":
                    self._capture()
                elif choice == "2":
                    self._browse("open")
                elif choice == "3":
                    self._browse("recent")
                elif choice == "4":
                    self._search()
                elif choice == "5":
                    self._browse("archive")
                else:
                    print("Choose a listed option, B, M, or Q.", file=self.output)
        except _ExitMenu as exit_request:
            return self._result(
                exit_request.exit_kind,
                "Return to the calling main menu."
                if exit_request.exit_kind is TeacherMenuExit.MAIN_MENU
                else "The calling application may now exit.",
            )
        except _InputEnded:
            return self._result(
                TeacherMenuExit.CANCELLED,
                "Notes session cancelled. Earlier confirmed saves remain saved."
                if self.confirmed
                else "Cancelled. No changes were made.",
            )

    def _candidate_context(self) -> NoteContext | None:
        hint = self.request.context
        work = hint.work
        if hint.class_id is None and work is None:
            return None
        # Caller hints are not authority. Only a teacher-confirmed, eligible
        # non-student kind can be stored; unclear work hints are discarded.
        eligible = {"assignment", "activity", "portfolio", "project", "unit", "lesson"}
        if work is not None and work.work_kind not in eligible:
            return None
        print("Optional context:", file=self.output)
        if hint.class_id is not None:
            print(f"Class: {hint.class_id}", file=self.output)
        if work is not None:
            print(f"Module: {work.module_id}; work: {work.work_id}", file=self.output)
        answer = (
            self._ask("Attach this context? Y/N (B to go back): ").strip().casefold()
        )
        if answer == "b":
            raise _GoBack
        if answer != "y":
            return None
        return NoteContext(
            module_id=None if work is None else work.module_id,
            class_id=hint.class_id,
            work_id=None if work is None else work.work_id,
        )

    def _enter_text(self, title: str) -> str | None:
        self._header(title)
        print("Enter your text. Type :save on its own line to save.", file=self.output)
        print("Type :cancel on its own line to discard this draft.", file=self.output)
        print("B, M, Q and :notes are ordinary text here.", file=self.output)
        lines: list[str] = []
        characters = 0
        while True:
            line = self._ask("> ")
            if line == ":cancel":
                print("Draft cancelled. Nothing was saved.", file=self.output)
                return None
            if line == ":save":
                content = "\n".join(lines)
                if not content.strip():
                    print(
                        "Enter some text before saving, or :cancel.", file=self.output
                    )
                    continue
                return content
            next_size = characters + len(line) + (1 if lines else 0)
            if next_size > MAX_NOTE_TEXT_LENGTH:
                print(
                    "Text is too long. Type :cancel or :save to review it.",
                    file=self.output,
                )
                continue
            lines.append(line)
            characters = next_size

    def _capture(self) -> None:
        while True:
            self._header("Quick Capture")
            print("1. Idea   2. Task   3. Reflection   B. Back", file=self.output)
            choice = self._choice("Choose a category: ")
            if choice == "b":
                return
            categories: dict[str, NoteCategory] = {
                "1": "idea",
                "2": "task",
                "3": "reflection",
            }
            if choice not in categories:
                print("Choose Idea, Task, Reflection, or B.", file=self.output)
                continue
            try:
                context = self._candidate_context()
            except _GoBack:
                continue
            text = self._enter_text(f"New {categories[choice].title()}")
            if text is None:
                return
            try:
                create_note(
                    categories[choice],
                    text,
                    context=context,
                    workspace_root=self._workspace(),
                )
            except (
                NotesReadError,
                NotesWriteError,
                NoteValidationError,
                ValueError,
            ) as exc:
                self._note_error(exc, writing=True)
                print(
                    "The draft remains below so you can copy it before leaving."
                    " It has not been confirmed as saved:",
                    file=self.output,
                )
                print(_safe_text(text), file=self.output)
                return
            self.confirmed = True
            print("Saved. Find it in Recent Notes or Open Tasks.", file=self.output)
            return

    def _collect(self, mode: str, query: str | None) -> list[NoteRecord]:
        if query is not None:
            records = search_notes(query, self._workspace(), include_archived=True)
        else:
            records = list_notes(self._workspace(), include_archived=True)
        if mode == "open":
            records = tuple(
                note
                for note in records
                if note.category == "task" and not note.completed and not note.archived
            )
        elif mode == "recent":
            records = tuple(note for note in records if not note.archived)
        elif mode == "archive":
            records = tuple(
                note
                for note in records
                if note.archived or (note.category == "task" and note.completed)
            )
        return sorted(
            (note for note in records if self.filters.matches(note)),
            key=lambda note: (note.updated_at, note.note_id),
            reverse=True,
        )

    def _search(self) -> None:
        self._header("Search Notes")
        print("Enter words to find, or :cancel to return.", file=self.output)
        query = self._ask("Search: ")
        if query == ":cancel":
            return
        if not query.strip() or len(query) > 256:
            print("Enter 1–256 search characters.", file=self.output)
            return
        self._browse("search", query=query)

    def _filters_menu(self) -> None:
        self._header("Filter Notes")
        print("Enter * to include all items for any field.", file=self.output)
        category = self._ask("Category (idea/task/reflection/*): ").strip().casefold()
        if category == ":cancel":
            return
        if category not in ("idea", "task", "reflection", "*"):
            print("Invalid category; filters unchanged.", file=self.output)
            return
        status = self._ask("Status (all/open/completed/archived): ").strip().casefold()
        if status == ":cancel":
            return
        if status not in ("all", "open", "completed", "archived"):
            print("Invalid status; filters unchanged.", file=self.output)
            return
        ids: list[str | None] = []
        for name in ("class ID", "module ID", "work ID"):
            raw = self._ask(f"{name} (* for all): ").strip()
            if raw == ":cancel":
                return
            if raw != "*" and (
                not raw
                or len(raw) > 128
                or not raw.replace("_", "").replace("-", "").isalnum()
                or not raw.isascii()
            ):
                print("Invalid context ID; filters unchanged.", file=self.output)
                return
            if name == "module ID" and raw != "*" and raw != raw.lower():
                print(
                    "Module ID must be lowercase; filters unchanged.", file=self.output
                )
                return
            ids.append(None if raw == "*" else raw)
        categories: dict[str, NoteCategory] = {
            "idea": "idea",
            "task": "task",
            "reflection": "reflection",
        }
        self.filters = _Filters(
            category=categories.get(category),
            status=status,
            class_id=ids[0],
            module_id=ids[1],
            work_id=ids[2],
        )
        print("Filters updated.", file=self.output)

    def _browse(self, mode: str, *, query: str | None = None) -> None:
        page = 0
        while True:
            try:
                records = self._collect(mode, query)
            except (NotesReadError, ValueError, WorkspaceRootError) as exc:
                self._note_error(exc)
                return
            count = len(records)
            size = 10
            max_page = (count - 1) // size if count else 0
            page = min(page, max_page)
            names = {
                "open": "Open Tasks",
                "recent": "Recent Notes",
                "archive": "Archived / Completed",
                "search": "Search Results",
            }
            self._header(names[mode])
            if not records:
                if mode == "open":
                    print(
                        "No open Tasks matched. Try Recent Notes or Quick Capture.",
                        file=self.output,
                    )
                elif mode == "recent":
                    try:
                        notebook_empty = not list_notes(
                            self._workspace(), include_archived=True
                        )
                    except NotesReadError as exc:
                        self._note_error(exc)
                        return
                    print(
                        "No Notes yet. Choose Quick Capture to add one."
                        if notebook_empty
                        else "No recent Notes matched. Clear filters or try Quick Capture.",
                        file=self.output,
                    )
                elif mode == "archive":
                    print("No archived or completed items matched.", file=self.output)
                else:
                    print(
                        "Nothing matched. Try different words or filters.",
                        file=self.output,
                    )
            subset = records[page * size : (page + 1) * size]
            for index, note in enumerate(subset, 1):
                preview = _safe_text(note.text.splitlines()[0][:58]).replace("\t", " ")
                state = (
                    "archived"
                    if note.archived
                    else "completed"
                    if note.completed
                    else "open"
                    if note.category == "task"
                    else "active"
                )
                print(
                    f"{index}. {note.category.title()} [{state}] — {preview}",
                    file=self.output,
                )
            print(
                "F. Filters   >. Next page   <. Previous page   B. Back",
                file=self.output,
            )
            choice = self._choice("Select a note: ")
            if choice == "b":
                return
            if choice == "f":
                self._filters_menu()
                page = 0
                continue
            if choice == ">":
                page = min(page + 1, max_page)
                continue
            if choice == "<":
                page = max(page - 1, 0)
                continue
            if choice.isascii() and choice.isdecimal():
                selected = int(choice)
                if 1 <= selected <= len(subset):
                    self._detail(subset[selected - 1].note_id)
                    continue
            print("Choose a listed number, F, <, >, or B.", file=self.output)

    def _detail(self, note_id: str) -> None:
        while True:
            try:
                note = get_note(note_id, self._workspace())
            except (NotesReadError, WorkspaceRootError) as exc:
                self._note_error(exc)
                return
            self._header(f"{note.category.title()} Detail")
            print(
                f"Status: {'Archived' if note.archived else 'Completed' if note.completed else 'Open' if note.category == 'task' else 'Active'}",
                file=self.output,
            )
            print(
                f"Updated: {note.updated_at}   Revision: {note.revision}",
                file=self.output,
            )
            print("Text:", file=self.output)
            print(_safe_text(note.text), file=self.output)
            print("1. Edit text", file=self.output)
            if note.category == "task":
                print(
                    "2. Reopen Task" if note.completed else "2. Complete Task",
                    file=self.output,
                )
            print("3. Unarchive" if note.archived else "3. Archive", file=self.output)
            print("B. Back", file=self.output)
            choice = self._choice("Choose: ")
            if choice == "b":
                return
            replacement_draft: str | None = None
            try:
                if choice == "1":
                    updated = self._enter_text("Edit Note — Replacement Text")
                    if updated is None:
                        continue
                    replacement_draft = updated
                    edit_note(
                        note.note_id,
                        updated,
                        expected_revision=note.revision,
                        workspace_root=self._workspace(),
                    )
                elif choice == "2" and note.category == "task":
                    set_task_completed(
                        note.note_id,
                        not note.completed,
                        expected_revision=note.revision,
                        workspace_root=self._workspace(),
                    )
                elif choice == "3":
                    prompt = (
                        "Unarchive this item? Y/N: "
                        if note.archived
                        else "Archive this item? Y/N: "
                    )
                    if self._ask(prompt).strip().casefold() != "y":
                        print("No changes were made.", file=self.output)
                        continue
                    set_archived(
                        note.note_id,
                        not note.archived,
                        expected_revision=note.revision,
                        workspace_root=self._workspace(),
                    )
                else:
                    print("Choose a listed option or B.", file=self.output)
                    continue
            except (
                NotesReadError,
                NotesWriteError,
                NoteValidationError,
                ValueError,
            ) as exc:
                self._note_error(exc, writing=True)
                if replacement_draft is not None:
                    print(
                        "Unsaved replacement text follows. Copy it before leaving:",
                        file=self.output,
                    )
                    print(_safe_text(replacement_draft), file=self.output)
                return
            self.confirmed = True
            print("Saved.", file=self.output)


def run_notes_controller(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None,
) -> SharedTeacherMenuResult:
    """Invoke the real Notes controller; caller has already validated I/O shape."""
    return _NotesController(
        request, read_line=read_line, output=output, error_output=error_output
    ).run()
