"""Pure registry-stage consumption checkpoint for Core #238 Slice 3G3.

A prepared after-image stage may disappear during a future native atomic
replacement of the live registry. The earlier 3G2 exclusive-pair reader only
covers the state *before* that operation. This classifier distinguishes the
possible interruption windows without inferring safety, durable persistence,
transaction success, or permission to mutate any file.

Observations are supplied bytes, not native attestations. In particular,
``observed_stage=None`` does NOT prove protected filesystem absence. A future
native, lock-holding reader must independently establish the namespace,
principal, exact current bytes, permissions and crash-durability boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pds_core import _teacher_private_journal_crash_checkpoint as checkpoint
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRegistryStageTransitionState(str, Enum):
    """All outcomes require independent review; none is a write token."""

    PRE_REPLACE_REVIEW_REQUIRED = "pre_replace_review_required"
    REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED = (
        "registry_after_descriptor_pending_review_required"
    )
    REGISTRY_AFTER_STAGE_REMAINS_REVIEW_REQUIRED = (
        "registry_after_stage_remains_review_required"
    )
    DESCRIPTOR_AFTER_REGISTRY_PENDING_REVIEW_REQUIRED = (
        "descriptor_after_registry_pending_review_required"
    )
    BOTH_AFTER_RETIREMENT_REVIEW_REQUIRED = "both_after_retirement_review_required"
    BOTH_AFTER_STAGE_REMAINS_REVIEW_REQUIRED = (
        "both_after_stage_remains_review_required"
    )
    INTENT_REFUSED = "intent_refused"
    INITIALIZATION_REFUSED = "initialization_refused"
    JOURNAL_REFUSED = "journal_refused"
    OBSERVATION_UNQUALIFIED = "observation_unqualified"
    STAGE_MISMATCH_REFUSED = "stage_mismatch_refused"
    STAGE_MISSING_BEFORE_REFUSED = "stage_missing_before_refused"
    STAGE_MISSING_PARTIAL_REFUSED = "stage_missing_partial_refused"
    FOREIGN_METADATA_REFUSED = "foreign_metadata_refused"


_MESSAGES = {
    PrivateRegistryStageTransitionState.PRE_REPLACE_REVIEW_REQUIRED: "Exact prepared before-state supplied; native registry replacement not authorized.",
    PrivateRegistryStageTransitionState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED: "Registry after-image supplied without stage; descriptor completion requires recovery review.",
    PrivateRegistryStageTransitionState.REGISTRY_AFTER_STAGE_REMAINS_REVIEW_REQUIRED: "Registry after-image and retained stage supplied; incomplete stage lifecycle requires review.",
    PrivateRegistryStageTransitionState.DESCRIPTOR_AFTER_REGISTRY_PENDING_REVIEW_REQUIRED: "Descriptor after-image precedes registry after-image; interruption review required.",
    PrivateRegistryStageTransitionState.BOTH_AFTER_RETIREMENT_REVIEW_REQUIRED: "Both after-images and missing stage supplied; journal retirement and durability require review.",
    PrivateRegistryStageTransitionState.BOTH_AFTER_STAGE_REMAINS_REVIEW_REQUIRED: "Both after-images and retained stage supplied; stage lifecycle review required.",
    PrivateRegistryStageTransitionState.INTENT_REFUSED: "Private registry-stage transition intent is invalid.",
    PrivateRegistryStageTransitionState.INITIALIZATION_REFUSED: "First binding requires a separate guarded absence protocol.",
    PrivateRegistryStageTransitionState.JOURNAL_REFUSED: "Canonical pending journal image was not supplied.",
    PrivateRegistryStageTransitionState.OBSERVATION_UNQUALIFIED: "Registry-stage transition observations are unqualified.",
    PrivateRegistryStageTransitionState.STAGE_MISMATCH_REFUSED: "Stage does not match the intended exact registry after-image.",
    PrivateRegistryStageTransitionState.STAGE_MISSING_BEFORE_REFUSED: "Registry remains before-state but stage is missing; preserve evidence.",
    PrivateRegistryStageTransitionState.STAGE_MISSING_PARTIAL_REFUSED: "Descriptor changed but registry did not, and stage is missing; preserve evidence.",
    PrivateRegistryStageTransitionState.FOREIGN_METADATA_REFUSED: "Supplied metadata is unrelated to the intended transition.",
}


@dataclass(frozen=True, slots=True)
class PrivateRegistryStageTransitionReview:
    """Bounded advisory result, intentionally without paths, bytes or handles."""

    state: PrivateRegistryStageTransitionState
    message: str


def _result(
    state: PrivateRegistryStageTransitionState,
) -> PrivateRegistryStageTransitionReview:
    return PrivateRegistryStageTransitionReview(state, _MESSAGES[state])


def _observation(raw: object, maximum: int) -> bool:
    return type(raw) is bytes and 0 < len(raw) <= maximum


def classify_private_registry_stage_transition(
    proposed: intents.PrivateTransactionIntent,
    *,
    observed_journal: bytes | None,
    observed_registry: bytes | None,
    observed_descriptor: bytes | None,
    observed_stage: bytes | None,
) -> PrivateRegistryStageTransitionReview:
    """Classify supplied exact bytes before/after prospective stage consumption.

    This is a PURE classification of caller-supplied evidence. None of the
    results grants authority to rename, overwrite, replay, retire a journal,
    claim durable success, initialize a binding, or open Notes. A later native
    reader must prove whether an absent stage actually was absent.
    """
    if type(proposed) is not intents.PrivateTransactionIntent:
        return _result(PrivateRegistryStageTransitionState.INTENT_REFUSED)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(PrivateRegistryStageTransitionState.INTENT_REFUSED)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(PrivateRegistryStageTransitionState.INITIALIZATION_REFUSED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(PrivateRegistryStageTransitionState.INTENT_REFUSED)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivateRegistryStageTransitionState.INTENT_REFUSED)

    if observed_journal is not None and not _observation(
        observed_journal, intents.MAX_INTENT_BYTES
    ):
        return _result(PrivateRegistryStageTransitionState.OBSERVATION_UNQUALIFIED)
    if observed_journal is None or observed_journal != canonical:
        return _result(PrivateRegistryStageTransitionState.JOURNAL_REFUSED)
    if not _observation(
        observed_registry, metadata.MAX_REGISTRY_BYTES
    ) or not _observation(observed_descriptor, metadata.MAX_ASSOCIATION_BYTES):
        return _result(PrivateRegistryStageTransitionState.OBSERVATION_UNQUALIFIED)
    if observed_stage is not None:
        if not _observation(observed_stage, metadata.MAX_REGISTRY_BYTES):
            return _result(PrivateRegistryStageTransitionState.OBSERVATION_UNQUALIFIED)
        if observed_stage != checked.registry_after:
            return _result(PrivateRegistryStageTransitionState.STAGE_MISMATCH_REFUSED)

    classified = checkpoint.classify_private_journal_crash_checkpoint(
        checked,
        observed_journal=canonical,
        observed_registry=observed_registry,
        observed_descriptor=observed_descriptor,
    ).state
    state = checkpoint.PrivateJournalCrashCheckpointState
    result = PrivateRegistryStageTransitionState
    stage_present = observed_stage is not None
    if classified is state.JOURNAL_BEFORE_REVIEW_REQUIRED:
        return _result(
            result.PRE_REPLACE_REVIEW_REQUIRED
            if stage_present
            else result.STAGE_MISSING_BEFORE_REFUSED
        )
    if classified is state.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED:
        return _result(
            result.DESCRIPTOR_AFTER_REGISTRY_PENDING_REVIEW_REQUIRED
            if stage_present
            else result.STAGE_MISSING_PARTIAL_REFUSED
        )
    if classified is state.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED:
        return _result(
            result.REGISTRY_AFTER_STAGE_REMAINS_REVIEW_REQUIRED
            if stage_present
            else result.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED
        )
    if classified is state.JOURNAL_AFTER_REVIEW_REQUIRED:
        return _result(
            result.BOTH_AFTER_STAGE_REMAINS_REVIEW_REQUIRED
            if stage_present
            else result.BOTH_AFTER_RETIREMENT_REVIEW_REQUIRED
        )
    if classified in {state.INTENT_REFUSED, state.JOURNAL_IMAGE_REFUSED}:
        return _result(result.INTENT_REFUSED)
    if classified is state.OBSERVATION_UNQUALIFIED:
        return _result(result.OBSERVATION_UNQUALIFIED)
    return _result(result.FOREIGN_METADATA_REFUSED)
