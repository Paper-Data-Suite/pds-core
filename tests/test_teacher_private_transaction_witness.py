"""#238 Slice 3B3: pure, non-authorizing interrupted-write classifications."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

UUID_A = "6fb32a62-83e2-43f6-9823-687801593c8b"
UUID_B = "d2f5733a-e471-4865-a070-e943ad20863f"
UUID_TXN = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
BEFORE_DESC = "a" * 64
AFTER_DESC = "b" * 64
BEFORE_REG = "c" * 64
AFTER_REG = "d" * 64


def plan(
    operation: witness.PrivateBindingOperation = witness.PrivateBindingOperation.FORK_COPY,
) -> witness.PrivateTransactionWitness:
    if operation is witness.PrivateBindingOperation.INITIALIZE:
        return witness.PrivateTransactionWitness(
            operation, UUID_TXN, None, UUID_B, 0, 1, None, AFTER_DESC, None, AFTER_REG
        )
    if operation is witness.PrivateBindingOperation.REBIND_MOVE:
        return witness.PrivateTransactionWitness(
            operation,
            UUID_TXN,
            UUID_A,
            UUID_A,
            1,
            2,
            BEFORE_DESC,
            BEFORE_DESC,
            BEFORE_REG,
            AFTER_REG,
        )
    return witness.PrivateTransactionWitness(
        operation,
        UUID_TXN,
        UUID_A,
        UUID_B,
        1,
        2,
        BEFORE_DESC,
        AFTER_DESC,
        BEFORE_REG,
        AFTER_REG,
    )


@pytest.mark.parametrize("operation", list(witness.PrivateBindingOperation))
def test_all_operations_have_valid_pure_witnesses(
    operation: witness.PrivateBindingOperation,
) -> None:
    data = plan(operation)
    assert data.registry_revision_after == data.registry_revision_before + 1
    assert "6fb32a" not in repr(data)
    assert "a" * 64 not in repr(data)
    assert "e3ba2e" not in repr(data)


@pytest.mark.parametrize(
    ("descriptor", "registry", "expected"),
    [
        (BEFORE_DESC, BEFORE_REG, witness.PrivateTransactionObservation.NOT_APPLIED),
        (AFTER_DESC, BEFORE_REG, witness.PrivateTransactionObservation.DESCRIPTOR_ONLY),
        (BEFORE_DESC, AFTER_REG, witness.PrivateTransactionObservation.REGISTRY_ONLY),
        (
            AFTER_DESC,
            AFTER_REG,
            witness.PrivateTransactionObservation.BOTH_APPLIED_REVIEW_REQUIRED,
        ),
        ("e" * 64, BEFORE_REG, witness.PrivateTransactionObservation.CONFLICT),
        (AFTER_DESC, "f" * 64, witness.PrivateTransactionObservation.CONFLICT),
        (None, None, witness.PrivateTransactionObservation.CONFLICT),
    ],
)
def test_fork_interrupted_states_classified_without_auto_repair(
    descriptor: str | None,
    registry: str | None,
    expected: witness.PrivateTransactionObservation,
) -> None:
    assert (
        witness.classify_private_transaction_observation(
            plan(), descriptor_sha256=descriptor, registry_sha256=registry
        )
        is expected
    )


@pytest.mark.parametrize(
    ("descriptor", "registry", "expected"),
    [
        (None, None, witness.PrivateTransactionObservation.NOT_APPLIED),
        (AFTER_DESC, None, witness.PrivateTransactionObservation.DESCRIPTOR_ONLY),
        (None, AFTER_REG, witness.PrivateTransactionObservation.REGISTRY_ONLY),
        (
            AFTER_DESC,
            AFTER_REG,
            witness.PrivateTransactionObservation.BOTH_APPLIED_REVIEW_REQUIRED,
        ),
    ],
)
def test_initialization_interrupted_states(
    descriptor: str | None,
    registry: str | None,
    expected: witness.PrivateTransactionObservation,
) -> None:
    assert (
        witness.classify_private_transaction_observation(
            plan(witness.PrivateBindingOperation.INITIALIZE),
            descriptor_sha256=descriptor,
            registry_sha256=registry,
        )
        is expected
    )


def test_move_has_unchanged_descriptor_and_changed_registry() -> None:
    proposal = plan(witness.PrivateBindingOperation.REBIND_MOVE)
    assert (
        witness.classify_private_transaction_observation(
            proposal, descriptor_sha256=BEFORE_DESC, registry_sha256=BEFORE_REG
        )
        is witness.PrivateTransactionObservation.NOT_APPLIED
    )
    assert (
        witness.classify_private_transaction_observation(
            proposal, descriptor_sha256=BEFORE_DESC, registry_sha256=AFTER_REG
        )
        is witness.PrivateTransactionObservation.BOTH_APPLIED_REVIEW_REQUIRED
    )


@pytest.mark.parametrize(
    "change",
    [
        "transaction_id",
        "association_after",
        "association_before",
        "descriptor_sha256_after",
        "registry_revision_before",
        "registry_revision_after",
        "registry_sha256_before",
        "registry_sha256_after",
        "descriptor_sha256_before",
        "operation",
    ],
)
def test_invalid_fork_witness_refused_with_safe_error(change: str) -> None:
    original = plan()
    with pytest.raises(witness.PrivateTransactionError) as result:
        if change == "transaction_id":
            replace(original, transaction_id="invalid")
        elif change == "association_after":
            replace(original, association_after=UUID_A)
        elif change == "association_before":
            replace(original, association_before=None)
        elif change == "descriptor_sha256_after":
            replace(original, descriptor_sha256_after=BEFORE_DESC)
        elif change == "registry_revision_before":
            replace(original, registry_revision_before=True)
        elif change == "registry_revision_after":
            replace(original, registry_revision_after=9)
        elif change == "registry_sha256_before":
            replace(original, registry_sha256_before=None)
        elif change == "registry_sha256_after":
            replace(original, registry_sha256_after=BEFORE_REG)
        elif change == "descriptor_sha256_before":
            replace(original, descriptor_sha256_before="X" * 64)
        elif change == "operation":
            replace(original, operation="fork_copy")  # type: ignore[arg-type]
        else:
            raise AssertionError("Unexpected invalid mutation case")
    assert "6fb32a" not in str(result.value)
    assert "synthetic" not in str(result.value)


def test_rebind_cannot_allocate_a_new_association() -> None:
    with pytest.raises(witness.PrivateTransactionError):
        replace(
            plan(witness.PrivateBindingOperation.REBIND_MOVE), association_after=UUID_B
        )


def test_initialize_cannot_claim_prior_descriptor() -> None:
    with pytest.raises(witness.PrivateTransactionError):
        replace(
            plan(witness.PrivateBindingOperation.INITIALIZE),
            descriptor_sha256_before=BEFORE_DESC,
        )


def test_mutation_rejected() -> None:
    with pytest.raises(FrozenInstanceError):
        plan().registry_revision_after = 17  # type: ignore[misc]


@pytest.mark.parametrize("invalid", ["BAD", 123, True, "F" * 64, "a" * 63])
def test_observed_invalid_digest_is_refused(invalid: object) -> None:
    with pytest.raises(witness.PrivateTransactionError):
        witness.classify_private_transaction_observation(
            plan(),
            descriptor_sha256=invalid,  # type: ignore[arg-type]
            registry_sha256=AFTER_REG,
        )


def test_no_write_api_or_notes_capability() -> None:
    assert not hasattr(witness, "commit_private_transaction")
    assert not hasattr(witness, "create_private_store")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_import_does_not_write_or_prompt(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    probe = (
        "from pds_core._teacher_private_transaction_witness import "
        "PrivateTransactionWitness, classify_private_transaction_observation; "
        "assert callable(classify_private_transaction_observation)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe],
        cwd=tmp_path,
        env=environment,
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []
