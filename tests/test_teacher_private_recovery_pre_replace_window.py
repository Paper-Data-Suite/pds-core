"""Core #238 3G38: no-op operation boundary under retained native custody."""

from __future__ import annotations

import hashlib
import inspect
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
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
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = window.PrivatePreReplaceWindowState
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

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)
    monkeypatch.setattr(custody, "_held_stage", held)
    monkeypatch.setattr(scope, "_observe", observe)
    return proposed, calls


def _review(
    item: intents.PrivateTransactionIntent,
    root: Path,
    *,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
) -> window.PrivatePreReplaceWindowReview:
    return window.review_protected_pre_replace_window(step, revision, item, root, root)


def test_four_frames_single_scope_after_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    result = _review(item, tmp_path)
    assert result.state is State.NO_OP_BOUNDARY_OBSERVED_NO_WRITE
    assert calls.count("frame") == 4
    assert calls.count("stage-check") == 9
    assert calls[0] == "guard-enter"
    assert calls[-2:] == ["stage-exit", "guard-exit"]
    assert result.unqualified_requirements == tuple(
        barrier.PrivateProductionWriteRequirement
    )
    assert "non_authorizing=True" in repr(result)
    for name in (
        "handle",
        "path",
        "owner",
        "token",
        "permit",
        "write",
        "execute",
        "bytes",
        "callback",
    ):
        assert not hasattr(result, name)
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


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
def test_invalid_step_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    item, calls = _setup(monkeypatch)
    assert (
        _review(item, tmp_path, step=cast(Step, invalid)).state is State.INVALID_REQUEST
    )
    assert not calls


@pytest.mark.parametrize("step", [x for x in Step if x is not Step.STAGE_TO_REGISTRY])
def test_other_operations_not_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    item, calls = _setup(monkeypatch)
    assert _review(item, tmp_path, step=step).state is State.OPERATION_NOT_ADMITTED
    assert not calls


@pytest.mark.parametrize("at", range(9))
def test_stage_drift_at_every_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    flags = tuple(i != at for i in range(9))
    item, calls = _setup(monkeypatch, checks=flags)
    assert _review(item, tmp_path).state is State.STAGE_CHANGED_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


@pytest.mark.parametrize("at", [1, 2, 3])
def test_stage_identity_drift_in_any_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    frames = [_frame() for _ in range(4)]
    bad = list(FILES)
    old = bad[3]
    bad[3] = (old[0], old[1] + 2, old[2], old[3], old[4])
    frames[at] = _frame(files=tuple(bad))
    item, _ = _setup(monkeypatch, frames=tuple(frames))
    assert _review(item, tmp_path).state is State.STAGE_CHANGED_PRESERVE


@pytest.mark.parametrize("at", [1, 2, 3])
def test_registry_identity_drift_by_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    frames = [_frame() for _ in range(4)]
    bad = list(FILES)
    old = bad[1]
    bad[1] = (old[0], old[1] + 20, old[2], old[3], old[4])
    frames[at] = _frame(files=tuple(bad))
    item, _ = _setup(monkeypatch, frames=tuple(frames))
    assert _review(item, tmp_path).state is State.DESTINATION_CHANGED_PRESERVE


@pytest.mark.parametrize("part", [0, 2])
def test_journal_or_descriptor_id_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    files = list(FILES)
    old = files[part]
    files[part] = (old[0], old[1] + 20, old[2], old[3], old[4])
    item, _ = _setup(monkeypatch, frames=(_frame(), _frame(files=tuple(files))))
    assert _review(item, tmp_path).state is State.FILE_CHANGED_PRESERVE


def test_registry_stage_alias_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = list(FILES)
    files[3] = files[1]
    item, _ = _setup(monkeypatch, frames=(_frame(files=tuple(files)),))
    assert _review(item, tmp_path).state is State.STAGE_CHANGED_PRESERVE


@pytest.mark.parametrize("part", range(4))
def test_image_conflict_any_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    images = list(IMAGES)
    images[part] = b"wrong-image"
    item, _ = _setup(monkeypatch, frames=(_frame(images=tuple(images)),))
    assert _review(item, tmp_path).state is State.IMAGE_CONFLICT_PRESERVE


def test_checkpoint_refusal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item, _ = _setup(
        monkeypatch,
        frames=(
            _frame(
                checkpoint=recovery.PrivatePostcrashReconciliationState.OWNER_CHANGED
            ),
        ),
    )
    assert _review(item, tmp_path).state is State.CHECKPOINT_CONFLICT_PRESERVE


def test_description_drift_at_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    count = [0]
    original = prepared.describe_private_prepared_stage_write_intent

    def describe(
        step: Step, revision: int, intent: intents.PrivateTransactionIntent
    ) -> prepared.PrivatePreparedWriteIntentReview:
        count[0] += 1
        result = original(step, revision, intent)
        if count[0] == 3:
            return prepared._result(
                prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED,
                replace(_description(), staged_registry_sha256="0" * 64),
            )
        return result

    monkeypatch.setattr(
        prepared, "describe_private_prepared_stage_write_intent", describe
    )
    assert _review(item, tmp_path).state is State.DESCRIPTION_CHANGED_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_inner_decode_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item, calls = _setup(monkeypatch)
    values = iter((item, object()))
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: next(values)
    )
    assert _review(item, tmp_path).state is State.INTENT_UNQUALIFIED
    assert calls == ["guard-enter", "guard-exit"]


def test_barrier_refuses_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ),
    )
    assert _review(item, tmp_path).state is State.REVISION_MISMATCH_REFUSED
    assert not calls


