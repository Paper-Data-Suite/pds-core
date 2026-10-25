"""Guarded first creation of the v1 private registry coordination file (#238).

The file is exactly ``.registry.lock`` with one zero byte. Creation requires
an already-existing, native-checked Notes v1 private root; it never creates
parent directories, registries, journals, workspace descriptors or Notes.
A created file is not a secure Notes collection or a write-authority handle.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState

_LOCK_FILE = ".registry.lock"
_LOCK_PAYLOAD = b"\x00"


class PrivateLockProvisionState(str, Enum):
    CREATED_RESTRICTIVE_UNQUALIFIED = "created_restrictive_unqualified"
    ALREADY_EXISTS = "already_exists"
    INVALID_REQUEST = "invalid_request"
    UNSAFE_PATH = "unsafe_path"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CREATION_UNVERIFIED = "creation_unverified"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED: "Private coordination file created; storage remains unqualified.",
    PrivateLockProvisionState.ALREADY_EXISTS: "Coordination file already exists and was not modified.",
    PrivateLockProvisionState.INVALID_REQUEST: "Private coordination request invalid.",
    PrivateLockProvisionState.UNSAFE_PATH: "Private coordination path unsafe.",
    PrivateLockProvisionState.REFUSED_PROTECTION: "Private coordination protection was not established.",
    PrivateLockProvisionState.REFUSED_BACKING: "Private coordination filesystem backing is unqualified.",
    PrivateLockProvisionState.ACCESS_DENIED: "Private coordination access denied.",
    PrivateLockProvisionState.CREATION_UNVERIFIED: "Coordination file may exist but was not verified; review required.",
    PrivateLockProvisionState.UNSUPPORTED: "Protected coordination file creation unsupported.",
}


@dataclass(frozen=True, slots=True)
class PrivateLockProvisionResult:
    """Bounded status; does not expose a file path, SID/UID, or OS handle."""

    state: PrivateLockProvisionState
    message: str


def _result(state: PrivateLockProvisionState) -> PrivateLockProvisionResult:
    return PrivateLockProvisionResult(state, _MESSAGES[state])


def _requested_root(value: Path, platform: str) -> bool:
    """Only the exact v1 local private root, never an arbitrary test/user path."""
    if not isinstance(value, Path) or not value.is_absolute():
        return False
    try:
        approved = inspection._candidate_private_root(platform)
    except (ValueError, RuntimeError, OSError):
        return False
    if platform == "win32":
        left = wincheck._windows_drive_components(value)
        right = wincheck._windows_drive_components(approved)
        return (
            left is not None
            and right is not None
            and (
                tuple(item.casefold() for item in left)
                == tuple(item.casefold() for item in right)
            )
        )
    return value == approved and all(
        component not in (".", "..") for component in str(value).split("/")
    )


def _linux_create(parent: Path) -> PrivateLockProvisionResult:
    if sys.platform != "linux" or not _requested_root(parent, "linux"):
        return _result(PrivateLockProvisionState.INVALID_REQUEST)
    uid_reader = getattr(os, "geteuid", None)
    if uid_reader is None:
        return _result(PrivateLockProvisionState.UNSUPPORTED)
    uid = uid_reader()
    if type(uid) is not int or uid <= 0:
        return _result(PrivateLockProvisionState.UNSUPPORTED)
    directory_fd, failure = posix._open_verified_parent(parent, uid)
    if failure is not None:
        if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
            return _result(PrivateLockProvisionState.REFUSED_BACKING)
        if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
            return _result(PrivateLockProvisionState.ACCESS_DENIED)
        if failure in (
            posix.PrivateChildCreationState.UNSAFE_PATH,
            posix.PrivateChildCreationState.INVALID_REQUEST,
        ):
            return _result(PrivateLockProvisionState.UNSAFE_PATH)
        return _result(PrivateLockProvisionState.REFUSED_PROTECTION)
    if directory_fd is None:
        return _result(PrivateLockProvisionState.UNSUPPORTED)
    created = False
    file_fd: int | None = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW")
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            file_fd = os.open(_LOCK_FILE, flags, 0o600, dir_fd=directory_fd)
            created = True
        except FileExistsError:
            return _result(PrivateLockProvisionState.ALREADY_EXISTS)
        except PermissionError:
            return _result(PrivateLockProvisionState.ACCESS_DENIED)
        except OSError:
            return _result(PrivateLockProvisionState.UNSUPPORTED)
        # Every post-create failure must be explicit about possible persistence.
        if os.write(file_fd, _LOCK_PAYLOAD) != len(_LOCK_PAYLOAD):
            return _result(PrivateLockProvisionState.CREATION_UNVERIFIED)
        os.fsync(file_fd)
        info = os.fstat(file_fd)
        linked = os.stat(_LOCK_FILE, dir_fd=directory_fd, follow_symlinks=False)
        parent_info = os.fstat(directory_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size != 1
            or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
            or info.st_dev != parent_info.st_dev
            or posix._acl_absent(file_fd) is not None
            or not posix._is_known_local_filesystem(file_fd)
        ):
            return _result(PrivateLockProvisionState.CREATION_UNVERIFIED)
        os.fsync(directory_fd)
        return _result(PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED)
    except (OSError, ValueError, OverflowError):
        return _result(
            PrivateLockProvisionState.CREATION_UNVERIFIED
            if created
            else PrivateLockProvisionState.UNSUPPORTED
        )
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD)]


def _create_file_explicit_dacl_windows(
    kernel: Any, advapi: Any, target: Path, account_sid: str
) -> tuple[int | None, int]:
    """Create-only, no inherited exposure window; return native handle for checks."""
    if wincreate._SID.fullmatch(account_sid) is None:
        raise wincreate._NativeUnavailable
    descriptor = ctypes.c_void_p()
    sddl = f"D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;{account_sid})"
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        raise wincreate._NativeUnavailable
    try:
        if not descriptor.value:
            raise wincreate._NativeUnavailable
        attrs = wincreate._SecurityAttributes(
            ctypes.sizeof(wincreate._SecurityAttributes), descriptor, False
        )
        # GENERIC_WRITE | FILE_READ_ATTRIBUTES | READ_CONTROL;
        # CREATE_NEW refuses any existing file, directory or reparse point.
        handle = kernel.CreateFileW(
            str(target),
            0x40000000 | 0x80 | 0x20000,
            0,
            ctypes.byref(attrs),
            1,
            0x80,
            None,
        )
        value = ctypes.cast(handle, ctypes.c_void_p).value
        if value is None or value == ctypes.c_void_p(-1).value:
            return None, ctypes.get_last_error()
        return value, 0
    finally:
        kernel.LocalFree(descriptor)


def _windows_create(parent: Path) -> PrivateLockProvisionResult:
    if sys.platform != "win32" or not _requested_root(parent, "win32"):
        return _result(PrivateLockProvisionState.INVALID_REQUEST)
    try:
        owner = inspection._effective_owner("win32")
        kernel, advapi = wincreate._windows_api()
    except (inspection._OwnerUnverifiable, wincreate._NativeUnavailable):
        return _result(PrivateLockProvisionState.UNSUPPORTED)
    if not wincreate._known_fixed_local_volume(kernel, parent):
        return _result(PrivateLockProvisionState.REFUSED_BACKING)
    state = wincheck._native_windows_walk(parent, owner)
    if state is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED:
        if state is NativePrivatePreflightState.ACCESS_DENIED:
            return _result(PrivateLockProvisionState.ACCESS_DENIED)
        return _result(PrivateLockProvisionState.REFUSED_PROTECTION)
    try:
        # Bound here rather than modifying the published preflight APIs.
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel.WriteFile.restype = wintypes.BOOL
        kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        kernel.FlushFileBuffers.restype = wintypes.BOOL
        kernel.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    except (OSError, AttributeError, TypeError, ValueError):
        return _result(PrivateLockProvisionState.UNSUPPORTED)
    handle_value: int | None = None
    created = False
    try:
        handle_value, error = _create_file_explicit_dacl_windows(
            kernel, advapi, parent / _LOCK_FILE, owner.value
        )
        if handle_value is None:
            if error in (80, 183):
                return _result(PrivateLockProvisionState.ALREADY_EXISTS)
            if error in (5, 1314):
                return _result(PrivateLockProvisionState.ACCESS_DENIED)
            return _result(PrivateLockProvisionState.UNSUPPORTED)
        created = True
        handle = wintypes.HANDLE(handle_value)
        buf = ctypes.create_string_buffer(_LOCK_PAYLOAD)
        written = wintypes.DWORD()
        if not kernel.WriteFile(
            handle, buf, len(_LOCK_PAYLOAD), ctypes.byref(written), None
        ) or written.value != len(_LOCK_PAYLOAD):
            return _result(PrivateLockProvisionState.CREATION_UNVERIFIED)
        if not kernel.FlushFileBuffers(handle):
            return _result(PrivateLockProvisionState.CREATION_UNVERIFIED)
        info = _FileAttributeTagInfo()
        if not kernel.GetFileInformationByHandleEx(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            return _result(PrivateLockProvisionState.CREATION_UNVERIFIED)
        if info.attributes & (0x10 | 0x400):  # DIRECTORY or REPARSE_POINT
            return _result(PrivateLockProvisionState.CREATION_UNVERIFIED)
        if (
            wincheck._handle_dacl_state(kernel, advapi, handle_value, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or wincheck._native_windows_walk(parent, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, parent)
        ):
            return _result(PrivateLockProvisionState.CREATION_UNVERIFIED)
        return _result(PrivateLockProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED)
    except (
        OSError,
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
        inspection._OwnerUnverifiable,
        wincreate._NativeUnavailable,
    ):
        return _result(
            PrivateLockProvisionState.CREATION_UNVERIFIED
            if created
            else PrivateLockProvisionState.UNSUPPORTED
        )
    finally:
        if handle_value is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle_value))


def create_private_registry_lock_file(
    existing_private_root: Path,
) -> PrivateLockProvisionResult:
    """Explicit one-file creation only; never creates the v1 root itself.

    Does not return a storage handle. Partial post-creation failure is left
    intact for recovery, never silently unlinked or chmod/chown repaired.
    """
    if not isinstance(existing_private_root, Path):
        return _result(PrivateLockProvisionState.INVALID_REQUEST)
    if sys.platform == "linux":
        return _linux_create(existing_private_root)
    if sys.platform == "win32":
        return _windows_create(existing_private_root)
    return _result(PrivateLockProvisionState.UNSUPPORTED)
