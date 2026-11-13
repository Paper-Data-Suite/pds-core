"""Non-authorizing recovery-operation admission and interruption triage (#238 3G17).

A prospective recovery operation must first have exact live preimages reviewed by
3G14's single retained native guard. This module translates that *completed*
review into an advisory state; the guard is not handed to a writer. A separate
pure classifier evaluates caller-provided interruption snapshots under 3G15's
exact-image transition contract. Neither result is a mutation permit, native
CAS reservation, persistence proof, journal retirement, or Notes service.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_operation_guard as guarded
from pds_core import _teacher_private_recovery_operation_postconditions as post
from pds_core import _teacher_private_transaction_intent as intents


class PrivateRecoveryAdmissionState(str, Enum):
    STABLE_PRECONDITION_REVIEW_REQUIRED = "stable_precondition_review_required"
    RETIREMENT_UNQUALIFIED = "retirement_unqualified"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    NAMESPACE_CHANGED_PRESERVE = "namespace_changed_preserve"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_ADMISSION_MESSAGES = {
    PrivateRecoveryAdmissionState.STABLE_PRECONDITION_REVIEW_REQUIRED: (
        "Exact native preconditions were reviewed under one guard; no execution is admitted."
    ),
    PrivateRecoveryAdmissionState.RETIREMENT_UNQUALIFIED: (
        "Journal retirement lacks qualified absence custody and durability."
    ),
    PrivateRecoveryAdmissionState.REVISION_MISMATCH_REFUSED: (
        "Expected protected registry revision does not match."
    ),
    PrivateRecoveryAdmissionState.CHECKPOINT_CONFLICT_PRESERVE: (
        "Native pre-operation checkpoint does not match; preserve all artifacts."
    ),
    PrivateRecoveryAdmissionState.IMAGE_CONFLICT_PRESERVE: (
        "Native evidence is unqualified, conflicting, or changed; preserve all artifacts."
    ),
    PrivateRecoveryAdmissionState.NAMESPACE_CHANGED_PRESERVE: (
        "Pending journal or stage namespace changed; preserve recovery evidence."
    ),
    PrivateRecoveryAdmissionState.OWNER_CHANGED: (
        "Effective native owner changed during the precondition review."
    ),
    PrivateRecoveryAdmissionState.GUARD_REFUSED: (
        "Native retained protection failed or refused the review."
    ),
    PrivateRecoveryAdmissionState.INTERRUPTED_PRESERVE: (
        "Native admission review was interrupted; preserve recovery evidence."
    ),
    PrivateRecoveryAdmissionState.INVALID_REQUEST: "Invalid recovery-operation admission request.",
    PrivateRecoveryAdmissionState.INITIALIZATION_REFUSED: (
        "First binding requires a separately qualified native absence protocol."
    ),
    PrivateRecoveryAdmissionState.UNSUPPORTED: (
        "Native recovery-operation admission review is unsupported."
    ),
    PrivateRecoveryAdmissionState.IO_ERROR: (
        "Native precondition review could not finish; preserve all artifacts."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryAdmissionReview:
    """Sanitized result; contains neither a native guard nor a write capability."""

    state: PrivateRecoveryAdmissionState
    message: str


def _admission(state: PrivateRecoveryAdmissionState) -> PrivateRecoveryAdmissionReview:
    return PrivateRecoveryAdmissionReview(state, _ADMISSION_MESSAGES[state])


_OPERATION_TO_REVIEW = {
    post.PrivateRecoveryOperationKind.STAGE_TO_REGISTRY: (
        actions.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART,
        guarded.PrivateRecoveryOperationGuardState.PREPARED_ONE_SCOPE_REVIEW_REQUIRED,
    ),
    post.PrivateRecoveryOperationKind.DESCRIPTOR_AFTER_IMAGE: (
        actions.PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION,
        guarded.PrivateRecoveryOperationGuardState.DESCRIPTOR_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
    ),
}

_GUARD_STATES = guarded.PrivateRecoveryOperationGuardState
_GUARD_FAILURES = {
    _GUARD_STATES.REVISION_MISMATCH_REFUSED: PrivateRecoveryAdmissionState.REVISION_MISMATCH_REFUSED,
    _GUARD_STATES.ACTION_MISMATCH_REFUSED: PrivateRecoveryAdmissionState.CHECKPOINT_CONFLICT_PRESERVE,
    _GUARD_STATES.CHECKPOINT_CONFLICT_PRESERVE: PrivateRecoveryAdmissionState.CHECKPOINT_CONFLICT_PRESERVE,
    _GUARD_STATES.IMAGE_MISMATCH_PRESERVE: PrivateRecoveryAdmissionState.IMAGE_CONFLICT_PRESERVE,
    _GUARD_STATES.IMAGE_DRIFT_PRESERVE: PrivateRecoveryAdmissionState.IMAGE_CONFLICT_PRESERVE,
    _GUARD_STATES.NAMESPACE_CHANGED_PRESERVE: PrivateRecoveryAdmissionState.NAMESPACE_CHANGED_PRESERVE,
    _GUARD_STATES.OWNER_CHANGED: PrivateRecoveryAdmissionState.OWNER_CHANGED,
    _GUARD_STATES.GUARD_REFUSED: PrivateRecoveryAdmissionState.GUARD_REFUSED,
    _GUARD_STATES.INTERRUPTED_PRESERVE: PrivateRecoveryAdmissionState.INTERRUPTED_PRESERVE,
    _GUARD_STATES.INVALID_REQUEST: PrivateRecoveryAdmissionState.INVALID_REQUEST,
    _GUARD_STATES.INITIALIZATION_REFUSED: PrivateRecoveryAdmissionState.INITIALIZATION_REFUSED,
    _GUARD_STATES.UNSUPPORTED: PrivateRecoveryAdmissionState.UNSUPPORTED,
    _GUARD_STATES.IO_ERROR: PrivateRecoveryAdmissionState.IO_ERROR,
}


def review_private_recovery_operation_admission(
    kind: post.PrivateRecoveryOperationKind,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRecoveryAdmissionReview:
    """Request one native 3G14 preimage review, never a writer or a token.

    Even the matching state is stale immediately after the guard releases.
    The only admissible *next* operation is independent protected review by a
    future writer; callers cannot reuse this response as authorization.
    """
    state = PrivateRecoveryAdmissionState
    if (
        type(kind) is not post.PrivateRecoveryOperationKind
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _admission(state.INVALID_REQUEST)
    if kind is post.PrivateRecoveryOperationKind.JOURNAL_RETIREMENT:
        return _admission(state.RETIREMENT_UNQUALIFIED)
    step, expected = _OPERATION_TO_REVIEW[kind]
    try:
        observed = guarded.review_operation_owned_private_recovery_guard(
            step,
            expected_revision,
            proposed,
            existing_private_root,
            existing_workspace_root,
        )
        if (
            type(observed) is not guarded.PrivateRecoveryOperationGuardReview
            or type(observed.state) is not guarded.PrivateRecoveryOperationGuardState
        ):
            return _admission(state.IMAGE_CONFLICT_PRESERVE)
        if observed.state is expected:
            return _admission(state.STABLE_PRECONDITION_REVIEW_REQUIRED)
        return _admission(
            _GUARD_FAILURES.get(observed.state, state.CHECKPOINT_CONFLICT_PRESERVE)
        )
    except KeyboardInterrupt:
        return _admission(state.INTERRUPTED_PRESERVE)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        return _admission(state.IO_ERROR)


class PrivateRecoveryReportedPhase(str, Enum):
    NOT_STARTED = "not_started"
    RETURNED = "returned"
    INTERRUPTED_OR_UNKNOWN = "interrupted_or_unknown"


class PrivateRecoveryInterruptionState(str, Enum):
    UNCHANGED_BEFORE_REVIEW_REQUIRED = "unchanged_before_review_required"
    POSTIMAGE_REVIEW_REQUIRED = "postimage_review_required"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    NO_PROGRESS_PRESERVE = "no_progress_preserve"
    UNEXPECTED_CHANGE_PRESERVE = "unexpected_change_preserve"
    PRECONDITION_REFUSED = "precondition_refused"
    CONFLICT_PRESERVE = "conflict_preserve"
    RETIREMENT_UNQUALIFIED = "retirement_unqualified"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INITIALIZATION_REFUSED = "initialization_refused"
    INVALID_REQUEST = "invalid_request"


_INTERRUPTION_MESSAGES = {
    PrivateRecoveryInterruptionState.UNCHANGED_BEFORE_REVIEW_REQUIRED: (
        "Exact before-image is unchanged; caller-reported nonexecution grants no authority."
    ),
    PrivateRecoveryInterruptionState.POSTIMAGE_REVIEW_REQUIRED: (
        "Caller-reported return and exact postimage agree; native custody and durability unproved."
    ),
    PrivateRecoveryInterruptionState.INTERRUPTED_PRESERVE: (
        "Unknown or interrupted operation phase; preserve all recovery artifacts."
    ),
    PrivateRecoveryInterruptionState.NO_PROGRESS_PRESERVE: (
        "Reported operation return has no observed image transition; preserve evidence."
    ),
    PrivateRecoveryInterruptionState.UNEXPECTED_CHANGE_PRESERVE: (
        "Reported nonexecution conflicts with changed images; preserve evidence."
    ),
    PrivateRecoveryInterruptionState.PRECONDITION_REFUSED: (
        "Starting exact byte images do not match the proposed checkpoint."
    ),
    PrivateRecoveryInterruptionState.CONFLICT_PRESERVE: (
        "Partial, changed or unsupported postcondition; preserve all artifacts."
    ),
    PrivateRecoveryInterruptionState.RETIREMENT_UNQUALIFIED: (
        "Journal retirement and durable absence cannot be qualified here."
    ),
    PrivateRecoveryInterruptionState.REVISION_MISMATCH_REFUSED: (
        "Expected registry revision does not match the proposed checkpoint."
    ),
    PrivateRecoveryInterruptionState.INITIALIZATION_REFUSED: (
        "First binding is not covered by this recovery protocol."
    ),
    PrivateRecoveryInterruptionState.INVALID_REQUEST: (
        "Invalid or noncanonical interruption-review request."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryInterruptionReview:
    """Sanitized, nonauthorizing triage of untrusted described images and phase."""

    state: PrivateRecoveryInterruptionState
    message: str


def _interruption(
    state: PrivateRecoveryInterruptionState,
) -> PrivateRecoveryInterruptionReview:
    return PrivateRecoveryInterruptionReview(state, _INTERRUPTION_MESSAGES[state])


def classify_private_recovery_operation_interruption(
    phase: PrivateRecoveryReportedPhase,
    kind: post.PrivateRecoveryOperationKind,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    before: post.PrivateRecoveryOperationImage,
    after: post.PrivateRecoveryOperationImage,
) -> PrivateRecoveryInterruptionReview:
    """Triage untrusted phase and image descriptions; never execute or resume.

    An interrupted/unknown phase is NEVER promoted to success even when
    supplied images match. Successful return is also not native custody or
    power-loss durability. This function has no path or filesystem access.
    """
    state = PrivateRecoveryInterruptionState
    if type(phase) is not PrivateRecoveryReportedPhase:
        return _interruption(state.INVALID_REQUEST)
    try:
        checked = post.classify_private_recovery_operation_postconditions(
            kind, expected_revision, proposed, before, after
        )
        if (
            type(checked) is not post.PrivateRecoveryPostconditionReview
            or type(checked.state) is not post.PrivateRecoveryPostconditionState
        ):
            return _interruption(state.CONFLICT_PRESERVE)
        observed = checked.state
        if observed is post.PrivateRecoveryPostconditionState.INVALID_REQUEST:
            return _interruption(state.INVALID_REQUEST)
        if observed is post.PrivateRecoveryPostconditionState.INITIALIZATION_REFUSED:
            return _interruption(state.INITIALIZATION_REFUSED)
        if observed is post.PrivateRecoveryPostconditionState.REVISION_MISMATCH_REFUSED:
            return _interruption(state.REVISION_MISMATCH_REFUSED)
        if observed is post.PrivateRecoveryPostconditionState.PRECONDITION_REFUSED:
            return _interruption(state.PRECONDITION_REFUSED)
        if observed is post.PrivateRecoveryPostconditionState.INTERRUPTED_PRESERVE:
            return _interruption(state.INTERRUPTED_PRESERVE)
        if phase is PrivateRecoveryReportedPhase.INTERRUPTED_OR_UNKNOWN:
            return _interruption(state.INTERRUPTED_PRESERVE)
        if kind is post.PrivateRecoveryOperationKind.JOURNAL_RETIREMENT:
            return _interruption(state.RETIREMENT_UNQUALIFIED)
        if phase is PrivateRecoveryReportedPhase.NOT_STARTED:
            if observed is post.PrivateRecoveryPostconditionState.NO_PROGRESS_PRESERVE:
                return _interruption(state.UNCHANGED_BEFORE_REVIEW_REQUIRED)
            return _interruption(state.UNEXPECTED_CHANGE_PRESERVE)
        if observed is post.PrivateRecoveryPostconditionState.NO_PROGRESS_PRESERVE:
            return _interruption(state.NO_PROGRESS_PRESERVE)
        if (
            observed
            is post.PrivateRecoveryPostconditionState.TRANSITION_OBSERVED_REVIEW_REQUIRED
        ):
            return _interruption(state.POSTIMAGE_REVIEW_REQUIRED)
        return _interruption(state.CONFLICT_PRESERVE)
    except KeyboardInterrupt:
        return _interruption(state.INTERRUPTED_PRESERVE)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        return _interruption(state.CONFLICT_PRESERVE)
