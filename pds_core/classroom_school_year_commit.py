"""Core #242 C3B2: locally guarded canonical school-year transitions.

Only first-year open, same-year no-op, and active-year close are supported.
Closed-year rollover and replacement deliberately remain unsupported.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pds_core.classroom_admin_preview import (
    ClassroomAdministrationPreviewError,
    SchoolYearChange,
    SchoolYearChangePreview,
    _guard,
    _overview,
    _state_fingerprint,
    plan_school_year_change,
)
from pds_core.school_years import (
    SchoolYearState,
    SchoolYearStateError,
    close_school_year,
    load_school_year_state,
    open_school_year,
    school_year_state_path,
)

SchoolYearWriteOutcome = Literal["committed", "no_change"]
_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SchoolYearCommitError(Exception):
    """Stable, bounded refusal; no private OS error details."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class SchoolYearConflictError(SchoolYearCommitError):
    """Reviewed state, proposed transition or local lock has changed."""


class SchoolYearWriteError(SchoolYearCommitError):
    """Write failed, possibly after the canonical state changed."""


@dataclass(frozen=True, slots=True)
class GuardedSchoolYearReview:
    proposal: SchoolYearChangePreview
    effective_at: datetime
    current_state_token: str
    candidate_state_token: str


@dataclass(frozen=True, slots=True)
class SchoolYearCommitResult:
    action: str
    outcome: SchoolYearWriteOutcome
    previous_school_year: str | None
    active_school_year: str | None
    previous_state_token: str
    committed_state_token: str


