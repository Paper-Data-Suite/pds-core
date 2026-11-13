"""Read-only native recovery identity bridge (Core #238 Slice 3G21).

Two independent path/open-handle identity censuses and exact image observations
run INSIDE one existing retained descriptor/journal/registry guard. The existing
readers and guard own native ACL, filesystem, owner and handle qualification.
This supplementary path identity evidence is advisory: not a writer, file-ID
reservation, CAS, durable commit, journal retirement or Notes authorization.
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypeAlias

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateNativeIdentityBridgeState(str, Enum):
    PREPARED_IDENTITY_REVIEW_REQUIRED = "prepared_identity_review_required"
    DESCRIPTOR_PENDING_IDENTITY_REVIEW_REQUIRED = (
        "descriptor_pending_identity_review_required"
    )
    JOURNAL_PENDING_IDENTITY_REVIEW_REQUIRED = (
        "journal_pending_identity_review_required"
    )
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    ACTION_MISMATCH_REFUSED = "action_mismatch_refused"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    IMAGE_DRIFT_PRESERVE = "image_drift_preserve"
    IDENTITY_UNQUALIFIED = "identity_unqualified"
    IDENTITY_DRIFT_PRESERVE = "identity_drift_preserve"
    NAMESPACE_CHANGED_PRESERVE = "namespace_changed_preserve"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INITIALIZATION_REFUSED = "initialization_refused"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateNativeIdentityBridgeState.PREPARED_IDENTITY_REVIEW_REQUIRED: "Native staged before-images and path identities remained stable under one guard; review only.",
    PrivateNativeIdentityBridgeState.DESCRIPTOR_PENDING_IDENTITY_REVIEW_REQUIRED: "Native registry after-image and descriptor before-image identities remained stable; review only.",
    PrivateNativeIdentityBridgeState.JOURNAL_PENDING_IDENTITY_REVIEW_REQUIRED: "Native metadata after-images and pending journal identities remained stable; retirement unqualified.",
    PrivateNativeIdentityBridgeState.REVISION_MISMATCH_REFUSED: "Registry revision differs from the canonical proposed checkpoint.",
    PrivateNativeIdentityBridgeState.ACTION_MISMATCH_REFUSED: "Recovery step does not match the stage-presence checkpoint.",
    PrivateNativeIdentityBridgeState.CHECKPOINT_CONFLICT_PRESERVE: "Native recovery checkpoint conflicts with the proposed step.",
    PrivateNativeIdentityBridgeState.IMAGE_CONFLICT_PRESERVE: "Exact native bytes or protected image sizes do not match the proposal.",
    PrivateNativeIdentityBridgeState.IMAGE_DRIFT_PRESERVE: "Native byte images changed within the retained guard.",
    PrivateNativeIdentityBridgeState.IDENTITY_UNQUALIFIED: "A path/open-handle native identity or file type was unqualified.",
    PrivateNativeIdentityBridgeState.IDENTITY_DRIFT_PRESERVE: "Path/open-handle file identity changed within the retained guard.",
    PrivateNativeIdentityBridgeState.NAMESPACE_CHANGED_PRESERVE: "Native pending journal/stage namespace changed or was unqualified.",
    PrivateNativeIdentityBridgeState.OWNER_CHANGED: "Effective native OS owner changed during review.",
    PrivateNativeIdentityBridgeState.GUARD_REFUSED: "Native retained guard refused the identity review.",
    PrivateNativeIdentityBridgeState.INTERRUPTED_PRESERVE: "Native identity review was interrupted; preserve recovery evidence.",
    PrivateNativeIdentityBridgeState.INITIALIZATION_REFUSED: "Initial binding requires a separately qualified absence protocol.",
    PrivateNativeIdentityBridgeState.INVALID_REQUEST: "Invalid native recovery identity review request.",
    PrivateNativeIdentityBridgeState.UNSUPPORTED: "Native identity review unsupported on this platform.",
    PrivateNativeIdentityBridgeState.IO_ERROR: "Native identity review could not finish without an I/O error.",
}


@dataclass(frozen=True, slots=True)
class PrivateNativeIdentityBridgeReview:
    """Sanitized finding, no bytes, file IDs, handles, paths or write authority."""

    state: PrivateNativeIdentityBridgeState
    message: str


def _result(
    state: PrivateNativeIdentityBridgeState,
) -> PrivateNativeIdentityBridgeReview:
    return PrivateNativeIdentityBridgeReview(state, _MESSAGES[state])


class _IdentityUnqualified(Exception):
    """Existing path or open handle failed the supplementary identity census."""


# Private internal observations. Never return these from the public review.
_Stamp: TypeAlias = tuple[int, int, int, int, int]
_Census: TypeAlias = tuple[_Stamp, _Stamp, _Stamp, _Stamp | None]


def _stamp(path: Path, limit: int) -> _Stamp:
    """Match path before/after stat to open read-only handle; never write.

    The retained native guard and canonical image readers enforce the stronger
    ACL, backing and native retained-HANDLE contracts. This census alone does
    not defeat hostile same-user writers or reparse races.
    """
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise _IdentityUnqualified
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        after = path.lstat()
    entries = (before, opened, after)
    if any(
        not stat.S_ISREG(entry.st_mode)
        or entry.st_nlink != 1
        or type(entry.st_dev) is not int
        or type(entry.st_ino) is not int
        or entry.st_ino <= 0
        or entry.st_size <= 0
        or entry.st_size > limit
        for entry in entries
    ):
        raise _IdentityUnqualified
    stamps: tuple[_Stamp, _Stamp, _Stamp] = (
        (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ),
        (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ),
        (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ),
    )
    if stamps[0][:3] != stamps[1][:3] or stamps[0] != stamps[2]:
        raise _IdentityUnqualified
    return stamps[0]


def _census(
    root: Path, workspace: Path, tx: str, stage: bool, journal_limit: int
) -> _Census:
    """Read-only census of exact existing canonical names under caller's guard."""
    registry = _stamp(root / "registry.json", metadata.MAX_REGISTRY_BYTES)
    descriptor_stamp = _stamp(
        workspace / ".pds" / "teacher-private-association.json",
        metadata.MAX_ASSOCIATION_BYTES,
    )
    journal_stamp = _stamp(root / "transactions" / (tx + ".json"), journal_limit)
    stage_stamp = (
        _stamp(root / ("." + tx + ".registry-stage"), metadata.MAX_REGISTRY_BYTES)
        if stage
        else None
    )
    present = (journal_stamp, registry, descriptor_stamp)
    if len({(part[0], part[1]) for part in present}) != 3:
        raise _IdentityUnqualified
    if stage_stamp is not None and (stage_stamp[0], stage_stamp[1]) in {
        (part[0], part[1]) for part in present
    }:
        raise _IdentityUnqualified
    return journal_stamp, registry, descriptor_stamp, stage_stamp


