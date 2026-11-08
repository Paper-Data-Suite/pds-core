"""Core #238 3G55: descriptor after-stage must never confer write authority."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import _teacher_private_recovery_descriptor_stage_custody as stage
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_ordered_coordination as ordered


State = stage.PrivateDescriptorStageState
ReadState = stage._ReadState
STEP = scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY
PRIVATE = Path("/fake/native-private")
WORKSPACE = Path("/fake/native-workspace")


def _fork() -> intents.PrivateTransactionIntent:
    return canonical._canonical_fork_intent()


def _review(
    proposed: intents.PrivateTransactionIntent | None = None,
) -> stage.PrivateDescriptorStageReview:
    return stage.review_prepared_canonical_descriptor_stage(
        STEP, 2, _fork() if proposed is None else proposed, PRIVATE, WORKSPACE
    )


def _ready(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Stub the native outer custody while retaining real canonical codecs."""
    owner = object()
    seen: dict[str, int] = {"reads": 0, "checkpoints": 0, "barriers": 0, "guards": 0}
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (None, owner))
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: None)
    monkeypatch.setattr(ordered, "_owner", lambda: owner)

    @contextmanager
    def guard(*_args: object) -> Iterator[None]:
        seen["guards"] = int(seen["guards"]) + 1
        yield

    monkeypatch.setattr(
        transition, "_hold_transitionable_journal_descriptor_guard", guard
    )

    def checkpoint(*_args: object) -> recovery.PrivatePostcrashReconciliationState:
        seen["checkpoints"] = int(seen["checkpoints"]) + 1
        return (
            recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED
        )

    monkeypatch.setattr(recovery, "_classify_present", checkpoint)

    def read(_root: Path, name: str) -> stage._StageRead:
        seen["reads"] = int(seen["reads"]) + 1
        assert name == "." + _fork().witness.transaction_id + ".descriptor-stage"
        return stage._StageRead(
            ReadState.OBSERVED, _fork().descriptor_after, (4, 19, 2)
        )

    monkeypatch.setattr(stage, "_read_stage", read)

    def blocked(*_args: object) -> bool:
        seen["barriers"] = int(seen["barriers"]) + 1
        return True

    monkeypatch.setattr(stage, "_barrier_blocked", blocked)
    return seen


def _inert(result: stage.PrivateDescriptorStageReview) -> None:
    assert result.pending_evidence_must_remain
    assert result.production_writes_blocked
    assert result.automatic_retry_forbidden
    assert result.journal_retirement_forbidden
    assert result.durability_unqualified
    assert result.native_custody_expires_on_release
    assert result.unqualified_requirements == barrier._REQUIRED
    assert "fake" not in repr(result).lower()
    assert "fake" not in result.message.lower()


def test_prepared_stage_observed_but_never_authorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _ready(monkeypatch)
    result = _review()
    assert result.state is State.STAGE_PRESENT_BARRIER_BLOCKED
    assert seen == {"reads": 2, "checkpoints": 2, "barriers": 2, "guards": 1}
    _inert(result)


@pytest.mark.parametrize("input_value", [None, 0, "string", False, object()])
def test_invalid_step_type_is_refused(input_value: object) -> None:
    assert (
        stage.review_prepared_canonical_descriptor_stage(
            cast(scratch.PrivateScratchWriterStep, input_value),
            2,
            _fork(),
            PRIVATE,
            WORKSPACE,
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("revision", [None, False, 0, -1, "2", 2.0, object()])
def test_bad_revision_rejected(revision: object) -> None:
    assert (
        stage.review_prepared_canonical_descriptor_stage(
            STEP, cast(int, revision), _fork(), PRIVATE, WORKSPACE
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("proposed", [None, object(), "intent"])
def test_bad_intent_rejected(proposed: object) -> None:
    assert (
        stage.review_prepared_canonical_descriptor_stage(
            STEP,
            2,
            cast(intents.PrivateTransactionIntent, proposed),
            PRIVATE,
            WORKSPACE,
        ).state
        is State.INVALID_REQUEST
    )


def test_wrong_step_refused() -> None:
    assert (
        stage.review_prepared_canonical_descriptor_stage(
            scratch.PrivateScratchWriterStep.INITIALIZE, 2, _fork(), PRIVATE, WORKSPACE
        ).state
        is State.OPERATION_NOT_ADMITTED
    )


def test_revision_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    assert (
        stage.review_prepared_canonical_descriptor_stage(
            STEP, 3, _fork(), PRIVATE, WORKSPACE
        ).state
        is State.REVISION_MISMATCH
    )


def test_decoder_identity_conflict_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    proposed = _fork()
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _raw: object()
    )
    assert _review(proposed).state is State.INTENT_UNQUALIFIED


def test_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "other")
    assert _review().state is State.UNSUPPORTED


def test_roots_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: False)
    assert _review().state is State.ROOT_UNQUALIFIED


def test_early_barrier_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(stage, "_barrier_blocked", lambda *_: False)
    assert _review().state is State.BARRIER_UNQUALIFIED


def test_owner_preflight_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (object(), None))
    assert _review().state is State.OWNER_OR_BINDING_REFUSED


