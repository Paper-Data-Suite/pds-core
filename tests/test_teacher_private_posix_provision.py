"""#238 Slice 3B7 protected-child prototype, no live private-store activation."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_posix_provision as create
from pds_core.teacher_experience import get_teacher_experience_capabilities

LINUX = pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")


def test_rejected_request_has_no_fs_mutation(tmp_path: Path) -> None:
    assert create.create_restrictive_child_linux(tmp_path, "../bad").state in {
        create.PrivateChildCreationState.INVALID_REQUEST,
        create.PrivateChildCreationState.UNSUPPORTED,
    }
    assert list(tmp_path.iterdir()) == []


def test_no_public_notes_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(create, "create_notes_store")


@LINUX
def test_linux_refuses_unknown_backing_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o700)
    protected.chmod(0o700)
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: False)
    result = create.create_restrictive_child_linux(protected, "notes")
    assert result.state is create.PrivateChildCreationState.REFUSED_BACKING
    assert not (protected / "notes").exists()


@LINUX
def test_linux_creates_only_one_verified_restrictive_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o700)
    protected.chmod(0o700)
    # This is a D1 synthetic locality fixture, not native filesystem proof.
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    state = create.create_restrictive_child_linux(protected, "notes-v1")
    assert (
        state.state is create.PrivateChildCreationState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    child = protected / "notes-v1"
    assert child.is_dir()
    assert stat.S_IMODE(child.stat().st_mode) == 0o700
    assert list(child.iterdir()) == []
    assert "notes-v1" not in repr(state)
    again = create.create_restrictive_child_linux(protected, "notes-v1")
    assert again.state is create.PrivateChildCreationState.ALREADY_EXISTS
    assert child.is_dir()


@LINUX
def test_existing_entry_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o700)
    protected.chmod(0o700)
    source = protected / "sentinel"
    source.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    assert (
        create.create_restrictive_child_linux(protected, "sentinel").state
        is create.PrivateChildCreationState.ALREADY_EXISTS
    )
    assert source.read_text(encoding="utf-8") == "preserve"


@LINUX
def test_unsafe_parent_mode_refused_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o755)
    protected.chmod(0o755)
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    assert (
        create.create_restrictive_child_linux(protected, "notes").state
        is create.PrivateChildCreationState.REFUSED_MODE
    )
    assert not (protected / "notes").exists()


@LINUX
def test_symlink_parent_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    result = create.create_restrictive_child_linux(link, "notes")
    assert result.state in {
        create.PrivateChildCreationState.UNSAFE_PATH,
        create.PrivateChildCreationState.UNSUPPORTED,
    }
    assert not (actual / "notes").exists()


@LINUX
def test_acl_failure_before_create_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o700)
    protected.chmod(0o700)
    monkeypatch.setattr(
        create, "_acl_absent", lambda fd: create.PrivateChildCreationState.REFUSED_ACL
    )
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    assert (
        create.create_restrictive_child_linux(protected, "notes").state
        is create.PrivateChildCreationState.REFUSED_ACL
    )
    assert not (protected / "notes").exists()


@LINUX
def test_process_owner_mismatch_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o700)
    protected.chmod(0o700)
    geteuid = getattr(os, "geteuid", None)
    assert geteuid is not None
    uid = int(geteuid())
    if uid == 0:
        pytest.skip("root is expressly unsupported")
    monkeypatch.setattr(os, "geteuid", lambda: uid + 1)
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    assert create.create_restrictive_child_linux(protected, "notes").state in {
        create.PrivateChildCreationState.REFUSED_OWNER,
        create.PrivateChildCreationState.UNSAFE_PATH,
    }
    assert not (protected / "notes").exists()


@LINUX
def test_extreme_umask_does_not_claim_created_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o700)
    protected.chmod(0o700)
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    old = os.umask(0o777)
    try:
        result = create.create_restrictive_child_linux(protected, "restricted")
    finally:
        os.umask(old)
    assert result.state is create.PrivateChildCreationState.CREATION_UNVERIFIED
    assert (protected / "restricted").exists()
    assert stat.S_IMODE((protected / "restricted").stat().st_mode) == 0


@LINUX
def test_unknown_current_owner_refuses_without_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "private"
    protected.mkdir(mode=0o700)
    protected.chmod(0o700)
    monkeypatch.setattr(os, "geteuid", lambda: "1000")
    monkeypatch.setattr(create, "_is_known_local_filesystem", lambda fd: True)
    assert (
        create.create_restrictive_child_linux(protected, "notes").state
        is create.PrivateChildCreationState.UNSUPPORTED
    )
    assert not (protected / "notes").exists()
