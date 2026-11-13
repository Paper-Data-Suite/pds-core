"""Read-only, guarded production-prerequisite observation (Core #238 3G36).

Recheck the effective process owner and native private-root protection against
Core's OWN prospective local root, then sample exact prepared native evidence
inside one existing retained descriptor/registry/journal guard. The native
probe is observational and the guard releases before the result is returned.
No caller-supplied readiness flags, callbacks, handles, paths to mutate,
writer operation, persistence claim, or production authority are exported.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_native_preflight as native
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateProductionNativePreflightState(str, Enum):
    PROTECTION_OBSERVED_NO_WRITE = "protection_observed_no_write"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INTENT_UNQUALIFIED = "intent_unqualified"
    ROOT_UNQUALIFIED = "root_unqualified"
    NATIVE_PROTECTION_REFUSED = "native_protection_refused"
    OWNER_MISMATCH = "owner_mismatch"
    BINDING_MISMATCH = "binding_mismatch"
    OWNER_CHANGED = "owner_changed"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    EVIDENCE_CONFLICT_PRESERVE = "evidence_conflict_preserve"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateProductionNativePreflightState, str] = {
    PrivateProductionNativePreflightState.PROTECTION_OBSERVED_NO_WRITE: (
        "Owner, native private-root attributes and prepared evidence observed under "
        "one retained guard; production mutation remains prohibited."
    ),
    PrivateProductionNativePreflightState.INVALID_REQUEST: "Invalid read-only prerequisite request.",
    PrivateProductionNativePreflightState.OPERATION_NOT_ADMITTED: "Only prepared stage-to-registry review is supported.",
    PrivateProductionNativePreflightState.REVISION_MISMATCH_REFUSED: "Expected registry revision was not admitted.",
    PrivateProductionNativePreflightState.INTENT_UNQUALIFIED: "Canonical transaction intent was unqualified.",
    PrivateProductionNativePreflightState.ROOT_UNQUALIFIED: "Private root or workspace path is not Core-qualified.",
    PrivateProductionNativePreflightState.NATIVE_PROTECTION_REFUSED: "Native private-root protection is not restrictive or verifiable.",
    PrivateProductionNativePreflightState.OWNER_MISMATCH: "Private metadata owner differs from the effective OS principal.",
    PrivateProductionNativePreflightState.BINDING_MISMATCH: "Current workspace is inconsistent with the proposed binding.",
    PrivateProductionNativePreflightState.OWNER_CHANGED: "Effective process owner changed during observation.",
    PrivateProductionNativePreflightState.NAMESPACE_CONFLICT_PRESERVE: "Protected transaction namespace changed; preserve evidence.",
    PrivateProductionNativePreflightState.EVIDENCE_CONFLICT_PRESERVE: "Protected registry, descriptor, stage or native identities conflicted.",
    PrivateProductionNativePreflightState.GUARD_REFUSED: "Operation-owned native guard could not be retained or released.",
    PrivateProductionNativePreflightState.INTERRUPTED_PRESERVE: "Protected preflight interrupted; preserve pending evidence.",
    PrivateProductionNativePreflightState.UNSUPPORTED: "Native preflight is unsupported for this OS context.",
    PrivateProductionNativePreflightState.IO_ERROR: "Protected prerequisite observation was refused.",
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateProductionNativePreflightReview:
    """Sanitized after-release result; NEVER a capability or permission."""

    state: PrivateProductionNativePreflightState
    message: str
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateProductionNativePreflightReview(non_authorizing=True)"


def _result(
    state: PrivateProductionNativePreflightState,
) -> PrivateProductionNativePreflightReview:
    return PrivateProductionNativePreflightReview(
        state, _MESSAGES[state], barrier._REQUIRED
    )


def _native_observation(
    private_root: Path,
    expected_owner: inspection.EffectiveOSOwner | None = None,
) -> tuple[
    PrivateProductionNativePreflightState | None, inspection.EffectiveOSOwner | None
]:
    """No user-provided owner/root accepted as evidence; sample Core probes."""
    state = PrivateProductionNativePreflightState
    inspected = inspection.inspect_private_root()
    if type(inspected) is not inspection.PrivateRootInspection:
        return state.ROOT_UNQUALIFIED, None
    if (
        inspected.state is not inspection.PrivateRootState.PRESENT_UNVERIFIED
        or not isinstance(inspected.candidate, Path)
        or inspected.candidate != private_root
        or type(inspected.owner) is not inspection.EffectiveOSOwner
    ):
        return state.ROOT_UNQUALIFIED, None
    owner = inspected.owner
    if expected_owner is not None and owner != expected_owner:
        return state.OWNER_CHANGED, None
    native_result = native.inspect_native_private_preflight()
    if (
        type(native_result) is not native.NativePrivatePreflight
        or native_result.state
        is not native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        return state.NATIVE_PROTECTION_REFUSED, None
    return None, owner


def _intent_owner_and_binding(
    checked: intents.PrivateTransactionIntent,
    owner: inspection.EffectiveOSOwner,
    workspace_root: Path,
) -> PrivateProductionNativePreflightState | None:
    """Validate canonical metadata's owner and accepted after-root, not authority."""
    state = PrivateProductionNativePreflightState
    before_raw = checked.registry_before
    after_raw = checked.registry_after
    if type(before_raw) is not bytes or type(after_raw) is not bytes:
        return state.INTENT_UNQUALIFIED
    before = metadata.decode_private_registry(before_raw)
    after = metadata.decode_private_registry(after_raw)
    if (
        before.owner.kind != owner.kind
        or before.owner.value != owner.value
        or after.owner != before.owner
    ):
        return state.OWNER_MISMATCH
    if (
        metadata.encode_private_registry(before) != before_raw
        or metadata.encode_private_registry(after) != after_raw
    ):
        return state.INTENT_UNQUALIFIED
    matches = [
        entry
        for entry in after.bindings
        if entry.association_id == checked.witness.association_after
    ]
    if len(matches) != 1 or matches[0].accepted_root != str(workspace_root):
        return state.BINDING_MISMATCH
    if checked.witness.operation is witness.PrivateBindingOperation.REBIND_MOVE:
        old = [
            entry
            for entry in before.bindings
            if entry.association_id == checked.witness.association_before
        ]
        if len(old) != 1 or old[0].accepted_root == str(workspace_root):
            return state.BINDING_MISMATCH
    return None


