"""Core #238 3G24: Win32 share-delete behavior on bounded synthetic scratch."""

from __future__ import annotations

import io
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import BinaryIO, Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_synthetic_windows_share as share
from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch

Mode = share.PrivateSyntheticWindowsShareMode
Fault = share.PrivateSyntheticWindowsShareFault
State = share.PrivateSyntheticWindowsShareState


class _EmulatedHeldImage(io.BytesIO):
    """A retained *snapshot* for deterministic share-outcome unit tests.

    A normal Windows ``path.open("rb")`` would hold a real HANDLE without
    FILE_SHARE_DELETE and prevent the allegedly successful simulated rename.
    These tests do not assert native Windows sharing: separate non-mocked
    CreateFileW tests exercise that behavior on Windows itself.
    """

    def __init__(self, raw: bytes, native_id: identity._FileID) -> None:
        super().__init__(raw)
        self.native_id = native_id


@pytest.fixture
def emulated_windows(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Emulate retained old-handle bytes/identity; use real scratch and replace.

    The OS sharing contract is explicitly NOT provided by this fixture.
    The caller's patched os.replace decides allowed/blocked branch behavior.
    """
    visited: list[Path] = []
    original_checker = share._held_before
    monkeypatch.setattr(share, "_windows", lambda: True)

    @contextmanager
    def held(path: Path, mode: Mode) -> Iterator[_EmulatedHeldImage]:
        assert type(mode) is Mode
        assert path.name == "registry.json"
        assert path.parent.name.startswith("core238_3g24_sharing_")
        visited.append(path.parent)
        native_id = identity._identity(path.parent, path.name)
        with _EmulatedHeldImage(path.read_bytes(), native_id) as snapshot:
            yield snapshot

    def held_before(stream: BinaryIO, expected: identity._FileID) -> bool:
        if not isinstance(stream, _EmulatedHeldImage):
            return original_checker(stream, expected)
        stream.seek(0)
        return (
            stream.native_id == expected
            and stream.read(len(scratch._BEFORE) + 1) == scratch._BEFORE
        )

    monkeypatch.setattr(share, "_native_target", held)
    monkeypatch.setattr(share, "_held_before", held_before)
    return visited


@pytest.mark.parametrize(
    "mode,blocked,expected",
    [
        (Mode.NO_DELETE_SHARE, True, State.NO_DELETE_SHARE_BLOCKED_UNQUALIFIED),
        (Mode.ALLOW_DELETE_SHARE, True, State.DELETE_SHARED_REPLACEMENT_REFUSED),
        (Mode.NO_DELETE_SHARE, False, State.SHARING_INVARIANT_CONFLICT_PRESERVE),
        (Mode.ALLOW_DELETE_SHARE, False, State.DELETE_SHARED_REPLACEMENT_UNQUALIFIED),
    ],
)
def test_synthetic_native_sharing_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    emulated_windows: list[Path],
    mode: Mode,
    blocked: bool,
    expected: State,
) -> None:
    actual = os.replace
    count = [0]

    def replacement(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        count[0] += 1
        if blocked:
            raise PermissionError("synthetic sharing denied")
        actual(source, target)

    monkeypatch.setattr(os, "replace", replacement)
    report = share.rehearse_synthetic_private_windows_sharing(mode)
    assert report.state is expected
    assert count == [1]
    assert len(emulated_windows) == 1
    assert not emulated_windows[0].exists()


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native file IDs")
def test_real_held_before_checks_open_handle_id_and_bytes(tmp_path: Path) -> None:
    """The production checker still reads the true native open file handle."""
    target = tmp_path / "registry.json"
    target.write_bytes(scratch._BEFORE)
    native_id = identity._identity(tmp_path, "registry.json")
    with target.open("rb") as stream:
        assert share._held_before(stream, native_id)
        assert not share._held_before(stream, (native_id[0], native_id[1] + 1))
    target.write_bytes(b"bad-synthetic-image")
    with target.open("rb") as stream:
        assert not share._held_before(stream, native_id)


@pytest.mark.skipif(sys.platform != "win32", reason="actual Windows native sharing")
@pytest.mark.parametrize("mode", list(Mode))
def test_real_windows_CreateFileW_share_mask(mode: Mode) -> None:
    result = share.rehearse_synthetic_private_windows_sharing(mode)
    if mode is Mode.NO_DELETE_SHARE:
        assert result.state is State.NO_DELETE_SHARE_BLOCKED_UNQUALIFIED
    else:
        assert result.state in {
            State.DELETE_SHARED_REPLACEMENT_UNQUALIFIED,
            State.DELETE_SHARED_REPLACEMENT_REFUSED,
        }
    assert "C:" not in result.message and "\\\\" not in result.message


@pytest.mark.parametrize(
    "invalid", [None, "no_delete_share", 0, True, (), {}, object()]
)
def test_invalid_sharing_mode_rejected_before_filesystem(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def reject_temp(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid input must not create scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", reject_temp)
    assert (
        share.rehearse_synthetic_private_windows_sharing(cast(Mode, invalid)).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("invalid", [None, "none", 0, False, (), object()])
def test_invalid_fault_rejected_before_filesystem(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def reject_temp(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid fault must not create scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", reject_temp)
    assert (
        share.rehearse_synthetic_private_windows_sharing(
            interruption=cast(Fault, invalid)
        ).state
        is State.INVALID_REQUEST
    )


def test_non_windows_platform_refuses_without_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(share, "_windows", lambda: False)

    def reject_temp(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unsupported request must not create scratch")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", reject_temp)
    assert share.rehearse_synthetic_private_windows_sharing().state is State.UNSUPPORTED


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("fault", [f for f in Fault if f is not Fault.NONE])
def test_interruption_at_each_native_boundary(
    emulated_windows: list[Path], mode: Mode, fault: Fault
) -> None:
    report = share.rehearse_synthetic_private_windows_sharing(mode, fault)
    assert report.state is State.INTERRUPTED_PRESERVE
    assert len(emulated_windows) == (
        0 if fault in {Fault.AFTER_GUARD, Fault.AFTER_PREIMAGE} else 1
    )
    if emulated_windows:
        assert not emulated_windows[0].exists()


@pytest.mark.parametrize(
    "filename",
    [
        "registry.json",
        ".synthetic.registry-stage",
        "descriptor.json",
        "transactions.json",
    ],
)
def test_invalid_synthetic_preimage_refuses_before_native_handle(
    monkeypatch: pytest.MonkeyPatch, emulated_windows: list[Path], filename: str
) -> None:
    original = scratch._write_new

    def corrupt(root: Path, name: str, data: bytes) -> None:
        original(root, name, data + (b"TAMPER" if name == filename else b""))

    monkeypatch.setattr(scratch, "_write_new", corrupt)
    assert (
        share.rehearse_synthetic_private_windows_sharing().state
        is State.PREIMAGE_REFUSED
    )
    assert emulated_windows == []


@pytest.mark.parametrize(
    "filename", ["registry.json", "descriptor.json", "transactions.json"]
)
def test_postimage_byte_conflict_refuses(
    monkeypatch: pytest.MonkeyPatch, emulated_windows: list[Path], filename: str
) -> None:
    original = os.replace

    def corrupt(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        original(source, target)
        (Path(target).parent / filename).write_bytes(b"CORRUPT")

    monkeypatch.setattr(os, "replace", corrupt)
    assert (
        share.rehearse_synthetic_private_windows_sharing(Mode.ALLOW_DELETE_SHARE).state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


def test_postimage_identity_conflict_refuses(
    monkeypatch: pytest.MonkeyPatch, emulated_windows: list[Path]
) -> None:
    original = identity._identities
    calls = [0]

    def changed(root: Path, *, stage: bool) -> identity._IdentitySet:
        answer = original(root, stage=stage)
        calls[0] += 1
        if calls[0] == 2:
            return (
                (answer[0][0], answer[0][1] + 1000),
                answer[1],
                answer[2],
                answer[3],
            )
        return answer

    monkeypatch.setattr(identity, "_identities", changed)
    assert (
        share.rehearse_synthetic_private_windows_sharing(Mode.ALLOW_DELETE_SHARE).state
        is State.HANDLE_IDENTITY_CONFLICT_PRESERVE
    )


def test_lockfile_identity_conflict_refuses(
    monkeypatch: pytest.MonkeyPatch, emulated_windows: list[Path]
) -> None:
    original = identity._identity
    lock_calls = [0]

    def changed(root: Path, name: str) -> identity._FileID:
        result = original(root, name)
        if name == scratch._LOCK:
            lock_calls[0] += 1
            if lock_calls[0] >= 3:
                return result[0], result[1] + 1000
        return result

    monkeypatch.setattr(identity, "_identity", changed)
    assert (
        share.rehearse_synthetic_private_windows_sharing(Mode.ALLOW_DELETE_SHARE).state
        is State.HANDLE_IDENTITY_CONFLICT_PRESERVE
    )


def test_readonly_held_handle_image_conflict_refuses(
    monkeypatch: pytest.MonkeyPatch, emulated_windows: list[Path]
) -> None:
    original = share._held_before
    counts = [0]

    def refused(stream: BinaryIO, expected: identity._FileID) -> bool:
        counts[0] += 1
        return original(stream, expected) if counts[0] == 1 else False

    monkeypatch.setattr(share, "_held_before", refused)
    assert (
        share.rehearse_synthetic_private_windows_sharing(Mode.ALLOW_DELETE_SHARE).state
        is State.HANDLE_IDENTITY_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("policy", list(Mode))
def test_unexpected_native_replace_io_error_is_not_sharing_denial(
    monkeypatch: pytest.MonkeyPatch, emulated_windows: list[Path], policy: Mode
) -> None:
    def refused(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic non-sharing I/O error")

    monkeypatch.setattr(os, "replace", refused)
    assert (
        share.rehearse_synthetic_private_windows_sharing(policy).state is State.IO_ERROR
    )


def test_native_handle_open_failure_never_calls_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(share, "_windows", lambda: True)

    @contextmanager
    def fail_open(_path: Path, _mode: Mode) -> Iterator[BinaryIO]:
        raise OSError("synthetic CreateFileW failure")
        yield  # pragma: no cover

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("replace must not run after failed CreateFileW")

    monkeypatch.setattr(share, "_native_target", fail_open)
    monkeypatch.setattr(os, "replace", fail_replace)
    assert share.rehearse_synthetic_private_windows_sharing().state is State.IO_ERROR


def test_native_lock_refusal_never_opens_native_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(share, "_windows", lambda: True)

    @contextmanager
    def fail_lock(_path: Path) -> Iterator[None]:
        raise scratch._GuardRefused
        yield  # pragma: no cover

    @contextmanager
    def fail_open(_path: Path, _mode: Mode) -> Iterator[BinaryIO]:
        raise AssertionError("target handle acquired without guard")
        yield  # pragma: no cover

    monkeypatch.setattr(scratch, "_scratch_lock", fail_lock)
    monkeypatch.setattr(share, "_native_target", fail_open)
    assert (
        share.rehearse_synthetic_private_windows_sharing().state is State.GUARD_REFUSED
    )


def test_keyboard_interrupt_preserves_evidence(
    monkeypatch: pytest.MonkeyPatch, emulated_windows: list[Path]
) -> None:
    def interrupted(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupted)
    assert (
        share.rehearse_synthetic_private_windows_sharing(Mode.ALLOW_DELETE_SHARE).state
        is State.INTERRUPTED_PRESERVE
    )


@pytest.mark.parametrize("value", list(State))
def test_sanitized_enum_and_frozen_result(value: State) -> None:
    report = share._result(value)
    assert (
        report.message and "C:" not in report.message and "/tmp/" not in report.message
    )
    assert report.state is value
    assert not any(
        hasattr(report, key)
        for key in ("root", "path", "handle", "owner", "permit", "bytes", "token")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(report, "state", State.IO_ERROR)


def test_windows_sharing_refusal_classification() -> None:
    assert share._sharing_refusal(PermissionError("denied"))
    assert not share._sharing_refusal(OSError("unexpected"))
    assert set(Mode) == {Mode.NO_DELETE_SHARE, Mode.ALLOW_DELETE_SHARE}
