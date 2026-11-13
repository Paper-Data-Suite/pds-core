"""Core #238 3G3: pure stage-consumption crash-window contract (synthetic)."""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_registry_stage_transition as lifecycle
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

_A = "6fb32a62-83e2-43f6-9823-687801593c8b"
_B = "d2f5733a-e471-4865-a070-e943ad20863f"
_TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
_ROOT_A = "/synthetic_workspace_a"
_ROOT_B = "/synthetic_workspace_b"
State = lifecycle.PrivateRegistryStageTransitionState


def _sha(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _descriptor(association: str) -> bytes:
    return metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(association)
    )


def _registry(
    revision: int, bindings: tuple[metadata.PrivateRegistryBinding, ...]
) -> bytes:
    return metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner("posix_euid", "1000"), revision, bindings
        )
    )


def _binding(
    association: str, root: str, revision: int = 1
) -> metadata.PrivateRegistryBinding:
    return metadata.PrivateRegistryBinding(association, revision, root)


def _proposal(
    operation: witness.PrivateBindingOperation,
) -> intents.PrivateTransactionIntent:
    before_registry: bytes | None
    before_descriptor: bytes | None
    after_registry: bytes
    after_descriptor: bytes
    before_revision: int
    association_before: str | None
    association_after: str
    if operation is witness.PrivateBindingOperation.INITIALIZE:
        before_registry = None
        before_descriptor = None
        after_registry = _registry(1, (_binding(_B, _ROOT_B),))
        after_descriptor = _descriptor(_B)
        before_revision = 0
        association_before = None
        association_after = _B
    elif operation is witness.PrivateBindingOperation.REBIND_MOVE:
        before_registry = _registry(2, (_binding(_A, _ROOT_A),))
        after_registry = _registry(3, (_binding(_A, _ROOT_B, 2),))
        before_descriptor = after_descriptor = _descriptor(_A)
        before_revision = 2
        association_before = association_after = _A
    else:
        before_registry = _registry(2, (_binding(_A, _ROOT_A),))
        after_registry = _registry(3, (_binding(_A, _ROOT_A), _binding(_B, _ROOT_B)))
        before_descriptor = _descriptor(_A)
        after_descriptor = _descriptor(_B)
        before_revision = 2
        association_before = _A
        association_after = _B
    checked_witness = witness.PrivateTransactionWitness(
        operation=operation,
        transaction_id=_TX,
        association_before=association_before,
        association_after=association_after,
        registry_revision_before=before_revision,
        registry_revision_after=before_revision + 1,
        descriptor_sha256_before=_sha(before_descriptor),
        descriptor_sha256_after=_sha(after_descriptor) or "",
        registry_sha256_before=_sha(before_registry),
        registry_sha256_after=_sha(after_registry) or "",
    )
    return intents.PrivateTransactionIntent(
        checked_witness,
        before_descriptor,
        after_descriptor,
        before_registry,
        after_registry,
    )


def _call(
    proposal: intents.PrivateTransactionIntent,
    *,
    reg_after: bool = False,
    desc_after: bool = False,
    stage_present: bool = True,
) -> lifecycle.PrivateRegistryStageTransitionReview:
    return lifecycle.classify_private_registry_stage_transition(
        proposal,
        observed_journal=intents.encode_private_transaction_intent(proposal),
        observed_registry=(
            proposal.registry_after if reg_after else proposal.registry_before
        ),
        observed_descriptor=(
            proposal.descriptor_after if desc_after else proposal.descriptor_before
        ),
        observed_stage=proposal.registry_after if stage_present else None,
    )


@pytest.mark.parametrize(
    ("reg_after", "desc_after", "stage_present", "expected"),
    [
        (False, False, True, State.PRE_REPLACE_REVIEW_REQUIRED),
        (False, False, False, State.STAGE_MISSING_BEFORE_REFUSED),
        (True, False, True, State.REGISTRY_AFTER_STAGE_REMAINS_REVIEW_REQUIRED),
        (True, False, False, State.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED),
        (False, True, True, State.DESCRIPTOR_AFTER_REGISTRY_PENDING_REVIEW_REQUIRED),
        (False, True, False, State.STAGE_MISSING_PARTIAL_REFUSED),
        (True, True, True, State.BOTH_AFTER_STAGE_REMAINS_REVIEW_REQUIRED),
        (True, True, False, State.BOTH_AFTER_RETIREMENT_REVIEW_REQUIRED),
    ],
)
def test_fork_copy_stage_lifecycle_matrix(
    reg_after: bool, desc_after: bool, stage_present: bool, expected: State
) -> None:
    assert (
        _call(
            _proposal(witness.PrivateBindingOperation.FORK_COPY),
            reg_after=reg_after,
            desc_after=desc_after,
            stage_present=stage_present,
        ).state
        is expected
    )


@pytest.mark.parametrize(
    ("reg_after", "stage_present", "expected"),
    [
        (False, True, State.PRE_REPLACE_REVIEW_REQUIRED),
        (False, False, State.STAGE_MISSING_BEFORE_REFUSED),
        (True, True, State.BOTH_AFTER_STAGE_REMAINS_REVIEW_REQUIRED),
        (True, False, State.BOTH_AFTER_RETIREMENT_REVIEW_REQUIRED),
    ],
)
def test_rebind_unchanged_descriptor_does_not_fabricate_partial_change(
    reg_after: bool, stage_present: bool, expected: State
) -> None:
    p = _proposal(witness.PrivateBindingOperation.REBIND_MOVE)
    assert p.descriptor_before == p.descriptor_after
    assert _call(p, reg_after=reg_after, stage_present=stage_present).state is expected


