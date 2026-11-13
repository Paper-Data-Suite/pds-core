"""Pure fail-closed operation postconditions for private recovery (Core #238 3G15).

Evaluate bounded *snapshots* around exactly one hypothetical recovery operation.
The snapshots must be obtained independently by a future native guarded writer;
this module neither reads files nor acquires locks nor executes any operation.
Matching postconditions are advisory, never a durability proof or authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRecoveryOperationKind(str, Enum):
    STAGE_TO_REGISTRY = "stage_to_registry"
    DESCRIPTOR_AFTER_IMAGE = "descriptor_after_image"
    JOURNAL_RETIREMENT = "journal_retirement"


class PrivateRecoveryPostconditionState(str, Enum):
    TRANSITION_OBSERVED_REVIEW_REQUIRED = "transition_observed_review_required"
    JOURNAL_ABSENCE_UNQUALIFIED = "journal_absence_unqualified"
    NO_PROGRESS_PRESERVE = "no_progress_preserve"
    PRECONDITION_REFUSED = "precondition_refused"
    POSTCONDITION_CONFLICT_PRESERVE = "postcondition_conflict_preserve"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"


_MESSAGES = {
    PrivateRecoveryPostconditionState.TRANSITION_OBSERVED_REVIEW_REQUIRED: (
        "Expected exact images were observed after one described operation; native custody and durability remain unverified."
    ),
    PrivateRecoveryPostconditionState.JOURNAL_ABSENCE_UNQUALIFIED: (
        "Pending journal absence was described after both metadata after-images; durable retirement is not proven."
    ),
    PrivateRecoveryPostconditionState.NO_PROGRESS_PRESERVE: (
        "No image transition was observed; preserve existing recovery evidence."
    ),
    PrivateRecoveryPostconditionState.PRECONDITION_REFUSED: (
        "The described starting images do not match the required recovery checkpoint."
    ),
    PrivateRecoveryPostconditionState.POSTCONDITION_CONFLICT_PRESERVE: (
        "Observed post-operation images are inconsistent or partially changed; preserve all evidence."
    ),
    PrivateRecoveryPostconditionState.REVISION_MISMATCH_REFUSED: (
        "The expected registry revision does not match the canonical transaction checkpoint."
    ),
    PrivateRecoveryPostconditionState.INVALID_REQUEST: "Invalid or noncanonical recovery postcondition request.",
    PrivateRecoveryPostconditionState.INITIALIZATION_REFUSED: (
        "Initial binding requires an independent guarded absence protocol."
    ),
    PrivateRecoveryPostconditionState.INTERRUPTED_PRESERVE: (
        "Postcondition classification interrupted; preserve all recovery artifacts."
    ),
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateRecoveryOperationImage:
    """Caller-supplied evidence only; no native handles, file IDs or authority.

    The order and explicit None values matter. A missing journal is not proof
    that journal retirement is durable or that the file cannot reappear.
    """

    journal: bytes | None = field(repr=False)
    registry: bytes = field(repr=False)
    descriptor: bytes = field(repr=False)
    stage: bytes | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class PrivateRecoveryPostconditionReview:
    """Sanitized state; no private bytes, revision, paths or capabilities."""

    state: PrivateRecoveryPostconditionState
    message: str


def _result(
    state: PrivateRecoveryPostconditionState,
) -> PrivateRecoveryPostconditionReview:
    return PrivateRecoveryPostconditionReview(state, _MESSAGES[state])


def _bounded(raw: object, limit: int, *, optional: bool) -> bool:
    if raw is None:
        return optional
    return type(raw) is bytes and len(raw) <= limit


def _image_valid(image: object, journal_limit: int) -> bool:
    if type(image) is not PrivateRecoveryOperationImage:
        return False
    return (
        _bounded(image.journal, journal_limit, optional=True)
        and _bounded(image.registry, metadata.MAX_REGISTRY_BYTES, optional=False)
        and _bounded(image.descriptor, metadata.MAX_ASSOCIATION_BYTES, optional=False)
        and _bounded(image.stage, metadata.MAX_REGISTRY_BYTES, optional=True)
    )


def classify_private_recovery_operation_postconditions(
    kind: PrivateRecoveryOperationKind,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    before: PrivateRecoveryOperationImage,
    after: PrivateRecoveryOperationImage,
) -> PrivateRecoveryPostconditionReview:
    """Classify exact, bounded before/after images of one proposed operation.

    Input snapshots do NOT constitute a native file-ID or custody proof. A
    future native operation coordinator must retain all guards and perform
    independent pre/post verification, journaling, persistence qualification,
    expected-revision CAS, and an interruption/recovery protocol. This pure
    function never calls a writer, opens files, retires journals or Notes.
    """
    state = PrivateRecoveryPostconditionState
    if (
        type(kind) is not PrivateRecoveryOperationKind
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
    ):
        return _result(state.INVALID_REQUEST)
    try:
        encoded = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(encoded)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != encoded
            or type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.descriptor_after) is not bytes
        ):
            return _result(state.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
        if not _image_valid(before, len(encoded)) or not _image_valid(
            after, len(encoded)
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
        required_revision = (
            prior.revision
            if kind is PrivateRecoveryOperationKind.STAGE_TO_REGISTRY
            else later.revision
        )
        if expected_revision != required_revision:
            return _result(state.REVISION_MISMATCH_REFUSED)

        pending = PrivateRecoveryOperationImage(
            journal=encoded,
            registry=checked.registry_before,
            descriptor=checked.descriptor_before,
            stage=checked.registry_after,
        )
        descriptor_pending = PrivateRecoveryOperationImage(
            journal=encoded,
            registry=checked.registry_after,
            descriptor=checked.descriptor_before,
            stage=None,
        )
        journal_pending = PrivateRecoveryOperationImage(
            journal=encoded,
            registry=checked.registry_after,
            descriptor=checked.descriptor_after,
            stage=None,
        )
        journal_absent = PrivateRecoveryOperationImage(
            journal=None,
            registry=checked.registry_after,
            descriptor=checked.descriptor_after,
            stage=None,
        )
        checkpoints = {
            PrivateRecoveryOperationKind.STAGE_TO_REGISTRY: (
                pending,
                descriptor_pending,
            ),
            PrivateRecoveryOperationKind.DESCRIPTOR_AFTER_IMAGE: (
                descriptor_pending,
                journal_pending,
            ),
            PrivateRecoveryOperationKind.JOURNAL_RETIREMENT: (
                journal_pending,
                journal_absent,
            ),
        }
        required, expected = checkpoints[kind]
        if before != required:
            return _result(state.PRECONDITION_REFUSED)
        if after == before:
            return _result(state.NO_PROGRESS_PRESERVE)
        if after != expected:
            return _result(state.POSTCONDITION_CONFLICT_PRESERVE)
        if kind is PrivateRecoveryOperationKind.JOURNAL_RETIREMENT:
            return _result(state.JOURNAL_ABSENCE_UNQUALIFIED)
        return _result(state.TRANSITION_OBSERVED_REVIEW_REQUIRED)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)
