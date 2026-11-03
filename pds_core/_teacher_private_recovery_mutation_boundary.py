"""Continuous native-lock recovery review boundary (Core #238 Slice 3G11).

Unlike 3G10's separate observations, hold the retained descriptor/journal/registry
scope continuously across two native checkpoint classifications and three
namespace/owner/inventory censuses. Detect intervening evidence changes even
under lock-honoring local writers. This is deliberately a *non-executing* gate:
no callback, action token, writes, journal retirement or Notes capability.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRecoveryMutationBoundaryState(str, Enum):
    MATCHING_RETAINED_REVIEW_REQUIRED = "matching_retained_review_required"
    STAGED_CONFLICT_PRESERVE = "staged_conflict_preserve"
    ACTION_MISMATCH_REFUSED = "action_mismatch_refused"
    IMAGE_DRIFT_PRESERVE = "image_drift_preserve"
    NAMESPACE_CHANGED_PRESERVE = "namespace_changed_preserve"
    OWNER_CHANGED = "owner_changed"
    CHECKPOINT_UNQUALIFIED = "checkpoint_unqualified"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRecoveryMutationBoundaryState.MATCHING_RETAINED_REVIEW_REQUIRED: "One continuous retained scope yielded matching native recovery images; no mutation is authorized.",
    PrivateRecoveryMutationBoundaryState.STAGED_CONFLICT_PRESERVE: "Stage and changed metadata require independent conflict review; preserve every recovery artifact.",
    PrivateRecoveryMutationBoundaryState.ACTION_MISMATCH_REFUSED: "Requested review step does not match the retained native checkpoint.",
    PrivateRecoveryMutationBoundaryState.IMAGE_DRIFT_PRESERVE: "Recovery checkpoint changed under retained guard; preserve every artifact.",
    PrivateRecoveryMutationBoundaryState.NAMESPACE_CHANGED_PRESERVE: "Journal/stage namespace or inventory changed or is unqualified; preserve all evidence.",
    PrivateRecoveryMutationBoundaryState.OWNER_CHANGED: "Effective local OS owner changed during retained review.",
    PrivateRecoveryMutationBoundaryState.CHECKPOINT_UNQUALIFIED: "Native recovery images are missing, invalid or unsafe; no action is approved.",
    PrivateRecoveryMutationBoundaryState.GUARD_REFUSED: "Retained native protection refused the recovery boundary.",
    PrivateRecoveryMutationBoundaryState.INTERRUPTED_PRESERVE: "Native recovery review interrupted; preserve all evidence.",
    PrivateRecoveryMutationBoundaryState.INVALID_REQUEST: "Invalid retained recovery review request.",
    PrivateRecoveryMutationBoundaryState.INITIALIZATION_REFUSED: "First binding requires an independent guarded absence protocol.",
    PrivateRecoveryMutationBoundaryState.UNSUPPORTED: "Retained native recovery review unsupported on this platform.",
    PrivateRecoveryMutationBoundaryState.IO_ERROR: "Retained native recovery observation could not finish.",
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryMutationBoundaryReview:
    """Sanitized result, not an action, commit token or replay permit."""

    state: PrivateRecoveryMutationBoundaryState
    message: str


def _result(
    state: PrivateRecoveryMutationBoundaryState,
) -> PrivateRecoveryMutationBoundaryReview:
    return PrivateRecoveryMutationBoundaryReview(state, _MESSAGES[state])


_ALLOWED = {
    recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED: actions.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART,
    recovery.PrivatePostcrashReconciliationState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: actions.PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION,
    recovery.PrivatePostcrashReconciliationState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED: actions.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT,
}


def review_retained_private_recovery_mutation_boundary(
    requested_step: actions.PrivateRecoveryProposedStep,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRecoveryMutationBoundaryReview:
    """Review proposed *recovery inspection*, never perform or reserve a write.

    Two native classifications and three namespace/inventory/owner checks all
    occur within a SINGLE retained descriptor guard. No reentrant acquisition
    or untrusted callbacks. The guard must release successfully before even an
    advisory matching result is returned. Lock continuity alone cannot prove
    power-loss durability, defeat hostile same-user modification or supply CAS.
    """
    state = PrivateRecoveryMutationBoundaryState
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    if (
        type(requested_step) is not actions.PrivateRecoveryProposedStep
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(state.INVALID_REQUEST)
    try:
        encoded = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(encoded)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != encoded
            or type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.witness.transaction_id) is not str
        ):
            return _result(state.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)

    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            namespace = recovery._namespace(
                existing_private_root, checked.witness.transaction_id
            )
            expected_inventory = (
                inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                if namespace[2]
                else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
            )
            findings: list[recovery.PrivatePostcrashReconciliationState] = []
            for _ in range(2):
                if (
                    readers._inventory(existing_private_root, owner)
                    is not expected_inventory
                ):
                    return _result(state.NAMESPACE_CHANGED_PRESERVE)
                if (
                    recovery._namespace(
                        existing_private_root, checked.witness.transaction_id
                    )
                    != namespace
                ):
                    return _result(state.NAMESPACE_CHANGED_PRESERVE)
                if ordered._owner() != owner:
                    return _result(state.OWNER_CHANGED)
                current = (
                    recovery._classify_present(
                        checked, existing_private_root, existing_workspace_root, owner
                    )
                    if namespace[2]
                    else recovery._classify_absent(
                        checked, existing_private_root, existing_workspace_root, owner
                    )
                )
                if type(current) is not recovery.PrivatePostcrashReconciliationState:
                    return _result(state.CHECKPOINT_UNQUALIFIED)
                findings.append(current)
            if (
                readers._inventory(existing_private_root, owner)
                is not expected_inventory
            ):
                return _result(state.NAMESPACE_CHANGED_PRESERVE)
            if (
                recovery._namespace(
                    existing_private_root, checked.witness.transaction_id
                )
                != namespace
            ):
                return _result(state.NAMESPACE_CHANGED_PRESERVE)
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            first, second = findings
            if first is not second:
                answer = state.IMAGE_DRIFT_PRESERVE
            elif (
                first
                is recovery.PrivatePostcrashReconciliationState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED
            ):
                answer = state.STAGED_CONFLICT_PRESERVE
            elif first not in _ALLOWED:
                answer = state.CHECKPOINT_UNQUALIFIED
            elif _ALLOWED[first] is not requested_step:
                answer = state.ACTION_MISMATCH_REFUSED
            else:
                answer = state.MATCHING_RETAINED_REVIEW_REQUIRED
        return _result(answer)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except pair._NamespaceChanged:
        return _result(state.NAMESPACE_CHANGED_PRESERVE)
    except retained.RetainedDescriptorGuardError as error:
        if error.code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
            return _result(state.OWNER_CHANGED)
        if error.code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
            return _result(state.UNSUPPORTED)
        return _result(state.GUARD_REFUSED)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(state.OWNER_CHANGED)
        return _result(state.GUARD_REFUSED)
    except FileNotFoundError:
        return _result(state.NAMESPACE_CHANGED_PRESERVE)
    except PermissionError:
        return _result(state.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(state.IO_ERROR)
