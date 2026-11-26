"""D1: reviewed full-roster replacement using existing Core authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pds_core.classroom_menu_outcome import _outcome_notice

from pds_core.classroom_admin_preview import (
    ClassroomAdministrationPreviewError,
    _guard,
    _state_fingerprint,
)
from pds_core.classroom_discovery import (
    ClassroomDiscoveryError,
    MAX_DISPLAY_STUDENTS,
    MAX_ROSTER_BYTES,
    inspect_classroom_overview,
    inspect_classroom_roster,
)
from pds_core.classroom_menu_school_year import _header
from pds_core.classroom_school_year_commit import (
    SchoolYearCommitError,
    _local_year_lock,
)
from pds_core.classes import load_class_roster
from pds_core.roster_imports import (
    RosterImportPreview,
    RosterImportWriteError,
    _roster_state_token,
    commit_roster_import,
    plan_roster_import,
)
from pds_core.rosters import (
    Roster,
    RosterError,
    RosterWriteError,
    StudentRecord,
    load_roster,
    student_display_name,
)
from pds_core.routes import class_metadata_path, class_roster_path
from pds_core.school_years import school_year_state_path
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherDurability,
    TeacherMenuExit,
)

_PAGE = 8
_MAX_REVIEW_CHARS = 160_000
_MAX_LINE = 4_000


class _Refusal(Exception):
    """Bounded teacher-safe refusal."""


class _Back(Exception):
    """Cancel to class roster."""


class _Return(Exception):
    def __init__(self, outcome: TeacherMenuExit) -> None:
        self.outcome = outcome


def _context(root: Path, class_id: str, year: str | None) -> tuple[str, str]:
    """Require an existing class explicitly belonging to the current year."""
    year_path = school_year_state_path(root)
    before = _state_fingerprint(year_path)
    overview = inspect_classroom_overview(root)
    selected = next(
        (item for item in overview.classes if item.class_id == class_id), None
    )
    if (
        year is None
        or overview.workspace.root != root
        or overview.active_school_year != year
        or selected is None
        or not selected.metadata_present
        or selected.school_year != year
    ):
        raise _Refusal("Select a class with metadata in the active school year.")
    metadata = class_metadata_path(root, class_id)
    _guard(metadata)
    with metadata.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise _Refusal("Class metadata exceeds the review limit.")
    if _state_fingerprint(year_path) != before:
        raise _Refusal("School year changed; select the class again.")
    inspect_classroom_roster(root, class_id)
    return before, hashlib.sha256(raw).hexdigest()


def _candidate(path: Path) -> Roster:
    if not path.is_file() or path.stat().st_size > MAX_ROSTER_BYTES:
        raise _Refusal("Candidate CSV is missing or exceeds the review limit.")
    candidate = load_roster(path)
    if len(candidate.students) > MAX_DISPLAY_STUDENTS:
        raise _Refusal("Candidate roster exceeds the review limit.")
    return candidate


def _row(record: StudentRecord) -> str:
    return json.dumps(
        {
            "name": student_display_name(record),
            "student_id": record.student_id,
            "first_name": record.first_name,
            "last_name": record.last_name,
            "period": record.period,
            "optional_fields": dict(record.extra_fields),
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def _review_lines(preview: RosterImportPreview, current: Roster | None) -> list[str]:
    old_columns = () if current is None else current.columns
    if not set(old_columns) <= set(preview.candidate.columns):
        raise _Refusal("Candidate omits existing columns; retain all optional columns.")
    lines = [
        f"Before columns: {json.dumps(old_columns, ensure_ascii=True)}",
        f"After columns: {json.dumps(preview.candidate.columns, ensure_ascii=True)}",
        f"Added: {preview.addition_count}; changed: {preview.change_count}; removed: {preview.removal_count}; unchanged: {preview.unchanged_count}",
    ]
    for label, records in (
        ("Before order", () if current is None else current.students),
        ("After order", preview.candidate.students),
    ):
        ids = [record.student_id for record in records]
        lines.append(f"{label}: {len(ids)} students")
        for start in range(0, len(ids), 12):
            lines.append(json.dumps(ids[start : start + 12], ensure_ascii=True))
    lines.extend(f"ADD {_row(record)}" for record in preview.additions)
    for change in preview.changes:
        lines.append(f"CHANGE before {_row(change.current)}")
        lines.append(f"CHANGE after  {_row(change.proposed)}")
    lines.extend(f"REMOVE {_row(record)}" for record in preview.removals)
    if (
        any(len(line) > _MAX_LINE for line in lines)
        or sum(map(len, lines)) > _MAX_REVIEW_CHARS
    ):
        raise _Refusal("Exact review exceeds interactive limits; use the roster CLI.")
    return lines


class _ImportFlow:
    def __init__(
        self,
        request: SharedTeacherMenuRequest,
        root: Path,
        class_id: str,
        year: str | None,
        read_line: Callable[[], str],
        output: TextIO,
        error_output: TextIO,
    ) -> None:
        self.request = request
        self.root = root
        self.class_id = class_id
        self.year = year
        self.read_line = read_line
        self.output = output
        self.errors = error_output

    def receipt(
        self,
        outcome: TeacherMenuExit,
        detail: str,
        durability: TeacherDurability = TeacherDurability.NO_CHANGE,
    ) -> SharedTeacherMenuResult:
        return SharedTeacherMenuResult(
            self.request.return_token,
            outcome,
            durability,
            frozenset()
            if durability is TeacherDurability.NO_CHANGE
            else frozenset({TeacherChangeScope.ROSTER}),
            f"{detail} Revalidate workspace, school year, class, roster and work on return.",
        )

    def read(self, prompt: str) -> str:
        print(prompt, end="", file=self.output, flush=True)
        try:
            raw = self.read_line()
        except (EOFError, StopIteration, KeyboardInterrupt):
            raise _Return(TeacherMenuExit.CANCELLED) from None
        if type(raw) is not str:
            raise _Return(TeacherMenuExit.FAILED)
        if raw == "":
            raise _Return(TeacherMenuExit.CANCELLED)
        choice = raw.strip()
        if choice.casefold() == "b":
            raise _Back
        if choice.casefold() == "m":
            raise _Return(TeacherMenuExit.MAIN_MENU)
        if choice.casefold() == "q":
            raise _Return(TeacherMenuExit.QUIT)
        return choice

    def run(self) -> SharedTeacherMenuResult | None:
        try:
            baseline = _context(self.root, self.class_id, self.year)
            _header(self.request, "Import full roster", self.output)
            print(f"Class: {self.class_id}; school year: {self.year}", file=self.output)
            print(
                "Select a complete Core-format CSV. Existing enrollments missing from it will be removed.",
                file=self.output,
            )
            raw = self.read("Candidate CSV path (or B/M/Q): ")
            if len(raw) > 4096 or not raw:
                raise _Refusal("Invalid candidate path.")
            path = Path(raw.strip('"')).expanduser().resolve(strict=True)
            if path == class_roster_path(self.root, self.class_id):
                raise _Refusal(
                    "Select an external candidate, not the canonical roster itself."
                )
            candidate = _candidate(path)
            preview = plan_roster_import(self.root, self.class_id, candidate)
            current = (
                load_class_roster(self.root, self.class_id)
                if preview.current_roster_present
                else None
            )
            if (
                current is not None
                and _roster_state_token(current) != preview.current_state_token
            ):
                raise _Refusal("Canonical roster changed during review.")
            if _context(self.root, self.class_id, self.year) != baseline:
                raise _Refusal("Class or year changed during review.")
            lines = _review_lines(preview, current)
            pages = (len(lines) + _PAGE - 1) // _PAGE
            for page in range(pages):
                _header(self.request, "Review full roster import", self.output)
                print(f"Workspace: {json.dumps(str(self.root))}", file=self.output)
                print(
                    f"Class: {self.class_id}; year: {self.year}; page {page + 1}/{pages}",
                    file=self.output,
                )
                print(f"Candidate: {json.dumps(str(path))}", file=self.output)
                for line in lines[page * _PAGE : (page + 1) * _PAGE]:
                    print(line, file=self.output)
                print(
                    "Only canonical enrollment changes; historical producer work is preserved.",
                    file=self.output,
                )
                print("PREVIEW ONLY — no write occurred.", file=self.output)
                if page + 1 < pages:
                    if (
                        self.read(
                            "N. Next review page  B. Cancel  M. Main Menu  Q. Quit: "
                        ).casefold()
                        != "n"
                    ):
                        raise _Back
                elif (
                    self.read(
                        "C. Confirm exact import  B. Cancel  M. Main Menu  Q. Quit: "
                    ).casefold()
                    != "c"
                ):
                    raise _Back
            with _local_year_lock(self.root):
                if _context(self.root, self.class_id, self.year) != baseline:
                    raise _Refusal("Class or year changed; review again.")
                fresh = _candidate(path)
                latest = plan_roster_import(self.root, self.class_id, fresh)
                if (
                    latest.current_state_token != preview.current_state_token
                    or latest.candidate_state_token != preview.candidate_state_token
                ):
                    raise _Refusal(
                        "Candidate or canonical roster changed; review again."
                    )
                if latest.current_state_token == latest.candidate_state_token:
                    return self.receipt(
                        TeacherMenuExit.BACK, "Roster already matched; no write."
                    )
                try:
                    commit_roster_import(
                        self.root,
                        self.class_id,
                        fresh,
                        expected_current_state_token=preview.current_state_token,
                        expected_candidate_state_token=preview.candidate_state_token,
                    )
                except (RosterWriteError, RosterImportWriteError):
                    _outcome_notice(
                        "Roster write uncertain; inspect canonical state before retry.",
                        file=self.errors,
                    )
                    return self.receipt(
                        TeacherMenuExit.FAILED,
                        "Roster write outcome uncertain.",
                        TeacherDurability.INDETERMINATE,
                    )
            _outcome_notice("Roster import committed.", file=self.output)
            return self.receipt(
                TeacherMenuExit.BACK,
                "Roster import committed.",
                TeacherDurability.COMMITTED,
            )
        except _Back:
            return None
        except _Return as nav:
            return self.receipt(nav.outcome, "Roster review returned.")
        except _Refusal as error:
            _outcome_notice(str(error), file=self.errors)
        except (
            RosterError,
            ClassroomDiscoveryError,
            ClassroomAdministrationPreviewError,
            SchoolYearCommitError,
            OSError,
            RuntimeError,
            ValueError,
        ):
            _outcome_notice(
                "Roster import refused; inspect the class and candidate and review again.",
                file=self.errors,
            )
        return self.receipt(TeacherMenuExit.FAILED, "Roster import refused.")


def run_roster_import_review(
    request: SharedTeacherMenuRequest,
    *,
    workspace_root: Path,
    class_id: str,
    expected_active_year: str | None,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO,
) -> SharedTeacherMenuResult | None:
    return _ImportFlow(
        request,
        workspace_root,
        class_id,
        expected_active_year,
        read_line,
        output,
        error_output,
    ).run()
