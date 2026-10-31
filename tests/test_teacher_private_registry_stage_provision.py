"""#238 3F2: create-only registry after-image staging, not metadata CAS."""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_stage_provision as stage
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities

SID = "S-1-5-21-11-22-33-44"
TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
NAME = "." + TX + ".registry-stage"
RAW = b"synthetic registry after image\n"


class _NativeFn:
    def __init__(self, callback: Callable[..., Any]) -> None:
        self.callback = callback
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: Any) -> Any:
        return self.callback(*args)


def _fake_windows(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    fault: str = "",
    collision: int = 0,
) -> None:
    owner = inspection.EffectiveOSOwner("windows_token_sid", SID)
    monkeypatch.setattr(inspection, "_effective_owner", lambda _platform: owner)

    def volume(_kernel: object, _root: Path) -> bool:
        events.append("volume")
        return fault != "volume"

    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", volume)

    def walk(_root: Path, _owner: object) -> NativePrivatePreflightState:
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
        target: Path,
        account_sid: str,
        *,
        write_through: bool = False,
    ) -> tuple[int | None, int]:
        events.append("create")
        assert target.name == NAME and target.parent.name == "private"
        assert account_sid == SID and write_through
        return (None, collision) if collision else (0x123, 0)

    monkeypatch.setattr(lock_file, "_create_file_explicit_dacl_windows", create)

    def write(
        _handle: object, _buffer: Any, count: int, written: Any, _overlapped: object
    ) -> bool:
        events.append("write")
        size = count - 1 if fault == "short_write" else count
        ctypes.cast(written, ctypes.POINTER(wintypes.DWORD))[0] = wintypes.DWORD(size)
        return fault != "write"

    def flush(_handle: object) -> bool:
        events.append("flush")
        if fault == "flush_exception":
            raise OSError("synthetic flush interruption")
        return fault != "flush"

    def close(_handle: object) -> bool:
        events.append("close")
        return True

    kernel = SimpleNamespace(
        WriteFile=_NativeFn(write),
        FlushFileBuffers=_NativeFn(flush),
        CloseHandle=_NativeFn(close),
    )
    monkeypatch.setattr(wincreate, "_windows_api", lambda: (kernel, object()))

    def info(_kernel: object, _handle: int) -> tuple[int, Any] | None:
        events.append("info")
        if fault == "info":
            return None
        return (
            0x400 if fault == "reparse" else 0,
            SimpleNamespace(
                directory=False,
                delete_pending=False,
                number_of_links=1,
                end_of_file=len(RAW) - (1 if fault == "size" else 0),
            ),
        )

    monkeypatch.setattr(descriptor, "_windows_info", info)

    def dacl(*_args: object) -> NativePrivatePreflightState:
        events.append("dacl")
        return (
            NativePrivatePreflightState.REFUSED_ACL
            if fault == "dacl"
            else NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        )

    monkeypatch.setattr(wincheck, "_handle_dacl_state", dacl)