def review_protected_production_native_prerequisites(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateProductionNativePreflightReview:
    """Observe native root/owner and exact protected prepared state; NEVER write.

    The existing guard is held across all inner checks, never yielded to the
    caller. A positive observation goes stale on release. No production writer
    is reachable here; durability, metadata mutation and journal retirement
    remain outside this slice.
    """
    state = PrivateProductionNativePreflightState
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
        decision = barrier.review_private_production_write_barrier(
            step, expected_revision, proposed
        )
        if type(decision) is not barrier.PrivateProductionWriteBarrierReview:
            return _result(state.INTENT_UNQUALIFIED)
        if (
            decision.state
            is barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ):
            return _result(state.REVISION_MISMATCH_REFUSED)
        if (
            decision.state
            is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ):
            return _result(state.INTENT_UNQUALIFIED)
        raw = intents.encode_private_transaction_intent(proposed)
        if type(raw) is not bytes or len(raw) > intents.MAX_INTENT_BYTES:
            return _result(state.INTENT_UNQUALIFIED)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(state.INTENT_UNQUALIFIED)
        early_refusal, owner = _native_observation(existing_private_root)
        if early_refusal is not None or owner is None:
            return _result(early_refusal or state.ROOT_UNQUALIFIED)
        mismatch = _intent_owner_and_binding(checked, owner, existing_workspace_root)
        if mismatch is not None:
            return _result(mismatch)
        if (
            type(checked.descriptor_before) is not bytes
            or type(checked.registry_before) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        images: parents._Image = (
            raw,
            checked.registry_before,
            checked.descriptor_before,
            checked.registry_after,
        )
        tx = checked.witness.transaction_id
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            # Fresh canonical re-decode occurs while the same native guard is
            # held. No stale preflight/description can substitute for it.
            inside = intents.decode_private_transaction_intent(raw)
            if (
                type(inside) is not intents.PrivateTransactionIntent
                or inside != proposed
                or inside != checked
                or intents.encode_private_transaction_intent(inside) != raw
            ):
                return _result(state.INTENT_UNQUALIFIED)
            inside_mismatch = _intent_owner_and_binding(
                inside, owner, existing_workspace_root
            )
            if inside_mismatch is not None:
                return _result(inside_mismatch)
            expected_namespace = recovery._namespace(existing_private_root, tx)
            if (
                type(expected_namespace) is not tuple
                or len(expected_namespace) != 3
                or expected_namespace[2] is not True
            ):
                return _result(state.NAMESPACE_CONFLICT_PRESERVE)
            wanted = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            baseline: scope._Frame | None = None
            for _ in range(3):
                refusal, current_owner = _native_observation(
                    existing_private_root, owner
                )
                if refusal is not None or current_owner is None:
                    return _result(refusal or state.OWNER_CHANGED)
                if ordered._owner() != owner:
                    return _result(state.OWNER_CHANGED)
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, expected_namespace, wanted
                ):
                    return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                current = scope._observe(
                    existing_private_root,
                    existing_workspace_root,
                    checked,
                    owner,
                    len(raw),
                )
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, expected_namespace, wanted
                ):
                    return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                if ordered._owner() != owner:
                    return _result(state.OWNER_CHANGED)
                if scope._frame_state(current, baseline, images) is not None:
                    return _result(state.EVIDENCE_CONFLICT_PRESERVE)
                if baseline is None:
                    baseline = current
            refusal, current_owner = _native_observation(existing_private_root, owner)
            if refusal is not None or current_owner is None:
                return _result(refusal or state.OWNER_CHANGED)
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            if not operation._same_native_namespace(
                existing_private_root, tx, owner, expected_namespace, wanted
            ):
                return _result(state.NAMESPACE_CONFLICT_PRESERVE)
            if (
                baseline is None
                or parents._parents(existing_private_root, existing_workspace_root)
                != baseline.parent_stamps
            ):
                return _result(state.EVIDENCE_CONFLICT_PRESERVE)
        return _result(state.PROTECTION_OBSERVED_NO_WRITE)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except (
        scope._ImageUnqualified,
        parents._ParentUnqualified,
        bridge._IdentityUnqualified,
    ):
        return _result(state.EVIDENCE_CONFLICT_PRESERVE)
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
        metadata.PrivateMetadataError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
