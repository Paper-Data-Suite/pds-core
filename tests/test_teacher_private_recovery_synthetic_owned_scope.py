"""#238 Slice 3G29: native parent HANDLE custody within one synthetic writer scope."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Callable, Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_owned_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_recovery_writer_sequence as sequence

State = scope.PrivateOwnedScopeState
Fault = scope.PrivateOwnedScopeFault
Step = admission.PrivateScratchWriterStep


def _go(
    step: Step = Step.STAGE_TO_REGISTRY,
    fault: Fault = Fault.NONE,
) -> scope.PrivateOwnedScopeReview:
    return scope.rehearse_synthetic_native_writer_owned_scope(step, fault)


def test_real_native_scratch_held_parent_replace_succeeds() -> None:
    result = _go()
    assert result.state is State.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED
    assert "no production" in result.message
    assert "durability" in result.message


@pytest.mark.parametrize("step", [s for s in Step if s is not Step.STAGE_TO_REGISTRY])
def test_unsupported_operations_do_not_allocate_scratch(
    monkeypatch: pytest.MonkeyPatch, step: Step
) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("should not allocate scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", deny)
    assert _go(step).state is State.OPERATION_NOT_ADMITTED


@pytest.mark.parametrize(
    "invalid", [None, False, True, 1, "stage_to_registry", {}, (), object()]
)
def test_invalid_step_refused_before_allocating(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("should not allocate scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", deny)
    assert _go(cast(Step, invalid)).state is State.INVALID_REQUEST


@pytest.mark.parametrize("invalid", [None, True, 0, "none", {}, [], object()])
def test_invalid_fault_refused_before_allocating(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("should not allocate scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", deny)
    assert _go(fault=cast(Fault, invalid)).state is State.INVALID_REQUEST


def test_unsupported_platform_refuses_without_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "unsupported")

    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no scratch on unsupported OS")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", deny)
    assert _go().state is State.UNSUPPORTED


@pytest.mark.parametrize("point", [f for f in Fault if f is not Fault.NONE])
def test_each_interrupt_cannot_admit_operation(point: Fault) -> None:
    assert _go(fault=point).state is State.INTERRUPTED_PRESERVE


@pytest.mark.parametrize(
    "point",
    [
        Fault.AFTER_GUARD,
        Fault.AFTER_PARENT_RETAINED,
        Fault.AFTER_PREIMAGE,
        Fault.AFTER_READER_RELEASE,
        Fault.AFTER_FINAL_CHECK,
    ],
)
def test_preoperation_interruption_does_not_replace(
    monkeypatch: pytest.MonkeyPatch, point: Fault
) -> None:
    calls = [0]

    def deny(*_args: object, **_kwargs: object) -> None:
        calls[0] += 1
        raise AssertionError("replace ran too early")

    monkeypatch.setattr(os, "replace", deny)
    assert _go(fault=point).state is State.INTERRUPTED_PRESERVE
    assert calls == [0]


def test_native_parent_handle_stays_held_across_replacement_and_final_recheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    parent_active = [False]
    lock_active = [False]
    original_parent = scope._held_native_parent
    original_lock = scratch._scratch_lock
    original_replace = os.replace
    original_postimage = scope._postimage

    @contextmanager
    def tracked_parent(root: Path) -> Iterator[Callable[[], bool]]:
        assert lock_active[0]
        with original_parent(root) as probe:
            parent_active[0] = True
            events.append("parent-acquire")
            try:
                yield probe
            finally:
                assert probe()
                parent_active[0] = False
                events.append("parent-release")

    @contextmanager
    def tracked_lock(path: Path) -> Iterator[None]:
        with original_lock(path):
            lock_active[0] = True
            events.append("guard-acquire")
            try:
                yield
            finally:
                assert not parent_active[0]
                lock_active[0] = False
                events.append("guard-release")

    def replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        assert parent_active[0] and lock_active[0]
        events.append("replace")
        original_replace(source, target)

    def postimage(
        root: Path,
        before: identity._IdentitySet,
        lock_id: identity._FileID,
        parent: tuple[int, int],
        probe: Callable[[], bool],
    ) -> State | None:
        assert parent_active[0] and lock_active[0] and probe()
        events.append("postimage")
        return original_postimage(root, before, lock_id, parent, probe)

    monkeypatch.setattr(scope, "_held_native_parent", tracked_parent)
    monkeypatch.setattr(scratch, "_scratch_lock", tracked_lock)
    monkeypatch.setattr(scope, "_postimage", postimage)
    monkeypatch.setattr(os, "replace", replace)
    assert _go().state is State.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED
    assert events == [
        "guard-acquire",
        "parent-acquire",
        "replace",
        "postimage",
        "postimage",
        "parent-release",
        "guard-release",
    ]


def test_parent_custody_refusal_prevents_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bad(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("replace must not execute")

    @contextmanager
    def failed(_root: Path) -> Iterator[Callable[[], bool]]:
        raise scope._ParentUnqualified
        yield lambda: False

    monkeypatch.setattr(scope, "_held_native_parent", failed)
    monkeypatch.setattr(os, "replace", bad)
    assert _go().state is State.PARENT_IDENTITY_CONFLICT_PRESERVE


def test_parent_path_handle_mismatch_prevents_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = scope._held_native_parent

    @contextmanager
    def wrong(root: Path) -> Iterator[Callable[[], bool]]:
        with original(root):
            yield lambda: False

    monkeypatch.setattr(scope, "_held_native_parent", wrong)
    assert _go().state is State.PARENT_IDENTITY_CONFLICT_PRESERVE


def test_native_parent_path_identity_is_stable_during_scratch_replacement(
    tmp_path: Path,
) -> None:
    with scope._held_native_parent(tmp_path) as matches:
        assert matches()
        (tmp_path / "a").write_bytes(b"a")
        (tmp_path / "b").write_bytes(b"b")
        os.replace(tmp_path / "a", tmp_path / "b")
        assert matches()
    assert not (tmp_path / "a").exists()
    assert (tmp_path / "b").read_bytes() == b"a"


def test_restrictive_reader_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admission, "_read_once", lambda *_: False)
    assert _go().state is State.READER_CONFLICT_PRESERVE


def test_mutation_not_invoked_before_reader_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader_open = [False]
    original_read = admission._read_once
    original_replace = os.replace

    def read(
        root: Path, file_id: identity._FileID, step: admission.PrivateScratchWriterFault
    ) -> bool:
        reader_open[0] = True
        try:
            return original_read(root, file_id, step)
        finally:
            reader_open[0] = False

    def replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        assert not reader_open[0]
        original_replace(source, target)

    monkeypatch.setattr(admission, "_read_once", read)
    monkeypatch.setattr(os, "replace", replace)
    assert _go().state is State.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED


def test_preimage_drift_after_reader_release(monkeypatch: pytest.MonkeyPatch) -> None:
    original = scope._preimage
    calls = [0]

    def drift(
        root: Path,
        before: identity._IdentitySet,
        lock_id: identity._FileID,
        parent: tuple[int, int],
        probe: Callable[[], bool],
    ) -> bool:
        calls[0] += 1
        return (
            original(root, before, lock_id, parent, probe) if calls[0] == 1 else False
        )

    monkeypatch.setattr(scope, "_preimage", drift)
    assert _go().state is State.ADMISSION_DRIFT_PRESERVE
    assert calls[0] == 2


def test_native_replace_denied_preserves_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("synthetic share denial")

    monkeypatch.setattr(os, "replace", refuse)
    assert _go().state is State.REPLACEMENT_REFUSED_PRESERVE


def test_unexpected_native_replace_error_is_not_sharing_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("not a sharing refusal")

    monkeypatch.setattr(os, "replace", refuse)
    assert _go().state is State.IO_ERROR


@pytest.mark.parametrize(
    "filename",
    [
        scratch._REGISTRY,
        scratch._STAGE,
        "descriptor.json",
        "transactions.json",
    ],
)
def test_corrupt_preimage_stops_before_replacement(
    monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    actual = scratch._write_new

    def corrupt(root: Path, name: str, data: bytes) -> None:
        actual(root, name, data + (b"corrupt" if name == filename else b""))

    monkeypatch.setattr(scratch, "_write_new", corrupt)
    assert _go().state is State.PREIMAGE_REFUSED


@pytest.mark.parametrize(
    "filename", [scratch._REGISTRY, "descriptor.json", "transactions.json"]
)
def test_corrupt_postimage_cannot_qualify(
    monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    real = os.replace

    def corrupt(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        real(source, target)
        (Path(target).parent / filename).write_bytes(b"corrupt")

    monkeypatch.setattr(os, "replace", corrupt)
    assert _go().state is State.POSTIMAGE_CONFLICT_PRESERVE


def test_native_file_identity_drift_after_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = identity._identities
    calls = [0]

    def changed(root: Path, *, stage: bool) -> identity._IdentitySet:
        result = real(root, stage=stage)
        calls[0] += 1
        if not stage:
            return (
                (result[0][0], result[0][1] + 12345),
                result[1],
                result[2],
                result[3],
            )
        return result

    monkeypatch.setattr(identity, "_identities", changed)
    assert _go().state is State.FILE_IDENTITY_CONFLICT_PRESERVE
    assert calls[0] > 1


def test_parent_drift_after_replace_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    original = scope._held_native_parent

    @contextmanager
    def drifting(root: Path) -> Iterator[Callable[[], bool]]:
        with original(root) as probe:
            calls = [0]

            def read() -> bool:
                calls[0] += 1
                return probe() if calls[0] < 10 else False

            yield read

    monkeypatch.setattr(scope, "_held_native_parent", drifting)
    assert _go().state is State.PARENT_IDENTITY_CONFLICT_PRESERVE


def test_sync_failure_does_not_return_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_root: Path) -> None:
        raise OSError("synthetic sync failure")

    monkeypatch.setattr(scratch, "_sync_target", refuse)
    assert _go().state is State.IO_ERROR


def test_sequence_conflict_refuses_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sequence, "_ordered", lambda *_: False)
    assert _go().state is State.POSTIMAGE_CONFLICT_PRESERVE


def test_native_lock_failure_prevents_parent_and_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def locked(_path: Path) -> Iterator[None]:
        raise scratch._GuardRefused
        yield

    monkeypatch.setattr(scratch, "_scratch_lock", locked)
    assert _go().state is State.NATIVE_GUARD_REFUSED


def test_keyboard_interrupt_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupted)
    assert _go().state is State.INTERRUPTED_PRESERVE


@pytest.mark.parametrize("value", list(State))
def test_result_sanitized_frozen_and_never_a_permit(value: State) -> None:
    review = scope._result(value)
    assert review.state is value
    assert review.message
    assert not any(
        hasattr(review, field)
        for field in ("path", "root", "handle", "bytes", "permit", "token", "owner")
    )
    assert "C:/" not in review.message and "/tmp/" not in review.message
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.INVALID_REQUEST)


def test_public_api_does_not_accept_paths_bytes_callbacks_or_native_handles() -> None:
    names = list(
        inspect.signature(scope.rehearse_synthetic_native_writer_owned_scope).parameters
    )
    assert names == ["step", "interruption"]
    assert not hasattr(scope, "commit_private_registry")
