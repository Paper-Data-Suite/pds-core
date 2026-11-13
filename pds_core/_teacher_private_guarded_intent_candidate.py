"""Guarded creation of one private journal *candidate* (#238 Slice 3E9).

This explicitly invoked internal helper may create an intent file, but does not
admit a durable transaction, create a binding, write either metadata document,
recover a transaction, expose a Notes store, or return a write capability.
A candidate is left intact on any post-creation failure for recovery review.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_provision as provision
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pending_journal_review as pending
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateGuardedIntentCandidateState(str, Enum):
    CREATED_UNQUALIFIED = "created_unqualified"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    INITIALIZATION_REQUIRES_SEPARATE_PROTOCOL = (
        "initialization_requires_separate_protocol"
    )
    OWNER_CHANGED = "owner_changed"
    OWNER_UNAVAILABLE = "owner_unavailable"
    GUARD_REFUSED = "guard_refused"
    PENDING_RECOVERY_REQUIRED = "pending_recovery_required"
    JOURNAL_DIRECTORY_UNQUALIFIED = "journal_directory_unqualified"
    METADATA_UNQUALIFIED = "metadata_unqualified"
    BEFORE_IMAGE_MISMATCH = "before_image_mismatch"
    IMAGES_CHANGED = "images_changed"
    PROVISION_REFUSED = "provision_refused"
    CREATION_UNVERIFIED = "creation_unverified"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateGuardedIntentCandidateState.CREATED_UNQUALIFIED: "One intent candidate was created and observed; binding and durable admission remain unqualified.",
    PrivateGuardedIntentCandidateState.INVALID_REQUEST: "Candidate request was refused before mutation.",
    PrivateGuardedIntentCandidateState.UNSUPPORTED: "Candidate preparation is unsupported.",
    PrivateGuardedIntentCandidateState.INITIALIZATION_REQUIRES_SEPARATE_PROTOCOL: "First binding requires a distinct qualified absence protocol.",
    PrivateGuardedIntentCandidateState.OWNER_CHANGED: "Effective OS owner changed; if creation occurred, preserve the candidate for review.",
    PrivateGuardedIntentCandidateState.OWNER_UNAVAILABLE: "Effective OS owner could not be qualified.",
    PrivateGuardedIntentCandidateState.GUARD_REFUSED: "Native retained guards refused; if creation occurred, preserve the candidate for review.",
    PrivateGuardedIntentCandidateState.PENDING_RECOVERY_REQUIRED: "Existing pending journal entries require recovery review.",
    PrivateGuardedIntentCandidateState.JOURNAL_DIRECTORY_UNQUALIFIED: "Journal directory census was unqualified.",
    PrivateGuardedIntentCandidateState.METADATA_UNQUALIFIED: "One or more protected metadata observations were unqualified.",
    PrivateGuardedIntentCandidateState.BEFORE_IMAGE_MISMATCH: "Current native metadata does not exactly match the proposed before-images.",
    PrivateGuardedIntentCandidateState.IMAGES_CHANGED: "Native metadata changed within the protected review.",
    PrivateGuardedIntentCandidateState.PROVISION_REFUSED: "Intent candidate creation was refused or collided; preserve existing journal entries.",
    PrivateGuardedIntentCandidateState.CREATION_UNVERIFIED: "Intent candidate may exist; preserve all journal entries for explicit recovery review.",
    PrivateGuardedIntentCandidateState.IO_ERROR: "Candidate preparation failed safely; inspect pending entries before any retry.",
}


@dataclass(frozen=True, slots=True)
class PrivateGuardedIntentCandidateReview:
    """Sanitized result, never a transaction token or Notes write capability."""

    state: PrivateGuardedIntentCandidateState
    message: str


def _result(
    state: PrivateGuardedIntentCandidateState,
) -> PrivateGuardedIntentCandidateReview:
    return PrivateGuardedIntentCandidateReview(state, _MESSAGES[state])


def _census(
    directory: Path, owner: inspection.EffectiveOSOwner
) -> pending.PrivatePendingJournalState:
    """Internal census only: locks are already held by the outer guard."""
    if sys.platform == "linux":
        return pending._scan_linux(directory, owner)
    return pending._scan_windows(directory, owner)


def _registry(
    root: Path, owner: inspection.EffectiveOSOwner
) -> registry_image.PrivateRegistryImageReview:
    if sys.platform == "linux":
        return registry_image._read_linux(root, owner)
    return registry_image._read_windows(root, owner)


def _descriptor(root: Path) -> descriptor_image.PrivateDescriptorImageReview:
    if sys.platform == "linux":
        return descriptor_image._read_linux(root)
    return descriptor_image._read_windows(root)


def _journal(
    directory: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> journal.PrivateJournalImageReview:
    if sys.platform == "linux":
        return journal._read_linux(directory, transaction_id, owner)
    return journal._read_windows(directory, transaction_id, owner)


def _guard_failure(
    code: retained.RetainedDescriptorGuardCode,
) -> PrivateGuardedIntentCandidateState:
    if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
        return PrivateGuardedIntentCandidateState.OWNER_CHANGED
    if code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE:
        return PrivateGuardedIntentCandidateState.OWNER_UNAVAILABLE
    if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
        return PrivateGuardedIntentCandidateState.UNSUPPORTED
    return PrivateGuardedIntentCandidateState.GUARD_REFUSED


def _census_failure(
    state: pending.PrivatePendingJournalState,
) -> PrivateGuardedIntentCandidateState | None:
    if state is pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED:
        return None
    if state is pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED:
        return PrivateGuardedIntentCandidateState.PENDING_RECOVERY_REQUIRED
    if state is pending.PrivatePendingJournalState.OWNER_CHANGED:
        return PrivateGuardedIntentCandidateState.OWNER_CHANGED
    if state is pending.PrivatePendingJournalState.OWNER_UNAVAILABLE:
        return PrivateGuardedIntentCandidateState.OWNER_UNAVAILABLE
    return PrivateGuardedIntentCandidateState.JOURNAL_DIRECTORY_UNQUALIFIED


def create_guarded_private_intent_candidate(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateGuardedIntentCandidateReview:
    """Create at most one private journal candidate after exact native prechecks.

    Requires existing triple-retained guards, owner, empty journal census,
    exact matching canonical native before-images, unchanged rereads and a
    final empty census. Only then invokes the protected create-only primitive.
    A successful file flush is NOT sufficient proof of Windows directory-entry
    durability, cross-machine arbitration, or a transaction commit. Failed
    post-write verification NEVER deletes a candidate or retries blindly.
    No nested public reader acquires an already-held lock.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateGuardedIntentCandidateState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateGuardedIntentCandidateState.INVALID_REQUEST)
    try:
        if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(
                PrivateGuardedIntentCandidateState.INITIALIZATION_REQUIRES_SEPARATE_PROTOCOL
            )
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(PrivateGuardedIntentCandidateState.INVALID_REQUEST)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(PrivateGuardedIntentCandidateState.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivateGuardedIntentCandidateState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            directory = existing_private_root / "transactions"
            if not provision._requested_transactions_dir(directory, sys.platform):
                return _result(PrivateGuardedIntentCandidateState.INVALID_REQUEST)
            census = _census(directory, owner)
            failure = _census_failure(census)
            if failure is not None:
                return _result(failure)
            first_r = _registry(existing_private_root, owner)
            first_d = _descriptor(existing_workspace_root)
            second_d = _descriptor(existing_workspace_root)
            second_r = _registry(existing_private_root, owner)
            if (
                first_r.state
                is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
                or second_r.state
                is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
                or first_d.state
                is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
                or second_d.state
                is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
                or type(first_r.image) is not bytes
                or type(second_r.image) is not bytes
                or type(first_d.image) is not bytes
                or type(second_d.image) is not bytes
            ):
                return _result(PrivateGuardedIntentCandidateState.METADATA_UNQUALIFIED)
            if first_r.image != second_r.image or first_d.image != second_d.image:
                return _result(PrivateGuardedIntentCandidateState.IMAGES_CHANGED)
            if (
                first_r.image != checked.registry_before
                or first_d.image != checked.descriptor_before
            ):
                return _result(PrivateGuardedIntentCandidateState.BEFORE_IMAGE_MISMATCH)
            if ordered._owner() != owner:
                return _result(PrivateGuardedIntentCandidateState.OWNER_CHANGED)
            failure = _census_failure(_census(directory, owner))
            if failure is not None:
                return _result(failure)
            created = provision.create_private_transaction_intent_file(
                directory, canonical
            )
            if (
                created.state
                is not provision.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
            ):
                if (
                    created.state
                    is provision.PrivateJournalProvisionState.CREATION_UNVERIFIED
                ):
                    return _result(
                        PrivateGuardedIntentCandidateState.CREATION_UNVERIFIED
                    )
                return _result(PrivateGuardedIntentCandidateState.PROVISION_REFUSED)
            for _ in range(2):
                observed = _journal(directory, checked.witness.transaction_id, owner)
                if (
                    observed.state
                    is not journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
                    or observed.image != canonical
                ):
                    return _result(
                        PrivateGuardedIntentCandidateState.CREATION_UNVERIFIED
                    )
            if ordered._owner() != owner:
                return _result(PrivateGuardedIntentCandidateState.OWNER_CHANGED)
            return _result(PrivateGuardedIntentCandidateState.CREATED_UNQUALIFIED)
    except retained.RetainedDescriptorGuardError as error:
        return _result(_guard_failure(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateGuardedIntentCandidateState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateGuardedIntentCandidateState.OWNER_UNAVAILABLE)
        return _result(PrivateGuardedIntentCandidateState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateGuardedIntentCandidateState.IO_ERROR)
