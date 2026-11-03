"""Core #238 3G19: real native rename confined to disposable synthetic scratch."""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_synthetic_native_writer as rehearsal
from pds_core import _teacher_private_recovery_writer_sequence as sequence

Fault = rehearsal.PrivateSyntheticWriterInterruption
State = rehearsal.PrivateSyntheticWriterState
Phase = sequence.PrivateRecoveryWriterPhase


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_real_scratch_native_rename_is_advisory() -> None:
    result = rehearsal.rehearse_synthetic_private_native_replace()
    assert result.state is State.PERSISTENCE_UNQUALIFIED
    assert "durability" in result.message
    assert not any(
        hasattr(result, name)
        for name in ("path", "root", "handle", "bytes", "token", "permit", "owner")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


@pytest.mark.parametrize("interruption", list(Fault)[1:])
@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_all_injected_interruptions_fail_closed(interruption: Fault) -> None:
    assert (
        rehearsal.rehearse_synthetic_private_native_replace(interruption).state
        is State.INTERRUPTED_PRESERVE
    )


@pytest.mark.parametrize("invalid", [None, "none", 0, 1, False, True, [], {}, object()])
def test_invalid_request_cannot_create_scratch(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def refuse_temp(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid input must not reach scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse_temp)
    assert (
        rehearsal.rehearse_synthetic_private_native_replace(cast(Fault, invalid)).state
        is State.INVALID_REQUEST
    )


def test_unsupported_platform_does_not_create_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    def refuse_temp(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unsupported platform must not create scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse_temp)
    assert (
        rehearsal.rehearse_synthetic_private_native_replace().state is State.UNSUPPORTED
    )


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
@pytest.mark.parametrize("interruption", list(Fault))
def test_scratch_paths_are_private_and_disposed(
    monkeypatch: pytest.MonkeyPatch, interruption: Fault
) -> None:
    visited: list[Path] = []
    real_write = rehearsal._write_new

    def watch(root: Path, name: str, value: bytes) -> None:
        visited.append(root)
        assert root.is_dir()
        assert root.name.startswith("core238_3g19_synthetic_")
        assert name in {
            "registry.json",
            ".synthetic.registry-stage",
            "descriptor.json",
            "transactions.json",
        }
        real_write(root, name, value)

    monkeypatch.setattr(rehearsal, "_write_new", watch)
    rehearsal.rehearse_synthetic_private_native_replace(interruption)
    assert len(visited) == 4
    assert len(set(visited)) == 1
    assert not visited[0].exists()


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
@pytest.mark.parametrize(
    "interruption,replacements,checks,syncs",
    [
        (Fault.AFTER_GUARD, 0, 0, 0),
        (Fault.AFTER_PREIMAGE, 0, 1, 0),
        (Fault.AFTER_NATIVE_REPLACE, 1, 1, 0),
        (Fault.AFTER_POSTIMAGE, 1, 2, 0),
        (Fault.AFTER_FILE_SYNC, 1, 2, 1),
        (Fault.NONE, 1, 3, 1),
    ],
)
def test_interruption_boundaries_preserve_correct_order(
    monkeypatch: pytest.MonkeyPatch,
    interruption: Fault,
    replacements: int,
    checks: int,
    syncs: int,
) -> None:
    counts = {"replace": 0, "checks": 0, "sync": 0}
    real_replace = os.replace
    real_check = rehearsal._expected
    real_sync = rehearsal._sync_target
    active = False
    real_guard = rehearsal._scratch_lock

    @contextmanager
    def guarded(path: Path) -> Iterator[None]:
        nonlocal active
        with real_guard(path):
            active = True
            try:
                yield
            finally:
                active = False

    def replacement(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        assert active
        assert counts["checks"] == 1
        counts["replace"] += 1
        real_replace(source, target)

    def image_check(root: Path, *, stage: bool) -> bool:
        assert active
        counts["checks"] += 1
        if stage:
            assert counts["replace"] == 0
        else:
            assert counts["replace"] == 1
        return real_check(root, stage=stage)

    def sync(root: Path) -> None:
        assert active
        assert counts["checks"] == 2
        counts["sync"] += 1
        real_sync(root)

    monkeypatch.setattr(rehearsal, "_scratch_lock", guarded)
    monkeypatch.setattr(os, "replace", replacement)
    monkeypatch.setattr(rehearsal, "_expected", image_check)
    monkeypatch.setattr(rehearsal, "_sync_target", sync)
    result = rehearsal.rehearse_synthetic_private_native_replace(interruption)
    assert not active
    assert counts == {"replace": replacements, "checks": checks, "sync": syncs}
    if interruption is Fault.NONE:
        assert result.state is State.PERSISTENCE_UNQUALIFIED
    else:
        assert result.state is State.INTERRUPTED_PRESERVE


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
@pytest.mark.parametrize(
    "name",
    [
        "registry.json",
        "descriptor.json",
        "transactions.json",
        ".synthetic.registry-stage",
    ],
)
def test_corrupt_preimage_blocks_native_replace(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    actual = rehearsal._write_new
    called = False

    def corrupted(root: Path, filename: str, raw: bytes) -> None:
        actual(root, filename, raw + b"CORRUPTED" if filename == name else raw)

    def refuse_replace(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("writer must not run after precheck refusal")

    monkeypatch.setattr(rehearsal, "_write_new", corrupted)
    monkeypatch.setattr(os, "replace", refuse_replace)
    assert (
        rehearsal.rehearse_synthetic_private_native_replace().state
        is State.PREIMAGE_REFUSED
    )
    assert not called


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
@pytest.mark.parametrize(
    "bad_name", ["registry.json", "descriptor.json", "transactions.json"]
)
def test_postimage_corruption_blocks_success(
    monkeypatch: pytest.MonkeyPatch, bad_name: str
) -> None:
    original = os.replace

    def corrupt(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        original(source, target)
        root = Path(target).parent
        (root / bad_name).write_bytes(b"changed")

    monkeypatch.setattr(os, "replace", corrupt)
    assert (
        rehearsal.rehearse_synthetic_private_native_replace().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_native_replace_failure_has_no_success_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic failure")

    monkeypatch.setattr(os, "replace", refused)
    assert rehearsal.rehearse_synthetic_private_native_replace().state is State.IO_ERROR


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_lock_failure_prevents_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def refused(_path: Path) -> Iterator[None]:
        raise rehearsal._GuardRefused
        yield

    def no_replace(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("writer called without a guard")

    monkeypatch.setattr(rehearsal, "_scratch_lock", refused)
    monkeypatch.setattr(os, "replace", no_replace)
    assert (
        rehearsal.rehearse_synthetic_private_native_replace().state
        is State.NATIVE_GUARD_REFUSED
    )


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_post_sync_recheck_catches_late_change(monkeypatch: pytest.MonkeyPatch) -> None:
    original = rehearsal._sync_target

    def corrupted(root: Path) -> None:
        original(root)
        (root / "registry.json").write_bytes(b"changed after fsync")

    monkeypatch.setattr(rehearsal, "_sync_target", corrupted)
    assert (
        rehearsal.rehearse_synthetic_private_native_replace().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_file_sync_failure_is_not_durable_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(_root: Path) -> None:
        raise OSError("synthetic fsync refused")

    monkeypatch.setattr(rehearsal, "_sync_target", refused)
    assert rehearsal.rehearse_synthetic_private_native_replace().state is State.IO_ERROR


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_actual_keyboard_interruption_preserves_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupted(_root: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(rehearsal, "_sync_target", interrupted)
    assert (
        rehearsal.rehearse_synthetic_private_native_replace().state
        is State.INTERRUPTED_PRESERVE
    )


def test_protocol_phase_enum_contract_is_exact() -> None:
    expected = (
        Phase.GUARD_ACQUIRED,
        Phase.PREIMAGE_REVALIDATED,
        Phase.OPERATION_INVOKED,
        Phase.OPERATION_RETURNED,
        Phase.POSTIMAGE_REVALIDATED,
        Phase.PERSISTENCE_REQUESTED,
        Phase.GUARD_RELEASED,
    )
    assert sequence._ordered(expected)
    assert not sequence._ordered(expected + (Phase.OPERATION_RETURNED,))


@pytest.mark.parametrize("candidate", list(State))
def test_all_sanitized_states_have_messages(candidate: State) -> None:
    report = rehearsal._result(candidate)
    assert report.state is candidate
    assert report.message and "C:" not in report.message
    assert "/tmp/" not in report.message
