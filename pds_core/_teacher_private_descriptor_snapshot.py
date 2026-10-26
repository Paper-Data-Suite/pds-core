"""Read-only, non-authorizing workspace association sidecar observation (#238).

The sidecar can live in a synced workspace and is NOT ownership evidence.
No registry lock is acquired here and no path, file, or directory is created.
No outcome permits binding, Notes access, or a cross-tree metadata commit.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Any

from pds_core import _teacher_private_metadata as metadata

_SIDECAR = "teacher-private-association.json"
_METADATA_DIR = ".pds"


class PrivateDescriptorSnapshotState(str, Enum):
    OBSERVED_UNQUALIFIED = "observed_unqualified"
    MISSING_METADATA_DIRECTORY = "missing_metadata_directory"
    MISSING_DESCRIPTOR = "missing_descriptor"
    CORRUPT_METADATA = "corrupt_metadata"
    INVALID_REQUEST = "invalid_request"
    REFUSED_PATH = "refused_path"
    ACCESS_DENIED = "access_denied"
    IO_ERROR = "io_error"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED: "Workspace descriptor observed; local owner binding remains unqualified.",
    PrivateDescriptorSnapshotState.MISSING_METADATA_DIRECTORY: "Workspace metadata directory absent; private registry continuity is unknown.",
    PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR: "Workspace descriptor absent; private registry continuity is unknown.",
    PrivateDescriptorSnapshotState.CORRUPT_METADATA: "Workspace descriptor is malformed or unsupported; its bytes were preserved.",
    PrivateDescriptorSnapshotState.INVALID_REQUEST: "Workspace descriptor inspection request invalid.",
    PrivateDescriptorSnapshotState.REFUSED_PATH: "Workspace descriptor path is unsafe or unqualified.",
    PrivateDescriptorSnapshotState.ACCESS_DENIED: "Workspace descriptor cannot be read with current permissions.",
    PrivateDescriptorSnapshotState.IO_ERROR: "Workspace descriptor observation could not be completed reliably.",
    PrivateDescriptorSnapshotState.UNSUPPORTED: "Workspace descriptor inspection unsupported here.",
}


@dataclass(frozen=True, slots=True)
class PrivateDescriptorSnapshot:
    """Nonsecret observed UUID and digest. Neither is an access credential."""

    state: PrivateDescriptorSnapshotState
    message: str
    association_id: str | None = field(default=None, repr=False)
    sha256: str | None = field(default=None, repr=False)


def _outcome(
    state: PrivateDescriptorSnapshotState, raw: bytes | None = None
) -> PrivateDescriptorSnapshot:
    if state is PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED:
        if raw is None:
            raise ValueError("Missing descriptor observation")
        try:
            parsed = metadata.decode_association_descriptor(raw)
            if metadata.encode_association_descriptor(parsed) != raw:
                return _outcome(PrivateDescriptorSnapshotState.CORRUPT_METADATA)
        except metadata.PrivateMetadataError:
            return _outcome(PrivateDescriptorSnapshotState.CORRUPT_METADATA)
        return PrivateDescriptorSnapshot(
            state,
            _MESSAGES[state],
            parsed.association_id,
            hashlib.sha256(raw).hexdigest(),
        )
    return PrivateDescriptorSnapshot(state, _MESSAGES[state])


def _valid_root(root: object) -> bool:
    if not isinstance(root, Path) or not root.is_absolute():
        return False
    raw = str(root)
    if "\x00" in raw or len(raw) > 4096:
        return False
    if sys.platform == "win32":
        # Reject UNC/device namespaces, ADS and any explicit dot/traversal.
        if raw.startswith(("\\\\", "//")):
            return False
        candidate = PureWindowsPath(raw)
        if not (
            candidate.is_absolute()
            and len(candidate.drive) == 2
            and candidate.drive[1] == ":"
            and candidate.root == "\\"
            and len(candidate.parts) >= 3
        ):
            return False
        components = raw.replace("/", "\\").split("\\")
        return not any(
            name in ("", ".", "..") or ":" in name for name in components[1:]
        )
    if sys.platform == "linux":
        return (
            raw.startswith("/")
            and not raw.startswith("//")
            and len(root.parts) >= 3
            and not any(name in ("", ".", "..") for name in raw.split("/")[1:])
        )
    return False


def _read_linux(root: Path) -> PrivateDescriptorSnapshot:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        return _outcome(PrivateDescriptorSnapshotState.UNSUPPORTED)
    current: int | None = None
    opened: int | None = None
    try:
        current = os.open("/", flags)
        for name in (*root.parts[1:], _METADATA_DIR):
            try:
                new = os.open(name, flags, dir_fd=current)
            except FileNotFoundError:
                return _outcome(
                    PrivateDescriptorSnapshotState.MISSING_METADATA_DIRECTORY
                )
            os.close(current)
            current = new
            if not stat.S_ISDIR(os.fstat(current).st_mode):
                return _outcome(PrivateDescriptorSnapshotState.REFUSED_PATH)
        try:
            opened = os.open(
                _SIDECAR,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
                dir_fd=current,
            )
        except FileNotFoundError:
            return _outcome(PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR)
        info = os.fstat(opened)
        link = os.stat(_SIDECAR, dir_fd=current, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (link.st_dev, link.st_ino)
        ):
            return _outcome(PrivateDescriptorSnapshotState.REFUSED_PATH)
        if not (1 <= info.st_size <= metadata.MAX_ASSOCIATION_BYTES):
            return _outcome(PrivateDescriptorSnapshotState.CORRUPT_METADATA)
        raw = bytearray()
        while len(raw) <= metadata.MAX_ASSOCIATION_BYTES:
            part = os.read(opened, metadata.MAX_ASSOCIATION_BYTES + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        final = os.fstat(opened)
        final_link = os.stat(_SIDECAR, dir_fd=current, follow_symlinks=False)
        if (
            len(raw) != info.st_size
            or (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            != (final.st_size, final.st_mtime_ns, final.st_ctime_ns)
            or (info.st_dev, info.st_ino) != (final_link.st_dev, final_link.st_ino)
        ):
            return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
        if len(raw) > metadata.MAX_ASSOCIATION_BYTES:
            return _outcome(PrivateDescriptorSnapshotState.CORRUPT_METADATA)
        return _outcome(PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED, bytes(raw))
    except PermissionError:
        return _outcome(PrivateDescriptorSnapshotState.ACCESS_DENIED)
    except (NotADirectoryError, IsADirectoryError):
        return _outcome(PrivateDescriptorSnapshotState.REFUSED_PATH)
    except OSError as exc:
        return _outcome(
            PrivateDescriptorSnapshotState.REFUSED_PATH
            if exc.errno in (errno.ELOOP, errno.ENOTDIR)
            else PrivateDescriptorSnapshotState.IO_ERROR
        )
    except (AttributeError, ValueError, OverflowError):
        return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
    finally:
        if opened is not None:
            os.close(opened)
        if current is not None:
            os.close(current)


class _AttributeTagInfo(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]


class _FileStandardInfo(ctypes.Structure):
    _fields_ = [
        ("allocation_size", ctypes.c_int64),
        ("end_of_file", ctypes.c_int64),
        ("number_of_links", wintypes.DWORD),
        ("delete_pending", ctypes.c_ubyte),
        ("directory", ctypes.c_ubyte),
    ]


def _windows_api() -> Any:
    loader = getattr(ctypes, "WinDLL", None)
    if sys.platform != "win32" or loader is None:
        raise OSError("Unsupported native platform")
    kernel = loader("kernel32", use_last_error=True)
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
    kernel.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _windows_open(kernel: Any, path: str, *, directory: bool) -> tuple[int | None, int]:
    # Observational handles only; FILE_SHARE_READ/WRITE/DELETE permits cloud
    # collaboration but no cross-machine consistency or currentness proof.
    raw = kernel.CreateFileW(
        path,
        0x80 | 0x1,
        7,
        None,
        3,
        0x00200000 | (0x02000000 if directory else 0),
        None,
    )
    value = ctypes.cast(raw, ctypes.c_void_p).value
    if value is None or value == ctypes.c_void_p(-1).value:
        return None, ctypes.get_last_error()
    return value, 0


def _windows_info(kernel: Any, value: int) -> tuple[int, _FileStandardInfo] | None:
    h = wintypes.HANDLE(value)
    attrs = _AttributeTagInfo()
    standard = _FileStandardInfo()
    if not kernel.GetFileInformationByHandleEx(
        h, 9, ctypes.byref(attrs), ctypes.sizeof(attrs)
    ) or not kernel.GetFileInformationByHandleEx(
        h, 1, ctypes.byref(standard), ctypes.sizeof(standard)
    ):
        return None
    return int(attrs.attributes), standard


def _windows_ancestry(kernel: Any, root: Path) -> PrivateDescriptorSnapshotState | None:
    # Refuse any current reparse component (including an online-only cloud
    # placeholder). No ACL-owner claim is derived from a synced workspace.
    path = PureWindowsPath(root)
    current = str(PureWindowsPath(path.parts[0]))
    for name in (*path.parts[1:], _METADATA_DIR):
        current = str(PureWindowsPath(current) / name)
        handle, error = _windows_open(kernel, current, directory=True)
        if handle is None:
            if error in (2, 3):
                return PrivateDescriptorSnapshotState.MISSING_METADATA_DIRECTORY
            if error in (5, 32):
                return PrivateDescriptorSnapshotState.ACCESS_DENIED
            return PrivateDescriptorSnapshotState.IO_ERROR
        try:
            info = _windows_info(kernel, handle)
            if info is None:
                return PrivateDescriptorSnapshotState.IO_ERROR
            attrs, standard = info
            if attrs & 0x400 or not (attrs & 0x10) or not standard.directory:
                return PrivateDescriptorSnapshotState.REFUSED_PATH
        finally:
            kernel.CloseHandle(wintypes.HANDLE(handle))
    return None


def _read_windows(root: Path) -> PrivateDescriptorSnapshot:
    handle: int | None = None
    kernel: Any = None
    try:
        kernel = _windows_api()
        failure = _windows_ancestry(kernel, root)
        if failure is not None:
            return _outcome(failure)
        handle, error = _windows_open(
            kernel, str(root / _METADATA_DIR / _SIDECAR), directory=False
        )
        if handle is None:
            if error in (2, 3):
                return _outcome(PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR)
            if error in (5, 32):
                return _outcome(PrivateDescriptorSnapshotState.ACCESS_DENIED)
            return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
        info = _windows_info(kernel, handle)
        if info is None:
            return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
        attrs, standard = info
        if (
            attrs & (0x10 | 0x400)
            or standard.directory
            or standard.delete_pending
            or standard.number_of_links != 1
        ):
            return _outcome(PrivateDescriptorSnapshotState.REFUSED_PATH)
        if not (1 <= standard.end_of_file <= metadata.MAX_ASSOCIATION_BYTES):
            return _outcome(PrivateDescriptorSnapshotState.CORRUPT_METADATA)
        buffer = ctypes.create_string_buffer(int(standard.end_of_file))
        offset = 0
        while offset < standard.end_of_file:
            got = wintypes.DWORD()
            if (
                not kernel.ReadFile(
                    wintypes.HANDLE(handle),
                    ctypes.byref(buffer, offset),
                    int(standard.end_of_file - offset),
                    ctypes.byref(got),
                    None,
                )
                or got.value == 0
            ):
                return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
            offset += got.value
        after = _windows_info(kernel, handle)
        if (
            after is None
            or after[1].end_of_file != standard.end_of_file
            or after[1].number_of_links != 1
        ):
            return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
        if _windows_ancestry(kernel, root) is not None:
            return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
        return _outcome(PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED, buffer.raw)
    except (OSError, ValueError, OverflowError, TypeError, AttributeError):
        return _outcome(PrivateDescriptorSnapshotState.IO_ERROR)
    finally:
        if handle is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle))


def inspect_workspace_descriptor(workspace_root: Path) -> PrivateDescriptorSnapshot:
    """Observe an existing sidecar only. Unbound/move/copy outcomes are elsewhere.

    This deliberately does not acquire the protected registry lock or create a
    workspace lock; observation is not a cross-tree consistent read.
    """
    if not _valid_root(workspace_root):
        return _outcome(
            PrivateDescriptorSnapshotState.UNSUPPORTED
            if sys.platform not in {"linux", "win32"}
            else PrivateDescriptorSnapshotState.INVALID_REQUEST
        )
    if sys.platform == "linux":
        return _read_linux(workspace_root)
    if sys.platform == "win32":
        return _read_windows(workspace_root)
    return _outcome(PrivateDescriptorSnapshotState.UNSUPPORTED)
