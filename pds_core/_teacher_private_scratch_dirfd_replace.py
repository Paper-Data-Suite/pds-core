"""Linux dirfd-relative scratch replacement rehearsal (#238 Slice 3G88).

No caller path, handle, bytes, transaction, user identity or callback is accepted.
A disposable directory is created and protected by a retained POSIX directory
fd for the complete operation; on Windows the exact operation is UNSUPPORTED.
Not a kernel atomic content-CAS, noncooperator exclusion, crash guarantee,
production binding, automatic replay or Notes permission.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness


class PrivateDirfdScratchScenario(str, Enum):
    NORMAL = "normal"
    LIVE_ENTRY_DRIFT = "live_entry_drift"
    STAGE_ENTRY_DRIFT = "stage_entry_drift"
    PARENT_RELINK = "parent_relink"


class PrivateDirfdScratchState(str, Enum):
    LINUX_DIRFD_SCRATCH_REPLACED_NONAUTHORIZING = (
        "linux_dirfd_scratch_replaced_nonauthorizing"
    )
    LIVE_ENTRY_DRIFT_REFUSED = "live_entry_drift_refused"
    STAGE_ENTRY_DRIFT_REFUSED = "stage_entry_drift_refused"
    PARENT_RELINK_REFUSED = "parent_relink_refused"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    WINDOWS_NATIVE_PROTOCOL_UNQUALIFIED = "windows_native_protocol_unqualified"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    NATIVE_CUSTODY_REFUSED = "native_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDirfdScratchReview:
    state: PrivateDirfdScratchState
    linux_directory_fd_retained: bool = False
    both_entries_checked_by_fd: bool = False
    replacement_called_dirfd_relative: bool = False
    exact_scratch_postimage_verified: bool = False
    pending_synthetic_journal_preserved: bool = False
    linux_parent_relink_refused: bool = False
    production_mutation_admitted: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    atomic_content_compare_and_swap_qualified: bool = False
    native_windows_replace_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateDirfdScratchReview(disposable_only=True, non_authorizing=True)"


def _result(
    state: PrivateDirfdScratchState,
    *,
    retained: bool = False,
    checked: bool = False,
    replaced: bool = False,
    verified: bool = False,
    journal: bool = False,
    relink: bool = False,
) -> PrivateDirfdScratchReview:
    return PrivateDirfdScratchReview(
        state=state,
        linux_directory_fd_retained=retained,
        both_entries_checked_by_fd=checked,
        replacement_called_dirfd_relative=replaced,
        exact_scratch_postimage_verified=verified,
        pending_synthetic_journal_preserved=journal,
        linux_parent_relink_refused=relink,
    )


class _UnsafeScratch(Exception):
    """An intentionally path-free, sanitized diagnostic failure."""


_LIVE = "registry.json"
_STAGE = "registry.stage"
_JOURNAL = "pending-journal.json"
_BEFORE = b"synthetic-registry-before-01"
_AFTER = b"synthetic-registry-after-002"
_PENDING = b"synthetic-journal-pending"


def _effective_uid() -> int:
    getter = getattr(os, "geteuid", None)
    if getter is None:
        raise _UnsafeScratch
    value: object = getter()
    if type(value) is not int or value <= 0:
        raise _UnsafeScratch
    return value


def _parent_ok(fd: int, pathname: Path) -> bool:
    """Compare held native parent with current name; not a race-free CAS."""
    opened = os.fstat(fd)
    current = os.lstat(pathname)
    return (
        stat.S_ISDIR(opened.st_mode)
        and stat.S_ISDIR(current.st_mode)
        and (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)
        and opened.st_uid == _effective_uid()
        and stat.S_IMODE(opened.st_mode) == 0o700
    )


def _write_exclusive(fd: int, name: str, payload: bytes) -> None:
    """Only fixed names and fixed synthetic bytes, in a newly owned temp dir."""
    handle = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW"),
        0o600,
        dir_fd=fd,
    )
    try:
        if os.write(handle, payload) != len(payload):
            raise _UnsafeScratch
        os.fsync(handle)
    finally:
        os.close(handle)


def _read_entry(fd: int, name: str) -> tuple[tuple[int, int, int, int], bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0)
    handle = os.open(name, flags, dir_fd=fd)
    try:
        info = os.fstat(handle)
        current = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != _effective_uid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or not 1 <= info.st_size <= 1024
            or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
        ):
            raise _UnsafeScratch
        data = os.read(handle, 1025)
        post = os.fstat(handle)
        final_name = os.stat(name, dir_fd=fd, follow_symlinks=False)
        first = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if (
            len(data) != info.st_size
            or (post.st_dev, post.st_ino, post.st_size, post.st_mtime_ns) != first
            or (
                final_name.st_dev,
                final_name.st_ino,
                final_name.st_size,
                final_name.st_mtime_ns,
            )
            != first
        ):
            raise _UnsafeScratch
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns), data
    finally:
        os.close(handle)


def probe_linux_disposable_dirfd_replace(
    scenario: PrivateDirfdScratchScenario,
) -> PrivateDirfdScratchReview:
    """Run one isolated Linux dirfd-relative synthetic registry transition.

    All file names and bytes are hardcoded and confined to newly allocated
    scratch. A successful result is non-authorizing; malicious same-owner
    threads/processes can still replace entries between checks and syscall.
    """
    state = PrivateDirfdScratchState
    if type(scenario) is not PrivateDirfdScratchScenario:
        return _result(state.INVALID_REQUEST_REFUSED)
    if sys.platform == "win32":
        return _result(state.WINDOWS_NATIVE_PROTOCOL_UNQUALIFIED)
    if sys.platform != "linux" or not (
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")
    ):
        return _result(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _result(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g88_dirfd_") as dirname:
            root = Path(dirname)
            parent = root / "target"
            parent.mkdir(mode=0o700)
            lock = parent / ".registry.lock"
            lock.write_bytes(b"0")
            lock.chmod(0o600)
            with locking.hold_existing_private_lock(lock):
                fd = os.open(
                    parent,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0),
                )
                try:
                    if not _parent_ok(fd, parent):
                        raise _UnsafeScratch
                    for name, payload in (
                        (_LIVE, _BEFORE),
                        (_STAGE, _AFTER),
                        (_JOURNAL, _PENDING),
                    ):
                        _write_exclusive(fd, name, payload)
                    before = _read_entry(fd, _LIVE)
                    staged = _read_entry(fd, _STAGE)
                    pending = _read_entry(fd, _JOURNAL)
                    if (before[1], staged[1], pending[1]) != (
                        _BEFORE,
                        _AFTER,
                        _PENDING,
                    ):
                        raise _UnsafeScratch
                    if scenario is PrivateDirfdScratchScenario.LIVE_ENTRY_DRIFT:
                        _write_exclusive(fd, "decoy-live", _BEFORE)
                        os.rename("decoy-live", _LIVE, src_dir_fd=fd, dst_dir_fd=fd)
                    elif scenario is PrivateDirfdScratchScenario.STAGE_ENTRY_DRIFT:
                        _write_exclusive(fd, "decoy-stage", _AFTER)
                        os.rename("decoy-stage", _STAGE, src_dir_fd=fd, dst_dir_fd=fd)
                    elif scenario is PrivateDirfdScratchScenario.PARENT_RELINK:
                        parent.rename(root / "old-target")
                        parent.mkdir(mode=0o700)
                    # Explicitly validate current parent and both file identities
                    # before the single fixed-name, native dirfd-relative replace.
                    if not _parent_ok(fd, parent):
                        return _result(
                            state.PARENT_RELINK_REFUSED,
                            retained=True,
                            relink=True,
                            journal=True,
                        )
                    if _read_entry(fd, _LIVE) != before:
                        return _result(
                            state.LIVE_ENTRY_DRIFT_REFUSED,
                            retained=True,
                            checked=True,
                            journal=True,
                        )
                    if _read_entry(fd, _STAGE) != staged:
                        return _result(
                            state.STAGE_ENTRY_DRIFT_REFUSED,
                            retained=True,
                            checked=True,
                            journal=True,
                        )
                    if _read_entry(fd, _JOURNAL) != pending:
                        raise _UnsafeScratch
                    if not _parent_ok(fd, parent):
                        raise _UnsafeScratch
                    os.replace(_STAGE, _LIVE, src_dir_fd=fd, dst_dir_fd=fd)
                    # This fsync is a request, NOT a power-loss durability proof.
                    os.fsync(fd)
                    if not _parent_ok(fd, parent):
                        raise _UnsafeScratch
                    post = _read_entry(fd, _LIVE)
                    if (
                        post[1] != _AFTER
                        or post[0][:2] != staged[0][:2]
                        or _read_entry(fd, _JOURNAL) != pending
                    ):
                        raise _UnsafeScratch
                    try:
                        os.stat(_STAGE, dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        raise _UnsafeScratch
                    return _result(
                        state.LINUX_DIRFD_SCRATCH_REPLACED_NONAUTHORIZING,
                        retained=True,
                        checked=True,
                        replaced=True,
                        verified=True,
                        journal=True,
                    )
                finally:
                    os.close(fd)
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        _UnsafeScratch,
    ):
        return _result(state.NATIVE_CUSTODY_REFUSED)
