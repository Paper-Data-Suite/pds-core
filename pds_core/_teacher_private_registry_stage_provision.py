"""Create-only owner-private registry after-image staging (#238 Slice 3F2).

This narrow internal primitive creates an unqualified staging artifact beside
registry.json. It never opens registry.json for writing, renames a staging file,
applies a binding, supplies a write capability, or resolves a pending journal.
The caller must separately retain the appropriate locks, verify the exact
journal and before-images, and implement a recovery protocol. This helper does
not claim to perform any of those prerequisites.
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
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateRegistryStageState(str, Enum):
    STAGED_UNQUALIFIED = "staged_unqualified"
    ALREADY_EXISTS = "already_exists"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    REFUSED_OWNER = "refused_owner"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CREATION_UNVERIFIED = "creation_unverified"


_MESSAGES = {
    PrivateRegistryStageState.STAGED_UNQUALIFIED: "Registry after-image staged; journal admission, target CAS and binding remain unqualified.",
    PrivateRegistryStageState.ALREADY_EXISTS: "Transaction-specific stage exists and was preserved without changes.",
    PrivateRegistryStageState.INVALID_REQUEST: "Registry after-image staging request refused before mutation.",
    PrivateRegistryStageState.UNSUPPORTED: "Registry staging is unsupported under this native account/filesystem.",
    PrivateRegistryStageState.REFUSED_OWNER: "Registry stage native OS owner did not match.",
    PrivateRegistryStageState.REFUSED_PROTECTION: "Registry stage parent protection is unqualified.",
    PrivateRegistryStageState.REFUSED_BACKING: "Registry stage backing is unqualified.",
    PrivateRegistryStageState.ACCESS_DENIED: "Registry stage creation access denied.",
    PrivateRegistryStageState.CREATION_UNVERIFIED: "Stage may exist after interrupted creation; preserve it for recovery review.",
}


@dataclass(frozen=True, slots=True)
class PrivateRegistryStageReview:
    state: PrivateRegistryStageState
    message: str


def _result(state: PrivateRegistryStageState) -> PrivateRegistryStageReview:
    return PrivateRegistryStageReview(state, _MESSAGES[state])


def _linux_create(
    root: Path, name: str, raw: bytes, owner: str
) -> PrivateRegistryStageReview:
    getter = getattr(os, "geteuid", None)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if getter is None or not nofollow:
        return _result(PrivateRegistryStageState.UNSUPPORTED)
    uid = getter()
    if type(uid) is not int or uid <= 0 or owner != str(uid):
        return _result(PrivateRegistryStageState.REFUSED_OWNER)
    parent_fd: int | None = None
    stage_fd: int | None = None
    created = False
    try:
        parent_fd, failure = posix._open_verified_parent(root, uid)
        if failure is not None:
            if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
                return _result(PrivateRegistryStageState.REFUSED_BACKING)
            if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
                return _result(PrivateRegistryStageState.ACCESS_DENIED)
            return _result(PrivateRegistryStageState.REFUSED_PROTECTION)
        if parent_fd is None:
            return _result(PrivateRegistryStageState.UNSUPPORTED)
        try:
            stage_fd = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | nofollow
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=parent_fd,
            )
            created = True
        except FileExistsError:
            return _result(PrivateRegistryStageState.ALREADY_EXISTS)
        except PermissionError:
            return _result(PrivateRegistryStageState.ACCESS_DENIED)
        written = 0
        while written < len(raw):
            count = os.write(stage_fd, raw[written:])
            if count <= 0:
                return _result(PrivateRegistryStageState.CREATION_UNVERIFIED)
            written += count
        os.fsync(stage_fd)
        opened = os.fstat(stage_fd)
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        parent = os.fstat(parent_fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(linked.st_mode)
            or opened.st_uid != uid
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size != len(raw)
            or (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino)
            or opened.st_dev != parent.st_dev
            or posix._acl_absent(stage_fd) is not None
            or not posix._is_known_local_filesystem(stage_fd)
        ):
            return _result(PrivateRegistryStageState.CREATION_UNVERIFIED)
        os.fsync(parent_fd)
        after = os.fstat(stage_fd)
        final_link = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        final_parent = os.fstat(parent_fd)
        if (
            (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            or (linked.st_dev, linked.st_ino) != (final_link.st_dev, final_link.st_ino)
            or (parent.st_dev, parent.st_ino)
            != (final_parent.st_dev, final_parent.st_ino)
            or getter() != uid
        ):
            return _result(PrivateRegistryStageState.CREATION_UNVERIFIED)
        return _result(PrivateRegistryStageState.STAGED_UNQUALIFIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(
            PrivateRegistryStageState.CREATION_UNVERIFIED
            if created
            else PrivateRegistryStageState.UNSUPPORTED
        )
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _windows_create(
    root: Path, name: str, raw: bytes, owner: str
) -> PrivateRegistryStageReview:
    kernel: Any = None
    handle_value: int | None = None
    created = False
    try:
        current = inspection._effective_owner("win32")
        if current.kind != "windows_token_sid" or current.value != owner:
            return _result(PrivateRegistryStageState.REFUSED_OWNER)
        kernel, advapi = wincreate._windows_api()
        if not wincreate._known_fixed_local_volume(kernel, root):
            return _result(PrivateRegistryStageState.REFUSED_BACKING)
        if (
            wincheck._native_windows_walk(root, current)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateRegistryStageState.REFUSED_PROTECTION)
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
        handle_value, error = lock_file._create_file_explicit_dacl_windows(
            kernel, advapi, root / name, current.value, write_through=True
        )
        if handle_value is None:
            if error in (80, 183):
                return _result(PrivateRegistryStageState.ALREADY_EXISTS)
            if error in (5, 1314):
                return _result(PrivateRegistryStageState.ACCESS_DENIED)
            return _result(PrivateRegistryStageState.UNSUPPORTED)
        created = True
        output = ctypes.create_string_buffer(raw)
        written = wintypes.DWORD()
        if not kernel.WriteFile(
            wintypes.HANDLE(handle_value), output, len(raw), ctypes.byref(written), None
        ) or written.value != len(raw):
            return _result(PrivateRegistryStageState.CREATION_UNVERIFIED)
        if not kernel.FlushFileBuffers(wintypes.HANDLE(handle_value)):
            return _result(PrivateRegistryStageState.CREATION_UNVERIFIED)
        info = descriptor._windows_info(kernel, handle_value)
        if (
            info is None
            or info[0] & (0x10 | 0x400)
            or info[1].directory
            or info[1].delete_pending
            or info[1].number_of_links != 1
            or int(info[1].end_of_file) != len(raw)
            or wincheck._handle_dacl_state(kernel, advapi, handle_value, current)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, root)
            or wincheck._native_windows_walk(root, current)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateRegistryStageState.CREATION_UNVERIFIED)
        return _result(PrivateRegistryStageState.STAGED_UNQUALIFIED)
    except (
        OSError,
        AttributeError,
        ValueError,
        TypeError,
        OverflowError,
        inspection._OwnerUnverifiable,
        wincreate._NativeUnavailable,
    ):
        return _result(
            PrivateRegistryStageState.CREATION_UNVERIFIED
            if created
            else PrivateRegistryStageState.UNSUPPORTED
        )
    finally:
        if handle_value is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle_value))


def create_private_registry_after_image_stage(
    proposed: intents.PrivateTransactionIntent, existing_private_root: Path
) -> PrivateRegistryStageReview:
    """Create only one immutable stage, not the registry replacement.

    This helper intentionally does not acquire ordered locks or prove that a
    qualifying journal exists. A future transaction coordinator must perform
    those checks before calling it. No stage result authorizes CAS or use.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRegistryStageState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
    ):
        return _result(PrivateRegistryStageState.INVALID_REQUEST)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        verified = intents.decode_private_transaction_intent(canonical)
        if (
            verified != proposed
            or intents.encode_private_transaction_intent(verified) != canonical
        ):
            return _result(PrivateRegistryStageState.INVALID_REQUEST)
        if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(PrivateRegistryStageState.INVALID_REQUEST)
        after = metadata.decode_private_registry(proposed.registry_after)
        if metadata.encode_private_registry(after) != proposed.registry_after:
            return _result(PrivateRegistryStageState.INVALID_REQUEST)
        owner = after.owner
        name = "." + proposed.witness.transaction_id + ".registry-stage"
        if sys.platform == "linux":
            if owner.kind != "posix_euid":
                return _result(PrivateRegistryStageState.REFUSED_OWNER)
            return _linux_create(
                existing_private_root, name, proposed.registry_after, owner.value
            )
        if owner.kind != "windows_token_sid":
            return _result(PrivateRegistryStageState.REFUSED_OWNER)
        return _windows_create(
            existing_private_root, name, proposed.registry_after, owner.value
        )
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        AttributeError,
        ValueError,
        TypeError,
        OverflowError,
    ):
        return _result(PrivateRegistryStageState.INVALID_REQUEST)
