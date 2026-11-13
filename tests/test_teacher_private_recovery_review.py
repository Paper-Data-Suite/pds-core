"""#238 Slice 3B5: pure refusal-only transaction recovery review."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_recovery_review as review
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witnesses
from pds_core.teacher_experience import get_teacher_experience_capabilities

UUID_A = "6fb32a62-83e2-43f6-9823-687801593c8b"
UUID_B = "d2f5733a-e471-4865-a070-e943ad20863f"
TXN_ID = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
UUID_C = "0d120148-69cc-4c92-97b1-894a00baa350"
OWNER = metadata.PrivateRegistryOwner("posix_euid", "1000")


def digest(body: bytes | None) -> str | None:
    import hashlib

    return hashlib.sha256(body).hexdigest() if body is not None else None


def reg(
    revision: int,
    bindings: tuple[metadata.PrivateRegistryBinding, ...],
    *,
    owner: metadata.PrivateRegistryOwner = OWNER,
) -> bytes:
    return metadata.encode_private_registry(
        metadata.PrivateRegistry(owner=owner, revision=revision, bindings=bindings)
    )


def binding(
    association: str, revision: int, root: str
) -> metadata.PrivateRegistryBinding:
    return metadata.PrivateRegistryBinding(association, revision, root)


def sidecar(association: str) -> bytes:
    return metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(association)
    )


def intent_for(
    operation: witnesses.PrivateBindingOperation,
) -> intents.PrivateTransactionIntent:
    first = binding(UUID_A, 1, "/synthetic_workspace_a")
    if operation is witnesses.PrivateBindingOperation.INITIALIZE:
        before_desc = None
        after_desc = sidecar(UUID_A)
        before_reg = None
        after_reg = reg(1, (first,))
        before_assoc = None
        after_assoc = UUID_A
        before_rev = 0
    elif operation is witnesses.PrivateBindingOperation.REBIND_MOVE:
        before_desc = sidecar(UUID_A)
        after_desc = before_desc
        before_reg = reg(1, (first,))
        after_reg = reg(2, (binding(UUID_A, 2, "/synthetic_workspace_moved"),))
        before_assoc = after_assoc = UUID_A
        before_rev = 1
    else:
        before_desc = sidecar(UUID_A)
        after_desc = sidecar(UUID_B)
        before_reg = reg(1, (first,))
        after_reg = reg(2, (first, binding(UUID_B, 1, "/synthetic_workspace_b")))
        before_assoc = UUID_A
        after_assoc = UUID_B
        before_rev = 1
    witness = witnesses.PrivateTransactionWitness(
        operation=operation,
        transaction_id=TXN_ID,
        association_before=before_assoc,
        association_after=after_assoc,
        registry_revision_before=before_rev,
        registry_revision_after=before_rev + 1,
        descriptor_sha256_before=digest(before_desc),
        descriptor_sha256_after=digest(after_desc) or "",
        registry_sha256_before=digest(before_reg),
        registry_sha256_after=digest(after_reg) or "",
    )
    return intents.PrivateTransactionIntent(
        witness, before_desc, after_desc, before_reg, after_reg
    )


def observed(body: bytes | None) -> review.ObservedPrivateDocument:
    if body is None:
        return review.ObservedPrivateDocument(review.DocumentObservationKind.ABSENT)
    return review.ObservedPrivateDocument(review.DocumentObservationKind.PRESENT, body)


def classify(
    transaction: intents.PrivateTransactionIntent,
    descriptor: bytes | None,
    registry: bytes | None,
) -> review.PrivateRecoveryReview:
    return review.review_private_transaction_observation(
        transaction, descriptor=observed(descriptor), registry=observed(registry)
    )


@pytest.mark.parametrize("operation", list(witnesses.PrivateBindingOperation))
def test_before_state_does_not_imply_empty_or_ready(
    operation: witnesses.PrivateBindingOperation,
) -> None:
    transaction = intent_for(operation)
    result = classify(
        transaction, transaction.descriptor_before, transaction.registry_before
    )
    assert result.state is review.PrivateRecoveryReviewState.BEFORE_STATE
    assert "ready" not in result.message.lower()


@pytest.mark.parametrize("operation", list(witnesses.PrivateBindingOperation))
def test_after_state_always_requires_finalization_review(
    operation: witnesses.PrivateBindingOperation,
) -> None:
    transaction = intent_for(operation)
    result = classify(
        transaction, transaction.descriptor_after, transaction.registry_after
    )
    assert result.state is review.PrivateRecoveryReviewState.AFTER_STATE_REVIEW_REQUIRED
    assert "finalization" in result.message.lower()


@pytest.mark.parametrize(
    "operation",
    [
        witnesses.PrivateBindingOperation.INITIALIZE,
        witnesses.PrivateBindingOperation.FORK_COPY,
    ],
)
def test_both_one_sided_states_require_recovery_review(
    operation: witnesses.PrivateBindingOperation,
) -> None:
    transaction = intent_for(operation)
    assert (
        classify(
            transaction, transaction.descriptor_after, transaction.registry_before
        ).state
        is review.PrivateRecoveryReviewState.DESCRIPTOR_ONLY
    )
    assert (
        classify(
            transaction, transaction.descriptor_before, transaction.registry_after
        ).state
        is review.PrivateRecoveryReviewState.REGISTRY_ONLY
    )


def test_rebind_unchanged_descriptor_does_not_create_false_partial() -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.REBIND_MOVE)
    assert transaction.descriptor_before == transaction.descriptor_after
    assert (
        classify(
            transaction, transaction.descriptor_after, transaction.registry_after
        ).state
        is review.PrivateRecoveryReviewState.AFTER_STATE_REVIEW_REQUIRED
    )


@pytest.mark.parametrize(
    ("descriptor_kind", "registry_kind"),
    [
        (
            review.DocumentObservationKind.UNREADABLE,
            review.DocumentObservationKind.ABSENT,
        ),
        (
            review.DocumentObservationKind.ABSENT,
            review.DocumentObservationKind.UNREADABLE,
        ),
        (
            review.DocumentObservationKind.UNREADABLE,
            review.DocumentObservationKind.UNREADABLE,
        ),
        (
            review.DocumentObservationKind.UNREADABLE,
            review.DocumentObservationKind.PRESENT,
        ),
    ],
)
def test_unreadable_never_collapses_to_absent(
    descriptor_kind: review.DocumentObservationKind,
    registry_kind: review.DocumentObservationKind,
) -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.INITIALIZE)
    d_body = (
        transaction.descriptor_after
        if descriptor_kind is review.DocumentObservationKind.PRESENT
        else None
    )
    r_body = (
        transaction.registry_after
        if registry_kind is review.DocumentObservationKind.PRESENT
        else None
    )
    outcome = review.review_private_transaction_observation(
        transaction,
        descriptor=review.ObservedPrivateDocument(descriptor_kind, d_body),
        registry=review.ObservedPrivateDocument(registry_kind, r_body),
    )
    assert outcome.state is review.PrivateRecoveryReviewState.ACCESS_UNVERIFIED
    assert "not readable" in outcome.message


@pytest.mark.parametrize("kind", list(review.DocumentObservationKind))
def test_observation_kind_is_strict(kind: review.DocumentObservationKind) -> None:
    if kind is review.DocumentObservationKind.PRESENT:
        with pytest.raises(review.PrivateRecoveryReviewError):
            review.ObservedPrivateDocument(kind)
    else:
        with pytest.raises(review.PrivateRecoveryReviewError):
            review.ObservedPrivateDocument(kind, b"not allowed")


@pytest.mark.parametrize("bad", [None, "not bytes", 1, True])
def test_present_invalid_byte_types_refused(bad: object) -> None:
    with pytest.raises(review.PrivateRecoveryReviewError):
        review.ObservedPrivateDocument(
            review.DocumentObservationKind.PRESENT, cast("bytes | None", bad)
        )


def test_empty_present_document_is_corrupt_not_absent() -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.INITIALIZE)
    assert (
        classify(transaction, b"", None).state
        is review.PrivateRecoveryReviewState.CORRUPT_METADATA
    )


def test_unrecognized_kind_refused() -> None:
    with pytest.raises(review.PrivateRecoveryReviewError):
        review.ObservedPrivateDocument(
            cast(review.DocumentObservationKind, "present"), b"fake"
        )


@pytest.mark.parametrize("bad", [None, "object", 123, True])
def test_untrusted_intent_is_not_accepted(bad: object) -> None:
    with pytest.raises(review.PrivateRecoveryReviewError):
        review.review_private_transaction_observation(
            cast(intents.PrivateTransactionIntent, bad),
            descriptor=observed(None),
            registry=observed(None),
        )


def test_untrusted_observations_not_coerced() -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.INITIALIZE)
    with pytest.raises(review.PrivateRecoveryReviewError):
        review.review_private_transaction_observation(
            transaction,
            descriptor=cast(review.ObservedPrivateDocument, None),
            registry=observed(None),
        )


@pytest.mark.parametrize("target", ["descriptor", "registry"])
def test_malformed_observation_is_corrupt_not_empty(target: str) -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.FORK_COPY)
    if target == "descriptor":
        result = classify(transaction, b'{"future":-1}', transaction.registry_before)
    else:
        result = classify(transaction, transaction.descriptor_before, b'{"future":-1}')
    assert result.state is review.PrivateRecoveryReviewState.CORRUPT_METADATA


@pytest.mark.parametrize("target", ["descriptor", "registry"])
def test_oversized_observation_is_corrupt_not_empty(target: str) -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.FORK_COPY)
    if target == "descriptor":
        result = classify(
            transaction,
            b"x" * (metadata.MAX_ASSOCIATION_BYTES + 1),
            transaction.registry_before,
        )
    else:
        result = classify(
            transaction,
            transaction.descriptor_before,
            b"x" * (metadata.MAX_REGISTRY_BYTES + 1),
        )
    assert result.state is review.PrivateRecoveryReviewState.CORRUPT_METADATA


def test_valid_but_unexpected_sidecar_is_conflict() -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.FORK_COPY)
    third = sidecar(UUID_C)
    assert (
        classify(transaction, third, transaction.registry_before).state
        is review.PrivateRecoveryReviewState.CONFLICT
    )


def test_valid_but_changed_binding_is_conflict() -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.FORK_COPY)
    third = reg(3, (binding(UUID_A, 1, "/different_root"),))
    assert (
        classify(transaction, transaction.descriptor_before, third).state
        is review.PrivateRecoveryReviewState.CONFLICT
    )


def test_valid_registry_claiming_different_owner_is_conflict() -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.FORK_COPY)
    third = reg(
        3,
        (binding(UUID_A, 1, "/synthetic_workspace_a"),),
        owner=metadata.PrivateRegistryOwner("posix_euid", "1001"),
    )
    result = classify(transaction, transaction.descriptor_before, third)
    assert result.state is review.PrivateRecoveryReviewState.CONFLICT
    assert "1001" not in result.message


def test_synthetic_owner_and_roots_not_visible_in_public_result() -> None:
    transaction = intent_for(witnesses.PrivateBindingOperation.FORK_COPY)
    result = classify(
        transaction, transaction.descriptor_after, transaction.registry_after
    )
    for needle in ("1000", "synthetic_workspace", UUID_A, UUID_B, "e3ba2e"):
        assert needle not in repr(result)
        assert needle not in result.message


def test_dataclass_does_not_show_document_body_and_is_immutable() -> None:
    doc = observed(b"secret synthetic value")
    assert "synthetic" not in repr(doc)
    with pytest.raises(FrozenInstanceError):
        doc.body = b"changed"  # type: ignore[misc]


def test_unavailable_is_not_a_success_signal() -> None:
    assert "ready" not in {member.value for member in review.PrivateRecoveryReviewState}
    assert not hasattr(review, "create_private_store")
    assert not hasattr(review, "commit_private_transaction")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_import_does_not_access_filesystem_or_print(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(root)
    code = (
        "from pds_core._teacher_private_recovery_review import "
        "ObservedPrivateDocument, review_private_transaction_observation; "
        "assert callable(review_private_transaction_observation)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=tmp_path,
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []
