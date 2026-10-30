"""Bounded, read-only native byte image of the protected registry (#238 3E6).

The returned image is internal advisory evidence only, never a binding handle,
CAS reservation, authority to replay a journal, or permission to access Notes.
Effective native owner, local backing, protection, file identity, and existing
ordered private locks are verified; no file is created or modified.
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
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_bootstrap as bootstrap
from pds_core import _teacher_private_retained_registry_guard as retained
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateRegistryImageState(str, Enum):
    OBSERVED_REVIEW_REQUIRED = "observed_review_required"
    MISSING = "missing"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_READ = "changed_during_read"
    INVALID_REGISTRY = "invalid_registry"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED: "Canonical native registry bytes observed; recovery review required.",
    PrivateRegistryImageState.MISSING: "Registry not observed; absence is not a fresh binding.",
    PrivateRegistryImageState.INVALID_REQUEST: "Private registry byte-image request refused.",
    PrivateRegistryImageState.UNSUPPORTED: "Private registry byte-image read unsupported.",
    PrivateRegistryImageState.OWNER_UNAVAILABLE: "Native owner unavailable.",
    PrivateRegistryImageState.OWNER_CHANGED: "Native owner changed during registry observation.",
    PrivateRegistryImageState.GUARD_REFUSED: "Native registry guard refused or changed.",
    PrivateRegistryImageState.REFUSED_PROTECTION: "Registry protection or identity unqualified.",
    PrivateRegistryImageState.REFUSED_BACKING: "Registry backing unqualified.",
    PrivateRegistryImageState.ACCESS_DENIED: "Registry access denied.",
    PrivateRegistryImageState.CHANGED_DURING_READ: "Registry identity or metadata changed during read.",
    PrivateRegistryImageState.INVALID_REGISTRY: "Registry bytes are noncanonical or malformed.",
    PrivateRegistryImageState.IO_ERROR: "Registry byte-image read could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateRegistryImageReview:
    """Private internal byte image is omitted from repr and sanitized errors."""

    state: PrivateRegistryImageState
    message: str
    image: bytes | None = field(default=None, repr=False)


def _result(
    state: PrivateRegistryImageState, image: bytes | None = None
) -> PrivateRegistryImageReview:
    return PrivateRegistryImageReview(state, _MESSAGES[state], image)


def _checked_image(
    raw: bytes, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryImageReview:
    if type(raw) is not bytes or not (0 < len(raw) <= metadata.MAX_REGISTRY_BYTES):
        return _result(PrivateRegistryImageState.INVALID_REGISTRY)
    try:
        parsed = metadata.decode_private_registry(raw)
        if metadata.encode_private_registry(parsed) != raw:
            return _result(PrivateRegistryImageState.INVALID_REGISTRY)
    except metadata.PrivateMetadataError:
        return _result(PrivateRegistryImageState.INVALID_REGISTRY)
    if parsed.owner.kind != owner.kind or parsed.owner.value != owner.value:
        return _result(PrivateRegistryImageState.REFUSED_PROTECTION)
    return _result(PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED, raw)


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


def _read_linux(
    root: Path, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryImageReview:
    getter = getattr(os, "geteuid", None)
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0) or getter is None:
        return _result(PrivateRegistryImageState.UNSUPPORTED)
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        return _result(PrivateRegistryImageState.OWNER_UNAVAILABLE)
    uid = int(owner.value)
    if getter() != uid:
        return _result(PrivateRegistryImageState.OWNER_CHANGED)
    parent_fd: int | None = None
    file_fd: int | None = None
    try:
        parent_fd, failure = posix._open_verified_parent(root, uid)
        if failure is not None:
            if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
                return _result(PrivateRegistryImageState.REFUSED_BACKING)
            if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
                return _result(PrivateRegistryImageState.ACCESS_DENIED)
            return _result(PrivateRegistryImageState.REFUSED_PROTECTION)
        if parent_fd is None:
            return _result(PrivateRegistryImageState.UNSUPPORTED)
        if not bootstrap._qualified_existing_lock_linux(root, uid, parent_fd):
            return _result(PrivateRegistryImageState.REFUSED_PROTECTION)
        try:
            file_fd = os.open(
                "registry.json",
                os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return _result(PrivateRegistryImageState.MISSING)
        except PermissionError:
            return _result(PrivateRegistryImageState.ACCESS_DENIED)
        start = os.fstat(file_fd)
        link = os.stat("registry.json", dir_fd=parent_fd, follow_symlinks=False)
        parent = os.fstat(parent_fd)
        if (
            not stat.S_ISREG(start.st_mode)
            or not stat.S_ISREG(link.st_mode)
            or _linux_signature(start) != _linux_signature(link)
            or start.st_uid != uid
            or stat.S_IMODE(start.st_mode) != 0o600
            or start.st_nlink != 1
            or start.st_dev != parent.st_dev
            or posix._acl_absent(file_fd) is not None
        ):
            return _result(PrivateRegistryImageState.REFUSED_PROTECTION)
        if not posix._is_known_local_filesystem(file_fd):
            return _result(PrivateRegistryImageState.REFUSED_BACKING)
        if not (0 < start.st_size <= metadata.MAX_REGISTRY_BYTES):
            return _result(PrivateRegistryImageState.INVALID_REGISTRY)
        data = bytearray()
        while len(data) <= metadata.MAX_REGISTRY_BYTES:
            part = os.read(
                file_fd, min(65536, metadata.MAX_REGISTRY_BYTES + 1 - len(data))
            )
            if not part:
                break
            data.extend(part)
        after = os.fstat(file_fd)
        final_link = os.stat("registry.json", dir_fd=parent_fd, follow_symlinks=False)
        final_parent = os.fstat(parent_fd)
        if (
            _linux_signature(start) != _linux_signature(after)
            or _linux_signature(start) != _linux_signature(final_link)
            or _linux_signature(parent) != _linux_signature(final_parent)
            or len(data) != start.st_size
            or getter() != uid
            or not bootstrap._qualified_existing_lock_linux(root, uid, parent_fd)
        ):
            return _result(PrivateRegistryImageState.CHANGED_DURING_READ)
        return _checked_image(bytes(data), owner)
    except (FileNotFoundError, NotADirectoryError):
        return _result(PrivateRegistryImageState.CHANGED_DURING_READ)
    except PermissionError:
        return _result(PrivateRegistryImageState.ACCESS_DENIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRegistryImageState.IO_ERROR)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _read_windows(
    root: Path, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryImageReview:
    if owner.kind != "windows_token_sid":
        return _result(PrivateRegistryImageState.OWNER_UNAVAILABLE)
    kernel: Any = None
    first: int | None = None
    second: int | None = None
    try:
        kernel, advapi = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, root):
            return _result(PrivateRegistryImageState.REFUSED_BACKING)
        if (
            wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not bootstrap._qualified_existing_lock_windows(
                kernel, advapi, root, owner
            )
        ):
            return _result(PrivateRegistryImageState.REFUSED_PROTECTION)
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
            str(root / "registry.json"),
            0x80000000 | 0x20000,  # GENERIC_READ | READ_CONTROL
            0x1,  # share read only: refuse concurrent native write/delete
            None,
            3,
            0x00200000,
            None,
        )
        first = ctypes.cast(raw, ctypes.c_void_p).value
        if first is None or first == ctypes.c_void_p(-1).value:
            first = None
            error = ctypes.get_last_error()
            if error in (2, 3):
                return _result(PrivateRegistryImageState.MISSING)
            if error in (5, 32):
                return _result(PrivateRegistryImageState.ACCESS_DENIED)
            return _result(PrivateRegistryImageState.IO_ERROR)
        signature = retained._windows_signature(kernel, first)
        if (
            signature is None
            or not (0 < signature[2] <= metadata.MAX_REGISTRY_BYTES)
            or wincheck._handle_dacl_state(kernel, advapi, first, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateRegistryImageState.REFUSED_PROTECTION)
        content = ctypes.create_string_buffer(signature[2])
        length = 0
        while length < signature[2]:
            got = wintypes.DWORD()
            if (
                not kernel.ReadFile(
                    wintypes.HANDLE(first),
                    ctypes.byref(content, length),
                    signature[2] - length,
                    ctypes.byref(got),
                    None,
                )
                or got.value == 0
            ):
                return _result(PrivateRegistryImageState.IO_ERROR)
            length += got.value
        if retained._windows_signature(kernel, first) != signature:
            return _result(PrivateRegistryImageState.CHANGED_DURING_READ)
        second, error = anchor._windows_open(kernel, root / "registry.json")
        if second is None:
            if error in (2, 3):
                return _result(PrivateRegistryImageState.CHANGED_DURING_READ)
            if error in (5, 32):
                return _result(PrivateRegistryImageState.ACCESS_DENIED)
            return _result(PrivateRegistryImageState.IO_ERROR)
        if (
            retained._windows_signature(kernel, second) != signature
            or wincheck._handle_dacl_state(kernel, advapi, second, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, root)
            or wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not bootstrap._qualified_existing_lock_windows(
                kernel, advapi, root, owner
            )
        ):
            return _result(PrivateRegistryImageState.CHANGED_DURING_READ)
        return _checked_image(content.raw, owner)
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        return _result(PrivateRegistryImageState.UNSUPPORTED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRegistryImageState.IO_ERROR)
    finally:
        if kernel is not None:
            if second is not None:
                kernel.CloseHandle(wintypes.HANDLE(second))
            if first is not None:
                kernel.CloseHandle(wintypes.HANDLE(first))


def _guard_refusal(
    code: retained.RetainedRegistryGuardCode,
) -> PrivateRegistryImageState:
    if code is retained.RetainedRegistryGuardCode.OWNER_CHANGED:
        return PrivateRegistryImageState.OWNER_CHANGED
    if code is retained.RetainedRegistryGuardCode.OWNER_UNAVAILABLE:
        return PrivateRegistryImageState.OWNER_UNAVAILABLE
    if code is retained.RetainedRegistryGuardCode.UNSUPPORTED:
        return PrivateRegistryImageState.UNSUPPORTED
    return PrivateRegistryImageState.GUARD_REFUSED


def inspect_existing_private_registry_image(
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRegistryImageReview:
    """Return bounded exact registry bytes only for a fully guarded observation.

    All three existing native/private coordination layers remain independently
    required before a future recovery composer may use these bytes. This method
    retains the journal directory and registry file but NOT a workspace sidecar.
    The image does not authorize a binding, Notes read, CAS, or recovery write.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRegistryImageState.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateRegistryImageState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_registry_guard(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            observed = (
                _read_linux(existing_private_root, first_owner)
                if sys.platform == "linux"
                else _read_windows(existing_private_root, first_owner)
            )
            if ordered._owner() != first_owner:
                return _result(PrivateRegistryImageState.OWNER_CHANGED)
            return observed
    except retained.RetainedRegistryGuardError as error:
        return _result(_guard_refusal(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateRegistryImageState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateRegistryImageState.OWNER_UNAVAILABLE)
        return _result(PrivateRegistryImageState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRegistryImageState.IO_ERROR)
