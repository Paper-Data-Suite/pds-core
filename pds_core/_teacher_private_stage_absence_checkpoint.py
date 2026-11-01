"""Retained native, *read-only* absent-stage recovery review (Core #238 3G4).

Slice 3G3 classifies supplied bytes with an optional stage, but cannot attest
that a missing stage is genuinely absent. This module joins the 3G3 pure
classifier to the existing native 3E/3F image readers, 3G2 namespace census,
protected stage inventory, and retained descriptor/registry/journal guards.

Even a matching stage-absent checkpoint is not proof that a native replacement
occurred, was durable, or can be replayed or retired. No writes or handles are
returned; hostile same-OS-user and cloud writers are outside this observation.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as exclusive
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_registry_stage_transition as transition
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateStageAbsenceCheckpointState(str, Enum):
    REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED = (
        "registry_after_descriptor_pending_review_required"
    )
    BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED = "both_after_stage_absent_review_required"
    STAGE_MISSING_BEFORE_REFUSED = "stage_missing_before_refused"
    STAGE_MISSING_PARTIAL_REFUSED = "stage_missing_partial_refused"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    NAMESPACE_UNQUALIFIED = "namespace_unqualified"
    NATIVE_IMAGE_UNQUALIFIED = "native_image_unqualified"
    CHECKPOINT_REFUSED = "checkpoint_refused"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateStageAbsenceCheckpointState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: "Registry after-image and absent stage observed; descriptor and durability review required.",
    PrivateStageAbsenceCheckpointState.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED: "After-images and absent stage observed; durability and retirement review required.",
    PrivateStageAbsenceCheckpointState.STAGE_MISSING_BEFORE_REFUSED: "Stage is absent while registry remains before-state; preserve recovery evidence.",
    PrivateStageAbsenceCheckpointState.STAGE_MISSING_PARTIAL_REFUSED: "Stage is absent with descriptor-only transition; preserve recovery evidence.",
    PrivateStageAbsenceCheckpointState.INVALID_REQUEST: "Private stage-absence request invalid.",
    PrivateStageAbsenceCheckpointState.INITIALIZATION_REFUSED: "First binding requires a separate guarded absence protocol.",
    PrivateStageAbsenceCheckpointState.UNSUPPORTED: "Native stage-absence checkpoint unsupported.",
    PrivateStageAbsenceCheckpointState.NAMESPACE_UNQUALIFIED: "Pending journal or private stage namespace is missing, unexpected, or changed.",
    PrivateStageAbsenceCheckpointState.NATIVE_IMAGE_UNQUALIFIED: "Protected journal or metadata bytes could not be verified consistently.",
    PrivateStageAbsenceCheckpointState.CHECKPOINT_REFUSED: "Observed journal and metadata cannot be reconciled to the proposed transition.",
    PrivateStageAbsenceCheckpointState.OWNER_CHANGED: "Effective OS owner changed during stage-absence review.",
    PrivateStageAbsenceCheckpointState.GUARD_REFUSED: "Retained native stage-absence guard refused the review.",
    PrivateStageAbsenceCheckpointState.IO_ERROR: "Private stage-absence checkpoint could not finish.",
}


@dataclass(frozen=True, slots=True)
class PrivateStageAbsenceCheckpointReview:
    """Bounded advisory response without owner, path, bytes, or write authority."""

    state: PrivateStageAbsenceCheckpointState
    message: str


def _result(
    state: PrivateStageAbsenceCheckpointState,
) -> PrivateStageAbsenceCheckpointReview:
    return PrivateStageAbsenceCheckpointReview(state, _MESSAGES[state])


def _namespace(
    root: Path, transaction_id: str
) -> tuple[frozenset[str], frozenset[str]]:
    """Two complete observations under an existing retained native guard.

    Directory enumeration only supports a lock-honoring local census; it does
    not give a cryptographic/provenance proof of deletion or distributed CAS.
    """
    pending = exclusive._names(root / "transactions")
    names = exclusive._names(root)
    if pending != frozenset({transaction_id + ".json"}):
        raise exclusive._NamespaceChanged
    if any("registry-stage" in item.casefold() for item in names):
        raise exclusive._NamespaceChanged
    return pending, names


def _images(
    proposed: intents.PrivateTransactionIntent,
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
) -> PrivateStageAbsenceCheckpointState:
    """Symmetric native images, read only, without reacquiring nested locks."""
    tx = proposed.witness.transaction_id
    directory = private_root / "transactions"
    journal_first = readers._journal(directory, tx, owner)
    registry_first = readers._registry(private_root, owner)
    descriptor_first = readers._descriptor(workspace_root)
    descriptor_second = readers._descriptor(workspace_root)
    registry_second = readers._registry(private_root, owner)
    journal_second = readers._journal(directory, tx, owner)
    if (
        readers._journal_failure(journal_first) is not None
        or readers._journal_failure(journal_second) is not None
        or readers._registry_failure(registry_first) is not None
        or readers._registry_failure(registry_second) is not None
        or readers._descriptor_failure(descriptor_first) is not None
        or readers._descriptor_failure(descriptor_second) is not None
        or type(journal_first.image) is not bytes
        or type(registry_first.image) is not bytes
        or type(descriptor_first.image) is not bytes
        or journal_first.image != journal_second.image
        or registry_first.image != registry_second.image
        or descriptor_first.image != descriptor_second.image
    ):
        return PrivateStageAbsenceCheckpointState.NATIVE_IMAGE_UNQUALIFIED
    classified = transition.classify_private_registry_stage_transition(
        proposed,
        observed_journal=journal_first.image,
        observed_registry=registry_first.image,
        observed_descriptor=descriptor_first.image,
        observed_stage=None,
    ).state
    mapping = {
        transition.PrivateRegistryStageTransitionState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: PrivateStageAbsenceCheckpointState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        transition.PrivateRegistryStageTransitionState.BOTH_AFTER_RETIREMENT_REVIEW_REQUIRED: PrivateStageAbsenceCheckpointState.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED,
        transition.PrivateRegistryStageTransitionState.STAGE_MISSING_BEFORE_REFUSED: PrivateStageAbsenceCheckpointState.STAGE_MISSING_BEFORE_REFUSED,
        transition.PrivateRegistryStageTransitionState.STAGE_MISSING_PARTIAL_REFUSED: PrivateStageAbsenceCheckpointState.STAGE_MISSING_PARTIAL_REFUSED,
    }
    return mapping.get(
        classified, PrivateStageAbsenceCheckpointState.CHECKPOINT_REFUSED
    )


def review_native_private_stage_absence(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateStageAbsenceCheckpointReview:
    """Advisory native journal+metadata checkpoint when NO stage was observed.

    Existing ordered locks plus journal/registry/descriptor native anchors are
    retained throughout the census and repeated byte reads. A double absence
    observation is NOT evidence of stage *consumption* (it could be missing for
    unrelated reasons), successful commit, persisted directory flushes or a
    safe decision to replay, retire, initialize or expose teacher-private data.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateStageAbsenceCheckpointState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateStageAbsenceCheckpointState.INVALID_REQUEST)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(PrivateStageAbsenceCheckpointState.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(PrivateStageAbsenceCheckpointState.INITIALIZATION_REFUSED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(PrivateStageAbsenceCheckpointState.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivateStageAbsenceCheckpointState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            namespace_before = _namespace(
                existing_private_root, checked.witness.transaction_id
            )
            if (
                readers._inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
            ):
                return _result(PrivateStageAbsenceCheckpointState.NAMESPACE_UNQUALIFIED)
            reviewed = _images(
                checked, existing_private_root, existing_workspace_root, owner
            )
            if (
                readers._inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
                or _namespace(existing_private_root, checked.witness.transaction_id)
                != namespace_before
            ):
                return _result(PrivateStageAbsenceCheckpointState.NAMESPACE_UNQUALIFIED)
            if ordered._owner() != owner:
                return _result(PrivateStageAbsenceCheckpointState.OWNER_CHANGED)
            return _result(reviewed)
    except exclusive._NamespaceChanged:
        return _result(PrivateStageAbsenceCheckpointState.NAMESPACE_UNQUALIFIED)
    except retained.RetainedDescriptorGuardError as error:
        if error.code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
            return _result(PrivateStageAbsenceCheckpointState.OWNER_CHANGED)
        if error.code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
            return _result(PrivateStageAbsenceCheckpointState.UNSUPPORTED)
        return _result(PrivateStageAbsenceCheckpointState.GUARD_REFUSED)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateStageAbsenceCheckpointState.OWNER_CHANGED)
        return _result(PrivateStageAbsenceCheckpointState.GUARD_REFUSED)
    except FileNotFoundError:
        return _result(PrivateStageAbsenceCheckpointState.NAMESPACE_UNQUALIFIED)
    except PermissionError:
        return _result(PrivateStageAbsenceCheckpointState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateStageAbsenceCheckpointState.IO_ERROR)
