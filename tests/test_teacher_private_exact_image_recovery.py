"""Core #238 Slice 3E2: exact-byte crash-image triage, never write authority."""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pds_core import _teacher_private_exact_image_recovery as recovery
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

_A = "6fb32a62-83e2-43f6-9823-687801593c8b"
_B = "d2f5733a-e471-4865-a070-e943ad20863f"
_TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
_ROOT_A = "/synthetic_workspace_a"
_ROOT_B = "/synthetic_workspace_b"


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
    before_reg: bytes | None
    before_desc: bytes | None
    after_reg: bytes
    after_desc: bytes
    before_revision: int
    association_before: str | None
    association_after: str
    if operation is witness.PrivateBindingOperation.INITIALIZE:
        before_reg = None
        before_desc = None
        after_reg = _registry(1, (_binding(_B, _ROOT_B),))
        after_desc = _descriptor(_B)
        before_revision = 0
        association_before = None
        association_after = _B
    elif operation is witness.PrivateBindingOperation.REBIND_MOVE:
        before_reg = _registry(2, (_binding(_A, _ROOT_A),))
        after_reg = _registry(3, (_binding(_A, _ROOT_B, 2),))
        before_desc = after_desc = _descriptor(_A)
        before_revision = 2
        association_before = association_after = _A
    else:
        before_reg = _registry(2, (_binding(_A, _ROOT_A),))
        after_reg = _registry(3, (_binding(_A, _ROOT_A), _binding(_B, _ROOT_B)))
        before_desc = _descriptor(_A)
        after_desc = _descriptor(_B)
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
        descriptor_sha256_before=_sha(before_desc),
        descriptor_sha256_after=_sha(after_desc) or "",
        registry_sha256_before=_sha(before_reg),
        registry_sha256_after=_sha(after_reg) or "",
    )
    return intents.PrivateTransactionIntent(
        checked_witness, before_desc, after_desc, before_reg, after_reg
    )


@pytest.mark.parametrize(
    "operation",
    [
        witness.PrivateBindingOperation.FORK_COPY,
        witness.PrivateBindingOperation.INITIALIZE,
    ],
)
@pytest.mark.parametrize(
    ("reg_after", "desc_after", "expected"),
    [
        (
            False,
            False,
            recovery.PrivateExactImageRecoveryState.BEFORE_IMAGES_REVIEW_REQUIRED,
        ),
        (
            True,
            False,
            recovery.PrivateExactImageRecoveryState.REGISTRY_ONLY_REVIEW_REQUIRED,
        ),
        (
            False,
            True,
            recovery.PrivateExactImageRecoveryState.DESCRIPTOR_ONLY_REVIEW_REQUIRED,
        ),
        (
            True,
            True,
            recovery.PrivateExactImageRecoveryState.AFTER_IMAGES_REVIEW_REQUIRED,
        ),
    ],
)
def test_exact_interruption_image_matrix(
    operation: witness.PrivateBindingOperation,
    reg_after: bool,
    desc_after: bool,
    expected: recovery.PrivateExactImageRecoveryState,
) -> None:
    proposal = _proposal(operation)
    reg = proposal.registry_after if reg_after else proposal.registry_before
    desc = proposal.descriptor_after if desc_after else proposal.descriptor_before
    actual = recovery.classify_private_exact_image_recovery(
        proposal, observed_registry=reg, observed_descriptor=desc
    )
    assert actual.state is expected
    assert "synthetic_workspace" not in repr(actual)
    assert _TX not in repr(actual)
    assert _A not in repr(actual)
    assert "1000" not in repr(actual)


@pytest.mark.parametrize(
    ("reg_after", "expected"),
    [
        (False, recovery.PrivateExactImageRecoveryState.BEFORE_IMAGES_REVIEW_REQUIRED),
        (True, recovery.PrivateExactImageRecoveryState.AFTER_IMAGES_REVIEW_REQUIRED),
    ],
)
def test_rebind_descriptor_is_identical_not_a_partial_update(
    reg_after: bool, expected: recovery.PrivateExactImageRecoveryState
) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.REBIND_MOVE)
    assert proposal.descriptor_before == proposal.descriptor_after
    result = recovery.classify_private_exact_image_recovery(
        proposal,
        observed_registry=(
            proposal.registry_after if reg_after else proposal.registry_before
        ),
        observed_descriptor=proposal.descriptor_before,
    )
    assert result.state is expected


