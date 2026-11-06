"""Production write-admission barrier for Core #238 Slice 3G35.

The 3G34 canonical two-root replacement qualifies *disposable scratch only*.
The 3G33 native evidence review is advisory after its guard is released.  No
result of either function may serve as production mutation authority.

This module maps one strict 3G32 candidate review to a permanent, explicit
PRODUCTION_BLOCKED state and enumerates evidence a future operation-owned
production writer must establish *inside its own continuously held guard*.
It accepts no caller paths, filesystem handles, ACL claims, review certificates,
callbacks, boolean bypass flags or write intents as execution capabilities.
Nothing here opens, creates, replaces, removes, locks, fsyncs or commits files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents


class PrivateProductionWriteBarrierState(str, Enum):
    PRODUCTION_BLOCKED = "production_blocked"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INITIALIZATION_REFUSED = "initialization_refused"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    NONCANONICAL_INTENT_REFUSED = "noncanonical_intent_refused"
    DESCRIPTION_UNQUALIFIED = "description_unqualified"


class PrivateProductionWriteRequirement(str, Enum):
    EFFECTIVE_OS_OWNER_AND_PRIVATE_ACL = "effective_os_owner_and_private_acl"
    WORKSPACE_DESCRIPTOR_BINDING = "workspace_descriptor_binding"
    TWO_ROOT_NATIVE_PARENT_CUSTODY = "two_root_native_parent_custody"
    EXCLUSIVE_OPERATION_OWNED_GUARD = "exclusive_operation_owned_guard"
    CANONICAL_INTENT_RECHECK_IN_GUARD = "canonical_intent_recheck_in_guard"
    EXACT_REGISTRY_JOURNAL_STAGE_IMAGES = "exact_registry_journal_stage_images"
    NATIVE_REPLACE_SHARING_AND_POSTIMAGE = "native_replace_sharing_and_postimage"
    DIRECTORY_DURABILITY_AND_CRASH_RECOVERY = "directory_durability_and_crash_recovery"
    RECOVERY_AND_JOURNAL_RETIREMENT_PROTOCOL = (
        "recovery_and_journal_retirement_protocol"
    )


# Each item requires production-native proof, not a synthetic or previous review.
# These are required qualifications, not booleans that callers can mark true.
_REQUIRED: tuple[PrivateProductionWriteRequirement, ...] = tuple(
    PrivateProductionWriteRequirement
)

_MESSAGES = {
    PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED: (
        "Production recovery mutation is disabled. Canonical intent description "
        "does not establish current native custody, atomicity or durability."
    ),
    PrivateProductionWriteBarrierState.INVALID_REQUEST: (
        "Invalid production mutation boundary request."
    ),
    PrivateProductionWriteBarrierState.OPERATION_NOT_ADMITTED: (
        "Only an existing prepared stage-to-registry step is in scope."
    ),
    PrivateProductionWriteBarrierState.INITIALIZATION_REFUSED: (
        "Initialization requires a distinct native absence and persistence protocol."
    ),
    PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED: (
        "The proposed protected registry revision does not match."
    ),
    PrivateProductionWriteBarrierState.NONCANONICAL_INTENT_REFUSED: (
        "Private transaction bytes or witness are unqualified."
    ),
    PrivateProductionWriteBarrierState.DESCRIPTION_UNQUALIFIED: (
        "The inert prepared write description could not be qualified."
    ),
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateProductionWriteBarrierReview:
    """Only a sanitized blocked decision and fixed required-evidence taxonomy.

    Neither this object nor its contents are a capability or proof of native
    ownership. There is deliberately no positive / ready / approved state.
    """

    state: PrivateProductionWriteBarrierState
    message: str
    unqualified_requirements: tuple[PrivateProductionWriteRequirement, ...] = field(
        repr=False
    )

    def __repr__(self) -> str:
        return "PrivateProductionWriteBarrierReview(non_authorizing=True)"


def _result(
    state: PrivateProductionWriteBarrierState,
) -> PrivateProductionWriteBarrierReview:
    return PrivateProductionWriteBarrierReview(state, _MESSAGES[state], _REQUIRED)


_TRANSLATION = {
    prepared.PrivatePreparedWriteIntentState.INVALID_REQUEST: PrivateProductionWriteBarrierState.INVALID_REQUEST,
    prepared.PrivatePreparedWriteIntentState.OPERATION_NOT_ADMITTED: PrivateProductionWriteBarrierState.OPERATION_NOT_ADMITTED,
    prepared.PrivatePreparedWriteIntentState.INITIALIZATION_REFUSED: PrivateProductionWriteBarrierState.INITIALIZATION_REFUSED,
    prepared.PrivatePreparedWriteIntentState.REVISION_MISMATCH_REFUSED: PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED,
    prepared.PrivatePreparedWriteIntentState.NONCANONICAL_INTENT_REFUSED: PrivateProductionWriteBarrierState.NONCANONICAL_INTENT_REFUSED,
    prepared.PrivatePreparedWriteIntentState.IO_ERROR: PrivateProductionWriteBarrierState.DESCRIPTION_UNQUALIFIED,
}


def review_private_production_write_barrier(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
) -> PrivateProductionWriteBarrierReview:
    """Validate a bounded description and refuse production mutation.

    This function is pure with respect to the filesystem. It intentionally does
    NOT accept stale 3G33/3G34 results, user claims of satisfied evidence, or a
    pre-existing guard. A future writer must own and qualify the entire native
    scope; it cannot reuse this function's returned review as authorization.
    """
    state = PrivateProductionWriteBarrierState
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
        finding = prepared.describe_private_prepared_stage_write_intent(
            step, expected_revision, proposed
        )
        if type(finding) is not prepared.PrivatePreparedWriteIntentReview:
            return _result(state.DESCRIPTION_UNQUALIFIED)
        if (
            finding.state
            is prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
        ):
            if (
                type(finding.description)
                is not prepared.PrivatePreparedWriteDescription
            ):
                return _result(state.DESCRIPTION_UNQUALIFIED)
            description = finding.description
            if (
                description.step is not step
                or description.expected_revision != expected_revision
                or description.resulting_revision != expected_revision + 1
            ):
                return _result(state.DESCRIPTION_UNQUALIFIED)
            # Even a qualified 3G32 description never establishes native proof.
            return _result(state.PRODUCTION_BLOCKED)
        return _result(_TRANSLATION.get(finding.state, state.DESCRIPTION_UNQUALIFIED))
    except (
        KeyboardInterrupt,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.DESCRIPTION_UNQUALIFIED)
