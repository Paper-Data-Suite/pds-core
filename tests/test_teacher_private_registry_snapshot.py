"""#238 Slice 3C2: strictly read-only, non-authorizing registry snapshot."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_snapshot as snapshot
from pds_core import _teacher_private_windows_provision as windows
from pds_core.teacher_experience import get_teacher_experience_capabilities

UUID = "6fb32a62-83e2-43f6-9823-687801593c8b"


def registry_raw(kind: str, owner: str, revision: int = 1, bindings: int = 0) -> bytes:
    if kind == "posix_euid":
        principal = metadata.PrivateRegistryOwner("posix_euid", owner)
        workspace = "/synthetic_workspace_a"
    else:
        principal = metadata.PrivateRegistryOwner("windows_token_sid", owner)
        workspace = "C:\\synthetic_workspace_a"
    collection = (
        (metadata.PrivateRegistryBinding(UUID, 1, workspace),) if bindings else ()
    )
    return metadata.encode_private_registry(
        metadata.PrivateRegistry(principal, revision, collection)
    )


def test_qualified_synthetic_bytes_still_not_ready() -> None:
    raw = registry_raw("posix_euid", "1000")
    result = snapshot._interpret(raw, "posix_euid", "1000")
    assert result.state is snapshot.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
    assert (result.revision, result.binding_count) == (1, 0)
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert raw.decode() not in repr(result)
    assert result.sha256 not in repr(result)
    assert not hasattr(result, "file_handle")


def test_existing_bindings_are_counts_not_notes_access() -> None:
    raw = registry_raw("posix_euid", "1000", 4, 1)
    result = snapshot._interpret(raw, "posix_euid", "1000")
    assert (result.revision, result.binding_count) == (4, 1)
    assert UUID not in repr(result)


@pytest.mark.parametrize(
    "raw",
    [b"", b"corrupt", b"{}", b"\xff", b"x" * 1024],
    ids=["empty", "corrupt", "shape", "utf8", "garbage"],
)
def test_corrupt_registry_never_becomes_missing(raw: bytes) -> None:
    result = snapshot._interpret(raw, "posix_euid", "1000")
    assert result.state is snapshot.PrivateRegistrySnapshotState.CORRUPT_METADATA
    assert result.revision is None and result.sha256 is None


def test_rejects_valid_but_noncanonical_bytes() -> None:
    raw = registry_raw("posix_euid", "1000")
    result = snapshot._interpret(raw + b"  ", "posix_euid", "1000")
    assert result.state is snapshot.PrivateRegistrySnapshotState.CORRUPT_METADATA


def test_native_owner_mismatch_does_not_leak_owner() -> None:
    raw = registry_raw("posix_euid", "1000")
    result = snapshot._interpret(raw, "posix_euid", "1001")
    assert result.state is snapshot.PrivateRegistrySnapshotState.OWNER_MISMATCH
    assert result.revision is None and result.sha256 is None
    assert "1001" not in repr(result)


def test_cross_platform_owner_kind_mismatch_refused() -> None:
    raw = registry_raw("windows_token_sid", "S-1-5-21-11-22-33-44")
    assert snapshot._interpret(raw, "posix_euid", "1000").state is (
        snapshot.PrivateRegistrySnapshotState.OWNER_MISMATCH
    )


def test_no_service_or_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(snapshot, "write_private_registry")
    assert not hasattr(snapshot, "commit_private_transaction")
    assert not hasattr(snapshot, "create_notes_store")


def test_unknown_platform_no_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    result = snapshot.inspect_existing_private_registry(tmp_path)
    assert result.state is snapshot.PrivateRegistrySnapshotState.UNSUPPORTED
    assert list(tmp_path.iterdir()) == []


def test_invalid_root_no_io(tmp_path: Path) -> None:
    result = snapshot.inspect_existing_private_registry(tmp_path)
    assert result.state is snapshot.PrivateRegistrySnapshotState.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def linux_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    getter = getattr(os, "geteuid", None)
    if sys.platform != "linux" or getter is None or getter() == 0:
        pytest.skip("native Linux nonroot only")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    root.mkdir(parents=True)
    root.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    lock = root / ".registry.lock"
    lock.write_bytes(b"\x00")
    lock.chmod(0o600)
    return root


def test_linux_missing_registry_does_not_initialize(linux_root: Path) -> None:
    lock = linux_root / ".registry.lock"
    before = lock.stat().st_mtime_ns
    result = snapshot.inspect_existing_private_registry(linux_root)
    assert result.state is snapshot.PrivateRegistrySnapshotState.MISSING
    assert result.revision is None
    assert sorted(x.name for x in linux_root.iterdir()) == [".registry.lock"]
    assert lock.stat().st_mtime_ns == before


def test_linux_existing_registry_observed_without_writes(linux_root: Path) -> None:
    getter = getattr(os, "geteuid", None)
    assert getter is not None
    raw = registry_raw("posix_euid", str(getter()), 3, 1)
    registry = linux_root / "registry.json"
    registry.write_bytes(raw)
    registry.chmod(0o600)
    before = registry.stat().st_mtime_ns
    result = snapshot.inspect_existing_private_registry(linux_root)
    assert result.state is snapshot.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
    assert result.revision == 3 and result.binding_count == 1
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert registry.read_bytes() == raw and registry.stat().st_mtime_ns == before
    assert (linux_root / ".registry.lock").read_bytes() == b"\x00"


@pytest.mark.parametrize(
    "payload",
    [b"", b"x" * (metadata.MAX_REGISTRY_BYTES + 1)],
    ids=["zero-byte", "oversized"],
)
def test_linux_refuses_invalid_registry_lengths(
    linux_root: Path, payload: bytes
) -> None:
    registry = linux_root / "registry.json"
    registry.write_bytes(payload)
    registry.chmod(0o600)
    result = snapshot.inspect_existing_private_registry(linux_root)
    assert result.state is snapshot.PrivateRegistrySnapshotState.CORRUPT_METADATA
    assert registry.read_bytes() == payload


def test_linux_corrupt_registry_is_preserved(linux_root: Path) -> None:
    registry = linux_root / "registry.json"
    registry.write_bytes(b"bad-private-metadata")
    registry.chmod(0o600)
    result = snapshot.inspect_existing_private_registry(linux_root)
    assert result.state is snapshot.PrivateRegistrySnapshotState.CORRUPT_METADATA
    assert registry.read_bytes() == b"bad-private-metadata"


def test_linux_owner_mismatch_is_not_ready(linux_root: Path) -> None:
    getter = getattr(os, "geteuid", None)
    assert getter is not None
    raw = registry_raw("posix_euid", str(getter() + 1))
    registry = linux_root / "registry.json"
    registry.write_bytes(raw)
    registry.chmod(0o600)
    assert snapshot.inspect_existing_private_registry(linux_root).state is (
        snapshot.PrivateRegistrySnapshotState.OWNER_MISMATCH
    )
    assert registry.read_bytes() == raw


def test_linux_unprotected_file_is_refused(linux_root: Path) -> None:
    registry = linux_root / "registry.json"
    registry.write_bytes(b"bad")
    registry.chmod(0o644)
    assert snapshot.inspect_existing_private_registry(linux_root).state is (
        snapshot.PrivateRegistrySnapshotState.REFUSED_PROTECTION
    )


def test_linux_symlink_file_not_followed(linux_root: Path) -> None:
    target = linux_root / "target"
    target.write_bytes(b"private-preserve")
    link = linux_root / "registry.json"
    link.symlink_to(target)
    assert snapshot.inspect_existing_private_registry(linux_root).state in {
        snapshot.PrivateRegistrySnapshotState.REFUSED_PROTECTION,
        snapshot.PrivateRegistrySnapshotState.IO_ERROR,
    }
    assert target.read_bytes() == b"private-preserve"


def test_linux_missing_lock_never_creates(linux_root: Path) -> None:
    (linux_root / ".registry.lock").unlink()
    assert snapshot.inspect_existing_private_registry(linux_root).state is (
        snapshot.PrivateRegistrySnapshotState.COORDINATION_UNAVAILABLE
    )
    assert list(linux_root.iterdir()) == []


def test_linux_lock_contention_is_refused(linux_root: Path) -> None:
    with locking.hold_existing_private_lock(linux_root / ".registry.lock"):
        state = snapshot.inspect_existing_private_registry(linux_root).state
        assert state is snapshot.PrivateRegistrySnapshotState.COORDINATION_UNAVAILABLE


def test_linux_registry_backing_refusal(
    linux_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: False)
    assert snapshot.inspect_existing_private_registry(linux_root).state is (
        snapshot.PrivateRegistrySnapshotState.REFUSED_BACKING
    )


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_synthetic_owner_registry_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pds_core import _teacher_private_lock_file_provision as create_lock

    owner = inspection._effective_owner("win32")
    kernel, advapi = windows._windows_api()
    if not windows._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("NTFS/ReFS fixed volume required")
    parent = tmp_path
    for part in ("Paper Data Suite", "private", "notes", "v1"):
        parent = parent / part
        made, code = windows._create_directory_explicit_dacl(
            kernel, advapi, parent, owner.value
        )
        assert made, f"Synthetic protected fixture create failed ({code})"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from pds_core import _teacher_private_lock_file_provision as lock_creator

    created = lock_creator.create_private_registry_lock_file(parent)
    assert (
        created.state
        is lock_creator.PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    raw = registry_raw("windows_token_sid", owner.value)
    handle_value, code = create_lock._create_file_explicit_dacl_windows(
        kernel, advapi, parent / "registry.json", owner.value
    )
    assert handle_value is not None, code
    try:
        handle = wintypes.HANDLE(handle_value)
        content = ctypes.create_string_buffer(raw)
        total = wintypes.DWORD()
        kernel.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel.WriteFile.restype = wintypes.BOOL
        assert kernel.WriteFile(handle, content, len(raw), ctypes.byref(total), None)
        assert total.value == len(raw)
        kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        kernel.FlushFileBuffers.restype = wintypes.BOOL
        assert kernel.FlushFileBuffers(handle)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle_value))
    result = snapshot.inspect_existing_private_registry(parent)
    assert result.state is snapshot.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
    assert result.revision == 1 and result.binding_count == 0
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert (parent / "registry.json").read_bytes() == raw


def test_windows_native_unsupported_without_platform(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("non-Windows guard")
    assert snapshot.inspect_existing_private_registry(tmp_path).state is (
        snapshot.PrivateRegistrySnapshotState.INVALID_REQUEST
    )
