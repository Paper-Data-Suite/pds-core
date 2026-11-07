"""Core #238 3G51: disposable journaled operation-to-restart drill."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as drill


@pytest.mark.parametrize(
    ("fault", "expected_state", "checkpoint", "attempted"),
    [
        (
            drill.PrivateJournaledRestartFault.NONE,
            drill.PrivateJournaledRestartState.SCRATCH_RESTART_BOTH_AFTER_UNQUALIFIED,
            drill.PrivateJournaledRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
            True,
        ),
        (
            drill.PrivateJournaledRestartFault.AFTER_PREPARATION,
            drill.PrivateJournaledRestartState.INJECTED_INTERRUPTION_HOLD,
            drill.PrivateJournaledRestartCheckpoint.PREPARED_STAGE_HOLD,
            False,
        ),
        (
            drill.PrivateJournaledRestartFault.AFTER_REGISTRY_REPLACE,
            drill.PrivateJournaledRestartState.INJECTED_INTERRUPTION_HOLD,
            drill.PrivateJournaledRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
            True,
        ),
        (
            drill.PrivateJournaledRestartFault.AFTER_REGISTRY_PERSIST_REQUEST,
            drill.PrivateJournaledRestartState.INJECTED_INTERRUPTION_HOLD,
            drill.PrivateJournaledRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
            True,
        ),
        (
            drill.PrivateJournaledRestartFault.AFTER_DESCRIPTOR_REPLACE,
            drill.PrivateJournaledRestartState.INJECTED_INTERRUPTION_HOLD,
            drill.PrivateJournaledRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
            True,
        ),
        (
            drill.PrivateJournaledRestartFault.AFTER_DESCRIPTOR_PERSIST_REQUEST,
            drill.PrivateJournaledRestartState.INJECTED_INTERRUPTION_HOLD,
            drill.PrivateJournaledRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
            True,
        ),
        (
            drill.PrivateJournaledRestartFault.AFTER_OPERATION_GUARD_RELEASE,
            drill.PrivateJournaledRestartState.INJECTED_INTERRUPTION_HOLD,
            drill.PrivateJournaledRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
            True,
        ),
    ],
)
def test_restart_observes_exact_post_interruption_checkpoint(
    fault: drill.PrivateJournaledRestartFault,
    expected_state: drill.PrivateJournaledRestartState,
    checkpoint: drill.PrivateJournaledRestartCheckpoint,
    attempted: bool,
) -> None:
    outcome = drill.rehearse_disposable_journaled_restart(fault)
    assert outcome.state is expected_state
    assert outcome.checkpoint is checkpoint
    assert outcome.replacement_may_have_occurred is attempted
    assert outcome.journal_seen_at_restart
    assert outcome.pending_evidence_must_remain
    assert outcome.production_writes_blocked
    assert outcome.automatic_replay_forbidden
    assert outcome.journal_retirement_forbidden
    assert outcome.durability_unqualified
    assert repr(outcome) == "PrivateJournaledRestartReview(non_authorizing=True)"


@pytest.mark.parametrize("bad_value", [None, "none", 0, False, object()])
def test_invalid_request_does_not_launch_scratch(bad_value: object) -> None:
    outcome = drill.rehearse_disposable_journaled_restart(bad_value)  # type: ignore[arg-type]
    assert outcome.state is drill.PrivateJournaledRestartState.INVALID_REQUEST
    assert not outcome.replacement_may_have_occurred
    assert not outcome.journal_seen_at_restart
    assert outcome.automatic_replay_forbidden


def test_only_module_generated_paths_can_be_used() -> None:
    import inspect

    params = inspect.signature(drill.rehearse_disposable_journaled_restart).parameters
    assert tuple(params) == ("interruption",)
    assert all(item not in params for item in ("path", "root", "callback", "intent"))


def test_exact_order_and_one_attempt_per_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changes: list[str] = []
    original = os.replace

    def observed_replace(
        src: os.PathLike[str] | str, dst: os.PathLike[str] | str
    ) -> None:
        destination = Path(dst)
        source = Path(src)
        assert destination.parent.exists()
        if destination.name == "registry.json":
            assert durable._exact(
                destination.parent / "transactions" / "synthetic-pending.json",
                durable._JOURNAL,
            )
            assert durable._exact(source, durable._REG_AFTER)
        else:
            assert destination.name == "teacher-private-association.json"
            assert durable._exact(source, durable._DESC_AFTER)
        changes.append(destination.name)
        original(src, dst)

    monkeypatch.setattr(os, "replace", observed_replace)
    outcome = drill.rehearse_disposable_journaled_restart()
    assert (
        outcome.state
        is drill.PrivateJournaledRestartState.SCRATCH_RESTART_BOTH_AFTER_UNQUALIFIED
    )
    assert changes == ["registry.json", "teacher-private-association.json"]
    assert outcome.phases == (
        "prepared_file_flushes",
        "prepared_directory_flushes",
        "registry_replaced",
        "registry_persist_requested",
        "descriptor_replaced",
        "descriptor_persist_requested",
    )


@pytest.mark.parametrize("refuse_at", [1, 2, 3, 4, 5])
def test_failed_directory_flush_preserves_restart_evidence(
    monkeypatch: pytest.MonkeyPatch, refuse_at: int
) -> None:
    original = durable._directory_flush
    seen = 0

    def fail_one(directory: Path) -> None:
        nonlocal seen
        seen += 1
        if seen == refuse_at:
            raise durable._DirectoryFlushRefused
        original(directory)

    monkeypatch.setattr(durable, "_directory_flush", fail_one)
    outcome = drill.rehearse_disposable_journaled_restart()
    assert (
        outcome.state
        is drill.PrivateJournaledRestartState.NATIVE_PERSISTENCE_REFUSED_HOLD
    )
    assert outcome.checkpoint in {
        drill.PrivateJournaledRestartCheckpoint.PREPARED_STAGE_HOLD,
        drill.PrivateJournaledRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
        drill.PrivateJournaledRestartCheckpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD,
    }
    assert outcome.journal_seen_at_restart
    assert outcome.automatic_replay_forbidden


@pytest.mark.parametrize("refuse_at", [1, 4, 5])
def test_failed_file_flush_preserves_restart_evidence(
    monkeypatch: pytest.MonkeyPatch, refuse_at: int
) -> None:
    original = durable._file_flush
    seen = 0

    def fail_one(path: Path) -> None:
        nonlocal seen
        seen += 1
        if seen == refuse_at:
            raise durable._FileFlushRefused
        original(path)

    monkeypatch.setattr(durable, "_file_flush", fail_one)
    outcome = drill.rehearse_disposable_journaled_restart()
    assert (
        outcome.state
        is drill.PrivateJournaledRestartState.NATIVE_PERSISTENCE_REFUSED_HOLD
    )
    assert outcome.journal_seen_at_restart
    assert outcome.automatic_replay_forbidden


@pytest.mark.parametrize("refuse_at", [1, 2])
def test_native_replacement_refusal_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, refuse_at: int
) -> None:
    original = os.replace
    seen = 0

    def refuse_once(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        nonlocal seen
        seen += 1
        if seen == refuse_at:
            raise PermissionError("injected synthetic refusal")
        original(src, dst)

    monkeypatch.setattr(os, "replace", refuse_once)
    outcome = drill.rehearse_disposable_journaled_restart()
    assert seen == refuse_at
    assert (
        outcome.state
        is drill.PrivateJournaledRestartState.REPLACEMENT_OUTCOME_UNKNOWN_HOLD
    )
    assert outcome.replacement_may_have_occurred
    assert outcome.checkpoint is (
        drill.PrivateJournaledRestartCheckpoint.PREPARED_STAGE_HOLD
        if refuse_at == 1
        else drill.PrivateJournaledRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
    )
    assert outcome.journal_seen_at_restart
    assert outcome.automatic_replay_forbidden


def test_reacquire_failure_does_not_claim_restart_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def refuse(_path: Path) -> Iterator[None]:
        raise drill._RestartGuardRefused
        yield

    monkeypatch.setattr(drill, "_held_existing_restart_lock", refuse)
    outcome = drill.rehearse_disposable_journaled_restart()
    assert outcome.state is drill.PrivateJournaledRestartState.RESTART_GUARD_REFUSED
    assert (
        outcome.checkpoint
        is drill.PrivateJournaledRestartCheckpoint.OBSERVATION_REFUSED
    )
    assert not outcome.journal_seen_at_restart
    assert outcome.automatic_replay_forbidden


def test_restart_evidence_tampering_cannot_be_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = drill._checkpoint
    seen = 0

    def conflict_at_restart(
        private: Path, descriptor: Path
    ) -> drill.PrivateJournaledRestartCheckpoint:
        nonlocal seen
        seen += 1
        if seen >= 6:
            return drill.PrivateJournaledRestartCheckpoint.CONFLICT_PRESERVE
        return original(private, descriptor)

    monkeypatch.setattr(drill, "_checkpoint", conflict_at_restart)
    outcome = drill.rehearse_disposable_journaled_restart()
    assert outcome.state is drill.PrivateJournaledRestartState.RESTART_EVIDENCE_CONFLICT
    assert outcome.automatic_replay_forbidden


def test_released_guard_precedes_restart_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = durable._scratch_lock
    restart = drill._held_existing_restart_lock
    events: list[str] = []

    @contextmanager
    def first_scope(path: Path) -> Iterator[None]:
        with first(path):
            events.append("operation_enter")
            yield
            events.append("operation_exit")

    @contextmanager
    def second_scope(path: Path) -> Iterator[None]:
        events.append("restart_enter")
        with restart(path):
            yield
        events.append("restart_exit")

    monkeypatch.setattr(durable, "_scratch_lock", first_scope)
    monkeypatch.setattr(drill, "_held_existing_restart_lock", second_scope)
    result = drill.rehearse_disposable_journaled_restart()
    assert (
        result.state
        is drill.PrivateJournaledRestartState.SCRATCH_RESTART_BOTH_AFTER_UNQUALIFIED
    )
    assert events == [
        "operation_enter",
        "operation_exit",
        "restart_enter",
        "restart_exit",
    ]


def test_unsupported_platform_never_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    outcome = drill.rehearse_disposable_journaled_restart()
    assert outcome.state is drill.PrivateJournaledRestartState.UNSUPPORTED
    assert outcome.automatic_replay_forbidden


def test_restart_guard_checks_single_byte_lock(tmp_path: Path) -> None:
    lock = tmp_path / ".native-lock"
    lock.write_bytes(b"not-lock")
    with pytest.raises(drill._RestartGuardRefused):
        with drill._held_existing_restart_lock(lock):
            pytest.fail("Unsafe lock admitted")


def test_namespace_census_rejects_unsafe_entries(tmp_path: Path) -> None:
    path = tmp_path / "private"
    path.mkdir()
    (path / "registry.json").write_bytes(b"x")
    assert drill._names(path, frozenset({"registry.json"}))
    (path / "extra").write_bytes(b"x")
    assert not drill._names(path, frozenset({"registry.json"}))
    assert not drill._names(path, frozenset({"registry.json", "unknown"}))


def test_no_token_exposes_payload_bytes() -> None:
    outcome = drill.rehearse_disposable_journaled_restart()
    public = repr(outcome)
    assert "synthetic-private-registry" not in public.lower()
    assert "synthetic" not in public.lower()
    assert outcome.journal_retirement_forbidden
    assert outcome.pending_evidence_must_remain


def test_keyboard_interrupt_after_registry_attempt_preserves_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = os.replace

    def interrupted(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        original(src, dst)
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupted)
    result = drill.rehearse_disposable_journaled_restart()
    assert result.state is drill.PrivateJournaledRestartState.INJECTED_INTERRUPTION_HOLD
    assert (
        result.checkpoint
        is drill.PrivateJournaledRestartCheckpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
    )
    assert result.replacement_may_have_occurred
    assert result.journal_seen_at_restart
    assert result.automatic_replay_forbidden
