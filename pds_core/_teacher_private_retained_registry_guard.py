"""Retain a private registry-file identity during guarded local review (#238 3D7).

This non-authorizing scope nests inside the existing retained transactions
journal guard. Both local locks, the private journal directory handle, and a
native registry file handle remain open until exit. Read-only identity and
protection checks cannot establish durable CAS or distributed serialization.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from contextlib import contextmanager
from ctypes import wintypes
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, NoReturn

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class RetainedRegistryGuardCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    JOURNAL_GUARD_REFUSED = "journal_guard_refused"
    MISSING_REGISTRY = "missing_registry"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_SCOPE = "changed_during_scope"
    IO_ERROR = "io_error"


class RetainedRegistryGuardError(RuntimeError):
    """Sanitized refusal without owner, raw path, file identifier or bytes."""

    def __init__(self, code: RetainedRegistryGuardCode) -> None:
        self.code = code
        super().__init__(f"Retained private registry guard refused: {code.value}.")


def _refuse(code: RetainedRegistryGuardCode) -> NoReturn:
    raise RetainedRegistryGuardError(code)


def _linux_signature(
    info: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _linux_check(
    parent_fd: int,
    file_fd: int,
    private_root: Path,
    parent_expected: tuple[int, int, int, int, int, int, int, int],
    expected: tuple[int, int, int, int, int, int, int, int],
    uid: int,
) -> None:
    """Check the opened file, its current directory entry and native protections."""
    try:
        getter = getattr(os, "geteuid", None)
        if getter is None or getter() != uid:
            _refuse(RetainedRegistryGuardCode.OWNER_CHANGED)
        current = os.fstat(file_fd)
        entry = os.stat("registry.json", dir_fd=parent_fd, follow_symlinks=False)
        native_parent = os.fstat(parent_fd)
        at_parent = os.lstat(private_root)
        if (
            not stat.S_ISDIR(native_parent.st_mode)
            or not stat.S_ISDIR(at_parent.st_mode)
            or _linux_signature(native_parent) != parent_expected
            or _linux_signature(at_parent) != parent_expected
            or not stat.S_ISREG(current.st_mode)
            or not stat.S_ISREG(entry.st_mode)
            or _linux_signature(current) != expected
            or _linux_signature(entry) != expected
        ):
            _refuse(RetainedRegistryGuardCode.CHANGED_DURING_SCOPE)
        if (
            current.st_uid != uid
            or stat.S_IMODE(current.st_mode) != 0o600
            or current.st_nlink != 1
        ):
            _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
        if posix._acl_absent(file_fd) is not None:
            _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
        if not posix._is_known_local_filesystem(file_fd):
            _refuse(RetainedRegistryGuardCode.REFUSED_BACKING)
    except (FileNotFoundError, NotADirectoryError):
        _refuse(RetainedRegistryGuardCode.CHANGED_DURING_SCOPE)
    except PermissionError:
        _refuse(RetainedRegistryGuardCode.ACCESS_DENIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        _refuse(RetainedRegistryGuardCode.IO_ERROR)


@contextmanager
def _held_linux_registry(
    private_root: Path, owner: inspection.EffectiveOSOwner
) -> Iterator[None]:
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0):
        _refuse(RetainedRegistryGuardCode.UNSUPPORTED)
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        _refuse(RetainedRegistryGuardCode.OWNER_UNAVAILABLE)
    uid = int(owner.value)
    if getattr(os, "geteuid", lambda: -1)() != uid:
        _refuse(RetainedRegistryGuardCode.OWNER_CHANGED)
    parent, failure = posix._open_verified_parent(private_root, uid)
    if failure is not None:
        if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
            _refuse(RetainedRegistryGuardCode.REFUSED_BACKING)
        if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
            _refuse(RetainedRegistryGuardCode.ACCESS_DENIED)
        _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
    if parent is None:
        _refuse(RetainedRegistryGuardCode.UNSUPPORTED)
    opened: int | None = None
    try:
        try:
            opened = os.open(
                "registry.json",
                os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent,
            )
        except FileNotFoundError:
            _refuse(RetainedRegistryGuardCode.MISSING_REGISTRY)
        except PermissionError:
            _refuse(RetainedRegistryGuardCode.ACCESS_DENIED)
        except OSError:
            _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
        try:
            expected = _linux_signature(os.fstat(opened))
            parent_expected = _linux_signature(os.fstat(parent))
        except (OSError, ValueError, OverflowError):
            _refuse(RetainedRegistryGuardCode.IO_ERROR)
        _linux_check(parent, opened, private_root, parent_expected, expected, uid)
        yield
        # Retaining an FD does not block same-owner or hostile writers.
        # Fail closed if the file or directory entry changed during the scope.
        _linux_check(parent, opened, private_root, parent_expected, expected, uid)
    finally:
        if opened is not None:
            os.close(opened)
        os.close(parent)


class _FileBasicInfo(ctypes.Structure):
    _fields_ = [
        ("creation_time", ctypes.c_int64),
        ("access_time", ctypes.c_int64),
        ("write_time", ctypes.c_int64),
        ("change_time", ctypes.c_int64),
        ("attributes", wintypes.DWORD),
    ]


def _windows_signature(
    kernel: Any, handle: int
) -> tuple[int, bytes, int, int, int] | None:
    identity = anchor._windows_id(kernel, handle)
    detail = descriptor._windows_info(kernel, handle)
    basic = _FileBasicInfo()
    if (
        identity is None
        or not any(identity[1])
        or detail is None
        or detail[0] & (0x400 | 0x10)
        or detail[1].directory
        or detail[1].delete_pending
        or detail[1].number_of_links != 1
        or not kernel.GetFileInformationByHandleEx(
            wintypes.HANDLE(handle), 0, ctypes.byref(basic), ctypes.sizeof(basic)
        )
        or basic.attributes & (0x400 | 0x10)
    ):
        return None
    return (
        identity[0],
        identity[1],
        int(detail[1].end_of_file),
        int(basic.write_time),
        int(basic.change_time),
    )


def _windows_check(
    kernel: Any,
    advapi: Any,
    path: Path,
    opened: int,
    expected: tuple[int, bytes, int, int, int],
    owner: inspection.EffectiveOSOwner,
) -> None:
    if _windows_signature(kernel, opened) != expected:
        _refuse(RetainedRegistryGuardCode.CHANGED_DURING_SCOPE)
    if (
        wincheck._handle_dacl_state(kernel, advapi, opened, owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
    second, error = anchor._windows_open(kernel, path)
    if second is None:
        if error in (2, 3):
            _refuse(RetainedRegistryGuardCode.CHANGED_DURING_SCOPE)
        if error in (5, 32):
            _refuse(RetainedRegistryGuardCode.ACCESS_DENIED)
        _refuse(RetainedRegistryGuardCode.IO_ERROR)
    try:
        if (
            _windows_signature(kernel, second) != expected
            or wincheck._handle_dacl_state(kernel, advapi, second, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            _refuse(RetainedRegistryGuardCode.CHANGED_DURING_SCOPE)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(second))
    if (
        wincheck._native_windows_walk(path.parent, owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
    if not wincreate._known_fixed_local_volume(kernel, path.parent):
        _refuse(RetainedRegistryGuardCode.REFUSED_BACKING)


@contextmanager
def _held_windows_registry(
    private_root: Path, owner: inspection.EffectiveOSOwner
) -> Iterator[None]:
    if owner.kind != "windows_token_sid":
        _refuse(RetainedRegistryGuardCode.OWNER_UNAVAILABLE)
    kernel: Any = None
    opened: int | None = None
    try:
        try:
            kernel, advapi = wincheck._bind_api()
            if not wincreate._known_fixed_local_volume(kernel, private_root):
                _refuse(RetainedRegistryGuardCode.REFUSED_BACKING)
            first_walk = wincheck._native_windows_walk(private_root, owner)
            if first_walk is NativePrivatePreflightState.MISSING:
                _refuse(RetainedRegistryGuardCode.MISSING_REGISTRY)
            if first_walk is NativePrivatePreflightState.ACCESS_DENIED:
                _refuse(RetainedRegistryGuardCode.ACCESS_DENIED)
            if first_walk is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED:
                _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
            path = private_root / "registry.json"
            opened, error = anchor._windows_open(kernel, path)
            if opened is None:
                if error in (2, 3):
                    _refuse(RetainedRegistryGuardCode.MISSING_REGISTRY)
                if error in (5, 32):
                    _refuse(RetainedRegistryGuardCode.ACCESS_DENIED)
                _refuse(RetainedRegistryGuardCode.IO_ERROR)
            expected = _windows_signature(kernel, opened)
            if expected is None:
                _refuse(RetainedRegistryGuardCode.REFUSED_PROTECTION)
            _windows_check(kernel, advapi, path, opened, expected, owner)
        except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
            _refuse(RetainedRegistryGuardCode.UNSUPPORTED)
        except (AttributeError, OSError, ValueError, TypeError, OverflowError):
            _refuse(RetainedRegistryGuardCode.IO_ERROR)
        yield
        try:
            _windows_check(kernel, advapi, path, opened, expected, owner)
        except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
            _refuse(RetainedRegistryGuardCode.UNSUPPORTED)
        except (AttributeError, OSError, ValueError, TypeError, OverflowError):
            _refuse(RetainedRegistryGuardCode.IO_ERROR)
    finally:
        if kernel is not None and opened is not None:
            kernel.CloseHandle(wintypes.HANDLE(opened))


@contextmanager
def _hold_existing_retained_registry_guard(
    existing_private_root: Path, existing_workspace_root: Path
) -> Iterator[None]:
    """Retain registry and transaction handles under one pair of local locks.

    Yields no handle or permission token. Does not read or commit registry,
    descriptor or intent contents; caller remains responsible for currentness,
    journal recovery, native workspace path safety and explicit confirmation.
    """
    if sys.platform not in {"linux", "win32"}:
        _refuse(RetainedRegistryGuardCode.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(RetainedRegistryGuardCode.INVALID_REQUEST)
    try:
        with journal_guard._hold_existing_retained_journal_guard(
            existing_private_root, existing_workspace_root
        ):
            before = ordered._owner()
            with (
                _held_linux_registry(existing_private_root, before)
                if sys.platform == "linux"
                else _held_windows_registry(existing_private_root, before)
            ):
                if before != ordered._owner():
                    _refuse(RetainedRegistryGuardCode.OWNER_CHANGED)
                yield
                if before != ordered._owner():
                    _refuse(RetainedRegistryGuardCode.OWNER_CHANGED)
    except journal_guard.RetainedJournalGuardError as error:
        if error.code is journal_guard.RetainedJournalGuardCode.OWNER_CHANGED:
            _refuse(RetainedRegistryGuardCode.OWNER_CHANGED)
        if error.code is journal_guard.RetainedJournalGuardCode.OWNER_UNAVAILABLE:
            _refuse(RetainedRegistryGuardCode.OWNER_UNAVAILABLE)
        _refuse(RetainedRegistryGuardCode.JOURNAL_GUARD_REFUSED)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            _refuse(RetainedRegistryGuardCode.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            _refuse(RetainedRegistryGuardCode.OWNER_UNAVAILABLE)
        _refuse(RetainedRegistryGuardCode.JOURNAL_GUARD_REFUSED)
