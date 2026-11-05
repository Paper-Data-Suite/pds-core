"""Read-only stage-to-registry checkpoint bridge (Core #238 Slice 3G28).

Connect the 3G27 synthetic writer's single allowed operation to the actual
3G22 native retained parent, namespace, file-identity and image review. The
existing reviewer acquires and releases its own protected native guard. This
bridge never invokes a writer, accepts a callback, exports guard ownership, or
returns an execution capability. The result is stale as soon as review ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents


class PrivateNativeWriterCheckpointState(str, Enum):
    PREPARED_EVIDENCE_REVIEW_ONLY = "prepared_evidence_review_only"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    ACTION_MISMATCH_REFUSED = "action_mismatch_refused"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    PARENT_IDENTITY_CONFLICT_PRESERVE = "parent_identity_conflict_preserve"
    FILE_IDENTITY_CONFLICT_PRESERVE = "file_identity_conflict_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateNativeWriterCheckpointState.PREPARED_EVIDENCE_REVIEW_ONLY: (
        "Prepared protected native checkpoint was observed under a released read-only "
        "guard. Writer admission, registry replacement and durable commit are refused."
    ),
    PrivateNativeWriterCheckpointState.OPERATION_NOT_ADMITTED: (
        "Only an existing prepared stage-to-registry checkpoint is reviewable; "
        "initialization, descriptor completion and journal retirement are not admitted."
    ),
    PrivateNativeWriterCheckpointState.INVALID_REQUEST: (
        "Invalid native writer checkpoint review request or untrusted result."
    ),
    PrivateNativeWriterCheckpointState.INITIALIZATION_REFUSED: (
        "Initialization needs an independent native absence and persistence protocol."
    ),
    PrivateNativeWriterCheckpointState.REVISION_MISMATCH_REFUSED: (
        "The expected native registry revision does not match the prepared intent."
    ),
    PrivateNativeWriterCheckpointState.ACTION_MISMATCH_REFUSED: (
        "Native checkpoint stage presence differs from the requested operation."
    ),
    PrivateNativeWriterCheckpointState.CHECKPOINT_CONFLICT_PRESERVE: (
        "Native checkpoint classification conflicts with the prepared operation."
    ),
    PrivateNativeWriterCheckpointState.PARENT_IDENTITY_CONFLICT_PRESERVE: (
        "A protected parent-directory identity is missing or changed; preserve evidence."
    ),
    PrivateNativeWriterCheckpointState.FILE_IDENTITY_CONFLICT_PRESERVE: (
        "A protected journal, registry, descriptor or stage file identity is unqualified."
    ),
    PrivateNativeWriterCheckpointState.IMAGE_CONFLICT_PRESERVE: (
        "Native byte images are inconsistent, changed or unqualified; preserve evidence."
    ),
    PrivateNativeWriterCheckpointState.NAMESPACE_CONFLICT_PRESERVE: (
        "Pending-journal or staged-registry namespace changed; preserve evidence."
    ),
    PrivateNativeWriterCheckpointState.OWNER_CHANGED: (
        "Effective native owner changed during the protected review."
    ),
    PrivateNativeWriterCheckpointState.GUARD_REFUSED: (
        "Protected native retained guard was unavailable or refused the review."
    ),
    PrivateNativeWriterCheckpointState.INTERRUPTED_PRESERVE: (
        "Read-only checkpoint review was interrupted; preserve pending evidence."
    ),
    PrivateNativeWriterCheckpointState.UNSUPPORTED: (
        "Native checkpoint review is unsupported on this platform."
    ),
    PrivateNativeWriterCheckpointState.IO_ERROR: (
        "Native checkpoint observation could not finish; preserve pending evidence."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateNativeWriterCheckpointReview:
    """Sanitized status only: no paths, byte images, native handles or permits."""

    state: PrivateNativeWriterCheckpointState
    message: str


def _result(
    state: PrivateNativeWriterCheckpointState,
) -> PrivateNativeWriterCheckpointReview:
    return PrivateNativeWriterCheckpointReview(state, _MESSAGES[state])


_PARENT_FAILURES: dict[
    parents.PrivateRecoveryParentContinuityState, PrivateNativeWriterCheckpointState
] = {
    parents.PrivateRecoveryParentContinuityState.PARENT_IDENTITY_UNQUALIFIED: PrivateNativeWriterCheckpointState.PARENT_IDENTITY_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.PARENT_DRIFT_PRESERVE: PrivateNativeWriterCheckpointState.PARENT_IDENTITY_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.FILE_IDENTITY_UNQUALIFIED: PrivateNativeWriterCheckpointState.FILE_IDENTITY_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.FILE_IDENTITY_DRIFT_PRESERVE: PrivateNativeWriterCheckpointState.FILE_IDENTITY_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.IMAGE_CONFLICT_PRESERVE: PrivateNativeWriterCheckpointState.IMAGE_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.IMAGE_DRIFT_PRESERVE: PrivateNativeWriterCheckpointState.IMAGE_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.CHECKPOINT_CONFLICT_PRESERVE: PrivateNativeWriterCheckpointState.CHECKPOINT_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.NAMESPACE_CHANGED_PRESERVE: PrivateNativeWriterCheckpointState.NAMESPACE_CONFLICT_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.OWNER_CHANGED: PrivateNativeWriterCheckpointState.OWNER_CHANGED,
    parents.PrivateRecoveryParentContinuityState.GUARD_REFUSED: PrivateNativeWriterCheckpointState.GUARD_REFUSED,
    parents.PrivateRecoveryParentContinuityState.REVISION_MISMATCH_REFUSED: PrivateNativeWriterCheckpointState.REVISION_MISMATCH_REFUSED,
    parents.PrivateRecoveryParentContinuityState.ACTION_MISMATCH_REFUSED: PrivateNativeWriterCheckpointState.ACTION_MISMATCH_REFUSED,
    parents.PrivateRecoveryParentContinuityState.INITIALIZATION_REFUSED: PrivateNativeWriterCheckpointState.INITIALIZATION_REFUSED,
    parents.PrivateRecoveryParentContinuityState.INTERRUPTED_PRESERVE: PrivateNativeWriterCheckpointState.INTERRUPTED_PRESERVE,
    parents.PrivateRecoveryParentContinuityState.INVALID_REQUEST: PrivateNativeWriterCheckpointState.INVALID_REQUEST,
    parents.PrivateRecoveryParentContinuityState.UNSUPPORTED: PrivateNativeWriterCheckpointState.UNSUPPORTED,
    parents.PrivateRecoveryParentContinuityState.IO_ERROR: PrivateNativeWriterCheckpointState.IO_ERROR,
}


def review_native_private_writer_checkpoint_admission(
    operation: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateNativeWriterCheckpointReview:
    """Bridge existing native prepared-checkpoint evidence to a *nonexecuting* review.

    The underlying 3G22 reader owns its retained guard for the *entire* native
    checkpoint classification and parent/file/byte/namespace census. Calling
    this method never produces a transferable permit. The guard has ALREADY
    RELEASED by the time the matching advisory result is returned. A future
    writer must independently reacquire protection and revalidate in its own
    operation scope; this result must never be passed to a writer.
    """
    state = PrivateNativeWriterCheckpointState
    if (
        type(operation) is not scratch.PrivateScratchWriterStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(state.INVALID_REQUEST)
    if operation is not scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    try:
        inspected = parents.review_native_private_recovery_parent_continuity(
            actions.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART,
            expected_revision,
            proposed,
            existing_private_root,
            existing_workspace_root,
        )
        if (
            type(inspected) is not parents.PrivateRecoveryParentContinuityReview
            or type(inspected.state) is not parents.PrivateRecoveryParentContinuityState
        ):
            return _result(state.INVALID_REQUEST)
        if (
            inspected.state
            is parents.PrivateRecoveryParentContinuityState.PARENTS_STABLE_REVIEW_REQUIRED
        ):
            return _result(state.PREPARED_EVIDENCE_REVIEW_ONLY)
        return _result(_PARENT_FAILURES.get(inspected.state, state.INVALID_REQUEST))
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except PermissionError:
        return _result(state.GUARD_REFUSED)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        return _result(state.IO_ERROR)
