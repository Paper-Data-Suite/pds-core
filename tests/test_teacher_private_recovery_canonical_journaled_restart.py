"""Core #238 3G52: canonical two-document restart, scratch-only fail-closed matrix."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from pds_core import _teacher_private_recovery_canonical_journaled_restart as drill
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as prior
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


@pytest.mark.parametrize("fault", list(drill.PrivateCanonicalRestartFault))
def test_disposable_canonical_fork_restart(
    fault: drill.PrivateCanonicalRestartFault,
) -> None:
    result = drill.rehearse_canonical_two_document_restart(fault)
    assert type(result) is drill.PrivateCanonicalRestartReview
    assert result.state in {
        drill.PrivateCanonicalRestartState.CANONICAL_SCRATCH_AFTER_IMAGES_UNQUALIFIED,
        drill.PrivateCanonicalRestartState.INJECTED_INTERRUPTION_HOLD,
        drill.PrivateCanonicalRestartState.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD,
    }
    assert result.pending_evidence_must_remain
    assert result.production_writes_blocked
    assert result.automatic_replay_forbidden
    assert result.journal_retirement_forbidden
    assert result.durability_unqualified
    assert result.journal_seen_at_restart
    assert result.checkpoint in {
        drill.PrivateCanonicalRestartCheckpoint.PREPARED_HOLD,
        drill.PrivateCanonicalRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
        drill.PrivateCanonicalRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
    }
    assert "private" not in repr(result)


def test_canonical_fork_is_real_and_distinct_in_both_documents() -> None:
    checked = drill._canonical_fork_intent()
    assert type(checked) is intents.PrivateTransactionIntent
    assert checked.witness.operation is witness.PrivateBindingOperation.FORK_COPY
    assert checked.witness.registry_revision_before == 2
    assert checked.witness.registry_revision_after == 3
    assert checked.witness.association_before != checked.witness.association_after
    assert checked.registry_before != checked.registry_after
    assert checked.descriptor_before != checked.descriptor_after
    raw = intents.encode_private_transaction_intent(checked)
    assert intents.decode_private_transaction_intent(raw) == checked
    assert (
        intents.encode_private_transaction_intent(
            intents.decode_private_transaction_intent(raw)
        )
        == raw
    )


@pytest.mark.parametrize("bad", [None, False, 1, "none", object()])
def test_invalid_fault_is_refused_without_creating_files(
    bad: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("Invalid request entered native scratch code")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", fail)
    result = drill.rehearse_canonical_two_document_restart(bad)  # type: ignore[arg-type]
    assert result.state is drill.PrivateCanonicalRestartState.INVALID_REQUEST
    assert not result.replacement_may_have_occurred


def test_unsupported_platform_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = drill.rehearse_canonical_two_document_restart()
    assert result.state is drill.PrivateCanonicalRestartState.UNSUPPORTED
    assert result.production_writes_blocked


@pytest.mark.parametrize(
    "phase,expected",
    [
        (
            drill.PrivateCanonicalRestartFault.AFTER_PREPARED_FLUSH,
            drill.PrivateCanonicalRestartCheckpoint.PREPARED_HOLD,
        ),
        (
            drill.PrivateCanonicalRestartFault.AFTER_REGISTRY_REPLACE,
            drill.PrivateCanonicalRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
        ),
        (
            drill.PrivateCanonicalRestartFault.AFTER_REGISTRY_FLUSH,
            drill.PrivateCanonicalRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
        ),
        (
            drill.PrivateCanonicalRestartFault.AFTER_DESCRIPTOR_REPLACE,
            drill.PrivateCanonicalRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
        ),
        (
            drill.PrivateCanonicalRestartFault.AFTER_DESCRIPTOR_FLUSH,
            drill.PrivateCanonicalRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
        ),
        (
            drill.PrivateCanonicalRestartFault.AFTER_OPERATION_LOCK_RELEASE,
            drill.PrivateCanonicalRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
        ),
    ],
)
def test_interruption_holds_exact_canonical_restart_checkpoint(
    phase: drill.PrivateCanonicalRestartFault,
    expected: drill.PrivateCanonicalRestartCheckpoint,
) -> None:
    result = drill.rehearse_canonical_two_document_restart(phase)
    if (
        result.state
        is drill.PrivateCanonicalRestartState.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD
    ):
        pytest.skip("Native filesystem refused disposable flush request")
    assert result.state is drill.PrivateCanonicalRestartState.INJECTED_INTERRUPTION_HOLD
    assert result.checkpoint is expected
    assert result.journal_seen_at_restart
    assert result.automatic_replay_forbidden


def test_completed_scratch_canonical_journal_remains_pending() -> None:
    result = drill.rehearse_canonical_two_document_restart()
    if (
        result.state
        is drill.PrivateCanonicalRestartState.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD
    ):
        pytest.skip("Native filesystem refused disposable flush request")
    assert (
        result.state
        is drill.PrivateCanonicalRestartState.CANONICAL_SCRATCH_AFTER_IMAGES_UNQUALIFIED
    )
    assert (
        result.checkpoint
        is drill.PrivateCanonicalRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
    )
    assert result.journal_seen_at_restart
    assert result.replacement_may_have_occurred
    assert result.phases == (
        "journal_and_stages_flushed",
        "prepared_parents_flushed",
        "registry_replaced",
        "registry_flush_requested",
        "descriptor_replaced",
        "descriptor_flush_requested",
    )


def test_native_replace_refusal_never_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []

    def refuse(source: Path, target: Path) -> None:
        calls.append((source, target))
        raise PermissionError("injected")

    monkeypatch.setattr(os, "replace", refuse)
    result = drill.rehearse_canonical_two_document_restart()
    if (
        result.state
        is drill.PrivateCanonicalRestartState.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD
    ):
        pytest.skip("Native filesystem refused disposable flush request")
    assert len(calls) == 1
    assert (
        result.state
        is drill.PrivateCanonicalRestartState.NATIVE_REPLACEMENT_OUTCOME_UNKNOWN_HOLD
    )
    assert result.checkpoint is drill.PrivateCanonicalRestartCheckpoint.PREPARED_HOLD
    assert result.journal_seen_at_restart
    assert result.automatic_replay_forbidden


@pytest.mark.parametrize("stage", [0, 1])
def test_native_replacement_partial_failure_preserves_restart(
    stage: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Names and real target paths are not caller-supplied: inspect only count.
    calls = 0
    original = os.replace

    def replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == stage + 1:
            raise OSError("injected replacement refusal")
        original(source, target)

    monkeypatch.setattr(os, "replace", replace)
    result = drill.rehearse_canonical_two_document_restart()
    if (
        result.state
        is drill.PrivateCanonicalRestartState.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD
    ):
        pytest.skip("Native filesystem refused disposable flush request")
    assert calls == stage + 1
    assert (
        result.state
        is drill.PrivateCanonicalRestartState.NATIVE_REPLACEMENT_OUTCOME_UNKNOWN_HOLD
    )
    assert result.checkpoint is (
        drill.PrivateCanonicalRestartCheckpoint.PREPARED_HOLD
        if stage == 0
        else drill.PrivateCanonicalRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
    )
    assert result.journal_seen_at_restart


def test_flush_request_refusal_is_never_upgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_path: Path) -> None:
        raise durable._DirectoryFlushRefused

    monkeypatch.setattr(durable, "_directory_flush", refuse)
    result = drill.rehearse_canonical_two_document_restart()
    assert (
        result.state
        is drill.PrivateCanonicalRestartState.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD
    )
    assert result.checkpoint is drill.PrivateCanonicalRestartCheckpoint.PREPARED_HOLD
    assert result.journal_seen_at_restart
    assert not result.replacement_may_have_occurred


def test_restart_guard_refusal_wipes_positive_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import contextmanager
    from typing import Iterator

    @contextmanager
    def refuse(_path: Path) -> Iterator[None]:
        raise prior._RestartGuardRefused
        yield

    monkeypatch.setattr(prior, "_held_existing_restart_lock", refuse)
    result = drill.rehearse_canonical_two_document_restart()
    assert result.state in {
        drill.PrivateCanonicalRestartState.GUARD_REFUSED_PRESERVE,
        drill.PrivateCanonicalRestartState.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD,
    }
    if result.state is drill.PrivateCanonicalRestartState.GUARD_REFUSED_PRESERVE:
        assert not result.journal_seen_at_restart


def test_checkpoint_rejects_corrupt_journal_and_extra_entries(tmp_path: Path) -> None:
    checked = drill._canonical_fork_intent()
    private = tmp_path / "private"
    descriptor_dir = tmp_path / "workspace" / ".pds"
    (private / "transactions").mkdir(parents=True)
    descriptor_dir.mkdir(parents=True)
    registry, stage, descriptor, dstage, journal = drill._paths(private, descriptor_dir)
    with durable._scratch_lock(private / ".native-lock"):
        for path, raw in (
            (registry, checked.registry_before),
            (stage, checked.registry_after),
            (descriptor, checked.descriptor_before),
            (dstage, checked.descriptor_after),
            (journal, intents.encode_private_transaction_intent(checked)),
        ):
            assert type(raw) is bytes
            durable._write_new(path, raw)
        assert (
            drill._checkpoint(private, descriptor_dir, checked)
            is drill.PrivateCanonicalRestartCheckpoint.PREPARED_HOLD
        )
        journal.write_bytes(b"forged")
        assert (
            drill._checkpoint(private, descriptor_dir, checked)
            is drill.PrivateCanonicalRestartCheckpoint.CONFLICT_PRESERVE
        )
        journal.write_bytes(intents.encode_private_transaction_intent(checked))
        (private / "unexpected").write_bytes(b"x")
        assert (
            drill._checkpoint(private, descriptor_dir, checked)
            is drill.PrivateCanonicalRestartCheckpoint.CONFLICT_PRESERVE
        )


def test_no_mutation_authority_visible_in_return_type() -> None:
    result = drill._result(
        drill.PrivateCanonicalRestartState.CANONICAL_SCRATCH_AFTER_IMAGES_UNQUALIFIED
    )
    assert result.pending_evidence_must_remain
    assert result.production_writes_blocked
    assert result.automatic_replay_forbidden
    assert result.journal_retirement_forbidden
    assert result.durability_unqualified
    assert not hasattr(result, "write")
    assert not hasattr(result, "commit")
    assert not hasattr(result, "retire")
