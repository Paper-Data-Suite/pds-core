"""Core #242 C3B5: reviewed creation of a canonical empty class."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pds_core.class_metadata import (
    ClassMetadata,
    ClassMetadataError,
    create_class_metadata,
    load_class_metadata_for_class,
    write_class_metadata,
)
from pds_core.classroom_admin_preview import (
    ClassCreationChange,
    ClassCreationPreview,
    ClassroomAdministrationPreviewError,
    _guard,
    _state_fingerprint,
    plan_class_creation,
)
from pds_core.classroom_school_year_commit import (
    SchoolYearCommitError,
    _local_year_lock,
)
from pds_core.routes import class_dir, class_metadata_path
from pds_core.school_years import (
    SchoolYearStateError,
    load_school_year_state,
    school_year_state_path,
)
from pds_core.workspace import WorkspaceRootError, inspect_workspace_root

RecoveryState = Literal["absent", "empty_directory", "matches_review", "conflict"]
WriteOutcome = Literal["no_change", "partial", "indeterminate"]
_TOKEN = re.compile(r"^[0-9a-f]{64}$")


class ClassCreationError(Exception):
    """Bounded administrative refusal."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class ClassCreationConflictError(ClassCreationError):
    """The reviewed destination or year is no longer available."""


class ClassCreationWriteError(ClassCreationError):
    """Failure with a conservative canonical class durability assessment."""

    def __init__(self, reason: str, message: str, outcome: WriteOutcome) -> None:
        self.outcome = outcome
        super().__init__(reason, message)


@dataclass(frozen=True, slots=True)
class GuardedClassCreationReview:
    proposal: ClassCreationPreview
    metadata: ClassMetadata
    current_state_token: str
    candidate_state_token: str


@dataclass(frozen=True, slots=True)
class ClassCreationResult:
    workspace_root: Path
    class_id: str
    school_year: str
    metadata_path: Path
    outcome: Literal["committed"] = "committed"


def _metadata(change: ClassCreationChange, at: datetime) -> ClassMetadata:
    if not isinstance(change, ClassCreationChange):
        raise ClassCreationError("invalid_change", "Class proposal is invalid.")
    # Windows device names are not portable class folder identifiers.
    if re.fullmatch(r"(?i:con|prn|aux|nul|com[0-9]|lpt[0-9])", change.class_id):
        raise ClassCreationError("invalid_class", "Class identifier is reserved.")
    try:
        return create_class_metadata(change.class_id, change.school_year, created_at=at)
    except ClassMetadataError as error:
        raise ClassCreationError(
            "invalid_timestamp", "A timezone-aware creation time is required."
        ) from error


