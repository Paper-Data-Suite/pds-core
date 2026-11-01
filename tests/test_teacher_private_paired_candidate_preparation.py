"""Core #238 3G1: two guarded create-only phases, synthetic fault injection."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_journal_provision as journal_create
from pds_core import _teacher_private_linux_stage_mutation_guard as linux_stage
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_mutation_aware_journal_guard as linux_journal
from pds_core import _teacher_private_paired_candidate_preparation as paired
from pds_core import _teacher_private_registry_stage_provision as stage_create
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_journal_mutation_guard as windows_journal
from pds_core import _teacher_private_windows_stage_mutation_guard as windows_stage
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = paired.PrivatePairedPreparationState


def _intent(
    operation: witness.PrivateBindingOperation = witness.PrivateBindingOperation.FORK_COPY,
) -> intents.PrivateTransactionIntent:
    item = object.__new__(intents.PrivateTransactionIntent)
    operation_witness = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(operation_witness, "operation", operation)
    object.__setattr__(item, "witness", operation_witness)
    return item


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    proposal: intents.PrivateTransactionIntent,
    platform: str,
    events: list[str],
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_args: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_args: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda _: b"test-intent"
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: proposal
    )

    @contextmanager
    def first(*_args: object) -> Iterator[None]:
        events.append("journal-enter")
        yield
        events.append("journal-verified")

    @contextmanager
    def second(*_args: object) -> Iterator[None]:
        events.append("stage-enter")
        yield
        events.append("stage-verified")

    monkeypatch.setattr(linux_journal, "hold_expected_private_journal_creation", first)
    monkeypatch.setattr(
        windows_journal, "hold_expected_windows_private_journal_creation", first
    )
    monkeypatch.setattr(
        linux_stage, "hold_expected_linux_private_registry_stage_creation", second
    )
    monkeypatch.setattr(
        windows_stage, "hold_expected_windows_private_registry_stage_creation", second
    )

    def write_journal(*_args: object) -> SimpleNamespace:
        events.append("journal-write")
        return SimpleNamespace(
            state=journal_create.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
        )

    def write_stage(*_args: object) -> SimpleNamespace:
        events.append("stage-write")
        return SimpleNamespace(
            state=stage_create.PrivateRegistryStageState.STAGED_UNQUALIFIED
        )

    monkeypatch.setattr(
        journal_create, "create_private_transaction_intent_file", write_journal
    )
    monkeypatch.setattr(
        stage_create, "create_private_registry_after_image_stage", write_stage
    )


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_pair_requires_correct_order_with_no_commit_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    proposal = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposal, platform, events)
    result = paired.prepare_private_journal_and_registry_stage(
        proposal, tmp_path, tmp_path
    )
    assert result.state is State.PREPARED_REVIEW_REQUIRED
    assert events == [
        "journal-enter",
        "journal-write",
        "journal-verified",
        "stage-enter",
        "stage-write",
        "stage-verified",
    ]
    assert not hasattr(result, "commit_token")
    assert not hasattr(result, "private_path")


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize(
    "rejection",
    [
        journal_create.PrivateJournalProvisionState.ALREADY_EXISTS,
        journal_create.PrivateJournalProvisionState.CREATION_UNVERIFIED,
        journal_create.PrivateJournalProvisionState.ACCESS_DENIED,
    ],
)
def test_failed_journal_never_begins_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    rejection: journal_create.PrivateJournalProvisionState,
) -> None:
    proposal = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposal, platform, events)
    monkeypatch.setattr(
        journal_create,
        "create_private_transaction_intent_file",
        lambda *_: SimpleNamespace(state=rejection),
    )
    result = paired.prepare_private_journal_and_registry_stage(
        proposal, tmp_path, tmp_path
    )
    assert result.state is State.JOURNAL_REVIEW_REQUIRED
    assert events == ["journal-enter"]


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize(
    "rejection",
    [
        stage_create.PrivateRegistryStageState.ALREADY_EXISTS,
        stage_create.PrivateRegistryStageState.CREATION_UNVERIFIED,
        stage_create.PrivateRegistryStageState.REFUSED_PROTECTION,
    ],
)
def test_failed_stage_preserves_journal_and_never_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    rejection: stage_create.PrivateRegistryStageState,
) -> None:
    proposal = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposal, platform, events)
    evidence = tmp_path / "pending-journal-synthetic"
    evidence.write_bytes(b"synthetic")
    monkeypatch.setattr(
        stage_create,
        "create_private_registry_after_image_stage",
        lambda *_: SimpleNamespace(state=rejection),
    )
    result = paired.prepare_private_journal_and_registry_stage(
        proposal, tmp_path, tmp_path
    )
    assert result.state is State.STAGE_REVIEW_REQUIRED
    assert evidence.read_bytes() == b"synthetic"
    assert events == [
        "journal-enter",
        "journal-write",
        "journal-verified",
        "stage-enter",
    ]


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_journal_guard_postcondition_refusal_prevents_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    proposal = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposal, platform, events)

    @contextmanager
    def refuses(*_args: object) -> Iterator[None]:
        yield
        raise linux_journal.PrivateJournalMutationGuardError(
            linux_journal.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION
        )

    target = linux_journal if platform == "linux" else windows_journal
    name = (
        "hold_expected_private_journal_creation"
        if platform == "linux"
        else "hold_expected_windows_private_journal_creation"
    )
    monkeypatch.setattr(target, name, refuses)
    assert (
        paired.prepare_private_journal_and_registry_stage(
            proposal, tmp_path, tmp_path
        ).state
        is State.JOURNAL_REVIEW_REQUIRED
    )
    assert "stage-enter" not in events


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_stage_guard_postcondition_refusal_preserves_review_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    proposal = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposal, platform, events)

    @contextmanager
    def refuses(*_args: object) -> Iterator[None]:
        yield
        if platform == "linux":
            raise linux_stage.PrivateLinuxStageMutationError(
                linux_stage.PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION
            )
        raise windows_stage.PrivateWindowsStageMutationError(
            windows_stage.PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION
        )

    target = linux_stage if platform == "linux" else windows_stage
    name = (
        "hold_expected_linux_private_registry_stage_creation"
        if platform == "linux"
        else "hold_expected_windows_private_registry_stage_creation"
    )
    monkeypatch.setattr(target, name, refuses)
    assert (
        paired.prepare_private_journal_and_registry_stage(
            proposal, tmp_path, tmp_path
        ).state
        is State.STAGE_REVIEW_REQUIRED
    )
    assert events[:3] == ["journal-enter", "journal-write", "journal-verified"]
    assert "stage-write" in events


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_initial_binding_cannot_create_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    proposal = _intent(witness.PrivateBindingOperation.INITIALIZE)
    events: list[str] = []
    _configure(monkeypatch, proposal, platform, events)
    assert (
        paired.prepare_private_journal_and_registry_stage(
            proposal, tmp_path, tmp_path
        ).state
        is State.INITIALIZATION_REFUSED
    )
    assert events == []


def test_invalid_request_and_unsupported_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposal, "linux", events)
    assert (
        paired.prepare_private_journal_and_registry_stage(
            cast(intents.PrivateTransactionIntent, object()), tmp_path, tmp_path
        ).state
        is State.INVALID_REQUEST
    )
    assert events == []
    monkeypatch.setattr(sys, "platform", "darwin")
    assert (
        paired.prepare_private_journal_and_registry_stage(
            proposal, tmp_path, tmp_path
        ).state
        is State.UNSUPPORTED
    )


def test_no_public_notes_write_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(paired, "commit_private_binding")
    assert not hasattr(paired, "replace_private_registry")
