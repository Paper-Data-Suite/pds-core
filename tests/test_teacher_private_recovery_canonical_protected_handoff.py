"""3G54 protected canonical FORK_COPY handoff; all writes remain blocked."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import _teacher_private_recovery_canonical_protected_handoff as handoff
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_sealed_pre_attempt as sealed
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents


State = handoff.PrivateCanonicalProtectedHandoffState
RState = recovery.PrivatePostcrashReconciliationState
_FORK_STEP = scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY
_PR = Path("/synthetic/protected-private")
_WR = Path("/synthetic/association-root")


def _canonical() -> intents.PrivateTransactionIntent:
    return canonical._canonical_fork_intent()


def _review() -> handoff.PrivateCanonicalProtectedHandoffReview:
    return handoff.review_canonical_fork_protected_handoff(
        _FORK_STEP, 2, _canonical(), _PR, _WR
    )


def _mock_native(
    monkeypatch: pytest.MonkeyPatch,
    *,
    seal: sealed.PrivateSealedPreAttemptState = (
        sealed.PrivateSealedPreAttemptState.ONE_SHOT_PREATTEMPT_BLOCKED
    ),
    recovered: recovery.PrivatePostcrashReconciliationState = (
        RState.STAGED_BEFORE_REVIEW_REQUIRED
    ),
) -> list[str]:
    calls: list[str] = []

    def blocked(
        _step: scratch.PrivateScratchWriterStep,
        _revision: int,
        _intent: intents.PrivateTransactionIntent,
    ) -> barrier.PrivateProductionWriteBarrierReview:
        calls.append("barrier")
        return barrier._result(
            barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        )

    def preattempt(
        _step: scratch.PrivateScratchWriterStep,
        _revision: int,
        _intent: intents.PrivateTransactionIntent,
        _private: Path,
        _workspace: Path,
    ) -> sealed.PrivateSealedPreAttemptReview:
        calls.append("one_shot")
        return sealed._result(seal)

    def reconcile(
        _intent: intents.PrivateTransactionIntent,
        _private: Path,
        _workspace: Path,
    ) -> recovery.PrivatePostcrashReconciliationReview:
        calls.append("independent_recovery")
        return recovery._result(recovered)

    monkeypatch.setattr(barrier, "review_private_production_write_barrier", blocked)
    monkeypatch.setattr(sealed, "review_sealed_native_pre_attempt_boundary", preattempt)
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        reconcile,
    )
    return calls


def _all_blocked(r: handoff.PrivateCanonicalProtectedHandoffReview) -> None:
    assert r.pending_evidence_must_remain is True
    assert r.production_writes_blocked is True
    assert r.no_automatic_retry is True
    assert r.journal_retirement_forbidden is True
    assert r.durability_unqualified is True
    assert r.separate_native_scopes_not_atomic is True
    assert r.unqualified_requirements == barrier._REQUIRED
    assert "Path(" not in repr(r)
    assert "native" not in repr(r).lower()
    assert not hasattr(r, "write")
    assert not hasattr(r, "permission")


def test_canonical_protected_handoff_never_authorizes_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_native(monkeypatch)
    r = _review()
    assert r.state is State.PREPARED_FORK_REOBSERVED_BLOCKED
    assert calls == ["barrier", "one_shot", "independent_recovery", "barrier"]
    _all_blocked(r)


@pytest.mark.parametrize(
    "bad",
    [None, False, 0, "fork", object(), [], {}],
)
def test_wrong_step_type_fails_before_native_calls(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    calls = _mock_native(monkeypatch)
    r = handoff.review_canonical_fork_protected_handoff(
        cast(scratch.PrivateScratchWriterStep, bad), 2, _canonical(), _PR, _WR
    )
    assert r.state is State.INVALID_REQUEST
    assert calls == []
    _all_blocked(r)


@pytest.mark.parametrize("bad", [None, 0, -1, True, "2", 2.0, object()])
def test_wrong_revision_type_fails_before_native_calls(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    calls = _mock_native(monkeypatch)
    r = handoff.review_canonical_fork_protected_handoff(
        _FORK_STEP, cast(int, bad), _canonical(), _PR, _WR
    )
    assert r.state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("bad", [None, 0, False, "fork", object(), b"{}"])
def test_wrong_intent_fails_without_touching_native(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    calls = _mock_native(monkeypatch)
    r = handoff.review_canonical_fork_protected_handoff(
        _FORK_STEP, 2, cast(intents.PrivateTransactionIntent, bad), _PR, _WR
    )
    assert r.state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize(
    "private,workspace",
    [(None, _WR), (_PR, None), ("/root", _WR), (_PR, "/root"), (0, _WR), (_PR, 1)],
)
def test_wrong_roots_refused_before_custody(
    monkeypatch: pytest.MonkeyPatch, private: object, workspace: object
) -> None:
    calls = _mock_native(monkeypatch)
    r = handoff.review_canonical_fork_protected_handoff(
        _FORK_STEP, 2, _canonical(), cast(Path, private), cast(Path, workspace)
    )
    assert r.state is State.INVALID_REQUEST
    assert calls == []


def test_other_step_refused_without_any_native_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_native(monkeypatch)
    r = handoff.review_canonical_fork_protected_handoff(
        scratch.PrivateScratchWriterStep.DESCRIPTOR_COMPLETION,
        2,
        _canonical(),
        _PR,
        _WR,
    )
    assert r.state is State.OPERATION_NOT_ADMITTED
    assert calls == []


def test_other_platform_refused_without_any_native_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_native(monkeypatch)
    monkeypatch.setattr(sys, "platform", "darwin")
    r = _review()
    assert r.state is State.UNSUPPORTED
    assert calls == []


def test_wrong_revision_refused_before_native_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_native(monkeypatch)
    r = handoff.review_canonical_fork_protected_handoff(
        _FORK_STEP, 3, _canonical(), _PR, _WR
    )
    assert r.state is State.REVISION_MISMATCH_REFUSED
    assert calls == []


@pytest.mark.parametrize(
    "state",
    [
        s
        for s in sealed.PrivateSealedPreAttemptState
        if s is not sealed.PrivateSealedPreAttemptState.ONE_SHOT_PREATTEMPT_BLOCKED
    ],
)
def test_protected_custody_refusals_stay_blocked(
    monkeypatch: pytest.MonkeyPatch, state: sealed.PrivateSealedPreAttemptState
) -> None:
    calls = _mock_native(monkeypatch, seal=state)
    r = _review()
    assert r.state is State.PROTECTED_SCOPE_DRIFT_PRESERVE
    assert calls == ["barrier", "one_shot"]
    _all_blocked(r)


@pytest.mark.parametrize(
    "recovered,expected",
    [
        (
            RState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            State.RECOVERY_REGISTRY_AFTER_PRESERVE,
        ),
        (
            RState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            State.RECOVERY_BOTH_AFTER_PRESERVE,
        ),
        *[
            (x, State.RECOVERY_OTHER_PRESERVE)
            for x in RState
            if x
            not in (
                RState.STAGED_BEFORE_REVIEW_REQUIRED,
                RState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
                RState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            )
        ],
    ],
)
def test_fresh_recovery_never_licenses_replay(
    monkeypatch: pytest.MonkeyPatch,
    recovered: recovery.PrivatePostcrashReconciliationState,
    expected: handoff.PrivateCanonicalProtectedHandoffState,
) -> None:
    calls = _mock_native(monkeypatch, recovered=recovered)
    r = _review()
    assert r.state is expected
    assert calls == ["barrier", "one_shot", "independent_recovery"]
    _all_blocked(r)


def test_invalid_native_seal_result_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _mock_native(monkeypatch)
    monkeypatch.setattr(
        sealed, "review_sealed_native_pre_attempt_boundary", lambda *_: object()
    )
    r = _review()
    assert r.state is State.PROTECTED_PREATTEMPT_REFUSED
    assert calls == ["barrier"]


def test_invalid_native_recovery_result_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_native(monkeypatch)
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *_: object(),
    )
    r = _review()
    assert r.state is State.RECOVERY_REFUSED
    assert calls == ["barrier", "one_shot"]


def test_incomplete_seal_requirements_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _mock_native(monkeypatch)
    monkeypatch.setattr(
        sealed,
        "review_sealed_native_pre_attempt_boundary",
        lambda *_: replace(
            sealed._result(
                sealed.PrivateSealedPreAttemptState.ONE_SHOT_PREATTEMPT_BLOCKED
            ),
            unqualified_requirements=(),
        ),
    )
    r = _review()
    assert r.state is State.PROTECTED_PREATTEMPT_REFUSED
    assert calls == ["barrier"]


@pytest.mark.parametrize("boundary", [1, 2])
def test_barrier_must_stay_blocked_at_both_boundaries(
    monkeypatch: pytest.MonkeyPatch, boundary: int
) -> None:
    calls = _mock_native(monkeypatch)
    count = 0

    def changing(
        _step: scratch.PrivateScratchWriterStep,
        _revision: int,
        _intent: intents.PrivateTransactionIntent,
    ) -> barrier.PrivateProductionWriteBarrierReview:
        nonlocal count
        count += 1
        calls.append("barrier")
        if count == boundary:
            return barrier._result(
                barrier.PrivateProductionWriteBarrierState.DESCRIPTION_UNQUALIFIED
            )
        return barrier._result(
            barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        )

    monkeypatch.setattr(barrier, "review_private_production_write_barrier", changing)
    r = _review()
    assert r.state is (
        State.BARRIER_UNQUALIFIED
        if boundary == 1
        else State.FINAL_BARRIER_CHANGED_PRESERVE
    )
    _all_blocked(r)
    assert len(calls) == (1 if boundary == 1 else 4)


def test_barrier_requirements_cannot_be_claimed_satisfied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_native(monkeypatch)

    def missing(
        _step: scratch.PrivateScratchWriterStep,
        _revision: int,
        _intent: intents.PrivateTransactionIntent,
    ) -> barrier.PrivateProductionWriteBarrierReview:
        calls.append("barrier")
        return replace(
            barrier._result(
                barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
            ),
            unqualified_requirements=(),
        )

    monkeypatch.setattr(barrier, "review_private_production_write_barrier", missing)
    assert _review().state is State.BARRIER_UNQUALIFIED
    assert calls == ["barrier"]


@pytest.mark.parametrize("stage", ["barrier", "sealed", "recovery"])
def test_interruption_preserves_evidence(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    _mock_native(monkeypatch)

    def interrupt(*_args: object) -> None:
        raise KeyboardInterrupt

    if stage == "barrier":
        monkeypatch.setattr(
            barrier, "review_private_production_write_barrier", interrupt
        )
    elif stage == "sealed":
        monkeypatch.setattr(
            sealed, "review_sealed_native_pre_attempt_boundary", interrupt
        )
    else:
        monkeypatch.setattr(
            recovery,
            "reconcile_native_private_pending_registry_after_interruption",
            interrupt,
        )
    r = _review()
    assert r.state is State.INTERRUPTED_PRESERVE
    _all_blocked(r)


def test_no_delegated_native_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_native(monkeypatch)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("native mutation reached")

    monkeypatch.setattr(os, "replace", forbidden)
    assert _review().state is State.PREPARED_FORK_REOBSERVED_BLOCKED


def test_canonical_decode_failure_is_not_native_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_native(monkeypatch)
    proposed = _canonical()

    def invalid(_raw: bytes) -> intents.PrivateTransactionIntent:
        raise intents.PrivateIntentError

    monkeypatch.setattr(intents, "decode_private_transaction_intent", invalid)
    assert (
        handoff.review_canonical_fork_protected_handoff(
            _FORK_STEP, 2, proposed, _PR, _WR
        ).state
        is State.INTENT_UNQUALIFIED
    )
    assert calls == []
