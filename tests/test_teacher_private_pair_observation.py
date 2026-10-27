"""#238 Slice 3C5: non-authorizing registry/descriptor paired observation."""

from __future__ import annotations

import hashlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_pair_observation as pair
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_bootstrap as bootstrap
from pds_core import _teacher_private_registry_snapshot as registry
from pds_core import _teacher_private_windows_provision as windows

ASSOC = "6fb32a62-83e2-43f6-9823-687801593c8b"


def _reg(
    state: registry.PrivateRegistrySnapshotState = registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
    digest: str = "a" * 64,
) -> registry.PrivateRegistrySnapshot:
    if state is registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED:
        return registry.PrivateRegistrySnapshot(state, "synthetic", 1, 0, digest)
    return registry.PrivateRegistrySnapshot(state, "synthetic")


def _desc(
    state: descriptor.PrivateDescriptorSnapshotState = descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
    digest: str = "b" * 64,
) -> descriptor.PrivateDescriptorSnapshot:
    if state is descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED:
        return descriptor.PrivateDescriptorSnapshot(state, "synthetic", ASSOC, digest)
    return descriptor.PrivateDescriptorSnapshot(state, "synthetic")


def test_pure_pair_only_observes_never_approves() -> None:
    observed = pair._classify(_reg(), _desc(), _desc(), _reg())
    assert observed.state is pair.PrivatePairObservationState.OBSERVED_UNQUALIFIED
    assert observed.registry_revision == 1
    assert observed.registry_binding_count == 0
    assert observed.association_id == ASSOC
    assert observed.registry_sha256 == "a" * 64
    assert observed.descriptor_sha256 == "b" * 64
    assert ASSOC not in repr(observed)
    assert "a" * 64 not in repr(observed)
    assert not hasattr(observed, "approved")
    assert not hasattr(observed, "ready")
    assert not hasattr(observed, "write_handle")


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            registry.PrivateRegistrySnapshotState.MISSING,
            pair.PrivatePairObservationState.MISSING_REGISTRY,
        ),
        (
            registry.PrivateRegistrySnapshotState.CORRUPT_METADATA,
            pair.PrivatePairObservationState.REFUSED_REGISTRY,
        ),
        (
            registry.PrivateRegistrySnapshotState.OWNER_MISMATCH,
            pair.PrivatePairObservationState.REFUSED_REGISTRY,
        ),
        (
            registry.PrivateRegistrySnapshotState.REFUSED_PROTECTION,
            pair.PrivatePairObservationState.REFUSED_REGISTRY,
        ),
        (
            registry.PrivateRegistrySnapshotState.IO_ERROR,
            pair.PrivatePairObservationState.REFUSED_REGISTRY,
        ),
    ],
)
def test_registry_failures_cannot_become_success(
    state: registry.PrivateRegistrySnapshotState,
    expected: pair.PrivatePairObservationState,
) -> None:
    result = pair._classify(_reg(state), _desc(), _desc(), _reg(state))
    assert result.state is expected
    assert result.association_id is None and result.registry_sha256 is None


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            descriptor.PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR,
            pair.PrivatePairObservationState.MISSING_DESCRIPTOR,
        ),
        (
            descriptor.PrivateDescriptorSnapshotState.MISSING_METADATA_DIRECTORY,
            pair.PrivatePairObservationState.MISSING_DESCRIPTOR,
        ),
        (
            descriptor.PrivateDescriptorSnapshotState.CORRUPT_METADATA,
            pair.PrivatePairObservationState.REFUSED_DESCRIPTOR,
        ),
        (
            descriptor.PrivateDescriptorSnapshotState.REFUSED_PATH,
            pair.PrivatePairObservationState.REFUSED_DESCRIPTOR,
        ),
        (
            descriptor.PrivateDescriptorSnapshotState.IO_ERROR,
            pair.PrivatePairObservationState.REFUSED_DESCRIPTOR,
        ),
    ],
)
def test_descriptor_failures_cannot_become_success(
    state: descriptor.PrivateDescriptorSnapshotState,
    expected: pair.PrivatePairObservationState,
) -> None:
    result = pair._classify(_reg(), _desc(state), _desc(state), _reg())
    assert result.state is expected
    assert result.association_id is None and result.descriptor_sha256 is None


