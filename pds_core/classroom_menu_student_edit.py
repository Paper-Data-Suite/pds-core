"""D2: reviewed individual enrollment edits through Core #241."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pds_core.classroom_admin_preview import ClassroomAdministrationPreviewError
from pds_core.classroom_discovery import ClassroomDiscoveryError
from pds_core.classroom_menu_roster_import import (
    _Back,
    _ImportFlow,
    _Refusal,
    _Return,
    _context,
    _row,
)
from pds_core.classroom_menu_school_year import _header
from pds_core.classroom_school_year_commit import (
    SchoolYearCommitError,
    _local_year_lock,
)
from pds_core.roster_edits import (
    RosterEditOperation,
    StudentRosterChange,
    StudentRosterEditError,
    StudentRosterEditWriteError,
    commit_student_roster_edit,
    plan_student_roster_edit,
)
from pds_core.roster_imports import _load_current_state
from pds_core.rosters import ROSTER_REQUIRED_COLUMNS, RosterError, student_lookup
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherDurability,
    TeacherMenuExit,
)

_MAX_FIELD = 2000
_MAX_REVIEW = 16000


class _StudentFlow(_ImportFlow):
    """Reuse D1's canonical context and injected navigation/receipt helpers."""

    def edit(
        self,
        operation: RosterEditOperation,
        selected_id: str | None,
    ) -> SharedTeacherMenuResult | None:
        try:
            baseline = _context(self.root, self.class_id, self.year)
            roster, token = _load_current_state(self.root, self.class_id)
            current = (
                None
                if roster is None or selected_id is None
                else student_lookup(roster).get(selected_id)
            )
            if operation != "add" and (selected_id is None or current is None):
                raise _Refusal("Selected enrollment is missing; select again.")
            _header(
                self.request,
                f"{operation.capitalize()} student enrollment",
                self.output,
            )
            print(f"Class: {self.class_id}; school year: {self.year}", file=self.output)
            if current is not None:
                old = _row(current)
                if len(old) > _MAX_REVIEW:
                    raise _Refusal(
                        "Exact record exceeds interactive review limits; use the roster CLI."
                    )
                print(f"Selected: {old}", file=self.output)
            fields: dict[str, str] = {}
            if operation == "add":
                student_id = self.read("New stable student ID (or B/M/Q): ")
                for key in ("first_name", "last_name", "period"):
                    fields[key] = self.read(f"{key} (or B/M/Q): ")
                if roster is not None:
                    print(
                        "Existing optional columns default to empty; enter values in the optional-field step.",
                        file=self.output,
                    )
            else:
                assert selected_id is not None
                student_id = selected_id

            if operation in {"add", "update"}:
                # Explicit field/value pairs avoid interpreting blank input as
                # permission to clear an existing value.
                allowed: tuple[str, ...] = ("first_name", "last_name", "period")
                if roster is not None:
                    allowed += tuple(
                        column
                        for column in roster.columns
                        if column not in ROSTER_REQUIRED_COLUMNS
                    )
                print(
                    f"Editable fields: {json.dumps(allowed, ensure_ascii=True)}",
                    file=self.output,
                )
                print(
                    "Enter a field name, then its exact value. Enter DONE to review. Enter CLEAR as a value to empty an optional field.",
                    file=self.output,
                )
                for _ in range(100):
                    key = self.read("Field (DONE/B/M/Q): ")
                    if key == "DONE":
                        break
                    if key not in allowed:
                        raise _Refusal("Field is not editable in this roster schema.")
                    value = self.read("Value (CLEAR/B/M/Q): ")
                    fields[key] = "" if value == "CLEAR" else value
                else:
                    raise _Refusal("Too many field entries; review a smaller change.")
            if any(len(value) > _MAX_FIELD for value in fields.values()):
                raise _Refusal("Field value exceeds interactive review limits.")
            change = StudentRosterChange(operation, student_id, fields)
            preview = plan_student_roster_edit(self.root, self.class_id, change)
            if (
                preview.current_state_token != token
                or _context(self.root, self.class_id, self.year) != baseline
            ):
                raise _Refusal(
                    "Class, year or roster changed during entry; review again."
                )
            before = (
                "(none)"
                if preview.current_record is None
                else _row(preview.current_record)
            )
            after = (
                "(none)"
                if preview.proposed_record is None
                else _row(preview.proposed_record)
            )
            if len(before) + len(after) > _MAX_REVIEW:
                raise _Refusal(
                    "Exact record exceeds interactive review limits; use the roster CLI."
                )
            _header(self.request, "Review student enrollment change", self.output)
            print(
                f"Workspace: {json.dumps(str(self.root), ensure_ascii=True)}",
                file=self.output,
            )
            print(
                f"Class: {self.class_id}; year: {self.year}; operation: {operation}",
                file=self.output,
            )
            print(f"Before: {before}", file=self.output)
            print(f"After: {after}", file=self.output)
            print(
                f"Changed fields: {json.dumps(preview.changed_fields, ensure_ascii=True)}",
                file=self.output,
            )
            print(
                f"Enrollment count: {preview.current_count} -> {preview.proposed_count}",
                file=self.output,
            )
            print(
                "Only this canonical enrollment changes. Historical producer work is preserved.",
                file=self.output,
            )
            print("PREVIEW ONLY — no write occurred.", file=self.output)
            if (
                self.read(
                    "C. Confirm exact change  B. Cancel  M. Main Menu  Q. Quit: "
                ).casefold()
                != "c"
            ):
                raise _Back
            with _local_year_lock(self.root):
                if _context(self.root, self.class_id, self.year) != baseline:
                    raise _Refusal("Class or year changed; review again.")
                result = commit_student_roster_edit(
                    self.root,
                    self.class_id,
                    change,
                    expected_current_state_token=preview.current_state_token,
                    expected_candidate_state_token=preview.candidate_state_token,
                    confirmed=True,
                )
            if result.outcome == "no_change":
                return self.receipt(
                    TeacherMenuExit.BACK, "Enrollment already matched; no write."
                )
            print("Enrollment change committed.", file=self.output)
            return self.receipt(
                TeacherMenuExit.BACK,
                "Enrollment change committed.",
                TeacherDurability.COMMITTED,
            )
        except _Back:
            return None
        except _Return as nav:
            return self.receipt(nav.outcome, "Enrollment review returned.")
        except StudentRosterEditWriteError as error:
            if error.reason == "write_outcome_uncertain":
                print(
                    "Roster write uncertain; inspect canonical state before retry.",
                    file=self.errors,
                )
                return self.receipt(
                    TeacherMenuExit.FAILED,
                    "Roster write outcome uncertain.",
                    TeacherDurability.INDETERMINATE,
                )
            print(
                "Enrollment write refused; inspect canonical state before retry.",
                file=self.errors,
            )
        except StudentRosterEditError as error:
            if error.reason == "empty_roster":
                print(
                    "Removing the final student is not supported by the current roster contract.",
                    file=self.errors,
                )
            else:
                print(
                    "Enrollment change refused; inspect current roster and review again.",
                    file=self.errors,
                )
        except _Refusal as error:
            print(str(error), file=self.errors)
        except (
            RosterError,
            ClassroomDiscoveryError,
            ClassroomAdministrationPreviewError,
            SchoolYearCommitError,
            OSError,
            RuntimeError,
            ValueError,
        ):
            print(
                "Enrollment change refused; inspect the class and review again.",
                file=self.errors,
            )
        return self.receipt(TeacherMenuExit.FAILED, "Enrollment change refused.")


def run_student_edit_review(
    request: SharedTeacherMenuRequest,
    *,
    workspace_root: Path,
    class_id: str,
    expected_active_year: str | None,
    operation: RosterEditOperation,
    selected_id: str | None,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO,
) -> SharedTeacherMenuResult | None:
    return _StudentFlow(
        request,
        workspace_root,
        class_id,
        expected_active_year,
        read_line,
        output,
        error_output,
    ).edit(operation, selected_id)
