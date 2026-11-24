"""Core #242 C3B1: nonmutating school-year and class creation reviews.

These snapshots are not write authorizations. Guarded commits, exact
noninteractive CLI parity, and shared-menu entry remain deferred.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pds_core.classroom_discovery import (
    ClassroomDiscoveryError,
    ClassroomOverview,
    inspect_classroom_overview,
)
from pds_core.identifiers import validate_identifier
from pds_core.routes import class_dir, class_metadata_path, class_roster_path
from pds_core.school_years import (
    SchoolYearState,
    SchoolYearStateError,
    load_school_year_state,
    school_year_state_path,
    validate_school_year,
)
from pds_core.workspace import WorkspaceRootError, inspect_workspace_root

_YEAR_STATE_LIMIT = 64 * 1024
SchoolYearAction = Literal["open", "close"]


class ClassroomAdministrationPreviewError(Exception):
    """A bounded read refusal without raw filesystem exception details."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SchoolYearChange:
    action: SchoolYearAction
    year: str | None = None

    def __post_init__(self) -> None:
        if self.action not in ("open", "close"):
            raise ValueError("Action must be open or close.")
        if self.action == "open":
            if self.year is None:
                raise ValueError("An opening year is required.")
            object.__setattr__(self, "year", validate_school_year(self.year))
        elif self.year is not None:
            raise ValueError("Closing cannot select another school year.")


@dataclass(frozen=True, slots=True)
class SchoolYearChangePreview:
    workspace_root: Path
    action: SchoolYearAction
    previous_record_status: Literal["missing", "open", "closed"]
    previous_school_year: str | None
    proposed_active_year: str | None
    no_change: bool
    state_token: str
    candidate_token: str


@dataclass(frozen=True, slots=True)
class ClassCreationChange:
    class_id: str
    school_year: str

    def __post_init__(self) -> None:
        validate_identifier(self.class_id, "class_id")
        object.__setattr__(
            self, "school_year", validate_school_year(self.school_year)
        )


@dataclass(frozen=True, slots=True)
class ClassCreationPreview:
    workspace_root: Path
    class_id: str
    school_year: str
    active_school_year: str
    target_class_directory: Path
    state_token: str
    candidate_token: str
    metadata_would_be_created: bool
    roster_would_be_created: bool


def _guard(path: Path) -> None:
    """Refuse canonical state and class symlink/junction redirection."""
    try:
        junction = getattr(path, "is_junction", None)
        if (
            path.is_symlink()
            or (junction is not None and junction())
            or path.resolve(strict=False) != path
        ):
            raise ClassroomAdministrationPreviewError(
                "unsafe_path", "A canonical classroom path is redirected."
            )
    except (OSError, RuntimeError) as error:
        raise ClassroomAdministrationPreviewError(
            "unavailable_path", "A canonical classroom path is unavailable."
        ) from error


def _state_fingerprint(path: Path) -> str:
    """Fingerprint exact school-year bytes with bounded reads and path scope."""
    _guard(path.parent)
    _guard(path)
    try:
        if not path.exists():
            content = b"missing"
        else:
            if not path.is_file():
                raise ClassroomAdministrationPreviewError(
                    "invalid_year_state", "School-year state is not a regular file."
                )
            if path.stat().st_size > _YEAR_STATE_LIMIT:
                raise ClassroomAdministrationPreviewError(
                    "oversized_year_state",
                    "School-year state exceeds the review size limit.",
                )
            data = path.read_bytes()
            if len(data) > _YEAR_STATE_LIMIT:
                raise ClassroomAdministrationPreviewError(
                    "oversized_year_state",
                    "School-year state exceeds the review size limit.",
                )
            content = b"present\x00" + data
    except (OSError, RuntimeError) as error:
        raise ClassroomAdministrationPreviewError(
            "unavailable_year_state", "School-year state cannot be inspected."
        ) from error
    digest = hashlib.sha256()
    digest.update(b"core242-school-year-preview-v1\x00")
    digest.update(str(path).encode("utf-8"))
    digest.update(b"\x00")
    digest.update(content)
    return digest.hexdigest()


def _overview(root: str | Path) -> ClassroomOverview:
    if not isinstance(root, (str, Path)):
        raise TypeError("workspace root must be a Path or string")
    try:
        status = inspect_workspace_root(root)
    except WorkspaceRootError as error:
        raise ClassroomAdministrationPreviewError(
            "invalid_workspace", "Selected workspace root is invalid."
        ) from error
    if not status.exists or not status.is_dir:
        raise ClassroomAdministrationPreviewError(
            "missing_workspace", "Select an existing workspace before administration."
        )
    # Size and reparse-point refusal must precede the existing JSON reader.
    _state_fingerprint(school_year_state_path(status.root))
    try:
        overview = inspect_classroom_overview(status.root)
    except ClassroomDiscoveryError as error:
        raise ClassroomAdministrationPreviewError(error.reason, str(error)) from error
    return overview