@pytest.mark.parametrize("operation", list(witness.PrivateBindingOperation))
@pytest.mark.parametrize("changed", ["registry", "descriptor", "both"])
def test_foreign_or_concurrent_metadata_refuses(
    operation: witness.PrivateBindingOperation, changed: str
) -> None:
    proposal = _proposal(operation)
    reg = proposal.registry_before
    desc = proposal.descriptor_before
    # Content is unrelated, rather than merely a hash claimed by the caller.
    if changed in ("registry", "both"):
        reg = b"foreign-registry-data"
    if changed in ("descriptor", "both"):
        desc = b"foreign-descriptor-data"
    assert (
        recovery.classify_private_exact_image_recovery(
            proposal, observed_registry=reg, observed_descriptor=desc
        ).state
        is recovery.PrivateExactImageRecoveryState.FOREIGN_IMAGE_REFUSED
    )


@pytest.mark.parametrize(
    ("registry", "descriptor"),
    [
        (b"", b""),
        (None, b""),
        (b"", None),
    ],
)
def test_absent_is_not_empty_bytes(
    registry: bytes | None, descriptor: bytes | None
) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.INITIALIZE)
    assert (
        recovery.classify_private_exact_image_recovery(
            proposal, observed_registry=registry, observed_descriptor=descriptor
        ).state
        is recovery.PrivateExactImageRecoveryState.FOREIGN_IMAGE_REFUSED
    )


@pytest.mark.parametrize(
    ("registry", "descriptor"),
    [
        (bytearray(b"data"), None),
        (None, bytearray(b"data")),
        ("data", None),
        (None, 17),
        (b"x" * (metadata.MAX_REGISTRY_BYTES + 1), None),
        (None, b"x" * (metadata.MAX_ASSOCIATION_BYTES + 1)),
    ],
    ids=(
        "bytearray-registry",
        "bytearray-descriptor",
        "string-registry",
        "integer-descriptor",
        "oversized-registry",
        "oversized-descriptor",
    ),
)
def test_unqualified_observations_refused(registry: object, descriptor: object) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.INITIALIZE)
    assert (
        recovery.classify_private_exact_image_recovery(
            proposal,
            observed_registry=registry,  # type: ignore[arg-type]
            observed_descriptor=descriptor,  # type: ignore[arg-type]
        ).state
        is recovery.PrivateExactImageRecoveryState.OBSERVATION_UNQUALIFIED
    )


def test_invalid_object_or_tampered_frozen_intent_refused() -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    assert (
        recovery.classify_private_exact_image_recovery(
            "not an intent",  # type: ignore[arg-type]
            observed_registry=proposal.registry_before,
            observed_descriptor=proposal.descriptor_before,
        ).state
        is recovery.PrivateExactImageRecoveryState.INTENT_REFUSED
    )
    object.__setattr__(proposal, "registry_after", b"forged")
    assert (
        recovery.classify_private_exact_image_recovery(
            proposal,
            observed_registry=proposal.registry_before,
            observed_descriptor=proposal.descriptor_before,
        ).state
        is recovery.PrivateExactImageRecoveryState.INTENT_REFUSED
    )


def test_substituted_before_bytes_cannot_be_accepted_as_same_proposal() -> None:
    original = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    assert original.registry_before is not None
    object.__setattr__(original, "registry_before", original.registry_before + b"\n")
    # The actual before image differs from the signature in the witness.
    assert (
        recovery.classify_private_exact_image_recovery(
            original,
            observed_registry=original.registry_before,
            observed_descriptor=original.descriptor_before,
        ).state
        is recovery.PrivateExactImageRecoveryState.INTENT_REFUSED
    )


def test_result_is_immutable_and_has_no_write_handle() -> None:
    proposed = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    outcome = recovery.classify_private_exact_image_recovery(
        proposed,
        observed_registry=proposed.registry_before,
        observed_descriptor=proposed.descriptor_before,
    )
    with pytest.raises(FrozenInstanceError):
        setattr(
            outcome,
            "state",
            recovery.PrivateExactImageRecoveryState.AFTER_IMAGES_REVIEW_REQUIRED,
        )
    for attribute in (
        "handle",
        "path",
        "raw",
        "metadata",
        "commit_token",
        "authorized",
    ):
        assert not hasattr(outcome, attribute)
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(recovery, "commit_private_binding")
    assert not hasattr(recovery, "admit_journal")
    assert not hasattr(recovery, "apply_recovery")


def test_side_effect_free_and_does_not_create_private_root(tmp_path: Path) -> None:
    proposed = _proposal(witness.PrivateBindingOperation.INITIALIZE)
    # This API intentionally accepts no path or filesystem handle.
    before = tuple(tmp_path.iterdir())
    outcome = recovery.classify_private_exact_image_recovery(
        proposed, observed_registry=None, observed_descriptor=None
    )
    assert (
        outcome.state
        is recovery.PrivateExactImageRecoveryState.BEFORE_IMAGES_REVIEW_REQUIRED
    )
    assert tuple(tmp_path.iterdir()) == before
