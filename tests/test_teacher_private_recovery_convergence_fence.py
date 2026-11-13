"""Core #238 3G13 independent retrospective recovery fence; zero writes."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_convergence_fence as convergence
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_mutation_boundary as boundary
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = convergence.PrivateRecoveryConvergenceState
Step = actions.PrivateRecoveryProposedStep
BState = boundary.PrivateRecoveryMutationBoundaryState
EState = exact.PrivateRecoveryExactRevisionState


def _intent() -> intents.PrivateTransactionIntent:
    item = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        item,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(item, "registry_before", b"private-r7")
    object.__setattr__(item, "registry_after", b"private-r8")
    object.__setattr__(item, "descriptor_before", b"private-desc-before")
    object.__setattr__(item, "descriptor_after", b"private-desc-after")
    return item


_INTENT = _intent()
_GOOD = BState.MATCHING_RETAINED_REVIEW_REQUIRED
_STATES = {
    Step.REVIEW_PREPARED_RESTART: EState.PREPARED_EXACT_REVIEW_REQUIRED,
    Step.REVIEW_DESCRIPTOR_COMPLETION: EState.DESCRIPTOR_PENDING_EXACT_REVIEW_REQUIRED,
    Step.REVIEW_JOURNAL_RETIREMENT: EState.JOURNAL_PENDING_EXACT_REVIEW_REQUIRED,
}


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    coarse: list[object] | None = None,
    detailed: list[object] | None = None,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    fail_at: int = 0,
    failure: BaseException | None = None,
    bad_intent: bool = False,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: b"canonical-secret"
    )
    monkeypatch.setattr(
        intents,
        "decode_private_transaction_intent",
        lambda *_: object() if bad_intent else _INTENT,
    )
    cs = iter(
        coarse
        if coarse is not None
        else [
            boundary.PrivateRecoveryMutationBoundaryReview(_GOOD, "sanitized")
            for _ in range(2)
        ]
    )
    ds = iter(
        detailed
        if detailed is not None
        else [
            exact.PrivateRecoveryExactRevisionReview(_STATES[step], "sanitized")
            for _ in range(2)
        ]
    )
    n = [0]

    def first(*_args: object) -> object:
        n[0] += 1
        calls.append("coarse")
        if n[0] == fail_at and failure is not None:
            raise failure
        return next(cs)

    def second(*_args: object) -> object:
        calls.append("exact")
        return next(ds)

    monkeypatch.setattr(
        boundary, "review_retained_private_recovery_mutation_boundary", first
    )
    monkeypatch.setattr(
        exact, "review_retained_private_recovery_exact_revision", second
    )


def _review(
    root: Path,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    revision: int = 7,
    proposed: intents.PrivateTransactionIntent = _INTENT,
) -> convergence.PrivateRecoveryConvergenceReview:
    return convergence.review_private_recovery_convergence_fence(
        step, revision, proposed, root, root
    )


@pytest.mark.parametrize(
    "step,revision,expected",
    [
        (Step.REVIEW_PREPARED_RESTART, 7, State.PREPARED_REVIEW_CONVERGED_NO_WRITE),
        (
            Step.REVIEW_DESCRIPTOR_COMPLETION,
            8,
            State.DESCRIPTOR_REVIEW_CONVERGED_NO_WRITE,
        ),
        (Step.REVIEW_JOURNAL_RETIREMENT, 8, State.JOURNAL_REVIEW_CONVERGED_NO_WRITE),
    ],
)
def test_matching_double_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step: Step,
    revision: int,
    expected: State,
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step)
    review = _review(tmp_path, step, revision)
    assert review.state is expected
    assert calls == ["coarse", "exact", "coarse", "exact"]
    assert not any(
        secret in repr(review)
        for secret in ("private-r7", str(tmp_path), "canonical-secret")
    )
    assert not hasattr(review, "write_authorized")
    assert not hasattr(review, "commit_token")
    assert not list(tmp_path.iterdir())
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.INVALID_REQUEST)


@pytest.mark.parametrize("platform", ["darwin", "freebsd", "cygwin", "haiku", "plan9"])
def test_unsupported_no_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert _review(tmp_path).state is State.UNSUPPORTED
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", [None, "restart", 1, True, object()])
def test_refuse_non_enum_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, cast(Step, bad)).state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("bad", [None, "7", 7.0, True, 0, -1, object()])
def test_refuse_non_int_positive_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, revision=cast(int, bad)).state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("bad", [None, "intent", object(), 13])
def test_refuse_invalid_intent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert (
        _review(tmp_path, proposed=cast(intents.PrivateTransactionIntent, bad)).state
        is State.INVALID_REQUEST
    )
    assert calls == []


@pytest.mark.parametrize("bad", [None, object(), "bad-root", 17])
def test_refuse_invalid_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert (
        convergence.review_private_recovery_convergence_fence(
            Step.REVIEW_PREPARED_RESTART, 7, _INTENT, cast(Path, bad), tmp_path
        ).state
        is State.INVALID_REQUEST
    )
    assert calls == []


def test_stale_revision_before_native_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, revision=8).state is State.REVISION_MISMATCH_REFUSED
    assert calls == []


def test_mismatched_canonical_intent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, bad_intent=True)
    assert _review(tmp_path).state is State.INVALID_REQUEST
    assert calls == []


def test_initializer_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    object.__setattr__(
        _INTENT.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    try:
        assert _review(tmp_path).state is State.INITIALIZATION_REFUSED
        assert calls == []
    finally:
        object.__setattr__(
            _INTENT.witness, "operation", witness.PrivateBindingOperation.REBIND_MOVE
        )


@pytest.mark.parametrize(
    "coarse_state",
    [
        BState.ACTION_MISMATCH_REFUSED,
        BState.IMAGE_DRIFT_PRESERVE,
        BState.STAGED_CONFLICT_PRESERVE,
        BState.NAMESPACE_CHANGED_PRESERVE,
        BState.CHECKPOINT_UNQUALIFIED,
        BState.OWNER_CHANGED,
        BState.GUARD_REFUSED,
        BState.INTERRUPTED_PRESERVE,
        BState.INITIALIZATION_REFUSED,
    ],
)
def test_coarse_refusal_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, coarse_state: BState
) -> None:
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        coarse=[boundary.PrivateRecoveryMutationBoundaryReview(coarse_state, "secret")],
    )
    assert _review(tmp_path).state is State.EVIDENCE_UNQUALIFIED_PRESERVE
    assert calls == ["coarse", "exact"]


@pytest.mark.parametrize(
    "exact_state",
    [
        EState.IMAGE_MISMATCH_PRESERVE,
        EState.IMAGE_DRIFT_PRESERVE,
        EState.NAMESPACE_CHANGED_PRESERVE,
        EState.GUARD_REFUSED,
        EState.OWNER_CHANGED,
        EState.IO_ERROR,
        EState.INTERRUPTED_PRESERVE,
        EState.INITIALIZATION_REFUSED,
    ],
)
def test_exact_disagreement_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exact_state: EState
) -> None:
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        detailed=[exact.PrivateRecoveryExactRevisionReview(exact_state, "secret")],
    )
    assert _review(tmp_path).state is State.CHECKPOINT_DISAGREEMENT_PRESERVE
    assert calls == ["coarse", "exact"]


def test_native_revision_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        detailed=[
            exact.PrivateRecoveryExactRevisionReview(
                EState.REVISION_MISMATCH_REFUSED, "secret"
            )
        ],
    )
    assert _review(tmp_path).state is State.REVISION_MISMATCH_REFUSED


@pytest.mark.parametrize("which", ["coarse", "exact"])
def test_malformed_native_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, which: str
) -> None:
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        coarse=[SimpleNamespace(state=_GOOD)] if which == "coarse" else None,
        detailed=[SimpleNamespace(state=EState.PREPARED_EXACT_REVIEW_REQUIRED)]
        if which == "exact"
        else None,
    )
    assert _review(tmp_path).state is State.EVIDENCE_UNQUALIFIED_PRESERVE


def test_second_pass_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        detailed=[
            exact.PrivateRecoveryExactRevisionReview(
                EState.PREPARED_EXACT_REVIEW_REQUIRED, "ok"
            ),
            exact.PrivateRecoveryExactRevisionReview(
                EState.IMAGE_DRIFT_PRESERVE, "drift"
            ),
        ],
    )
    assert _review(tmp_path).state is State.OBSERVATION_CHANGED_PRESERVE
    assert calls == ["coarse", "exact", "coarse", "exact"]


def test_second_coarse_change(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        coarse=[
            boundary.PrivateRecoveryMutationBoundaryReview(_GOOD, "ok"),
            boundary.PrivateRecoveryMutationBoundaryReview(
                BState.NAMESPACE_CHANGED_PRESERVE, "drift"
            ),
        ],
    )
    assert _review(tmp_path).state is State.OBSERVATION_CHANGED_PRESERVE


@pytest.mark.parametrize(
    "failure",
    [
        KeyboardInterrupt(),
        OSError("private location"),
        PermissionError("private secret"),
        ValueError("private bytes"),
    ],
)
def test_interruption_and_failure_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, fail_at=1, failure=failure)
    result = _review(tmp_path)
    if isinstance(failure, KeyboardInterrupt):
        assert result.state is State.INTERRUPTED_PRESERVE
    else:
        assert result.state is State.EVIDENCE_UNQUALIFIED_PRESERVE
    assert "private" not in repr(result)


def test_no_notes_or_writer_exports() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(convergence, "retire_private_journal")
    assert not hasattr(convergence, "write_private_registry")
    assert not hasattr(convergence, "open_notes")