def test_initialization_requires_independent_protocol() -> None:
    proposal = _proposal(witness.PrivateBindingOperation.INITIALIZE)
    assert _call(proposal).state is State.INITIALIZATION_REFUSED


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_mismatched_canonical_journal_refused(missing: bool) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    raw = None if missing else b"not-the-canonical-journal"
    result = lifecycle.classify_private_registry_stage_transition(
        proposal,
        observed_journal=raw,
        observed_registry=proposal.registry_before,
        observed_descriptor=proposal.descriptor_before,
        observed_stage=proposal.registry_after,
    )
    assert result.state is State.JOURNAL_REFUSED


@pytest.mark.parametrize(
    "invalid",
    [b"bad-stage", b"", b"x" * (metadata.MAX_REGISTRY_BYTES + 1)],
    ids=("noncanonical", "empty", "oversized"),
)
def test_invalid_stage_never_reports_success(invalid: bytes) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    result = lifecycle.classify_private_registry_stage_transition(
        proposal,
        observed_journal=intents.encode_private_transaction_intent(proposal),
        observed_registry=proposal.registry_before,
        observed_descriptor=proposal.descriptor_before,
        observed_stage=invalid,
    )
    assert result.state in {
        State.STAGE_MISMATCH_REFUSED,
        State.OBSERVATION_UNQUALIFIED,
    }


@pytest.mark.parametrize("image", ["registry", "descriptor"])
def test_foreign_metadata_refused(image: str) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    registry = b"foreign" if image == "registry" else proposal.registry_before
    descriptor = b"foreign" if image == "descriptor" else proposal.descriptor_before
    result = lifecycle.classify_private_registry_stage_transition(
        proposal,
        observed_journal=intents.encode_private_transaction_intent(proposal),
        observed_registry=registry,
        observed_descriptor=descriptor,
        observed_stage=proposal.registry_after,
    )
    assert result.state is State.FOREIGN_METADATA_REFUSED


@pytest.mark.parametrize("image", ["registry", "descriptor", "stage", "journal"])
def test_invalid_observation_types_refused(image: str) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    kwargs: dict[str, object] = {
        "observed_journal": intents.encode_private_transaction_intent(proposal),
        "observed_registry": proposal.registry_before,
        "observed_descriptor": proposal.descriptor_before,
        "observed_stage": proposal.registry_after,
    }
    kwargs["observed_" + image] = bytearray(b"forged")
    result = lifecycle.classify_private_registry_stage_transition(
        proposal,
        observed_journal=cast(bytes | None, kwargs["observed_journal"]),
        observed_registry=cast(bytes | None, kwargs["observed_registry"]),
        observed_descriptor=cast(bytes | None, kwargs["observed_descriptor"]),
        observed_stage=cast(bytes | None, kwargs["observed_stage"]),
    )
    assert result.state is State.OBSERVATION_UNQUALIFIED


def test_equal_bytearray_journal_is_not_accepted_as_canonical_bytes() -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    raw = bytearray(intents.encode_private_transaction_intent(proposal))
    result = lifecycle.classify_private_registry_stage_transition(
        proposal,
        observed_journal=cast(bytes, raw),
        observed_registry=proposal.registry_before,
        observed_descriptor=proposal.descriptor_before,
        observed_stage=proposal.registry_after,
    )
    assert result.state is State.OBSERVATION_UNQUALIFIED


def test_rejects_tampered_frozen_intent() -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(proposal, "registry_after", b"forged")
    result = lifecycle.classify_private_registry_stage_transition(
        proposal,
        observed_journal=b"synthetic",
        observed_registry=proposal.registry_before,
        observed_descriptor=proposal.descriptor_before,
        observed_stage=proposal.registry_after,
    )
    assert result.state is State.INTENT_REFUSED


def test_invalid_proposal_object_refused() -> None:
    result = lifecycle.classify_private_registry_stage_transition(
        cast(intents.PrivateTransactionIntent, object()),
        observed_journal=b"synthetic",
        observed_registry=b"registry",
        observed_descriptor=b"descriptor",
        observed_stage=b"stage",
    )
    assert result.state is State.INTENT_REFUSED


def test_no_paths_no_write_tokens_and_capabilities_unchanged(tmp_path: Path) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    before = tuple(tmp_path.iterdir())
    result = _call(proposal, stage_present=False, reg_after=True)
    assert tuple(tmp_path.iterdir()) == before
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.PRE_REPLACE_REVIEW_REQUIRED)
    for private in (_TX, _A, _B, _ROOT_A, _ROOT_B, "1000"):
        assert private not in result.message and private not in repr(result)
    for name in ("path", "handle", "image", "commit_token", "authorized", "apply"):
        assert not hasattr(result, name)
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for name in ("replace_registry", "commit", "replay", "retire_journal", "write"):
        assert not hasattr(lifecycle, name)
