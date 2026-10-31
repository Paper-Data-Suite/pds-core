"""#238 3F6: read-only retained guards are not mutation-aware write scopes.

Synthetic metadata and disposable Linux temporary paths only. These tests
intentionally confirm fail-closed behavior; they do not grant write authority.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_registry_stage_provision as stage
from pds_core import _teacher_private_guarded_intent_candidate as candidate
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _stat(
    *,
    directory: bool = True,
    ctime: int = 100,
    mtime: int = 100,
    dev: int = 11,
    ino: int = 22,
    uid: int = 1000,
    mode: int | None = None,
) -> os.stat_result:
    """Synthetic os.stat_result-like attributes, without real private paths."""
    kind = stat.S_IFDIR if directory else stat.S_IFREG
    permissions = 0o700 if directory else 0o600
    return cast(
        os.stat_result,
        SimpleNamespace(
            st_dev=dev,
            st_ino=ino,
            st_uid=uid,
            st_mode=(kind | permissions) if mode is None else mode,
            st_nlink=1,
            st_size=140 if not directory else 4096,
            st_mtime_ns=mtime,
            st_ctime_ns=ctime,
        ),
    )


@pytest.mark.parametrize("changed", ["ctime", "inode", "device", "owner", "mode"])
def test_journal_guard_retained_identity_changes_with_directory_metadata(
    changed: str,
) -> None:
    original = _stat()
    options = {
        "ctime": _stat(ctime=101),
        "inode": _stat(ino=23),
        "device": _stat(dev=12),
        "owner": _stat(uid=1001),
        "mode": _stat(mode=stat.S_IFDIR | 0o755),
    }
    changed_stat = options[changed]
    assert journal_guard._identity(original) != journal_guard._identity(changed_stat)


@pytest.mark.parametrize("changed", ["ctime", "mtime", "inode", "device", "mode"])
def test_registry_guard_retained_parent_signature_changes(
    changed: str,
) -> None:
    original = _stat()
    options = {
        "ctime": _stat(ctime=101),
        "mtime": _stat(mtime=101),
        "inode": _stat(ino=23),
        "device": _stat(dev=12),
        "mode": _stat(mode=stat.S_IFDIR | 0o755),
    }
    changed_stat = options[changed]
    assert registry_guard._linux_signature(original) != registry_guard._linux_signature(
        changed_stat
    )


def test_linux_journal_guard_rejects_only_directory_ctime_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _stat()
    after = _stat(ctime=101)
    assert (before.st_dev, before.st_ino, before.st_mode, before.st_uid) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
    )
    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", lambda _fd: after)
        patch.setattr(os, "lstat", lambda _path: after)
        patch.setattr(os, "geteuid", lambda: 1000, raising=False)
        with pytest.raises(journal_guard.RetainedJournalGuardError) as exc:
            journal_guard._linux_check(
                7, tmp_path, 1000, journal_guard._identity(before)
            )
    assert exc.value.code is journal_guard.RetainedJournalGuardCode.CHANGED_DURING_SCOPE


def test_linux_registry_guard_rejects_only_parent_timestamp_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_before = _stat()
    parent_after = _stat(ctime=101, mtime=102)
    file_unchanged = _stat(directory=False, ino=31)
    assert (parent_before.st_dev, parent_before.st_ino) == (
        parent_after.st_dev,
        parent_after.st_ino,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            os,
            "fstat",
            lambda fd: parent_after if fd == 8 else file_unchanged,
        )
        patch.setattr(os, "lstat", lambda _path: parent_after)
        patch.setattr(os, "stat", lambda *_args, **_kw: file_unchanged)
        patch.setattr(os, "geteuid", lambda: 1000, raising=False)
        with pytest.raises(registry_guard.RetainedRegistryGuardError) as exc:
            registry_guard._linux_check(
                8,
                9,
                tmp_path,
                registry_guard._linux_signature(parent_before),
                registry_guard._linux_signature(file_unchanged),
                1000,
            )
    assert (
        exc.value.code is registry_guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native metadata test")
@pytest.mark.parametrize("target", ["transactions", "private-root"])
def test_linux_actual_exclusive_file_create_changes_parent_snapshot(
    tmp_path: Path, target: str
) -> None:
    """Create synthetic file *only* in pytest's disposable temporary directory."""
    parent = tmp_path / target
    parent.mkdir(mode=0o700)
    before = os.stat(parent, follow_symlinks=False)
    new_file = parent / ".synthetic-transaction-candidate"
    descriptor = os.open(
        new_file,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    os.close(descriptor)
    after = os.stat(parent, follow_symlinks=False)
    assert new_file.is_file()
    assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    if (before.st_ctime_ns, before.st_mtime_ns) == (
        after.st_ctime_ns,
        after.st_mtime_ns,
    ):
        pytest.skip("Filesystem timestamp resolution cannot demonstrate this race")
    if target == "transactions":
        assert journal_guard._identity(before) != journal_guard._identity(after)
    else:
        assert registry_guard._linux_signature(
            before
        ) != registry_guard._linux_signature(after)


def test_existing_candidate_and_stage_results_do_not_grant_cas() -> None:
    """Guard and staging contracts must not accidentally become write authority."""
    assert not hasattr(candidate.PrivateGuardedIntentCandidateReview, "write_handle")
    assert not hasattr(candidate, "commit_private_binding")
    assert not hasattr(stage.PrivateRegistryStageReview, "commit_token")
    assert not hasattr(stage, "replace_private_registry")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
