"""Retain a native private journal directory identity during a guarded scope.

Core #238 Slice 3D5: local, no-write, non-authorizing foundation. Existing
registry/workspace locks are held while a verified native directory handle
remains open. The path is independently checked at entry and normal exit.
Neither the handle nor a capability/token is yielded to a caller. On cloud
or hostile same-user filesystems this is NOT an atomic/distributed guard.
"""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from ctypes import wintypes
from enum import Enum
from pathlib import Path
from typing import Iterator, NoReturn

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class RetainedJournalGuardCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    COORDINATION_REFUSED = "coordination_refused"
    MISSING_DIRECTORY = "missing_directory"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_SCOPE = "changed_during_scope"
    IO_ERROR = "io_error"


class RetainedJournalGuardError(RuntimeError):
    """Bounded refusal: never include paths, identities, handles or contents."""

    def __init__(self, code: RetainedJournalGuardCode) -> None:
        self.code = code
        super().__init__(
            f"Retained private journal directory guard refused: {code.value}."
        )


def _refuse(code: RetainedJournalGuardCode) -> NoReturn:
    raise RetainedJournalGuardError(code)


def _identity(s: os.stat_result) -> tuple[int, int, int, int, int]:
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_ctime_ns)


def _linux_check(
    fd: int, directory: Path, uid: int, expected: tuple[int, int, int, int, int]
) -> None:
    """Verify the same opened private directory and present path each time."""
    try:
        active = os.fstat(fd)
        at_path = os.lstat(directory)
        getter = getattr(os, "geteuid", None)
        if getter is None or getter() != uid:
            _refuse(RetainedJournalGuardCode.OWNER_CHANGED)
        if (
            not stat.S_ISDIR(active.st_mode)
            or not stat.S_ISDIR(at_path.st_mode)
            or _identity(active) != expected
            or _identity(at_path) != expected
        ):
            _refuse(RetainedJournalGuardCode.CHANGED_DURING_SCOPE)
        if active.st_uid != uid or stat.S_IMODE(active.st_mode) != 0o700:
            _refuse(RetainedJournalGuardCode.REFUSED_PROTECTION)
        if posix._acl_absent(fd) is not None:
            _refuse(RetainedJournalGuardCode.REFUSED_PROTECTION)
        if not posix._is_known_local_filesystem(fd):
            _refuse(RetainedJournalGuardCode.REFUSED_BACKING)
    except (FileNotFoundError, NotADirectoryError):
        _refuse(RetainedJournalGuardCode.CHANGED_DURING_SCOPE)
    except PermissionError:
        _refuse(RetainedJournalGuardCode.ACCESS_DENIED)
    except (OSError, ValueError, AttributeError, OverflowError):
        _refuse(RetainedJournalGuardCode.IO_ERROR)


@contextmanager
def _held_linux(directory: Path, owner: inspection.EffectiveOSOwner) -> Iterator[None]:
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0):
        _refuse(RetainedJournalGuardCode.UNSUPPORTED)
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        _refuse(RetainedJournalGuardCode.OWNER_UNAVAILABLE)
    uid = int(owner.value)
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() != uid:
        _refuse(RetainedJournalGuardCode.OWNER_CHANGED)
    fd, problem = posix._open_verified_parent(directory, uid)
    if problem is not None:
        if problem is posix.PrivateChildCreationState.REFUSED_BACKING:
            _refuse(RetainedJournalGuardCode.REFUSED_BACKING)
        if problem is posix.PrivateChildCreationState.ACCESS_DENIED:
            _refuse(RetainedJournalGuardCode.ACCESS_DENIED)
        if problem is posix.PrivateChildCreationState.UNSAFE_PATH:
            _refuse(RetainedJournalGuardCode.MISSING_DIRECTORY)
        _refuse(RetainedJournalGuardCode.REFUSED_PROTECTION)
    if fd is None:
        _refuse(RetainedJournalGuardCode.UNSUPPORTED)
    try:
        try:
            expected = _identity(os.fstat(fd))
        except (OSError, ValueError, OverflowError):
            _refuse(RetainedJournalGuardCode.IO_ERROR)
        _linux_check(fd, directory, uid, expected)
        # This handle and both local locks remain held throughout the body.
        yield
        # Verify again on successful scope completion; a failing operation's
        # exception must not be replaced by a cleanup/classification error.
        _linux_check(fd, directory, uid, expected)
    finally:
        os.close(fd)


