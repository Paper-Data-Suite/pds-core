"""Non-mutating protected writer-owned scope rehearsal (Core #238 Slice 3G30).

A single existing native descriptor/registry/journal guard is held across three
prepared-checkpoint snapshots (pre-admission, operation boundary, post-boundary).
Unlike the 3G28 handoff, review does not release and reacquire the guard between
frames. No callback or writer is accepted, and no mutating operation exists here.

The returned result is advisory *after* guard release. It is never a write permit,
native compare-and-swap, proof of durability, or journal-retirement authority.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateProtectedWriterScopeState(str, Enum):
    PREPARED_SCOPE_DRY_RUN_ONLY = "prepared_scope_dry_run_only"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    PARENT_CONFLICT_PRESERVE = "parent_conflict_preserve"
    FILE_CONFLICT_PRESERVE = "file_conflict_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateProtectedWriterScopeState.PREPARED_SCOPE_DRY_RUN_ONLY: (
        "Prepared checkpoint remained stable across three frames inside one "
        "native retained guard. No writer was invoked or authorized."
    ),
    PrivateProtectedWriterScopeState.OPERATION_NOT_ADMITTED: (
        "Only prepared stage-to-registry rebind review is covered."
    ),
    PrivateProtectedWriterScopeState.INVALID_REQUEST: "Invalid or noncanonical scope request.",
    PrivateProtectedWriterScopeState.INITIALIZATION_REFUSED: "Initialization lacks qualified native absence custody.",
    PrivateProtectedWriterScopeState.REVISION_MISMATCH_REFUSED: "Prepared registry revision disagrees with the intent.",
    PrivateProtectedWriterScopeState.CHECKPOINT_CONFLICT_PRESERVE: "Protected prepared recovery checkpoint was unqualified.",
    PrivateProtectedWriterScopeState.PARENT_CONFLICT_PRESERVE: "Parent directory identity was unsafe or changed under protection.",
    PrivateProtectedWriterScopeState.FILE_CONFLICT_PRESERVE: "Protected native file identities or lengths were unsafe or changed.",
    PrivateProtectedWriterScopeState.IMAGE_CONFLICT_PRESERVE: "Protected exact byte images were unsafe or changed.",
    PrivateProtectedWriterScopeState.NAMESPACE_CONFLICT_PRESERVE: "Protected stage or journal namespace changed.",
    PrivateProtectedWriterScopeState.OWNER_CHANGED: "Effective native owner changed during the protected scope.",
    PrivateProtectedWriterScopeState.GUARD_REFUSED: "Retained native protection was unavailable or refused release.",
    PrivateProtectedWriterScopeState.INTERRUPTED_PRESERVE: "Protected dry-run interrupted; preserve pending artifacts.",
    PrivateProtectedWriterScopeState.UNSUPPORTED: "Native protected rehearsal unsupported on this OS.",
    PrivateProtectedWriterScopeState.IO_ERROR: "Native protected dry-run encountered an I/O refusal.",
}


@dataclass(frozen=True, slots=True)
class PrivateProtectedWriterScopeReview:
    state: PrivateProtectedWriterScopeState
    message: str


def _result(
    state: PrivateProtectedWriterScopeState,
) -> PrivateProtectedWriterScopeReview:
    return PrivateProtectedWriterScopeReview(state, _MESSAGES[state])


class _ImageUnqualified(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _Frame:
    parent_stamps: parents._Parents
    file_stamps: bridge._Census
    images: parents._Image
    checkpoint: recovery.PrivatePostcrashReconciliationState


def _frame_state(
    observed: _Frame,
    baseline: _Frame | None,
    expected_images: parents._Image,
) -> PrivateProtectedWriterScopeState | None:
    """Evaluate one already protected frame; never emit a positive write token."""
    state = PrivateProtectedWriterScopeState
    if type(observed) is not _Frame:
        return state.INVALID_REQUEST
    if (
        observed.checkpoint
        is not recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED
    ):
        return state.CHECKPOINT_CONFLICT_PRESERVE
    if type(observed.images) is not tuple or len(observed.images) != 4:
        return state.IMAGE_CONFLICT_PRESERVE
    journal, registry, association, staged = observed.images
    if any(
        type(item) is not bytes for item in (journal, registry, association, staged)
    ):
        return state.IMAGE_CONFLICT_PRESERVE
    if observed.images != expected_images:
        return state.IMAGE_CONFLICT_PRESERVE
    files = observed.file_stamps
    if type(files) is not tuple or len(files) != 4:
        return state.FILE_CONFLICT_PRESERVE
    for stamp, image in zip(
        files, (journal, registry, association, staged), strict=True
    ):
        if type(image) is not bytes:
            return state.IMAGE_CONFLICT_PRESERVE
        if (
            stamp is None
            or type(stamp) is not tuple
            or len(stamp) != 5
            or stamp[2] != len(image)
        ):
            return state.FILE_CONFLICT_PRESERVE
    if type(observed.parent_stamps) is not tuple or len(observed.parent_stamps) != 4:
        return state.PARENT_CONFLICT_PRESERVE
    if baseline is not None:
        if observed.parent_stamps != baseline.parent_stamps:
            return state.PARENT_CONFLICT_PRESERVE
        if observed.file_stamps != baseline.file_stamps:
            return state.FILE_CONFLICT_PRESERVE
        if observed.images != baseline.images:
            return state.IMAGE_CONFLICT_PRESERVE
    return None


def _observe(
    private: Path,
    workspace: Path,
    checked: intents.PrivateTransactionIntent,
    owner: inspection.EffectiveOSOwner,
    journal_size: int,
) -> _Frame:
    """Only use existing *read-only* protected native inspection primitives."""
    image = exact._images(
        private, workspace, checked.witness.transaction_id, owner, True
    )
    if image is None or type(image) is not tuple or len(image) != 4:
        raise _ImageUnqualified
    return _Frame(
        parents._parents(private, workspace),
        bridge._census(
            private, workspace, checked.witness.transaction_id, True, journal_size
        ),
        image,
        recovery._classify_present(checked, private, workspace, owner),
    )


def review_protected_native_writer_scope_dry_run(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateProtectedWriterScopeReview:
    """Read-only in-scope admission rehearsal; no operation slot is exported.

    All frames occur under the SAME existing retained guard. The central frame
    models the instant where a future bounded writer would act, but this
    implementation intentionally performs another read rather than a write.
    """
    state = PrivateProtectedWriterScopeState
    if (
        type(step) is not scratch.PrivateScratchWriterStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(state.INVALID_REQUEST)
    if step is not scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if not lock_file._requested_root(
        existing_private_root, sys.platform
    ) or not descriptor._valid_root(existing_workspace_root):
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
        before = checked.registry_before
        after = checked.registry_after
        sidecar = checked.descriptor_before
        if (
            type(before) is not bytes
            or type(after) is not bytes
            or type(sidecar) is not bytes
        ):
            return _result(state.INVALID_REQUEST)
        previous = metadata.decode_private_registry(before)
        following = metadata.decode_private_registry(after)
        if (
            metadata.encode_private_registry(previous) != before
            or metadata.encode_private_registry(following) != after
            or previous.revision != checked.witness.registry_revision_before
            or following.revision != checked.witness.registry_revision_after
            or following.revision != previous.revision + 1
        ):
            return _result(state.INVALID_REQUEST)
        if expected_revision != previous.revision:
            return _result(state.REVISION_MISMATCH_REFUSED)
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        OSError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)
    expected_images: parents._Image = (raw, before, sidecar, after)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            namespace = recovery._namespace(
                existing_private_root, checked.witness.transaction_id
            )
            wanted = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            # No reentry to 3G22: it would reacquire the same nonreentrant locks.
            baseline: _Frame | None = None
            answer = state.PREPARED_SCOPE_DRY_RUN_ONLY
            for _ in range(3):
                if (
                    not operation._same_native_namespace(
                        existing_private_root,
                        checked.witness.transaction_id,
                        owner,
                        namespace,
                        wanted,
                    )
                    or not namespace[2]
                ):
                    answer = state.NAMESPACE_CONFLICT_PRESERVE
                    break
                if ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
                    break
                observation = _observe(
                    existing_private_root,
                    existing_workspace_root,
                    checked,
                    owner,
                    len(raw),
                )
                if not operation._same_native_namespace(
                    existing_private_root,
                    checked.witness.transaction_id,
                    owner,
                    namespace,
                    wanted,
                ):
                    answer = state.NAMESPACE_CONFLICT_PRESERVE
                    break
                if ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
                    break
                refusal = _frame_state(observation, baseline, expected_images)
                if refusal is not None:
                    answer = refusal
                    break
                if baseline is None:
                    baseline = observation
            if answer is state.PREPARED_SCOPE_DRY_RUN_ONLY:
                if not operation._same_native_namespace(
                    existing_private_root,
                    checked.witness.transaction_id,
                    owner,
                    namespace,
                    wanted,
                ):
                    answer = state.NAMESPACE_CONFLICT_PRESERVE
                elif ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
                elif baseline is None:
                    answer = state.CHECKPOINT_CONFLICT_PRESERVE
                elif (
                    parents._parents(existing_private_root, existing_workspace_root)
                    != baseline.parent_stamps
                ):
                    answer = state.PARENT_CONFLICT_PRESERVE
        # A failed guard release cannot return the positive advisory state.
        return _result(answer)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except _ImageUnqualified:
        return _result(state.IMAGE_CONFLICT_PRESERVE)
    except parents._ParentUnqualified:
        return _result(state.PARENT_CONFLICT_PRESERVE)
    except bridge._IdentityUnqualified:
        return _result(state.FILE_CONFLICT_PRESERVE)
    except pair._NamespaceChanged:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
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
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except PermissionError:
        return _result(state.GUARD_REFUSED)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        return _result(state.IO_ERROR)
