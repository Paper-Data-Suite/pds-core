"""Fail-closed writer-scope *sequence contract* for Core #238 Slice 3G18.

Model the order in which a future native operation-owned guard must recheck a
checkpoint, call a bounded writer, inspect the result and request persistence.
This module accepts ONLY caller-reported phases and byte images. It does not
acquire a guard, invoke a writer, return a write token, certify custody or
persistence, retire a journal, or expose Notes. A future coordinator cannot
reuse an output from this function as authorization to write.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pds_core import _teacher_private_recovery_operation_admission as admission
from pds_core import _teacher_private_recovery_operation_postconditions as post
from pds_core import _teacher_private_transaction_intent as intents


class PrivateRecoveryWriterPhase(str, Enum):
    """Reported phase markers, not attestations of kernel-backed events."""

    GUARD_ACQUIRED = "guard_acquired"
    PREIMAGE_REVALIDATED = "preimage_revalidated"
    OPERATION_INVOKED = "operation_invoked"
    OPERATION_RETURNED = "operation_returned"
    POSTIMAGE_REVALIDATED = "postimage_revalidated"
    PERSISTENCE_REQUESTED = "persistence_requested"
    GUARD_RELEASED = "guard_released"


class PrivateRecoveryWriterSequenceState(str, Enum):
    PRECHECK_REVIEW_REQUIRED = "precheck_review_required"
    RETURNED_POSTIMAGE_REVIEW_REQUIRED = "returned_postimage_review_required"
    PERSISTENCE_UNQUALIFIED = "persistence_unqualified"
    INCOMPLETE_PRESERVE = "incomplete_preserve"
    ORDER_REFUSED = "order_refused"
    REPORTED_PHASE_CONFLICT_PRESERVE = "reported_phase_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    NO_PROGRESS_PRESERVE = "no_progress_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    PREIMAGE_CONFLICT_PRESERVE = "preimage_conflict_preserve"
    RETIREMENT_UNQUALIFIED = "retirement_unqualified"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INITIALIZATION_REFUSED = "initialization_refused"
    INVALID_REQUEST = "invalid_request"


_MESSAGES = {
    PrivateRecoveryWriterSequenceState.PRECHECK_REVIEW_REQUIRED: "Described exact preimage was unchanged; the guard and native writer have not been qualified.",
    PrivateRecoveryWriterSequenceState.RETURNED_POSTIMAGE_REVIEW_REQUIRED: "Described returned operation has matching postimages; retained native custody and durability remain unproved.",
    PrivateRecoveryWriterSequenceState.PERSISTENCE_UNQUALIFIED: "A persistence request was reported but completion and power-loss durability are unqualified.",
    PrivateRecoveryWriterSequenceState.INCOMPLETE_PRESERVE: "Required reported operation-scope phases are missing; preserve recovery evidence.",
    PrivateRecoveryWriterSequenceState.ORDER_REFUSED: "Operation phases are out of order, repeated, or cross guard-release boundaries.",
    PrivateRecoveryWriterSequenceState.REPORTED_PHASE_CONFLICT_PRESERVE: "Reported execution phase contradicts the recorded sequence or changed images.",
    PrivateRecoveryWriterSequenceState.INTERRUPTED_PRESERVE: "Operation state is interrupted or unknown; preserve all recovery artifacts.",
    PrivateRecoveryWriterSequenceState.NO_PROGRESS_PRESERVE: "A return was reported without an image transition; preserve pending evidence.",
    PrivateRecoveryWriterSequenceState.POSTIMAGE_CONFLICT_PRESERVE: "Described recovery postimages conflict with the expected exact operation transition.",
    PrivateRecoveryWriterSequenceState.PREIMAGE_CONFLICT_PRESERVE: "Described preimages are not the exact pending checkpoint; preserve evidence.",
    PrivateRecoveryWriterSequenceState.RETIREMENT_UNQUALIFIED: "Journal retirement lacks native absence custody and durable persistence qualification.",
    PrivateRecoveryWriterSequenceState.REVISION_MISMATCH_REFUSED: "The expected registry revision differs from the proposed transaction revision.",
    PrivateRecoveryWriterSequenceState.INITIALIZATION_REFUSED: "Initial binding requires a separate native absence and persistence protocol.",
    PrivateRecoveryWriterSequenceState.INVALID_REQUEST: "Invalid recovery writer-sequence review request.",
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryWriterSequenceReview:
    """Sanitized finding: no paths, byte images, native handles, or permits."""

    state: PrivateRecoveryWriterSequenceState
    message: str


def _result(
    state: PrivateRecoveryWriterSequenceState,
) -> PrivateRecoveryWriterSequenceReview:
    return PrivateRecoveryWriterSequenceReview(state, _MESSAGES[state])


_PHASE_ORDER = (
    PrivateRecoveryWriterPhase.GUARD_ACQUIRED,
    PrivateRecoveryWriterPhase.PREIMAGE_REVALIDATED,
    PrivateRecoveryWriterPhase.OPERATION_INVOKED,
    PrivateRecoveryWriterPhase.OPERATION_RETURNED,
    PrivateRecoveryWriterPhase.POSTIMAGE_REVALIDATED,
    PrivateRecoveryWriterPhase.PERSISTENCE_REQUESTED,
    PrivateRecoveryWriterPhase.GUARD_RELEASED,
)


def _ordered(phases: tuple[PrivateRecoveryWriterPhase, ...]) -> bool:
    if not phases or phases[0] is not PrivateRecoveryWriterPhase.GUARD_ACQUIRED:
        return False
    indexes = tuple(_PHASE_ORDER.index(phase) for phase in phases)
    if tuple(sorted(set(indexes))) != indexes:
        return False
    phase_set = set(phases)
    if PrivateRecoveryWriterPhase.OPERATION_INVOKED in phase_set and (
        PrivateRecoveryWriterPhase.PREIMAGE_REVALIDATED not in phase_set
    ):
        return False
    if PrivateRecoveryWriterPhase.OPERATION_RETURNED in phase_set and (
        PrivateRecoveryWriterPhase.OPERATION_INVOKED not in phase_set
    ):
        return False
    if PrivateRecoveryWriterPhase.POSTIMAGE_REVALIDATED in phase_set and (
        PrivateRecoveryWriterPhase.OPERATION_RETURNED not in phase_set
    ):
        return False
    if PrivateRecoveryWriterPhase.PERSISTENCE_REQUESTED in phase_set and (
        PrivateRecoveryWriterPhase.POSTIMAGE_REVALIDATED not in phase_set
    ):
        return False
    if PrivateRecoveryWriterPhase.GUARD_RELEASED in phase_set:
        if phases[-1] is not PrivateRecoveryWriterPhase.GUARD_RELEASED:
            return False
        if (
            PrivateRecoveryWriterPhase.OPERATION_INVOKED in phase_set
            and PrivateRecoveryWriterPhase.POSTIMAGE_REVALIDATED not in phase_set
        ):
            # An interrupted writer may have released the guard, but its
            # postcondition is unknown; do not describe it as orderly custody.
            return False
    return True


def review_private_recovery_writer_sequence(
    kind: post.PrivateRecoveryOperationKind,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    phases: tuple[PrivateRecoveryWriterPhase, ...],
    reported: admission.PrivateRecoveryReportedPhase,
    before: post.PrivateRecoveryOperationImage,
    after: post.PrivateRecoveryOperationImage,
) -> PrivateRecoveryWriterSequenceReview:
    """Classify an untrusted sequence report; never perform a native operation.

    Missing, reordered or contradictory phases are refused. In particular,
    claimed persistence and a claimed guard release do not prove a durable
    commit. The pure 3G17 interruption classifier validates the exact proposed
    before/after image and expected revision without granting authorization.
    """
    state = PrivateRecoveryWriterSequenceState
    if (
        type(phases) is not tuple
        or not 1 <= len(phases) <= len(_PHASE_ORDER)
        or any(type(phase) is not PrivateRecoveryWriterPhase for phase in phases)
        or type(reported) is not admission.PrivateRecoveryReportedPhase
        or type(kind) is not post.PrivateRecoveryOperationKind
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or type(before) is not post.PrivateRecoveryOperationImage
        or type(after) is not post.PrivateRecoveryOperationImage
    ):
        return _result(state.INVALID_REQUEST)
    if not _ordered(phases):
        return _result(state.ORDER_REFUSED)
    if kind is post.PrivateRecoveryOperationKind.JOURNAL_RETIREMENT:
        return _result(state.RETIREMENT_UNQUALIFIED)

    try:
        classified = admission.classify_private_recovery_operation_interruption(
            reported, kind, expected_revision, proposed, before, after
        )
        if (
            type(classified) is not admission.PrivateRecoveryInterruptionReview
            or type(classified.state) is not admission.PrivateRecoveryInterruptionState
        ):
            return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
        outcome = classified.state
        failures = {
            admission.PrivateRecoveryInterruptionState.INVALID_REQUEST: state.INVALID_REQUEST,
            admission.PrivateRecoveryInterruptionState.INITIALIZATION_REFUSED: state.INITIALIZATION_REFUSED,
            admission.PrivateRecoveryInterruptionState.REVISION_MISMATCH_REFUSED: state.REVISION_MISMATCH_REFUSED,
            admission.PrivateRecoveryInterruptionState.RETIREMENT_UNQUALIFIED: state.RETIREMENT_UNQUALIFIED,
            admission.PrivateRecoveryInterruptionState.PRECONDITION_REFUSED: state.PREIMAGE_CONFLICT_PRESERVE,
            admission.PrivateRecoveryInterruptionState.CONFLICT_PRESERVE: state.POSTIMAGE_CONFLICT_PRESERVE,
        }
        if outcome in failures:
            return _result(failures[outcome])
        invoked = PrivateRecoveryWriterPhase.OPERATION_INVOKED in phases
        returned = PrivateRecoveryWriterPhase.OPERATION_RETURNED in phases
        checked = PrivateRecoveryWriterPhase.POSTIMAGE_REVALIDATED in phases
        persisted = PrivateRecoveryWriterPhase.PERSISTENCE_REQUESTED in phases
        revalidated = PrivateRecoveryWriterPhase.PREIMAGE_REVALIDATED in phases

        if reported is admission.PrivateRecoveryReportedPhase.NOT_STARTED:
            if invoked or returned or checked or persisted:
                return _result(state.REPORTED_PHASE_CONFLICT_PRESERVE)
            if (
                outcome
                is not admission.PrivateRecoveryInterruptionState.UNCHANGED_BEFORE_REVIEW_REQUIRED
            ):
                return _result(state.REPORTED_PHASE_CONFLICT_PRESERVE)
            if not revalidated:
                return _result(state.INCOMPLETE_PRESERVE)
            return _result(state.PRECHECK_REVIEW_REQUIRED)

        if reported is admission.PrivateRecoveryReportedPhase.INTERRUPTED_OR_UNKNOWN:
            return _result(state.INTERRUPTED_PRESERVE)
        if not invoked or not returned:
            return _result(state.REPORTED_PHASE_CONFLICT_PRESERVE)
        if not checked:
            return _result(state.INCOMPLETE_PRESERVE)
        if outcome is admission.PrivateRecoveryInterruptionState.NO_PROGRESS_PRESERVE:
            return _result(state.NO_PROGRESS_PRESERVE)
        if (
            outcome
            is not admission.PrivateRecoveryInterruptionState.POSTIMAGE_REVIEW_REQUIRED
        ):
            return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
        if persisted:
            return _result(state.PERSISTENCE_UNQUALIFIED)
        return _result(state.RETURNED_POSTIMAGE_REVIEW_REQUIRED)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