def _validate_time(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SchoolYearCommitError(
            "invalid_timestamp", "A timezone-aware timestamp is required."
        )
    if value.utcoffset() is None:
        raise SchoolYearCommitError(
            "invalid_timestamp", "A timezone-aware timestamp is required."
        )
    return value


def _review_token(proposal: SchoolYearChangePreview, at: datetime) -> str:
    digest = hashlib.sha256()
    digest.update(b"core242-guarded-school-year-v1\x00")
    for value in (
        str(proposal.workspace_root),
        proposal.state_token,
        proposal.candidate_token,
        at.isoformat(),
    ):
        digest.update(value.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _checked_state(
    preview: SchoolYearChangePreview,
) -> SchoolYearState | None:
    path = school_year_state_path(preview.workspace_root)
    before = _state_fingerprint(path)
    if before != preview.state_token:
        raise SchoolYearConflictError(
            "current_state_changed", "School-year state changed; review again."
        )
    try:
        state = load_school_year_state(preview.workspace_root)
    except (SchoolYearStateError, OSError) as error:
        raise SchoolYearCommitError(
            "invalid_year_state", "School-year state cannot be inspected."
        ) from error
    if _state_fingerprint(path) != before:
        raise SchoolYearConflictError(
            "current_state_changed", "School-year state changed; review again."
        )
    return state


def _review(
    root: str | Path,
    change: SchoolYearChange,
    at: datetime,
) -> GuardedSchoolYearReview:
    _validate_time(at)
    try:
        proposal = plan_school_year_change(root, change)
        state = _checked_state(proposal)
        if change.action == "open" and not proposal.no_change:
            # Existing class metadata may belong to an older school year.
            # First-year opening must not reinterpret such history silently.
            overview = _overview(proposal.workspace_root)
            if overview.classes:
                raise SchoolYearCommitError(
                    "class_history_policy_required",
                    "Cannot initialize a first year over existing classes.",
                )
            if _state_fingerprint(
                school_year_state_path(proposal.workspace_root)
            ) != proposal.state_token:
                raise SchoolYearConflictError(
                    "current_state_changed", "School-year state changed; review again."
                )
        elif change.action == "close":
            if state is None or at < state.opened_at:
                raise SchoolYearCommitError(
                    "invalid_timestamp", "Closure cannot precede year opening."
                )
    except ClassroomAdministrationPreviewError as error:
        raise SchoolYearCommitError(error.reason, str(error)) from error
    return GuardedSchoolYearReview(
        proposal=proposal,
        effective_at=at,
        current_state_token=proposal.state_token,
        candidate_state_token=_review_token(proposal, at),
    )


def plan_guarded_school_year_change(
    root: str | Path,
    change: SchoolYearChange,
    *,
    effective_at: datetime,
) -> GuardedSchoolYearReview:
    """Read-only review of one precisely timestamped transition."""
    if not isinstance(change, SchoolYearChange):
        raise SchoolYearCommitError(
            "invalid_change", "School-year transition is invalid."
        )
    return _review(root, change, effective_at)


def _assert_token(value: str) -> None:
    if type(value) is not str or _TOKEN_PATTERN.fullmatch(value) is None:
        raise SchoolYearCommitError(
            "invalid_token", "The reviewed school-year state token is invalid."
        )


def _check_review(
    observed: GuardedSchoolYearReview,
    current: str,
    candidate: str,
) -> None:
    if observed.current_state_token != current:
        raise SchoolYearConflictError(
            "current_state_changed", "School-year state changed; review again."
        )
    if observed.candidate_state_token != candidate:
        raise SchoolYearConflictError(
            "candidate_changed", "School-year proposal differs from review."
        )


@contextmanager
def _local_year_lock(root: Path) -> Iterator[None]:
    """Coordinate only participating new C3B2 writers on one computer."""
    _guard(root)
    lock = root / ".school-year.write.lock"
    _guard(lock)
    owned = False
    try:
        try:
            with lock.open("x", encoding="utf-8"):
                owned = True
        except FileExistsError as error:
            raise SchoolYearConflictError(
                "write_conflict", "Another local school-year writer is active."
            ) from error
        except OSError as error:
            raise SchoolYearWriteError(
                "lock_failed", "School-year local writer lock is unavailable."
            ) from error
        yield
    finally:
        if owned:
            try:
                lock.unlink(missing_ok=True)
            except OSError:
                # A committed canonical write must not be reported as undone.
                pass


def _receipt(
    review: GuardedSchoolYearReview,
    outcome: SchoolYearWriteOutcome,
    token: str,
) -> SchoolYearCommitResult:
    plan = review.proposal
    active = (
        plan.previous_school_year if plan.no_change else plan.proposed_active_year
    )
    return SchoolYearCommitResult(
        action=plan.action,
        outcome=outcome,
        previous_school_year=plan.previous_school_year,
        active_school_year=active,
        previous_state_token=review.current_state_token,
        committed_state_token=token,
    )


def commit_guarded_school_year_change(
    root: str | Path,
    change: SchoolYearChange,
    *,
    effective_at: datetime,
    expected_current_state_token: str,
    expected_candidate_state_token: str,
    confirmed: bool,
) -> SchoolYearCommitResult:
    """Commit exactly one reviewed transition via canonical Core writers.

    Local lock does not protect against uncoordinated legacy CLI writers
    or multi-device sync conflicts. Uncertain writes require inspection.
    """
    if confirmed is not True:
        raise SchoolYearCommitError(
            "not_confirmed", "Explicit confirmation is required."
        )
    _assert_token(expected_current_state_token)
    _assert_token(expected_candidate_state_token)
    first = plan_guarded_school_year_change(
        root, change, effective_at=effective_at
    )
    _check_review(
        first, expected_current_state_token, expected_candidate_state_token
    )
    if first.proposal.no_change:
        again = plan_guarded_school_year_change(
            root, change, effective_at=effective_at
        )
        _check_review(
            again, expected_current_state_token, expected_candidate_state_token
        )
        return _receipt(again, "no_change", again.current_state_token)

    with _local_year_lock(first.proposal.workspace_root):
        fresh = plan_guarded_school_year_change(
            root, change, effective_at=effective_at
        )
        _check_review(
            fresh, expected_current_state_token, expected_candidate_state_token
        )
        path = school_year_state_path(fresh.proposal.workspace_root)
        try:
            if change.action == "open":
                assert change.year is not None
                written = open_school_year(
                    fresh.proposal.workspace_root,
                    change.year,
                    opened_at=effective_at,
                    overwrite=False,
                )
            else:
                written = close_school_year(
                    fresh.proposal.workspace_root,
                    closed_at=effective_at,
                )
            saved = load_school_year_state(fresh.proposal.workspace_root)
            if (
                saved != written
                or saved is None
                or (
                    change.action == "open"
                    and (
                        saved.active_school_year != change.year
                        or saved.opened_at != effective_at
                        or saved.closed_at is not None
                    )
                )
                or (
                    change.action == "close"
                    and (
                        saved.active_school_year != fresh.proposal.previous_school_year
                        or saved.closed_at != effective_at
                    )
                )
            ):
                raise SchoolYearWriteError(
                    "write_outcome_uncertain",
                    "Canonical school-year state is uncertain; inspect before retry.",
                )
            token = _state_fingerprint(path)
        except SchoolYearWriteError:
            raise
        except (SchoolYearStateError, ClassroomAdministrationPreviewError, OSError):
            raise SchoolYearWriteError(
                "write_outcome_uncertain",
                "School-year write outcome uncertain; inspect before retry.",
            ) from None
        return _receipt(fresh, "committed", token)
