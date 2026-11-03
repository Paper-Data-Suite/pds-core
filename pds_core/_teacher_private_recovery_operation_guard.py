"""Single operation-owned native guard for recovery *inspection* (Core #238 3G14).

One complete native retained scope covers repeated checkpoint classifications, exact
file images, revision and namespace checks. No callbacks or mutable handles leave
this scope. A converged finding is NOT a commit permit, CAS, stage consumption,
descriptor repair, journal retirement, durable-persistence proof or Notes access.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as steps
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRecoveryOperationGuardState(str, Enum):
    PREPARED_ONE_SCOPE_REVIEW_REQUIRED = "prepared_one_scope_review_required"
    DESCRIPTOR_PENDING_ONE_SCOPE_REVIEW_REQUIRED = (
        "descriptor_pending_one_scope_review_required"
    )
    JOURNAL_PENDING_ONE_SCOPE_REVIEW_REQUIRED = (
        "journal_pending_one_scope_review_required"
    )
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    ACTION_MISMATCH_REFUSED = "action_mismatch_refused"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    IMAGE_MISMATCH_PRESERVE = "image_mismatch_preserve"
    IMAGE_DRIFT_PRESERVE = "image_drift_preserve"
    NAMESPACE_CHANGED_PRESERVE = "namespace_changed_preserve"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRecoveryOperationGuardState.PREPARED_ONE_SCOPE_REVIEW_REQUIRED: "Prepared journal, stage and before-images matched within one retained scope; review only.",
    PrivateRecoveryOperationGuardState.DESCRIPTOR_PENDING_ONE_SCOPE_REVIEW_REQUIRED: "Registry after-image and descriptor before-image matched within one retained scope; review only.",
    PrivateRecoveryOperationGuardState.JOURNAL_PENDING_ONE_SCOPE_REVIEW_REQUIRED: "Registry and descriptor after-images matched within one retained scope; review only.",
    PrivateRecoveryOperationGuardState.REVISION_MISMATCH_REFUSED: "Observed or requested registry revision is not the canonical expected revision.",
    PrivateRecoveryOperationGuardState.ACTION_MISMATCH_REFUSED: "Recovery review step does not match the native checkpoint.",
    PrivateRecoveryOperationGuardState.CHECKPOINT_CONFLICT_PRESERVE: "Native recovery checkpoint conflicts with the requested safe stage; preserve artifacts.",
    PrivateRecoveryOperationGuardState.IMAGE_MISMATCH_PRESERVE: "Native journal, registry, descriptor or stage bytes were missing or inconsistent.",
    PrivateRecoveryOperationGuardState.IMAGE_DRIFT_PRESERVE: "Native checkpoint or exact byte image changed during the retained review.",
    PrivateRecoveryOperationGuardState.NAMESPACE_CHANGED_PRESERVE: "Native pending/stage namespace or inventory changed or was unqualified.",
    PrivateRecoveryOperationGuardState.OWNER_CHANGED: "Effective native OS owner changed during review.",
    PrivateRecoveryOperationGuardState.GUARD_REFUSED: "Existing native retained guard refused the review.",
    PrivateRecoveryOperationGuardState.INTERRUPTED_PRESERVE: "Native recovery inspection interrupted; preserve all artifacts.",
    PrivateRecoveryOperationGuardState.INVALID_REQUEST: "Invalid operation-owned recovery inspection request.",
    PrivateRecoveryOperationGuardState.INITIALIZATION_REFUSED: "Initial association requires a separate native absence protocol.",
    PrivateRecoveryOperationGuardState.UNSUPPORTED: "Operation-owned native recovery review unsupported.",
    PrivateRecoveryOperationGuardState.IO_ERROR: "Native recovery evidence could not be verified; no mutation performed.",
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryOperationGuardReview:
    """Sanitized result only; never expose bytes, paths, handles or a write token."""

    state: PrivateRecoveryOperationGuardState
    message: str


def _result(
    state: PrivateRecoveryOperationGuardState,
) -> PrivateRecoveryOperationGuardReview:
    return PrivateRecoveryOperationGuardReview(state, _MESSAGES[state])


_EXPECTED: dict[
    steps.PrivateRecoveryProposedStep,
    tuple[
        bool,
        recovery.PrivatePostcrashReconciliationState,
        PrivateRecoveryOperationGuardState,
    ],
] = {
    steps.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART: (
        True,
        recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
        PrivateRecoveryOperationGuardState.PREPARED_ONE_SCOPE_REVIEW_REQUIRED,
    ),
    steps.PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION: (
        False,
        recovery.PrivatePostcrashReconciliationState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        PrivateRecoveryOperationGuardState.DESCRIPTOR_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
    ),
    steps.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT: (
        False,
        recovery.PrivatePostcrashReconciliationState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
        PrivateRecoveryOperationGuardState.JOURNAL_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
    ),
}


def _same_native_namespace(
    private_root: Path,
    transaction_id: str,
    owner: inspection.EffectiveOSOwner,
    original: tuple[frozenset[str], frozenset[str], bool],
    expected_inventory: inventory.PrivateRegistryStageInventoryState,
) -> bool:
    # Native reader accepts a qualified EffectiveOSOwner. No nested locks.
    return (
        readers._inventory(private_root, owner) is expected_inventory
        and recovery._namespace(private_root, transaction_id) == original
    )


def review_operation_owned_private_recovery_guard(
    requested_step: steps.PrivateRecoveryProposedStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRecoveryOperationGuardReview:
    """Hold one retained native guard while confirming exact recovery evidence.

    Twice: verify namespace/owner/inventory, classify checkpoint natively and
    inspect exact journal/registry/descriptor/stage images. Compare both rounds
    and the transaction witness revision before releasing the guard. No mutation
    or external callback occurs while holding the guard. Hostile same-user
    writers, power-loss durability and cross-device CAS are NOT established.
    """
    state = PrivateRecoveryOperationGuardState
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if (
        type(requested_step) is not steps.PrivateRecoveryProposedStep
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
        if (
            type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.descriptor_after) is not bytes
            or type(checked.witness.transaction_id) is not str
        ):
            return _result(state.INVALID_REQUEST)
        before = metadata.decode_private_registry(checked.registry_before)
        after = metadata.decode_private_registry(checked.registry_after)
        if (
            before.revision != checked.witness.registry_revision_before
            or after.revision != checked.witness.registry_revision_after
            or after.revision != before.revision + 1
            or metadata.encode_private_registry(before) != checked.registry_before
            or metadata.encode_private_registry(after) != checked.registry_after
        ):
            return _result(state.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)

    expects_stage, checkpoint_expected, successful = _EXPECTED[requested_step]
    required_revision = before.revision if expects_stage else after.revision
    if expected_revision != required_revision:
        return _result(state.REVISION_MISMATCH_REFUSED)

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
            first: (
                tuple[
                    recovery.PrivatePostcrashReconciliationState,
                    tuple[bytes, bytes, bytes, bytes | None],
                ]
                | None
            ) = None
            answer = successful
            for _ in range(2):
                if not _same_native_namespace(
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
                if not _same_native_namespace(
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
                    or image is None
                    or type(image) is not tuple
                    or len(image) != 4
                    or any(type(value) is not bytes for value in image[:3])
                    or (image[3] is not None and type(image[3]) is not bytes)
                ):
                    answer = state.IMAGE_MISMATCH_PRESERVE
                    break
                observation = (checkpoint, image)
                if first is None:
                    first = observation
                elif first != observation:
                    answer = state.IMAGE_DRIFT_PRESERVE
                    break
            if answer is successful and not _same_native_namespace(
                existing_private_root,
                checked.witness.transaction_id,
                owner,
                namespace,
                expected_inventory,
            ):
                answer = state.NAMESPACE_CHANGED_PRESERVE
            if answer is successful and ordered._owner() != owner:
                answer = state.OWNER_CHANGED
            if answer is successful:
                assert first is not None
                checkpoint, image = first
                journal, registry, association, staged = image
                if namespace[2] != expects_stage:
                    answer = state.ACTION_MISMATCH_REFUSED
                elif checkpoint is not checkpoint_expected:
                    answer = state.CHECKPOINT_CONFLICT_PRESERVE
                elif journal != raw:
                    answer = state.IMAGE_MISMATCH_PRESERVE
                elif registry != (
                    checked.registry_before if expects_stage else checked.registry_after
                ):
                    answer = state.IMAGE_MISMATCH_PRESERVE
                elif association != (
                    checked.descriptor_after
                    if requested_step
                    is steps.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT
                    else checked.descriptor_before
                ):
                    answer = state.IMAGE_MISMATCH_PRESERVE
                elif staged != (checked.registry_after if expects_stage else None):
                    answer = state.IMAGE_MISMATCH_PRESERVE
                else:
                    try:
                        parsed = metadata.decode_private_registry(registry)
                        if parsed.revision != expected_revision:
                            answer = state.REVISION_MISMATCH_REFUSED
                    except (
                        metadata.PrivateMetadataError,
                        ValueError,
                        TypeError,
                        AttributeError,
                    ):
                        answer = state.IMAGE_MISMATCH_PRESERVE
        return _result(answer)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
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
