"""Create-only empty private registry bootstrap candidate for Core #238.

A narrowly scoped internal primitive: exact local Notes v1 root; existing
verified private owner and .registry.lock; nonblocking coordination held across
an exclusive, explicitly protected registry.json creation. A created file is
NOT a bound workspace, approved transaction, Notes service or READY handle.
Never mutates any existing registry, descriptor, journal, record or lock file.
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

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState

_FILE_NAME = "registry.json"


class PrivateRegistryBootstrapState(str, Enum):
    CREATED_RESTRICTIVE_UNQUALIFIED = "created_restrictive_unqualified"
    ALREADY_EXISTS = "already_exists"
    INVALID_REQUEST = "invalid_request"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"
    CREATION_UNVERIFIED = "creation_unverified"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateRegistryBootstrapState.CREATED_RESTRICTIVE_UNQUALIFIED: "Empty owner registry candidate created; workspace binding remains unqualified.",
    PrivateRegistryBootstrapState.ALREADY_EXISTS: "Registry entry exists; bytes were preserved without inspection or replacement.",
    PrivateRegistryBootstrapState.INVALID_REQUEST: "Private registry bootstrap request invalid.",
    PrivateRegistryBootstrapState.REFUSED_PROTECTION: "Private registry protection could not be established.",
    PrivateRegistryBootstrapState.REFUSED_BACKING: "Private registry backing is unqualified.",
    PrivateRegistryBootstrapState.ACCESS_DENIED: "Private registry creation access denied.",
    PrivateRegistryBootstrapState.COORDINATION_UNAVAILABLE: "Registry lock unavailable or unsafe; no registry write attempted.",
    PrivateRegistryBootstrapState.CREATION_UNVERIFIED: "Registry candidate may exist; manual review required.",
    PrivateRegistryBootstrapState.UNSUPPORTED: "Private registry bootstrap unsupported on this platform.",
}


@dataclass(frozen=True, slots=True)
class PrivateRegistryBootstrapResult:
    state: PrivateRegistryBootstrapState
    message: str


def _result(state: PrivateRegistryBootstrapState) -> PrivateRegistryBootstrapResult:
    return PrivateRegistryBootstrapResult(state, _MESSAGES[state])


def _bytes_for_owner(kind: str, principal: str) -> bytes:
    """Never accept user-provided registry bytes or install a binding here."""
    if kind == "windows_token_sid":
        owner = metadata.PrivateRegistryOwner("windows_token_sid", principal)
    elif kind == "posix_euid":
        owner = metadata.PrivateRegistryOwner("posix_euid", principal)
    else:
        raise metadata.PrivateMetadataError(
            metadata.PrivateMetadataErrorCode.INVALID_IDENTITY
        )
    return metadata.encode_private_registry(metadata.PrivateRegistry(owner, 1, ()))


def _qualified_existing_lock_linux(root: Path, uid: int, directory_fd: int) -> bool:
    """Refuse an unverified lock file even when flock acquisition succeeded."""
    opened: int | None = None
    try:
        opened = os.open(
            ".registry.lock",
            os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
        info = os.fstat(opened)
        parent = os.fstat(directory_fd)
        linked = os.stat(".registry.lock", dir_fd=directory_fd, follow_symlinks=False)
        return bool(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == uid
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_nlink == 1
            and info.st_size == 1
            and (info.st_dev, info.st_ino) == (linked.st_dev, linked.st_ino)
            and info.st_dev == parent.st_dev
            and os.read(opened, 2) == b"\x00"
            and posix._acl_absent(opened) is None
            and posix._is_known_local_filesystem(opened)
        )
    except (OSError, AttributeError, ValueError, OverflowError):
        return False
    finally:
        if opened is not None:
            os.close(opened)


class _FileStandardInfo(ctypes.Structure):
    _fields_ = [
        ("allocation_size", ctypes.c_int64),
        ("end_of_file", ctypes.c_int64),
        ("number_of_links", wintypes.DWORD),
        ("delete_pending", wintypes.BOOL),
        ("directory", wintypes.BOOL),
    ]


def _qualified_existing_lock_windows(
    kernel: Any, advapi: Any, root: Path, owner: inspection.EffectiveOSOwner
) -> bool:
    """Check opened lock-file handle properties without reading its locked byte."""
    # Native handle DACL validation is internal and does not return authority.
    handle_value: int | None = None
    try:
        native = kernel
        native.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        native.CreateFileW.restype = wintypes.HANDLE
        native.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        native.GetFileInformationByHandleEx.restype = wintypes.BOOL
        raw = native.CreateFileW(
            str(root / ".registry.lock"), 0x80 | 0x20000, 7, None, 3, 0x00200000, None
        )
        handle_value = ctypes.cast(raw, ctypes.c_void_p).value
        if handle_value is None or handle_value == ctypes.c_void_p(-1).value:
            handle_value = None
            return False
        h = wintypes.HANDLE(handle_value)
        attrs = lock_provision._FileAttributeTagInfo()
        standard = _FileStandardInfo()
        security_kernel, security_advapi = wincheck._bind_api()
        return bool(
            native.GetFileInformationByHandleEx(
                h, 9, ctypes.byref(attrs), ctypes.sizeof(attrs)
            )
            and not attrs.attributes & (0x10 | 0x400)
            and native.GetFileInformationByHandleEx(
                h, 1, ctypes.byref(standard), ctypes.sizeof(standard)
            )
            and not standard.directory
            and not standard.delete_pending
            and standard.end_of_file == 1
            and standard.number_of_links == 1
            and wincheck._handle_dacl_state(
                security_kernel, security_advapi, handle_value, owner
            )
            is NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        )
    except (
        AttributeError,
        OSError,
        ValueError,
        TypeError,
        OverflowError,
        wincheck._NativeUnavailable,
    ):
        return False
    finally:
        if handle_value is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle_value))


def _linux_create(root: Path) -> PrivateRegistryBootstrapResult:
    uid_reader = getattr(os, "geteuid", None)
    if uid_reader is None or not hasattr(os, "O_NOFOLLOW"):
        return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
    uid = uid_reader()
    if type(uid) is not int or uid <= 0:
        return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
    data = _bytes_for_owner("posix_euid", str(uid))
    fd, failure = posix._open_verified_parent(root, uid)
    if failure is not None:
        if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
            return _result(PrivateRegistryBootstrapState.REFUSED_BACKING)
        if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
            return _result(PrivateRegistryBootstrapState.ACCESS_DENIED)
        return _result(PrivateRegistryBootstrapState.REFUSED_PROTECTION)
    if fd is None:
        return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
    created = False
    file_fd: int | None = None
    try:
        if not _qualified_existing_lock_linux(root, uid, fd):
            return _result(PrivateRegistryBootstrapState.REFUSED_PROTECTION)
        try:
            file_fd = os.open(
                _FILE_NAME,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW")
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=fd,
            )
            created = True
        except FileExistsError:
            return _result(PrivateRegistryBootstrapState.ALREADY_EXISTS)
        except PermissionError:
            return _result(PrivateRegistryBootstrapState.ACCESS_DENIED)
        except OSError:
            return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
        written = 0
        while written < len(data):
            count = os.write(file_fd, data[written:])
            if count <= 0:
                return _result(PrivateRegistryBootstrapState.CREATION_UNVERIFIED)
            written += count
        os.fsync(file_fd)
        observed = os.fstat(file_fd)
        linked = os.stat(_FILE_NAME, dir_fd=fd, follow_symlinks=False)
        parent = os.fstat(fd)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != uid
            or stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_nlink != 1
            or observed.st_size != len(data)
            or (observed.st_dev, observed.st_ino) != (linked.st_dev, linked.st_ino)
            or observed.st_dev != parent.st_dev
            or posix._acl_absent(file_fd) is not None
            or not posix._is_known_local_filesystem(file_fd)
        ):
            return _result(PrivateRegistryBootstrapState.CREATION_UNVERIFIED)
        os.fsync(fd)
        return _result(PrivateRegistryBootstrapState.CREATED_RESTRICTIVE_UNQUALIFIED)
    except (OSError, AttributeError, ValueError, OverflowError):
        return _result(
            PrivateRegistryBootstrapState.CREATION_UNVERIFIED
            if created
            else PrivateRegistryBootstrapState.UNSUPPORTED
        )
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(fd)


def _windows_create(root: Path) -> PrivateRegistryBootstrapResult:
    try:
        current_owner = inspection._effective_owner("win32")
        if current_owner.kind != "windows_token_sid":
            return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
        kernel, advapi = wincreate._windows_api()
    except (inspection._OwnerUnverifiable, wincreate._NativeUnavailable):
        return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
    if not wincreate._known_fixed_local_volume(kernel, root):
        return _result(PrivateRegistryBootstrapState.REFUSED_BACKING)
    if (
        wincheck._native_windows_walk(root, current_owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        return _result(PrivateRegistryBootstrapState.REFUSED_PROTECTION)
    if not _qualified_existing_lock_windows(kernel, advapi, root, current_owner):
        return _result(PrivateRegistryBootstrapState.REFUSED_PROTECTION)
    try:
        data = _bytes_for_owner("windows_token_sid", current_owner.value)
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
    except (
        OSError,
        AttributeError,
        TypeError,
        ValueError,
        metadata.PrivateMetadataError,
    ):
        return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
    created = False
    handle_value: int | None = None
    try:
        handle_value, error = lock_provision._create_file_explicit_dacl_windows(
            kernel, advapi, root / _FILE_NAME, current_owner.value
        )
        if handle_value is None:
            if error in (80, 183):
                return _result(PrivateRegistryBootstrapState.ALREADY_EXISTS)
            if error in (5, 1314):
                return _result(PrivateRegistryBootstrapState.ACCESS_DENIED)
            return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
        created = True
        handle = wintypes.HANDLE(handle_value)
        buffer = ctypes.create_string_buffer(data)
        written = wintypes.DWORD()
        if not kernel.WriteFile(
            handle, buffer, len(data), ctypes.byref(written), None
        ) or written.value != len(data):
            return _result(PrivateRegistryBootstrapState.CREATION_UNVERIFIED)
        if not kernel.FlushFileBuffers(handle):
            return _result(PrivateRegistryBootstrapState.CREATION_UNVERIFIED)
        attributes = lock_provision._FileAttributeTagInfo()
        if not kernel.GetFileInformationByHandleEx(
            handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)
        ) or attributes.attributes & (0x10 | 0x400):
            return _result(PrivateRegistryBootstrapState.CREATION_UNVERIFIED)
        security_kernel, security_advapi = wincheck._bind_api()
        if (
            wincheck._handle_dacl_state(
                security_kernel, security_advapi, handle_value, current_owner
            )
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or wincheck._native_windows_walk(root, current_owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, root)
        ):
            return _result(PrivateRegistryBootstrapState.CREATION_UNVERIFIED)
        return _result(PrivateRegistryBootstrapState.CREATED_RESTRICTIVE_UNQUALIFIED)
    except (
        OSError,
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
        inspection._OwnerUnverifiable,
        wincreate._NativeUnavailable,
        wincheck._NativeUnavailable,
    ):
        return _result(
            PrivateRegistryBootstrapState.CREATION_UNVERIFIED
            if created
            else PrivateRegistryBootstrapState.UNSUPPORTED
        )
    finally:
        if handle_value is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle_value))


def create_empty_private_registry_candidate(
    existing_private_root: Path,
) -> PrivateRegistryBootstrapResult:
    """Explicit create-only empty owner-registry candidate; no workspace binding.

    An existing prequalified .registry.lock must be acquired nonblockingly.
    No caller is wired to a public API. The result never grants writable scope.
    """
    if not isinstance(existing_private_root, Path):
        return _result(PrivateRegistryBootstrapState.INVALID_REQUEST)
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRegistryBootstrapState.UNSUPPORTED)
    if not lock_provision._requested_root(existing_private_root, sys.platform):
        return _result(PrivateRegistryBootstrapState.INVALID_REQUEST)
    # Path-based lock is coordination only, not held native parent-handle proof.
    # Revalidate parent inside the lock before the exclusive create.
    try:
        with locking.hold_existing_private_lock(
            existing_private_root / ".registry.lock"
        ):
            if sys.platform == "linux":
                return _linux_create(existing_private_root)
            return _windows_create(existing_private_root)
    except locking.PrivateExistingFileLockError:
        return _result(PrivateRegistryBootstrapState.COORDINATION_UNAVAILABLE)
