"""Read-only native postimage observation for guarded recovery (Core #238 3G16).

Two complete native snapshots under ONE retained descriptor/journal/registry scope
are compared with the 3G15 pure operation-postcondition contract. The synthetic
before-image is an *expectation derived from a pending journal*, not proof a
mutation occurred. This module has no writer, callback, permit or durability API.
Journal retirement is deliberately refused until native absence custody is proven.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_operation_postconditions as post
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateNativeRecoveryPostimageState(str, Enum):
    STABLE_POSTIMAGE_REVIEW_REQUIRED = "stable_postimage_review_required"
    STAGE_PRESENT_PRESERVE = "stage_present_preserve"
    NO_PROGRESS_PRESERVE = "no_progress_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    IMAGE_DRIFT_PRESERVE = "image_drift_preserve"
    NAMESPACE_CHANGED_PRESERVE = "namespace_changed_preserve"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    RETIREMENT_UNQUALIFIED = "retirement_unqualified"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateNativeRecoveryPostimageState.STABLE_POSTIMAGE_REVIEW_REQUIRED: "Current protected images match an expected postcondition; earlier mutation, CAS and durability are not proved.",
    PrivateNativeRecoveryPostimageState.STAGE_PRESENT_PRESERVE: "A pending registry stage remains; preserve all evidence without advancing recovery.",
    PrivateNativeRecoveryPostimageState.NO_PROGRESS_PRESERVE: "The observed images still match a pre-operation checkpoint; preserve evidence.",
    PrivateNativeRecoveryPostimageState.POSTIMAGE_CONFLICT_PRESERVE: "Native postimages do not match the proposed transition; preserve all artifacts.",
    PrivateNativeRecoveryPostimageState.IMAGE_DRIFT_PRESERVE: "Native image bytes changed during one retained guard; preserve evidence.",
    PrivateNativeRecoveryPostimageState.NAMESPACE_CHANGED_PRESERVE: "Pending journal, staged-entry namespace or inventory changed or was unqualified.",
    PrivateNativeRecoveryPostimageState.REVISION_MISMATCH_REFUSED: "Requested registry revision differs from the canonical journal transition.",
    PrivateNativeRecoveryPostimageState.RETIREMENT_UNQUALIFIED: "Native journal absence and durable retirement cannot be established by this guard.",
    PrivateNativeRecoveryPostimageState.OWNER_CHANGED: "Effective OS owner changed during native observation.",
    PrivateNativeRecoveryPostimageState.GUARD_REFUSED: "Existing native retained guard refused or changed during observation.",
    PrivateNativeRecoveryPostimageState.INTERRUPTED_PRESERVE: "Native postcondition observation interrupted; preserve all evidence.",
    PrivateNativeRecoveryPostimageState.INVALID_REQUEST: "Invalid native postcondition observation request.",
    PrivateNativeRecoveryPostimageState.INITIALIZATION_REFUSED: "Initial binding requires a separately qualified native absence protocol.",
    PrivateNativeRecoveryPostimageState.UNSUPPORTED: "Native postcondition observation unsupported on this platform.",
    PrivateNativeRecoveryPostimageState.IO_ERROR: "Native postcondition observation could not finish; no mutation was performed.",
}


@dataclass(frozen=True, slots=True)
class PrivateNativeRecoveryPostimageReview:
    """Sanitized state only: never a path, byte image, revision or write token."""

    state: PrivateNativeRecoveryPostimageState
    message: str


def _result(
    state: PrivateNativeRecoveryPostimageState,
) -> PrivateNativeRecoveryPostimageReview:
    return PrivateNativeRecoveryPostimageReview(state, _MESSAGES[state])


def _valid_native_image(image: object) -> bool:
    return (
        type(image) is tuple
        and len(image) == 4
        and all(type(value) is bytes for value in image[:3])
        and image[3] is None
    )


def review_native_private_recovery_postimage(
    kind: post.PrivateRecoveryOperationKind,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateNativeRecoveryPostimageReview:
    """Observe protected *current* postimages, never perform a recovery operation.

    The hypothetical preimage is constructed from the exact pending intent.
    Even a stable match does not establish that the preimage existed, a writer
    ran, its effect was durable, or the journal can safely be retired.
    Any actual future native writer must revalidate inside its OWN retained
    mutation scope, with verified persistence and interruption postconditions.
    """
    state = PrivateNativeRecoveryPostimageState
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if (
        type(kind) is not post.PrivateRecoveryOperationKind
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(state.INVALID_REQUEST)
    if kind is post.PrivateRecoveryOperationKind.JOURNAL_RETIREMENT:
        return _result(state.RETIREMENT_UNQUALIFIED)
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
        before_registry = metadata.decode_private_registry(checked.registry_before)
        after_registry = metadata.decode_private_registry(checked.registry_after)
        if (
            before_registry.revision != checked.witness.registry_revision_before
            or after_registry.revision != checked.witness.registry_revision_after
            or after_registry.revision != before_registry.revision + 1
            or metadata.encode_private_registry(before_registry)
            != checked.registry_before
            or metadata.encode_private_registry(after_registry)
            != checked.registry_after
        ):
            return _result(state.INVALID_REQUEST)
        required = (
            before_registry.revision
            if kind is post.PrivateRecoveryOperationKind.STAGE_TO_REGISTRY
            else after_registry.revision
        )
        if expected_revision != required:
            return _result(state.REVISION_MISMATCH_REFUSED)
        expected_preimage = (
            post.PrivateRecoveryOperationImage(
                encoded,
                checked.registry_before,
                checked.descriptor_before,
                checked.registry_after,
            )
            if kind is post.PrivateRecoveryOperationKind.STAGE_TO_REGISTRY
            else post.PrivateRecoveryOperationImage(
                encoded,
                checked.registry_after,
                checked.descriptor_before,
                None,
            )
        )
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)

    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            namespace = recovery._namespace(
                existing_private_root, checked.witness.transaction_id
            )
            if namespace[2]:
                answer = state.STAGE_PRESENT_PRESERVE
            else:
                expected_inventory = (
                    inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
                )
                answer = state.STABLE_POSTIMAGE_REVIEW_REQUIRED
                first: tuple[bytes, bytes, bytes, bytes | None] | None = None
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
                    image = exact._images(
                        existing_private_root,
                        existing_workspace_root,
                        checked.witness.transaction_id,
                        owner,
                        False,
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
                    if not _valid_native_image(image):
                        answer = state.POSTIMAGE_CONFLICT_PRESERVE
                        break
                    assert isinstance(image, tuple)
                    if first is None:
                        first = image
                    elif first != image:
                        answer = state.IMAGE_DRIFT_PRESERVE
                        break
                if answer is state.STABLE_POSTIMAGE_REVIEW_REQUIRED:
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
                    elif first is None:
                        answer = state.POSTIMAGE_CONFLICT_PRESERVE
                    else:
                        observed = post.PrivateRecoveryOperationImage(*first)
                        classified = (
                            post.classify_private_recovery_operation_postconditions(
                                kind,
                                expected_revision,
                                checked,
                                expected_preimage,
                                observed,
                            )
                        )
                        if (
                            type(classified)
                            is not post.PrivateRecoveryPostconditionReview
                        ):
                            answer = state.POSTIMAGE_CONFLICT_PRESERVE
                        elif (
                            classified.state
                            is post.PrivateRecoveryPostconditionState.NO_PROGRESS_PRESERVE
                        ):
                            answer = state.NO_PROGRESS_PRESERVE
                        elif (
                            classified.state
                            is not post.PrivateRecoveryPostconditionState.TRANSITION_OBSERVED_REVIEW_REQUIRED
                        ):
                            answer = state.POSTIMAGE_CONFLICT_PRESERVE
            # Guard release and native postcondition must succeed before the advisory return.
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
