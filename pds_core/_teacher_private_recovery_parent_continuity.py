"""Read-only parent-directory and recovery namespace continuity (Core #238 3G22).

Inspect existing recovery evidence in three consecutive frames under ONE retained
native descriptor/journal/registry guard. Supplement 3G21's native file-identity
census with four *parent directory* path identities. No callback, file writer,
permission token, durability assertion, journal retirement, or Notes access.
"""

from __future__ import annotations

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
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRecoveryParentContinuityState(str, Enum):
    PARENTS_STABLE_REVIEW_REQUIRED = "parents_stable_review_required"
    PARENT_IDENTITY_UNQUALIFIED = "parent_identity_unqualified"
    PARENT_DRIFT_PRESERVE = "parent_drift_preserve"
    FILE_IDENTITY_UNQUALIFIED = "file_identity_unqualified"
    FILE_IDENTITY_DRIFT_PRESERVE = "file_identity_drift_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    IMAGE_DRIFT_PRESERVE = "image_drift_preserve"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    NAMESPACE_CHANGED_PRESERVE = "namespace_changed_preserve"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    ACTION_MISMATCH_REFUSED = "action_mismatch_refused"
    INITIALIZATION_REFUSED = "initialization_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRecoveryParentContinuityState.PARENTS_STABLE_REVIEW_REQUIRED: "Existing parent paths, file identities and recovery images remained stable; no write or durability authority.",
    PrivateRecoveryParentContinuityState.PARENT_IDENTITY_UNQUALIFIED: "A protected parent directory identity or file type was unqualified.",
    PrivateRecoveryParentContinuityState.PARENT_DRIFT_PRESERVE: "Protected parent directory identity changed under one retained guard.",
    PrivateRecoveryParentContinuityState.FILE_IDENTITY_UNQUALIFIED: "Native recovery file identity census was unqualified.",
    PrivateRecoveryParentContinuityState.FILE_IDENTITY_DRIFT_PRESERVE: "Recovery file identities changed during read-only observation.",
    PrivateRecoveryParentContinuityState.IMAGE_CONFLICT_PRESERVE: "Protected recovery image is inconsistent with the proposed checkpoint.",
    PrivateRecoveryParentContinuityState.IMAGE_DRIFT_PRESERVE: "Protected recovery byte images changed during read-only observation.",
    PrivateRecoveryParentContinuityState.CHECKPOINT_CONFLICT_PRESERVE: "Native recovery checkpoint did not match the proposed step.",
    PrivateRecoveryParentContinuityState.NAMESPACE_CHANGED_PRESERVE: "Pending journal or stage namespace changed during the retained scope.",
    PrivateRecoveryParentContinuityState.OWNER_CHANGED: "Effective native owner changed within the retained scope.",
    PrivateRecoveryParentContinuityState.GUARD_REFUSED: "Native retained guard refused or changed during observation.",
    PrivateRecoveryParentContinuityState.REVISION_MISMATCH_REFUSED: "Registry revision differs from the canonical recovery checkpoint.",
    PrivateRecoveryParentContinuityState.ACTION_MISMATCH_REFUSED: "Recovery step does not match stage presence.",
    PrivateRecoveryParentContinuityState.INITIALIZATION_REFUSED: "Initialization requires a separately qualified absence protocol.",
    PrivateRecoveryParentContinuityState.INTERRUPTED_PRESERVE: "Read-only continuity review interrupted; preserve all evidence.",
    PrivateRecoveryParentContinuityState.INVALID_REQUEST: "Invalid recovery parent continuity review request.",
    PrivateRecoveryParentContinuityState.UNSUPPORTED: "Native recovery parent continuity is unsupported on this platform.",
    PrivateRecoveryParentContinuityState.IO_ERROR: "Native recovery continuity observation could not finish safely.",
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryParentContinuityReview:
    """Sanitized finding: no path, byte image, file ID, handle or write permit."""

    state: PrivateRecoveryParentContinuityState
    message: str


def _result(
    state: PrivateRecoveryParentContinuityState,
) -> PrivateRecoveryParentContinuityReview:
    return PrivateRecoveryParentContinuityReview(state, _MESSAGES[state])


class _ParentUnqualified(Exception):
    """A directory pathname failed its identity and type inspection."""


_DirStamp: TypeAlias = tuple[int, int, int, int, int]
_Parents: TypeAlias = tuple[_DirStamp, _DirStamp, _DirStamp, _DirStamp]
_Image: TypeAlias = tuple[bytes, bytes, bytes, bytes | None]


def _directory_stamp(path: Path) -> _DirStamp:
    """Two read-only path inspections, beneath an independently retained guard.

    Windows CRT cannot reliably open directories via ``os.open``. Stronger
    retained directory HANDLE verification is owned by 3D5/3E0 guards, not by
    this supplementary path census. This function never opens write handles.
    """
    before = path.lstat()
    after = path.lstat()
    if any(
        not stat.S_ISDIR(item.st_mode)
        or type(item.st_dev) is not int
        or type(item.st_ino) is not int
        or item.st_ino <= 0
        for item in (before, after)
    ):
        raise _ParentUnqualified
    one: _DirStamp = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    two: _DirStamp = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if one != two:
        raise _ParentUnqualified
    return one


