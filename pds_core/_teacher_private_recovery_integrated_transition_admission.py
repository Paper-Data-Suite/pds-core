"""Core #238 Slice 3G43: integrate canonical native transition admission, read-only.

One operation-owned observational scope holds the existing cross-process ordered
locks, protected journal and descriptor, and retained registry/stage handles.
Native names, immutable canonical intent bytes, binding, revisions, owner and
all four protected byte images must agree throughout. This NEVER executes a
replacement or returns a mutation permit. Synthetic fakes are test-only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_pre_replace_window as window
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_recovery_transition_registry_custody as native
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_transaction_intent as intents


class PrivateIntegratedTransitionState(str, Enum):
    PREPARED_CANONICAL_CUSTODY_OBSERVED_NO_WRITE = (
        "prepared_canonical_custody_observed_no_write"
    )
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INTENT_UNQUALIFIED = "intent_unqualified"
    ROOT_UNQUALIFIED = "root_unqualified"
    OWNER_OR_PROTECTION_REFUSED = "owner_or_protection_refused"
    OWNER_CHANGED = "owner_changed"
    BINDING_MISMATCH = "binding_mismatch"
    CANONICAL_DESCRIPTION_CHANGED_PRESERVE = "canonical_description_changed_preserve"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    NATIVE_PAIR_REFUSED = "native_pair_refused"
    NATIVE_IDENTITY_CHANGED_PRESERVE = "native_identity_changed_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    PARENT_CHANGED_PRESERVE = "parent_changed_preserve"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateIntegratedTransitionState, str] = {
    item: "Integrated private transition evidence refused; preserve pending recovery artifacts."
    for item in PrivateIntegratedTransitionState
}
_MESSAGES[
    PrivateIntegratedTransitionState.PREPARED_CANONICAL_CUSTODY_OBSERVED_NO_WRITE
] = (
    "Canonical prepared transition remained under one retained native scope; "
    "no replacement or durability authority was issued."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateIntegratedTransitionReview:
    state: PrivateIntegratedTransitionState
    message: str
    pending_evidence_must_remain: bool = True
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(default=barrier._REQUIRED, repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateIntegratedTransitionReview(non_authorizing=True)"


def _result(
    state: PrivateIntegratedTransitionState,
) -> PrivateIntegratedTransitionReview:
    return PrivateIntegratedTransitionReview(state, _MESSAGES[state])


def review_integrated_native_prepared_transition(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateIntegratedTransitionReview:
    """Guard the *existing* prepared transaction without modifying its files.

    This entrypoint is never a permission to call os.replace. In particular,
    a positive review is invalidated as soon as this function releases its
    handles. Production writers must implement their own single-scope commit,
    postimage, durability, interruption and retirement phases.
    """
    state = PrivateIntegratedTransitionState
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
            or type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        before = checked.registry_before
        after = checked.registry_after
        descriptor_before = checked.descriptor_before
        if (
            type(before) is not bytes
            or type(after) is not bytes
            or type(descriptor_before) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        initial = window._description(step, expected_revision, checked)
        if initial is None:
            return _result(state.INTENT_UNQUALIFIED)
        refusal, owner = preflight._native_observation(existing_private_root)
        if refusal is not None or owner is None:
            return _result(state.OWNER_OR_PROTECTION_REFUSED)
        if (
            preflight._intent_owner_and_binding(checked, owner, existing_workspace_root)
            is not None
        ):
            return _result(state.BINDING_MISMATCH)
        transaction_id = checked.witness.transaction_id
        with transition._hold_transitionable_journal_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            # Do not accept a stale serialization, owner scope, or description
            # from an earlier, released guard.
            inside = intents.decode_private_transaction_intent(raw)
            if (
                inside != checked
                or inside != proposed
                or intents.encode_private_transaction_intent(inside) != raw
                or window._description(step, expected_revision, inside) != initial
            ):
                return _result(state.CANONICAL_DESCRIPTION_CHANGED_PRESERVE)
            namespace = recovery._namespace(existing_private_root, transaction_id)
            if (
                type(namespace) is not tuple
                or len(namespace) != 3
                or namespace[2] is not True
            ):
                return _result(state.NAMESPACE_CONFLICT_PRESERVE)
            inventory_expected = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            images: parents._Image = (raw, before, descriptor_before, after)
            with native._held_registry_stage_pair(
                existing_private_root, transaction_id, owner, len(before), len(after)
            ) as check:
                baseline: scope._Frame | None = None
                for frame_number in range(4):
                    current_refusal, current_owner = preflight._native_observation(
                        existing_private_root, owner
                    )
                    if (
                        current_refusal is not None
                        or current_owner is None
                        or ordered._owner() != owner
                    ):
                        return _result(state.OWNER_CHANGED)
                    if (
                        preflight._intent_owner_and_binding(
                            inside, owner, existing_workspace_root
                        )
                        is not None
                    ):
                        return _result(state.BINDING_MISMATCH)
                    if (
                        check()
                        is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
                    ):
                        return _result(state.NATIVE_IDENTITY_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root,
                        transaction_id,
                        owner,
                        namespace,
                        inventory_expected,
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    if (
                        frame_number in {1, 3}
                        and window._description(step, expected_revision, inside)
                        != initial
                    ):
                        return _result(state.CANONICAL_DESCRIPTION_CHANGED_PRESERVE)
                    frame = scope._observe(
                        existing_private_root,
                        existing_workspace_root,
                        inside,
                        owner,
                        len(raw),
                    )
                    if (
                        check()
                        is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
                    ):
                        return _result(state.NATIVE_IDENTITY_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root,
                        transaction_id,
                        owner,
                        namespace,
                        inventory_expected,
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    if (
                        window._frame_state(frame, baseline, images, initial, inside)
                        is not None
                    ):
                        return _result(state.IMAGE_CONFLICT_PRESERVE)
                    if baseline is None:
                        baseline = frame
                # A final, independent checkpoint still runs while the pair
                # and both ordered coordination locks remain held.
                final_refusal, final_owner = preflight._native_observation(
                    existing_private_root, owner
                )
                if (
                    final_refusal is not None
                    or final_owner is None
                    or ordered._owner() != owner
                ):
                    return _result(state.OWNER_CHANGED)
                if (
                    check()
                    is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
                ):
                    return _result(state.NATIVE_IDENTITY_CHANGED_PRESERVE)
                if not operation._same_native_namespace(
                    existing_private_root,
                    transaction_id,
                    owner,
                    namespace,
                    inventory_expected,
                ):
                    return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                if (
                    baseline is None
                    or parents._parents(existing_private_root, existing_workspace_root)
                    != baseline.parent_stamps
                ):
                    return _result(state.PARENT_CHANGED_PRESERVE)
        return _result(state.PREPARED_CANONICAL_CUSTODY_OBSERVED_NO_WRITE)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except transition._WriterGuardRefused:
        return _result(state.GUARD_REFUSED)
    except native._IdentityRefused:
        return _result(state.NATIVE_PAIR_REFUSED)
    except (
        scope._ImageUnqualified,
        parents._ParentUnqualified,
        bridge._IdentityUnqualified,
    ):
        return _result(state.IMAGE_CONFLICT_PRESERVE)
    except pair._NamespaceChanged:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except FileNotFoundError:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except PermissionError:
        return _result(state.GUARD_REFUSED)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        intents.PrivateIntentError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
