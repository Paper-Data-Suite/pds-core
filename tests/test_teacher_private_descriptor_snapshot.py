"""Core #238 Slice 3C3: non-authorizing, read-only workspace descriptor."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_descriptor_snapshot as snapshot
from pds_core import _teacher_private_metadata as metadata

_ASSOC = "6fb32a62-83e2-43f6-9823-687801593c8b"


def test_windows_file_standard_info_boolean_abi() -> None:
    # FILE_STANDARD_INFO uses one-byte BOOLEANs, not four-byte BOOLs.
    fields = getattr(snapshot._FileStandardInfo, "_fields_")
    assert fields[-2:] == [
        ("delete_pending", ctypes.c_ubyte),
        ("directory", ctypes.c_ubyte),
    ]
    first = getattr(snapshot._FileStandardInfo, "delete_pending").offset
    second = getattr(snapshot._FileStandardInfo, "directory").offset
    assert second == first + 1
    if sys.platform == "win32":
        assert first == 20
        assert second == 21
        assert ctypes.sizeof(snapshot._FileStandardInfo) == 24


def valid_bytes() -> bytes:
    return metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_ASSOC)
    )


def test_pure_canonical_descriptor_remains_unqualified() -> None:
    raw = valid_bytes()
    result = snapshot._outcome(
        snapshot.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED, raw
    )
    assert result.state is snapshot.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
    assert result.association_id == _ASSOC
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert _ASSOC not in repr(result)
    assert raw.decode() not in repr(result)
    assert result.sha256 not in repr(result)
    assert "ready" not in result.state.value


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"{}",
        b"not-json",
        b"\xff",
        b"x" * 4097,
        valid_bytes() + b" ",
        valid_bytes().replace(b'"version": 1', b'"version": 2'),
    ],
    ids=[
        "empty",
        "empty-object",
        "non-json",
        "utf8",
        "oversize",
        "noncanonical",
        "version",
    ],
)
def test_invalid_content_is_corrupt_not_missing(bad: bytes) -> None:
    result = snapshot._outcome(
        snapshot.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED, bad
    )
    assert result.state is snapshot.PrivateDescriptorSnapshotState.CORRUPT_METADATA
    assert result.association_id is None and result.sha256 is None


@pytest.mark.parametrize(
    "state",
    [
        s
        for s in snapshot.PrivateDescriptorSnapshotState
        if s is not snapshot.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
    ],
)
def test_refusals_contain_no_identifier_or_path(
    state: snapshot.PrivateDescriptorSnapshotState,
) -> None:
    result = snapshot._outcome(state)
    assert result.association_id is None
    assert result.sha256 is None
    assert _ASSOC not in repr(result)
    assert "/synthetic_workspace" not in repr(result)


def test_no_mutating_methods_or_notes_exports() -> None:
    assert not hasattr(snapshot, "write_workspace_descriptor")
    assert not hasattr(snapshot, "commit_private_transaction")
    assert not hasattr(snapshot, "create_notes_store")


def test_bad_request_never_creates(tmp_path: Path) -> None:
    result = snapshot.inspect_workspace_descriptor(Path("relative"))
    assert result.state is snapshot.PrivateDescriptorSnapshotState.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
def test_existing_workspace_without_pds_is_distinct_missing_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert snapshot.inspect_workspace_descriptor(workspace).state is (
        snapshot.PrivateDescriptorSnapshotState.MISSING_METADATA_DIRECTORY
    )
    assert list(workspace.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
def test_existing_pds_without_descriptor_is_distinct_missing_file(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    pds = workspace / ".pds"
    pds.mkdir(parents=True)
    assert snapshot.inspect_workspace_descriptor(workspace).state is (
        snapshot.PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR
    )
    assert list(pds.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
def test_read_only_descriptor_with_generic_marker_unchanged(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pds = workspace / ".pds"
    pds.mkdir(parents=True)
    association = pds / "teacher-private-association.json"
    marker = pds / "workspace.json"
    raw = valid_bytes()
    association.write_bytes(raw)
    marker.write_bytes(b"generic-workspace-marker-do-not-touch")
    before = {x.name: (x.read_bytes(), x.stat().st_mtime_ns) for x in pds.iterdir()}
    observed = snapshot.inspect_workspace_descriptor(workspace)
    assert (
        observed.state is snapshot.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
    )
    assert observed.association_id == _ASSOC
    assert observed.sha256 == hashlib.sha256(raw).hexdigest()
    assert {
        x.name: (x.read_bytes(), x.stat().st_mtime_ns) for x in pds.iterdir()
    } == before


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
def test_corrupt_descriptor_is_preserved(tmp_path: Path) -> None:
    pds = tmp_path / "workspace" / ".pds"
    pds.mkdir(parents=True)
    file = pds / "teacher-private-association.json"
    file.write_bytes(b"garbled")
    result = snapshot.inspect_workspace_descriptor(pds.parent)
    assert result.state is snapshot.PrivateDescriptorSnapshotState.CORRUPT_METADATA
    assert file.read_bytes() == b"garbled"


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
def test_symlinked_pds_refused_without_reading_target(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "teacher-private-association.json").write_bytes(valid_bytes())
    (workspace / ".pds").symlink_to(target, target_is_directory=True)
    result = snapshot.inspect_workspace_descriptor(workspace)
    assert result.state is snapshot.PrivateDescriptorSnapshotState.REFUSED_PATH
    assert (target / "teacher-private-association.json").read_bytes() == valid_bytes()


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
def test_symlinked_final_descriptor_refused(tmp_path: Path) -> None:
    pds = tmp_path / "workspace" / ".pds"
    pds.mkdir(parents=True)
    target = tmp_path / "target"
    target.write_bytes(valid_bytes())
    (pds / "teacher-private-association.json").symlink_to(target)
    result = snapshot.inspect_workspace_descriptor(pds.parent)
    assert result.state is snapshot.PrivateDescriptorSnapshotState.REFUSED_PATH
    assert target.read_bytes() == valid_bytes()


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
def test_hardlinked_final_descriptor_refused(tmp_path: Path) -> None:
    pds = tmp_path / "workspace" / ".pds"
    pds.mkdir(parents=True)
    target = tmp_path / "target"
    target.write_bytes(valid_bytes())
    os.link(target, pds / "teacher-private-association.json")
    result = snapshot.inspect_workspace_descriptor(pds.parent)
    assert result.state is snapshot.PrivateDescriptorSnapshotState.REFUSED_PATH


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-native read-only snapshot")
def test_windows_existing_descriptor_read_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pds = workspace / ".pds"
    pds.mkdir(parents=True)
    association = pds / "teacher-private-association.json"
    marker = pds / "workspace.json"
    association.write_bytes(valid_bytes())
    marker.write_bytes(b"generic")
    before = (
        association.read_bytes(),
        association.stat().st_mtime_ns,
        marker.read_bytes(),
    )
    result = snapshot.inspect_workspace_descriptor(workspace)
    assert result.state is snapshot.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
    assert result.association_id == _ASSOC
    assert (
        association.read_bytes(),
        association.stat().st_mtime_ns,
        marker.read_bytes(),
    ) == before


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-native read-only snapshot")
def test_windows_missing_and_reparse_refusal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert snapshot.inspect_workspace_descriptor(workspace).state is (
        snapshot.PrivateDescriptorSnapshotState.MISSING_METADATA_DIRECTORY
    )
    pds = workspace / ".pds"
    pds.mkdir()
    assert snapshot.inspect_workspace_descriptor(workspace).state is (
        snapshot.PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR
    )
    # On Windows, creation of symlinks requires a permission or developer mode;
    # do not bypass that native policy just to fabricate this adversarial case.


def test_unknown_platform_never_creates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    result = snapshot.inspect_workspace_descriptor(tmp_path)
    assert result.state is snapshot.PrivateDescriptorSnapshotState.UNSUPPORTED
    assert list(tmp_path.iterdir()) == []
