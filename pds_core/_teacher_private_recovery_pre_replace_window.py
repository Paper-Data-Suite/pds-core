"""Read-only operation-owned pre-replacement boundary rehearsal (#238 3G38).

One existing retained descriptor/registry/journal guard and one held stage-file
scope surround FOUR native observations: two preflight frames, a final admission
frame and an additional post-boundary (NO-OP) frame. Exact canonical candidate
fingerprints, native parent/file continuity, registry-stage distinct identity,
owner, and namespace are rechecked without transferring guard ownership.

The modeled operation boundary is intentionally a no-op. No writer, user-supplied
callback/handle, replace, journal retirement, durable-commit proof or Notes API
is reachable. Every returned finding is stale after guard release.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import (
    _teacher_private_recovery_protected_write_intent_review as protected,
)
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_retained_stage_custody as custody
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents


class PrivatePreReplaceWindowState(str, Enum):
    NO_OP_BOUNDARY_OBSERVED_NO_WRITE = "no_op_boundary_observed_no_write"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INTENT_UNQUALIFIED = "intent_unqualified"
    DESCRIPTION_CHANGED_PRESERVE = "description_changed_preserve"
    ROOT_UNQUALIFIED = "root_unqualified"
    NATIVE_PROTECTION_REFUSED = "native_protection_refused"
    BINDING_MISMATCH = "binding_mismatch"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    STAGE_CUSTODY_REFUSED = "stage_custody_refused"
    STAGE_CHANGED_PRESERVE = "stage_changed_preserve"
    DESTINATION_CHANGED_PRESERVE = "destination_changed_preserve"
    FILE_CHANGED_PRESERVE = "file_changed_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivatePreReplaceWindowState, str] = {
    PrivatePreReplaceWindowState.NO_OP_BOUNDARY_OBSERVED_NO_WRITE: (
        "Four exact native observations straddled a no-op boundary inside one "
        "retained scope. Guard released; production mutation remains prohibited."
    ),
    PrivatePreReplaceWindowState.INVALID_REQUEST: "Invalid protected pre-replacement request.",
    PrivatePreReplaceWindowState.OPERATION_NOT_ADMITTED: "Only prepared stage-to-registry review is in scope.",
    PrivatePreReplaceWindowState.REVISION_MISMATCH_REFUSED: "Expected registry revision was refused.",
    PrivatePreReplaceWindowState.INTENT_UNQUALIFIED: "Canonical prepared transaction was unqualified.",
    PrivatePreReplaceWindowState.DESCRIPTION_CHANGED_PRESERVE: "Canonical write description changed under custody.",
    PrivatePreReplaceWindowState.ROOT_UNQUALIFIED: "Requested private or workspace root was refused.",
    PrivatePreReplaceWindowState.NATIVE_PROTECTION_REFUSED: "Native owner or private-root protection was unqualified.",
    PrivatePreReplaceWindowState.BINDING_MISMATCH: "Owner/workspace binding did not qualify.",
    PrivatePreReplaceWindowState.OWNER_CHANGED: "Effective OS principal changed while guarded.",
    PrivatePreReplaceWindowState.GUARD_REFUSED: "Retained guard could not be acquired or released.",
    PrivatePreReplaceWindowState.STAGE_CUSTODY_REFUSED: "Native stage custody could not be established.",
    PrivatePreReplaceWindowState.STAGE_CHANGED_PRESERVE: "Native stage identity or entry changed; preserve evidence.",
    PrivatePreReplaceWindowState.DESTINATION_CHANGED_PRESERVE: "Registry destination identity changed; preserve evidence.",
    PrivatePreReplaceWindowState.FILE_CHANGED_PRESERVE: "Protected journal or descriptor identity changed.",
    PrivatePreReplaceWindowState.IMAGE_CONFLICT_PRESERVE: "Protected prepared bytes or file sizes conflicted.",
    PrivatePreReplaceWindowState.NAMESPACE_CONFLICT_PRESERVE: "Transaction/stage namespace changed under guard.",
    PrivatePreReplaceWindowState.CHECKPOINT_CONFLICT_PRESERVE: "Native prepared recovery checkpoint was unqualified.",
    PrivatePreReplaceWindowState.INTERRUPTED_PRESERVE: "Pre-replacement review interrupted; preserve pending evidence.",
    PrivatePreReplaceWindowState.UNSUPPORTED: "Native protected pre-replacement review unsupported.",
    PrivatePreReplaceWindowState.IO_ERROR: "Protected pre-replacement observation was refused.",
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivatePreReplaceWindowReview:
    """Sanitized post-release result; never a write capability or custody token."""

    state: PrivatePreReplaceWindowState
    message: str
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(repr=False)
    )

    def __repr__(self) -> str:
        return "PrivatePreReplaceWindowReview(non_authorizing=True)"


def _result(state: PrivatePreReplaceWindowState) -> PrivatePreReplaceWindowReview:
    return PrivatePreReplaceWindowReview(state, _MESSAGES[state], barrier._REQUIRED)


def _description(
    step: scratch.PrivateScratchWriterStep,
    revision: int,
    item: intents.PrivateTransactionIntent,
) -> prepared.PrivatePreparedWriteDescription | None:
    """Obtain actual canonical digest data, not a caller-provided prior review."""
    result = prepared.describe_private_prepared_stage_write_intent(step, revision, item)
    if (
        type(result) is not prepared.PrivatePreparedWriteIntentReview
        or result.state
        is not prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
        or type(result.description) is not prepared.PrivatePreparedWriteDescription
    ):
        return None
    return result.description


def _file_state(
    observed: scope._Frame, baseline: scope._Frame | None
) -> PrivatePreReplaceWindowState | None:
    """Distinguish stage/destination drift without interpreting a prior review."""
    state = PrivatePreReplaceWindowState
    files = observed.file_stamps
    if (
        type(files) is not tuple
        or len(files) != 4
        or any(
            item is None or type(item) is not tuple or len(item) != 5 for item in files
        )
    ):
        return state.FILE_CHANGED_PRESERVE
    journal, registry, descriptor_stamp, stage = files
    if stage is None:
        return state.STAGE_CHANGED_PRESERVE
    if any(
        type(value) is not int or value < 0
        for stamp in (journal, registry, descriptor_stamp, stage)
        for value in stamp
    ):
        return state.FILE_CHANGED_PRESERVE
    identities = {
        (stamp[0], stamp[1]) for stamp in (journal, registry, descriptor_stamp, stage)
    }
    if len(identities) != 4 or registry[0:2] == stage[0:2]:
        return state.STAGE_CHANGED_PRESERVE
    if baseline is not None:
        old_files = baseline.file_stamps
        if type(old_files) is not tuple or len(old_files) != 4:
            return state.FILE_CHANGED_PRESERVE
        if stage != old_files[3]:
            return state.STAGE_CHANGED_PRESERVE
        if registry != old_files[1]:
            return state.DESTINATION_CHANGED_PRESERVE
        if journal != old_files[0] or descriptor_stamp != old_files[2]:
            return state.FILE_CHANGED_PRESERVE
    return None


def _frame_state(
    observed: scope._Frame,
    baseline: scope._Frame | None,
    wanted: parents._Image,
    description: prepared.PrivatePreparedWriteDescription,
    checked: intents.PrivateTransactionIntent,
) -> PrivatePreReplaceWindowState | None:
    state = PrivatePreReplaceWindowState
    if type(observed) is not scope._Frame:
        return state.CHECKPOINT_CONFLICT_PRESERVE
    file_failure = _file_state(observed, baseline)
    if file_failure is not None:
        return file_failure
    refusal = scope._frame_state(observed, baseline, wanted)
    if refusal is not None:
        if (
            refusal
            is scope.PrivateProtectedWriterScopeState.CHECKPOINT_CONFLICT_PRESERVE
        ):
            return state.CHECKPOINT_CONFLICT_PRESERVE
        if refusal is scope.PrivateProtectedWriterScopeState.PARENT_CONFLICT_PRESERVE:
            return state.DESTINATION_CHANGED_PRESERVE
        return state.IMAGE_CONFLICT_PRESERVE
    if not protected._fingerprints_match(observed, description, checked):
        return state.IMAGE_CONFLICT_PRESERVE
    return None


def review_protected_pre_replace_window(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivatePreReplaceWindowReview:
    """Four in-scope observations around a NO-OP boundary; never perform a write.

    No execution callback, prior review, readiness boolean, caller native handle,
    or writable destination is accepted. The function returns only after guards
    release, and a positive observation cannot be reused as write admission.
    """
    state = PrivatePreReplaceWindowState
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
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    if not lock_file._requested_root(
        existing_private_root, sys.platform
    ) or not descriptor._valid_root(existing_workspace_root):
        return _result(state.ROOT_UNQUALIFIED)
    try:
        candidate = barrier.review_private_production_write_barrier(
            step, expected_revision, proposed
        )
        if type(candidate) is not barrier.PrivateProductionWriteBarrierReview:
            return _result(state.INTENT_UNQUALIFIED)
        if (
            candidate.state
            is barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ):
            return _result(state.REVISION_MISMATCH_REFUSED)
        if (
            candidate.state
            is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ):
            return _result(state.INTENT_UNQUALIFIED)
        initial = _description(step, expected_revision, proposed)
        if initial is None:
            return _result(state.INTENT_UNQUALIFIED)
        raw = intents.encode_private_transaction_intent(proposed)
        if type(raw) is not bytes or len(raw) > intents.MAX_INTENT_BYTES:
            return _result(state.INTENT_UNQUALIFIED)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
            or type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        before = checked.registry_before
        after = checked.registry_after
        sidecar = checked.descriptor_before
        if (
            type(before) is not bytes
            or type(after) is not bytes
            or type(sidecar) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        tx = checked.witness.transaction_id
        early, owner = preflight._native_observation(existing_private_root)
        if early is not None or owner is None:
            return _result(state.NATIVE_PROTECTION_REFUSED)
        if (
            preflight._intent_owner_and_binding(checked, owner, existing_workspace_root)
            is not None
        ):
            return _result(state.BINDING_MISMATCH)
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            fresh = intents.decode_private_transaction_intent(raw)
            if (
                type(fresh) is not intents.PrivateTransactionIntent
                or fresh != checked
                or fresh != proposed
                or intents.encode_private_transaction_intent(fresh) != raw
            ):
                return _result(state.INTENT_UNQUALIFIED)
            inside_description = _description(step, expected_revision, fresh)
            if inside_description is None or inside_description != initial:
                return _result(state.DESCRIPTION_CHANGED_PRESERVE)
            if (
                preflight._intent_owner_and_binding(
                    fresh, owner, existing_workspace_root
                )
                is not None
            ):
                return _result(state.BINDING_MISMATCH)
            expected_namespace = recovery._namespace(existing_private_root, tx)
            if (
                type(expected_namespace) is not tuple
                or len(expected_namespace) != 3
                or expected_namespace[2] is not True
            ):
                return _result(state.NAMESPACE_CONFLICT_PRESERVE)
            wanted = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            images: parents._Image = (raw, before, sidecar, after)
            with custody._held_stage(
                existing_private_root, tx, owner, len(after)
            ) as stage_held:
                baseline: scope._Frame | None = None
                # The third frame is the simulated immediate pre-replace point.
                # The fourth checks that even a no-op boundary did not drift.
                for frame_number in range(4):
                    observed_state, current_owner = preflight._native_observation(
                        existing_private_root, owner
                    )
                    if (
                        observed_state is not None
                        or current_owner is None
                        or ordered._owner() != owner
                    ):
                        return _result(state.OWNER_CHANGED)
                    if not stage_held():
                        return _result(state.STAGE_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root, tx, owner, expected_namespace, wanted
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    if frame_number == 2:
                        boundary_description = _description(
                            step, expected_revision, fresh
                        )
                        if (
                            boundary_description is None
                            or boundary_description != initial
                        ):
                            return _result(state.DESCRIPTION_CHANGED_PRESERVE)
                    current = scope._observe(
                        existing_private_root,
                        existing_workspace_root,
                        fresh,
                        owner,
                        len(raw),
                    )
                    if not stage_held():
                        return _result(state.STAGE_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root, tx, owner, expected_namespace, wanted
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    frame_refusal = _frame_state(
                        current, baseline, images, initial, fresh
                    )
                    if frame_refusal is not None:
                        return _result(frame_refusal)
                    if baseline is None:
                        baseline = current
                final_state, final_owner = preflight._native_observation(
                    existing_private_root, owner
                )
                if (
                    final_state is not None
                    or final_owner is None
                    or ordered._owner() != owner
                ):
                    return _result(state.OWNER_CHANGED)
                if not stage_held():
                    return _result(state.STAGE_CHANGED_PRESERVE)
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, expected_namespace, wanted
                ):
                    return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                if (
                    baseline is None
                    or parents._parents(existing_private_root, existing_workspace_root)
                    != baseline.parent_stamps
                ):
                    return _result(state.DESTINATION_CHANGED_PRESERVE)
        return _result(state.NO_OP_BOUNDARY_OBSERVED_NO_WRITE)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except custody._StageChanged:
        return _result(state.STAGE_CHANGED_PRESERVE)
    except custody._StageRefused:
        return _result(state.STAGE_CUSTODY_REFUSED)
    except (
        scope._ImageUnqualified,
        parents._ParentUnqualified,
        bridge._IdentityUnqualified,
    ):
        return _result(state.IMAGE_CONFLICT_PRESERVE)
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
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        intents.PrivateIntentError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
