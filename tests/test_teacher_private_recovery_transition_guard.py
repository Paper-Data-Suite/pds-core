"""Core #238 3G41: production journal/descriptor transition scope (no write)."""

from __future__ import annotations

import hashlib
import inspect
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Callable, Iterator, Literal, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_pre_replace_window as window
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_retained_stage_custody as custody
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_recovery_transition_guard as writer
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = writer.PrivateTransitionGuardState
Step = scratch.PrivateScratchWriterStep
TX = "11111111-1111-4111-8111-111111111111"
ASSOCIATION = "22222222-2222-4222-8222-222222222222"
RAW = b"mock-canonical-journal"
BEFORE = b"mock-registry-before"
AFTER = b"mock-registry-after"
SIDECAR = b"mock-sidecar"
PARENTS: parents._Parents = (
    (1, 101, 0o40700, 10, 20),
    (1, 102, 0o40700, 10, 20),
    (1, 103, 0o40700, 10, 20),
    (1, 104, 0o40700, 10, 20),
)
FILES = (
    (1, 201, len(RAW), 10, 20),
    (1, 202, len(BEFORE), 10, 20),
    (1, 203, len(SIDECAR), 10, 20),
    (1, 204, len(AFTER), 10, 20),
)
IMAGES: parents._Image = (RAW, BEFORE, SIDECAR, AFTER)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _intent() -> intents.PrivateTransactionIntent:
    item = object.__new__(intents.PrivateTransactionIntent)
    evidence = object.__new__(witness.PrivateTransactionWitness)
    for key, value in {
        "operation": witness.PrivateBindingOperation.REBIND_MOVE,
        "transaction_id": TX,
        "association_before": ASSOCIATION,
        "association_after": ASSOCIATION,
        "registry_revision_before": 7,
        "registry_revision_after": 8,
        "descriptor_sha256_before": _sha(SIDECAR),
        "descriptor_sha256_after": _sha(SIDECAR),
        "registry_sha256_before": _sha(BEFORE),
        "registry_sha256_after": _sha(AFTER),
    }.items():
        object.__setattr__(evidence, key, value)
    for key, value in {
        "witness": evidence,
        "registry_before": BEFORE,
        "registry_after": AFTER,
        "descriptor_before": SIDECAR,
        "descriptor_after": SIDECAR,
    }.items():
        object.__setattr__(item, key, value)
    return item


def _description() -> prepared.PrivatePreparedWriteDescription:
    return prepared.PrivatePreparedWriteDescription(
        step=Step.STAGE_TO_REGISTRY,
        binding_operation=witness.PrivateBindingOperation.REBIND_MOVE,
        expected_revision=7,
        resulting_revision=8,
        transaction_id=TX,
        pending_intent_sha256=_sha(RAW),
        registry_before_sha256=_sha(BEFORE),
        staged_registry_sha256=_sha(AFTER),
        descriptor_before_sha256=_sha(SIDECAR),
        descriptor_after_sha256=_sha(SIDECAR),
    )


def _frame(
    *,
    files: object = FILES,
    images: object = IMAGES,
    parents_value: object = PARENTS,
    checkpoint: recovery.PrivatePostcrashReconciliationState = recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
) -> scope._Frame:
    return scope._Frame(
        cast(parents._Parents, parents_value),
        cast(bridge._Census, files),
        cast(parents._Image, images),
        checkpoint,
    )


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    checks: tuple[bool, ...] = (),
    frames: tuple[object, ...] = (),
    guard_release: Exception | None = None,
    stage_release: Exception | None = None,
) -> tuple[intents.PrivateTransactionIntent, list[str]]:
    calls: list[str] = []
    proposed = _intent()
    kind = "windows_token_sid" if sys.platform == "win32" else "posix_euid"
    owner = inspection.EffectiveOSOwner(
        cast(Literal["windows_token_sid", "posix_euid"], kind),
        "S-1-5-21-111-222-333-1001" if sys.platform == "win32" else "1000",
    )
    active, stage = [False], [False]
    check_iter = iter(checks)
    frame_iter = iter(frames)
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda *_: RAW)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: proposed
    )
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ),
    )
    monkeypatch.setattr(
        prepared,
        "describe_private_prepared_stage_write_intent",
        lambda *_: prepared._result(
            prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED,
            _description(),
        ),
    )
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (None, owner))
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: None)
    monkeypatch.setattr(
        recovery, "_namespace", lambda *_: (frozenset({TX}), frozenset({TX}), True)
    )
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: True)
    monkeypatch.setattr(ordered, "_owner", lambda: owner)
    monkeypatch.setattr(parents, "_parents", lambda *_: PARENTS)

    @contextmanager
    def guard(*_args: object) -> Iterator[None]:
        assert not active[0]
        calls.append("guard-enter")
        active[0] = True
        try:
            yield
        finally:
            assert not stage[0]
            active[0] = False
            calls.append("guard-exit")
            if guard_release is not None:
                raise guard_release

    @contextmanager
    def held(*_args: object) -> Iterator[Callable[[], bool]]:
        assert active[0]
        stage[0] = True
        calls.append("stage-enter")

        def check() -> bool:
            assert active[0] and stage[0]
            calls.append("stage-check")
            return next(check_iter, True)

        try:
            yield check
        finally:
            stage[0] = False
            calls.append("stage-exit")
            if stage_release is not None:
                raise stage_release

    def observe(*_args: object) -> scope._Frame:
        assert active[0] and stage[0]
        calls.append("frame")
        return cast(scope._Frame, next(frame_iter, _frame()))

    monkeypatch.setattr(writer, "_hold_transitionable_journal_descriptor_guard", guard)
    monkeypatch.setattr(custody, "_held_stage", held)
    monkeypatch.setattr(scope, "_observe", observe)
    return proposed, calls


