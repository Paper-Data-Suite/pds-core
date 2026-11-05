"""Core #238 3G27: single-scope synthetic native writer admission and refusals."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_writer_admission as writer
from pds_core import _teacher_private_recovery_writer_sequence as sequence

Step = writer.PrivateScratchWriterStep
Fault = writer.PrivateScratchWriterFault
State = writer.PrivateScratchWriterState


@pytest.mark.skipif(sys.platform not in ("linux", "win32"), reason="native scratch")
def test_actual_native_scratch_writer_admission_succeeds_without_authority() -> None:
    result = writer.rehearse_synthetic_writer_owned_admission()
    assert result.state is State.REPLACEMENT_OBSERVED_PERSISTENCE_UNQUALIFIED
    assert "no production authority" in result.message
    assert not any(
        hasattr(result, name) for name in ("path", "handle", "token", "permit", "bytes")
    )


@pytest.mark.parametrize(
    "step", [Step.INITIALIZE, Step.DESCRIPTOR_COMPLETION, Step.JOURNAL_RETIREMENT]
)
def test_not_admitted_ops_stop_before_scratch(
    monkeypatch: pytest.MonkeyPatch, step: Step
) -> None:
    monkeypatch.setattr(
        tempfile, "TemporaryDirectory", lambda **_: pytest.fail("scratch allocated")
    )
    assert (
        writer.rehearse_synthetic_writer_owned_admission(step).state
        is State.OPERATION_NOT_ADMITTED
    )


@pytest.mark.parametrize("bad", [None, "stage_to_registry", True, 0, {}, (), object()])
def test_invalid_step_stops_before_scratch(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    monkeypatch.setattr(
        tempfile, "TemporaryDirectory", lambda **_: pytest.fail("scratch allocated")
    )
    assert (
        writer.rehearse_synthetic_writer_owned_admission(cast(Step, bad)).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("bad", [None, "none", False, 0, {}, (), object()])
def test_invalid_fault_stops_before_scratch(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    monkeypatch.setattr(
        tempfile, "TemporaryDirectory", lambda **_: pytest.fail("scratch allocated")
    )
    assert (
        writer.rehearse_synthetic_writer_owned_admission(
            interruption=cast(Fault, bad)
        ).state
        is State.INVALID_REQUEST
    )


def test_unsupported_platform_does_not_allocate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "unsupported")
    monkeypatch.setattr(
        tempfile, "TemporaryDirectory", lambda **_: pytest.fail("scratch allocated")
    )
    assert writer.rehearse_synthetic_writer_owned_admission().state is State.UNSUPPORTED


@pytest.mark.parametrize("fault", [item for item in Fault if item is not Fault.NONE])
@pytest.mark.skipif(sys.platform not in ("linux", "win32"), reason="native scratch")
def test_interruption_never_authorizes_completion(fault: Fault) -> None:
    assert (
        writer.rehearse_synthetic_writer_owned_admission(interruption=fault).state
        is State.INTERRUPTED_PRESERVE
    )


def test_preimage_corruption_before_reader_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = scratch._write_new

    def corrupt(root: Path, name: str, data: bytes) -> None:
        original(root, name, data + (b"tamper" if name == "registry.json" else b""))

    monkeypatch.setattr(scratch, "_write_new", corrupt)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.PREIMAGE_REFUSED
    )


def test_reader_content_conflict_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer, "_reader_good", lambda *_: False)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.READER_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("count", [1, 2, 3])
def test_identity_drift_at_any_admission_frame_stops_replace(
    monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    original = writer._starting
    calls = [0]
    replaced = [False]
    real_replace = os.replace

    def changed(
        root: Path,
        expected: identity._IdentitySet,
        lock_id: identity._FileID,
        parent: tuple[int, int],
    ) -> bool:
        calls[0] += 1
        if calls[0] == count:
            return False
        return original(root, expected, lock_id, parent)

    def forbidden(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        replaced[0] = True
        real_replace(source, target)

    monkeypatch.setattr(writer, "_starting", changed)
    monkeypatch.setattr(os, "replace", forbidden)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.ADMISSION_DRIFT_PRESERVE
    )
    assert replaced == [False]


def test_final_admission_precedes_only_replace_and_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = os.replace
    observed: list[str] = []
    before = writer._starting
    sync = scratch._sync_target

    def starting(
        root: Path,
        expected: identity._IdentitySet,
        lock_id: identity._FileID,
        parent: tuple[int, int],
    ) -> bool:
        observed.append("admission")
        return before(root, expected, lock_id, parent)

    def replacement(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        observed.append("replace")
        original(source, target)

    def syncing(root: Path) -> None:
        observed.append("sync")
        sync(root)

    monkeypatch.setattr(writer, "_starting", starting)
    monkeypatch.setattr(os, "replace", replacement)
    monkeypatch.setattr(scratch, "_sync_target", syncing)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.REPLACEMENT_OBSERVED_PERSISTENCE_UNQUALIFIED
    )
    assert observed == ["admission", "admission", "admission", "replace", "sync"]


def test_reader_closed_before_native_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    original = writer._read_once
    opened = [False]
    events: list[str] = []
    actual = os.replace

    def read(root: Path, old: identity._FileID, interruption: Fault) -> bool:
        opened[0] = True
        events.append("read")
        result = original(root, old, interruption)
        opened[0] = False
        return result

    def replace(source: os.PathLike[str], dest: os.PathLike[str]) -> None:
        assert not opened[0]
        events.append("replace")
        actual(source, dest)

    monkeypatch.setattr(writer, "_read_once", read)
    monkeypatch.setattr(os, "replace", replace)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.REPLACEMENT_OBSERVED_PERSISTENCE_UNQUALIFIED
    )
    assert events == ["read", "replace"]


def test_native_sharing_refusal_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [0]

    def refused(*_args: object) -> None:
        calls[0] += 1
        raise PermissionError("scratch sharing refusal")

    monkeypatch.setattr(os, "replace", refused)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.REPLACEMENT_REFUSED_PRESERVE
    )
    assert calls == [1]


def test_unexpected_replace_oserror_is_not_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        os, "replace", lambda *_: (_ for _ in ()).throw(OSError("broken"))
    )
    assert writer.rehearse_synthetic_writer_owned_admission().state is State.IO_ERROR


@pytest.mark.parametrize(
    "name", ["registry.json", "descriptor.json", "transactions.json"]
)
def test_postimage_byte_corruption_fails_closed(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    original = os.replace

    def replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        original(source, target)
        (Path(target).parent / name).write_bytes(b"CORRUPT")

    monkeypatch.setattr(os, "replace", replace)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


def test_postimage_identity_conflict_preserves(monkeypatch: pytest.MonkeyPatch) -> None:
    original = identity._identities
    calls = [0]

    def drift(root: Path, *, stage: bool) -> identity._IdentitySet:
        value = original(root, stage=stage)
        if not stage:
            calls[0] += 1
            if calls[0] == 1:
                return (value[0][0], value[0][1] + 1), value[1], value[2], value[3]
        return value

    monkeypatch.setattr(identity, "_identities", drift)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.IDENTITY_CONFLICT_PRESERVE
    )


def test_parent_identity_change_detected_before_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = writer._parent_id
    calls = [0]
    real_replace = os.replace
    replace_calls = [0]

    def changed(root: Path) -> tuple[int, int]:
        value = original(root)
        calls[0] += 1
        return (value[0], value[1] + 1) if calls[0] >= 2 else value

    def replacement(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        replace_calls[0] += 1
        real_replace(source, target)

    monkeypatch.setattr(writer, "_parent_id", changed)
    monkeypatch.setattr(os, "replace", replacement)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.ADMISSION_DRIFT_PRESERVE
    )
    assert replace_calls == [0]


def test_sync_failure_does_not_produce_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(_root: Path) -> None:
        raise OSError("scratch file sync refused")

    monkeypatch.setattr(scratch, "_sync_target", refused)
    assert writer.rehearse_synthetic_writer_owned_admission().state is State.IO_ERROR


def test_sequence_failure_does_not_produce_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sequence, "_ordered", lambda *_: False)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


def test_guard_refusal_blocks_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager
    from typing import Iterator

    @contextmanager
    def refused(_path: Path) -> Iterator[None]:
        raise scratch._GuardRefused
        yield  # pragma: no cover

    monkeypatch.setattr(scratch, "_scratch_lock", refused)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state is State.GUARD_REFUSED
    )


def test_keyboard_interrupt_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(*_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupted)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.INTERRUPTED_PRESERVE
    )


@pytest.mark.parametrize("status", list(State))
def test_report_sanitization_and_frozen_result(status: State) -> None:
    result = writer._result(status)
    assert result.state is status
    assert not any(
        hasattr(result, name)
        for name in ("path", "bytes", "handle", "token", "permit", "owner")
    )
    assert not any(mark in result.message for mark in ("C:\\", "/tmp/", "\\\\"))
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


def test_all_admission_files_reclaimed_after_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = tempfile.TemporaryDirectory
    visited: list[Path] = []

    def record(*, prefix: str | None = None) -> tempfile.TemporaryDirectory[str]:
        instance = original(prefix=prefix)
        visited.append(Path(instance.name))
        return instance

    monkeypatch.setattr(tempfile, "TemporaryDirectory", record)
    assert (
        writer.rehearse_synthetic_writer_owned_admission().state
        is State.REPLACEMENT_OBSERVED_PERSISTENCE_UNQUALIFIED
    )
    assert len(visited) == 1
    assert not visited[0].exists()
