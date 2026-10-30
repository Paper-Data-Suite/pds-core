"""Read one canonical workspace association descriptor under native guards (#238 3E7).

The workspace sidecar is untrusted and may be synced. Native file identity and
stable canonical bytes are observational evidence only, not proof of owner,
durability, a CAS reservation, a binding, or permission to write Notes records.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_retained_descriptor_guard as retained


class PrivateDescriptorImageState(str, Enum):
    OBSERVED_REVIEW_REQUIRED = "observed_review_required"
    MISSING = "missing"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_CHANGED = "owner_changed"
    OWNER_UNAVAILABLE = "owner_unavailable"
    GUARD_REFUSED = "guard_refused"
    REFUSED_PATH = "refused_path"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_READ = "changed_during_read"
    INVALID_DESCRIPTOR = "invalid_descriptor"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED: "Canonical native workspace descriptor bytes observed; review required.",
    PrivateDescriptorImageState.MISSING: "Workspace descriptor not observed; absence grants no association.",
    PrivateDescriptorImageState.INVALID_REQUEST: "Workspace descriptor image request refused.",
    PrivateDescriptorImageState.UNSUPPORTED: "Native workspace descriptor image read unsupported.",
    PrivateDescriptorImageState.OWNER_CHANGED: "Effective OS owner changed during descriptor observation.",
    PrivateDescriptorImageState.OWNER_UNAVAILABLE: "Effective OS owner could not be verified.",
    PrivateDescriptorImageState.GUARD_REFUSED: "Native descriptor guard refused or changed.",
    PrivateDescriptorImageState.REFUSED_PATH: "Workspace sidecar path, type or identity is unqualified.",
    PrivateDescriptorImageState.ACCESS_DENIED: "Workspace descriptor read access denied.",
    PrivateDescriptorImageState.CHANGED_DURING_READ: "Workspace descriptor or its parent changed during the read.",
    PrivateDescriptorImageState.INVALID_DESCRIPTOR: "Workspace descriptor is malformed or noncanonical.",
    PrivateDescriptorImageState.IO_ERROR: "Workspace descriptor byte read could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateDescriptorImageReview:
    """Internal exact bytes, never returned in repr or sanitized messages."""

    state: PrivateDescriptorImageState
    message: str
    image: bytes | None = field(default=None, repr=False)


def _result(
    state: PrivateDescriptorImageState, image: bytes | None = None
) -> PrivateDescriptorImageReview:
    return PrivateDescriptorImageReview(state, _MESSAGES[state], image)


def _checked_image(raw: bytes) -> PrivateDescriptorImageReview:
    if type(raw) is not bytes or not (0 < len(raw) <= metadata.MAX_ASSOCIATION_BYTES):
        return _result(PrivateDescriptorImageState.INVALID_DESCRIPTOR)
    try:
        parsed = metadata.decode_association_descriptor(raw)
        if metadata.encode_association_descriptor(parsed) != raw:
            return _result(PrivateDescriptorImageState.INVALID_DESCRIPTOR)
    except metadata.PrivateMetadataError:
        return _result(PrivateDescriptorImageState.INVALID_DESCRIPTOR)
    return _result(PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED, raw)


def _linux_signature(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_linux(workspace_root: Path) -> PrivateDescriptorImageReview:
    """Use no-follow dirfd traversal; the outer guard owns cross-tree locks."""
    if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
        return _result(PrivateDescriptorImageState.UNSUPPORTED)
    parent_fd: int | None = None
    file_fd: int | None = None
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW")
        | getattr(os, "O_DIRECTORY")
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        parent_fd = os.open("/", flags)
        for component in (*workspace_root.parts[1:], ".pds"):
            next_fd = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        parent = os.fstat(parent_fd)
        named_parent = os.lstat(workspace_root / ".pds")
        if not stat.S_ISDIR(parent.st_mode) or _linux_signature(
            parent
        ) != _linux_signature(named_parent):
            return _result(PrivateDescriptorImageState.REFUSED_PATH)
        try:
            file_fd = os.open(
                "teacher-private-association.json",
                os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return _result(PrivateDescriptorImageState.MISSING)
        start = os.fstat(file_fd)
        entry = os.stat(
            "teacher-private-association.json",
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(start.st_mode)
            or _linux_signature(start) != _linux_signature(entry)
            or start.st_nlink != 1
        ):
            return _result(PrivateDescriptorImageState.REFUSED_PATH)
        if not (0 < start.st_size <= metadata.MAX_ASSOCIATION_BYTES):
            return _result(PrivateDescriptorImageState.INVALID_DESCRIPTOR)
        content = bytearray()
        while len(content) <= metadata.MAX_ASSOCIATION_BYTES:
            chunk = os.read(
                file_fd,
                min(4096, metadata.MAX_ASSOCIATION_BYTES + 1 - len(content)),
            )
            if not chunk:
                break
            content.extend(chunk)
        later = os.fstat(file_fd)
        later_entry = os.stat(
            "teacher-private-association.json",
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        later_parent = os.fstat(parent_fd)
        later_named_parent = os.lstat(workspace_root / ".pds")
        if (
            len(content) != start.st_size
            or _linux_signature(start) != _linux_signature(later)
            or _linux_signature(start) != _linux_signature(later_entry)
            or _linux_signature(parent) != _linux_signature(later_parent)
            or _linux_signature(parent) != _linux_signature(later_named_parent)
        ):
            return _result(PrivateDescriptorImageState.CHANGED_DURING_READ)
        return _checked_image(bytes(content))
    except FileNotFoundError:
        return _result(PrivateDescriptorImageState.MISSING)
    except PermissionError:
        return _result(PrivateDescriptorImageState.ACCESS_DENIED)
    except (NotADirectoryError, IsADirectoryError):
        return _result(PrivateDescriptorImageState.REFUSED_PATH)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateDescriptorImageState.IO_ERROR)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _read_windows(workspace_root: Path) -> PrivateDescriptorImageReview:
    """Read stable FileIdInfo-backed sidecar through non-following Win32 handles."""
    kernel: Any = None
    first: int | None = None
    second: int | None = None
    path = workspace_root / ".pds" / "teacher-private-association.json"
    try:
        kernel = descriptor._windows_api()
        if descriptor._windows_ancestry(kernel, workspace_root) is not None:
            return _result(PrivateDescriptorImageState.REFUSED_PATH)
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
        kernel.ReadFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel.ReadFile.restype = wintypes.BOOL
        raw = kernel.CreateFileW(
            str(path),
            0x80000000,  # GENERIC_READ; no write or deletion access
            0x1,  # Share read only for this short native observation
            None,
            3,
            0x00200000,  # OPEN_EXISTING; FILE_FLAG_OPEN_REPARSE_POINT
            None,
        )
        first = ctypes.cast(raw, ctypes.c_void_p).value
        if first is None or first == ctypes.c_void_p(-1).value:
            first = None
            error = ctypes.get_last_error()
            if error in (2, 3):
                return _result(PrivateDescriptorImageState.MISSING)
            if error in (5, 32):
                return _result(PrivateDescriptorImageState.ACCESS_DENIED)
            return _result(PrivateDescriptorImageState.IO_ERROR)
        signature = retained._windows_signature(kernel, first, directory=False)
        if signature is None or not (
            0 < signature[2] <= metadata.MAX_ASSOCIATION_BYTES
        ):
            return _result(PrivateDescriptorImageState.REFUSED_PATH)
        content = ctypes.create_string_buffer(signature[2])
        size = 0
        while size < signature[2]:
            count = wintypes.DWORD()
            if (
                not kernel.ReadFile(
                    wintypes.HANDLE(first),
                    ctypes.byref(content, size),
                    signature[2] - size,
                    ctypes.byref(count),
                    None,
                )
                or count.value == 0
            ):
                return _result(PrivateDescriptorImageState.IO_ERROR)
            size += count.value
        if retained._windows_signature(kernel, first, directory=False) != signature:
            return _result(PrivateDescriptorImageState.CHANGED_DURING_READ)
        second, error = descriptor._windows_open(kernel, str(path), directory=False)
        if second is None:
            if error in (2, 3):
                return _result(PrivateDescriptorImageState.CHANGED_DURING_READ)
            if error in (5, 32):
                return _result(PrivateDescriptorImageState.ACCESS_DENIED)
            return _result(PrivateDescriptorImageState.IO_ERROR)
        if (
            retained._windows_signature(kernel, second, directory=False) != signature
            or descriptor._windows_ancestry(kernel, workspace_root) is not None
        ):
            return _result(PrivateDescriptorImageState.CHANGED_DURING_READ)
        return _checked_image(content.raw)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateDescriptorImageState.IO_ERROR)
    finally:
        if kernel is not None:
            if second is not None:
                kernel.CloseHandle(wintypes.HANDLE(second))
            if first is not None:
                kernel.CloseHandle(wintypes.HANDLE(first))


def _guard_failure(
    code: retained.RetainedDescriptorGuardCode,
) -> PrivateDescriptorImageState:
    if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
        return PrivateDescriptorImageState.OWNER_CHANGED
    if code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE:
        return PrivateDescriptorImageState.OWNER_UNAVAILABLE
    if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
        return PrivateDescriptorImageState.UNSUPPORTED
    return PrivateDescriptorImageState.GUARD_REFUSED


def inspect_existing_workspace_descriptor_image(
    existing_private_root: Path, existing_workspace_root: Path
) -> PrivateDescriptorImageReview:
    """Read a canonical sidecar under all existing native retained guards.

    A protected registry and journal directory remain retained within the
    descriptor guard. This does not establish cross-device/sync coordination,
    durability, association ownership, CAS or permission to mutate metadata.
    Never call this entry point from another retained lock context.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateDescriptorImageState.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateDescriptorImageState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            observation = (
                _read_linux(existing_workspace_root)
                if sys.platform == "linux"
                else _read_windows(existing_workspace_root)
            )
            if ordered._owner() != first_owner:
                return _result(PrivateDescriptorImageState.OWNER_CHANGED)
            return observation
    except retained.RetainedDescriptorGuardError as error:
        return _result(_guard_failure(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateDescriptorImageState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateDescriptorImageState.OWNER_UNAVAILABLE)
        return _result(PrivateDescriptorImageState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateDescriptorImageState.IO_ERROR)
