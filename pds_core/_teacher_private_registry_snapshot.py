"""Strict, locked, read-only private registry snapshot for Core #238 Slice 3C2.

A snapshot is a non-authorizing observation, not an owner binding, READY proof,
revision reservation, privileged handle or permission to mutate metadata.
Never creates, truncates, repairs, or returns private registry bytes/paths.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_bootstrap as bootstrap
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState

_REGISTRY = "registry.json"


class PrivateRegistrySnapshotState(str, Enum):
    OBSERVED_UNQUALIFIED = "observed_unqualified"
    MISSING = "missing"
    CORRUPT_METADATA = "corrupt_metadata"
    OWNER_MISMATCH = "owner_mismatch"
    INVALID_REQUEST = "invalid_request"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"
    IO_ERROR = "io_error"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED: "Owner registry observed; binding and storage remain unqualified.",
    PrivateRegistrySnapshotState.MISSING: "No registry file was observed; absence is not proof of no private records.",
    PrivateRegistrySnapshotState.CORRUPT_METADATA: "Registry metadata is invalid or ambiguous; existing bytes were preserved.",
    PrivateRegistrySnapshotState.OWNER_MISMATCH: "Registry owner differs from the effective OS owner.",
    PrivateRegistrySnapshotState.INVALID_REQUEST: "Private registry inspection request invalid.",
    PrivateRegistrySnapshotState.REFUSED_PROTECTION: "Native registry protection or file identity was not established.",
    PrivateRegistrySnapshotState.REFUSED_BACKING: "Private registry backing is unqualified.",
    PrivateRegistrySnapshotState.ACCESS_DENIED: "Private registry inspection access denied.",
    PrivateRegistrySnapshotState.COORDINATION_UNAVAILABLE: "Private registry coordination lock unavailable.",
    PrivateRegistrySnapshotState.IO_ERROR: "Registry inspection could not complete reliably.",
    PrivateRegistrySnapshotState.UNSUPPORTED: "Registry inspection unsupported on this platform.",
}


@dataclass(frozen=True, slots=True)
class PrivateRegistrySnapshot:
    """Read-only bounded evidence; revision and SHA-256 are NOT commit tokens."""

    state: PrivateRegistrySnapshotState
    message: str
    revision: int | None = None
    binding_count: int | None = None
    sha256: str | None = field(default=None, repr=False)


def _outcome(
    state: PrivateRegistrySnapshotState,
    *,
    raw: bytes | None = None,
    registry: metadata.PrivateRegistry | None = None,
) -> PrivateRegistrySnapshot:
    if state is PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED:
        if raw is None or registry is None:
            raise ValueError("Missing validated registry observation")
        return PrivateRegistrySnapshot(
            state,
            _MESSAGES[state],
            registry.revision,
            len(registry.bindings),
            hashlib.sha256(raw).hexdigest(),
        )
    return PrivateRegistrySnapshot(state, _MESSAGES[state])


def _interpret(raw: bytes, kind: str, owner: str) -> PrivateRegistrySnapshot:
    try:
        parsed = metadata.decode_private_registry(raw)
        if metadata.encode_private_registry(parsed) != raw:
            return _outcome(PrivateRegistrySnapshotState.CORRUPT_METADATA)
    except metadata.PrivateMetadataError:
        return _outcome(PrivateRegistrySnapshotState.CORRUPT_METADATA)
    if parsed.owner.kind != kind or parsed.owner.value != owner:
        return _outcome(PrivateRegistrySnapshotState.OWNER_MISMATCH)
    return _outcome(
        PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED, raw=raw, registry=parsed
    )


def _linux_read(root: Path) -> PrivateRegistrySnapshot:
    getter = getattr(os, "geteuid", None)
    if getter is None or not getattr(os, "O_NOFOLLOW", 0):
        return _outcome(PrivateRegistrySnapshotState.UNSUPPORTED)
    uid = getter()
    if type(uid) is not int or uid <= 0:
        return _outcome(PrivateRegistrySnapshotState.UNSUPPORTED)
    directory_fd, failure = posix._open_verified_parent(root, uid)
    if failure is not None:
        if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
            return _outcome(PrivateRegistrySnapshotState.REFUSED_BACKING)
        if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
            return _outcome(PrivateRegistrySnapshotState.ACCESS_DENIED)
        return _outcome(PrivateRegistrySnapshotState.REFUSED_PROTECTION)
    if directory_fd is None:
        return _outcome(PrivateRegistrySnapshotState.UNSUPPORTED)
    opened: int | None = None
    try:
        if not bootstrap._qualified_existing_lock_linux(root, uid, directory_fd):
            return _outcome(PrivateRegistrySnapshotState.REFUSED_PROTECTION)
        try:
            opened = os.open(
                _REGISTRY,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return _outcome(PrivateRegistrySnapshotState.MISSING)
        except PermissionError:
            return _outcome(PrivateRegistrySnapshotState.ACCESS_DENIED)
        info = os.fstat(opened)
        parent = os.fstat(directory_fd)
        linked = os.stat(_REGISTRY, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
            or info.st_dev != parent.st_dev
            or posix._acl_absent(opened) is not None
            or not posix._is_known_local_filesystem(opened)
        ):
            return _outcome(PrivateRegistrySnapshotState.REFUSED_PROTECTION)
        if info.st_size < 1 or info.st_size > metadata.MAX_REGISTRY_BYTES:
            return _outcome(PrivateRegistrySnapshotState.CORRUPT_METADATA)
        chunks = bytearray()
        while len(chunks) <= metadata.MAX_REGISTRY_BYTES:
            part = os.read(
                opened, min(65536, metadata.MAX_REGISTRY_BYTES + 1 - len(chunks))
            )
            if not part:
                break
            chunks.extend(part)
        current = os.fstat(opened)
        after = os.stat(_REGISTRY, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(chunks) > metadata.MAX_REGISTRY_BYTES
            or len(chunks) != info.st_size
            or (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino)
            or (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            != (current.st_size, current.st_mtime_ns, current.st_ctime_ns)
            or not bootstrap._qualified_existing_lock_linux(root, uid, directory_fd)
        ):
            return _outcome(PrivateRegistrySnapshotState.IO_ERROR)
        return _interpret(bytes(chunks), "posix_euid", str(uid))
    except PermissionError:
        return _outcome(PrivateRegistrySnapshotState.ACCESS_DENIED)
    except (OSError, AttributeError, ValueError, OverflowError):
        return _outcome(PrivateRegistrySnapshotState.IO_ERROR)
    finally:
        if opened is not None:
            os.close(opened)
        os.close(directory_fd)


def _windows_read(root: Path) -> PrivateRegistrySnapshot:
    handle_value: int | None = None
    kernel: Any = None
    try:
        owner = inspection._effective_owner("win32")
        if owner.kind != "windows_token_sid":
            return _outcome(PrivateRegistrySnapshotState.UNSUPPORTED)
        kernel, advapi = wincreate._windows_api()
        if not wincreate._known_fixed_local_volume(kernel, root):
            return _outcome(PrivateRegistrySnapshotState.REFUSED_BACKING)
        if (
            wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not bootstrap._qualified_existing_lock_windows(
                kernel, advapi, root, owner
            )
        ):
            return _outcome(PrivateRegistrySnapshotState.REFUSED_PROTECTION)
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
        raw_handle = kernel.CreateFileW(
            str(root / _REGISTRY),
            0x1 | 0x80 | 0x20000,
            0,
            None,
            3,
            0x00200000,
            None,
        )
        handle_value = ctypes.cast(raw_handle, ctypes.c_void_p).value
        if handle_value is None or handle_value == ctypes.c_void_p(-1).value:
            error = ctypes.get_last_error()
            handle_value = None
            if error in (2, 3):
                return _outcome(PrivateRegistrySnapshotState.MISSING)
            if error in (5, 32):
                return _outcome(PrivateRegistrySnapshotState.ACCESS_DENIED)
            return _outcome(PrivateRegistrySnapshotState.IO_ERROR)
        handle = wintypes.HANDLE(handle_value)
        attrs = lock_provision._FileAttributeTagInfo()
        standard = bootstrap._FileStandardInfo()
        if (
            not kernel.GetFileInformationByHandleEx(
                handle, 9, ctypes.byref(attrs), ctypes.sizeof(attrs)
            )
            or attrs.attributes & (0x10 | 0x400)
            or not kernel.GetFileInformationByHandleEx(
                handle, 1, ctypes.byref(standard), ctypes.sizeof(standard)
            )
            or standard.directory
            or standard.delete_pending
            or standard.number_of_links != 1
            or wincheck._handle_dacl_state(kernel, advapi, handle_value, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _outcome(PrivateRegistrySnapshotState.REFUSED_PROTECTION)
        if (
            standard.end_of_file < 1
            or standard.end_of_file > metadata.MAX_REGISTRY_BYTES
        ):
            return _outcome(PrivateRegistrySnapshotState.CORRUPT_METADATA)
        buffer = ctypes.create_string_buffer(int(standard.end_of_file))
        offset = 0
        while offset < standard.end_of_file:
            got = wintypes.DWORD()
            if (
                not kernel.ReadFile(
                    handle,
                    ctypes.byref(buffer, offset),
                    int(standard.end_of_file - offset),
                    ctypes.byref(got),
                    None,
                )
                or got.value == 0
            ):
                return _outcome(PrivateRegistrySnapshotState.IO_ERROR)
            offset += got.value
        later = bootstrap._FileStandardInfo()
        if (
            not kernel.GetFileInformationByHandleEx(
                handle, 1, ctypes.byref(later), ctypes.sizeof(later)
            )
            or later.end_of_file != standard.end_of_file
            or later.number_of_links != 1
            or not wincreate._known_fixed_local_volume(kernel, root)
            or wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not bootstrap._qualified_existing_lock_windows(
                kernel, advapi, root, owner
            )
        ):
            return _outcome(PrivateRegistrySnapshotState.IO_ERROR)
        return _interpret(buffer.raw, "windows_token_sid", owner.value)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        inspection._OwnerUnverifiable,
        wincreate._NativeUnavailable,
        wincheck._NativeUnavailable,
    ):
        return _outcome(PrivateRegistrySnapshotState.IO_ERROR)
    finally:
        if handle_value is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle_value))


def inspect_existing_private_registry(
    existing_private_root: Path,
) -> PrivateRegistrySnapshot:
    """Observe registry under coordination; no file creation or binding access.

    Returned revision/digest only describe this observation, never authorize a
    later commit. Caller must reacquire guards and re-verify all bytes/owner.
    """
    if not isinstance(existing_private_root, Path) or sys.platform not in {
        "win32",
        "linux",
    }:
        return _outcome(
            PrivateRegistrySnapshotState.INVALID_REQUEST
            if sys.platform in {"win32", "linux"}
            else PrivateRegistrySnapshotState.UNSUPPORTED
        )
    if not lock_provision._requested_root(existing_private_root, sys.platform):
        return _outcome(PrivateRegistrySnapshotState.INVALID_REQUEST)
    try:
        with locking.hold_existing_private_lock(
            existing_private_root / ".registry.lock"
        ):
            if sys.platform == "linux":
                return _linux_read(existing_private_root)
            return _windows_read(existing_private_root)
    except locking.PrivateExistingFileLockError:
        return _outcome(PrivateRegistrySnapshotState.COORDINATION_UNAVAILABLE)