_SUCCESS = {
    actions.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART: PrivateNativeIdentityBridgeState.PREPARED_IDENTITY_REVIEW_REQUIRED,
    actions.PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION: PrivateNativeIdentityBridgeState.DESCRIPTOR_PENDING_IDENTITY_REVIEW_REQUIRED,
    actions.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT: PrivateNativeIdentityBridgeState.JOURNAL_PENDING_IDENTITY_REVIEW_REQUIRED,
}


def review_native_private_recovery_identity_bridge(
    requested_step: actions.PrivateRecoveryProposedStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateNativeIdentityBridgeReview:
    """Qualify supplementary path IDs with canonical native images, READ ONLY.

    The existing retained guard protects journal/registry/descriptor anchors.
    Two censuses + native image/checkpoint classifications execute within ONE
    retained scope, without callbacks, writes or nested lock acquisitions.
    Even a positive result is not an action token or proof of persistence.
    """
    state = PrivateNativeIdentityBridgeState
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if (
        type(requested_step) is not actions.PrivateRecoveryProposedStep
        or type(expected_revision) is not int
        or expected_revision < 1
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
        ):
            return _result(state.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.descriptor_after) is not bytes
            or type(checked.witness.transaction_id) is not str
        ):
            return _result(state.INVALID_REQUEST)
        prior = metadata.decode_private_registry(checked.registry_before)
        later = metadata.decode_private_registry(checked.registry_after)
        if (
            prior.revision != checked.witness.registry_revision_before
            or later.revision != checked.witness.registry_revision_after
            or later.revision != prior.revision + 1
            or metadata.encode_private_registry(prior) != checked.registry_before
            or metadata.encode_private_registry(later) != checked.registry_after
        ):
            return _result(state.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)
    expects_stage, expected_checkpoint, _ = operation._EXPECTED[requested_step]
    required_revision = prior.revision if expects_stage else later.revision
    if expected_revision != required_revision:
        return _result(state.REVISION_MISMATCH_REFUSED)
    expected_bytes: tuple[bytes, bytes, bytes, bytes | None] = (
        encoded,
        checked.registry_before if expects_stage else checked.registry_after,
        checked.descriptor_after
        if requested_step
        is actions.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT
        else checked.descriptor_before,
        checked.registry_after if expects_stage else None,
    )
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
            first: tuple[_Census, tuple[bytes, bytes, bytes, bytes | None]] | None = (
                None
            )
            answer = _SUCCESS[requested_step]
            for _ in range(2):
                if not operation._same_native_namespace(
                    existing_private_root,
                    checked.witness.transaction_id,
                    owner,
                    namespace,
                    expected_inventory,
                ):
                    answer = state.NAMESPACE_CHANGED_PRESERVE
                    break
                if ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
                    break
                stamps = _census(
                    existing_private_root,
                    existing_workspace_root,
                    checked.witness.transaction_id,
                    namespace[2],
                    len(encoded),
                )
                checkpoint = (
                    recovery._classify_present(
                        checked, existing_private_root, existing_workspace_root, owner
                    )
                    if namespace[2]
                    else recovery._classify_absent(
                        checked, existing_private_root, existing_workspace_root, owner
                    )
                )
                image = exact._images(
                    existing_private_root,
                    existing_workspace_root,
                    checked.witness.transaction_id,
                    owner,
                    namespace[2],
                )
                if not operation._same_native_namespace(
                    existing_private_root,
                    checked.witness.transaction_id,
                    owner,
                    namespace,
                    expected_inventory,
                ):
                    answer = state.NAMESPACE_CHANGED_PRESERVE
                    break
                if ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
                    break
                if (
                    type(checkpoint) is not recovery.PrivatePostcrashReconciliationState
                    or type(image) is not tuple
                    or len(image) != 4
                    or any(type(part) is not bytes for part in image[:3])
                    or (image[3] is not None and type(image[3]) is not bytes)
                ):
                    answer = state.IMAGE_CONFLICT_PRESERVE
                    break
                image = (image[0], image[1], image[2], image[3])
                observation = (stamps, image)
                if first is None:
                    first = observation
                elif first[0] != stamps:
                    answer = state.IDENTITY_DRIFT_PRESERVE
                    break
                elif first[1] != image:
                    answer = state.IMAGE_DRIFT_PRESERVE
                    break
                if checkpoint is not expected_checkpoint:
                    answer = state.CHECKPOINT_CONFLICT_PRESERVE
                    break
                if namespace[2] != expects_stage:
                    answer = state.ACTION_MISMATCH_REFUSED
                    break
                if image != expected_bytes:
                    answer = state.IMAGE_CONFLICT_PRESERVE
                    break
                if (
                    (
                        stamps[0][2] != len(image[0])
                        or stamps[1][2] != len(image[1])
                        or stamps[2][2] != len(image[2])
                    )
                    or (
                        expects_stage
                        and (
                            stamps[3] is None
                            or stamps[3][2] != len(checked.registry_after)
                        )
                    )
                    or (not expects_stage and stamps[3] is not None)
                ):
                    answer = state.IDENTITY_UNQUALIFIED
                    break
            if answer in _SUCCESS.values():
                if not operation._same_native_namespace(
                    existing_private_root,
                    checked.witness.transaction_id,
                    owner,
                    namespace,
                    expected_inventory,
                ):
                    answer = state.NAMESPACE_CHANGED_PRESERVE
                elif ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
        return _result(answer)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except _IdentityUnqualified:
        return _result(state.IDENTITY_UNQUALIFIED)
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
