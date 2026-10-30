"""Exact native three-image checkpoint review within triple retained guards (#238 3E8).

All images are obtained by internal native readers while the enclosing retained
journal/registry/descriptor context and ordered locks remain held. This is
advisory crash triage, not a journal-durability witness, admission, CAS,
repair, binding commit, or Notes capability. No mutation occurs here.
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
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateNativeRecoveryReviewState(str, Enum):
    JOURNALED_BEFORE_REVIEW_REQUIRED = "journaled_before_review_required"
    JOURNALED_DESCRIPTOR_ONLY_REVIEW_REQUIRED = (
        "journaled_descriptor_only_review_required"
    )
    JOURNALED_REGISTRY_ONLY_REVIEW_REQUIRED = "journaled_registry_only_review_required"
    JOURNALED_AFTER_REVIEW_REQUIRED = "journaled_after_review_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    INITIALIZATION_REVIEW_REQUIRED = "initialization_review_required"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    JOURNAL_MISSING = "journal_missing"
    JOURNAL_UNQUALIFIED = "journal_unqualified"
    REGISTRY_UNQUALIFIED = "registry_unqualified"
    DESCRIPTOR_UNQUALIFIED = "descriptor_unqualified"
    IMAGES_CHANGED = "images_changed"
    CHECKPOINT_REFUSED = "checkpoint_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateNativeRecoveryReviewState.JOURNALED_BEFORE_REVIEW_REQUIRED: "Journal and native metadata before-images agree; independent recovery review required.",
    PrivateNativeRecoveryReviewState.JOURNALED_DESCRIPTOR_ONLY_REVIEW_REQUIRED: "Journal and descriptor-only native after-image agree; independent recovery review required.",
    PrivateNativeRecoveryReviewState.JOURNALED_REGISTRY_ONLY_REVIEW_REQUIRED: "Journal and registry-only native after-image agree; independent recovery review required.",
    PrivateNativeRecoveryReviewState.JOURNALED_AFTER_REVIEW_REQUIRED: "Journal and both native after-images agree; independent completion review required.",
    PrivateNativeRecoveryReviewState.INVALID_REQUEST: "Native recovery review request refused.",
    PrivateNativeRecoveryReviewState.UNSUPPORTED: "Native recovery review unsupported.",
    PrivateNativeRecoveryReviewState.INITIALIZATION_REVIEW_REQUIRED: "Initialization requires a separate guarded absence protocol.",
    PrivateNativeRecoveryReviewState.OWNER_UNAVAILABLE: "Native owner could not be verified.",
    PrivateNativeRecoveryReviewState.OWNER_CHANGED: "Native owner changed during observation.",
    PrivateNativeRecoveryReviewState.GUARD_REFUSED: "Required retained native guards refused or changed.",
    PrivateNativeRecoveryReviewState.JOURNAL_MISSING: "Named journal was not observed; no recovery authorized.",
    PrivateNativeRecoveryReviewState.JOURNAL_UNQUALIFIED: "Named journal failed native qualification.",
    PrivateNativeRecoveryReviewState.REGISTRY_UNQUALIFIED: "Registry native byte observation unqualified.",
    PrivateNativeRecoveryReviewState.DESCRIPTOR_UNQUALIFIED: "Workspace descriptor native byte observation unqualified.",
    PrivateNativeRecoveryReviewState.IMAGES_CHANGED: "One or more native images changed across the guarded observations.",
    PrivateNativeRecoveryReviewState.CHECKPOINT_REFUSED: "Native images and transaction intent do not form an acceptable recovery observation.",
    PrivateNativeRecoveryReviewState.IO_ERROR: "Native recovery review could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateNativeRecoveryReview:
    """Sanitized advisory outcome: never returns private images, IDs or handles."""

    state: PrivateNativeRecoveryReviewState
    message: str


def _result(state: PrivateNativeRecoveryReviewState) -> PrivateNativeRecoveryReview:
    return PrivateNativeRecoveryReview(state, _MESSAGES[state])


def _journal(
    directory: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> journal.PrivateJournalImageReview:
    """Internal lock-free native reader; enclosing guard already owns locks."""
    if sys.platform == "linux":
        return journal._read_linux(directory, transaction_id, owner)
    return journal._read_windows(directory, transaction_id, owner)


def _registry(
    private_root: Path, owner: inspection.EffectiveOSOwner
) -> registry_image.PrivateRegistryImageReview:
    if sys.platform == "linux":
        return registry_image._read_linux(private_root, owner)
    return registry_image._read_windows(private_root, owner)


def _descriptor(workspace_root: Path) -> descriptor_image.PrivateDescriptorImageReview:
    if sys.platform == "linux":
        return descriptor_image._read_linux(workspace_root)
    return descriptor_image._read_windows(workspace_root)


def _guard_error(
    code: retained.RetainedDescriptorGuardCode,
) -> PrivateNativeRecoveryReviewState:
    if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
        return PrivateNativeRecoveryReviewState.OWNER_CHANGED
    if code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE:
        return PrivateNativeRecoveryReviewState.OWNER_UNAVAILABLE
    if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
        return PrivateNativeRecoveryReviewState.UNSUPPORTED
    return PrivateNativeRecoveryReviewState.GUARD_REFUSED


def _journal_error(
    observed: journal.PrivateJournalImageReview,
) -> PrivateNativeRecoveryReviewState | None:
    if observed.state is journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED:
        return (
            None
            if type(observed.image) is bytes
            else PrivateNativeRecoveryReviewState.JOURNAL_UNQUALIFIED
        )
    if observed.state is journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED:
        return PrivateNativeRecoveryReviewState.JOURNAL_MISSING
    if observed.state is journal.PrivateJournalImageState.OWNER_CHANGED:
        return PrivateNativeRecoveryReviewState.OWNER_CHANGED
    if observed.state is journal.PrivateJournalImageState.OWNER_UNAVAILABLE:
        return PrivateNativeRecoveryReviewState.OWNER_UNAVAILABLE
    return PrivateNativeRecoveryReviewState.JOURNAL_UNQUALIFIED


def _registry_error(
    observed: registry_image.PrivateRegistryImageReview,
) -> PrivateNativeRecoveryReviewState | None:
    if (
        observed.state
        is registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
    ):
        return (
            None
            if type(observed.image) is bytes
            else PrivateNativeRecoveryReviewState.REGISTRY_UNQUALIFIED
        )
    if observed.state is registry_image.PrivateRegistryImageState.OWNER_CHANGED:
        return PrivateNativeRecoveryReviewState.OWNER_CHANGED
    if observed.state is registry_image.PrivateRegistryImageState.OWNER_UNAVAILABLE:
        return PrivateNativeRecoveryReviewState.OWNER_UNAVAILABLE
    return PrivateNativeRecoveryReviewState.REGISTRY_UNQUALIFIED


def _descriptor_error(
    observed: descriptor_image.PrivateDescriptorImageReview,
) -> PrivateNativeRecoveryReviewState | None:
    if (
        observed.state
        is descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
    ):
        return (
            None
            if type(observed.image) is bytes
            else PrivateNativeRecoveryReviewState.DESCRIPTOR_UNQUALIFIED
        )
    if observed.state is descriptor_image.PrivateDescriptorImageState.OWNER_CHANGED:
        return PrivateNativeRecoveryReviewState.OWNER_CHANGED
    if observed.state is descriptor_image.PrivateDescriptorImageState.OWNER_UNAVAILABLE:
        return PrivateNativeRecoveryReviewState.OWNER_UNAVAILABLE
    return PrivateNativeRecoveryReviewState.DESCRIPTOR_UNQUALIFIED


_CHECKPOINT_STATES = {
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED: PrivateNativeRecoveryReviewState.JOURNALED_BEFORE_REVIEW_REQUIRED,
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED: PrivateNativeRecoveryReviewState.JOURNALED_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED: PrivateNativeRecoveryReviewState.JOURNALED_REGISTRY_ONLY_REVIEW_REQUIRED,
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED: PrivateNativeRecoveryReviewState.JOURNALED_AFTER_REVIEW_REQUIRED,
}


def review_native_private_recovery_images(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateNativeRecoveryReview:
    """Observe journal/registry/descriptor twice inside triple-retained guards.

    No caller-supplied metadata bytes and no nested public reader calls.
    Each native read checks its own backing and file/path identity; the existing
    retained context checks the anchors again on exit, overriding success.
    The read order is journal, registry, descriptor, descriptor, registry,
    journal. Equality proves only matching observed bytes, *not* file-wide
    atomicity, journal durability, distributed CAS or write permission.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateNativeRecoveryReviewState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
        or not journal._valid_id(
            getattr(getattr(proposed, "witness", None), "transaction_id", None)
        )
    ):
        return _result(PrivateNativeRecoveryReviewState.INVALID_REQUEST)
    if (
        getattr(proposed.witness, "operation", None)
        is witness.PrivateBindingOperation.INITIALIZE
    ):
        return _result(PrivateNativeRecoveryReviewState.INITIALIZATION_REVIEW_REQUIRED)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            txid = proposed.witness.transaction_id
            first_j = _journal(existing_private_root / "transactions", txid, owner)
            problem = _journal_error(first_j)
            if problem is not None:
                return _result(problem)
            first_r = _registry(existing_private_root, owner)
            problem = _registry_error(first_r)
            if problem is not None:
                return _result(problem)
            first_d = _descriptor(existing_workspace_root)
            problem = _descriptor_error(first_d)
            if problem is not None:
                return _result(problem)
            second_d = _descriptor(existing_workspace_root)
            problem = _descriptor_error(second_d)
            if problem is not None:
                return _result(problem)
            second_r = _registry(existing_private_root, owner)
            problem = _registry_error(second_r)
            if problem is not None:
                return _result(problem)
            second_j = _journal(existing_private_root / "transactions", txid, owner)
            problem = _journal_error(second_j)
            if problem is not None:
                return _result(problem)
            if ordered._owner() != owner:
                return _result(PrivateNativeRecoveryReviewState.OWNER_CHANGED)
            if (
                first_j.image != second_j.image
                or first_r.image != second_r.image
                or first_d.image != second_d.image
            ):
                return _result(PrivateNativeRecoveryReviewState.IMAGES_CHANGED)
            classified = checkpoint.classify_private_journal_crash_checkpoint(
                proposed,
                observed_journal=first_j.image,
                observed_registry=first_r.image,
                observed_descriptor=first_d.image,
            )
            return _result(
                _CHECKPOINT_STATES.get(
                    classified.state,
                    PrivateNativeRecoveryReviewState.CHECKPOINT_REFUSED,
                )
            )
    except retained.RetainedDescriptorGuardError as error:
        return _result(_guard_error(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateNativeRecoveryReviewState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateNativeRecoveryReviewState.OWNER_UNAVAILABLE)
        return _result(PrivateNativeRecoveryReviewState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateNativeRecoveryReviewState.IO_ERROR)