@pytest.mark.parametrize(
    ("fault", "state_expected"),
    [
        ("", stage.PrivateRegistryStageState.STAGED_UNQUALIFIED),
        ("write", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
        ("short_write", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
        ("flush", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
        ("flush_exception", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
        ("info", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
        ("reparse", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
        ("size", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
        ("dacl", stage.PrivateRegistryStageState.CREATION_UNVERIFIED),
    ],
)
def test_windows_create_only_fault_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
    state_expected: stage.PrivateRegistryStageState,
) -> None:
    events: list[str] = []
    _fake_windows(monkeypatch, events, fault=fault)
    root = tmp_path / "private"
    result = stage._windows_create(root, NAME, RAW, SID)
    assert result.state is state_expected
    assert events.count("create") == 1
    assert events.count("close") == 1
    assert "registry.json" not in repr(result)
    if fault in ("write", "short_write"):
        assert "flush" not in events
    if fault in ("flush", "flush_exception"):
        assert "info" not in events
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("error", [80, 183, 5])
def test_windows_collision_or_access_denied_never_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: int
) -> None:
    events: list[str] = []
    _fake_windows(monkeypatch, events, collision=error)
    result = stage._windows_create(tmp_path / "private", NAME, RAW, SID)
    assert result.state is (
        stage.PrivateRegistryStageState.ACCESS_DENIED
        if error == 5
        else stage.PrivateRegistryStageState.ALREADY_EXISTS
    )
    assert "write" not in events and "close" not in events


@pytest.mark.parametrize("fault", ["walk", "volume"])
def test_windows_preflight_refuses_before_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    events: list[str] = []
    _fake_windows(monkeypatch, events, fault=fault)
    result = stage._windows_create(tmp_path / "private", NAME, RAW, SID)
    assert result.state in {
        stage.PrivateRegistryStageState.REFUSED_BACKING,
        stage.PrivateRegistryStageState.REFUSED_PROTECTION,
    }
    assert "create" not in events


def test_windows_owner_mismatch_precedes_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake_windows(monkeypatch, events)
    assert (
        stage._windows_create(
            tmp_path / "private", NAME, RAW, "S-1-5-21-55-66-77-88"
        ).state
        is stage.PrivateRegistryStageState.REFUSED_OWNER
    )
    assert "create" not in events


@pytest.fixture
def linux_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    getter = getattr(os, "geteuid", None)
    if sys.platform != "linux" or getter is None or getter() <= 0:
        pytest.skip("Native non-root Linux required")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return root


def _uid() -> str:
    getter = getattr(os, "geteuid", None)
    assert getter is not None
    return str(getter())


def test_linux_stages_without_touching_registry(linux_private: Path) -> None:
    registry = linux_private / "registry.json"
    registry.write_bytes(b"preserve-current-registry")
    outcome = stage._linux_create(linux_private, NAME, RAW, _uid())
    assert outcome.state is stage.PrivateRegistryStageState.STAGED_UNQUALIFIED
    staged = linux_private / NAME
    assert staged.read_bytes() == RAW
    assert stat.S_IMODE(staged.stat().st_mode) == 0o600
    assert registry.read_bytes() == b"preserve-current-registry"
    second = stage._linux_create(linux_private, NAME, RAW + b"changed", _uid())
    assert second.state is stage.PrivateRegistryStageState.ALREADY_EXISTS
    assert staged.read_bytes() == RAW


@pytest.mark.parametrize("sync_call", [1, 2])
def test_linux_fsync_failures_leave_stage_intact(
    linux_private: Path, monkeypatch: pytest.MonkeyPatch, sync_call: int
) -> None:
    actual = os.fsync
    calls = 0

    def injected(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == sync_call:
            raise OSError("synthetic fsync fault")
        actual(fd)

    monkeypatch.setattr(os, "fsync", injected)
    assert (
        stage._linux_create(linux_private, NAME, RAW, _uid()).state
        is stage.PrivateRegistryStageState.CREATION_UNVERIFIED
    )
    assert calls == sync_call
    staged = linux_private / NAME
    assert staged.read_bytes() == RAW
    assert (
        stage._linux_create(linux_private, NAME, RAW, _uid()).state
        is stage.PrivateRegistryStageState.ALREADY_EXISTS
    )


def test_linux_hardlink_collision_preserves_both_names(linux_private: Path) -> None:
    old = linux_private / "known-existing"
    old.write_bytes(b"foreign")
    os.link(old, linux_private / NAME)
    result = stage._linux_create(linux_private, NAME, RAW, _uid())
    assert result.state is stage.PrivateRegistryStageState.ALREADY_EXISTS
    assert old.read_bytes() == b"foreign"
    assert (linux_private / NAME).read_bytes() == b"foreign"


def test_linux_rejects_changed_os_owner(linux_private: Path) -> None:
    assert (
        stage._linux_create(linux_private, NAME, RAW, "888888").state
        is stage.PrivateRegistryStageState.REFUSED_OWNER
    )
    assert not (linux_private / NAME).exists()


def test_public_invalid_request_has_no_effects(tmp_path: Path) -> None:
    result = stage.create_private_registry_after_image_stage(
        cast(intents.PrivateTransactionIntent, "untrusted"), tmp_path
    )
    assert result.state is stage.PrivateRegistryStageState.INVALID_REQUEST
    assert not list(tmp_path.iterdir())


def test_no_binding_or_notes_capabilities() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(stage, "commit_private_binding")
    assert not hasattr(stage, "replace_private_registry")
    assert not hasattr(stage, "admit_durable_transaction")
    assert not hasattr(stage, "open_notes_store")
    assert all(
        not item.value.startswith("ready") for item in stage.PrivateRegistryStageState
    )


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_public_derives_fixed_name_and_after_bytes_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    proposed = object.__new__(intents.PrivateTransactionIntent)
    operation = witness.PrivateBindingOperation.REBIND_MOVE
    object.__setattr__(
        proposed, "witness", SimpleNamespace(transaction_id=TX, operation=operation)
    )
    object.__setattr__(proposed, "registry_after", RAW)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda _p: b"canonical"
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _b: proposed
    )
    kind = "windows_token_sid" if platform == "win32" else "posix_euid"
    value = SID if platform == "win32" else "1000"
    monkeypatch.setattr(
        metadata,
        "decode_private_registry",
        lambda _b: SimpleNamespace(owner=SimpleNamespace(kind=kind, value=value)),
    )
    monkeypatch.setattr(metadata, "encode_private_registry", lambda _b: RAW)
    events: list[object] = []

    def fake_create(
        root: Path, name: str, raw: bytes, principal: str
    ) -> stage.PrivateRegistryStageReview:
        events.extend([root, name, raw, principal])
        return stage.PrivateRegistryStageReview(
            stage.PrivateRegistryStageState.STAGED_UNQUALIFIED, "synthetic"
        )

    if platform == "win32":
        monkeypatch.setattr(stage, "_windows_create", fake_create)
    else:
        monkeypatch.setattr(stage, "_linux_create", fake_create)
    assert (
        stage.create_private_registry_after_image_stage(proposed, tmp_path).state
        is stage.PrivateRegistryStageState.STAGED_UNQUALIFIED
    )
    assert events == [tmp_path, NAME, RAW, value]
    assert list(tmp_path.iterdir()) == []


def test_public_refuses_initialization_before_any_create(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proposed = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        proposed,
        "witness",
        SimpleNamespace(
            transaction_id=TX, operation=witness.PrivateBindingOperation.INITIALIZE
        ),
    )
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda _p: b"canonical"
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _b: proposed
    )
    monkeypatch.setattr(
        stage, "_linux_create", lambda *_: pytest.fail("unexpected create")
    )
    monkeypatch.setattr(
        stage, "_windows_create", lambda *_: pytest.fail("unexpected create")
    )
    assert (
        stage.create_private_registry_after_image_stage(proposed, tmp_path).state
        is stage.PrivateRegistryStageState.INVALID_REQUEST
    )
    assert list(tmp_path.iterdir()) == []
