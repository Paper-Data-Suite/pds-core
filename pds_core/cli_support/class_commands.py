"""Script-safe CLI parity for reviewed empty-class creation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from pds_core.classroom_admin_preview import ClassCreationChange
from pds_core.classroom_class_commit import (
    ClassCreationConflictError,
    ClassCreationError,
    ClassCreationWriteError,
    commit_guarded_class_creation,
    inspect_class_creation_recovery,
    plan_guarded_class_creation,
)
from pds_core.standards import StandardsLibrary
from pds_core.workspace import WorkspaceRootError, resolve_workspace_root

_INPUT = {"not_confirmed", "invalid_change", "invalid_class",
          "invalid_timestamp", "invalid_token"}
_STALE = {"class_exists", "no_open_year", "year_mismatch", "write_conflict",
          "current_state_changed", "candidate_changed", "stale_year_state"}
_STORAGE = {"invalid_workspace", "missing_workspace", "unsafe_path",
            "unavailable_path", "inspection_failed", "invalid_year_state",
            "invalid_school_year", "oversized_year_state", "unavailable_year_state",
            "invalid_metadata", "invalid_classes", "classes_unavailable",
            "invalid_roster", "lock_failed"}


def _root(args: argparse.Namespace) -> Path:
    try:
        root = resolve_workspace_root(args.workspace)
        if not root.is_dir():
            raise ClassCreationError(
                "missing_workspace", "An existing workspace is required."
            )
    except (WorkspaceRootError, OSError):
        raise ClassCreationError(
            "invalid_workspace", "Selected workspace is invalid."
        ) from None
    return root


def _emit(
    args: argparse.Namespace,
    command: str,
    data: dict[str, object],
    stdout: TextIO,
    stderr: TextIO,
    *,
    reason: str | None = None,
    message: str = "",
    code: int = 0,
) -> int:
    if args.format == "json":
        payload: dict[str, object] = {
            "schema_version": "1",
            "command": command,
            "scope": "class",
            "ok": reason is None,
            "data": data,
        }
        if reason is not None:
            payload["error"] = {"code": f"class.{reason}", "message": message}
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True), file=stdout)
    else:
        if reason is not None:
            print(f"Error [class.{reason}]: {message}", file=stderr)
        for key, value in data.items():
            print(f"{key}: {json.dumps(value, ensure_ascii=True)}", file=stdout)
    return code


def _failure(
    args: argparse.Namespace,
    command: str,
    error: ClassCreationError,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    data: dict[str, object] = {}
    reason = error.reason
    if isinstance(error, ClassCreationWriteError):
        reason = "write_incomplete"
        data = {
            "status": error.outcome,
            "changed_scopes": [] if error.outcome == "no_change" else ["CLASS"],
            "revalidation_required": True,
        }
        code = 6 if error.outcome == "no_change" else 7
        message = "Class creation incomplete; inspect canonical state before retry."
    elif reason in _INPUT:
        code = 2
        message = "Class creation input or confirmation is invalid."
    elif reason in _STALE:
        code = 4
        message = "Class proposal is unavailable or stale; preview again."
    elif reason in _STORAGE:
        code = 5
        message = "Canonical classroom state cannot be accessed safely."
    elif isinstance(error, ClassCreationConflictError):
        reason = "unavailable"
        code = 4
        message = "Class proposal cannot be safely reviewed."
    else:
        reason = "unavailable"
        code = 5
        message = "Class operation is unavailable."
    return _emit(
        args, command, data, stdout, stderr,
        reason=reason, message=message, code=code,
    )


def handle_class_creation(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    operation = args.workspace_command
    command = f"workspace {operation}"
    try:
        root = _root(args)
        change = ClassCreationChange(args.class_id, args.school_year)
        data: dict[str, object] = {
            "operation": "create_class",
            "workspace_root": str(root),
            "class_id": change.class_id,
            "school_year": change.school_year,
            "created_at": args.created_at.isoformat(),
        }
        if operation == "class-preview":
            review = plan_guarded_class_creation(
                root, change, created_at=args.created_at
            )
            data.update({
                "workspace_root": str(review.proposal.workspace_root),
                "target_class_directory": str(review.proposal.target_class_directory),
                "metadata_would_be_created": True,
                "roster_would_be_created": False,
                "current_state_token": review.current_state_token,
                "candidate_state_token": review.candidate_state_token,
                "status": "preview",
                "saved": False,
            })
        elif operation == "class-commit":
            result = commit_guarded_class_creation(
                root,
                change,
                created_at=args.created_at,
                expected_current_state_token=args.expected_current_state_token,
                expected_candidate_state_token=args.expected_candidate_state_token,
                confirmed=args.confirm,
            )
            data.update({
                "workspace_root": str(result.workspace_root),
                "metadata_path": str(result.metadata_path),
                "status": result.outcome,
                "changed_scopes": ["CLASS"],
                "revalidation_required": True,
            })
        elif operation == "class-recovery":
            observed = inspect_class_creation_recovery(
                root, change, created_at=args.created_at
            )
            data.update({
                "status": observed,
                "saved": False,
                "ownership_established": False,
                "revalidation_required": True,
                "retry_authorized": False,
            })
        else:
            raise ClassCreationError("invalid_change", "Invalid class command.")
    except ClassCreationError as error:
        return _failure(args, command, error, stdout, stderr)
    return _emit(args, command, data, stdout, stderr)
