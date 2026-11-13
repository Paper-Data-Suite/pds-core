"""Core #238 Slice 3E3: journal-image crash checkpoints, no replay or write."""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pds_core import _teacher_private_journal_crash_checkpoint as checkpoints
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


@pytest.mark.parametrize("operation", list(witness.PrivateBindingOperation))
@pytest.mark.parametrize(
    ("registry_after", "descriptor_after", "journal_present", "expected"),
    [
        (
            False,
            False,
            False,
            checkpoints.PrivateJournalCrashCheckpointState.NO_JOURNAL_BEFORE_REVIEW_REQUIRED,
        ),
        (
            False,
            False,
            True,
            checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
        ),
        (
            True,
            False,
            True,
            checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED,
        ),
        (
            False,
            True,
            True,
            checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
        ),
        (
            True,
            True,
            True,
            checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
        ),
        (
            True,
            False,
            False,
            checkpoints.PrivateJournalCrashCheckpointState.UNJOURNALED_PARTIAL_REFUSED,
        ),
        (
            False,
            True,
            False,
            checkpoints.PrivateJournalCrashCheckpointState.UNJOURNALED_PARTIAL_REFUSED,
        ),
        (
            True,
            True,
            False,
            checkpoints.PrivateJournalCrashCheckpointState.UNJOURNALED_AFTER_REFUSED,
        ),
    ],
    ids=[
        "before-no-journal",
        "before-journal",
        "registry-only-journal",
        "descriptor-only-journal",
        "after-journal",
        "registry-only-no-journal",
        "descriptor-only-no-journal",
        "after-no-journal",
    ],
)
def test_checkpoint_matrix(
    operation: witness.PrivateBindingOperation,
    registry_after: bool,
    descriptor_after: bool,
    journal_present: bool,
    expected: checkpoints.PrivateJournalCrashCheckpointState,
) -> None:
    proposal = _proposal(operation)
    if operation is witness.PrivateBindingOperation.REBIND_MOVE:
        # The unchanged descriptor makes descriptor-only an impossible state.
        if (registry_after, descriptor_after) in {(True, False), (False, True)}:
            expected = (
                checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED
                if registry_after and journal_present
                else checkpoints.PrivateJournalCrashCheckpointState.UNJOURNALED_AFTER_REFUSED
                if registry_after
                else checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED
                if journal_present
                else checkpoints.PrivateJournalCrashCheckpointState.NO_JOURNAL_BEFORE_REVIEW_REQUIRED
            )
    journal = (
        intents.encode_private_transaction_intent(proposal) if journal_present else None
    )
    result = checkpoints.classify_private_journal_crash_checkpoint(
        proposal,
        observed_journal=journal,
        observed_registry=proposal.registry_after
        if registry_after
        else proposal.registry_before,
        observed_descriptor=proposal.descriptor_after
        if descriptor_after
        else proposal.descriptor_before,
    )
    assert result.state is expected
    assert all(term not in repr(result) for term in (_A, _B, _TX, "1000", _ROOT_A))


@pytest.mark.parametrize("operation", list(witness.PrivateBindingOperation))
@pytest.mark.parametrize(
    "tamper",
    ["empty", "appended", "reordered", "other-intent", "bad-type", "oversized"],
)
def test_corrupt_or_wrong_journal_never_qualifies(
    operation: witness.PrivateBindingOperation, tamper: str
) -> None:
    proposal = _proposal(operation)
    valid = intents.encode_private_transaction_intent(proposal)
    journal: bytes | None
    if tamper == "empty":
        journal = b""
    elif tamper == "appended":
        journal = valid + b" "
    elif tamper == "reordered":
        journal = valid[1:] + valid[:1]
    elif tamper == "other-intent":
        other = _proposal(witness.PrivateBindingOperation.INITIALIZE)
        journal = intents.encode_private_transaction_intent(other)
        if journal == valid:
            journal = valid + b"x"
    elif tamper == "oversized":
        journal = b"x" * (intents.MAX_INTENT_BYTES + 1)
    else:
        journal = "untrusted nonbytes"  # type: ignore[assignment]
    result = checkpoints.classify_private_journal_crash_checkpoint(
        proposal,
        observed_journal=journal,
        observed_registry=proposal.registry_before,
        observed_descriptor=proposal.descriptor_before,
    )
    assert result.state in {
        checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_IMAGE_REFUSED,
        checkpoints.PrivateJournalCrashCheckpointState.OBSERVATION_UNQUALIFIED,
    }


