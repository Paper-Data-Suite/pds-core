"""Core #238 3G37: held stage and destination evidence, no production writes."""

from __future__ import annotations

import inspect
import os
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
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_retained_stage_custody as custody
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = custody.PrivateRetainedStageCustodyState
Step = scratch.PrivateScratchWriterStep
TX = "11111111-1111-4111-8111-111111111111"
RAW = b"canonical-pending-journal"
BEFORE = b"canonical-registry-before"
AFTER = b"canonical-registry-after"
SIDECAR = b"canonical-sidecar"
_STAMPS: parents._Parents = (
    (1, 101, 0o40700, 10, 20),
    (1, 102, 0o40700, 10, 20),
    (1, 103, 0o40700, 10, 20),
    (1, 104, 0o40700, 10, 20),
)


def _intent() -> intents.PrivateTransactionIntent:
    item = object.__new__(intents.PrivateTransactionIntent)
    w = object.__new__(witness.PrivateTransactionWitness)
    for key, value in {
        "operation": witness.PrivateBindingOperation.REBIND_MOVE,
        "transaction_id": TX,
        "association_before": "22222222-2222-4222-8222-222222222222",
        "association_after": "22222222-2222-4222-8222-222222222222",
        "registry_revision_before": 7,
        "registry_revision_after": 8,
        "descriptor_sha256_before": "1" * 64,
        "descriptor_sha256_after": "1" * 64,
        "registry_sha256_before": "2" * 64,
        "registry_sha256_after": "3" * 64,
    }.items():
        object.__setattr__(w, key, value)
    for key, value in {
        "witness": w,
        "registry_before": BEFORE,
        "registry_after": AFTER,
        "descriptor_before": SIDECAR,
        "descriptor_after": SIDECAR,
    }.items():
        object.__setattr__(item, key, value)
    return item


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    workspace: Path,
    *,
    stage_checks: tuple[bool, ...] = (),
    frames: tuple[scope._Frame, ...] = (),
    guard_release: Exception | None = None,
    stage_release: Exception | None = None,
) -> tuple[intents.PrivateTransactionIntent, list[str]]:
    calls: list[str] = []
    item = _intent()
    kind: Literal["windows_token_sid", "posix_euid"] = (
        "windows_token_sid" if sys.platform == "win32" else "posix_euid"
    )
    owner = inspection.EffectiveOSOwner(
        kind, "S-1-5-21-111-222-333-1001" if sys.platform == "win32" else "1000"
    )
    active = [False]
    stage_active = [False]
    checks = iter(stage_checks)
    frame_iterator = iter(frames)
    default_frame = scope._Frame(
        _STAMPS,
        (
            (1, 201, len(RAW), 10, 20),
            (1, 202, len(BEFORE), 10, 20),
            (1, 203, len(SIDECAR), 10, 20),
            (1, 204, len(AFTER), 10, 20),
        ),
        (RAW, BEFORE, SIDECAR, AFTER),
        recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
    )
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda *_: RAW)
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda *_: item)
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ),
    )
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (None, owner))
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: None)

    @contextmanager
    def guard(*_args: object) -> Iterator[None]:
        calls.append("guard-enter")
        assert not active[0]
        active[0] = True
        try:
            yield
        finally:
            assert not stage_active[0]
            active[0] = False
            calls.append("guard-exit")
            if guard_release:
                raise guard_release

    @contextmanager
    def hold_stage(*_args: object) -> Iterator[Callable[[], bool]]:
        assert active[0]
        stage_active[0] = True
        calls.append("stage-enter")

        def check() -> bool:
            assert active[0] and stage_active[0]
            calls.append("stage-check")
            return next(checks, True)

        try:
            yield check
        finally:
            stage_active[0] = False
            calls.append("stage-exit")
            if stage_release:
                raise stage_release

    def observe(*_args: object) -> scope._Frame:
        assert active[0] and stage_active[0]
        calls.append("frame")
        return next(frame_iterator, default_frame)

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)
    monkeypatch.setattr(custody, "_held_stage", hold_stage)
    monkeypatch.setattr(scope, "_observe", observe)
    monkeypatch.setattr(
        recovery, "_namespace", lambda *_: (frozenset(), frozenset(), True)
    )
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: True)
    monkeypatch.setattr(ordered, "_owner", lambda: owner)
    monkeypatch.setattr(parents, "_parents", lambda *_: _STAMPS)
    return item, calls


