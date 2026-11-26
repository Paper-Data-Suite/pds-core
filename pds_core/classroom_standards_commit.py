"""Core #242: guarded Standards snapshots and profile membership edits.

Use the existing Standards model, validators, membership operations and writer.
No separate Standards storage or public menu capability is introduced.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pds_core.classroom_admin_preview import (
    ClassroomAdministrationPreviewError,
    _guard,
)
from pds_core.classroom_school_year_commit import (
    SchoolYearCommitError,
    _local_year_lock,
)
from pds_core.standards import (
    StandardsLibrary,
    StandardsValidationError,
    add_standards_to_profile,
    find_standards_profile,
    remove_standards_from_profile,
    set_profile_standards,
    standards_library_from_dict,
    standards_library_path,
    standards_library_to_dict,
    write_standards_library,
)
from pds_core.workspace import WorkspaceRootError, inspect_workspace_root

_MAX_BYTES = 32 * 1024 * 1024
_TOKEN = re.compile(r"^[0-9a-f]{64}$")
MembershipAction = Literal["add", "remove", "set"]


class StandardsReviewError(Exception):
    """Bounded refusal; never expose raw filesystem or library contents."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class StandardsReviewConflict(StandardsReviewError):
    """The reviewed library or proposal has changed."""


class StandardsReviewWriteError(StandardsReviewError):
    """Canonical write outcome requires inspection before retry."""


@dataclass(frozen=True, slots=True)
class StandardsSnapshot:
    workspace_root: Path
    library: StandardsLibrary
    present: bool
    state_token: str


@dataclass(frozen=True, slots=True)
class ProfileMembershipChange:
    action: MembershipAction
    profile_id: str
    standard_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileMembershipReview:
    snapshot: StandardsSnapshot
    change: ProfileMembershipChange
    before: tuple[str, ...]
    after: tuple[str, ...]
    candidate: StandardsLibrary
    candidate_state_token: str


@dataclass(frozen=True, slots=True)
class ProfileMembershipResult:
    outcome: Literal["committed", "no_change"]
    workspace_root: Path
    profile_id: str
    before: tuple[str, ...]
    after: tuple[str, ...]
    state_token: str


def _read_state(path: Path) -> tuple[bytes | None, str]:
    _guard(path.parent)
    _guard(path)
    digest = hashlib.sha256()
    digest.update(b"core242-standards-state-v1\x00")
    digest.update(str(path).encode("utf-8"))
    if not path.exists():
        if path.parent.exists() and not path.parent.is_dir():
            raise StandardsReviewError(
                "invalid_library", "Standards collection is not a directory."
            )
        digest.update(b"\x00missing")
        return None, digest.hexdigest()
    if not path.is_file():
        raise StandardsReviewError(
            "invalid_library", "Standards library is not a file."
        )
    with path.open("rb") as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise StandardsReviewError(
            "oversized_library", "Standards library exceeds review limit."
        )
    digest.update(b"\x00present\x00")
    digest.update(raw)
    return raw, digest.hexdigest()


def _fingerprint(path: Path) -> tuple[bool, str]:
    raw, token = _read_state(path)
    return raw is not None, token


def inspect_standards_snapshot(root: str | Path) -> StandardsSnapshot:
    """Read canonical validated definitions and profiles; never create files."""
    try:
        status = inspect_workspace_root(root)
        if not status.exists or not status.is_dir:
            raise StandardsReviewError(
                "missing_workspace", "Select an existing workspace."
            )
        path = standards_library_path(status.root)
        raw, token = _read_state(path)
        present = raw is not None
        if raw is None:
            library = StandardsLibrary(standards=(), profiles=())
        else:
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise StandardsReviewError(
                    "invalid_library", "Standards library is not an object."
                )
            library = standards_library_from_dict(cast(dict[str, object], decoded))
        if _fingerprint(path) != (present, token):
            raise StandardsReviewConflict(
                "state_changed", "Standards library changed; review again."
            )
    except (
        WorkspaceRootError,
        ClassroomAdministrationPreviewError,
        OSError,
        StandardsValidationError,
        UnicodeError,
        RecursionError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ):
        raise StandardsReviewError(
            "invalid_library", "Canonical Standards library cannot be inspected safely."
        ) from None
    return StandardsSnapshot(status.root, library, present, token)