def _review(
    item: intents.PrivateTransactionIntent,
    root: Path,
    *,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
) -> writer.PrivateTransitionGuardReview:
    return writer.review_native_transitionable_production_scope(
        step, revision, item, root, root
    )


def test_four_frames_under_transitionable_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    outcome = _review(item, tmp_path)
    assert outcome.state is State.TRANSITION_SCOPE_OBSERVED_NO_WRITE
    assert outcome.pending_evidence_must_remain
    assert outcome.unqualified_requirements == tuple(
        barrier.PrivateProductionWriteRequirement
    )
    assert calls.count("frame") == 4
    assert calls[0] == "guard-enter"
    assert calls[-2:] == ["stage-exit", "guard-exit"]
    assert "non_authorizing=True" in repr(outcome)
    with pytest.raises(FrozenInstanceError):
        setattr(outcome, "state", State.IO_ERROR)


@pytest.mark.parametrize("invalid", [None, False, -1, 0, 7.0, "7", {}, object()])
def test_invalid_revision_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    item, calls = _setup(monkeypatch)
    assert (
        _review(item, tmp_path, revision=cast(int, invalid)).state
        is State.INVALID_REQUEST
    )
    assert not calls


@pytest.mark.parametrize("invalid", [None, 0, True, "stage_to_registry", {}, object()])
def test_invalid_operation_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    item, calls = _setup(monkeypatch)
    assert (
        _review(item, tmp_path, step=cast(Step, invalid)).state is State.INVALID_REQUEST
    )
    assert not calls


@pytest.mark.parametrize(
    "step", [value for value in Step if value is not Step.STAGE_TO_REGISTRY]
)
def test_disallowed_operation_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    item, calls = _setup(monkeypatch)
    assert _review(item, tmp_path, step=step).state is State.OPERATION_NOT_ADMITTED
    assert not calls


@pytest.mark.parametrize("at", range(9))
def test_stage_custody_drift_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    item, calls = _setup(monkeypatch, checks=tuple(i != at for i in range(9)))
    assert _review(item, tmp_path).state is State.STAGE_CHANGED_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


@pytest.mark.parametrize("at", [1, 2, 3])
def test_registry_identity_changes_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    frames = [_frame() for _ in range(4)]
    files = list(FILES)
    old = files[1]
    files[1] = (old[0], old[1] + 99, old[2], old[3], old[4])
    frames[at] = _frame(files=tuple(files))
    item, _ = _setup(monkeypatch, frames=tuple(frames))
    assert _review(item, tmp_path).state is State.PREIMAGE_CONFLICT_PRESERVE


@pytest.mark.parametrize("at", [1, 2, 3])
def test_stage_identity_changes_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    frames = [_frame() for _ in range(4)]
    files = list(FILES)
    old = files[3]
    files[3] = (old[0], old[1] + 99, old[2], old[3], old[4])
    frames[at] = _frame(files=tuple(files))
    item, _ = _setup(monkeypatch, frames=tuple(frames))
    assert _review(item, tmp_path).state is State.PREIMAGE_CONFLICT_PRESERVE


@pytest.mark.parametrize("part", range(4))
def test_byte_image_changes_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    images = list(IMAGES)
    images[part] = b"synthetic-drift"
    item, _ = _setup(monkeypatch, frames=(_frame(images=tuple(images)),))
    assert _review(item, tmp_path).state is State.PREIMAGE_CONFLICT_PRESERVE


def test_registry_stage_alias_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = list(FILES)
    files[3] = files[1]
    item, _ = _setup(monkeypatch, frames=(_frame(files=tuple(files)),))
    assert _review(item, tmp_path).state is State.PREIMAGE_CONFLICT_PRESERVE


def test_namespace_drift_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: False)
    assert _review(item, tmp_path).state is State.NAMESPACE_CONFLICT_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_bad_binding_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(
        preflight,
        "_intent_owner_and_binding",
        lambda *_: preflight.PrivateProductionNativePreflightState.BINDING_MISMATCH,
    )
    assert _review(item, tmp_path).state is State.BINDING_MISMATCH
    assert not calls


