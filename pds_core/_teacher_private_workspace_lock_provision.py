"""Create-only, non-authorizing workspace coordination file (Core #238 3C8).

A local process can later lock this byte using the existing file-lock helper.
The file is non-secret workspace metadata, NOT a cross-device/OneDrive lock,
commit permission, ownership proof, Notes service, or registry mutation.
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

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as registry_file
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState

_METADATA_DIR = ".pds"
_LOCK_FILE = ".teacher-private-association.lock"
_LOCK_PAYLOAD = b"\x00"


class WorkspaceCoordinationProvisionState(str, Enum):
    CREATED_UNQUALIFIED = "created_unqualified"
    ALREADY_EXISTS = "already_exists"
    INVALID_REQUEST = "invalid_request"
    MISSING_METADATA_DIRECTORY = "missing_metadata_directory"
    REFUSED_PATH = "refused_path"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CREATION_UNVERIFIED = "creation_unverified"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    WorkspaceCoordinationProvisionState.CREATED_UNQUALIFIED: (
        "Workspace coordination file created; metadata writes remain unqualified."
    ),
    WorkspaceCoordinationProvisionState.ALREADY_EXISTS: (
        "Workspace coordination entry already exists and was left untouched."
    ),
    WorkspaceCoordinationProvisionState.INVALID_REQUEST: "Workspace coordination request invalid.",
    WorkspaceCoordinationProvisionState.MISSING_METADATA_DIRECTORY: (
        "Workspace metadata directory is absent; no setup performed."
    ),
    WorkspaceCoordinationProvisionState.REFUSED_PATH: "Workspace coordination path unsafe.",
    WorkspaceCoordinationProvisionState.REFUSED_PROTECTION: (
        "Workspace coordination filesystem permissions unqualified."
    ),
    WorkspaceCoordinationProvisionState.REFUSED_BACKING: (
        "Workspace coordination backing is unqualified."
    ),
    WorkspaceCoordinationProvisionState.ACCESS_DENIED: "Workspace coordination access denied.",
    WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED: (
        "Workspace coordination creation may be incomplete; review required."
    ),
    WorkspaceCoordinationProvisionState.UNSUPPORTED: (
        "Workspace coordination creation unsupported here."
    ),
}


@dataclass(frozen=True, slots=True)
class WorkspaceCoordinationProvisionResult:
    state: WorkspaceCoordinationProvisionState
    message: str


def _result(
    state: WorkspaceCoordinationProvisionState,
) -> WorkspaceCoordinationProvisionResult:
    return WorkspaceCoordinationProvisionResult(state, _MESSAGES[state])


def _walk_linux(
    workspace_root: Path, uid: int
) -> tuple[int | None, WorkspaceCoordinationProvisionState | None]:
    """No-follow walk through the workspace and its existing .pds directory.

    Retain the metadata directory FD to pin the target for openat creation.
    This is not a cross-tree atomic commit or protection from same-user code.
    """
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    current: int | None = None
    try:
        current = os.open("/", flags)
        names = (*workspace_root.parts[1:], _METADATA_DIR)
        for index, name in enumerate(names):
            next_fd = os.open(name, flags, dir_fd=current)
            os.close(current)
            current = next_fd
            info = os.fstat(current)
            if not stat.S_ISDIR(info.st_mode):
                return None, WorkspaceCoordinationProvisionState.REFUSED_PATH
            # A root-owned sticky /tmp parent is allowable; other writable
            # ancestors and foreign-owned path segments are not.
            mode = stat.S_IMODE(info.st_mode)
            if info.st_uid not in (0, uid) or (
                mode & 0o022 and not (info.st_uid == 0 and mode & stat.S_ISVTX)
            ):
                return None, WorkspaceCoordinationProvisionState.REFUSED_PATH
            if index == len(names) - 1:
                if info.st_uid != uid or mode & 0o077:
                    return None, WorkspaceCoordinationProvisionState.REFUSED_PROTECTION
                if posix._acl_absent(current) is not None:
                    return None, WorkspaceCoordinationProvisionState.REFUSED_PROTECTION
                if not posix._is_known_local_filesystem(current):
                    return None, WorkspaceCoordinationProvisionState.REFUSED_BACKING
        returned = current
        current = None
        return returned, None
    except FileNotFoundError:
        return None, WorkspaceCoordinationProvisionState.MISSING_METADATA_DIRECTORY
    except PermissionError:
        return None, WorkspaceCoordinationProvisionState.ACCESS_DENIED
    except (NotADirectoryError, IsADirectoryError):
        return None, WorkspaceCoordinationProvisionState.REFUSED_PATH
    except OSError:
        return None, WorkspaceCoordinationProvisionState.UNSUPPORTED
    finally:
        if current is not None:
            os.close(current)


def _create_linux(root: Path) -> WorkspaceCoordinationProvisionResult:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        return _result(WorkspaceCoordinationProvisionState.UNSUPPORTED)
    getuid = getattr(os, "geteuid", None)
    uid = getuid() if getuid is not None else None
    if type(uid) is not int or uid <= 0:
        return _result(WorkspaceCoordinationProvisionState.UNSUPPORTED)
    parent, failure = _walk_linux(root, uid)
    if failure is not None:
        return _result(failure)
    if parent is None:
        return _result(WorkspaceCoordinationProvisionState.UNSUPPORTED)
    created = False
    opened: int | None = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            opened = os.open(_LOCK_FILE, flags, 0o600, dir_fd=parent)
            created = True
        except FileExistsError:
            return _result(WorkspaceCoordinationProvisionState.ALREADY_EXISTS)
        except PermissionError:
            return _result(WorkspaceCoordinationProvisionState.ACCESS_DENIED)
        except OSError:
            return _result(WorkspaceCoordinationProvisionState.UNSUPPORTED)
        if os.write(opened, _LOCK_PAYLOAD) != 1:
            return _result(WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED)
        os.fsync(opened)
        info = os.fstat(opened)
        linked = os.stat(_LOCK_FILE, dir_fd=parent, follow_symlinks=False)
        parent_info = os.fstat(parent)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size != 1
            or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
            or info.st_dev != parent_info.st_dev
            or posix._acl_absent(opened) is not None
            or not posix._is_known_local_filesystem(opened)
        ):
            return _result(WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED)
        os.fsync(parent)
        return _result(WorkspaceCoordinationProvisionState.CREATED_UNQUALIFIED)
    except (OSError, ValueError, OverflowError):
        return _result(
            WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED
            if created
            else WorkspaceCoordinationProvisionState.UNSUPPORTED
        )
    finally:
        if opened is not None:
            os.close(opened)
        os.close(parent)


def _windows_parent(
    kernel: Any, advapi: Any, root: Path, owner: inspection.EffectiveOSOwner
) -> WorkspaceCoordinationProvisionState | None:
    """Verify metadata folder DACL from an open handle; not a retained write token."""
    if descriptor._windows_ancestry(kernel, root) is not None:
        return WorkspaceCoordinationProvisionState.REFUSED_PATH
    parent = root / _METADATA_DIR
    # Request READ_CONTROL explicitly: a descriptor-only reader need not have
    # it, but DACL inspection via GetSecurityInfo requires that access right.
    opened = kernel.CreateFileW(
        str(parent),
        0x00000080 | 0x00020000,
        7,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    value = ctypes.cast(opened, ctypes.c_void_p).value
    error = ctypes.get_last_error() if value in (None, ctypes.c_void_p(-1).value) else 0
    if value == ctypes.c_void_p(-1).value:
        value = None
    if value is None:
        if error in (2, 3):
            return WorkspaceCoordinationProvisionState.MISSING_METADATA_DIRECTORY
        if error in (5, 32):
            return WorkspaceCoordinationProvisionState.ACCESS_DENIED
        return WorkspaceCoordinationProvisionState.UNSUPPORTED
    try:
        info = descriptor._windows_info(kernel, value)
        if info is None or info[0] & 0x400 or not info[1].directory:
            return WorkspaceCoordinationProvisionState.REFUSED_PATH
        if (
            wincheck._handle_dacl_state(kernel, advapi, value, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return WorkspaceCoordinationProvisionState.REFUSED_PROTECTION
        return None
    finally:
        kernel.CloseHandle(wintypes.HANDLE(value))


def _create_windows(root: Path) -> WorkspaceCoordinationProvisionResult:
    created = False
    handle_value: int | None = None
    kernel: Any = None
    try:
        owner = inspection._effective_owner("win32")
        kernel, advapi = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, root):
            return _result(WorkspaceCoordinationProvisionState.REFUSED_BACKING)
        failure = _windows_parent(kernel, advapi, root, owner)
        if failure is not None:
            return _result(failure)
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
        handle_value, error = registry_file._create_file_explicit_dacl_windows(
            kernel, advapi, root / _METADATA_DIR / _LOCK_FILE, owner.value
        )
        if handle_value is None:
            if error in (80, 183):
                return _result(WorkspaceCoordinationProvisionState.ALREADY_EXISTS)
            if error in (5, 1314):
                return _result(WorkspaceCoordinationProvisionState.ACCESS_DENIED)
            return _result(WorkspaceCoordinationProvisionState.UNSUPPORTED)
        created = True
        handle = wintypes.HANDLE(handle_value)
        buffer = ctypes.create_string_buffer(_LOCK_PAYLOAD)
        written = wintypes.DWORD()
        if (
            not kernel.WriteFile(handle, buffer, 1, ctypes.byref(written), None)
            or written.value != 1
        ):
            return _result(WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED)
        if not kernel.FlushFileBuffers(handle):
            return _result(WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED)
        info = descriptor._windows_info(kernel, handle_value)
        if (
            info is None
            or info[0] & (0x10 | 0x400)
            or info[1].directory
            or info[1].delete_pending
            or info[1].number_of_links != 1
            or info[1].end_of_file != 1
            or wincheck._handle_dacl_state(kernel, advapi, handle_value, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or _windows_parent(kernel, advapi, root, owner) is not None
            or not wincreate._known_fixed_local_volume(kernel, root)
        ):
            return _result(WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED)
        return _result(WorkspaceCoordinationProvisionState.CREATED_UNQUALIFIED)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        inspection._OwnerUnverifiable,
        wincheck._NativeUnavailable,
        wincreate._NativeUnavailable,
    ):
        return _result(
            WorkspaceCoordinationProvisionState.CREATION_UNVERIFIED
            if created
            else WorkspaceCoordinationProvisionState.UNSUPPORTED
        )
    finally:
        if handle_value is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle_value))


def create_workspace_coordination_file(
    workspace_root: Path,
) -> WorkspaceCoordinationProvisionResult:
    """Explicit one-file create only; existing workspace and .pds are required.

    No descriptor, protected registry, private store, or Notes record changes.
    A successful creation is insufficient to authorize a future binding write.
    """
    if not descriptor._valid_root(workspace_root):
        return _result(
            WorkspaceCoordinationProvisionState.UNSUPPORTED
            if sys.platform not in {"linux", "win32"}
            else WorkspaceCoordinationProvisionState.INVALID_REQUEST
        )
    if sys.platform == "linux":
        return _create_linux(workspace_root)
    if sys.platform == "win32":
        return _create_windows(workspace_root)
    return _result(WorkspaceCoordinationProvisionState.UNSUPPORTED)
