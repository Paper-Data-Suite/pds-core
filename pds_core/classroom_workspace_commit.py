"""Guarded workspace preference commits for Core #242 C2A.

The local lock coordinates this new writer, not legacy writers or cloud sync.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pds_core import workspace
from pds_core.classroom_workspace_preference import (
    WorkspacePreferenceChange,
    WorkspacePreferencePlanError,
    WorkspacePreferencePreview,
    _config_fingerprint,
    plan_workspace_preference_change,
)

WorkspaceCommitOutcome = Literal["committed", "no_change"]
_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")


class WorkspacePreferenceCommitError(Exception):
    """A teacher-safe refusal with a stable reason."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class WorkspacePreferenceConflictError(WorkspacePreferenceCommitError):
    """The reviewed state, candidate, or local writer lock changed."""


class WorkspacePreferenceWriteError(WorkspacePreferenceCommitError):
    """Write failure, including uncertain canonical outcomes."""


@dataclass(frozen=True, slots=True)
class GuardedWorkspacePreferencePreview:
    proposal: WorkspacePreferencePreview
    current_state_token: str
    candidate_state_token: str


@dataclass(frozen=True, slots=True)
class WorkspacePreferenceCommitResult:
    operation: str
    outcome: WorkspaceCommitOutcome
    previous_saved_root: Path | None
    saved_root: Path | None
    previous_state_token: str
    committed_state_token: str


def _candidate_token(value: WorkspacePreferencePreview) -> str:
    content: dict[str, object] = {
        "schema": "core242-preference-v1",
        "operation": value.operation,
        "before": str(value.previous_saved_root),
        "after": str(value.proposed_saved_root),
        "effective_before": str(value.current_effective_root),
        "effective_after": str(value.proposed_effective_root),
        "source": value.current_resolution_source,
        "target_exists": value.target_exists,
        "current_token": value.config_state_token,
    }
    serialized = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def plan_guarded_workspace_preference_change(
    change: WorkspacePreferenceChange,
) -> GuardedWorkspacePreferencePreview:
    """Pair C1's read-only preview with an exact-candidate token."""
    proposal = plan_workspace_preference_change(change)
    return GuardedWorkspacePreferencePreview(
        proposal,
        proposal.config_state_token,
        _candidate_token(proposal),
    )


def _require_token(value: str) -> None:
    if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
        raise WorkspacePreferenceCommitError(
            "invalid_token", "Reviewed workspace state token is invalid."
        )


def _plan(change: WorkspacePreferenceChange) -> GuardedWorkspacePreferencePreview:
    try:
        return plan_guarded_workspace_preference_change(change)
    except WorkspacePreferencePlanError as error:
        raise WorkspacePreferenceCommitError(error.reason, str(error)) from error


def _check_tokens(
    review: GuardedWorkspacePreferencePreview,
    current: str,
    candidate: str,
) -> None:
    if review.current_state_token != current:
        raise WorkspacePreferenceConflictError(
            "current_state_changed",
            "Saved workspace preference changed. Preview again.",
        )
    if review.candidate_state_token != candidate:
        raise WorkspacePreferenceConflictError(
            "candidate_changed", "Proposed workspace change differs from preview."
        )


def _guard_path(path: Path) -> None:
    for checked in (path.parent, path):
        try:
            junction = getattr(checked, "is_junction", None)
            if (
                checked.is_symlink()
                or (junction is not None and junction())
                or checked.resolve(strict=False) != checked
            ):
                raise WorkspacePreferenceCommitError(
                    "unsafe_path", "Workspace configuration path is redirected."
                )
        except (OSError, RuntimeError) as error:
            raise WorkspacePreferenceCommitError(
                "path_unavailable", "Workspace configuration path is unavailable."
            ) from error


@contextmanager
def _local_lock(config_path: Path) -> Iterator[None]:
    _guard_path(config_path)
    parent = config_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise WorkspacePreferenceWriteError(
            "lock_failed", "Workspace preference lock directory is unavailable."
        ) from error
    _guard_path(config_path)
    lock = parent / ".workspace-preference.write.lock"
    _guard_path(lock)
    owned = False
    try:
        try:
            with lock.open("x", encoding="utf-8"):
                owned = True
        except FileExistsError as error:
            raise WorkspacePreferenceConflictError(
                "write_conflict", "Another local preference writer is active."
            ) from error
        except OSError as error:
            raise WorkspacePreferenceWriteError(
                "lock_failed", "Workspace preference lock could not be created."
            ) from error
        yield
    finally:
        if owned:
            try:
                lock.unlink(missing_ok=True)
            except OSError:
                pass


def _receipt(
    review: GuardedWorkspacePreferencePreview,
    outcome: WorkspaceCommitOutcome,
    token: str,
) -> WorkspacePreferenceCommitResult:
    proposal = review.proposal
    return WorkspacePreferenceCommitResult(
        operation=proposal.operation,
        outcome=outcome,
        previous_saved_root=proposal.previous_saved_root,
        saved_root=proposal.proposed_saved_root,
        previous_state_token=review.current_state_token,
        committed_state_token=token,
    )


def commit_guarded_workspace_preference_change(
    change: WorkspacePreferenceChange,
    *,
    expected_current_state_token: str,
    expected_candidate_state_token: str,
    confirmed: bool,
) -> WorkspacePreferenceCommitResult:
    """Commit a reviewed change; no distributed CAS guarantee is implied."""
    if confirmed is not True:
        raise WorkspacePreferenceCommitError(
            "not_confirmed", "Explicit confirmation is required."
        )
    _require_token(expected_current_state_token)
    _require_token(expected_candidate_state_token)
    if not isinstance(change, WorkspacePreferenceChange):
        raise WorkspacePreferenceCommitError(
            "invalid_change", "Workspace preference change is invalid."
        )

    first = _plan(change)
    _check_tokens(first, expected_current_state_token, expected_candidate_state_token)
    config_path = workspace.get_workspace_config_path()
    _guard_path(config_path)

    if first.proposal.no_change:
        fresh = _plan(change)
        _check_tokens(
            fresh, expected_current_state_token, expected_candidate_state_token
        )
        return _receipt(fresh, "no_change", fresh.current_state_token)

    with _local_lock(config_path):
        fresh = _plan(change)
        _check_tokens(
            fresh, expected_current_state_token, expected_candidate_state_token
        )
        proposal = fresh.proposal
        if proposal.no_change:
            return _receipt(fresh, "no_change", fresh.current_state_token)
        try:
            if proposal.operation == "set":
                assert proposal.proposed_saved_root is not None
                workspace.ensure_workspace_root(proposal.proposed_saved_root)
                workspace.save_workspace_root(proposal.proposed_saved_root)
            else:
                workspace.clear_saved_workspace_root()
            persisted = workspace.load_workspace_config().workspace_root
            if persisted != proposal.proposed_saved_root:
                raise WorkspacePreferenceWriteError(
                    "write_outcome_uncertain",
                    "Workspace state is uncertain; inspect before retrying.",
                )
            committed = _config_fingerprint(config_path)
        except WorkspacePreferenceWriteError:
            raise
        except (workspace.WorkspaceRootError, WorkspacePreferencePlanError, OSError):
            raise WorkspacePreferenceWriteError(
                "write_outcome_uncertain",
                "Write outcome is uncertain; inspect before retrying.",
            ) from None

        return _receipt(fresh, "committed", committed)
