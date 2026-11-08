"""Protected canonical FORK_COPY pre-attempt/restart handoff (#238 Slice 3G54).

Bind the genuine Core canonical fork intent to the existing protected native
one-shot pre-attempt reader, then independently reopen recovery custody.  No
observation spans both scopes: this module NEVER supplies an operation permit,
retry token, durable completion, journal retirement or Notes capability.

The protected production write barrier MUST remain blocked at both boundaries.
No native write, journal change, cleanup, or mutation is executed here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_sealed_pre_attempt as sealed
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateCanonicalProtectedHandoffState(str, Enum):
    PREPARED_FORK_REOBSERVED_BLOCKED = "prepared_fork_reobserved_blocked"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    INTENT_UNQUALIFIED = "intent_unqualified"
    FORK_REQUIRED = "fork_required"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    BARRIER_UNQUALIFIED = "barrier_unqualified"
    PROTECTED_PREATTEMPT_REFUSED = "protected_preattempt_refused"
    PROTECTED_SCOPE_DRIFT_PRESERVE = "protected_scope_drift_preserve"
    RECOVERY_REGISTRY_AFTER_PRESERVE = "recovery_registry_after_preserve"
    RECOVERY_BOTH_AFTER_PRESERVE = "recovery_both_after_preserve"
    RECOVERY_OTHER_PRESERVE = "recovery_other_preserve"
    RECOVERY_REFUSED = "recovery_refused"
    FINAL_BARRIER_CHANGED_PRESERVE = "final_barrier_changed_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateCanonicalProtectedHandoffState, str] = {
    state: "Canonical protected handoff remains unqualified; preserve transaction evidence."
    for state in PrivateCanonicalProtectedHandoffState
}
_MESSAGES[PrivateCanonicalProtectedHandoffState.PREPARED_FORK_REOBSERVED_BLOCKED] = (
    "Canonical FORK_COPY was observed inside protected one-shot custody and then "
    "independently reobserved prepared. Production writing remains blocked."
)
_MESSAGES[PrivateCanonicalProtectedHandoffState.PROTECTED_SCOPE_DRIFT_PRESERVE] = (
    "Protected one-shot custody refused or changed; independently recheck pending evidence."
)
_MESSAGES[PrivateCanonicalProtectedHandoffState.RECOVERY_REGISTRY_AFTER_PRESERVE] = (
    "Independent native restart observed the registry after-image; preserve the journal."
)
_MESSAGES[PrivateCanonicalProtectedHandoffState.RECOVERY_BOTH_AFTER_PRESERVE] = (
    "Independent native restart observed both after-images; journal retirement unqualified."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateCanonicalProtectedHandoffReview:
    """After-release diagnostic ONLY. No path, image, handle, or write capability."""

    state: PrivateCanonicalProtectedHandoffState
    message: str
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    no_automatic_retry: bool = True
    journal_retirement_forbidden: bool = True
    durability_unqualified: bool = True
    separate_native_scopes_not_atomic: bool = True
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(default=barrier._REQUIRED, repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateCanonicalProtectedHandoffReview(non_authorizing=True)"


def _result(
    state: PrivateCanonicalProtectedHandoffState,
) -> PrivateCanonicalProtectedHandoffReview:
    return PrivateCanonicalProtectedHandoffReview(state, _MESSAGES[state])


def _barrier_still_blocked(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    checked: intents.PrivateTransactionIntent,
) -> bool:
    """Advisory check, never a write admission or a reusable receipt."""
    review = barrier.review_private_production_write_barrier(
        step, expected_revision, checked
    )
    return (
        type(review) is barrier.PrivateProductionWriteBarrierReview
        and review.state
        is barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        and review.unqualified_requirements == barrier._REQUIRED
    )


def review_canonical_fork_protected_handoff(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateCanonicalProtectedHandoffReview:
    """Read-only cross-scope check for one already prepared canonical FORK_COPY.

    The 3G45 protected reader retains native guards while checking the first
    prepared state; a separate 3G9 native reconciliation reacquires its own
    native guard. The two scopes are NOT atomic, and cannot be fused by passing
    a result object. Even a complete match cannot authorize an operation.
    """
    status = PrivateCanonicalProtectedHandoffState
    if (
        type(step) is not scratch.PrivateScratchWriterStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(status.INVALID_REQUEST)
    if step is not scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(status.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"linux", "win32"}:
        return _result(status.UNSUPPORTED)
    try:
        raw = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(raw) is not bytes
            or checked != proposed
            or type(checked) is not intents.PrivateTransactionIntent
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(status.INTENT_UNQUALIFIED)
        if checked.witness.operation is not witness.PrivateBindingOperation.FORK_COPY:
            return _result(status.FORK_REQUIRED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.descriptor_after) is not bytes
            or checked.descriptor_before == checked.descriptor_after
            or checked.registry_before == checked.registry_after
        ):
            return _result(status.INTENT_UNQUALIFIED)
        if expected_revision != checked.witness.registry_revision_before:
            return _result(status.REVISION_MISMATCH_REFUSED)
        if not _barrier_still_blocked(step, expected_revision, checked):
            return _result(status.BARRIER_UNQUALIFIED)
        first = sealed.review_sealed_native_pre_attempt_boundary(
            step,
            expected_revision,
            checked,
            existing_private_root,
            existing_workspace_root,
        )
        if type(first) is not sealed.PrivateSealedPreAttemptReview:
            return _result(status.PROTECTED_PREATTEMPT_REFUSED)
        if first.unqualified_requirements != barrier._REQUIRED:
            return _result(status.PROTECTED_PREATTEMPT_REFUSED)
        if (
            first.state
            is not sealed.PrivateSealedPreAttemptState.ONE_SHOT_PREATTEMPT_BLOCKED
        ):
            return _result(status.PROTECTED_SCOPE_DRIFT_PRESERVE)
        # This is deliberately a FRESH native scope, not the old held handle.
        second = recovery.reconcile_native_private_pending_registry_after_interruption(
            checked,
            existing_private_root,
            existing_workspace_root,
        )
        if type(second) is not recovery.PrivatePostcrashReconciliationReview:
            return _result(status.RECOVERY_REFUSED)
        if (
            second.state
            is recovery.PrivatePostcrashReconciliationState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED
        ):
            return _result(status.RECOVERY_REGISTRY_AFTER_PRESERVE)
        if (
            second.state
            is recovery.PrivatePostcrashReconciliationState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED
        ):
            return _result(status.RECOVERY_BOTH_AFTER_PRESERVE)
        if (
            second.state
            is not recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED
        ):
            return _result(status.RECOVERY_OTHER_PRESERVE)
        if not _barrier_still_blocked(step, expected_revision, checked):
            return _result(status.FINAL_BARRIER_CHANGED_PRESERVE)
        return _result(status.PREPARED_FORK_REOBSERVED_BLOCKED)
    except KeyboardInterrupt:
        return _result(status.INTERRUPTED_PRESERVE)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(status.INTENT_UNQUALIFIED)
    except OSError:
        return _result(status.IO_ERROR)
