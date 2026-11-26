"""Script-safe guarded Standards profile membership commands."""

from __future__ import annotations

import argparse
import json
from typing import TextIO, cast

from pds_core.classroom_standards_commit import (
    MembershipAction,
    ProfileMembershipChange,
    StandardsReviewConflict,
    StandardsReviewError,
    StandardsReviewWriteError,
    commit_profile_membership,
    inspect_standards_snapshot,
    plan_profile_membership,
)
from pds_core.standards import StandardsLibrary, standards_library_to_dict
from pds_core.workspace import WorkspaceRootError, resolve_workspace_root


def handle_guarded_standards(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    operation = args.workspace_command
    command = f"workspace {operation}"
    data: dict[str, object] = {}
    error: dict[str, str] | None = None
    code = 0
    try:
        try:
            root = resolve_workspace_root(args.workspace)
        except (WorkspaceRootError, OSError):
            raise StandardsReviewError(
                "invalid_workspace", "Selected workspace is invalid."
            ) from None
        if operation == "standards-inspect":
            snapshot = inspect_standards_snapshot(root)
            data = {
                "workspace_root": str(snapshot.workspace_root),
                "present": snapshot.present,
                "state_token": snapshot.state_token,
                "library": standards_library_to_dict(snapshot.library),
                "saved": False,
            }
        else:
            change = ProfileMembershipChange(
                cast(MembershipAction, args.action),
                args.profile_id,
                tuple(args.standard_ids),
            )
            if operation == "standards-preview":
                review = plan_profile_membership(root, change)
                data = {
                    "workspace_root": str(review.snapshot.workspace_root),
                    "action": change.action,
                    "profile_id": change.profile_id,
                    "before": review.before,
                    "after": review.after,
                    "current_state_token": review.snapshot.state_token,
                    "candidate_state_token": review.candidate_state_token,
                    "status": "preview",
                    "saved": False,
                }
            elif operation == "standards-commit":
                result = commit_profile_membership(
                    root, change,
                    expected_current_state_token=args.expected_current_state_token,
                    expected_candidate_state_token=args.expected_candidate_state_token,
                    confirmed=args.confirm,
                )
                data = {
                    "workspace_root": str(result.workspace_root),
                    "profile_id": result.profile_id,
                    "before": result.before,
                    "after": result.after,
                    "status": result.outcome,
                    "state_token": result.state_token,
                    "changed_scopes": ["STANDARDS"] if result.outcome == "committed" else [],
                    "revalidation_required": True,
                }
            else:
                raise StandardsReviewError("invalid_change", "Invalid operation.")
    except StandardsReviewError as exc:
        reason = exc.reason
        if isinstance(exc, StandardsReviewWriteError):
            code = 7
            data = {
                "status": "indeterminate",
                "changed_scopes": ["STANDARDS"],
                "revalidation_required": True,
            }
        elif isinstance(exc, StandardsReviewConflict):
            code = 4
        elif reason in {"invalid_change", "invalid_profile", "invalid_membership",
                        "not_confirmed", "invalid_token"}:
            code = 2
        else:
            code = 5
        error = {"code": f"standards.{reason}", "message": str(exc)}
    if args.format == "json":
        payload: dict[str, object] = {
            "schema_version": "1", "command": command, "scope": "standards",
            "ok": error is None, "data": data,
        }
        if error is not None:
            payload["error"] = error
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True), file=stdout)
    else:
        if error is not None:
            print(f"Error [{error['code']}]: {error['message']}", file=stderr)
        for key, value in data.items():
            print(f"{key}: {json.dumps(value, ensure_ascii=True)}", file=stdout)
    return code
