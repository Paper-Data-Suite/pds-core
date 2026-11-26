"""Read-only workspace-preference change previews for Core #242 C1.

Existing Core workspace functions remain authoritative. This planning
module creates no preference, workspace, marker, or lock. Its fingerprint
is a snapshot for a later guarded service, not an authorization token.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pds_core import workspace

WorkspacePreferenceOperation = Literal["set", "reset"]
_MAX_CONFIG_BYTES = 16 * 1024


class WorkspacePreferencePlanError(Exception):
    """A bounded diagnostic that never exposes underlying private paths."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class WorkspacePreferenceChange:
    operation: WorkspacePreferenceOperation
    target_root: str | Path | None = None

    def __post_init__(self) -> None:
        if self.operation not in ("set", "reset"):
            raise ValueError("operation must be set or reset")
        if self.operation == "set":
            if not isinstance(self.target_root, (str, Path)):
                raise ValueError("set requires a target workspace path")
        elif self.target_root is not None:
            raise ValueError("reset cannot specify a target workspace path")


@dataclass(frozen=True, slots=True)
class WorkspacePreferencePreview:
    operation: WorkspacePreferenceOperation
    previous_saved_root: Path | None
    proposed_saved_root: Path | None
    current_effective_root: Path
    proposed_effective_root: Path
    current_resolution_source: str
    environment_override_active: bool
    target_exists: bool | None
    target_would_be_created: bool
    no_change: bool
    config_state_token: str


def _config_fingerprint(config_path: Path) -> str:
    """Record exact configuration bytes without disclosing their contents."""
    try:
        junction = getattr(config_path, "is_junction", None)
        if config_path.is_symlink() or (junction is not None and junction()):
            raise WorkspacePreferencePlanError(
                "redirected_config",
                "The saved workspace preference path is redirected.",
            )
        if not config_path.exists():
            blob = b"missing"
        else:
            if not config_path.is_file():
                raise WorkspacePreferencePlanError(
                    "invalid_config",
                    "The saved workspace preference is not a regular file.",
                )
            if config_path.stat().st_size > _MAX_CONFIG_BYTES:
                raise WorkspacePreferencePlanError(
                    "oversized_config",
                    "The saved workspace preference exceeds the review limit.",
                )
            data = config_path.read_bytes()
            if len(data) > _MAX_CONFIG_BYTES:
                raise WorkspacePreferencePlanError(
                    "oversized_config",
                    "The saved workspace preference exceeds the review limit.",
                )
            blob = b"present\x00" + data
    except (OSError, RuntimeError) as error:
        raise WorkspacePreferencePlanError(
            "unreadable_config",
            "The saved workspace preference cannot be inspected safely.",
        ) from error
    digest = hashlib.sha256()
    digest.update(b"pds-workspace-preference-preview-v1\x00")
    digest.update(str(config_path).encode("utf-8"))
    digest.update(b"\x00")
    digest.update(blob)
    return digest.hexdigest()


def plan_workspace_preference_change(
    change: WorkspacePreferenceChange,
) -> WorkspacePreferencePreview:
    """Inspect a possible preference change; never create or save anything.

    The selected workspace is intentionally resolved without caller-provided
    context hints, because those hints are not authoritative preference state.
    """
    if not isinstance(change, WorkspacePreferenceChange):
        raise TypeError("change must be WorkspacePreferenceChange")

    try:
        config_path = workspace.get_workspace_config_path()
        original_token = _config_fingerprint(config_path)
        previous = workspace.load_workspace_config().workspace_root
        effective = workspace.inspect_workspace_root()
        if _config_fingerprint(config_path) != original_token:
            raise WorkspacePreferencePlanError(
                "stale_config",
                "The saved workspace preference changed during the preview.",
            )
    except workspace.WorkspaceRootError as error:
        raise WorkspacePreferencePlanError(
            "invalid_config",
            "The current workspace preference could not be validated.",
        ) from error

    if change.operation == "set":
        assert change.target_root is not None
        if "\x00" in str(change.target_root):
            raise WorkspacePreferencePlanError(
                "invalid_target", "The requested workspace root is invalid."
            )
        try:
            target = workspace.inspect_workspace_root(change.target_root)
        except workspace.WorkspaceRootError as error:
            raise WorkspacePreferencePlanError(
                "invalid_target",
                "The requested workspace root is invalid.",
            ) from error
        if target.exists and not target.is_dir:
            raise WorkspacePreferencePlanError(
                "invalid_target",
                "The requested workspace root is not a directory.",
            )
        if not target.is_writable:
            raise WorkspacePreferencePlanError(
                "unwritable_target",
                "The requested workspace root is not writable.",
            )
        proposed = target.root
        target_exists: bool | None = target.exists
    else:
        proposed = None
        target_exists = None

    if effective.source == "environment":
        proposed_effective = effective.root
    elif proposed is not None:
        proposed_effective = proposed
    else:
        try:
            proposed_effective = workspace.get_default_workspace_root()
        except workspace.WorkspaceRootError as error:
            raise WorkspacePreferencePlanError(
                "invalid_default",
                "The default workspace root could not be resolved.",
            ) from error

    return WorkspacePreferencePreview(
        operation=change.operation,
        previous_saved_root=previous,
        proposed_saved_root=proposed,
        current_effective_root=effective.root,
        proposed_effective_root=proposed_effective,
        current_resolution_source=effective.source,
        environment_override_active=effective.source == "environment",
        target_exists=target_exists,
        target_would_be_created=target_exists is False,
        no_change=previous == proposed,
        config_state_token=original_token,
    )
