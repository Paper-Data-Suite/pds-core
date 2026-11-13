"""Retained exact-image and registry-revision recovery review (Core #238 3G12).

One continuous native descriptor/journal/registry lock protects two complete
native byte-image observations, namespace/owner/inventory checks, and strict
before/after revision matching. This is evidence review, NOT a CAS reservation,
write, replay, durable commit, journal retirement or Notes capability.
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
from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRecoveryExactRevisionState(str, Enum):
    PREPARED_EXACT_REVIEW_REQUIRED = "prepared_exact_review_required"
    DESCRIPTOR_PENDING_EXACT_REVIEW_REQUIRED = (
        "descriptor_pending_exact_review_required"
    )
    JOURNAL_PENDING_EXACT_REVIEW_REQUIRED = "journal_pending_exact_review_required"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
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
    PrivateRecoveryExactRevisionState.PREPARED_EXACT_REVIEW_REQUIRED: "Exact staged before-image and revision observed under one retained guard; independent review required.",
    PrivateRecoveryExactRevisionState.DESCRIPTOR_PENDING_EXACT_REVIEW_REQUIRED: "Exact registry after-image and expected revision observed; descriptor review required.",
    PrivateRecoveryExactRevisionState.JOURNAL_PENDING_EXACT_REVIEW_REQUIRED: "Exact metadata after-images and expected revision observed; journal durability and retirement unqualified.",
    PrivateRecoveryExactRevisionState.REVISION_MISMATCH_REFUSED: "Expected registry revision does not match the protected checkpoint.",
    PrivateRecoveryExactRevisionState.IMAGE_MISMATCH_PRESERVE: "One or more protected images differs from the pending proposal; preserve all evidence.",
    PrivateRecoveryExactRevisionState.IMAGE_DRIFT_PRESERVE: "Native image bytes changed during retained review; preserve all evidence.",
    PrivateRecoveryExactRevisionState.NAMESPACE_CHANGED_PRESERVE: "Journal/stage namespace or inventory changed or is unqualified.",
    PrivateRecoveryExactRevisionState.OWNER_CHANGED: "Effective local OS owner changed during the review.",
    PrivateRecoveryExactRevisionState.GUARD_REFUSED: "Native retained guard refused or changed during review.",
    PrivateRecoveryExactRevisionState.INTERRUPTED_PRESERVE: "Recovery observation interrupted; preserve all evidence.",
    PrivateRecoveryExactRevisionState.INVALID_REQUEST: "Exact-image recovery request invalid.",
    PrivateRecoveryExactRevisionState.INITIALIZATION_REFUSED: "First binding requires a separately qualified absence protocol.",
    PrivateRecoveryExactRevisionState.UNSUPPORTED: "Native exact-image review unsupported on this platform.",
    PrivateRecoveryExactRevisionState.IO_ERROR: "Native exact-image recovery observation could not finish.",
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryExactRevisionReview:
    """Sanitized advisory state; never exposes bytes, paths, owner, revision, handles or authority."""

    state: PrivateRecoveryExactRevisionState
    message: str


def _result(
    state: PrivateRecoveryExactRevisionState,
) -> PrivateRecoveryExactRevisionReview:
    return PrivateRecoveryExactRevisionReview(state, _MESSAGES[state])


def _images(
    root: Path,
    workspace: Path,
    transaction_id: str,
    owner: inspection.EffectiveOSOwner,
    stage: bool,
) -> tuple[bytes, bytes, bytes, bytes | None] | None:
    """Existing-native-handle image reads only; caller holds complete retained guard.

    The underlying readers verify native filesystem backing, metadata format,
    owner and file identity. They MUST NOT acquire any nested review locks.
    """
    journal = readers._journal(root / "transactions", transaction_id, owner)
    registry = readers._registry(root, owner)
    association = readers._descriptor(workspace)
    staged = readers._stage(root, transaction_id, owner) if stage else None
    if (
        readers._journal_failure(journal) is not None
        or readers._registry_failure(registry) is not None
        or readers._descriptor_failure(association) is not None
        or (staged is not None and readers._stage_failure(staged) is not None)
        or type(journal.image) is not bytes
        or type(registry.image) is not bytes
        or type(association.image) is not bytes
        or (staged is not None and type(staged.image) is not bytes)
    ):
        return None
    return (
        journal.image,
        registry.image,
        association.image,
        staged.image if staged is not None else None,
    )


def review_retained_private_recovery_exact_revision(
    requested_step: actions.PrivateRecoveryProposedStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRecoveryExactRevisionReview:
    """Review exactly one expected registry revision and journal/metadata images.

    The returned sanitized match is NOT a reusable token and cannot authorize
    any mutation. A protected lock-honoring local observation is not durability,
    hostile-same-user protection, or cross-device CAS.
    """
    state = PrivateRecoveryExactRevisionState
    if sys.platform not in {"linux", "win32"}:
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

    allowed = {
        actions.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART: (
            True,
            before.revision,
        ),
        actions.PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION: (
            False,
            after.revision,
        ),
        actions.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT: (
            False,
            after.revision,
        ),
    }
    expects_stage, required_revision = allowed[requested_step]
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
            if namespace[2] != expects_stage:
                return _result(state.IMAGE_MISMATCH_PRESERVE)
            expected_inventory = (
                inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                if expects_stage
                else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
            )
            first: tuple[bytes, bytes, bytes, bytes | None] | None = None
            for round_no in range(2):
                if (
                    readers._inventory(existing_private_root, owner)
                    is not expected_inventory
                    or recovery._namespace(
                        existing_private_root, checked.witness.transaction_id
                    )
                    != namespace
                ):
                    return _result(state.NAMESPACE_CHANGED_PRESERVE)
                if ordered._owner() != owner:
                    return _result(state.OWNER_CHANGED)
                observed = _images(
                    existing_private_root,
                    existing_workspace_root,
                    checked.witness.transaction_id,
                    owner,
                    expects_stage,
                )
                if observed is None:
                    return _result(state.IMAGE_MISMATCH_PRESERVE)
                if round_no == 0:
                    first = observed
                elif observed != first:
                    return _result(state.IMAGE_DRIFT_PRESERVE)
            if (
                readers._inventory(existing_private_root, owner)
                is not expected_inventory
                or recovery._namespace(
                    existing_private_root, checked.witness.transaction_id
                )
                != namespace
            ):
                return _result(state.NAMESPACE_CHANGED_PRESERVE)
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            assert (
                first is not None
            )  # First image is assigned if both native reads succeeded.
            journal, registry, association, staged = first
            if journal != raw:
                answer = state.IMAGE_MISMATCH_PRESERVE
            elif expects_stage:
                answer = (
                    state.PREPARED_EXACT_REVIEW_REQUIRED
                    if registry == checked.registry_before
                    and association == checked.descriptor_before
                    and staged == checked.registry_after
                    else state.IMAGE_MISMATCH_PRESERVE
                )
            elif (
                requested_step
                is actions.PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION
            ):
                answer = (
                    state.DESCRIPTOR_PENDING_EXACT_REVIEW_REQUIRED
                    if registry == checked.registry_after
                    and association == checked.descriptor_before
                    and staged is None
                    else state.IMAGE_MISMATCH_PRESERVE
                )
            else:
                answer = (
                    state.JOURNAL_PENDING_EXACT_REVIEW_REQUIRED
                    if registry == checked.registry_after
                    and association == checked.descriptor_after
                    and staged is None
                    else state.IMAGE_MISMATCH_PRESERVE
                )
            if answer in {
                state.PREPARED_EXACT_REVIEW_REQUIRED,
                state.DESCRIPTOR_PENDING_EXACT_REVIEW_REQUIRED,
                state.JOURNAL_PENDING_EXACT_REVIEW_REQUIRED,
            }:
                # Exact native bytes also require the caller's revision, not only
                # the expected witness revision from the proposed intent.
                try:
                    observed_registry = metadata.decode_private_registry(registry)
                    if observed_registry.revision != expected_revision:
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
