"""Native in-scope protected write-intent review (Core #238 Slice 3G33).

Re-derive the inert 3G32 description INSIDE the same operation-owned guard
that collects three exact native checkpoint frames. The result is intentionally
non-authorizing, emitted only after successful guard release; no private writer,
callback, handle, state-changing operation, or replay capability is exported.

An exact description is not sufficient: each frame must match the live pending
journal, preimage, descriptor, stage, native parents and file identities. A
later writer must independently establish all requirements in its own guard.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents


class PrivateProtectedWriteIntentState(str, Enum):
    PROTECTED_INTENT_REVIEW_ONLY = "protected_intent_review_only"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INITIALIZATION_REFUSED = "initialization_refused"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    NONCANONICAL_INTENT_REFUSED = "noncanonical_intent_refused"
    INTENT_DRIFT_PRESERVE = "intent_drift_preserve"
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
    PrivateProtectedWriteIntentState.PROTECTED_INTENT_REVIEW_ONLY: (
        "Canonical write description and three native frames matched inside one "
        "retained guard; guard released. No operation or authorization exists."
    ),
    PrivateProtectedWriteIntentState.INVALID_REQUEST: "Unqualified protected intent request.",
    PrivateProtectedWriteIntentState.OPERATION_NOT_ADMITTED: "Only prepared stage-to-registry review is supported.",
    PrivateProtectedWriteIntentState.INITIALIZATION_REFUSED: "First binding lacks qualified absence custody.",
    PrivateProtectedWriteIntentState.REVISION_MISMATCH_REFUSED: "Prepared expected revision is inconsistent.",
    PrivateProtectedWriteIntentState.NONCANONICAL_INTENT_REFUSED: "Canonical transaction intent was refused.",
    PrivateProtectedWriteIntentState.INTENT_DRIFT_PRESERVE: "Typed intent or fingerprints changed during protected review.",
    PrivateProtectedWriteIntentState.CHECKPOINT_CONFLICT_PRESERVE: "Prepared checkpoint is inconsistent.",
    PrivateProtectedWriteIntentState.PARENT_CONFLICT_PRESERVE: "Protected parent continuity is unqualified.",
    PrivateProtectedWriteIntentState.FILE_CONFLICT_PRESERVE: "Protected native file identity is unqualified.",
    PrivateProtectedWriteIntentState.IMAGE_CONFLICT_PRESERVE: "Protected exact byte images or digests differ.",
    PrivateProtectedWriteIntentState.NAMESPACE_CONFLICT_PRESERVE: "Protected journal or stage namespace changed.",
    PrivateProtectedWriteIntentState.OWNER_CHANGED: "Effective owner changed in protected scope.",
    PrivateProtectedWriteIntentState.GUARD_REFUSED: "Retained native guard was refused or release failed.",
    PrivateProtectedWriteIntentState.INTERRUPTED_PRESERVE: "Protected review was interrupted; preserve evidence.",
    PrivateProtectedWriteIntentState.UNSUPPORTED: "Native protected review unsupported on this OS.",
    PrivateProtectedWriteIntentState.IO_ERROR: "Protected observation could not be completed safely.",
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateProtectedWriteIntentReview:
    """Sanitized advisory outcome. No path, native handle, bytes, or permit."""

    state: PrivateProtectedWriteIntentState
    message: str

    def __repr__(self) -> str:
        return "PrivateProtectedWriteIntentReview(non_authorizing=True)"


def _result(
    state: PrivateProtectedWriteIntentState,
) -> PrivateProtectedWriteIntentReview:
    return PrivateProtectedWriteIntentReview(state, _MESSAGES[state])


_SCOPE_REFUSALS = {
    scope.PrivateProtectedWriterScopeState.INVALID_REQUEST: PrivateProtectedWriteIntentState.INVALID_REQUEST,
    scope.PrivateProtectedWriterScopeState.CHECKPOINT_CONFLICT_PRESERVE: PrivateProtectedWriteIntentState.CHECKPOINT_CONFLICT_PRESERVE,
    scope.PrivateProtectedWriterScopeState.PARENT_CONFLICT_PRESERVE: PrivateProtectedWriteIntentState.PARENT_CONFLICT_PRESERVE,
    scope.PrivateProtectedWriterScopeState.FILE_CONFLICT_PRESERVE: PrivateProtectedWriteIntentState.FILE_CONFLICT_PRESERVE,
    scope.PrivateProtectedWriterScopeState.IMAGE_CONFLICT_PRESERVE: PrivateProtectedWriteIntentState.IMAGE_CONFLICT_PRESERVE,
}


def _fingerprints_match(
    frame: scope._Frame,
    description: prepared.PrivatePreparedWriteDescription,
    checked: intents.PrivateTransactionIntent,
) -> bool:
    """Hash only already native-checked images while native custody is held."""
    if type(frame) is not scope._Frame:
        return False
    images = frame.images
    if type(images) is not tuple or len(images) != 4:
        return False
    if any(type(value) is not bytes for value in images):
        return False
    journal, registry, sidecar, stage = images
    if type(stage) is not bytes:
        return False
    return (
        hashlib.sha256(journal).hexdigest() == description.pending_intent_sha256
        and hashlib.sha256(registry).hexdigest() == description.registry_before_sha256
        and hashlib.sha256(sidecar).hexdigest() == description.descriptor_before_sha256
        and hashlib.sha256(stage).hexdigest() == description.staged_registry_sha256
        and type(checked.descriptor_after) is bytes
        and hashlib.sha256(checked.descriptor_after).hexdigest()
        == description.descriptor_after_sha256
    )


def _description_state(
    state: prepared.PrivatePreparedWriteIntentState,
) -> PrivateProtectedWriteIntentState:
    translation = {
        prepared.PrivatePreparedWriteIntentState.OPERATION_NOT_ADMITTED: PrivateProtectedWriteIntentState.OPERATION_NOT_ADMITTED,
        prepared.PrivatePreparedWriteIntentState.INITIALIZATION_REFUSED: PrivateProtectedWriteIntentState.INITIALIZATION_REFUSED,
        prepared.PrivatePreparedWriteIntentState.REVISION_MISMATCH_REFUSED: PrivateProtectedWriteIntentState.REVISION_MISMATCH_REFUSED,
        prepared.PrivatePreparedWriteIntentState.NONCANONICAL_INTENT_REFUSED: PrivateProtectedWriteIntentState.NONCANONICAL_INTENT_REFUSED,
        prepared.PrivatePreparedWriteIntentState.INVALID_REQUEST: PrivateProtectedWriteIntentState.INVALID_REQUEST,
        prepared.PrivatePreparedWriteIntentState.IO_ERROR: PrivateProtectedWriteIntentState.IO_ERROR,
    }
    return translation.get(
        state, PrivateProtectedWriteIntentState.NONCANONICAL_INTENT_REFUSED
    )


def review_protected_native_prepared_write_intent(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateProtectedWriteIntentReview:
    """Read-only, exact protected review; returned finding never permits a write.

    No description, previous review, path from a description, callback, handle,
    guard, or writer is accepted as authority. One guard covers all redecoding,
    three observations, fingerprints, owner/namespace and final parent check.
    """
    state = PrivateProtectedWriteIntentState
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
    # Early pure refusal is an optimization, not native admission. Revalidation
    # repeats under retained custody even when the first description matches.
    first = prepared.describe_private_prepared_stage_write_intent(
        step, expected_revision, proposed
    )
    if (
        first.state
        is not prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
        or type(first.description) is not prepared.PrivatePreparedWriteDescription
    ):
        return _result(_description_state(first.state))
    initial = first.description
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            second = prepared.describe_private_prepared_stage_write_intent(
                step, expected_revision, proposed
            )
            if (
                second.state
                is not prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
                or type(second.description)
                is not prepared.PrivatePreparedWriteDescription
                or second.description != initial
            ):
                return _result(state.INTENT_DRIFT_PRESERVE)
            raw = intents.encode_private_transaction_intent(proposed)
            if type(raw) is not bytes or len(raw) > intents.MAX_INTENT_BYTES:
                return _result(state.INTENT_DRIFT_PRESERVE)
            checked = intents.decode_private_transaction_intent(raw)
            if (
                type(checked) is not intents.PrivateTransactionIntent
                or checked != proposed
                or intents.encode_private_transaction_intent(checked) != raw
                or hashlib.sha256(raw).hexdigest()
                != second.description.pending_intent_sha256
            ):
                return _result(state.INTENT_DRIFT_PRESERVE)
            before = checked.registry_before
            sidecar = checked.descriptor_before
            after = checked.registry_after
            if (
                type(before) is not bytes
                or type(sidecar) is not bytes
                or type(after) is not bytes
            ):
                return _result(state.INTENT_DRIFT_PRESERVE)
            expected_images: parents._Image = (raw, before, sidecar, after)
            tx = checked.witness.transaction_id
            namespace = recovery._namespace(existing_private_root, tx)
            wanted = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            if (
                type(namespace) is not tuple
                or len(namespace) != 3
                or namespace[2] is not True
            ):
                return _result(state.NAMESPACE_CONFLICT_PRESERVE)
            baseline: scope._Frame | None = None
            answer = state.PROTECTED_INTENT_REVIEW_ONLY
            for _ in range(3):
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, namespace, wanted
                ):
                    answer = state.NAMESPACE_CONFLICT_PRESERVE
                    break
                if ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
                    break
                frame = scope._observe(
                    existing_private_root,
                    existing_workspace_root,
                    checked,
                    owner,
                    len(raw),
                )
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, namespace, wanted
                ):
                    answer = state.NAMESPACE_CONFLICT_PRESERVE
                    break
                if ordered._owner() != owner:
                    answer = state.OWNER_CHANGED
                    break
                refusal = scope._frame_state(
                    frame,
                    baseline,
                    expected_images,
                )
                if refusal is not None:
                    answer = _SCOPE_REFUSALS.get(
                        refusal, state.CHECKPOINT_CONFLICT_PRESERVE
                    )
                    break
                if not _fingerprints_match(frame, second.description, checked):
                    answer = state.IMAGE_CONFLICT_PRESERVE
                    break
                if baseline is None:
                    baseline = frame
            if answer is state.PROTECTED_INTENT_REVIEW_ONLY:
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, namespace, wanted
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
        # Only successful __exit__ can deliver the positive advisory status.
        return _result(answer)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except scope._ImageUnqualified:
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
    except (
        OSError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
        intents.PrivateIntentError,
    ):
        return _result(state.IO_ERROR)
