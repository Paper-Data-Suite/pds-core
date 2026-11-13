"""Pure, non-authorizing binding precondition comparison (#238 Slice 3C6).

Compares a proposed private transaction's before-state to an earlier paired
observation and an alleged owner/workspace path. No I/O, locks, writes, native
identity proof, CAS reservation, human approval or Notes capability occurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateBindingPreconditionState(str, Enum):
    MATCHED_REVIEW_REQUIRED = "matched_review_required"
    INVALID_REQUEST = "invalid_request"
    OBSERVATION_UNQUALIFIED = "observation_unqualified"
    MISSING_STATE_REVIEW_REQUIRED = "missing_state_review_required"
    REGISTRY_STALE = "registry_stale"
    DESCRIPTOR_STALE = "descriptor_stale"
    OWNER_MISMATCH = "owner_mismatch"
    WORKSPACE_MISMATCH = "workspace_mismatch"
    INTENT_REFUSED = "intent_refused"


_MESSAGES = {
    PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED: "Observed before-state agrees with a proposal; no write is authorized.",
    PrivateBindingPreconditionState.INVALID_REQUEST: "Invalid private-binding precondition request.",
    PrivateBindingPreconditionState.OBSERVATION_UNQUALIFIED: "Paired metadata observation was not completed reliably.",
    PrivateBindingPreconditionState.MISSING_STATE_REVIEW_REQUIRED: "Missing before-state needs independent guarded review.",
    PrivateBindingPreconditionState.REGISTRY_STALE: "Registry observation differs from the proposed before-state.",
    PrivateBindingPreconditionState.DESCRIPTOR_STALE: "Workspace descriptor differs from the proposed before-state.",
    PrivateBindingPreconditionState.OWNER_MISMATCH: "Proposed registry owner differs from the supplied owner observation.",
    PrivateBindingPreconditionState.WORKSPACE_MISMATCH: "Requested workspace is not the proposal's exact destination.",
    PrivateBindingPreconditionState.INTENT_REFUSED: "Proposed transition metadata is not canonically valid.",
}


@dataclass(frozen=True, slots=True)
class PrivateBindingPreconditionReview:
    """Sanitized advisory classification. Never a token or currentness proof."""

    state: PrivateBindingPreconditionState
    message: str


def _result(state: PrivateBindingPreconditionState) -> PrivateBindingPreconditionReview:
    return PrivateBindingPreconditionReview(state, _MESSAGES[state])


def review_binding_preconditions(
    proposed: intents.PrivateTransactionIntent,
    observed: paired.PrivatePairObservation,
    workspace_root: Path,
    owner_observation: inspection.EffectiveOSOwner,
) -> PrivateBindingPreconditionReview:
    """Compare exact prior bytes without I/O or authorization.

    This is not an atomic cross-tree snapshot, binding lookup or CAS check.
    The owner_observation is a value supplied by the caller, NOT independently
    re-read from the current OS token/effective UID by this pure function.
    Even MATCHED_REVIEW_REQUIRED cannot authorize journaling or a commit.
    """
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or type(observed) is not paired.PrivatePairObservation
        or type(owner_observation) is not inspection.EffectiveOSOwner
        or not descriptor._valid_root(workspace_root)
    ):
        return _result(PrivateBindingPreconditionState.INVALID_REQUEST)

    # Re-encode and decode the entire proposal rather than trusting arbitrary
    # mutable/raw fields on an object constructed outside the approved codec.
    try:
        original_bytes = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(original_bytes)
        if intents.encode_private_transaction_intent(checked) != original_bytes:
            return _result(PrivateBindingPreconditionState.INTENT_REFUSED)
        old_registry = (
            metadata.decode_private_registry(checked.registry_before)
            if checked.registry_before is not None
            else None
        )
        new_registry = metadata.decode_private_registry(checked.registry_after)
        if metadata.encode_private_registry(new_registry) != checked.registry_after:
            return _result(PrivateBindingPreconditionState.INTENT_REFUSED)
        if old_registry is not None and (
            metadata.encode_private_registry(old_registry) != checked.registry_before
        ):
            return _result(PrivateBindingPreconditionState.INTENT_REFUSED)
        old_descriptor = (
            metadata.decode_association_descriptor(checked.descriptor_before)
            if checked.descriptor_before is not None
            else None
        )
        if old_descriptor is not None and (
            metadata.encode_association_descriptor(old_descriptor)
            != checked.descriptor_before
        ):
            return _result(PrivateBindingPreconditionState.INTENT_REFUSED)
        new_descriptor = metadata.decode_association_descriptor(
            checked.descriptor_after
        )
        if (
            metadata.encode_association_descriptor(new_descriptor)
            != checked.descriptor_after
        ):
            return _result(PrivateBindingPreconditionState.INTENT_REFUSED)
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        ValueError,
        TypeError,
    ):
        return _result(PrivateBindingPreconditionState.INTENT_REFUSED)

    # A paired snapshot deliberately omits before-state hashes for missing
    # documents. Initialization cannot be approved or inferred from its
    # missing-state classification. A later guarded writer must prove absence.
    if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
        return _result(PrivateBindingPreconditionState.MISSING_STATE_REVIEW_REQUIRED)
    if observed.state is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED:
        return _result(PrivateBindingPreconditionState.OBSERVATION_UNQUALIFIED)
    if old_registry is None:
        return _result(PrivateBindingPreconditionState.INTENT_REFUSED)
    if (
        new_registry.owner.kind != owner_observation.kind
        or new_registry.owner.value != owner_observation.value
        or old_registry.owner != new_registry.owner
    ):
        return _result(PrivateBindingPreconditionState.OWNER_MISMATCH)
    if (
        observed.registry_revision != checked.witness.registry_revision_before
        or observed.registry_binding_count != len(old_registry.bindings)
        or observed.registry_sha256 != checked.witness.registry_sha256_before
    ):
        return _result(PrivateBindingPreconditionState.REGISTRY_STALE)
    if (
        observed.association_id != checked.witness.association_before
        or observed.descriptor_sha256 != checked.witness.descriptor_sha256_before
    ):
        return _result(PrivateBindingPreconditionState.DESCRIPTOR_STALE)
    matching = [
        item
        for item in new_registry.bindings
        if item.association_id == checked.witness.association_after
    ]
    if len(matching) != 1 or matching[0].accepted_root != str(workspace_root):
        return _result(PrivateBindingPreconditionState.WORKSPACE_MISMATCH)
    if checked.witness.operation is witness.PrivateBindingOperation.REBIND_MOVE:
        prior = [
            item
            for item in old_registry.bindings
            if item.association_id == checked.witness.association_before
        ]
        if len(prior) != 1 or prior[0].accepted_root == str(workspace_root):
            return _result(PrivateBindingPreconditionState.WORKSPACE_MISMATCH)
    return _result(PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED)
