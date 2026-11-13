"""Read-only native journal/metadata/stage checkpoint (#238 Slice 3F5).

One retained scope protects ordered local locks and journal, private registry and
workspace descriptor anchors. Native reads are internal and never reacquire
those locks. Exact matches are advisory, not journal durability, CAS authority,
replay, stage cleanup or Notes access.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_crash_checkpoint as checkpoint
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_image_snapshot as stage_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRetainedStageCheckpointState(str, Enum):
    MATCHING_BEFORE_STAGE_REVIEW_REQUIRED = "matching_before_stage_review_required"
    OTHER_CHECKPOINT_REVIEW_REQUIRED = "other_checkpoint_review_required"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    STAGE_INVENTORY_UNQUALIFIED = "stage_inventory_unqualified"
    JOURNAL_UNQUALIFIED = "journal_unqualified"
    REGISTRY_UNQUALIFIED = "registry_unqualified"
    DESCRIPTOR_UNQUALIFIED = "descriptor_unqualified"
    STAGE_UNQUALIFIED = "stage_unqualified"
    IMAGES_CHANGED = "images_changed"
    STAGE_MISMATCH = "stage_mismatch"
    CHECKPOINT_REFUSED = "checkpoint_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRetainedStageCheckpointState.MATCHING_BEFORE_STAGE_REVIEW_REQUIRED: "A named native stage and journal match one before-state proposal; independent recovery review required.",
    PrivateRetainedStageCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED: "Journal and metadata indicate a non-before checkpoint; independent recovery review required.",
    PrivateRetainedStageCheckpointState.INVALID_REQUEST: "Retained stage checkpoint request invalid.",
    PrivateRetainedStageCheckpointState.INITIALIZATION_REFUSED: "Initialization needs a separate guarded absence and persistence protocol.",
    PrivateRetainedStageCheckpointState.UNSUPPORTED: "Retained stage checkpoint review unsupported.",
    PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE: "Effective native OS owner unavailable.",
    PrivateRetainedStageCheckpointState.OWNER_CHANGED: "Effective native OS owner changed during review.",
    PrivateRetainedStageCheckpointState.GUARD_REFUSED: "Retained native guard refused or changed during review.",
    PrivateRetainedStageCheckpointState.STAGE_INVENTORY_UNQUALIFIED: "Stage inventory is missing, unsafe or unqualified; review pending artifacts.",
    PrivateRetainedStageCheckpointState.JOURNAL_UNQUALIFIED: "Named journal is missing or failed native qualification.",
    PrivateRetainedStageCheckpointState.REGISTRY_UNQUALIFIED: "Live registry failed native qualification.",
    PrivateRetainedStageCheckpointState.DESCRIPTOR_UNQUALIFIED: "Workspace descriptor failed native qualification.",
    PrivateRetainedStageCheckpointState.STAGE_UNQUALIFIED: "Named registry stage failed native qualification.",
    PrivateRetainedStageCheckpointState.IMAGES_CHANGED: "One or more native images changed across observations.",
    PrivateRetainedStageCheckpointState.STAGE_MISMATCH: "Named stage bytes do not exactly match the proposed after-image.",
    PrivateRetainedStageCheckpointState.CHECKPOINT_REFUSED: "Journal and live metadata cannot be reconciled to the proposed intent.",
    PrivateRetainedStageCheckpointState.IO_ERROR: "Retained stage checkpoint review stopped without mutation.",
}


@dataclass(frozen=True, slots=True)
class PrivateRetainedStageCheckpointReview:
    """No private byte images, paths, owner IDs, file handles or write tokens."""

    state: PrivateRetainedStageCheckpointState
    message: str


def _result(
    state: PrivateRetainedStageCheckpointState,
) -> PrivateRetainedStageCheckpointReview:
    return PrivateRetainedStageCheckpointReview(state, _MESSAGES[state])


def _inventory(
    root: Path, owner: inspection.EffectiveOSOwner
) -> inventory.PrivateRegistryStageInventoryState:
    return (
        inventory._scan_linux(root, owner)
        if sys.platform == "linux"
        else inventory._scan_windows(root, owner)
    )


def _journal(
    directory: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> journal.PrivateJournalImageReview:
    return (
        journal._read_linux(directory, transaction_id, owner)
        if sys.platform == "linux"
        else journal._read_windows(directory, transaction_id, owner)
    )


def _registry(
    root: Path, owner: inspection.EffectiveOSOwner
) -> registry_image.PrivateRegistryImageReview:
    return (
        registry_image._read_linux(root, owner)
        if sys.platform == "linux"
        else registry_image._read_windows(root, owner)
    )


def _descriptor(root: Path) -> descriptor_image.PrivateDescriptorImageReview:
    return (
        descriptor_image._read_linux(root)
        if sys.platform == "linux"
        else descriptor_image._read_windows(root)
    )


def _stage(
    root: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> stage_image.PrivateRegistryStageImageReview:
    return stage_image._native_image(root, transaction_id, owner)


def _guard_failure(
    code: retained.RetainedDescriptorGuardCode,
) -> PrivateRetainedStageCheckpointState:
    if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
        return PrivateRetainedStageCheckpointState.OWNER_CHANGED
    if code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE:
        return PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE
    if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
        return PrivateRetainedStageCheckpointState.UNSUPPORTED
    return PrivateRetainedStageCheckpointState.GUARD_REFUSED


def _journal_failure(
    observed: journal.PrivateJournalImageReview,
) -> PrivateRetainedStageCheckpointState | None:
    if (
        observed.state is journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
        and type(observed.image) is bytes
    ):
        return None
    if observed.state is journal.PrivateJournalImageState.OWNER_CHANGED:
        return PrivateRetainedStageCheckpointState.OWNER_CHANGED
    if observed.state is journal.PrivateJournalImageState.OWNER_UNAVAILABLE:
        return PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE
    return PrivateRetainedStageCheckpointState.JOURNAL_UNQUALIFIED


def _registry_failure(
    observed: registry_image.PrivateRegistryImageReview,
) -> PrivateRetainedStageCheckpointState | None:
    if (
        observed.state
        is registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
        and type(observed.image) is bytes
    ):
        return None
    if observed.state is registry_image.PrivateRegistryImageState.OWNER_CHANGED:
        return PrivateRetainedStageCheckpointState.OWNER_CHANGED
    if observed.state is registry_image.PrivateRegistryImageState.OWNER_UNAVAILABLE:
        return PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE
    return PrivateRetainedStageCheckpointState.REGISTRY_UNQUALIFIED


def _descriptor_failure(
    observed: descriptor_image.PrivateDescriptorImageReview,
) -> PrivateRetainedStageCheckpointState | None:
    if (
        observed.state
        is descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
        and type(observed.image) is bytes
    ):
        return None
    if observed.state is descriptor_image.PrivateDescriptorImageState.OWNER_CHANGED:
        return PrivateRetainedStageCheckpointState.OWNER_CHANGED
    if observed.state is descriptor_image.PrivateDescriptorImageState.OWNER_UNAVAILABLE:
        return PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE
    return PrivateRetainedStageCheckpointState.DESCRIPTOR_UNQUALIFIED


def _stage_failure(
    observed: stage_image.PrivateRegistryStageImageReview,
) -> PrivateRetainedStageCheckpointState | None:
    if (
        observed.state
        is stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
        and type(observed.image) is bytes
    ):
        return None
    if observed.state is stage_image.PrivateRegistryStageImageState.OWNER_CHANGED:
        return PrivateRetainedStageCheckpointState.OWNER_CHANGED
    if observed.state is stage_image.PrivateRegistryStageImageState.OWNER_UNAVAILABLE:
        return PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE
    return PrivateRetainedStageCheckpointState.STAGE_UNQUALIFIED


def review_retained_registry_stage_checkpoint(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRetainedStageCheckpointReview:
    """Observe one named journal and stage with two live metadata reads.

    Order: stage inventory, journal, registry, descriptor, stage, stage,
    descriptor, registry, journal, inventory. No caller-supplied image, no
    nested public lock acquisition, no mutation. A general stage inventory
    cannot prove that *only* this one stage exists; further exclusivity and
    cleanup decisions require a future protocol. A matching state grants no
    durability or CAS authority, including on cloud-synced workspaces.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRetainedStageCheckpointState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateRetainedStageCheckpointState.INVALID_REQUEST)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(PrivateRetainedStageCheckpointState.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(PrivateRetainedStageCheckpointState.INITIALIZATION_REFUSED)
        if stage_image._stage_name(checked.witness.transaction_id) is None:
            return _result(PrivateRetainedStageCheckpointState.INVALID_REQUEST)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(PrivateRetainedStageCheckpointState.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        AttributeError,
        TypeError,
        OverflowError,
    ):
        return _result(PrivateRetainedStageCheckpointState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            tx = checked.witness.transaction_id
            directory = existing_private_root / "transactions"
            if (
                _inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            ):
                return _result(
                    PrivateRetainedStageCheckpointState.STAGE_INVENTORY_UNQUALIFIED
                )
            first_journal = _journal(directory, tx, owner)
            failure = _journal_failure(first_journal)
            if failure is not None:
                return _result(failure)
            first_registry = _registry(existing_private_root, owner)
            failure = _registry_failure(first_registry)
            if failure is not None:
                return _result(failure)
            first_descriptor = _descriptor(existing_workspace_root)
            failure = _descriptor_failure(first_descriptor)
            if failure is not None:
                return _result(failure)
            first_stage = _stage(existing_private_root, tx, owner)
            failure = _stage_failure(first_stage)
            if failure is not None:
                return _result(failure)
            second_stage = _stage(existing_private_root, tx, owner)
            failure = _stage_failure(second_stage)
            if failure is not None:
                return _result(failure)
            second_descriptor = _descriptor(existing_workspace_root)
            failure = _descriptor_failure(second_descriptor)
            if failure is not None:
                return _result(failure)
            second_registry = _registry(existing_private_root, owner)
            failure = _registry_failure(second_registry)
            if failure is not None:
                return _result(failure)
            second_journal = _journal(directory, tx, owner)
            failure = _journal_failure(second_journal)
            if failure is not None:
                return _result(failure)
            if (
                first_journal.image != second_journal.image
                or first_registry.image != second_registry.image
                or first_descriptor.image != second_descriptor.image
                or first_stage.image != second_stage.image
            ):
                return _result(PrivateRetainedStageCheckpointState.IMAGES_CHANGED)
            if first_stage.image != checked.registry_after:
                return _result(PrivateRetainedStageCheckpointState.STAGE_MISMATCH)
            if (
                _inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            ):
                return _result(
                    PrivateRetainedStageCheckpointState.STAGE_INVENTORY_UNQUALIFIED
                )
            if ordered._owner() != owner:
                return _result(PrivateRetainedStageCheckpointState.OWNER_CHANGED)
            classified = checkpoint.classify_private_journal_crash_checkpoint(
                checked,
                observed_journal=first_journal.image,
                observed_registry=first_registry.image,
                observed_descriptor=first_descriptor.image,
            ).state
            if (
                classified
                is checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED
            ):
                return _result(
                    PrivateRetainedStageCheckpointState.MATCHING_BEFORE_STAGE_REVIEW_REQUIRED
                )
            if classified in {
                checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
                checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED,
                checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
            }:
                return _result(
                    PrivateRetainedStageCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED
                )
            return _result(PrivateRetainedStageCheckpointState.CHECKPOINT_REFUSED)
    except retained.RetainedDescriptorGuardError as error:
        return _result(_guard_failure(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateRetainedStageCheckpointState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE)
        return _result(PrivateRetainedStageCheckpointState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRetainedStageCheckpointState.IO_ERROR)
