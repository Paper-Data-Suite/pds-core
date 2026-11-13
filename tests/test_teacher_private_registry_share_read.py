"""#238 Slice 3D8: registry reader can coexist with retained native read handle.

Read-sharing is narrowly permitted; the registry reader still refuses a
concurrent write/delete while its own native handle remains open. Neither
this test nor the implementation grants binding or journal write authority.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_registry_snapshot as snapshot
from pds_core import _teacher_private_registry_bootstrap as bootstrap
from pds_core import _teacher_private_retained_registry_guard as retained
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities


class _FakeCall:
    """Small ctypes-like callable for checking Win32 CreateFileW arguments."""

    def __init__(self, result: object = None) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        return self.result


class _FakeKernel:
    def __init__(self) -> None:
        # Returning an invalid handle forces a fail-closed reader outcome.
        self.CreateFileW = _FakeCall(ctypes.c_void_p(-1))
        self.GetFileInformationByHandleEx = _FakeCall()
        self.ReadFile = _FakeCall()
        self.CloseHandle = _FakeCall(1)


def test_reader_requests_read_sharing_and_no_write_or_delete_sharing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspect API arguments on all platforms without a real Windows handle."""
    principal = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    kernel = _FakeKernel()
    monkeypatch.setattr(inspection, "_effective_owner", lambda _platform: principal)
    monkeypatch.setattr(wincreate, "_windows_api", lambda: (kernel, object()))
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        wincheck,
        "_native_windows_walk",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    monkeypatch.setattr(bootstrap, "_qualified_existing_lock_windows", lambda *_: True)

    outcome = snapshot._windows_read(Path("C:/synthetic/private/notes/v1"))
    assert outcome.state is snapshot.PrivateRegistrySnapshotState.IO_ERROR
    assert len(kernel.CreateFileW.calls) == 1
    args = kernel.CreateFileW.calls[0]
    assert str(args[0]).endswith("registry.json")
    assert args[1] == 0x1 | 0x80 | 0x20000
    assert args[2] == 0x1  # FILE_SHARE_READ only; write and delete remain unshared.
    assert args[4] == 3  # OPEN_EXISTING, never create or truncate.
    assert args[5] == 0x00200000  # FILE_FLAG_OPEN_REPARSE_POINT.
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_registry_reader_does_not_expose_write_authority() -> None:
    assert not hasattr(snapshot, "commit_private_binding")
    assert not hasattr(snapshot, "write_private_registry")
    assert not hasattr(retained, "admit_transaction")


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_native_windows_snapshot_coexists_with_retained_registry_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use the same native secure fixture shape as registry snapshot tests."""
    principal = inspection._effective_owner("win32")
    kernel, advapi = wincreate._windows_api()
    if not wincreate._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Known fixed NTFS/ReFS volume required")

    private = tmp_path
    for part in ("Paper Data Suite", "private", "notes", "v1"):
        private = private / part
        made, code = wincreate._create_directory_explicit_dacl(
            kernel, advapi, private, principal.value
        )
        assert made, code
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    lock = lock_provision.create_private_registry_lock_file(private)
    assert (
        lock.state
        is lock_provision.PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    raw = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            owner=metadata.PrivateRegistryOwner("windows_token_sid", principal.value),
            revision=1,
            bindings=(),
        )
    )
    handle_value, code = lock_provision._create_file_explicit_dacl_windows(
        kernel, advapi, private / "registry.json", principal.value
    )
    assert handle_value is not None, code
    handle = wintypes.HANDLE(handle_value)
    try:
        kernel.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel.WriteFile.restype = wintypes.BOOL
        data = ctypes.create_string_buffer(raw)
        written = wintypes.DWORD()
        assert kernel.WriteFile(handle, data, len(raw), ctypes.byref(written), None)
        assert written.value == len(raw)
        kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        kernel.FlushFileBuffers.restype = wintypes.BOOL
        assert kernel.FlushFileBuffers(handle)
    finally:
        kernel.CloseHandle(handle)

    with retained._held_windows_registry(private, principal):
        first = snapshot._windows_read(private)
        second = snapshot._windows_read(private)
        assert first.state is snapshot.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
        assert (
            second.state is snapshot.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
        )
        assert first.sha256 == second.sha256
        assert (first.revision, first.binding_count) == (1, 0)
    assert (private / "registry.json").read_bytes() == raw
