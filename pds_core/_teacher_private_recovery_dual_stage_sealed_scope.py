"""One continuously guarded canonical FORK_COPY *observation* (#238 3G56).

The operation-owned journal/descriptor lock and native registry/stage identity
window enclose all three frame observations. The additional workspace descriptor
after-stage is independently reopened in every frame and must retain its exact
canonical image and identity. This is deliberately NOT a writer: no attempt
marker, os.replace, callback, handle export, journal retirement or Notes access.
An observed stage identity between opens cannot rule out transient swaps or
prove power-loss durability; no returned object grants operation authority.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_descriptor_stage_custody as stages
from pds_core import _teacher_private_recovery_one_shot_transition_pair as one_shot
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_recovery_transition_registry_custody as native
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateDualStageScopeState(str, Enum):
    DUAL_STAGES_OBSERVED_BARRIER_BLOCKED = "dual_stages_observed_barrier_blocked"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    INTENT_UNQUALIFIED = "intent_unqualified"
    FORK_REQUIRED = "fork_required"
    REVISION_MISMATCH = "revision_mismatch"
    ROOT_UNQUALIFIED = "root_unqualified"
    BARRIER_REFUSED = "barrier_refused"
    OWNER_OR_BINDING_REFUSED = "owner_or_binding_refused"
    OWNER_CHANGED = "owner_changed"
    CANONICAL_DRIFT_PRESERVE = "canonical_drift_preserve"
    REGISTRY_STAGE_CHANGED_PRESERVE = "registry_stage_changed_preserve"
    REGISTRY_IMAGE_CONFLICT_PRESERVE = "registry_image_conflict_preserve"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    DESCRIPTOR_STAGE_MISSING_PRESERVE = "descriptor_stage_missing_preserve"
    DESCRIPTOR_STAGE_UNSAFE_PRESERVE = "descriptor_stage_unsafe_preserve"
    DESCRIPTOR_STAGE_IMAGE_CONFLICT_PRESERVE = (
        "descriptor_stage_image_conflict_preserve"
    )
    DESCRIPTOR_STAGE_CHANGED_PRESERVE = "descriptor_stage_changed_preserve"
    ATTEMPT_MARKER_CONFLICT_PRESERVE = "attempt_marker_conflict_preserve"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateDualStageScopeState, str] = {
    item: "Canonical dual-stage native custody refused; preserve pending recovery evidence."
    for item in PrivateDualStageScopeState
}
_MESSAGES[PrivateDualStageScopeState.DUAL_STAGES_OBSERVED_BARRIER_BLOCKED] = (
    "Registry and descriptor stages were observed within one retained native scope; "
    "no attempt was marked and production mutation remains blocked."
)
_MESSAGES[PrivateDualStageScopeState.DESCRIPTOR_STAGE_MISSING_PRESERVE] = (
    "Canonical descriptor after-stage is missing; preserve pending evidence."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDualStageScopeReview:
    state: PrivateDualStageScopeState
    message: str
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    automatic_replay_forbidden: bool = True
    journal_retirement_forbidden: bool = True
    durable_commit_unqualified: bool = True
    custody_expired_on_release: bool = True
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(default=barrier._REQUIRED, repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateDualStageScopeReview(non_authorizing=True)"


def _result(state: PrivateDualStageScopeState) -> PrivateDualStageScopeReview:
    return PrivateDualStageScopeReview(state, _MESSAGES[state])


def _canonical(
    proposed: intents.PrivateTransactionIntent,
) -> tuple[intents.PrivateTransactionIntent, bytes] | None:
    try:
        raw = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(raw) is not bytes
            or type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return None
        return checked, raw
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return None


def review_canonical_fork_dual_stage_sealed_scope(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateDualStageScopeReview:
    """Read canonical prepared images and BOTH stages under one native scope.

    No callback, pre-authorized prior result, caller-supplied handle, or write
    destination is accepted. The ordinary Core production barrier is not
    weakened. Returned observations are stale immediately after guard release.
    """
    state = PrivateDualStageScopeState
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
    validated = _canonical(proposed)
    if validated is None:
        return _result(state.INTENT_UNQUALIFIED)
    checked, raw = validated
    if checked.witness.operation is not witness.PrivateBindingOperation.FORK_COPY:
        return _result(state.FORK_REQUIRED)
    before = checked.registry_before
    after = checked.registry_after
    descriptor_before = checked.descriptor_before
    descriptor_after = checked.descriptor_after
    if (
        type(before) is not bytes
        or type(after) is not bytes
        or before == after
        or type(descriptor_before) is not bytes
        or type(descriptor_after) is not bytes
        or descriptor_before == descriptor_after
    ):
        return _result(state.INTENT_UNQUALIFIED)
    if expected_revision != checked.witness.registry_revision_before:
        return _result(state.REVISION_MISMATCH)
    if not lock_file._requested_root(
        existing_private_root, sys.platform
    ) or not descriptor._valid_root(existing_workspace_root):
        return _result(state.ROOT_UNQUALIFIED)
    if not stages._barrier_blocked(step, expected_revision, checked):
        return _result(state.BARRIER_REFUSED)

    expected_images: tuple[bytes, bytes, bytes, bytes] = (
        raw,
        before,
        descriptor_before,
        after,
    )
    stage_name = f".{checked.witness.transaction_id}.descriptor-stage"
    try:
        refusal, owner = preflight._native_observation(existing_private_root)
        if refusal is not None or owner is None:
            return _result(state.OWNER_OR_BINDING_REFUSED)
        if (
            preflight._intent_owner_and_binding(checked, owner, existing_workspace_root)
            is not None
        ):
            return _result(state.OWNER_OR_BINDING_REFUSED)
        with transition._hold_transitionable_journal_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            inside = _canonical(proposed)
            if inside is None or inside != validated:
                return _result(state.CANONICAL_DRIFT_PRESERVE)
            with one_shot._held_one_shot_transition_pair(
                existing_private_root,
                checked.witness.transaction_id,
                owner,
                len(before),
                len(after),
            ) as held:
                baseline: scope._Frame | None = None
                first_stage: stages._StageRead | None = None
                for _ in range(3):
                    current_refusal, current_owner = preflight._native_observation(
                        existing_private_root, owner
                    )
                    if (
                        current_refusal is not None
                        or current_owner is None
                        or current_owner != owner
                        or ordered._owner() != owner
                    ):
                        return _result(state.OWNER_CHANGED)
                    if (
                        preflight._intent_owner_and_binding(
                            checked, owner, existing_workspace_root
                        )
                        is not None
                    ):
                        return _result(state.OWNER_OR_BINDING_REFUSED)
                    if _canonical(proposed) != validated:
                        return _result(state.CANONICAL_DRIFT_PRESERVE)
                    if held.attempted:
                        return _result(state.ATTEMPT_MARKER_CONFLICT_PRESERVE)
                    if (
                        held.observe()
                        is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
                    ):
                        return _result(state.REGISTRY_STAGE_CHANGED_PRESERVE)
                    frame = scope._observe(
                        existing_private_root,
                        existing_workspace_root,
                        checked,
                        owner,
                        len(raw),
                    )
                    if scope._frame_state(frame, baseline, expected_images) is not None:
                        return _result(state.REGISTRY_IMAGE_CONFLICT_PRESERVE)
                    if baseline is None:
                        baseline = frame
                    if (
                        recovery._classify_present(
                            checked,
                            existing_private_root,
                            existing_workspace_root,
                            owner,
                        )
                        is not recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED
                    ):
                        return _result(state.CHECKPOINT_CONFLICT_PRESERVE)
                    observed = stages._read_stage(existing_workspace_root, stage_name)
                    if observed.state is stages._ReadState.MISSING:
                        return _result(state.DESCRIPTOR_STAGE_MISSING_PRESERVE)
                    if (
                        observed.state is not stages._ReadState.OBSERVED
                        or type(observed.image) is not bytes
                        or observed.identity is None
                    ):
                        return _result(state.DESCRIPTOR_STAGE_UNSAFE_PRESERVE)
                    if observed.image != descriptor_after:
                        return _result(state.DESCRIPTOR_STAGE_IMAGE_CONFLICT_PRESERVE)
                    if first_stage is None:
                        first_stage = observed
                    elif first_stage != observed:
                        return _result(state.DESCRIPTOR_STAGE_CHANGED_PRESERVE)
                    if (
                        held.attempted
                        or held.observe()
                        is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
                    ):
                        return _result(state.REGISTRY_STAGE_CHANGED_PRESERVE)
                if not stages._barrier_blocked(step, expected_revision, checked):
                    return _result(state.BARRIER_REFUSED)
                if held.attempted:
                    return _result(state.ATTEMPT_MARKER_CONFLICT_PRESERVE)
                if ordered._owner() != owner:
                    return _result(state.OWNER_CHANGED)
        return _result(state.DUAL_STAGES_OBSERVED_BARRIER_BLOCKED)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except (transition._WriterGuardRefused, one_shot._AttemptScopeRefused):
        return _result(state.GUARD_REFUSED)
    except intents.PrivateIntentError:
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