@pytest.mark.parametrize("which", ["registry", "descriptor", "both"])
@pytest.mark.parametrize("journal_present", [True, False])
def test_foreign_metadata_fails_closed(which: str, journal_present: bool) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    registry = proposal.registry_before
    descriptor = proposal.descriptor_before
    if which in {"registry", "both"}:
        registry = b"foreign registry"
    if which in {"descriptor", "both"}:
        descriptor = b"foreign descriptor"
    result = checkpoints.classify_private_journal_crash_checkpoint(
        proposal,
        observed_journal=intents.encode_private_transaction_intent(proposal)
        if journal_present
        else None,
        observed_registry=registry,
        observed_descriptor=descriptor,
    )
    assert (
        result.state
        is checkpoints.PrivateJournalCrashCheckpointState.FOREIGN_METADATA_REFUSED
    )


def test_unqualified_and_tampered_intent_refused() -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    assert (
        checkpoints.classify_private_journal_crash_checkpoint(
            "invalid",  # type: ignore[arg-type]
            observed_journal=None,
            observed_registry=None,
            observed_descriptor=None,
        ).state
        is checkpoints.PrivateJournalCrashCheckpointState.INTENT_REFUSED
    )
    object.__setattr__(proposal, "registry_after", b"malicious")
    assert (
        checkpoints.classify_private_journal_crash_checkpoint(
            proposal,
            observed_journal=None,
            observed_registry=None,
            observed_descriptor=None,
        ).state
        is checkpoints.PrivateJournalCrashCheckpointState.INTENT_REFUSED
    )


def test_empty_bytes_are_not_verified_absence() -> None:
    proposal = _proposal(witness.PrivateBindingOperation.INITIALIZE)
    result = checkpoints.classify_private_journal_crash_checkpoint(
        proposal, observed_journal=None, observed_registry=b"", observed_descriptor=None
    )
    assert (
        result.state
        is checkpoints.PrivateJournalCrashCheckpointState.FOREIGN_METADATA_REFUSED
    )


def test_missing_journal_does_not_confirm_completed_transaction() -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    result = checkpoints.classify_private_journal_crash_checkpoint(
        proposal,
        observed_journal=None,
        observed_registry=proposal.registry_after,
        observed_descriptor=proposal.descriptor_after,
    )
    assert (
        result.state
        is checkpoints.PrivateJournalCrashCheckpointState.UNJOURNALED_AFTER_REFUSED
    )
    assert not hasattr(result, "commit_token") and not hasattr(result, "authorized")


def test_result_frozen_no_writable_service(tmp_path: Path) -> None:
    proposal = _proposal(witness.PrivateBindingOperation.FORK_COPY)
    before = tuple(tmp_path.iterdir())
    result = checkpoints.classify_private_journal_crash_checkpoint(
        proposal,
        observed_journal=None,
        observed_registry=proposal.registry_before,
        observed_descriptor=proposal.descriptor_before,
    )
    with pytest.raises(FrozenInstanceError):
        setattr(
            result,
            "state",
            checkpoints.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
        )
    assert tuple(tmp_path.iterdir()) == before
    assert not hasattr(checkpoints, "write_journal")
    assert not hasattr(checkpoints, "commit_private_binding")
    assert not hasattr(checkpoints, "recover_private_binding")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
