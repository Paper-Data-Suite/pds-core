"""Core #238 Slice 3C8: explicit, create-only workspace coordination."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_file_lock as file_lock
from pds_core import _teacher_private_lock_file_provision as registry_file
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core import _teacher_private_workspace_lock_provision as provision
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = provision.WorkspaceCoordinationProvisionState


@pytest.fixture
def linux_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    getuid = getattr(os, "geteuid", None)
    if sys.platform != "linux" or getuid is None or getuid() == 0:
        pytest.skip("Native POSIX tests require nonroot Linux")
    root = tmp_path / "synthetic-workspace"
    root.mkdir(mode=0o700)
    (root / ".pds").mkdir(mode=0o700)
    # Tests exercise real openat and modes, but mock locality; not D2 backing.
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return root


def test_exact_fixed_name_and_lockable_byte() -> None:
    assert provision._METADATA_DIR == ".pds"
    assert provision._LOCK_FILE == ".teacher-private-association.lock"
    assert provision._LOCK_PAYLOAD == b"\x00"


def test_no_capabilities_notes_service_or_secret_diagnostics() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(provision, "write_notes_record")
    assert not hasattr(provision, "commit_private_binding")
    for state in State:
        result = provision._result(state)
        assert result.state is state
        assert "\\" not in result.message
        assert "/home/" not in result.message
        assert "S-1-" not in repr(result)


def test_rejects_invalid_request_without_creating(tmp_path: Path) -> None:
    assert provision.create_workspace_coordination_file("invalid").state is (  # type: ignore[arg-type]
        State.INVALID_REQUEST
    )
    assert provision.create_workspace_coordination_file(Path("relative")).state is (
        State.INVALID_REQUEST
    )
    assert list(tmp_path.iterdir()) == []


def test_unsupported_platform_without_creating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert provision.create_workspace_coordination_file(tmp_path).state is (
        State.UNSUPPORTED
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_missing_metadata_directory_is_noop(tmp_path: Path) -> None:
    getuid = getattr(os, "geteuid", None)
    if getuid is None or getuid() == 0:
        pytest.skip("Requires nonroot POSIX")
    root = tmp_path / "synthetic-workspace"
    root.mkdir(mode=0o700)
    outcome = provision.create_workspace_coordination_file(root)
    assert outcome.state is State.MISSING_METADATA_DIRECTORY
    assert list(root.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_create_once_under_existing_metadata_directory(linux_workspace: Path) -> None:
    before = set((linux_workspace / ".pds").iterdir())
    result = provision.create_workspace_coordination_file(linux_workspace)
    assert result.state is State.CREATED_UNQUALIFIED
    file = linux_workspace / ".pds" / provision._LOCK_FILE
    assert set((linux_workspace / ".pds").iterdir()) == before | {file}
    assert file.read_bytes() == b"\x00"
    info = file.stat()
    getuid = getattr(os, "geteuid", None)
    assert getuid is not None
    assert info.st_uid == getuid()
    assert info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600
    with file_lock.hold_existing_private_lock(file):
        pass
    assert provision.create_workspace_coordination_file(linux_workspace).state is (
        State.ALREADY_EXISTS
    )
    assert file.read_bytes() == b"\x00"
    assert not (linux_workspace / ".pds" / "teacher-private-association.json").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_existing_file_preserved(linux_workspace: Path) -> None:
    target = linux_workspace / ".pds" / provision._LOCK_FILE
    target.write_bytes(b"synthetic-original-content")
    assert provision.create_workspace_coordination_file(linux_workspace).state is (
        State.ALREADY_EXISTS
    )
    assert target.read_bytes() == b"synthetic-original-content"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_existing_symlink_is_not_followed(linux_workspace: Path) -> None:
    destination = linux_workspace / "preserve"
    destination.write_bytes(b"synthetic-preserve")
    target = linux_workspace / ".pds" / provision._LOCK_FILE
    target.symlink_to(destination)
    assert provision.create_workspace_coordination_file(linux_workspace).state is (
        State.ALREADY_EXISTS
    )
    assert target.is_symlink() and destination.read_bytes() == b"synthetic-preserve"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_symlink_metadata_directory_refused(linux_workspace: Path) -> None:
    metadata = linux_workspace / ".pds"
    metadata.rmdir()
    elsewhere = linux_workspace / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    metadata.symlink_to(elsewhere, target_is_directory=True)
    assert provision.create_workspace_coordination_file(linux_workspace).state in {
        State.REFUSED_PATH,
        State.UNSUPPORTED,
    }
    assert list(elsewhere.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_writable_metadata_directory_fails_closed(linux_workspace: Path) -> None:
    metadata = linux_workspace / ".pds"
    metadata.chmod(0o777)
    assert provision.create_workspace_coordination_file(linux_workspace).state is (
        State.REFUSED_PATH
    )
    assert list(metadata.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_readable_metadata_directory_unqualified(linux_workspace: Path) -> None:
    metadata = linux_workspace / ".pds"
    metadata.chmod(0o755)
    assert provision.create_workspace_coordination_file(linux_workspace).state is (
        State.REFUSED_PROTECTION
    )
    assert list(metadata.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_locality_uncertainty_fails_closed(
    linux_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: False)
    assert provision.create_workspace_coordination_file(linux_workspace).state is (
        State.REFUSED_BACKING
    )
    assert list((linux_workspace / ".pds").iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_unverifiable_creation_preserved(linux_workspace: Path) -> None:
    old_umask = os.umask(0o777)
    try:
        result = provision.create_workspace_coordination_file(linux_workspace)
    finally:
        os.umask(old_umask)
    assert result.state is State.CREATION_UNVERIFIED
    file = linux_workspace / ".pds" / provision._LOCK_FILE
    assert file.is_file() and file.stat().st_size == 1
    assert stat.S_IMODE(file.stat().st_mode) == 0


def test_windows_secure_creation_reuses_no_inherited_dacl_window() -> None:
    # Existing protected-file native implementation supplies CREATE_NEW + D:P.
    assert registry_file._LOCK_PAYLOAD == provision._LOCK_PAYLOAD
    assert wincreate._SID.fullmatch("S-1-5-21-11-22-33-44") is not None


def test_windows_parent_dacl_query_requests_read_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pds_core import _teacher_private_inspection as inspection
    from pds_core._teacher_private_native_preflight import NativePrivatePreflightState

    monkeypatch.setattr(descriptor, "_windows_ancestry", lambda *_: None)
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (0, SimpleNamespace(directory=True)),
    )
    monkeypatch.setattr(
        wincheck,
        "_handle_dacl_state",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    observed: list[int] = []

    class FakeKernel:
        def CreateFileW(
            self,
            path: str,
            access: int,
            share: int,
            attrs: object,
            disposition: int,
            flags: int,
            template: object,
        ) -> int:
            assert path.endswith(".pds")
            assert share == 7 and disposition == 3
            assert flags & 0x00200000 and flags & 0x02000000
            observed.append(access)
            return 12345

        def CloseHandle(self, handle: object) -> bool:
            return True

    owner = cast(inspection.EffectiveOSOwner, object())
    assert (
        provision._windows_parent(
            FakeKernel(), object(), Path(r"C:\Synthetic\Workspace"), owner
        )
        is None
    )
    assert observed == [0x00000080 | 0x00020000]


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows only")
def test_windows_native_create_only_and_file_lock(tmp_path: Path) -> None:
    from pds_core import _teacher_private_inspection as inspection

    owner = inspection._effective_owner("win32")
    kernel, advapi = wincreate._windows_api()
    if not wincreate._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Requires supported fixed NTFS/ReFS volume")
    root = tmp_path / "synthetic-workspace"
    root.mkdir()
    ok, error = wincreate._create_directory_explicit_dacl(
        kernel, advapi, root / ".pds", owner.value
    )
    assert ok, f"Fixture .pds protected directory creation failed: {error}"
    result = provision.create_workspace_coordination_file(root)
    assert result.state is State.CREATED_UNQUALIFIED
    file = root / ".pds" / provision._LOCK_FILE
    assert file.read_bytes() == b"\x00"
    with file_lock.hold_existing_private_lock(file):
        pass
    assert provision.create_workspace_coordination_file(root).state is (
        State.ALREADY_EXISTS
    )
    assert sorted(p.name for p in (root / ".pds").iterdir()) == [provision._LOCK_FILE]
