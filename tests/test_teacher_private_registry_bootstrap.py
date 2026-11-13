"""Core #238 3C1 — lock-guarded empty-registry candidate, never Notes binding."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_file_lock as locks
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_bootstrap as bootstrap
from pds_core import _teacher_private_windows_provision as windows
from pds_core.teacher_experience import get_teacher_experience_capabilities


@pytest.fixture
def linux_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    uid_reader = getattr(os, "geteuid", None)
    if sys.platform != "linux" or uid_reader is None or uid_reader() == 0:
        pytest.skip("Linux non-root only")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return root


def prepare_lock(root: Path) -> Path:
    target = root / ".registry.lock"
    target.write_bytes(b"\x00")
    target.chmod(0o600)
    return target


def test_bootstrap_encodes_only_empty_owner_registry() -> None:
    blob = bootstrap._bytes_for_owner("posix_euid", "1000")
    value = metadata.decode_private_registry(blob)
    assert value.revision == 1
    assert value.bindings == ()
    assert value.owner.kind == "posix_euid"
    assert value.owner.value == "1000"
    assert blob == metadata.encode_private_registry(value)
    assert "1000" not in repr(
        bootstrap._result(bootstrap.PrivateRegistryBootstrapState.UNSUPPORTED)
    )


def test_invalid_owner_kind_refused() -> None:
    with pytest.raises(metadata.PrivateMetadataError):
        bootstrap._bytes_for_owner("synthetic_identity", "1000")


def test_wrong_root_nonmutating(tmp_path: Path) -> None:
    result = bootstrap.create_empty_private_registry_candidate(tmp_path)
    assert result.state in {
        bootstrap.PrivateRegistryBootstrapState.INVALID_REQUEST,
        bootstrap.PrivateRegistryBootstrapState.UNSUPPORTED,
    }
    assert list(tmp_path.iterdir()) == []


def test_wrong_argument_nonmutating(tmp_path: Path) -> None:
    result = bootstrap.create_empty_private_registry_candidate(42)  # type: ignore[arg-type]
    assert result.state is bootstrap.PrivateRegistryBootstrapState.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == []


def test_no_notes_binding_capabilities() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(bootstrap, "commit_private_binding")
    assert not hasattr(bootstrap, "create_notes_store")


def test_missing_lock_refuses_without_registry(linux_root: Path) -> None:
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert (
        result.state is bootstrap.PrivateRegistryBootstrapState.COORDINATION_UNAVAILABLE
    )
    assert not (linux_root / "registry.json").exists()


def test_creates_only_owner_empty_registry(linux_root: Path) -> None:
    lock = prepare_lock(linux_root)
    before = lock.read_bytes()
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert (
        result.state
        is bootstrap.PrivateRegistryBootstrapState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    path = linux_root / "registry.json"
    data = path.read_bytes()
    registry = metadata.decode_private_registry(data)
    uid_reader = getattr(os, "geteuid", None)
    assert uid_reader is not None
    assert registry.owner.value == str(uid_reader())
    assert registry.revision == 1 and registry.bindings == ()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
    assert sorted(p.name for p in linux_root.iterdir()) == [
        ".registry.lock",
        "registry.json",
    ]
    assert lock.read_bytes() == before
    again = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert again.state is bootstrap.PrivateRegistryBootstrapState.ALREADY_EXISTS
    assert path.read_bytes() == data


def test_never_overwrites_existing_registry(linux_root: Path) -> None:
    prepare_lock(linux_root)
    entry = linux_root / "registry.json"
    entry.write_bytes(b"preserve-even-unknown-future-version")
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert result.state is bootstrap.PrivateRegistryBootstrapState.ALREADY_EXISTS
    assert entry.read_bytes() == b"preserve-even-unknown-future-version"


def test_rejects_world_accessible_parent(linux_root: Path) -> None:
    prepare_lock(linux_root)
    linux_root.chmod(0o755)
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert result.state is bootstrap.PrivateRegistryBootstrapState.REFUSED_PROTECTION
    assert not (linux_root / "registry.json").exists()


def test_rejects_insecure_lock_mode(linux_root: Path) -> None:
    lock = prepare_lock(linux_root)
    lock.chmod(0o644)
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert (
        result.state is bootstrap.PrivateRegistryBootstrapState.COORDINATION_UNAVAILABLE
    )
    assert not (linux_root / "registry.json").exists()


def test_rejects_unexpected_lock_content(linux_root: Path) -> None:
    lock = prepare_lock(linux_root)
    lock.write_bytes(b"X")
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert result.state is bootstrap.PrivateRegistryBootstrapState.REFUSED_PROTECTION
    assert not (linux_root / "registry.json").exists()


def test_rejects_missing_local_backing(
    linux_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_lock(linux_root)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: False)
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert result.state is bootstrap.PrivateRegistryBootstrapState.REFUSED_BACKING
    assert not (linux_root / "registry.json").exists()


def test_rejects_symlinked_lock(linux_root: Path) -> None:
    dest = linux_root / "sentinel"
    dest.write_bytes(b"\x00")
    dest.chmod(0o600)
    (linux_root / ".registry.lock").symlink_to(dest)
    result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert (
        result.state is bootstrap.PrivateRegistryBootstrapState.COORDINATION_UNAVAILABLE
    )
    assert not (linux_root / "registry.json").exists()
    assert dest.read_bytes() == b"\x00"


def test_restrictive_umask_preserves_partial_registry(linux_root: Path) -> None:
    prepare_lock(linux_root)
    old = os.umask(0o777)
    try:
        result = bootstrap.create_empty_private_registry_candidate(linux_root)
    finally:
        os.umask(old)
    assert result.state is bootstrap.PrivateRegistryBootstrapState.CREATION_UNVERIFIED
    entry = linux_root / "registry.json"
    assert entry.exists()
    assert stat.S_IMODE(entry.stat().st_mode) == 0


def test_existing_lock_blocks_concurrent_bootstrap(linux_root: Path) -> None:
    lock_path = prepare_lock(linux_root)
    with locks.hold_existing_private_lock(lock_path):
        result = bootstrap.create_empty_private_registry_candidate(linux_root)
    assert (
        result.state is bootstrap.PrivateRegistryBootstrapState.COORDINATION_UNAVAILABLE
    )
    assert not (linux_root / "registry.json").exists()


def test_result_never_returns_path_principal_or_handle() -> None:
    for state in bootstrap.PrivateRegistryBootstrapState:
        message = repr(bootstrap._result(state))
        assert "C:\\Users" not in message and "/home/" not in message
        assert "S-1-5" not in message and "registry.json" not in message


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows only")
def test_windows_native_empty_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = inspection._effective_owner("win32")
    kernel, advapi = windows._windows_api()
    if not windows._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Host test volume is not supported fixed NTFS/ReFS")
    root = tmp_path
    for name in ("Paper Data Suite", "private", "notes", "v1"):
        root = root / name
        done, code = windows._create_directory_explicit_dacl(
            kernel, advapi, root, owner.value
        )
        assert done, f"Fixture protected directory creation failed {code}"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # Populate the prequalified coordination lock using 3B9 native operation.
    created = lock_provision.create_private_registry_lock_file(root)
    assert (
        created.state
        is lock_provision.PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    result = bootstrap.create_empty_private_registry_candidate(root)
    assert (
        result.state
        is bootstrap.PrivateRegistryBootstrapState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    current = metadata.decode_private_registry((root / "registry.json").read_bytes())
    assert current.revision == 1 and current.bindings == ()
    assert current.owner.value == owner.value
    assert bootstrap.create_empty_private_registry_candidate(root).state is (
        bootstrap.PrivateRegistryBootstrapState.ALREADY_EXISTS
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows only")
def test_windows_missing_lock_never_creates_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = tmp_path / "Paper Data Suite" / "private" / "notes" / "v1"
    assert bootstrap.create_empty_private_registry_candidate(root).state is (
        bootstrap.PrivateRegistryBootstrapState.COORDINATION_UNAVAILABLE
    )
    assert not root.exists()
