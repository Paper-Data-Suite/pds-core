"""Core #238 3G10: two native observations may suggest review, never recovery writes."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as candidate
from pds_core import _teacher_private_transaction_intent as intents
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = candidate.PrivateRecoveryActionPreconditionState
Step = candidate.PrivateRecoveryProposedStep
Observed = recovery.PrivatePostcrashReconciliationState


def _intent() -> intents.PrivateTransactionIntent:
    return object.__new__(intents.PrivateTransactionIntent)


def _review(state: Observed) -> recovery.PrivatePostcrashReconciliationReview:
    return recovery.PrivatePostcrashReconciliationReview(state, "synthetic-recovery")


def _observe(
    monkeypatch: pytest.MonkeyPatch,
    steps: list[Observed],
    calls: list[tuple[object, ...]],
) -> None:
    iterator = iter(steps)

    def native(*args: object) -> recovery.PrivatePostcrashReconciliationReview:
        calls.append(args)
        return _review(next(iterator))

    monkeypatch.setattr(
        recovery, "reconcile_native_private_pending_registry_after_interruption", native
    )


def _call(
    tmp_path: Path,
    step: Step = Step.REVIEW_PREPARED_RESTART,
) -> candidate.PrivateRecoveryActionPreconditionReview:
    return candidate.review_private_recovery_action_preconditions(
        step, _intent(), tmp_path, tmp_path
    )


@pytest.mark.parametrize("platform", ["darwin", "freebsd", "sunos"])
def test_unsupported_platform_never_calls_native(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *_: pytest.fail("native read after unsupported platform"),
    )
    assert _call(tmp_path).state is State.UNSUPPORTED
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", [None, "next", 2, object()])
def test_bad_action_rejected_before_native(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *_: pytest.fail("native read after invalid action"),
    )
    value = candidate.review_private_recovery_action_preconditions(
        cast(Step, bad), _intent(), tmp_path, tmp_path
    )
    assert value.state is State.INVALID_REQUEST


@pytest.mark.parametrize("bad", [None, object(), 23, "intent"])
def test_bad_intent_rejected_before_native(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *_: pytest.fail("native read after invalid intent"),
    )
    value = candidate.review_private_recovery_action_preconditions(
        Step.REVIEW_PREPARED_RESTART,
        cast(intents.PrivateTransactionIntent, bad),
        tmp_path,
        tmp_path,
    )
    assert value.state is State.INVALID_REQUEST


@pytest.mark.parametrize("bad", [None, object(), "root", 2])
def test_bad_root_rejected_before_native(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *_: pytest.fail("native read after invalid root"),
    )
    value = candidate.review_private_recovery_action_preconditions(
        Step.REVIEW_PREPARED_RESTART, _intent(), cast(Path, bad), tmp_path
    )
    assert value.state is State.INVALID_REQUEST
    value = candidate.review_private_recovery_action_preconditions(
        Step.REVIEW_PREPARED_RESTART, _intent(), tmp_path, cast(Path, bad)
    )
    assert value.state is State.INVALID_REQUEST


@pytest.mark.parametrize(
    ("observed", "step"),
    [
        (Observed.STAGED_BEFORE_REVIEW_REQUIRED, Step.REVIEW_PREPARED_RESTART),
        (
            Observed.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_DESCRIPTOR_COMPLETION,
        ),
        (
            Observed.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_JOURNAL_RETIREMENT,
        ),
    ],
)
def test_matching_stable_checkpoint_is_advisory_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    observed: Observed,
    step: Step,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[tuple[object, ...]] = []
    _observe(monkeypatch, [observed, observed], calls)
    result = _call(tmp_path, step)
    assert result.state is State.MATCHING_CHECKPOINT_REVIEW_REQUIRED
    assert len(calls) == 2
    assert calls[0] != () and calls[0][1:] == (tmp_path, tmp_path)
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "commit_token")
    assert not hasattr(result, "path")
    assert not hasattr(result, "witness")
    assert not hasattr(result, "next_action")
    assert not hasattr(result, "write")
    assert "synthetic-recovery" not in repr(result)
    assert str(tmp_path) not in result.message
    assert not list(tmp_path.iterdir())
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.UNSUPPORTED)


@pytest.mark.parametrize(
    ("observed", "requested"),
    [
        (Observed.STAGED_BEFORE_REVIEW_REQUIRED, Step.REVIEW_DESCRIPTOR_COMPLETION),
        (Observed.STAGED_BEFORE_REVIEW_REQUIRED, Step.REVIEW_JOURNAL_RETIREMENT),
        (
            Observed.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_PREPARED_RESTART,
        ),
        (
            Observed.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_JOURNAL_RETIREMENT,
        ),
        (
            Observed.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_PREPARED_RESTART,
        ),
        (
            Observed.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_DESCRIPTOR_COMPLETION,
        ),
    ],
)
def test_mismatched_step_never_qualified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, observed: Observed, requested: Step
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    calls: list[tuple[object, ...]] = []
    _observe(monkeypatch, [observed, observed], calls)
    assert _call(tmp_path, requested).state is State.ACTION_MISMATCH_REFUSED
    assert len(calls) == 2


@pytest.mark.parametrize(
    "observed",
    [
        Observed.STAGED_BEFORE_REVIEW_REQUIRED,
        Observed.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        Observed.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
        Observed.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED,
    ],
)
def test_checkpoint_drift_refuses_every_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, observed: Observed
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[tuple[object, ...]] = []
    _observe(monkeypatch, [observed, Observed.IMAGES_UNQUALIFIED], calls)
    assert _call(tmp_path).state is State.CHECKPOINT_CHANGED
    assert len(calls) == 2


def test_stage_with_changed_metadata_requires_conflict_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    calls: list[tuple[object, ...]] = []
    observed = Observed.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED
    _observe(monkeypatch, [observed, observed], calls)
    assert _call(tmp_path).state is State.STAGE_CONFLICT_PRESERVE
    assert len(calls) == 2


@pytest.mark.parametrize(
    "observed",
    [
        Observed.STAGE_MISSING_BEFORE_REFUSED,
        Observed.STAGE_MISSING_PARTIAL_REFUSED,
        Observed.IMAGES_UNQUALIFIED,
        Observed.NAMESPACE_UNQUALIFIED,
        Observed.INITIALIZATION_REFUSED,
        Observed.OWNER_CHANGED,
        Observed.GUARD_REFUSED,
        Observed.IO_ERROR,
    ],
)
def test_unqualified_first_checkpoint_fails_without_second(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, observed: Observed
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[tuple[object, ...]] = []
    _observe(monkeypatch, [observed], calls)
    assert _call(tmp_path).state is State.CHECKPOINT_UNQUALIFIED
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("observed", "expect"),
    [
        (Observed.INVALID_REQUEST, State.INVALID_REQUEST),
        (Observed.UNSUPPORTED, State.UNSUPPORTED),
    ],
)
def test_delegate_refusal_fails_before_second(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, observed: Observed, expect: State
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    calls: list[tuple[object, ...]] = []
    _observe(monkeypatch, [observed], calls)
    assert _call(tmp_path).state is expect
    assert len(calls) == 1


@pytest.mark.parametrize(
    "problem", [OSError("private-secret"), ValueError("private-secret")]
)
def test_native_exception_refuses_and_sanitizes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, problem: Exception
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    def native(*_args: object) -> recovery.PrivatePostcrashReconciliationReview:
        raise problem

    monkeypatch.setattr(
        recovery, "reconcile_native_private_pending_registry_after_interruption", native
    )
    result = _call(tmp_path)
    assert result.state is State.CHECKPOINT_UNQUALIFIED
    assert "private-secret" not in result.message and "private-secret" not in repr(
        result
    )


@pytest.mark.parametrize("when", [1, 2])
def test_keyboard_interrupt_preserves_no_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, when: int
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    number = [0]

    def native(*_args: object) -> recovery.PrivatePostcrashReconciliationReview:
        number[0] += 1
        if number[0] == when:
            raise KeyboardInterrupt
        return _review(Observed.STAGED_BEFORE_REVIEW_REQUIRED)

    monkeypatch.setattr(
        recovery, "reconcile_native_private_pending_registry_after_interruption", native
    )
    assert _call(tmp_path).state is State.INTERRUPTED_PRESERVE
    assert number[0] == when
    assert not list(tmp_path.iterdir())


def test_system_exit_propagates_without_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    def native(*_args: object) -> recovery.PrivatePostcrashReconciliationReview:
        raise SystemExit(37)

    monkeypatch.setattr(
        recovery, "reconcile_native_private_pending_registry_after_interruption", native
    )
    with pytest.raises(SystemExit) as error:
        _call(tmp_path)
    assert error.value.code == 37
    assert not list(tmp_path.iterdir())


def test_unexpected_result_type_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *_: object(),
    )
    assert _call(tmp_path).state is State.CHECKPOINT_UNQUALIFIED


def test_no_notes_or_public_writer_capabilities() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(candidate, "commit_private_binding")
    assert not hasattr(candidate, "retire_private_journal")
    assert not hasattr(candidate, "replay_private_registry")
