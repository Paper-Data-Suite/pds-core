"""Core #238 Slice 3C6: advisory, side-effect-free precondition comparison."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witnesses

ORIGINAL = "0b283e11-b17b-42ac-8c96-79037b1ea4d9"
FORKED = "ea867513-59c5-4cf2-b7d1-a5c9b203c734"
TRANSACTION = "c0bbda1f-41fc-45c8-ab52-94601b2abe9d"


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def required_digest(data: bytes) -> str:
    """Nonoptional content hash for required after-state witness fields."""
    return hashlib.sha256(data).hexdigest()


def principal() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def make_registry(
    owner: inspection.EffectiveOSOwner,
    revision: int,
    bindings: tuple[metadata.PrivateRegistryBinding, ...],
) -> bytes:
    if owner.kind == "windows_token_sid":
        value = metadata.PrivateRegistryOwner("windows_token_sid", owner.value)
    else:
        value = metadata.PrivateRegistryOwner("posix_euid", owner.value)
    return metadata.encode_private_registry(
        metadata.PrivateRegistry(value, revision, bindings)
    )


def build(
    tmp_path: Path,
    *,
    operation: witnesses.PrivateBindingOperation = witnesses.PrivateBindingOperation.FORK_COPY,
) -> tuple[
    intents.PrivateTransactionIntent,
    paired.PrivatePairObservation,
    Path,
    inspection.EffectiveOSOwner,
]:
    owner = principal()
    destination = tmp_path / "destination"
    source = tmp_path / "source"
    old_id = ORIGINAL
    new_id = (
        FORKED if operation is witnesses.PrivateBindingOperation.FORK_COPY else ORIGINAL
    )
    old_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(old_id)
    )
    new_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(new_id)
    )
    before = make_registry(
        owner, 5, (metadata.PrivateRegistryBinding(old_id, 3, str(source)),)
    )
    after_bindings: tuple[metadata.PrivateRegistryBinding, ...]
    if operation is witnesses.PrivateBindingOperation.FORK_COPY:
        after_bindings = (
            metadata.PrivateRegistryBinding(old_id, 3, str(source)),
            metadata.PrivateRegistryBinding(new_id, 1, str(destination)),
        )
    else:
        after_bindings = (metadata.PrivateRegistryBinding(old_id, 4, str(destination)),)
    after = make_registry(owner, 6, after_bindings)
    w = witnesses.PrivateTransactionWitness(
        operation,
        TRANSACTION,
        old_id,
        new_id,
        5,
        6,
        digest(old_descriptor),
        required_digest(new_descriptor),
        digest(before),
        required_digest(after),
    )
    proposal = intents.PrivateTransactionIntent(
        w, old_descriptor, new_descriptor, before, after
    )
    observed = paired.PrivatePairObservation(
        paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED,
        "Synthetic non-authorizing observation",
        5,
        1,
        old_id,
        digest(before),
        digest(old_descriptor),
    )
    return proposal, observed, destination, owner


def test_fork_before_state_matches_without_authorizing(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    result = preconditions.review_binding_preconditions(proposal, observed, path, owner)
    assert (
        result.state
        is preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
    )
    assert "ready" not in result.state.value
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "commit_token")
    assert ORIGINAL not in repr(result)
    assert str(path) not in repr(result)
    assert owner.value not in repr(result)


def test_move_before_state_matches_without_writing(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(
        tmp_path, operation=witnesses.PrivateBindingOperation.REBIND_MOVE
    )
    before = list(tmp_path.iterdir())
    result = preconditions.review_binding_preconditions(proposal, observed, path, owner)
    assert (
        result.state
        is preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
    )
    assert list(tmp_path.iterdir()) == before == []


def test_changed_registry_revision_refused(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    outcome = preconditions.review_binding_preconditions(
        proposal, replace(observed, registry_revision=6), path, owner
    )
    assert outcome.state is preconditions.PrivateBindingPreconditionState.REGISTRY_STALE


def test_changed_registry_digest_refused(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    outcome = preconditions.review_binding_preconditions(
        proposal, replace(observed, registry_sha256="0" * 64), path, owner
    )
    assert outcome.state is preconditions.PrivateBindingPreconditionState.REGISTRY_STALE


def test_wrong_binding_count_refused(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    outcome = preconditions.review_binding_preconditions(
        proposal, replace(observed, registry_binding_count=2), path, owner
    )
    assert outcome.state is preconditions.PrivateBindingPreconditionState.REGISTRY_STALE


def test_changed_descriptor_digest_refused(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    outcome = preconditions.review_binding_preconditions(
        proposal, replace(observed, descriptor_sha256="f" * 64), path, owner
    )
    assert (
        outcome.state is preconditions.PrivateBindingPreconditionState.DESCRIPTOR_STALE
    )


def test_wrong_association_refused(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    outcome = preconditions.review_binding_preconditions(
        proposal, replace(observed, association_id=FORKED), path, owner
    )
    assert (
        outcome.state is preconditions.PrivateBindingPreconditionState.DESCRIPTOR_STALE
    )


def test_wrong_principal_refused(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    changed = inspection.EffectiveOSOwner(owner.kind, "different")
    outcome = preconditions.review_binding_preconditions(
        proposal, observed, path, changed
    )
    assert outcome.state is preconditions.PrivateBindingPreconditionState.OWNER_MISMATCH


def test_cross_platform_principal_refused(tmp_path: Path) -> None:
    proposal, observed, path, _owner = build(tmp_path)
    other = (
        inspection.EffectiveOSOwner("posix_euid", "1000")
        if sys.platform == "win32"
        else inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    )
    assert (
        preconditions.review_binding_preconditions(
            proposal, observed, path, other
        ).state
        is preconditions.PrivateBindingPreconditionState.OWNER_MISMATCH
    )


def test_different_destination_refused(tmp_path: Path) -> None:
    proposal, observed, _path, owner = build(tmp_path)
    different = tmp_path / "another"
    assert (
        preconditions.review_binding_preconditions(
            proposal, observed, different, owner
        ).state
        is preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH
    )


def test_source_root_cannot_be_new_destination(tmp_path: Path) -> None:
    proposal, observed, _path, owner = build(tmp_path)
    assert (
        preconditions.review_binding_preconditions(
            proposal, observed, tmp_path / "source", owner
        ).state
        is preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH
    )


@pytest.mark.parametrize(
    "state",
    [
        x
        for x in paired.PrivatePairObservationState
        if x is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
    ],
)
def test_unreliable_observation_never_matches(
    state: paired.PrivatePairObservationState, tmp_path: Path
) -> None:
    proposal, observed, path, owner = build(tmp_path)
    outcome = preconditions.review_binding_preconditions(
        proposal, replace(observed, state=state), path, owner
    )
    assert (
        outcome.state
        is preconditions.PrivateBindingPreconditionState.OBSERVATION_UNQUALIFIED
    )


def test_relative_destination_refused(tmp_path: Path) -> None:
    proposal, observed, _path, owner = build(tmp_path)
    assert (
        preconditions.review_binding_preconditions(
            proposal, observed, Path("relative"), owner
        ).state
        is preconditions.PrivateBindingPreconditionState.INVALID_REQUEST
    )


def test_invalid_proposal_type_refused(tmp_path: Path) -> None:
    _proposal, observed, path, owner = build(tmp_path)
    outcome = preconditions.review_binding_preconditions(
        "not-an-intent",  # type: ignore[arg-type]
        observed,
        path,
        owner,
    )
    assert (
        outcome.state is preconditions.PrivateBindingPreconditionState.INVALID_REQUEST
    )


def test_initialization_requires_separate_absence_proof(tmp_path: Path) -> None:
    owner = principal()
    path = tmp_path / "destination"
    after_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(FORKED)
    )
    after_registry = make_registry(
        owner, 1, (metadata.PrivateRegistryBinding(FORKED, 1, str(path)),)
    )
    w = witnesses.PrivateTransactionWitness(
        witnesses.PrivateBindingOperation.INITIALIZE,
        TRANSACTION,
        None,
        FORKED,
        0,
        1,
        None,
        required_digest(after_descriptor),
        None,
        required_digest(after_registry),
    )
    proposal = intents.PrivateTransactionIntent(
        w, None, after_descriptor, None, after_registry
    )
    observed = paired.PrivatePairObservation(
        paired.PrivatePairObservationState.MISSING_DESCRIPTOR, "No sidecar"
    )
    assert (
        preconditions.review_binding_preconditions(
            proposal, observed, path, owner
        ).state
        is preconditions.PrivateBindingPreconditionState.MISSING_STATE_REVIEW_REQUIRED
    )


def test_noncanonical_proposed_before_registry_refused(tmp_path: Path) -> None:
    proposal, observed, path, owner = build(tmp_path)
    assert proposal.registry_before is not None
    raw = proposal.registry_before + b" "
    changed_witness = replace(proposal.witness, registry_sha256_before=digest(raw))
    changed = intents.PrivateTransactionIntent(
        changed_witness,
        proposal.descriptor_before,
        proposal.descriptor_after,
        raw,
        proposal.registry_after,
    )
    forged_observation = replace(observed, registry_sha256=digest(raw))
    assert (
        preconditions.review_binding_preconditions(
            changed, forged_observation, path, owner
        ).state
        is preconditions.PrivateBindingPreconditionState.INTENT_REFUSED
    )


def test_no_io_exports_or_permissions(tmp_path: Path) -> None:
    assert not hasattr(preconditions, "write_private_registry")
    assert not hasattr(preconditions, "commit_private_transaction")
    assert not hasattr(preconditions, "authorize_private_storage")
    assert list(tmp_path.iterdir()) == []