def _review(
    item: intents.PrivateTransactionIntent,
    root: Path,
    workspace: Path,
    *,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
) -> custody.PrivateRetainedStageCustodyReview:
    return custody.review_retained_production_stage_and_destination(
        step, revision, item, root, workspace
    )


def test_three_frames_inside_single_native_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, workspace = tmp_path / "private", tmp_path / "workspace"
    intent, calls = _setup(monkeypatch, root, workspace)
    result = _review(intent, root, workspace)
    assert result.state is State.STAGE_AND_DESTINATION_OBSERVED_NO_WRITE
    assert calls.count("frame") == 3
    assert calls.count("stage-check") == 7
    assert calls[0] == "guard-enter"
    assert calls[-2:] == ["stage-exit", "guard-exit"]
    assert result.unqualified_requirements == tuple(
        barrier.PrivateProductionWriteRequirement
    )
    assert "non_authorizing=True" in repr(result)
    assert not any(
        hasattr(result, key)
        for key in (
            "handle",
            "path",
            "owner",
            "token",
            "write",
            "execute",
            "callback",
            "bytes",
        )
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.INVALID_REQUEST)


@pytest.mark.parametrize("value", [None, False, -1, 0, 7.0, "7", {}, object()])
def test_invalid_revision_refused_without_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: object
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    result = _review(item, tmp_path, tmp_path, revision=cast(int, value))
    assert result.state is State.INVALID_REQUEST
    assert not calls


@pytest.mark.parametrize("value", [None, False, 7, "stage_to_registry", {}, object()])
def test_invalid_step_refused_without_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: object
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    result = _review(item, tmp_path, tmp_path, step=cast(Step, value))
    assert result.state is State.INVALID_REQUEST
    assert not calls


@pytest.mark.parametrize("other", [x for x in Step if x is not Step.STAGE_TO_REGISTRY])
def test_other_operations_never_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, other: Step
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    result = _review(item, tmp_path, tmp_path, step=other)
    assert result.state is State.OPERATION_NOT_ADMITTED
    assert not calls


@pytest.mark.parametrize("field", ["private", "workspace"])
def test_invalid_root_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    monkeypatch.setattr(
        lock_file if field == "private" else descriptor,
        "_requested_root" if field == "private" else "_valid_root",
        lambda *_: False,
    )
    assert _review(item, tmp_path, tmp_path).state is State.ROOT_UNQUALIFIED
    assert not calls


@pytest.mark.parametrize("state", list(State))
def test_sanitized_states(state: State) -> None:
    message = custody._result(state).message
    assert "C:" not in message and "/tmp/" not in message
    assert "non_authorizing=True" in repr(custody._result(state))


@pytest.mark.parametrize("at", [0, 1, 2, 3, 4, 5, 6])
def test_stage_drift_fails_closed_and_releases_all_handles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    flags = tuple(i != at for i in range(7))
    item, calls = _setup(monkeypatch, tmp_path, tmp_path, stage_checks=flags)
    result = _review(item, tmp_path, tmp_path)
    assert result.state is State.STAGE_CHANGED_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_stage_release_error_does_not_return_positive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(
        monkeypatch, tmp_path, tmp_path, stage_release=custody._StageChanged()
    )
    assert _review(item, tmp_path, tmp_path).state is State.STAGE_CHANGED_PRESERVE
    assert calls[-1] == "guard-exit"


def test_guard_release_error_does_not_return_positive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(
        monkeypatch,
        tmp_path,
        tmp_path,
        guard_release=retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
        ),
    )
    assert _review(item, tmp_path, tmp_path).state is State.GUARD_REFUSED
    assert calls[-1] == "guard-exit"


def test_bad_exact_stage_image_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = scope._Frame(
        _STAMPS,
        (
            (1, 201, len(RAW), 10, 20),
            (1, 202, len(BEFORE), 10, 20),
            (1, 203, len(SIDECAR), 10, 20),
            (1, 204, len(AFTER), 10, 20),
        ),
        (RAW, BEFORE, SIDECAR, b"altered"),
        recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
    )
    item, calls = _setup(monkeypatch, tmp_path, tmp_path, frames=(original,))
    assert _review(item, tmp_path, tmp_path).state is State.IMAGE_CONFLICT_PRESERVE
    assert calls[-1] == "guard-exit"