def _parents(private: Path, workspace: Path) -> _Parents:
    """Census the four already-existing parent paths, never create them."""
    return (
        _directory_stamp(private),
        _directory_stamp(private / "transactions"),
        _directory_stamp(workspace),
        _directory_stamp(workspace / ".pds"),
    )


def review_native_private_recovery_parent_continuity(
    requested_step: actions.PrivateRecoveryProposedStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRecoveryParentContinuityReview:
    """Review parent identity and native recovery checkpoint under one guard.

    Three read-only rounds approximate observation boundaries only. No native
    operation is accepted or invoked, no guard is handed to any caller, and a
    matching result never establishes durability or permits journal retirement.
    """
    state = PrivateRecoveryParentContinuityState
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
        raw = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(state.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
        registry_before = checked.registry_before
        registry_after = checked.registry_after
        descriptor_before = checked.descriptor_before
        descriptor_after = checked.descriptor_after
        if (
            type(registry_before) is not bytes
            or type(registry_after) is not bytes
            or type(descriptor_before) is not bytes
            or type(descriptor_after) is not bytes
            or type(checked.witness.transaction_id) is not str
        ):
            return _result(state.INVALID_REQUEST)
        prior = metadata.decode_private_registry(registry_before)
        later = metadata.decode_private_registry(registry_after)
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
    if expected_revision != (prior.revision if expects_stage else later.revision):
        return _result(state.REVISION_MISMATCH_REFUSED)
    wanted: _Image = (
        raw,
        registry_before if expects_stage else registry_after,
        descriptor_after
        if requested_step
        is actions.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT
        else descriptor_before,
        registry_after if expects_stage else None,
    )
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            namespace = recovery._namespace(
                existing_private_root, checked.witness.transaction_id
            )
            stage = namespace[2]
            expected_inventory = (
                inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                if stage
                else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
            )
            first_parents: _Parents | None = None
            first_files: bridge._Census | None = None
            first_image: _Image | None = None
            answer = state.PARENTS_STABLE_REVIEW_REQUIRED
            for _ in range(3):
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
                parents = _parents(existing_private_root, existing_workspace_root)
                files = bridge._census(
                    existing_private_root,
                    existing_workspace_root,
                    checked.witness.transaction_id,
                    stage,
                    len(raw),
                )
                checkpoint = (
                    recovery._classify_present(
                        checked, existing_private_root, existing_workspace_root, owner
                    )
                    if stage
                    else recovery._classify_absent(
                        checked, existing_private_root, existing_workspace_root, owner
                    )
                )
                observed = exact._images(
                    existing_private_root,
                    existing_workspace_root,
                    checked.witness.transaction_id,
                    owner,
                    stage,
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
                    or type(observed) is not tuple
                    or len(observed) != 4
                    or any(type(value) is not bytes for value in observed[:3])
                    or (observed[3] is not None and type(observed[3]) is not bytes)
                ):
                    answer = state.IMAGE_CONFLICT_PRESERVE
                    break
                image = observed
                if first_parents is None:
                    first_parents, first_files, first_image = parents, files, image
                elif parents != first_parents:
                    answer = state.PARENT_DRIFT_PRESERVE
                    break
                elif files != first_files:
                    answer = state.FILE_IDENTITY_DRIFT_PRESERVE
                    break
                elif image != first_image:
                    answer = state.IMAGE_DRIFT_PRESERVE
                    break
                if checkpoint is not expected_checkpoint:
                    answer = state.CHECKPOINT_CONFLICT_PRESERVE
                    break
                if stage != expects_stage:
                    answer = state.ACTION_MISMATCH_REFUSED
                    break
                if image != wanted:
                    answer = state.IMAGE_CONFLICT_PRESERVE
                    break
                staged_image = image[3]
                if (
                    files[0][2] != len(image[0])
                    or files[1][2] != len(image[1])
                    or files[2][2] != len(image[2])
                    or (
                        stage
                        and (
                            files[3] is None
                            or staged_image is None
                            or files[3][2] != len(staged_image)
                        )
                    )
                    or (not stage and files[3] is not None)
                ):
                    answer = state.FILE_IDENTITY_UNQUALIFIED
                    break
            if answer is state.PARENTS_STABLE_REVIEW_REQUIRED:
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
                elif first_parents != _parents(
                    existing_private_root, existing_workspace_root
                ):
                    answer = state.PARENT_DRIFT_PRESERVE
        return _result(answer)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except _ParentUnqualified:
        return _result(state.PARENT_IDENTITY_UNQUALIFIED)
    except bridge._IdentityUnqualified:
        return _result(state.FILE_IDENTITY_UNQUALIFIED)
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
