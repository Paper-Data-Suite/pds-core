"""Non-authorizing, two-checkpoint recovery action preconditions (Core #238 3G10).

Consult 3G9's independently protected native read-only recovery checkpoint
*twice*, then compare both outcomes to a narrowly specified proposed next
step. Refuse drift, interruption and mismatched steps. Neither a matching
review nor two matching observations provides mutation/commit authority.

There are no writes, mutation callbacks, retained handles or public exports.
A later qualified coordinator must independently revalidate under its own
mutation-aware native scope; this advisory result is never reusable as a token.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_transaction_intent as intents


class PrivateRecoveryProposedStep(str, Enum):
    REVIEW_PREPARED_RESTART = "review_prepared_restart"
    REVIEW_DESCRIPTOR_COMPLETION = "review_descriptor_completion"
    REVIEW_JOURNAL_RETIREMENT = "review_journal_retirement"


class PrivateRecoveryActionPreconditionState(str, Enum):
    MATCHING_CHECKPOINT_REVIEW_REQUIRED = "matching_checkpoint_review_required"
    STAGE_CONFLICT_PRESERVE = "stage_conflict_preserve"
    ACTION_MISMATCH_REFUSED = "action_mismatch_refused"
    CHECKPOINT_CHANGED = "checkpoint_changed"
    CHECKPOINT_UNQUALIFIED = "checkpoint_unqualified"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateRecoveryActionPreconditionState.MATCHING_CHECKPOINT_REVIEW_REQUIRED: (
        "Two matching native checkpoints support reviewing the requested recovery step; no action is authorized."
    ),
    PrivateRecoveryActionPreconditionState.STAGE_CONFLICT_PRESERVE: (
        "A retained stage with changed metadata requires independent conflict review; preserve all evidence."
    ),
    PrivateRecoveryActionPreconditionState.ACTION_MISMATCH_REFUSED: (
        "The requested recovery step does not match the observed checkpoint; preserve all evidence."
    ),
    PrivateRecoveryActionPreconditionState.CHECKPOINT_CHANGED: (
        "Native recovery observations changed between protected scopes; preserve all evidence."
    ),
    PrivateRecoveryActionPreconditionState.CHECKPOINT_UNQUALIFIED: (
        "Native recovery evidence is missing, unsafe or unqualified; no recovery step is approved."
    ),
    PrivateRecoveryActionPreconditionState.INTERRUPTED_PRESERVE: (
        "Recovery precondition review was interrupted; preserve all evidence."
    ),
    PrivateRecoveryActionPreconditionState.INVALID_REQUEST: "Invalid recovery precondition review request.",
    PrivateRecoveryActionPreconditionState.UNSUPPORTED: "Native recovery precondition review unsupported.",
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryActionPreconditionReview:
    """Sanitized review only: no path, identity, transaction data or write token."""

    state: PrivateRecoveryActionPreconditionState
    message: str


def _result(
    state: PrivateRecoveryActionPreconditionState,
) -> PrivateRecoveryActionPreconditionReview:
    return PrivateRecoveryActionPreconditionReview(state, _MESSAGES[state])


_STEP_FOR_STATE = {
    recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED: (
        PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART
    ),
    recovery.PrivatePostcrashReconciliationState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: (
        PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION
    ),
    recovery.PrivatePostcrashReconciliationState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED: (
        PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT
    ),
}


def review_private_recovery_action_preconditions(
    requested_step: PrivateRecoveryProposedStep,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRecoveryActionPreconditionReview:
    """Compare two *separately guarded* 3G9 observations; never mutate data.

    Even success is advisory. Each 3G9 read releases its locks; a different
    process may change evidence between/after observations. Matching reads
    cannot replace a future atomic expected-revision CAS, teacher approval,
    descriptor writer or durability proof. Do not expose as a teacher command.
    """
    result = PrivateRecoveryActionPreconditionState
    if sys.platform not in {"linux", "win32"}:
        return _result(result.UNSUPPORTED)
    if (
        type(requested_step) is not PrivateRecoveryProposedStep
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(result.INVALID_REQUEST)

    try:
        first = recovery.reconcile_native_private_pending_registry_after_interruption(
            proposed, existing_private_root, existing_workspace_root
        )
        if (
            type(first) is not recovery.PrivatePostcrashReconciliationReview
            or type(first.state) is not recovery.PrivatePostcrashReconciliationState
        ):
            return _result(result.CHECKPOINT_UNQUALIFIED)
        if first.state is recovery.PrivatePostcrashReconciliationState.INVALID_REQUEST:
            return _result(result.INVALID_REQUEST)
        if first.state is recovery.PrivatePostcrashReconciliationState.UNSUPPORTED:
            return _result(result.UNSUPPORTED)
        reviewable = set(_STEP_FOR_STATE) | {
            recovery.PrivatePostcrashReconciliationState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED
        }
        if first.state not in reviewable:
            return _result(result.CHECKPOINT_UNQUALIFIED)
        second = recovery.reconcile_native_private_pending_registry_after_interruption(
            proposed, existing_private_root, existing_workspace_root
        )
        if (
            type(second) is not recovery.PrivatePostcrashReconciliationReview
            or type(second.state) is not recovery.PrivatePostcrashReconciliationState
        ):
            return _result(result.CHECKPOINT_UNQUALIFIED)
        if second.state is not first.state:
            return _result(result.CHECKPOINT_CHANGED)
        if (
            first.state
            is recovery.PrivatePostcrashReconciliationState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED
        ):
            return _result(result.STAGE_CONFLICT_PRESERVE)
        if _STEP_FOR_STATE[first.state] is not requested_step:
            return _result(result.ACTION_MISMATCH_REFUSED)
        return _result(result.MATCHING_CHECKPOINT_REVIEW_REQUIRED)
    except KeyboardInterrupt:
        return _result(result.INTERRUPTED_PRESERVE)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(result.CHECKPOINT_UNQUALIFIED)