def _candidate_token(
    snapshot: StandardsSnapshot,
    change: ProfileMembershipChange,
    candidate: StandardsLibrary,
) -> str:
    data = {
        "domain": "core242-profile-membership-v1",
        "root": str(snapshot.workspace_root),
        "current": snapshot.state_token,
        "action": change.action,
        "profile": change.profile_id,
        "requested": change.standard_ids,
        "candidate": standards_library_to_dict(candidate),
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def plan_profile_membership(
    root: str | Path, change: ProfileMembershipChange
) -> ProfileMembershipReview:
    """Review one existing profile's membership using existing Core authority."""
    if (
        not isinstance(change, ProfileMembershipChange)
        or change.action not in ("add", "remove", "set")
        or type(change.profile_id) is not str
        or not change.profile_id.strip()
        or type(change.standard_ids) is not tuple
        or any(type(item) is not str for item in change.standard_ids)
    ):
        raise StandardsReviewError("invalid_change", "Profile proposal is invalid.")
    snapshot = inspect_standards_snapshot(root)
    previous = find_standards_profile(snapshot.library, change.profile_id)
    if previous is None:
        raise StandardsReviewError(
            "invalid_profile", "Selected profile does not exist."
        )
    try:
        if change.action == "add":
            candidate = add_standards_to_profile(
                snapshot.library, change.profile_id, change.standard_ids
            )
        elif change.action == "remove":
            candidate = remove_standards_from_profile(
                snapshot.library, change.profile_id, change.standard_ids
            )
        else:
            candidate = set_profile_standards(
                snapshot.library, change.profile_id, change.standard_ids
            )
        updated = find_standards_profile(candidate, change.profile_id)
        assert updated is not None
        token = _candidate_token(snapshot, change, candidate)
    except StandardsValidationError:
        raise StandardsReviewError(
            "invalid_membership", "Requested profile membership is invalid."
        ) from None
    return ProfileMembershipReview(
        snapshot, change, previous.standards, updated.standards, candidate, token
    )


def _check(review: ProfileMembershipReview, current: str, candidate: str) -> None:
    if review.snapshot.state_token != current:
        raise StandardsReviewConflict(
            "state_changed", "Standards library changed; review again."
        )
    if review.candidate_state_token != candidate:
        raise StandardsReviewConflict(
            "candidate_changed", "Profile proposal differs from review."
        )


def commit_profile_membership(
    root: str | Path,
    change: ProfileMembershipChange,
    *,
    expected_current_state_token: str,
    expected_candidate_state_token: str,
    confirmed: bool,
) -> ProfileMembershipResult:
    """Commit a reviewed membership change; no definition or profile deletion."""
    if confirmed is not True:
        raise StandardsReviewError(
            "not_confirmed", "Explicit confirmation is required."
        )
    for token in (expected_current_state_token, expected_candidate_state_token):
        if type(token) is not str or _TOKEN.fullmatch(token) is None:
            raise StandardsReviewError("invalid_token", "Reviewed token is invalid.")
    if inspect_standards_snapshot(root).state_token != expected_current_state_token:
        raise StandardsReviewConflict(
            "state_changed", "Standards library changed; review again."
        )
    first = plan_profile_membership(root, change)
    _check(first, expected_current_state_token, expected_candidate_state_token)
    canonical = first.snapshot.workspace_root
    try:
        with _local_year_lock(canonical):
            if (
                inspect_standards_snapshot(root).state_token
                != expected_current_state_token
            ):
                raise StandardsReviewConflict(
                    "state_changed", "Standards library changed; review again."
                )
            fresh = plan_profile_membership(root, change)
            _check(fresh, expected_current_state_token, expected_candidate_state_token)
            if fresh.candidate == fresh.snapshot.library:
                return ProfileMembershipResult(
                    "no_change",
                    canonical,
                    change.profile_id,
                    fresh.before,
                    fresh.after,
                    fresh.snapshot.state_token,
                )
            path = standards_library_path(canonical)
            try:
                fingerprint = _fingerprint(path)
            except (OSError, ClassroomAdministrationPreviewError):
                raise StandardsReviewError(
                    "invalid_library", "Standards library cannot be inspected safely."
                ) from None
            if fingerprint != (True, expected_current_state_token):
                raise StandardsReviewConflict(
                    "state_changed", "Standards library changed; review again."
                )
            try:
                write_standards_library(path, fresh.candidate, overwrite=True)
                saved = inspect_standards_snapshot(canonical)
                if saved.library != fresh.candidate:
                    raise StandardsReviewWriteError(
                        "write_uncertain", "Standards write outcome is uncertain."
                    )
            except (OSError, StandardsReviewError, ClassroomAdministrationPreviewError):
                raise StandardsReviewWriteError(
                    "write_uncertain", "Inspect Standards before retry."
                ) from None
            return ProfileMembershipResult(
                "committed",
                canonical,
                change.profile_id,
                fresh.before,
                fresh.after,
                saved.state_token,
            )
    except SchoolYearCommitError as error:
        raise StandardsReviewConflict(
            error.reason, "Local administrative writer is unavailable."
        ) from None
    except ClassroomAdministrationPreviewError:
        raise StandardsReviewError(
            "unsafe_path", "Administrative writer path is unsafe."
        ) from None
