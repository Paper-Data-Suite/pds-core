"""Core #238 3G56: both canonical stages must agree under one native guard."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import _teacher_private_recovery_descriptor_stage_custody as stages
from pds_core import _teacher_private_recovery_dual_stage_sealed_scope as dual
from pds_core import _teacher_private_recovery_one_shot_transition_pair as one_shot
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_recovery_transition_registry_custody as native
from pds_core import _teacher_private_transaction_intent as intents


State = dual.PrivateDualStageScopeState
STEP = scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY
PRIVATE = Path("/fake/private")
WORKSPACE = Path("/fake/workspace")


def _fork() -> intents.PrivateTransactionIntent:
    return canonical._canonical_fork_intent()


def _review(
    proposed: intents.PrivateTransactionIntent | None = None,
) -> dual.PrivateDualStageScopeReview:
    intent = _fork() if proposed is None else proposed
    return dual.review_canonical_fork_dual_stage_sealed_scope(
        STEP, 2, intent, PRIVATE, WORKSPACE
    )


class _Window:
    def __init__(self) -> None:
        self.attempted = False
        self.identity = native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        self.reads = 0

    def observe(self) -> native.PrivateRegistryTransitionIdentityState:
        self.reads += 1
        return self.identity


def _ready(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, int], _Window]:
    owner = object()
    seen: dict[str, int] = {
        "locks": 0,
        "pair": 0,
        "native": 0,
        "stage": 0,
        "frames": 0,
        "frame_checks": 0,
        "checkpoints": 0,
        "barriers": 0,
        "owners": 0,
    }
    window = _Window()
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    def owner_probe(*_args: object) -> tuple[None, object]:
        seen["native"] += 1
        return None, owner

    monkeypatch.setattr(preflight, "_native_observation", owner_probe)
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: None)

    def get_owner() -> object:
        seen["owners"] += 1
        return owner

    monkeypatch.setattr(ordered, "_owner", get_owner)

    @contextmanager
    def hold(*_args: object) -> Iterator[None]:
        seen["locks"] += 1
        yield

    monkeypatch.setattr(
        transition, "_hold_transitionable_journal_descriptor_guard", hold
    )

    @contextmanager
    def pair(*_args: object) -> Iterator[_Window]:
        seen["pair"] += 1
        yield window

    monkeypatch.setattr(one_shot, "_held_one_shot_transition_pair", pair)

    def frame(*_args: object) -> object:
        seen["frames"] += 1
        return object()

    def frame_check(*_args: object) -> None:
        seen["frame_checks"] += 1
        return None

    monkeypatch.setattr(scope, "_observe", frame)
    monkeypatch.setattr(scope, "_frame_state", frame_check)

    def checkpoint(*_args: object) -> recovery.PrivatePostcrashReconciliationState:
        seen["checkpoints"] += 1
        return (
            recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED
        )

    monkeypatch.setattr(recovery, "_classify_present", checkpoint)

    def read(_root: Path, name: str) -> stages._StageRead:
        seen["stage"] += 1
        assert name == "." + _fork().witness.transaction_id + ".descriptor-stage"
        return stages._StageRead(
            stages._ReadState.OBSERVED, _fork().descriptor_after, (4, 14, 2)
        )

    monkeypatch.setattr(stages, "_read_stage", read)

    def blocked(*_args: object) -> bool:
        seen["barriers"] += 1
        return True

    monkeypatch.setattr(stages, "_barrier_blocked", blocked)
    return seen, window


def _inert(result: dual.PrivateDualStageScopeReview) -> None:
    assert result.pending_evidence_must_remain
    assert result.production_writes_blocked
    assert result.automatic_replay_forbidden
    assert result.journal_retirement_forbidden
    assert result.durable_commit_unqualified
    assert result.custody_expired_on_release
    assert result.unqualified_requirements == barrier._REQUIRED
    assert "fake" not in repr(result).lower()
    assert "fake" not in result.message.lower()


def test_three_complete_frames_under_one_native_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen, window = _ready(monkeypatch)
    result = _review()
    assert result.state is State.DUAL_STAGES_OBSERVED_BARRIER_BLOCKED
    assert seen["locks"] == seen["pair"] == 1
    assert (
        seen["frames"]
        == seen["frame_checks"]
        == seen["stage"]
        == seen["checkpoints"]
        == 3
    )
    assert seen["barriers"] == 2
    assert seen["native"] == 4
    assert window.reads == 6
    assert not window.attempted
    _inert(result)


@pytest.mark.parametrize("step", [None, 0, object(), "stage", False])
def test_invalid_step_is_refused(step: object) -> None:
    result = dual.review_canonical_fork_dual_stage_sealed_scope(
        cast(scratch.PrivateScratchWriterStep, step), 2, _fork(), PRIVATE, WORKSPACE
    )
    assert result.state is State.INVALID_REQUEST
    _inert(result)


@pytest.mark.parametrize("revision", [None, -1, 0, False, "2", 2.0, object()])
def test_invalid_revision_is_refused(revision: object) -> None:
    assert (
        dual.review_canonical_fork_dual_stage_sealed_scope(
            STEP, cast(int, revision), _fork(), PRIVATE, WORKSPACE
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("intent", [None, False, object(), "intent"])
def test_invalid_intent_is_refused(intent: object) -> None:
    assert (
        dual.review_canonical_fork_dual_stage_sealed_scope(
            STEP, 2, cast(intents.PrivateTransactionIntent, intent), PRIVATE, WORKSPACE
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("root_index", [0, 1])
def test_invalid_roots_are_refused(root_index: int) -> None:
    roots: list[object] = [PRIVATE, WORKSPACE]
    roots[root_index] = "untrusted"
    assert (
        dual.review_canonical_fork_dual_stage_sealed_scope(
            STEP, 2, _fork(), cast(Path, roots[0]), cast(Path, roots[1])
        ).state
        is State.INVALID_REQUEST
    )


def test_wrong_revision_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    assert (
        dual.review_canonical_fork_dual_stage_sealed_scope(
            STEP, 3, _fork(), PRIVATE, WORKSPACE
        ).state
        is State.REVISION_MISMATCH
    )


def test_root_check_failure_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: False)
    assert _review().state is State.ROOT_UNQUALIFIED


def test_workspace_path_failure_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: False)
    assert _review().state is State.ROOT_UNQUALIFIED


@pytest.mark.parametrize("attempt", [1, 2])
def test_barrier_pre_and_post_refusal(
    monkeypatch: pytest.MonkeyPatch, attempt: int
) -> None:
    _ready(monkeypatch)
    calls = 0

    def barrier_check(*_args: object) -> bool:
        nonlocal calls
        calls += 1
        return calls != attempt

    monkeypatch.setattr(stages, "_barrier_blocked", barrier_check)
    assert _review().state is State.BARRIER_REFUSED


def test_unqualified_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (object(), None))
    assert _review().state is State.OWNER_OR_BINDING_REFUSED


def test_binding_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: object())
    assert _review().state is State.OWNER_OR_BINDING_REFUSED


def test_owner_changes_inside_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(ordered, "_owner", lambda: object())
    assert _review().state is State.OWNER_CHANGED


def test_native_owner_drifts_between_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    calls = 0

    def changed(*_args: object) -> tuple[None, object]:
        nonlocal calls
        calls += 1
        return None, object()

    monkeypatch.setattr(preflight, "_native_observation", changed)
    assert _review().state is State.OWNER_CHANGED


def test_proposed_intent_drift_after_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    original = dual._canonical
    count = 0

    def drift(
        intent: intents.PrivateTransactionIntent,
    ) -> tuple[intents.PrivateTransactionIntent, bytes] | None:
        nonlocal count
        count += 1
        return None if count == 2 else original(intent)

    monkeypatch.setattr(dual, "_canonical", drift)
    assert _review().state is State.CANONICAL_DRIFT_PRESERVE


def test_attempt_marker_preexisting_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _seen, window = _ready(monkeypatch)
    window.attempted = True
    assert _review().state is State.ATTEMPT_MARKER_CONFLICT_PRESERVE


def test_native_registry_identity_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    _seen, window = _ready(monkeypatch)
    window.identity = native.PrivateRegistryTransitionIdentityState.OWNER_CHANGED
    assert _review().state is State.REGISTRY_STAGE_CHANGED_PRESERVE


def test_canonical_registry_frame_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(scope, "_frame_state", lambda *_: object())
    assert _review().state is State.REGISTRY_IMAGE_CONFLICT_PRESERVE


def test_pending_checkpoint_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(
        recovery,
        "_classify_present",
        lambda *_: recovery.PrivatePostcrashReconciliationState.IO_ERROR,
    )
    assert _review().state is State.CHECKPOINT_CONFLICT_PRESERVE


@pytest.mark.parametrize(
    ("read_state", "expected"),
    [
        (stages._ReadState.MISSING, State.DESCRIPTOR_STAGE_MISSING_PRESERVE),
        (stages._ReadState.UNSAFE, State.DESCRIPTOR_STAGE_UNSAFE_PRESERVE),
        (stages._ReadState.REFUSED, State.DESCRIPTOR_STAGE_UNSAFE_PRESERVE),
    ],
)
def test_descriptor_stage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    read_state: stages._ReadState,
    expected: State,
) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(stages, "_read_stage", lambda *_: stages._StageRead(read_state))
    assert _review().state is expected


def test_descriptor_stage_content_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(
        stages,
        "_read_stage",
        lambda *_: stages._StageRead(stages._ReadState.OBSERVED, b"other", (3, 5, 9)),
    )
    assert _review().state is State.DESCRIPTOR_STAGE_IMAGE_CONFLICT_PRESERVE


def test_descriptor_stage_identity_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    count = 0

    def changed(_root: Path, _name: str) -> stages._StageRead:
        nonlocal count
        count += 1
        return stages._StageRead(
            stages._ReadState.OBSERVED, _fork().descriptor_after, (1, 2, count)
        )

    monkeypatch.setattr(stages, "_read_stage", changed)
    assert _review().state is State.DESCRIPTOR_STAGE_CHANGED_PRESERVE


def test_descriptor_stage_missing_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(
        stages,
        "_read_stage",
        lambda *_: stages._StageRead(
            stages._ReadState.OBSERVED, _fork().descriptor_after
        ),
    )
    assert _review().state is State.DESCRIPTOR_STAGE_UNSAFE_PRESERVE


def test_guard_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)

    @contextmanager
    def refused(*_args: object) -> Iterator[None]:
        raise transition._WriterGuardRefused(
            transition.PrivateTransitionGuardState.GUARD_REFUSED
        )
        yield

    monkeypatch.setattr(
        transition, "_hold_transitionable_journal_descriptor_guard", refused
    )
    assert _review().state is State.GUARD_REFUSED


def test_pair_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)

    @contextmanager
    def refused(*_args: object) -> Iterator[_Window]:
        raise one_shot._AttemptScopeRefused
        yield _Window()

    monkeypatch.setattr(one_shot, "_held_one_shot_transition_pair", refused)
    assert _review().state is State.GUARD_REFUSED


def test_checkpoint_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)

    def interrupted(*_args: object) -> recovery.PrivatePostcrashReconciliationState:
        raise KeyboardInterrupt

    monkeypatch.setattr(recovery, "_classify_present", interrupted)
    assert _review().state is State.INTERRUPTED_PRESERVE


def test_native_io_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)

    def failure(*_args: object) -> object:
        raise OSError("sensitive details must not escape")

    monkeypatch.setattr(scope, "_observe", failure)
    result = _review()
    assert result.state is State.IO_ERROR
    assert "sensitive details" not in result.message
    _inert(result)


def test_decoder_refusal_is_not_native_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed = _fork()
    _ready(monkeypatch)

    def failure(_data: bytes) -> intents.PrivateTransactionIntent:
        raise intents.PrivateIntentError

    monkeypatch.setattr(intents, "decode_private_transaction_intent", failure)
    assert _review(proposed).state is State.INTENT_UNQUALIFIED


def test_no_mutating_operation_in_module() -> None:
    import inspect

    source = inspect.getsource(dual)
    assert "os.replace(" not in source
    assert ".mark_attempt(" not in source
    assert "unlink(" not in source
    assert "write_bytes(" not in source
    assert "rmtree(" not in source