def test_binding_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: object())
    assert _review().state is State.OWNER_OR_BINDING_REFUSED


def test_owner_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(ordered, "_owner", lambda: object())
    assert _review().state is State.OWNER_CHANGED


def test_native_checkpoint_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(
        recovery,
        "_classify_present",
        lambda *_: recovery.PrivatePostcrashReconciliationState.IO_ERROR,
    )
    assert _review().state is State.CHECKPOINT_CONFLICT_PRESERVE


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        (stage._StageRead(ReadState.MISSING), State.STAGE_MISSING_PRESERVE),
        (stage._StageRead(ReadState.UNSAFE), State.STAGE_UNSAFE_PRESERVE),
        (stage._StageRead(ReadState.REFUSED), State.STAGE_UNSAFE_PRESERVE),
        (
            stage._StageRead(ReadState.OBSERVED, b"wrong", (1, 2)),
            State.STAGE_IMAGE_CONFLICT_PRESERVE,
        ),
        (stage._StageRead(ReadState.OBSERVED, b"", None), State.STAGE_UNSAFE_PRESERVE),
    ],
)
def test_stage_refusals(
    monkeypatch: pytest.MonkeyPatch,
    observed: stage._StageRead,
    expected: stage.PrivateDescriptorStageState,
) -> None:
    _ready(monkeypatch)
    monkeypatch.setattr(stage, "_read_stage", lambda *_: observed)
    result = _review()
    assert result.state is expected
    _inert(result)


def test_stage_identity_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    first = stage._StageRead(ReadState.OBSERVED, _fork().descriptor_after, (1, 2))
    second = stage._StageRead(ReadState.OBSERVED, _fork().descriptor_after, (3, 4))
    results = iter((first, second))
    monkeypatch.setattr(stage, "_read_stage", lambda *_: next(results))
    assert _review().state is State.STAGE_CHANGED_PRESERVE


def test_barrier_rechecked_inside_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    values = iter((True, False))
    monkeypatch.setattr(stage, "_barrier_blocked", lambda *_: next(values))
    assert _review().state is State.BARRIER_UNQUALIFIED


def test_guard_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)

    @contextmanager
    def refuse(*_args: object) -> Iterator[None]:
        raise transition._WriterGuardRefused(
            transition.PrivateTransitionGuardState.GUARD_REFUSED
        )
        yield

    monkeypatch.setattr(
        transition, "_hold_transitionable_journal_descriptor_guard", refuse
    )
    assert _review().state is State.GUARD_REFUSED


def test_interruption(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)

    @contextmanager
    def interrupted(*_args: object) -> Iterator[None]:
        raise KeyboardInterrupt
        yield

    monkeypatch.setattr(
        transition, "_hold_transitionable_journal_descriptor_guard", interrupted
    )
    assert _review().state is State.INTERRUPTED_PRESERVE


def test_codec_failure_before_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    ready = _ready(monkeypatch)
    proposed = _fork()
    monkeypatch.setattr(
        intents,
        "decode_private_transaction_intent",
        lambda _raw: (_ for _ in ()).throw(intents.PrivateIntentError()),
    )
    assert _review(proposed).state is State.INTENT_UNQUALIFIED
    assert ready["guards"] == 0


@pytest.mark.skipif(sys.platform != "linux", reason="native POSIX dirfd test")
def test_linux_descriptor_stage_native_reads(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    directory = root / ".pds"
    directory.mkdir(parents=True)
    name = "." + _fork().witness.transaction_id + ".descriptor-stage"
    stage_path = directory / name
    assert stage._read_linux(root, name).state is ReadState.MISSING
    stage_path.write_bytes(_fork().descriptor_after)
    observed = stage._read_linux(root, name)
    assert observed.state is ReadState.OBSERVED
    assert observed.image == _fork().descriptor_after
    assert observed.identity is not None
    stage_path.unlink()
    stage_path.symlink_to(directory / "missing-file")
    assert stage._read_linux(root, name).state in {ReadState.MISSING, ReadState.REFUSED}


@pytest.mark.skipif(sys.platform != "linux", reason="native POSIX dirfd test")
def test_linux_descriptor_stage_refuses_symlink_and_folder(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    directory = root / ".pds"
    directory.mkdir(parents=True)
    name = "." + _fork().witness.transaction_id + ".descriptor-stage"
    target = tmp_path / "target"
    target.write_bytes(_fork().descriptor_after)
    stage_path = directory / name
    stage_path.symlink_to(target)
    assert stage._read_linux(root, name).state is ReadState.REFUSED
    stage_path.unlink()
    stage_path.mkdir()
    assert stage._read_linux(root, name).state in {ReadState.UNSAFE, ReadState.REFUSED}


def test_stage_identity_and_image_private_repr() -> None:
    data = stage._StageRead(ReadState.OBSERVED, b"SENSITIVE", (1, 2, 3))
    assert "SENSITIVE" not in repr(data)
    outcome = stage._result(State.STAGE_PRESENT_BARRIER_BLOCKED)
    assert "SENSITIVE" not in repr(outcome)
    assert "SENSITIVE" not in outcome.message
    _inert(outcome)
