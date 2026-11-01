"""Review one prepared journal/stage pair's *exclusive* native namespace.

Core #238 Slice 3G2. This is a non-authorizing checkpoint, not transaction
admission, durability, CAS, automatic recovery, Notes storage, or cleanup.
The underlying 3F5 checkpoint reader owns byte-image verification; this scope
adds exact transaction/stage namespace census under the SAME retained locks.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_crash_checkpoint as checkpoint
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as stage_review
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateExclusivePairCheckpointState(str, Enum):
    MATCHING_BEFORE_REVIEW_REQUIRED = "matching_before_review_required"
    OTHER_CHECKPOINT_REVIEW_REQUIRED = "other_checkpoint_review_required"
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
    PrivateExclusivePairCheckpointState.MATCHING_BEFORE_REVIEW_REQUIRED: "One matching journal and stage were observed with before-state metadata; recovery and durability review still required.",
    PrivateExclusivePairCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED: "An exclusive journal and stage were observed at another metadata checkpoint; recovery review required.",
    PrivateExclusivePairCheckpointState.INVALID_REQUEST: "Private pair checkpoint request invalid.",
    PrivateExclusivePairCheckpointState.INITIALIZATION_REFUSED: "First-time binding requires an independent absence protocol.",
    PrivateExclusivePairCheckpointState.UNSUPPORTED: "Native exclusive pair checkpoint is unsupported.",
    PrivateExclusivePairCheckpointState.NAMESPACE_UNQUALIFIED: "Pending transaction entries or registry stages are missing, competing or changed.",
    PrivateExclusivePairCheckpointState.NATIVE_IMAGE_UNQUALIFIED: "One or more protected native images could not be verified.",
    PrivateExclusivePairCheckpointState.CHECKPOINT_REFUSED: "Prepared pair does not reconcile with exact proposed metadata.",
    PrivateExclusivePairCheckpointState.OWNER_CHANGED: "Effective local OS owner changed during pair review.",
    PrivateExclusivePairCheckpointState.GUARD_REFUSED: "Retained native guard refused the pair review.",
    PrivateExclusivePairCheckpointState.IO_ERROR: "Private pair checkpoint read could not finish.",
}


@dataclass(frozen=True, slots=True)
class PrivateExclusivePairCheckpointReview:
    """Bounded advisory status, never a write token or private data carrier."""

    state: PrivateExclusivePairCheckpointState
    message: str


def _result(
    state: PrivateExclusivePairCheckpointState,
) -> PrivateExclusivePairCheckpointReview:
    return PrivateExclusivePairCheckpointReview(state, _MESSAGES[state])


class _NamespaceChanged(RuntimeError):
    """Internal marker for nonmatching or inconsistent directory enumerations."""


def _names(path: Path) -> frozenset[str]:
    with os.scandir(path) as entries:
        before = frozenset(entry.name for entry in entries)
    with os.scandir(path) as entries:
        after = frozenset(entry.name for entry in entries)
    if before != after:
        raise _NamespaceChanged
    return before


def _census(
    private_root: Path, transaction_id: str
) -> tuple[frozenset[str], frozenset[str]]:
    """Include all directory names; require precisely one transaction and stage.

    The native retained descriptor guard protects parent-file identities; two
    observations are not exclusive from hostile same-user writers. This check
    only establishes a conservative lock-honoring local observation.
    """
    pending = _names(private_root / "transactions")
    root = _names(private_root)
    stage_name = "." + transaction_id + ".registry-stage"
    if pending != frozenset({transaction_id + ".json"}):
        raise _NamespaceChanged
    stage_names = frozenset(
        name for name in root if "registry-stage" in name.casefold()
    )
    if stage_names != frozenset({stage_name}):
        raise _NamespaceChanged
    return pending, root


def _review_images(
    proposed: intents.PrivateTransactionIntent,
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
) -> PrivateExclusivePairCheckpointState:
    """Symmetric native image review; call only inside an existing retained scope."""
    tx = proposed.witness.transaction_id
    directory = private_root / "transactions"
    if (
        stage_review._inventory(private_root, owner)
        is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
    ):
        return PrivateExclusivePairCheckpointState.NAMESPACE_UNQUALIFIED
    j1 = stage_review._journal(directory, tx, owner)
    r1 = stage_review._registry(private_root, owner)
    d1 = stage_review._descriptor(workspace_root)
    s1 = stage_review._stage(private_root, tx, owner)
    s2 = stage_review._stage(private_root, tx, owner)
    d2 = stage_review._descriptor(workspace_root)
    r2 = stage_review._registry(private_root, owner)
    j2 = stage_review._journal(directory, tx, owner)
    if (
        stage_review._journal_failure(j1) is not None
        or stage_review._journal_failure(j2) is not None
        or stage_review._registry_failure(r1) is not None
        or stage_review._registry_failure(r2) is not None
        or stage_review._descriptor_failure(d1) is not None
        or stage_review._descriptor_failure(d2) is not None
        or stage_review._stage_failure(s1) is not None
        or stage_review._stage_failure(s2) is not None
        or j1.image != j2.image
        or r1.image != r2.image
        or d1.image != d2.image
        or s1.image != s2.image
    ):
        return PrivateExclusivePairCheckpointState.NATIVE_IMAGE_UNQUALIFIED
    if j1.image != intents.encode_private_transaction_intent(proposed):
        return PrivateExclusivePairCheckpointState.CHECKPOINT_REFUSED
    if s1.image != proposed.registry_after:
        return PrivateExclusivePairCheckpointState.CHECKPOINT_REFUSED
    if (
        stage_review._inventory(private_root, owner)
        is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
    ):
        return PrivateExclusivePairCheckpointState.NAMESPACE_UNQUALIFIED
    if ordered._owner() != owner:
        return PrivateExclusivePairCheckpointState.OWNER_CHANGED
    classified = checkpoint.classify_private_journal_crash_checkpoint(
        proposed,
        observed_journal=j1.image,
        observed_registry=r1.image,
        observed_descriptor=d1.image,
    ).state
    if (
        classified
        is checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED
    ):
        return PrivateExclusivePairCheckpointState.MATCHING_BEFORE_REVIEW_REQUIRED
    if classified in {
        checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
        checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED,
        checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
    }:
        return PrivateExclusivePairCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED
    return PrivateExclusivePairCheckpointState.CHECKPOINT_REFUSED


def review_exclusive_prepared_private_pair(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateExclusivePairCheckpointReview:
    """Inspect one prepared pair without writing, committing or deleting anything.

    Requires a qualified owner, unchanged retained journal/registry/descriptor
    anchors, one journal entry, one matching stage, exact canonical bytes and
    independently reconciled before/after checkpoint. A successful review is
    not durable journal admission, CAS authority or a reservation to commit.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateExclusivePairCheckpointState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateExclusivePairCheckpointState.INVALID_REQUEST)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(PrivateExclusivePairCheckpointState.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(PrivateExclusivePairCheckpointState.INITIALIZATION_REFUSED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.witness.transaction_id) is not str
        ):
            return _result(PrivateExclusivePairCheckpointState.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivateExclusivePairCheckpointState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            namespace_before = _census(
                existing_private_root, checked.witness.transaction_id
            )
            status = _review_images(
                checked, existing_private_root, existing_workspace_root, owner
            )
            if (
                _census(existing_private_root, checked.witness.transaction_id)
                != namespace_before
            ):
                return _result(
                    PrivateExclusivePairCheckpointState.NAMESPACE_UNQUALIFIED
                )
            if ordered._owner() != owner:
                return _result(PrivateExclusivePairCheckpointState.OWNER_CHANGED)
            return _result(status)
    except _NamespaceChanged:
        return _result(PrivateExclusivePairCheckpointState.NAMESPACE_UNQUALIFIED)
    except retained.RetainedDescriptorGuardError as error:
        if error.code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
            return _result(PrivateExclusivePairCheckpointState.OWNER_CHANGED)
        if error.code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
            return _result(PrivateExclusivePairCheckpointState.UNSUPPORTED)
        return _result(PrivateExclusivePairCheckpointState.GUARD_REFUSED)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateExclusivePairCheckpointState.OWNER_CHANGED)
        return _result(PrivateExclusivePairCheckpointState.GUARD_REFUSED)
    except FileNotFoundError:
        return _result(PrivateExclusivePairCheckpointState.NAMESPACE_UNQUALIFIED)
    except PermissionError:
        return _result(PrivateExclusivePairCheckpointState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateExclusivePairCheckpointState.IO_ERROR)