def test_bad_owner_protection_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(
        preflight,
        "_native_observation",
        lambda *_: (
            preflight.PrivateProductionNativePreflightState.NATIVE_PROTECTION_REFUSED,
            None,
        ),
    )
    assert _review(item, tmp_path).state is State.OWNER_OR_PROTECTION_REFUSED
    assert not calls


def test_guard_release_failure_never_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(
        monkeypatch, guard_release=writer._WriterGuardRefused(State.GUARD_REFUSED)
    )
    assert _review(item, tmp_path).state is State.GUARD_REFUSED
    assert calls[-1] == "guard-exit"


def test_stage_release_failure_never_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, stage_release=custody._StageChanged())
    assert _review(item, tmp_path).state is State.STAGE_CHANGED_PRESERVE
    assert calls[-1] == "guard-exit"


def test_description_changed_inside_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(
        window, "_description", lambda *_: _description() if not calls else None
    )
    assert _review(item, tmp_path).state is State.DESCRIPTION_CHANGED_PRESERVE
    assert calls[-1] == "guard-exit"


def test_pending_namespace_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(
        recovery, "_namespace", lambda *_: (frozenset(), frozenset(), False)
    )
    assert _review(item, tmp_path).state is State.NAMESPACE_CONFLICT_PRESERVE
    assert calls[-1] == "guard-exit"


def test_interruption_is_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)

    def interrupted(*_args: object) -> scope._Frame:
        raise KeyboardInterrupt

    monkeypatch.setattr(scope, "_observe", interrupted)
    assert _review(item, tmp_path).state is State.INTERRUPTED_PRESERVE
    assert calls[-1] == "guard-exit"


def test_guard_directly_retains_journal_and_descriptor_without_old_registry_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(ordered, "_owner", lambda: owner)

    @contextmanager
    def journal(*_args: object) -> Iterator[None]:
        calls.append("journal-enter")
        try:
            yield
        finally:
            calls.append("journal-exit")

    @contextmanager
    def sidecar(*_args: object) -> Iterator[None]:
        calls.append("sidecar-enter")
        try:
            yield
        finally:
            calls.append("sidecar-exit")

    monkeypatch.setattr(journal_guard, "_hold_existing_retained_journal_guard", journal)
    monkeypatch.setattr(retained, "_held_linux_descriptor", sidecar)
    monkeypatch.setattr(retained, "_held_windows_descriptor", sidecar)
    with writer._hold_transitionable_journal_descriptor_guard(
        tmp_path, tmp_path
    ) as held:
        assert held is None
        calls.append("inside")
    assert calls == [
        "journal-enter",
        "sidecar-enter",
        "inside",
        "sidecar-exit",
        "journal-exit",
    ]


def test_guard_direct_refuses_owner_change_on_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = inspection.EffectiveOSOwner("posix_euid", "1000")
    other = inspection.EffectiveOSOwner("posix_euid", "1001")
    calls = [0]
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    def effective() -> inspection.EffectiveOSOwner:
        calls[0] += 1
        return first if calls[0] < 3 else other

    monkeypatch.setattr(ordered, "_owner", effective)

    @contextmanager
    def passthrough(*_args: object) -> Iterator[None]:
        yield

    monkeypatch.setattr(
        journal_guard, "_hold_existing_retained_journal_guard", passthrough
    )
    monkeypatch.setattr(retained, "_held_linux_descriptor", passthrough)
    monkeypatch.setattr(retained, "_held_windows_descriptor", passthrough)
    with pytest.raises(writer._WriterGuardRefused) as found:
        with writer._hold_transitionable_journal_descriptor_guard(tmp_path, tmp_path):
            pass
    assert found.value.state is State.OWNER_CHANGED


@pytest.mark.parametrize("kind", list(State))
def test_sanitized_outcomes(kind: State) -> None:
    result = writer._result(kind)
    assert result.pending_evidence_must_remain
    assert "non_authorizing=True" in repr(result)
    assert "C:" not in result.message and "/tmp/" not in result.message
    for forbidden in (
        "path",
        "handle",
        "owner",
        "permit",
        "write_operation",
        "callback",
    ):
        assert not hasattr(result, forbidden)


def test_no_production_mutation_reachable() -> None:
    source = inspect.getsource(writer)
    public = inspect.signature(writer.review_native_transitionable_production_scope)
    assert tuple(public.parameters) == (
        "step",
        "expected_revision",
        "proposed",
        "existing_private_root",
        "existing_workspace_root",
    )
    for action in (
        "os.replace(",
        "os.rename(",
        "os.fsync(",
        "mkdir(",
        ".unlink(",
        "TemporaryDirectory(",
    ):
        assert action not in source
    assert "_hold_existing_retained_registry_guard(" not in source
    assert not any(
        hasattr(writer, name)
        for name in (
            "execute",
            "commit",
            "write_registry",
            "retire_journal",
            "authorize_writer",
        )
    )
