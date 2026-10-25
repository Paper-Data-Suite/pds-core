"""#238 Slice 3B9: exact, opt-in private registry lock-file creation."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_lock_file_provision as provision
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_provision as windows
from pds_core import _teacher_private_inspection as inspection
from pds_core.teacher_experience import get_teacher_experience_capabilities


@pytest.fixture
def linux_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    if sys.platform != "linux":
        pytest.skip("Linux-only file-creation fixture")
    uid_reader = getattr(os, "geteuid", None)
    if uid_reader is None or uid_reader() == 0:
        pytest.skip("Requires non-root POSIX user")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    root.mkdir(parents=True)
    root.chmod(0o700)
    # Synthetic locality qualification is NOT a native D2 filesystem claim.
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return root


def test_exact_file_name_and_nonzero_payload() -> None:
    assert provision._LOCK_FILE == ".registry.lock"
    assert provision._LOCK_PAYLOAD == b"\x00"
    assert len(provision._LOCK_PAYLOAD) == 1


def test_result_has_no_path_or_principal() -> None:
    state = provision._result(provision.PrivateLockProvisionState.ACCESS_DENIED)
    assert "path" not in repr(state).lower()
    assert "sid" not in repr(state).lower()
    assert "access_denied" in state.state.value


def test_rejects_nonpath_request_without_effects(tmp_path: Path) -> None:
    before = list(tmp_path.iterdir())
    result = provision.create_private_registry_lock_file("not-a-path")  # type: ignore[arg-type]
    assert result.state is provision.PrivateLockProvisionState.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == before


def test_rejects_unqualified_alternative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    elif sys.platform == "linux":
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    stranger = tmp_path / "elsewhere"
    stranger.mkdir(mode=0o700)
    assert provision.create_private_registry_lock_file(stranger).state in {
        provision.PrivateLockProvisionState.INVALID_REQUEST,
        provision.PrivateLockProvisionState.UNSUPPORTED,
    }
    assert list(stranger.iterdir()) == []


def test_relative_root_is_not_authorized() -> None:
    assert not provision._requested_root(Path("relative"), "linux")
    assert not provision._requested_root(Path("relative"), "win32")


def test_no_notes_capabilities_or_store_creation() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(provision, "create_notes_store")
    assert not hasattr(provision, "write_private_registry")


def test_unknown_platform_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert provision.create_private_registry_lock_file(tmp_path).state is (
        provision.PrivateLockProvisionState.UNSUPPORTED
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native only")
def test_linux_creates_one_protected_existing_lock_without_notes(
    linux_root: Path,
) -> None:
    outcome = provision.create_private_registry_lock_file(linux_root)
    assert outcome.state is (
        provision.PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    file = linux_root / ".registry.lock"
    assert file.read_bytes() == b"\x00"
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert file.stat().st_nlink == 1
    with locking.hold_existing_private_lock(file):
        pass
    assert provision.create_private_registry_lock_file(linux_root).state is (
        provision.PrivateLockProvisionState.ALREADY_EXISTS
    )
    assert file.read_bytes() == b"\x00"
    assert sorted(path.name for path in linux_root.iterdir()) == [".registry.lock"]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native only")
def test_linux_never_overwrites_existing_file(linux_root: Path) -> None:
    file = linux_root / ".registry.lock"
    file.write_bytes(b"synthetic-preserve")
    before = file.read_bytes()
    state = provision.create_private_registry_lock_file(linux_root)
    assert state.state is provision.PrivateLockProvisionState.ALREADY_EXISTS
    assert file.read_bytes() == before


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native only")
def test_linux_parent_mode_failure_does_not_create(linux_root: Path) -> None:
    linux_root.chmod(0o755)
    result = provision.create_private_registry_lock_file(linux_root)
    assert result.state is provision.PrivateLockProvisionState.REFUSED_PROTECTION
    assert not (linux_root / ".registry.lock").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native only")
def test_linux_local_backing_failure_does_not_create(
    linux_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: False)
    result = provision.create_private_registry_lock_file(linux_root)
    assert result.state is provision.PrivateLockProvisionState.REFUSED_BACKING
    assert not (linux_root / ".registry.lock").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native only")
def test_linux_existing_symlink_is_not_followed(linux_root: Path) -> None:
    file = linux_root / ".registry.lock"
    destination = linux_root / "destination"
    destination.write_bytes(b"synthetic")
    file.symlink_to(destination)
    result = provision.create_private_registry_lock_file(linux_root)
    assert result.state is provision.PrivateLockProvisionState.ALREADY_EXISTS
    assert destination.read_bytes() == b"synthetic"
    assert file.is_symlink()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native only")
def test_linux_restrictive_umask_causes_explicit_partial_state(
    linux_root: Path,
) -> None:
    old = os.umask(0o777)
    try:
        result = provision.create_private_registry_lock_file(linux_root)
    finally:
        os.umask(old)
    assert result.state is provision.PrivateLockProvisionState.CREATION_UNVERIFIED
    file = linux_root / ".registry.lock"
    assert file.is_file()
    assert stat.S_IMODE(file.stat().st_mode) == 0
    assert file.stat().st_size == 1


def test_windows_filename_binding_is_component_exact() -> None:
    scope = Path(r"C:\Users\Synthetic\AppData\Local\Paper Data Suite\private\notes\v1")
    if sys.platform == "win32":
        # Pure approval test, platform-local env does not authenticate anything.
        assert scope.is_absolute()
    else:
        assert not provision._requested_root(scope, "win32")


def test_windows_invalid_sid_cannot_be_interpolated_into_sddl() -> None:
    with pytest.raises(windows._NativeUnavailable):
        provision._create_file_explicit_dacl_windows(
            object(), object(), Path("synthetic"), "S-1-5-21-1);(A;;FA;;;WD"
        )


def test_windows_sddl_is_owner_system_admin_only() -> None:
    captured: list[str] = []
    closed: list[bool] = []

    class FakeAdvapi:
        def ConvertStringSecurityDescriptorToSecurityDescriptorW(
            self, sddl: str, version: int, out: Any, size: Any
        ) -> bool:
            assert version == 1 and size is None
            captured.append(sddl)
            import ctypes

            ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p)).contents.value = 1234
            return True

    class FakeKernel:
        def CreateFileW(
            self,
            path: str,
            access: int,
            share: int,
            attrs: Any,
            disposition: int,
            flags: int,
            template: Any,
        ) -> int:
            assert path.endswith(".registry.lock")
            assert disposition == 1 and share == 0 and template is None
            assert access & 0x40000000
            assert flags == 0x80
            return 5678

        def LocalFree(self, ptr: Any) -> None:
            closed.append(True)

    handle, error = provision._create_file_explicit_dacl_windows(
        FakeKernel(),
        FakeAdvapi(),
        Path("synthetic") / ".registry.lock",
        "S-1-5-21-11-22-33-44",
    )
    assert handle == 5678 and error == 0
    assert len(captured) == 1
    assert captured[0].startswith("D:P")
    assert "(A;;FA;;;SY)" in captured[0]
    assert "(A;;FA;;;BA)" in captured[0]
    assert "(A;;FA;;;S-1-5-21-11-22-33-44)" in captured[0]
    assert "WD" not in captured[0] and "AU" not in captured[0]
    assert closed == [True]


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows handle/DACL only")
def test_windows_native_protected_lock_file_and_existing_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = inspection._effective_owner("win32")
    kernel, advapi = windows._windows_api()
    if not windows._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Not a supported fixed local NTFS/ReFS test volume")
    parent = tmp_path
    for component in ("Paper Data Suite", "private", "notes", "v1"):
        parent = parent / component
        ok, error = windows._create_directory_explicit_dacl(
            kernel, advapi, parent, owner.value
        )
        assert ok, f"Synthetic protected-directory fixture failed: {error}"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    result = provision.create_private_registry_lock_file(parent)
    assert result.state is (
        provision.PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    lock_file = parent / ".registry.lock"
    assert lock_file.read_bytes() == b"\x00"
    with locking.hold_existing_private_lock(lock_file):
        pass
    assert provision.create_private_registry_lock_file(parent).state is (
        provision.PrivateLockProvisionState.ALREADY_EXISTS
    )
    assert list(parent.iterdir()) == [lock_file]