def test_registry_revision_or_digest_changes_during_observation() -> None:
    assert pair._classify(_reg(), _desc(), _desc(), _reg(digest="c" * 64)).state is (
        pair.PrivatePairObservationState.CHANGED_DURING_OBSERVATION
    )
    changed = registry.PrivateRegistrySnapshot(
        registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
        "synthetic",
        2,
        0,
        "a" * 64,
    )
    assert pair._classify(_reg(), _desc(), _desc(), changed).state is (
        pair.PrivatePairObservationState.CHANGED_DURING_OBSERVATION
    )


def test_descriptor_digest_or_state_changes_during_observation() -> None:
    assert pair._classify(_reg(), _desc(), _desc(digest="c" * 64), _reg()).state is (
        pair.PrivatePairObservationState.CHANGED_DURING_OBSERVATION
    )
    assert (
        pair._classify(
            _reg(),
            _desc(descriptor.PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR),
            _desc(),
            _reg(),
        ).state
        is pair.PrivatePairObservationState.CHANGED_DURING_OBSERVATION
    )


def test_status_messages_and_failures_never_leak_principals() -> None:
    for state in pair.PrivatePairObservationState:
        result = pair._result(state)
        assert result.association_id is None
        assert result.registry_revision is None
        assert "S-1-5-" not in repr(result)
        assert "/workspace" not in repr(result)


def test_no_notes_service_or_writing_methods() -> None:
    assert not hasattr(pair, "commit_private_transaction")
    assert not hasattr(pair, "write_private_registry")
    assert not hasattr(pair, "create_notes_store")
    assert not hasattr(pair, "bind_workspace")


def test_invalid_root_refuses_before_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        locking,
        "hold_existing_private_lock",
        lambda _path: pytest.fail("unexpected lock acquisition"),
    )
    result = pair.observe_private_registry_and_workspace_descriptor(tmp_path, tmp_path)
    assert result.state is pair.PrivatePairObservationState.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == []


def test_unknown_platform_refuses_before_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    result = pair.observe_private_registry_and_workspace_descriptor(tmp_path, tmp_path)
    assert result.state is pair.PrivatePairObservationState.UNSUPPORTED
    assert list(tmp_path.iterdir()) == []


def test_single_lock_brackets_four_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    @contextmanager
    def fake_lock(_path: Path) -> Iterator[None]:
        calls.append("lock")
        try:
            yield
        finally:
            calls.append("unlock")

    monkeypatch.setattr(
        lock_provision, "_requested_root", lambda _path, _platform: True
    )
    monkeypatch.setattr(descriptor, "_valid_root", lambda _path: True)
    monkeypatch.setattr(locking, "hold_existing_private_lock", fake_lock)

    def observed_registry(_root: Path) -> registry.PrivateRegistrySnapshot:
        calls.append("registry")
        return _reg()

    def observed_descriptor(_root: Path) -> descriptor.PrivateDescriptorSnapshot:
        calls.append("descriptor")
        return _desc()

    monkeypatch.setattr(pair, "_registry_read", observed_registry)
    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", observed_descriptor)
    result = pair.observe_private_registry_and_workspace_descriptor(
        Path("/root"), Path("/workspace")
    )
    assert result.state is pair.PrivatePairObservationState.OBSERVED_UNQUALIFIED
    assert calls == [
        "lock",
        "registry",
        "descriptor",
        "descriptor",
        "registry",
        "unlock",
    ]


def test_coordination_busy_refuses_without_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def busy(_path: Path) -> Iterator[None]:
        raise locking.PrivateExistingFileLockError(
            locking.PrivateExistingFileLockCode.BUSY
        )
        yield

    monkeypatch.setattr(
        lock_provision, "_requested_root", lambda _path, _platform: True
    )
    monkeypatch.setattr(descriptor, "_valid_root", lambda _path: True)
    monkeypatch.setattr(locking, "hold_existing_private_lock", busy)
    monkeypatch.setattr(
        pair, "_registry_read", lambda _root: pytest.fail("read on busy lock")
    )
    result = pair.observe_private_registry_and_workspace_descriptor(
        Path("/root"), Path("/workspace")
    )
    assert result.state is pair.PrivatePairObservationState.COORDINATION_UNAVAILABLE


