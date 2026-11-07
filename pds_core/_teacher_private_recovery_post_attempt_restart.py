"""Native restart handoff after an uncertain registry replacement (#238 3G47).

A prior one-shot attempt is NEVER a commit certificate. This function independently
re-opens the pending journal, registry, association descriptor, and stage census
using Core's existing native protected postcrash reconciliation scope. No stage,
registry or journal is changed; no retry, retirement or Notes activation occurs.

This is a recovery *classification*, not an admission token or a durable proof.
A preflight observed before the native guard is advisory and is not carried
forward as a write permit. Unsupported permissions and ambiguous states fail
closed while preserving every pending recovery artifact.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivatePostAttemptRestartState(str, Enum):
    PREPARED_STAGE_PENDING_REVIEW = "prepared_stage_pending_review"
    REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW = (
        "registry_after_descriptor_pending_review"
    )
    BOTH_AFTER_JOURNAL_PENDING_REVIEW = "both_after_journal_pending_review"
    STAGE_REMAINS_OTHER_CHECKPOINT_PRESERVE = "stage_remains_other_checkpoint_preserve"
    STAGE_MISSING_BEFORE_PRESERVE = "stage_missing_before_preserve"
    STAGE_MISSING_PARTIAL_PRESERVE = "stage_missing_partial_preserve"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    IMAGE_UNQUALIFIED_PRESERVE = "image_unqualified_preserve"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INITIALIZATION_REFUSED = "initialization_refused"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INTENT_UNQUALIFIED = "intent_unqualified"
    ROOT_UNQUALIFIED = "root_unqualified"
    UNSUPPORTED = "unsupported"
    OWNER_OR_PROTECTION_REFUSED = "owner_or_protection_refused"
    BINDING_MISMATCH = "binding_mismatch"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivatePostAttemptRestartState, str] = {
    key: "Independent private recovery checkpoint refused or remains unresolved; "
    "preserve the pending transaction and do not retry replacement."
    for key in PrivatePostAttemptRestartState
}
_MESSAGES[PrivatePostAttemptRestartState.PREPARED_STAGE_PENDING_REVIEW] = (
    "Native prepared before-state and stage observed after an uncertain attempt; "
    "do not assume the previous operation never occurred or retry it."
)
_MESSAGES[PrivatePostAttemptRestartState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW] = (
    "Native registry after-image and pending descriptor observed; "
    "durable recovery and descriptor completion are not authorized."
)
_MESSAGES[PrivatePostAttemptRestartState.BOTH_AFTER_JOURNAL_PENDING_REVIEW] = (
    "Both native after-images and pending journal observed; "
    "durability and retirement have not been qualified."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivatePostAttemptRestartReview:
    state: PrivatePostAttemptRestartState
    message: str
    replacement_may_have_occurred: bool = True
    pending_evidence_must_remain: bool = True
    automatic_retry_forbidden: bool = True
    production_writes_blocked: bool = True
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(default=barrier._REQUIRED, repr=False)
    )

    def __repr__(self) -> str:
        return "PrivatePostAttemptRestartReview(non_authorizing=True)"


def _result(state: PrivatePostAttemptRestartState) -> PrivatePostAttemptRestartReview:
    return PrivatePostAttemptRestartReview(state, _MESSAGES[state])


_MAP: dict[
    recovery.PrivatePostcrashReconciliationState, PrivatePostAttemptRestartState
] = {
    recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED: PrivatePostAttemptRestartState.PREPARED_STAGE_PENDING_REVIEW,
    recovery.PrivatePostcrashReconciliationState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: PrivatePostAttemptRestartState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW,
    recovery.PrivatePostcrashReconciliationState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED: PrivatePostAttemptRestartState.BOTH_AFTER_JOURNAL_PENDING_REVIEW,
    recovery.PrivatePostcrashReconciliationState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED: PrivatePostAttemptRestartState.STAGE_REMAINS_OTHER_CHECKPOINT_PRESERVE,
    recovery.PrivatePostcrashReconciliationState.STAGE_MISSING_BEFORE_REFUSED: PrivatePostAttemptRestartState.STAGE_MISSING_BEFORE_PRESERVE,
    recovery.PrivatePostcrashReconciliationState.STAGE_MISSING_PARTIAL_REFUSED: PrivatePostAttemptRestartState.STAGE_MISSING_PARTIAL_PRESERVE,
    recovery.PrivatePostcrashReconciliationState.IMAGES_UNQUALIFIED: PrivatePostAttemptRestartState.IMAGE_UNQUALIFIED_PRESERVE,
    recovery.PrivatePostcrashReconciliationState.NAMESPACE_UNQUALIFIED: PrivatePostAttemptRestartState.NAMESPACE_CONFLICT_PRESERVE,
    recovery.PrivatePostcrashReconciliationState.INVALID_REQUEST: PrivatePostAttemptRestartState.INTENT_UNQUALIFIED,
    recovery.PrivatePostcrashReconciliationState.INITIALIZATION_REFUSED: PrivatePostAttemptRestartState.INITIALIZATION_REFUSED,
    recovery.PrivatePostcrashReconciliationState.UNSUPPORTED: PrivatePostAttemptRestartState.UNSUPPORTED,
    recovery.PrivatePostcrashReconciliationState.OWNER_CHANGED: PrivatePostAttemptRestartState.OWNER_CHANGED,
    recovery.PrivatePostcrashReconciliationState.GUARD_REFUSED: PrivatePostAttemptRestartState.GUARD_REFUSED,
    recovery.PrivatePostcrashReconciliationState.IO_ERROR: PrivatePostAttemptRestartState.IO_ERROR,
}


def review_private_post_attempt_native_restart(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivatePostAttemptRestartReview:
    """Re-establish native state AFTER an unknown/attempted registry transition.

    An attempted operation is assumed; this method does not accept a claimed
    commit result, observed images, arbitrary checkpoint, callback, or retry
    token. It acquires a *new* native reconciliation scope independently.
    The old process's handle/guard has no authority in this restart.
    """
    state = PrivatePostAttemptRestartState
    if (
        type(step) is not scratch.PrivateScratchWriterStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(state.INVALID_REQUEST)
    if step is not scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if not lock_file._requested_root(
        existing_private_root, sys.platform
    ) or not descriptor._valid_root(existing_workspace_root):
        return _result(state.ROOT_UNQUALIFIED)
    try:
        decision = barrier.review_private_production_write_barrier(
            step, expected_revision, proposed
        )
        if type(decision) is not barrier.PrivateProductionWriteBarrierReview:
            return _result(state.INTENT_UNQUALIFIED)
        if (
            decision.state
            is barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ):
            return _result(state.REVISION_MISMATCH_REFUSED)
        if (
            decision.state
            is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
            or decision.unqualified_requirements != barrier._REQUIRED
        ):
            return _result(state.INTENT_UNQUALIFIED)
        raw = intents.encode_private_transaction_intent(proposed)
        if type(raw) is not bytes or not (0 < len(raw) <= intents.MAX_INTENT_BYTES):
            return _result(state.INTENT_UNQUALIFIED)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(state.INTENT_UNQUALIFIED)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.descriptor_after) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        before = metadata.decode_private_registry(checked.registry_before)
        after = metadata.decode_private_registry(checked.registry_after)
        if (
            metadata.encode_private_registry(before) != checked.registry_before
            or metadata.encode_private_registry(after) != checked.registry_after
            or before.revision != expected_revision
            or after.revision != before.revision + 1
            or checked.witness.registry_revision_before != before.revision
            or checked.witness.registry_revision_after != after.revision
        ):
            return _result(state.REVISION_MISMATCH_REFUSED)
        refusal, owner = preflight._native_observation(existing_private_root)
        if refusal is not None or owner is None:
            return _result(state.OWNER_OR_PROTECTION_REFUSED)
        if (
            preflight._intent_owner_and_binding(checked, owner, existing_workspace_root)
            is not None
        ):
            return _result(state.BINDING_MISMATCH)
        # The native reconciliation reader acquires fresh ordered locks, retains
        # the journal/registry/descriptor, and verifies its own native byte
        # images and namespace. Never hold or reuse an earlier attempt scope.
        observed = (
            recovery.reconcile_native_private_pending_registry_after_interruption(
                checked, existing_private_root, existing_workspace_root
            )
        )
        if type(observed) is not recovery.PrivatePostcrashReconciliationReview:
            return _result(state.CHECKPOINT_CONFLICT_PRESERVE)
        observed_state = observed.state
        if type(observed_state) is not recovery.PrivatePostcrashReconciliationState:
            return _result(state.CHECKPOINT_CONFLICT_PRESERVE)
        return _result(_MAP.get(observed_state, state.CHECKPOINT_CONFLICT_PRESERVE))
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except (intents.PrivateIntentError, metadata.PrivateMetadataError):
        return _result(state.INTENT_UNQUALIFIED)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