def _token(plan: ClassCreationPreview, metadata: ClassMetadata) -> str:
    digest = hashlib.sha256()
    for item in (
        "core242-guarded-class-v1",
        str(plan.workspace_root),
        plan.state_token,
        plan.candidate_token,
        str(plan.target_class_directory),
        metadata.created_at.isoformat(),
    ):
        digest.update(item.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def plan_guarded_class_creation(
    root: str | Path, change: ClassCreationChange, *, created_at: datetime
) -> GuardedClassCreationReview:
    """Review a new empty class; do not create any directories or locks."""
    metadata = _metadata(change, created_at)
    try:
        plan = plan_class_creation(root, change)
        parent = plan.target_class_directory.parent
        # Enforce portable case-insensitive identity on both Windows and POSIX.
        if parent.exists() and any(
            entry.name.casefold() == change.class_id.casefold()
            for entry in parent.iterdir()
        ):
            raise ClassCreationConflictError(
                "class_exists", "A class destination already exists."
            )
        state = load_school_year_state(plan.workspace_root)
        if (
            state is None
            or state.closed_at is not None
            or state.active_school_year != change.school_year
            or _state_fingerprint(school_year_state_path(plan.workspace_root))
            != plan.state_token
        ):
            raise ClassCreationConflictError(
                "current_state_changed", "School-year state changed; review again."
            )
        if created_at < state.opened_at:
            raise ClassCreationError(
                "invalid_timestamp", "Class creation cannot precede year opening."
            )
    except ClassroomAdministrationPreviewError as error:
        raise ClassCreationConflictError(error.reason, str(error)) from error
    except (OSError, SchoolYearStateError):
        raise ClassCreationError(
            "inspection_failed", "Class destination cannot be inspected safely."
        ) from None
    return GuardedClassCreationReview(
        plan, metadata, plan.state_token, _token(plan, metadata)
    )


def inspect_class_creation_recovery(
    root: str | Path, change: ClassCreationChange, *, created_at: datetime
) -> RecoveryState:
    """Inspect an interrupted destination; never infer ownership or retry.

    An exact match is evidence of observed contents, not a write receipt.
    Missing or empty destinations are not authorization to adopt or delete.
    """
    expected = _metadata(change, created_at)
    try:
        status = inspect_workspace_root(root)
        if not status.exists or not status.is_dir:
            return "conflict"
        target = class_dir(status.root, change.class_id)
        path = class_metadata_path(status.root, change.class_id)
        for checked in (target.parent, target, path):
            _guard(checked)
        if not target.exists():
            return "absent"
        if not target.is_dir():
            return "conflict"
        entries = tuple(target.iterdir())
        if not entries:
            return "empty_directory"
        if entries != (path,) or not path.is_file():
            return "conflict"
        if path.stat().st_size > 64 * 1024:
            return "conflict"
        if load_class_metadata_for_class(status.root, change.class_id) == expected:
            return "matches_review"
    except (
        OSError,
        WorkspaceRootError,
        ClassroomAdministrationPreviewError,
        ClassMetadataError,
    ):
        return "conflict"
    return "conflict"


def _check(review: GuardedClassCreationReview, current: str, candidate: str) -> None:
    if review.current_state_token != current:
        raise ClassCreationConflictError(
            "current_state_changed", "School-year state changed; review again."
        )
    if review.candidate_state_token != candidate:
        raise ClassCreationConflictError(
            "candidate_changed", "Class proposal differs from review."
        )


def commit_guarded_class_creation(
    root: str | Path,
    change: ClassCreationChange,
    *,
    created_at: datetime,
    expected_current_state_token: str,
    expected_candidate_state_token: str,
    confirmed: bool,
) -> ClassCreationResult:
    """Create exclusively; share the local year lock with C3B2.

    Stage using Core's existing metadata writer, then publish without replacing
    an existing canonical file. Unsupported hard links fail closed.
    """
    if confirmed is not True:
        raise ClassCreationError("not_confirmed", "Explicit confirmation is required.")
    for token in (expected_current_state_token, expected_candidate_state_token):
        if type(token) is not str or _TOKEN.fullmatch(token) is None:
            raise ClassCreationError("invalid_token", "Reviewed token is invalid.")
    first = plan_guarded_class_creation(root, change, created_at=created_at)
    _check(first, expected_current_state_token, expected_candidate_state_token)
    canonical_root = first.proposal.workspace_root
    target = first.proposal.target_class_directory
    path = class_metadata_path(canonical_root, change.class_id)
    owned = False
    published = False
    try:
        with _local_year_lock(canonical_root):
            fresh = plan_guarded_class_creation(root, change, created_at=created_at)
            _check(fresh, expected_current_state_token, expected_candidate_state_token)
            # Stage outside classes so discovery never sees a staging class.
            with tempfile.TemporaryDirectory(
                prefix=".core242-class-", dir=canonical_root
            ) as directory:
                staged = Path(directory) / "class.json"
                write_class_metadata(staged, fresh.metadata, overwrite=False)
                latest = plan_guarded_class_creation(
                    root, change, created_at=created_at
                )
                _check(
                    latest, expected_current_state_token, expected_candidate_state_token
                )
                _guard(target.parent)
                target.parent.mkdir(exist_ok=True)
                _guard(target)
                try:
                    target.mkdir(exist_ok=False)
                except FileExistsError as error:
                    raise ClassCreationConflictError(
                        "class_exists", "Class destination appeared; review again."
                    ) from error
                owned = True
                _guard(path)
                if (
                    _state_fingerprint(school_year_state_path(canonical_root))
                    != expected_current_state_token
                ):
                    raise OSError("year changed after directory creation")
                os.link(staged, path)
                published = True
                if (
                    inspect_class_creation_recovery(
                        canonical_root, change, created_at=created_at
                    )
                    != "matches_review"
                    or _state_fingerprint(school_year_state_path(canonical_root))
                    != expected_current_state_token
                ):
                    raise OSError("canonical verification failed")
    except SchoolYearCommitError as error:
        raise ClassCreationConflictError(error.reason, str(error)) from error
    except (OSError, ClassMetadataError, ClassroomAdministrationPreviewError):
        observed = inspect_class_creation_recovery(
            canonical_root, change, created_at=created_at
        )
        outcome: WriteOutcome = "indeterminate"
        if owned and not published and observed == "empty_directory":
            outcome = "partial"
        elif not owned and observed == "absent":
            outcome = "no_change"
        raise ClassCreationWriteError(
            "write_incomplete",
            "Class creation did not finish normally; inspect canonical state before retry.",
            outcome,
        ) from None
    return ClassCreationResult(
        canonical_root, change.class_id, change.school_year, path
    )
