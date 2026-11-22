"""Noninteractive individual roster-edit CLI composing Core #241 services.

The change-file is bounded UTF-8 JSON; student identifiers never need to appear
in shell arguments. No prompting, implicit confirmation or alternate writer.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Mapping, TextIO, cast

from pds_core.cli_support.roster_imports import _emit_json
from pds_core.roster_edits import (
    RosterEditOperation,
    StudentRosterChange,
    StudentRosterEditClassNotFoundError,
    StudentRosterEditCommitResult,
    StudentRosterEditConflictError,
    StudentRosterEditError,
    StudentRosterEditPreview,
    StudentRosterEditRequestError,
    StudentRosterEditValidationError,
    StudentRosterEditWriteError,
    commit_student_roster_edit,
    plan_student_roster_edit,
)
from pds_core.rosters import StudentRecord
from pds_core.standards import StandardsLibrary

MAX_CHANGE_FILE_BYTES = 16_384
MAX_CHANGED_FIELDS = 64

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_NOT_FOUND = 3
EXIT_STALE = 4
EXIT_STORAGE = 5
EXIT_WRITE = 6
EXIT_UNCERTAIN = 7


class RosterEditChangeFileError(ValueError):
    """Malformed or unreadable bounded change input; contains no input data."""


def _raise_duplicate_key(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RosterEditChangeFileError(
                "Change JSON contains a repeated key."
            )
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise RosterEditChangeFileError("Change JSON contains an invalid number.")


def _read_change_file(path: str) -> StudentRosterChange:
    try:
        if path == "-":
            if sys.stdin.isatty():
                raise RosterEditChangeFileError(
                    "Redirect stdin or provide a change file; no prompt is available."
                )
            stream = getattr(sys.stdin, "buffer", None)
            if stream is None:
                raw = sys.stdin.read(MAX_CHANGE_FILE_BYTES + 1).encode("utf-8")
            else:
                raw = cast(bytes, stream.read(MAX_CHANGE_FILE_BYTES + 1))
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(MAX_CHANGE_FILE_BYTES + 1)
    except (OSError, UnicodeError) as error:
        raise RosterEditChangeFileError(
            "Could not read the bounded UTF-8 change source."
        ) from error

    if len(raw) > MAX_CHANGE_FILE_BYTES:
        raise RosterEditChangeFileError("Change JSON exceeds the supported size.")
    try:
        document: object = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=_raise_duplicate_key,
            parse_constant=_reject_constant,
        )
    except (
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise RosterEditChangeFileError(
            "Change source must contain valid UTF-8 JSON."
        ) from error

    if not isinstance(document, dict):
        raise RosterEditChangeFileError("Change JSON must be one object.")
    if set(document) - {"schema_version", "operation", "student_id", "fields"}:
        raise RosterEditChangeFileError(
            "Change JSON contains unsupported top-level keys."
        )
    if document.get("schema_version") != "1":
        raise RosterEditChangeFileError(
            "Change JSON must use schema_version 1."
        )
    operation = document.get("operation")
    student_id = document.get("student_id")
    if type(operation) is not str or operation not in {"add", "update", "remove"}:
        raise RosterEditChangeFileError("Change JSON operation is invalid.")
    if type(student_id) is not str:
        raise RosterEditChangeFileError("Change JSON student identity is invalid.")

    if "fields" not in document and operation != "remove":
        raise RosterEditChangeFileError("Change JSON fields are required.")
    fields: object = document.get("fields", {})
    if not isinstance(fields, dict):
        raise RosterEditChangeFileError("Change JSON fields must be an object.")
    if len(fields) > MAX_CHANGED_FIELDS:
        raise RosterEditChangeFileError("Too many change fields.")
    if any(type(key) is not str or type(value) is not str
           for key, value in fields.items()):
        raise RosterEditChangeFileError("Change JSON fields must map strings.")

    return StudentRosterChange(
        operation=cast(RosterEditOperation, operation),
        student_id=student_id,
        fields=cast(Mapping[str, str], fields),
    )


def _safe_text(value: str) -> str:
    return "".join(
        char
        if not unicodedata.category(char).startswith("C")
        else "\ufffd"
        for char in value
    )


def _record_field(record: StudentRecord, name: str) -> str:
    if name in {"first_name", "last_name", "period"}:
        return cast(str, getattr(record, name))
    return record.extra_fields.get(name, "")


def _selected_fields(preview: StudentRosterEditPreview) -> tuple[str, ...]:
    if preview.operation == "remove":
        return ("first_name", "last_name", "period")
    return preview.changed_fields


def _record_selection(
    record: StudentRecord | None,
    fields: tuple[str, ...],
) -> dict[str, str] | None:
    if record is None:
        return None
    return {field: _record_field(record, field) for field in fields}


def _preview_data(preview: StudentRosterEditPreview) -> dict[str, object]:
    fields = _selected_fields(preview)
    return {
        "class_id": preview.class_id,
        "operation": preview.operation,
        "student_id": preview.student_id,
        "current_roster_present": preview.current_roster_present,
        "current_state_token": preview.current_state_token,
        "candidate_state_token": preview.candidate_state_token,
        "counts": {
            "before": preview.current_count,
            "after": preview.proposed_count,
        },
        "changed_fields": list(preview.changed_fields),
        "before": _record_selection(preview.current_record, fields),
        "after": _record_selection(preview.proposed_record, fields),
        "no_change": preview.no_change,
        "saved": False,
    }


def _emit_preview_text(
    preview: StudentRosterEditPreview, output: TextIO
) -> None:
    data = _preview_data(preview)
    print("Individual student roster edit preview", file=output)
    print(f"Class: {preview.class_id}", file=output)
    print(f"Action: {preview.operation}", file=output)
    print(f"Student ID: {preview.student_id}", file=output)
    print(
        f"Enrollment count: {preview.current_count} -> {preview.proposed_count}",
        file=output,
    )
    before = cast(dict[str, str] | None, data["before"])
    after = cast(dict[str, str] | None, data["after"])
    if preview.no_change:
        print("Requested fields already match; no change will be written.", file=output)
    else:
        for field in _selected_fields(preview):
            previous = "-" if before is None else _safe_text(before[field])
            proposed = "-" if after is None else _safe_text(after[field])
            print(f"{field}: {previous!r} -> {proposed!r}", file=output)
    print(f"Current state token: {preview.current_state_token}", file=output)
    print(f"Candidate state token: {preview.candidate_state_token}", file=output)
    print("Status: PREVIEW ONLY - NO WRITE", file=output)


def _commit_data(result: StudentRosterEditCommitResult) -> dict[str, object]:
    return {
        "class_id": result.class_id,
        "operation": result.operation,
        "student_id": result.student_id,
        "status": result.outcome,
        "previous_state_token": result.previous_state_token,
        "committed_state_token": result.committed_state_token,
    }


def _emit_commit_text(
    result: StudentRosterEditCommitResult, output: TextIO
) -> None:
    print("Individual student roster edit result", file=output)
    print(f"Class: {result.class_id}", file=output)
    print(f"Action: {result.operation}", file=output)
    print(f"Student ID: {result.student_id}", file=output)
    print(f"Previous state token: {result.previous_state_token}", file=output)
    print(f"Committed state token: {result.committed_state_token}", file=output)
    print(f"Status: {result.outcome.upper()}", file=output)


_ERROR_MESSAGES: Mapping[str, str] = {
    "invalid_change_file": "Change JSON cannot be read or validated safely.",
    "invalid_operation": "The requested roster action is not supported.",
    "invalid_student_id": "The selected student ID is invalid.",
    "invalid_class_id": "The selected class ID is invalid.",
    "invalid_workspace": "The selected workspace is invalid.",
    "invalid_fields": "The supplied roster fields are invalid.",
    "immutable_identity": "Class and student IDs cannot be modified.",
    "missing_required_field": "Required student fields are missing.",
    "invalid_change": "The roster change request is invalid.",
    "invalid_token": "The reviewed roster state tokens are invalid.",
    "not_confirmed": "An explicit confirmation is required.",
    "missing_class": "The selected class does not exist.",
    "missing_class_metadata": "First add requires valid class metadata.",
    "duplicate_student": "The student is already enrolled in this class.",
    "missing_student": "The student is absent from this class roster.",
    "invalid_student": "The proposed student data failed validation.",
    "invalid_roster": "The current roster failed validation.",
    "empty_roster": "The final student cannot be removed.",
    "unsupported_field": "An edited field is absent from roster columns.",
    "current_state_changed": "Roster changed; preview again before committing.",
    "candidate_changed": "Proposed change differs from the reviewed preview.",
    "write_conflict": "Another roster writer is active; preview again.",
    "read_failed": "Canonical roster cannot be read safely.",
    "path_failed": "Canonical class path cannot be inspected safely.",
    "unsafe_path": "Canonical roster path is redirected; operation refused.",
    "write_failed": "Canonical roster could not be written.",
    "lock_failed": "Canonical roster write lock could not be managed.",
    "write_outcome_uncertain": (
        "Write outcome uncertain; inspect the canonical roster before retrying."
    ),
}


def _error_code(error: BaseException) -> tuple[int, str, str]:
    if isinstance(error, RosterEditChangeFileError):
        reason = "invalid_change_file"
        return EXIT_INPUT, reason, _ERROR_MESSAGES[reason]
    if not isinstance(error, StudentRosterEditError):
        return EXIT_STORAGE, "unavailable", "Roster edit is unavailable."
    reason = error.reason
    if reason not in _ERROR_MESSAGES:
        return EXIT_STORAGE, "unavailable", "Roster edit is unavailable."
    if isinstance(error, StudentRosterEditConflictError):
        status = EXIT_STALE
    elif isinstance(error, StudentRosterEditClassNotFoundError):
        status = EXIT_NOT_FOUND
    elif isinstance(error, StudentRosterEditValidationError):
        status = EXIT_NOT_FOUND if reason == "missing_student" else EXIT_INPUT
        if reason == "invalid_roster":
            status = EXIT_STORAGE
    elif isinstance(error, StudentRosterEditWriteError):
        status = (
            EXIT_UNCERTAIN if reason == "write_outcome_uncertain"
            else EXIT_STORAGE if reason in {"read_failed", "path_failed", "unsafe_path"}
            else EXIT_WRITE
        )
    elif isinstance(error, StudentRosterEditRequestError):
        status = EXIT_INPUT
    else:
        status = EXIT_STORAGE
    return status, reason, _ERROR_MESSAGES[reason]


def _failure(
    args: argparse.Namespace,
    command: str,
    error: BaseException,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    status, reason, message = _error_code(error)
    code = f"roster_student.{reason}"
    if args.format == "json":
        _emit_json(
            command,
            args.workspace_root,
            False,
            {},
            stdout,
            error_code=code,
            error_message=message,
        )
    else:
        print(f"Error [{code}]: {message}", file=stderr)
    return status


def handle_student_roster_preview(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Return one strictly non-mutating student edit preview."""
    try:
        change = _read_change_file(args.change_file)
        preview = plan_student_roster_edit(
            args.workspace_root, args.class_id, change
        )
    except (RosterEditChangeFileError, StudentRosterEditError) as error:
        return _failure(args, "roster student-preview", error, stdout, stderr)
    if args.format == "json":
        _emit_json(
            "roster student-preview",
            args.workspace_root,
            True,
            _preview_data(preview),
            stdout,
        )
    else:
        _emit_preview_text(preview, stdout)
    return EXIT_OK


def handle_student_roster_commit(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Commit exactly the reviewed candidate with explicit CLI confirmation."""
    try:
        change = _read_change_file(args.change_file)
        result = commit_student_roster_edit(
            args.workspace_root,
            args.class_id,
            change,
            expected_current_state_token=args.expected_current_state_token,
            expected_candidate_state_token=args.expected_candidate_state_token,
            confirmed=args.confirm,
        )
    except (RosterEditChangeFileError, StudentRosterEditError) as error:
        return _failure(args, "roster student-commit", error, stdout, stderr)
    if args.format == "json":
        _emit_json(
            "roster student-commit",
            args.workspace_root,
            True,
            _commit_data(result),
            stdout,
        )
    else:
        _emit_commit_text(result, stdout)
    return EXIT_OK
