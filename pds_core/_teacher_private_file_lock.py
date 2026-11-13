"""Noncreating, nonblocking cross-process file-lock primitive (Core #238).

This internal primitive locks ONE BYTE of an *already existing* regular file.
It does not create lock files, authenticate an OS user, check effective ACLs,
validate private-store backing or authorize a metadata commit. A later guarded
storage service must supply and continuously qualify the lock file, parent
handles, lock ordering and protected transaction state.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Iterator


class PrivateExistingFileLockCode(str, Enum):
    """Sanitized reasons; never expose private paths or identities."""

    INVALID_PATH = "invalid_path"
    MISSING = "missing"
    UNSAFE_FILE = "unsafe_file"
    ACCESS_DENIED = "access_denied"
    BUSY = "busy"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


class PrivateExistingFileLockError(RuntimeError):
    """Bounded, path-free failure from the existing-file lock primitive."""

    def __init__(self, code: PrivateExistingFileLockCode) -> None:
        self.code = code
        super().__init__(f"Private coordination lock refused: {code.value}.")


def _refuse(code: PrivateExistingFileLockCode) -> None:
    raise PrivateExistingFileLockError(code)


def _validate_candidate(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        _refuse(PrivateExistingFileLockCode.INVALID_PATH)
    if ".." in path.parts or "\x00" in str(path):
        _refuse(PrivateExistingFileLockCode.INVALID_PATH)
    if sys.platform == "win32" and str(path).startswith(("\\\\", "//")):
        _refuse(PrivateExistingFileLockCode.INVALID_PATH)


def _safe_regular_file(info: os.stat_result) -> bool:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size < 1:
        return False
    # POSIX: refuse modes with any group/world access and unexpected ownership.
    # These checks are still NOT sufficient to qualify POSIX ACL protection.
    if sys.platform != "win32":
        getter = getattr(os, "geteuid", None)
        if getter is None or info.st_uid != getter():
            return False
        if stat.S_IMODE(info.st_mode) != 0o600:
            return False
    return True


def _open_existing(path: Path) -> int:
    """Open without creation and reject obvious symlinks/aliases.

    Windows path checks are advisory until a parent-handle chain and effective
    DACL checks are held by the later transaction service. No lock implies
    authorization or path continuity after the context closes.
    """
    _validate_candidate(path)
    if sys.platform not in {"win32", "darwin", "linux"}:
        _refuse(PrivateExistingFileLockCode.UNSUPPORTED)
    if sys.platform != "win32" and not getattr(os, "O_NOFOLLOW", 0):
        _refuse(PrivateExistingFileLockCode.UNSUPPORTED)
    try:
        initial = os.lstat(path)
        if not _safe_regular_file(initial):
            _refuse(PrivateExistingFileLockCode.UNSAFE_FILE)
        if getattr(initial, "st_file_attributes", 0) & 0x400:
            _refuse(PrivateExistingFileLockCode.UNSAFE_FILE)
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        if sys.platform == "win32":
            flags |= getattr(os, "O_BINARY", 0)
        else:
            flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
    except FileNotFoundError:
        _refuse(PrivateExistingFileLockCode.MISSING)
    except PermissionError:
        _refuse(PrivateExistingFileLockCode.ACCESS_DENIED)
    except OSError:
        _refuse(PrivateExistingFileLockCode.IO_ERROR)
    try:
        observed = os.fstat(fd)
        # Detect replacement between lstat and open when native identity is
        # available. This is NOT an atomic parent-path binding guarantee.
        if (
            observed.st_dev != initial.st_dev
            or observed.st_ino != initial.st_ino
            or not _safe_regular_file(observed)
        ):
            _refuse(PrivateExistingFileLockCode.UNSAFE_FILE)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _acquire(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _refuse(PrivateExistingFileLockCode.BUSY)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} or getattr(
            exc, "winerror", None
        ) in {32, 33}:
            _refuse(PrivateExistingFileLockCode.BUSY)
        _refuse(PrivateExistingFileLockCode.IO_ERROR)


def _release(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        _refuse(PrivateExistingFileLockCode.IO_ERROR)


@contextmanager
def hold_existing_private_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive nonblocking cross-process lock on a preexisting file.

    No file bytes are changed and no files are created. There is no timeout,
    polling, stale-lock deletion or implicit recovery. A BUSY state is a safe
    caller-visible refusal. Locking does not qualify store protection or permit
    subsequent private writes. This helper does NOT expose the writable fd.
    """
    fd = _open_existing(path)
    acquired = False
    try:
        _acquire(fd)
        acquired = True
        yield
    finally:
        try:
            if acquired:
                _release(fd)
        finally:
            os.close(fd)
