"""Inert typed prepared-stage write description (Core #238 Slice 3G32).

Derive bounded digests and a stage-to-registry operation kind from a canonical
private transaction intent. This module deliberately has NO path, OS, native
handle, lock, guard, callback, writer, mutation or durable-commit API. Even a
matching description is stale immediately and is NEVER a writer permit.

A future operation-owned writer must independently validate the whole canonical
intent and every native precondition inside the SAME continuously held guard.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivatePreparedWriteIntentState(str, Enum):
    DESCRIPTION_ONLY_REVIEW_REQUIRED = "description_only_review_required"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INITIALIZATION_REFUSED = "initialization_refused"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    NONCANONICAL_INTENT_REFUSED = "noncanonical_intent_refused"
    INVALID_REQUEST = "invalid_request"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED: (
        "Canonical prepared-stage fingerprints described; no native guard is held "
        "and no write, replay, commit or retirement is admitted."
    ),
    PrivatePreparedWriteIntentState.OPERATION_NOT_ADMITTED: (
        "Only a prepared stage-to-registry operation can be described."
    ),
    PrivatePreparedWriteIntentState.INITIALIZATION_REFUSED: (
        "First binding requires separate native absence custody and durability."
    ),
    PrivatePreparedWriteIntentState.REVISION_MISMATCH_REFUSED: (
        "Expected protected revision differs from the prepared canonical intent."
    ),
    PrivatePreparedWriteIntentState.NONCANONICAL_INTENT_REFUSED: (
        "Transaction images, witness, or canonical round trip are unqualified."
    ),
    PrivatePreparedWriteIntentState.INVALID_REQUEST: (
        "Prepared write description request has an invalid exact type or value."
    ),
    PrivatePreparedWriteIntentState.IO_ERROR: (
        "Pure canonical intent inspection failed; no execution is authorized."
    ),
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivatePreparedWriteDescription:
    """Non-executable description, never a transferable authorization object.

    Contains no byte images, root paths, file names, OS handles, guard instances,
    supplied callbacks or mutable state. SHA-256 values identify candidate bytes
    only; they are not authentication, freshness, CAS or native custody evidence.
    """

    step: scratch.PrivateScratchWriterStep
    binding_operation: witness.PrivateBindingOperation
    expected_revision: int
    resulting_revision: int
    transaction_id: str = field(repr=False)
    pending_intent_sha256: str = field(repr=False)
    registry_before_sha256: str = field(repr=False)
    staged_registry_sha256: str = field(repr=False)
    descriptor_before_sha256: str = field(repr=False)
    descriptor_after_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "PrivatePreparedWriteDescription(non_authorizing=True)"


@dataclass(frozen=True, slots=True, repr=False)
class PrivatePreparedWriteIntentReview:
    state: PrivatePreparedWriteIntentState
    message: str
    description: PrivatePreparedWriteDescription | None = field(repr=False)

    def __repr__(self) -> str:
        return "PrivatePreparedWriteIntentReview(non_authorizing=True)"


def _result(
    state: PrivatePreparedWriteIntentState,
    description: PrivatePreparedWriteDescription | None = None,
) -> PrivatePreparedWriteIntentReview:
    return PrivatePreparedWriteIntentReview(state, _MESSAGES[state], description)


def describe_private_prepared_stage_write_intent(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
) -> PrivatePreparedWriteIntentReview:
    """Describe EXACT prepared transaction bytes without inspecting any storage.

    No caller path is accepted; this function neither calls a protected reviewer
    nor borrows a prior advisory result. A future writer MUST NOT interpret the
    returned description as evidence that the guarded checkpoint still exists.
    """
    state = PrivatePreparedWriteIntentState
    if (
        type(step) is not scratch.PrivateScratchWriterStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
    ):
        return _result(state.INVALID_REQUEST)
    if step is not scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    try:
        raw = intents.encode_private_transaction_intent(proposed)
        if type(raw) is not bytes or len(raw) > intents.MAX_INTENT_BYTES:
            return _result(state.NONCANONICAL_INTENT_REFUSED)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(state.NONCANONICAL_INTENT_REFUSED)
        recorded = checked.witness
        if (
            type(recorded) is not witness.PrivateTransactionWitness
            or type(recorded.operation) is not witness.PrivateBindingOperation
        ):
            return _result(state.NONCANONICAL_INTENT_REFUSED)
        if recorded.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
        if recorded.operation not in {
            witness.PrivateBindingOperation.REBIND_MOVE,
            witness.PrivateBindingOperation.FORK_COPY,
        }:
            return _result(state.NONCANONICAL_INTENT_REFUSED)
        before = checked.registry_before
        after = checked.registry_after
        old_descriptor = checked.descriptor_before
        new_descriptor = checked.descriptor_after
        if (
            type(before) is not bytes
            or not before
            or type(after) is not bytes
            or not after
            or type(old_descriptor) is not bytes
            or not old_descriptor
            or type(new_descriptor) is not bytes
            or not new_descriptor
            or type(recorded.transaction_id) is not str
            or type(recorded.registry_revision_before) is not int
            or recorded.registry_revision_before < 1
            or type(recorded.registry_revision_after) is not int
            or recorded.registry_revision_after != recorded.registry_revision_before + 1
        ):
            return _result(state.NONCANONICAL_INTENT_REFUSED)
        if expected_revision != recorded.registry_revision_before:
            return _result(state.REVISION_MISMATCH_REFUSED)
        old_hash = hashlib.sha256(before).hexdigest()
        new_hash = hashlib.sha256(after).hexdigest()
        descriptor_before_hash = hashlib.sha256(old_descriptor).hexdigest()
        descriptor_after_hash = hashlib.sha256(new_descriptor).hexdigest()
        if (
            old_hash != recorded.registry_sha256_before
            or new_hash != recorded.registry_sha256_after
            or descriptor_before_hash != recorded.descriptor_sha256_before
            or descriptor_after_hash != recorded.descriptor_sha256_after
        ):
            return _result(state.NONCANONICAL_INTENT_REFUSED)
        return _result(
            state.DESCRIPTION_ONLY_REVIEW_REQUIRED,
            PrivatePreparedWriteDescription(
                step=step,
                binding_operation=recorded.operation,
                expected_revision=expected_revision,
                resulting_revision=recorded.registry_revision_after,
                transaction_id=recorded.transaction_id,
                pending_intent_sha256=hashlib.sha256(raw).hexdigest(),
                registry_before_sha256=old_hash,
                staged_registry_sha256=new_hash,
                descriptor_before_sha256=descriptor_before_hash,
                descriptor_after_sha256=descriptor_after_hash,
            ),
        )
    except (intents.PrivateIntentError, witness.PrivateTransactionError):
        return _result(state.NONCANONICAL_INTENT_REFUSED)
    except KeyboardInterrupt:
        return _result(state.IO_ERROR)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(state.IO_ERROR)
