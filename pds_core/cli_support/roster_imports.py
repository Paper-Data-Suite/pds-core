"""Non-interactive CLI handlers for guarded full-roster import."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

import pds_core.roster_imports as roster_import_service
from pds_core.identifiers import IdentifierValidationError
from pds_core.roster_imports import (
    RosterImportCandidateChangedError,
    RosterImportClassMismatchError,
    RosterImportConflictError,
    RosterImportCommitResult,
    RosterImportPreview,
    RosterImportRequestError,
    RosterImportWriteError,
)
from pds_core.rosters import (
    RosterError,
    RosterReadError,
    RosterValidationError,
    RosterWriteError,
)
from pds_core.standards import StandardsLibrary


def _emit_json(
    command: str,
    workspace: Path,
    ok: bool,
    data: object,
    stdout: TextIO,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": "1",
        "command": command,
        "workspace": workspace.as_posix(),
        "ok": ok,
        "data": data,
    }
    if error_code is not None and error_message is not None:
        payload["error"] = {
            "code": error_code,
            "message": error_message,
        }
    print(
        json.dumps(
            payload,
            sort_keys=True,
            allow_nan=False,
            ensure_ascii=False,
        ),
        file=stdout,
    )


def _preview_data(preview: RosterImportPreview) -> dict[str, object]:
    return {
        "class_id": preview.class_id,
        "current_roster_present": preview.current_roster_present,
        "current_state_token": preview.current_state_token,
        "candidate_state_token": preview.candidate_state_token,
        "counts": {
            "added": preview.addition_count,
            "changed": preview.change_count,
            "removed": preview.removal_count,
            "unchanged": preview.unchanged_count,
        },
        "added_student_ids": [record.student_id for record in preview.additions],
        "changed_student_ids": [change.student_id for change in preview.changes],
        "removed_student_ids": [record.student_id for record in preview.removals],
        "unchanged_student_ids": list(preview.unchanged_student_ids),
    }


def _print_ids(label: str, values: list[str], stdout: TextIO) -> None:
    rendered = ", ".join(values) if values else "-"
    print(f"{label}: {rendered}", file=stdout)


def _emit_preview_text(
    args: argparse.Namespace,
    preview: RosterImportPreview,
    stdout: TextIO,
) -> None:
    print("Roster import preview", file=stdout)
    print(f"Workspace: {args.workspace_root}", file=stdout)
    print(f"Class: {preview.class_id}", file=stdout)
    print(f"Candidate: {args.candidate_csv}", file=stdout)
    print(
        "Current roster: "
        f"{'present' if preview.current_roster_present else 'absent'}",
        file=stdout,
    )
    print(f"Added: {preview.addition_count}", file=stdout)
    print(f"Changed: {preview.change_count}", file=stdout)
    print(f"Removed: {preview.removal_count}", file=stdout)
    print(f"Unchanged: {preview.unchanged_count}", file=stdout)
    _print_ids(
        "Added student IDs",
        [record.student_id for record in preview.additions],
        stdout,
    )
    _print_ids(
        "Changed student IDs",
        [change.student_id for change in preview.changes],
        stdout,
    )
    _print_ids(
        "Removed student IDs",
        [record.student_id for record in preview.removals],
        stdout,
    )
    print(f"Current state token: {preview.current_state_token}", file=stdout)
    print(f"Candidate state token: {preview.candidate_state_token}", file=stdout)
    print("Status: PREVIEW ONLY - NO WRITE", file=stdout)


def _commit_data(result: RosterImportCommitResult) -> dict[str, object]:
    return {
        "class_id": result.class_id,
        "student_count": len(result.roster.students),
        "previous_state_token": result.previous_state_token,
        "committed_state_token": result.committed_state_token,
    }


def _emit_commit_text(result: RosterImportCommitResult, stdout: TextIO) -> None:
    print("Roster import committed", file=stdout)
    print(f"Class: {result.class_id}", file=stdout)
    print(f"Students: {len(result.roster.students)}", file=stdout)
    print(f"Previous state token: {result.previous_state_token}", file=stdout)
    print(f"Committed state token: {result.committed_state_token}", file=stdout)
    print("Status: COMMITTED", file=stdout)


def _safe_error(
    error: BaseException,
    *,
    candidate_path: Path | None = None,
) -> tuple[str, str]:
    if isinstance(error, RosterImportCandidateChangedError):
        return (
            "roster_import.candidate_changed",
            "Candidate roster changed after preview; create a new preview before committing.",
        )
    if isinstance(error, RosterImportConflictError):
        if error.expected_state_token is None:
            return (
                "roster_import.write_conflict",
                "Another canonical roster write is in progress; create a fresh preview and retry.",
            )
        return (
            "roster_import.current_state_changed",
            "Canonical roster changed after preview; create a new preview before committing.",
        )
    if isinstance(error, RosterImportClassMismatchError):
        return (
            "roster_import.class_mismatch",
            "Candidate roster class_id does not match the requested target class_id.",
        )
    if isinstance(error, RosterValidationError):
        return (
            "roster_import.validation_failed",
            "Candidate or canonical roster failed Core roster validation.",
        )
    if isinstance(error, RosterReadError):
        if candidate_path is not None:
            try:
                candidate = candidate_path.resolve(strict=False)
                failed_path = error.path.resolve(strict=False)
            except (OSError, RuntimeError):
                candidate = candidate_path
                failed_path = error.path
            if failed_path == candidate:
                return (
                    "roster_import.candidate_read_failed",
                    "Candidate roster CSV could not be read.",
                )
        return (
            "roster_import.current_read_failed",
            "Canonical roster state could not be read safely.",
        )
    if isinstance(error, RosterImportRequestError):
        return (
            "roster_import.invalid_request",
            "Roster import request or guarded state token is invalid.",
        )
    if isinstance(error, (RosterImportWriteError, RosterWriteError)):
        return (
            "roster_import.write_failed",
            "Canonical roster could not be written safely.",
        )
    if isinstance(error, IdentifierValidationError):
        return (
            "roster_import.invalid_class_id",
            "Requested class_id is not a valid Core identifier.",
        )
    return (
        "roster_import.failed",
        "Roster import operation failed.",
    )


def _emit_error(
    args: argparse.Namespace,
    command: str,
    error: BaseException,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    code, message = _safe_error(
        error,
        candidate_path=Path(args.candidate_csv),
    )
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
    return 1


def handle_roster_import_preview(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Render one read-only guarded full-roster import preview."""
    try:
        preview = roster_import_service.plan_roster_import(
            args.workspace_root,
            args.class_id,
            args.candidate_csv,
        )
    except (IdentifierValidationError, RosterError) as error:
        return _emit_error(
            args,
            "roster import-preview",
            error,
            stdout,
            stderr,
        )

    if args.format == "json":
        _emit_json(
            "roster import-preview",
            args.workspace_root,
            True,
            _preview_data(preview),
            stdout,
        )
    else:
        _emit_preview_text(args, preview, stdout)
    return 0


def handle_roster_import_commit(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Commit exactly one previously reviewed guarded full-roster import."""
    try:
        result = roster_import_service.commit_roster_import(
            args.workspace_root,
            args.class_id,
            args.candidate_csv,
            expected_current_state_token=args.expected_current_state_token,
            expected_candidate_state_token=args.expected_candidate_state_token,
        )
    except (IdentifierValidationError, RosterError) as error:
        return _emit_error(
            args,
            "roster import-commit",
            error,
            stdout,
            stderr,
        )

    if args.format == "json":
        _emit_json(
            "roster import-commit",
            args.workspace_root,
            True,
            _commit_data(result),
            stdout,
        )
    else:
        _emit_commit_text(result, stdout)
    return 0