@pytest.fixture
def linux_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    reader = getattr(os, "geteuid", None)
    if sys.platform != "linux" or reader is None or reader() == 0:
        pytest.skip("Linux nonroot filesystem test")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    (root / ".registry.lock").write_bytes(b"\x00")
    (root / ".registry.lock").chmod(0o600)
    content = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner("posix_euid", str(reader())), 1, ()
        )
    )
    (root / "registry.json").write_bytes(content)
    (root / "registry.json").chmod(0o600)
    workspace = tmp_path / "workspace"
    pds = workspace / ".pds"
    pds.mkdir(parents=True)
    (pds / "teacher-private-association.json").write_bytes(
        metadata.encode_association_descriptor(
            metadata.PrivateAssociationDescriptor(ASSOC)
        )
    )
    (pds / "workspace.json").write_bytes(b"untouched-marker")
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return root, workspace


def test_linux_native_pair_is_read_only_and_not_bound(
    linux_pair: tuple[Path, Path],
) -> None:
    root, workspace = linux_pair
    originals = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in (
            root / "registry.json",
            root / ".registry.lock",
            workspace / ".pds" / "teacher-private-association.json",
            workspace / ".pds" / "workspace.json",
        )
    }
    result = pair.observe_private_registry_and_workspace_descriptor(root, workspace)
    assert result.state is pair.PrivatePairObservationState.OBSERVED_UNQUALIFIED
    assert result.association_id == ASSOC
    assert result.registry_binding_count == 0  # UUID alone is not a binding!
    assert (
        result.registry_sha256
        == hashlib.sha256((root / "registry.json").read_bytes()).hexdigest()
    )
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in originals} == originals


def test_linux_missing_and_corrupt_stay_distinct(linux_pair: tuple[Path, Path]) -> None:
    root, workspace = linux_pair
    sidecar = workspace / ".pds" / "teacher-private-association.json"
    sidecar.unlink()
    result = pair.observe_private_registry_and_workspace_descriptor(root, workspace)
    assert result.state is pair.PrivatePairObservationState.MISSING_DESCRIPTOR
    sidecar.write_bytes(b"bad")
    result = pair.observe_private_registry_and_workspace_descriptor(root, workspace)
    assert result.state is pair.PrivatePairObservationState.REFUSED_DESCRIPTOR
    assert sidecar.read_bytes() == b"bad"


def test_linux_registry_corrupt_never_recreated(linux_pair: tuple[Path, Path]) -> None:
    root, workspace = linux_pair
    file = root / "registry.json"
    file.write_bytes(b"bad")
    result = pair.observe_private_registry_and_workspace_descriptor(root, workspace)
    assert result.state is pair.PrivatePairObservationState.REFUSED_REGISTRY
    assert file.read_bytes() == b"bad"


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-native paired snapshot only"
)
def test_windows_native_pair_with_protected_private_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel, advapi = windows._windows_api()
    if not windows._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Native Windows test requires local fixed NTFS/ReFS volume")
    owner = inspection._effective_owner("win32")
    root = tmp_path
    for segment in ("Paper Data Suite", "private", "notes", "v1"):
        root = root / segment
        created, reason = windows._create_directory_explicit_dacl(
            kernel, advapi, root, owner.value
        )
        assert created, f"Protected test directory could not be created: {reason}"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    created_lock = lock_provision.create_private_registry_lock_file(root)
    assert (
        created_lock.state
        is lock_provision.PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    created_registry = bootstrap.create_empty_private_registry_candidate(root)
    assert (
        created_registry.state
        is bootstrap.PrivateRegistryBootstrapState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    workspace = tmp_path / "workspace"
    pds = workspace / ".pds"
    pds.mkdir(parents=True)
    sidecar = pds / "teacher-private-association.json"
    sidecar.write_bytes(
        metadata.encode_association_descriptor(
            metadata.PrivateAssociationDescriptor(ASSOC)
        )
    )
    before = sidecar.read_bytes()
    result = pair.observe_private_registry_and_workspace_descriptor(root, workspace)
    assert result.state is pair.PrivatePairObservationState.OBSERVED_UNQUALIFIED
    assert result.registry_binding_count == 0
    assert result.association_id == ASSOC
    assert sidecar.read_bytes() == before