def test_native_protection_refusal_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (object(), None))
    assert _review(item, tmp_path).state is State.NATIVE_PROTECTION_REFUSED
    assert not calls


def test_binding_refusal_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: object())
    assert _review(item, tmp_path).state is State.BINDING_MISMATCH
    assert not calls


def test_stage_open_refusal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item, calls = _setup(monkeypatch)

    @contextmanager
    def refuse(*args: object) -> Iterator[Callable[[], bool]]:
        raise custody._StageRefused
        yield lambda: True

    monkeypatch.setattr(custody, "_held_stage", refuse)
    assert _review(item, tmp_path).state is State.STAGE_CUSTODY_REFUSED
    assert calls == ["guard-enter", "guard-exit"]


def test_stage_guard_release_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, stage_release=custody._StageChanged())
    assert _review(item, tmp_path).state is State.STAGE_CHANGED_PRESERVE
    assert calls[-1] == "guard-exit"


def test_parent_guard_release_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(
        monkeypatch,
        guard_release=retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
        ),
    )
    assert _review(item, tmp_path).state is State.GUARD_REFUSED
    assert calls[-1] == "guard-exit"


def test_namespace_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item, calls = _setup(monkeypatch)
    seen = [0]

    def same(*args: object) -> bool:
        seen[0] += 1
        return seen[0] != 7

    monkeypatch.setattr(operation, "_same_native_namespace", same)
    assert _review(item, tmp_path).state is State.NAMESPACE_CONFLICT_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_owner_change(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    item, calls = _setup(monkeypatch)
    seen = [0]
    original = preflight._native_observation

    def changed(
        root: Path, expected_owner: inspection.EffectiveOSOwner | None = None
    ) -> tuple[
        preflight.PrivateProductionNativePreflightState | None,
        inspection.EffectiveOSOwner | None,
    ]:
        seen[0] += 1
        if seen[0] == 5:
            return None, None
        return original(root, expected_owner)

    monkeypatch.setattr(preflight, "_native_observation", changed)
    assert _review(item, tmp_path).state is State.OWNER_CHANGED
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_interrupt_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)

    def interrupted(*args: object) -> scope._Frame:
        raise KeyboardInterrupt

    monkeypatch.setattr(scope, "_observe", interrupted)
    assert _review(item, tmp_path).state is State.INTERRUPTED_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


@pytest.mark.parametrize("state", list(State))
def test_sanitized_statuses(state: State) -> None:
    report = window._result(state)
    assert "C:" not in report.message and "/tmp/" not in report.message
    assert "non_authorizing=True" in repr(report)


def test_no_execution_or_callback_api() -> None:
    source = inspect.getsource(window)
    signature = inspect.signature(window.review_protected_pre_replace_window)
    assert tuple(signature.parameters) == (
        "step",
        "expected_revision",
        "proposed",
        "existing_private_root",
        "existing_workspace_root",
    )
    for forbidden in (
        "os.replace(",
        "os.rename(",
        "unlink(",
        "os.fsync(",
        "mkdir(",
        "TemporaryDirectory(",
    ):
        assert forbidden not in source
    assert not any(
        hasattr(window, name)
        for name in (
            "execute",
            "commit_registry",
            "retire_journal",
            "authorize_writer",
            "open_writable",
        )
    )


@pytest.mark.parametrize("field", ["private", "workspace"])
def test_invalid_root_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str
) -> None:
    item, calls = _setup(monkeypatch)
    if field == "private":
        monkeypatch.setattr(lock_file, "_requested_root", lambda *_: False)
    else:
        monkeypatch.setattr(descriptor, "_valid_root", lambda *_: False)
    assert _review(item, tmp_path).state is State.ROOT_UNQUALIFIED
    assert not calls


def test_initial_description_refusal_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    monkeypatch.setattr(
        prepared,
        "describe_private_prepared_stage_write_intent",
        lambda *_: prepared._result(
            prepared.PrivatePreparedWriteIntentState.INVALID_REQUEST
        ),
    )
    assert _review(item, tmp_path).state is State.INTENT_UNQUALIFIED
    assert not calls


def test_noncanonical_codec_refusal_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)

    def refuse(*_args: object) -> bytes:
        raise intents.PrivateIntentError

    monkeypatch.setattr(intents, "encode_private_transaction_intent", refuse)
    assert _review(item, tmp_path).state is State.IO_ERROR
    assert not calls


def test_owner_changes_at_final_scope_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    seen = [0]
    original = preflight._native_observation

    def changed(
        root: Path, expected_owner: inspection.EffectiveOSOwner | None = None
    ) -> tuple[
        preflight.PrivateProductionNativePreflightState | None,
        inspection.EffectiveOSOwner | None,
    ]:
        seen[0] += 1
        if seen[0] == 6:
            return None, None
        return original(root, expected_owner)

    monkeypatch.setattr(preflight, "_native_observation", changed)
    assert _review(item, tmp_path).state is State.OWNER_CHANGED
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_stage_custody_always_outlives_fourth_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch)
    assert _review(item, tmp_path).state is State.NO_OP_BOUNDARY_OBSERVED_NO_WRITE
    assert calls.index("stage-enter") < calls.index("frame")
    assert calls.index("stage-exit") > max(
        index for index, name in enumerate(calls) if name == "frame"
    )
    assert calls.index("guard-exit") > calls.index("stage-exit")


def test_no_prior_review_or_explicit_permission_controls() -> None:
    params = inspect.signature(window.review_protected_pre_replace_window).parameters
    assert "prior" not in params
    assert "ready" not in params
    assert "approved" not in params
    assert "write" not in params
    assert "callback" not in params
    assert "permit" not in params
    assert "handle" not in params