def _year_snapshot(
    overview: ClassroomOverview,
) -> tuple[SchoolYearState | None, str]:
    path = school_year_state_path(overview.workspace.root)
    before = _state_fingerprint(path)
    try:
        state = load_school_year_state(overview.workspace.root)
    except (SchoolYearStateError, OSError) as error:
        raise ClassroomAdministrationPreviewError(
            "invalid_year_state", "Canonical school-year state is invalid."
        ) from error
    after = _state_fingerprint(path)
    if before != after:
        raise ClassroomAdministrationPreviewError(
            "stale_year_state", "School-year state changed during inspection."
        )
    active = (
        None
        if state is None or state.closed_at is not None
        else state.active_school_year
    )
    if overview.active_school_year != active:
        raise ClassroomAdministrationPreviewError(
            "stale_year_state", "School-year state changed during inspection."
        )
    return state, after


def _candidate(state_token: str, action: str, identity: str) -> str:
    digest = hashlib.sha256()
    digest.update(b"core242-admin-candidate-v1\x00")
    for item in (state_token, action, identity):
        digest.update(item.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def plan_school_year_change(
    root: str | Path, change: SchoolYearChange
) -> SchoolYearChangePreview:
    """Preview initial open, same-year no-op, or close; never replace history."""
    if not isinstance(change, SchoolYearChange):
        raise TypeError("change must be SchoolYearChange")
    overview = _overview(root)
    state, token = _year_snapshot(overview)
    status: Literal["missing", "open", "closed"] = (
        "missing" if state is None else "closed" if state.closed_at else "open"
    )
    previous = None if state is None else state.active_school_year
    no_change = False
    proposed: str | None
    if change.action == "open":
        assert change.year is not None
        proposed = change.year
        if status == "closed":
            raise ClassroomAdministrationPreviewError(
                "year_history_policy_required",
                "Opening a new year would replace closed-year history.",
            )
        if status == "open":
            if previous != proposed:
                raise ClassroomAdministrationPreviewError(
                    "active_year_conflict", "A different school year is open."
                )
            no_change = True
    else:
        proposed = None
        if status != "open":
            raise ClassroomAdministrationPreviewError(
                "no_open_year", "There is no active school year to close."
            )
    return SchoolYearChangePreview(
        workspace_root=overview.workspace.root,
        action=change.action,
        previous_record_status=status,
        previous_school_year=previous,
        proposed_active_year=proposed,
        no_change=no_change,
        state_token=token,
        candidate_token=_candidate(token, change.action, change.year or ""),
    )


def plan_class_creation(
    root: str | Path, change: ClassCreationChange
) -> ClassCreationPreview:
    """Preview creation of a new empty class without touching its folder."""
    if not isinstance(change, ClassCreationChange):
        raise TypeError("change must be ClassCreationChange")
    overview = _overview(root)
    state, token = _year_snapshot(overview)
    if state is None or state.closed_at is not None:
        raise ClassroomAdministrationPreviewError(
            "no_open_year", "Open a school year before creating a class."
        )
    if state.active_school_year != change.school_year:
        raise ClassroomAdministrationPreviewError(
            "year_mismatch", "The class year does not match the active year."
        )
    if any(item.class_id == change.class_id for item in overview.classes):
        raise ClassroomAdministrationPreviewError(
            "class_exists", "The selected class already exists."
        )
    parent = overview.workspace.root / "classes"
    target = class_dir(overview.workspace.root, change.class_id)
    metadata = class_metadata_path(overview.workspace.root, change.class_id)
    roster = class_roster_path(overview.workspace.root, change.class_id)
    for checked in (parent, target, metadata, roster):
        _guard(checked)
    if target.exists() or metadata.exists() or roster.exists():
        raise ClassroomAdministrationPreviewError(
            "class_exists", "A class path already exists at the destination."
        )
    return ClassCreationPreview(
        workspace_root=overview.workspace.root,
        class_id=change.class_id,
        school_year=change.school_year,
        active_school_year=state.active_school_year,
        target_class_directory=target,
        state_token=token,
        candidate_token=_candidate(
            token, "create_class", change.class_id + "\x00" + change.school_year
        ),
        metadata_would_be_created=True,
        roster_would_be_created=False,
    )
