"""#238 Slice 3F1: journal creation crash-point and preservation regression.

Synthetic bytes and synthetic OS-user paths only. Never creates Notes records,
updates registry/association metadata, or claims a multi-file commit.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_provision as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities

SID = "S-1-5-21-11-22-33-44"
TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
RAW = b"synthetic-canonical-intent-image\n"


class _NativeFn:
    def __init__(self, callback: Callable[..., Any]) -> None:
        self.callback = callback
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: Any) -> Any:
        return self.callback(*args)


def _current_uid() -> str:
    getter = getattr(os, "geteuid", None)
    assert getter is not None
    return str(getter())


def _fake_windows(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    fault: str = "",
    collision: int = 0,
) -> None:
    """Intercept native calls so Windows paths never touch the real filesystem."""
    owner = inspection.EffectiveOSOwner("windows_token_sid", SID)
    monkeypatch.setattr(journal, "_requested_transactions_dir", lambda *_: True)
    monkeypatch.setattr(inspection, "_effective_owner", lambda _platform: owner)

    def volume(_kernel: object, _path: Path) -> bool:
        events.append("volume")
        return fault != "volume"

    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", volume)

    def walk(_directory: Path, _principal: object) -> NativePrivatePreflightState:
        events.append("walk")
        return (
            NativePrivatePreflightState.REFUSED_ACL
            if fault == "walk"
            else NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        )

    monkeypatch.setattr(wincheck, "_native_windows_walk", walk)

    def create(
        _kernel: object,
        _advapi: object,
        _destination: Path,
        _sid: str,
        *,
        write_through: bool = False,
    ) -> tuple[int | None, int]:
        events.append("create")
        assert write_through and _sid == SID
        return (None, collision) if collision else (0x121, 0)

    monkeypatch.setattr(lock_file, "_create_file_explicit_dacl_windows", create)

    def write(
        _handle: object, _buffer: Any, count: int, written: Any, _overlapped: object
    ) -> bool:
        events.append("write")
        n = count - 1 if fault == "short_write" else count
        ctypes.cast(written, ctypes.POINTER(wintypes.DWORD))[0] = wintypes.DWORD(n)
        return fault != "write"

    def flush(_handle: object) -> bool:
        events.append("flush")
        if fault == "flush_exception":
            raise OSError("synthetic flush fault")
        return fault != "flush"

    def info(_handle: object, _kind: int, _output: Any, _size: int) -> bool:
        events.append("info")
        if fault == "info":
            return False
        if fault == "attributes":
            attrs = ctypes.cast(
                _output, ctypes.POINTER(lock_file._FileAttributeTagInfo)
            )
            attrs.contents.attributes = 0x400
        return True

    def close(_handle: object) -> bool:
        events.append("close")
        return True

    kernel = SimpleNamespace(
        CreateFileW=_NativeFn(lambda *_: None),
        WriteFile=_NativeFn(write),
        FlushFileBuffers=_NativeFn(flush),
        GetFileInformationByHandleEx=_NativeFn(info),
        CloseHandle=_NativeFn(close),
    )
    monkeypatch.setattr(wincreate, "_windows_api", lambda: (kernel, object()))

    def dacl(*_args: object) -> NativePrivatePreflightState:
        events.append("dacl")
        return (
            NativePrivatePreflightState.REFUSED_ACL
            if fault == "dacl"
            else NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        )

    monkeypatch.setattr(wincheck, "_handle_dacl_state", dacl)


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        ("", journal.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED),
        ("write", journal.PrivateJournalProvisionState.CREATION_UNVERIFIED),
        ("short_write", journal.PrivateJournalProvisionState.CREATION_UNVERIFIED),
        ("flush", journal.PrivateJournalProvisionState.CREATION_UNVERIFIED),
        ("flush_exception", journal.PrivateJournalProvisionState.CREATION_UNVERIFIED),
        ("info", journal.PrivateJournalProvisionState.CREATION_UNVERIFIED),
        ("attributes", journal.PrivateJournalProvisionState.CREATION_UNVERIFIED),
        ("dacl", journal.PrivateJournalProvisionState.CREATION_UNVERIFIED),
    ],
)
def test_windows_post_create_faults_preserve_candidate_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
    expected: journal.PrivateJournalProvisionState,
) -> None:
    events: list[str] = []
    _fake_windows(monkeypatch, events, fault=fault)
    result = journal._windows_create(tmp_path, RAW, TX + ".json", SID)
    assert result.state is expected
    assert events.count("create") == 1
    assert events.count("close") == 1
    if fault in ("write", "short_write"):
        assert "flush" not in events
    if fault in ("flush", "flush_exception"):
        assert "info" not in events
    if fault in ("info", "attributes"):
        assert "dacl" not in events
    assert list(tmp_path.iterdir()) == []  # Mock cannot write anything.


@pytest.mark.parametrize("code", [80, 183])
def test_windows_collision_does_not_write_or_close_foreign_handle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: int
) -> None:
    events: list[str] = []
    _fake_windows(monkeypatch, events, collision=code)
    state = journal._windows_create(tmp_path, RAW, TX + ".json", SID).state
    assert state is journal.PrivateJournalProvisionState.ALREADY_EXISTS
    assert "write" not in events and "flush" not in events
    assert "close" not in events
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("fault", ["volume", "walk"])
def test_windows_precreate_fault_never_calls_create(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fault: str
) -> None:
    events: list[str] = []
    _fake_windows(monkeypatch, events, fault=fault)
    state = journal._windows_create(tmp_path, RAW, TX + ".json", SID).state
    assert state in {
        journal.PrivateJournalProvisionState.REFUSED_BACKING,
        journal.PrivateJournalProvisionState.REFUSED_PROTECTION,
    }
    assert "create" not in events and "close" not in events
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def linux_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    uid_fn = getattr(os, "geteuid", None)
    if sys.platform != "linux" or uid_fn is None or uid_fn() == 0:
        pytest.skip("Native Linux non-root required")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = (
        tmp_path / "paper-data-suite" / "private" / "notes" / "v1" / "transactions"
    )
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return directory


@pytest.mark.parametrize("fault_at", [1, 2])
def test_linux_fsync_failure_preserves_exact_candidate(
    linux_directory: Path, monkeypatch: pytest.MonkeyPatch, fault_at: int
) -> None:
    real_sync = os.fsync
    calls = 0

    def injected(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == fault_at:
            raise OSError("synthetic fsync failure")
        real_sync(fd)

    monkeypatch.setattr(os, "fsync", injected)
    result = journal._linux_create(linux_directory, RAW, TX + ".json", _current_uid())
    assert result.state is journal.PrivateJournalProvisionState.CREATION_UNVERIFIED
    assert calls == fault_at
    file = linux_directory / (TX + ".json")
    assert file.read_bytes() == RAW
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert (
        journal._linux_create(linux_directory, RAW, TX + ".json", _current_uid()).state
        is journal.PrivateJournalProvisionState.ALREADY_EXISTS
    )
    assert file.read_bytes() == RAW


def test_linux_partial_write_then_error_preserves_partial_candidate(
    linux_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual_write = os.write
    calls = 0

    def injected(fd: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return actual_write(fd, data[: max(1, len(data) // 2)])
        raise OSError("synthetic mid-write interruption")

    monkeypatch.setattr(os, "write", injected)
    outcome = journal._linux_create(linux_directory, RAW, TX + ".json", _current_uid())
    assert outcome.state is journal.PrivateJournalProvisionState.CREATION_UNVERIFIED
    assert calls == 2
    file = linux_directory / (TX + ".json")
    assert file.read_bytes() == RAW[: len(RAW) // 2]
    assert (
        journal._linux_create(linux_directory, RAW, TX + ".json", _current_uid()).state
        is journal.PrivateJournalProvisionState.ALREADY_EXISTS
    )
    assert file.read_bytes() != RAW


def test_linux_hardlink_collision_never_changes_existing_inode(
    linux_directory: Path,
) -> None:
    sibling = linux_directory.parent / "synthetic-existing.json"
    sibling.write_bytes(b"preserve-foreign-bytes")
    linked = linux_directory / (TX + ".json")
    os.link(sibling, linked)
    outcome = journal._linux_create(linux_directory, RAW, linked.name, _current_uid())
    assert outcome.state is journal.PrivateJournalProvisionState.ALREADY_EXISTS
    assert sibling.read_bytes() == b"preserve-foreign-bytes"
    assert linked.read_bytes() == sibling.read_bytes()


def test_no_notes_or_durable_admission_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(journal, "commit_private_binding")
    assert not hasattr(journal, "admit_durable_transaction")
    assert not hasattr(journal, "create_notes_record")