def test_native_stage_context_is_not_public_permission() -> None:
    source = inspect.getsource(custody)
    for fragment in ("os.replace(", "os.rename(", "unlink(", "os.fsync(", "mkdir("):
        assert fragment not in source
    signature = inspect.signature(
        custody.review_retained_production_stage_and_destination
    )
    assert not any(
        name in signature.parameters
        for name in ("callback", "write", "permit", "token", "stage_handle", "guard")
    )
    assert not hasattr(custody, "commit_registry")
    assert not hasattr(custody, "retire_journal")


def test_noncanonical_stage_component_rejected() -> None:
    for invalid in ("../foo", "x" * 200, "foo/bar", "ABC", "not-valid-uuid"):
        with pytest.raises(custody._StageRefused):
            custody._stage_name(invalid)
    assert custody._stage_name(TX) == "." + TX + ".registry-stage"


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux file-descriptor test")
def test_linux_stage_handle_detects_entry_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Synthetic data only. Exercise the held descriptor and exact path identity.
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    name = "." + TX + ".registry-stage"
    stage = root / name
    stage.write_bytes(b"synthetic-after")
    stage.chmod(0o600)
    uid = getattr(os, "geteuid", lambda: -1)()
    if uid <= 0:
        pytest.skip("POSIX root principal is not qualified by Core")
    monkeypatch.setattr(
        posix,
        "_open_verified_parent",
        lambda path, _uid: (os.open(path, os.O_RDONLY), None),
    )
    monkeypatch.setattr(posix, "_acl_absent", lambda *_: None)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda *_: True)
    owner = inspection.EffectiveOSOwner("posix_euid", str(uid))
    with pytest.raises(custody._StageChanged):
        with custody._held_linux_stage(
            root, name, owner, len(b"synthetic-after")
        ) as check:
            assert check()
            stage.unlink()
            stage.write_bytes(b"synthetic-after")
            stage.chmod(0o600)
            assert not check()


def test_barrier_rejection_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ),
    )
    assert _review(item, tmp_path, tmp_path).state is State.REVISION_MISMATCH_REFUSED
    assert not calls


def test_native_protection_refusal_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (object(), None))
    assert _review(item, tmp_path, tmp_path).state is State.NATIVE_PROTECTION_REFUSED
    assert not calls


def test_binding_mismatch_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: object())
    assert _review(item, tmp_path, tmp_path).state is State.BINDING_MISMATCH
    assert not calls


def test_inner_canonical_intent_drift_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    values = iter((item, object()))
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: next(values)
    )
    assert _review(item, tmp_path, tmp_path).state is State.INTENT_UNQUALIFIED
    assert calls == ["guard-enter", "guard-exit"]


def test_stage_open_refusal_maps_to_safe_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)

    @contextmanager
    def refuse(*_args: object) -> Iterator[Callable[[], bool]]:
        raise custody._StageRefused
        yield lambda: True

    monkeypatch.setattr(custody, "_held_stage", refuse)
    assert _review(item, tmp_path, tmp_path).state is State.STAGE_CUSTODY_REFUSED
    assert calls == ["guard-enter", "guard-exit"]


def test_namespace_drift_inside_held_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    values = iter((True, False))
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: next(values))
    assert _review(item, tmp_path, tmp_path).state is State.NAMESPACE_CONFLICT_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_native_owner_change_inside_held_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)
    calls_seen = [0]
    observed = preflight._native_observation

    def change(
        root: Path,
        expected_owner: inspection.EffectiveOSOwner | None = None,
    ) -> tuple[
        preflight.PrivateProductionNativePreflightState | None,
        inspection.EffectiveOSOwner | None,
    ]:
        calls_seen[0] += 1
        return (None, None) if calls_seen[0] == 2 else observed(root, expected_owner)

    monkeypatch.setattr(preflight, "_native_observation", change)
    assert _review(item, tmp_path, tmp_path).state is State.OWNER_CHANGED
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_native_observer_interruption_releases_handles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, calls = _setup(monkeypatch, tmp_path, tmp_path)

    def interrupt(*_args: object) -> scope._Frame:
        raise KeyboardInterrupt

    monkeypatch.setattr(scope, "_observe", interrupt)
    assert _review(item, tmp_path, tmp_path).state is State.INTERRUPTED_PRESERVE
    assert calls[-2:] == ["stage-exit", "guard-exit"]


def test_no_caller_controlled_native_handle_in_api() -> None:
    params = inspect.signature(
        custody.review_retained_production_stage_and_destination
    ).parameters
    assert tuple(params) == (
        "step",
        "expected_revision",
        "proposed",
        "existing_private_root",
        "existing_workspace_root",
    )
    assert "os.replace(" not in inspect.getsource(custody)