def _windows_check(
    kernel: object,
    advapi: object,
    directory: Path,
    handle: int,
    expected: tuple[int, bytes],
    owner: inspection.EffectiveOSOwner,
) -> None:
    """Verify handle identity and DACL, plus a new path-open identity."""
    info = descriptor._windows_info(kernel, handle)
    if (
        info is None
        or info[0] & 0x400
        or not (info[0] & 0x10)
        or not info[1].directory
        or info[1].delete_pending
    ):
        _refuse(RetainedJournalGuardCode.REFUSED_PROTECTION)
    if (
        wincheck._handle_dacl_state(kernel, advapi, handle, owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        _refuse(RetainedJournalGuardCode.REFUSED_PROTECTION)
    if anchor._windows_id(kernel, handle) != expected:
        _refuse(RetainedJournalGuardCode.CHANGED_DURING_SCOPE)
    second, error = anchor._windows_open(kernel, directory)
    if second is None:
        if error in (2, 3):
            _refuse(RetainedJournalGuardCode.CHANGED_DURING_SCOPE)
        if error in (5, 32):
            _refuse(RetainedJournalGuardCode.ACCESS_DENIED)
        _refuse(RetainedJournalGuardCode.IO_ERROR)
    try:
        second_info = descriptor._windows_info(kernel, second)
        if (
            second_info is None
            or second_info[0] & 0x400
            or not (second_info[0] & 0x10)
            or not second_info[1].directory
            or second_info[1].delete_pending
            or anchor._windows_id(kernel, second) != expected
            or wincheck._handle_dacl_state(kernel, advapi, second, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            _refuse(RetainedJournalGuardCode.CHANGED_DURING_SCOPE)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(second))  # type: ignore[attr-defined]
    if (
        wincheck._native_windows_walk(directory, owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        _refuse(RetainedJournalGuardCode.REFUSED_PROTECTION)
    if not wincreate._known_fixed_local_volume(kernel, directory):
        _refuse(RetainedJournalGuardCode.REFUSED_BACKING)


@contextmanager
def _held_windows(
    directory: Path, owner: inspection.EffectiveOSOwner
) -> Iterator[None]:
    if owner.kind != "windows_token_sid":
        _refuse(RetainedJournalGuardCode.OWNER_UNAVAILABLE)
    first: int | None = None
    kernel = None
    try:
        try:
            kernel, advapi = wincheck._bind_api()
            if not wincreate._known_fixed_local_volume(kernel, directory):
                _refuse(RetainedJournalGuardCode.REFUSED_BACKING)
            initial = wincheck._native_windows_walk(directory, owner)
            if initial is NativePrivatePreflightState.MISSING:
                _refuse(RetainedJournalGuardCode.MISSING_DIRECTORY)
            if initial is NativePrivatePreflightState.ACCESS_DENIED:
                _refuse(RetainedJournalGuardCode.ACCESS_DENIED)
            if initial is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED:
                _refuse(RetainedJournalGuardCode.REFUSED_PROTECTION)
            first, error = anchor._windows_open(kernel, directory)
            if first is None:
                if error in (2, 3):
                    _refuse(RetainedJournalGuardCode.MISSING_DIRECTORY)
                if error in (5, 32):
                    _refuse(RetainedJournalGuardCode.ACCESS_DENIED)
                _refuse(RetainedJournalGuardCode.IO_ERROR)
            expected = anchor._windows_id(kernel, first)
            if expected is None or not any(expected[1]):
                _refuse(RetainedJournalGuardCode.UNSUPPORTED)
            _windows_check(kernel, advapi, directory, first, expected, owner)
        except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
            _refuse(RetainedJournalGuardCode.UNSUPPORTED)
        except (AttributeError, OSError, ValueError, TypeError, OverflowError):
            _refuse(RetainedJournalGuardCode.IO_ERROR)
        yield
        try:
            _windows_check(kernel, advapi, directory, first, expected, owner)
        except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
            _refuse(RetainedJournalGuardCode.UNSUPPORTED)
        except (AttributeError, OSError, ValueError, TypeError, OverflowError):
            _refuse(RetainedJournalGuardCode.IO_ERROR)
    finally:
        if first is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(first))


@contextmanager
def _hold_existing_retained_journal_guard(
    existing_private_root: Path, existing_workspace_root: Path
) -> Iterator[None]:
    """Hold both locks and the native journal directory through a no-write scope.

    Yields only None. Does not yield an FD/HANDLE/path/commit token or validate
    journal contents, registry CAS, approved user action or complete parent-chain
    continuity. Future writers must supply stronger checks before any mutation.
    """
    if sys.platform not in {"linux", "win32"}:
        _refuse(RetainedJournalGuardCode.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(RetainedJournalGuardCode.INVALID_REQUEST)
    try:
        with ordered._hold_existing_ordered_coordination(
            existing_private_root, existing_workspace_root
        ):
            before = ordered._owner()
            directory = existing_private_root / "transactions"
            held = (
                _held_linux(directory, before)
                if sys.platform == "linux"
                else _held_windows(directory, before)
            )
            with held:
                if before != ordered._owner():
                    _refuse(RetainedJournalGuardCode.OWNER_CHANGED)
                yield
                if before != ordered._owner():
                    _refuse(RetainedJournalGuardCode.OWNER_CHANGED)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            _refuse(RetainedJournalGuardCode.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            _refuse(RetainedJournalGuardCode.OWNER_UNAVAILABLE)
        _refuse(RetainedJournalGuardCode.COORDINATION_REFUSED)
