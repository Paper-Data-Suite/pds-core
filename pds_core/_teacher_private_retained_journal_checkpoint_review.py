"""Read-only journal crash checkpoint review within triple retained guards (#238 3E5).

This advisory composition retains the ordered private locks, private journal
and registry anchors, and workspace descriptor identity while observing one
canonical named journal twice and checking the two metadata snapshots. Neither
journal read nor digest consensus proves durability or confers write authority.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_journal_crash_checkpoint as checkpoint
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_registry_snapshot as registry
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRetainedJournalCheckpointState(str, Enum):
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
    JOURNAL_CHANGED = "journal_changed"
    METADATA_UNQUALIFIED = "metadata_unqualified"
    OBSERVATIONS_CHANGED = "observations_changed"
    PROVIDED_IMAGES_UNQUALIFIED = "provided_images_unqualified"
    CHECKPOINT_REFUSED = "checkpoint_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRetainedJournalCheckpointState.JOURNALED_BEFORE_REVIEW_REQUIRED: "One journal and before-images agree within local guards; independent recovery review required.",
    PrivateRetainedJournalCheckpointState.JOURNALED_DESCRIPTOR_ONLY_REVIEW_REQUIRED: "Journal and descriptor-only after-image agree; independent partial recovery review required.",
    PrivateRetainedJournalCheckpointState.JOURNALED_REGISTRY_ONLY_REVIEW_REQUIRED: "Journal and registry-only after-image agree; independent partial recovery review required.",
    PrivateRetainedJournalCheckpointState.JOURNALED_AFTER_REVIEW_REQUIRED: "Journal and after-images agree; independent completion review required.",
    PrivateRetainedJournalCheckpointState.INVALID_REQUEST: "Retained journal checkpoint request refused.",
    PrivateRetainedJournalCheckpointState.UNSUPPORTED: "Retained journal checkpoint review unsupported.",
    PrivateRetainedJournalCheckpointState.INITIALIZATION_REVIEW_REQUIRED: "Initialization needs separate verified absence and retained write-target design.",
    PrivateRetainedJournalCheckpointState.OWNER_UNAVAILABLE: "Effective OS owner unavailable.",
    PrivateRetainedJournalCheckpointState.OWNER_CHANGED: "Effective OS owner changed during review.",
    PrivateRetainedJournalCheckpointState.GUARD_REFUSED: "Native private guard refused or changed during review.",
    PrivateRetainedJournalCheckpointState.JOURNAL_MISSING: "Named transaction journal is missing; no recovery authorized.",
    PrivateRetainedJournalCheckpointState.JOURNAL_UNQUALIFIED: "Named transaction journal failed native verification.",
    PrivateRetainedJournalCheckpointState.JOURNAL_CHANGED: "Named journal image changed across guarded observations.",
    PrivateRetainedJournalCheckpointState.METADATA_UNQUALIFIED: "Current metadata snapshots cannot be qualified.",
    PrivateRetainedJournalCheckpointState.OBSERVATIONS_CHANGED: "Metadata snapshots changed across guarded observations.",
    PrivateRetainedJournalCheckpointState.PROVIDED_IMAGES_UNQUALIFIED: "Supplied metadata images do not match the guarded native snapshots.",
    PrivateRetainedJournalCheckpointState.CHECKPOINT_REFUSED: "Crash checkpoint classifier refused observed state.",
    PrivateRetainedJournalCheckpointState.IO_ERROR: "Retained journal checkpoint review could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateRetainedJournalCheckpointReview:
    """Sanitized advisory state; no owner/path/bytes/capability returned."""

    state: PrivateRetainedJournalCheckpointState
    message: str


def _result(
    state: PrivateRetainedJournalCheckpointState,
) -> PrivateRetainedJournalCheckpointReview:
    return PrivateRetainedJournalCheckpointReview(state, _MESSAGES[state])


def _native_image(
    directory: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> journal.PrivateJournalImageReview:
    """Lock-free internal reader: outer retained guard already owns both locks."""
    if sys.platform == "linux":
        return journal._read_linux(directory, transaction_id, owner)
    return journal._read_windows(directory, transaction_id, owner)


def _journal_failure(
    result: journal.PrivateJournalImageReview,
) -> PrivateRetainedJournalCheckpointState | None:
    if result.state is journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED:
        return (
            None
            if type(result.image) is bytes
            else PrivateRetainedJournalCheckpointState.JOURNAL_UNQUALIFIED
        )
    if result.state is journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED:
        return PrivateRetainedJournalCheckpointState.JOURNAL_MISSING
    if result.state is journal.PrivateJournalImageState.OWNER_CHANGED:
        return PrivateRetainedJournalCheckpointState.OWNER_CHANGED
    if result.state is journal.PrivateJournalImageState.OWNER_UNAVAILABLE:
        return PrivateRetainedJournalCheckpointState.OWNER_UNAVAILABLE
    if result.state is journal.PrivateJournalImageState.CHANGED_DURING_READ:
        return PrivateRetainedJournalCheckpointState.JOURNAL_CHANGED
    return PrivateRetainedJournalCheckpointState.JOURNAL_UNQUALIFIED


def _guard_failure(
    code: retained.RetainedDescriptorGuardCode,
) -> PrivateRetainedJournalCheckpointState:
    if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
        return PrivateRetainedJournalCheckpointState.OWNER_CHANGED
    if code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE:
        return PrivateRetainedJournalCheckpointState.OWNER_UNAVAILABLE
    if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
        return PrivateRetainedJournalCheckpointState.UNSUPPORTED
    return PrivateRetainedJournalCheckpointState.GUARD_REFUSED


_CHECKPOINT_STATES = {
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED: PrivateRetainedJournalCheckpointState.JOURNALED_BEFORE_REVIEW_REQUIRED,
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED: PrivateRetainedJournalCheckpointState.JOURNALED_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED: PrivateRetainedJournalCheckpointState.JOURNALED_REGISTRY_ONLY_REVIEW_REQUIRED,
    checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED: PrivateRetainedJournalCheckpointState.JOURNALED_AFTER_REVIEW_REQUIRED,
}


def review_retained_private_journal_checkpoint(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
    *,
    observed_registry: bytes,
    observed_descriptor: bytes,
) -> PrivateRetainedJournalCheckpointReview:
    """Observe one journal plus metadata within all three existing native guards.

    Provided metadata bytes are *untrusted*. Their SHA-256 must match the
    independently observed native snapshots twice; that check does not upgrade
    them to a native exact-byte read or authorize a CAS. The two journal reads
    are separately verified; this scope does not retain a journal-file handle
    across them, prove flush durability, or exclude non-cooperating sync writers.
    Never call the public 3E4 journal reader here (it would reacquire locks).
    The guard's exit error overrides an otherwise successful advisory result.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRetainedJournalCheckpointState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
        or not journal._valid_id(
            getattr(getattr(proposed, "witness", None), "transaction_id", None)
        )
        or type(observed_registry) is not bytes
        or type(observed_descriptor) is not bytes
        or not (0 < len(observed_registry) <= metadata.MAX_REGISTRY_BYTES)
        or not (0 < len(observed_descriptor) <= metadata.MAX_ASSOCIATION_BYTES)
    ):
        return _result(PrivateRetainedJournalCheckpointState.INVALID_REQUEST)
    if (
        getattr(proposed.witness, "operation", None)
        is witness.PrivateBindingOperation.INITIALIZE
    ):
        return _result(
            PrivateRetainedJournalCheckpointState.INITIALIZATION_REVIEW_REQUIRED
        )
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            directory = existing_private_root / "transactions"
            first_journal = _native_image(
                directory, proposed.witness.transaction_id, first_owner
            )
            problem = _journal_failure(first_journal)
            if problem is not None:
                return _result(problem)
            first_registry = paired._registry_read(existing_private_root)
            first_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_registry = paired._registry_read(existing_private_root)
            second_journal = _native_image(
                directory, proposed.witness.transaction_id, first_owner
            )
            problem = _journal_failure(second_journal)
            if problem is not None:
                return _result(problem)
            if first_journal.image != second_journal.image:
                return _result(PrivateRetainedJournalCheckpointState.JOURNAL_CHANGED)
            if ordered._owner() != first_owner:
                return _result(PrivateRetainedJournalCheckpointState.OWNER_CHANGED)
            if (
                first_registry.state
                is not registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
                or second_registry.state
                is not registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
                or first_descriptor.state
                is not descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
                or second_descriptor.state
                is not descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
            ):
                return _result(
                    PrivateRetainedJournalCheckpointState.METADATA_UNQUALIFIED
                )
            current = paired._classify(
                first_registry, first_descriptor, second_descriptor, second_registry
            )
            if (
                current.state
                is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
            ):
                return _result(
                    PrivateRetainedJournalCheckpointState.OBSERVATIONS_CHANGED
                )
            if (
                current.registry_sha256 != hashlib.sha256(observed_registry).hexdigest()
                or current.descriptor_sha256
                != hashlib.sha256(observed_descriptor).hexdigest()
            ):
                return _result(
                    PrivateRetainedJournalCheckpointState.PROVIDED_IMAGES_UNQUALIFIED
                )
            triage = checkpoint.classify_private_journal_crash_checkpoint(
                proposed,
                observed_journal=first_journal.image,
                observed_registry=observed_registry,
                observed_descriptor=observed_descriptor,
            )
            state = _CHECKPOINT_STATES.get(triage.state)
            if state is None:
                return _result(PrivateRetainedJournalCheckpointState.CHECKPOINT_REFUSED)
            return _result(state)
    except retained.RetainedDescriptorGuardError as error:
        return _result(_guard_failure(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateRetainedJournalCheckpointState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateRetainedJournalCheckpointState.OWNER_UNAVAILABLE)
        return _result(PrivateRetainedJournalCheckpointState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRetainedJournalCheckpointState.IO_ERROR)
