"""Native read-only post-crash registry-stage reconciliation (Core #238 3G9).

Combine the protected, exclusive stage-present (3G2) and stage-absent (3G4)
checkpoints under ONE existing retained descriptor/journal/registry guard. Never
reenter locking readers, infer crash durability, replay data, or retire a journal.

The review is an advisory observation of current bytes on a qualified local
filesystem; it does not prove the sequence of events before a power loss.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_stage_absence_checkpoint as absence
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivatePostcrashReconciliationState(str, Enum):
    STAGED_BEFORE_REVIEW_REQUIRED = "staged_before_review_required"
    STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED = (
        "stage_remains_other_checkpoint_review_required"
    )
    REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED = (
        "registry_after_descriptor_pending_review_required"
    )
    BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED = (
        "both_after_journal_pending_review_required"
    )
    STAGE_MISSING_BEFORE_REFUSED = "stage_missing_before_refused"
    STAGE_MISSING_PARTIAL_REFUSED = "stage_missing_partial_refused"
    IMAGES_UNQUALIFIED = "images_unqualified"
    NAMESPACE_UNQUALIFIED = "namespace_unqualified"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED: "Exact pending journal and prepared before-state observed; preserve stage and review admission.",
    PrivatePostcrashReconciliationState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED: "Pending journal and stage remain with non-before metadata; preserve all artifacts for recovery review.",
    PrivatePostcrashReconciliationState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: "Registry after-image and missing stage observed; descriptor completion and durability remain unqualified.",
    PrivatePostcrashReconciliationState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED: "Both after-images and missing stage observed; pending journal, durability and retirement require review.",
    PrivatePostcrashReconciliationState.STAGE_MISSING_BEFORE_REFUSED: "Stage is missing while registry remains before-image; preserve evidence without replay.",
    PrivatePostcrashReconciliationState.STAGE_MISSING_PARTIAL_REFUSED: "Stage is missing with descriptor-only metadata; preserve evidence without replay.",
    PrivatePostcrashReconciliationState.IMAGES_UNQUALIFIED: "Pending journal, descriptor, registry or stage images cannot be reconciled.",
    PrivatePostcrashReconciliationState.NAMESPACE_UNQUALIFIED: "Pending journal or staged-entry namespace is missing, competing or changed.",
    PrivatePostcrashReconciliationState.INVALID_REQUEST: "Post-crash reconciliation request invalid.",
    PrivatePostcrashReconciliationState.INITIALIZATION_REFUSED: "First binding requires a separate guarded absence protocol.",
    PrivatePostcrashReconciliationState.UNSUPPORTED: "Native post-crash reconciliation unsupported.",
    PrivatePostcrashReconciliationState.OWNER_CHANGED: "Effective OS owner changed during recovery review.",
    PrivatePostcrashReconciliationState.GUARD_REFUSED: "Retained native recovery guard refused review.",
    PrivatePostcrashReconciliationState.IO_ERROR: "Native post-crash review could not finish.",
}


@dataclass(frozen=True, slots=True)
class PrivatePostcrashReconciliationReview:
    """Sanitized state only; no paths, bytes, handles or write authority."""

    state: PrivatePostcrashReconciliationState
    message: str


def _result(
    state: PrivatePostcrashReconciliationState,
) -> PrivatePostcrashReconciliationReview:
    return PrivatePostcrashReconciliationReview(state, _MESSAGES[state])


def _namespace(root: Path, tx: str) -> tuple[frozenset[str], frozenset[str], bool]:
    """Complete census of both namespaces; accept only zero or one exact stage."""
    pending = pair._names(root / "transactions")
    names = pair._names(root)
    if pending != frozenset({tx + ".json"}):
        raise pair._NamespaceChanged
    stages = frozenset(name for name in names if "registry-stage" in name.casefold())
    expected_stage = "." + tx + ".registry-stage"
    if stages not in (frozenset(), frozenset({expected_stage})):
        raise pair._NamespaceChanged
    return pending, names, bool(stages)


def _classify_present(
    proposed: intents.PrivateTransactionIntent,
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
) -> PrivatePostcrashReconciliationState:
    """Invoke native 3G2 reader inside an already held native guard."""
    # The helper expects EffectiveOSOwner; _owner() supplies that exact type.
    status = pair._review_images(proposed, private_root, workspace_root, owner)
    state = pair.PrivateExclusivePairCheckpointState
    if status is state.MATCHING_BEFORE_REVIEW_REQUIRED:
        return PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED
    if status is state.OTHER_CHECKPOINT_REVIEW_REQUIRED:
        return PrivatePostcrashReconciliationState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED
    if status is state.NAMESPACE_UNQUALIFIED:
        return PrivatePostcrashReconciliationState.NAMESPACE_UNQUALIFIED
    if status is state.OWNER_CHANGED:
        return PrivatePostcrashReconciliationState.OWNER_CHANGED
    return PrivatePostcrashReconciliationState.IMAGES_UNQUALIFIED


def _classify_absent(
    proposed: intents.PrivateTransactionIntent,
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
) -> PrivatePostcrashReconciliationState:
    """Invoke native 3G4 reader inside an already held native guard."""
    status = absence._images(proposed, private_root, workspace_root, owner)
    state = absence.PrivateStageAbsenceCheckpointState
    mapping = {
        state.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: PrivatePostcrashReconciliationState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        state.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED: PrivatePostcrashReconciliationState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
        state.STAGE_MISSING_BEFORE_REFUSED: PrivatePostcrashReconciliationState.STAGE_MISSING_BEFORE_REFUSED,
        state.STAGE_MISSING_PARTIAL_REFUSED: PrivatePostcrashReconciliationState.STAGE_MISSING_PARTIAL_REFUSED,
        state.NAMESPACE_UNQUALIFIED: PrivatePostcrashReconciliationState.NAMESPACE_UNQUALIFIED,
        state.OWNER_CHANGED: PrivatePostcrashReconciliationState.OWNER_CHANGED,
    }
    return mapping.get(status, PrivatePostcrashReconciliationState.IMAGES_UNQUALIFIED)


def reconcile_native_private_pending_registry_after_interruption(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivatePostcrashReconciliationReview:
    """Single-lock stage-present/absent recovery observation, with zero writes.

    No observation grants authority to consume a stage, replay the registry,
    finish the descriptor, retire the journal, initialize or expose Notes.
    This does not certify file or parent-directory power-loss durability.
    """
    state = PrivatePostcrashReconciliationState
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
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
        ):
            return _result(state.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.witness.transaction_id) is not str
        ):
            return _result(state.INVALID_REQUEST)
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
            observed = _namespace(existing_private_root, checked.witness.transaction_id)
            expected_inventory = (
                inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                if observed[2]
                else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
            )
            if (
                readers._inventory(existing_private_root, owner)
                is not expected_inventory
            ):
                return _result(state.NAMESPACE_UNQUALIFIED)
            classified = (
                _classify_present(
                    checked, existing_private_root, existing_workspace_root, owner
                )
                if observed[2]
                else _classify_absent(
                    checked, existing_private_root, existing_workspace_root, owner
                )
            )
            if (
                readers._inventory(existing_private_root, owner)
                is not expected_inventory
                or _namespace(existing_private_root, checked.witness.transaction_id)
                != observed
            ):
                return _result(state.NAMESPACE_UNQUALIFIED)
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            answer = _result(classified)
        return answer  # Guard postcondition must succeed before any advisory result.
    except pair._NamespaceChanged:
        return _result(state.NAMESPACE_UNQUALIFIED)
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
        return _result(state.NAMESPACE_UNQUALIFIED)
    except PermissionError:
        return _result(state.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(state.IO_ERROR)
