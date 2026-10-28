"""Non-authorizing native transaction-directory identity probe (#238 3D3).

Holds existing registry/workspace locks while checking an existing protected
private journal directory. On Linux it retains a no-follow directory fd;
on Windows it compares FileIdInfo from independently opened directory handles
while the first is still open. This is a bounded observation, never journal
admission, safe cross-device serialization, or authority to mutate metadata.
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
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateJournalAnchorState(str, Enum):
    IDENTITY_OBSERVED_UNQUALIFIED = "identity_observed_unqualified"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    COORDINATION_REFUSED = "coordination_refused"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    MISSING_DIRECTORY = "missing_directory"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_REVIEW = "changed_during_review"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED: "Native directory identity agreed within this observation; journal admission remains unqualified.",
    PrivateJournalAnchorState.INVALID_REQUEST: "Invalid native journal directory inspection request.",
    PrivateJournalAnchorState.UNSUPPORTED: "Native journal directory inspection unsupported.",
    PrivateJournalAnchorState.COORDINATION_REFUSED: "Existing local coordination unavailable.",
    PrivateJournalAnchorState.OWNER_UNAVAILABLE: "Native OS principal unavailable.",
    PrivateJournalAnchorState.OWNER_CHANGED: "Native OS principal changed during inspection.",
    PrivateJournalAnchorState.MISSING_DIRECTORY: "Private transactions directory is absent.",
    PrivateJournalAnchorState.REFUSED_PROTECTION: "Journal directory protection cannot be qualified.",
    PrivateJournalAnchorState.REFUSED_BACKING: "Journal directory has unqualified backing.",
    PrivateJournalAnchorState.ACCESS_DENIED: "Journal directory access denied.",
    PrivateJournalAnchorState.CHANGED_DURING_REVIEW: "Journal directory identity changed during inspection.",
    PrivateJournalAnchorState.IO_ERROR: "Native journal directory inspection failed safely.",
}


@dataclass(frozen=True, slots=True)
class PrivateJournalAnchorReview:
    """Sanitized advisory result: never return handles, file IDs, or paths."""

    state: PrivateJournalAnchorState
    message: str


def _result(state: PrivateJournalAnchorState) -> PrivateJournalAnchorReview:
    return PrivateJournalAnchorReview(state, _MESSAGES[state])


def _linux_anchor(
    directory: Path, owner: inspection.EffectiveOSOwner
) -> PrivateJournalAnchorState:
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0):
        return PrivateJournalAnchorState.UNSUPPORTED
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        return PrivateJournalAnchorState.OWNER_UNAVAILABLE
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() != int(owner.value):
        return PrivateJournalAnchorState.OWNER_CHANGED
    try:
        before = os.lstat(directory)
    except FileNotFoundError:
        return PrivateJournalAnchorState.MISSING_DIRECTORY
    except PermissionError:
        return PrivateJournalAnchorState.ACCESS_DENIED
    except OSError:
        return PrivateJournalAnchorState.IO_ERROR
    if not stat.S_ISDIR(before.st_mode):
        return PrivateJournalAnchorState.REFUSED_PROTECTION
    opened, problem = posix._open_verified_parent(directory, int(owner.value))
    if problem is not None:
        if problem is posix.PrivateChildCreationState.REFUSED_BACKING:
            return PrivateJournalAnchorState.REFUSED_BACKING
        if problem is posix.PrivateChildCreationState.ACCESS_DENIED:
            return PrivateJournalAnchorState.ACCESS_DENIED
        return PrivateJournalAnchorState.REFUSED_PROTECTION
    if opened is None:
        return PrivateJournalAnchorState.UNSUPPORTED
    try:
        active_before = os.fstat(opened)
        at_path = os.stat(directory, follow_symlinks=False)
        active_after = os.fstat(opened)
        after = os.lstat(directory)

        def signature(snapshot: os.stat_result) -> tuple[int, int, int, int, int]:
            return (
                snapshot.st_dev,
                snapshot.st_ino,
                snapshot.st_mode,
                snapshot.st_uid,
                snapshot.st_ctime_ns,
            )

        if (
            not stat.S_ISDIR(active_before.st_mode)
            or not stat.S_ISDIR(at_path.st_mode)
            or not stat.S_ISDIR(after.st_mode)
            or signature(before) != signature(at_path)
            or signature(before) != signature(active_before)
            or signature(active_before) != signature(active_after)
            or signature(before) != signature(after)
        ):
            return PrivateJournalAnchorState.CHANGED_DURING_REVIEW
        return PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED
    except (FileNotFoundError, NotADirectoryError):
        return PrivateJournalAnchorState.CHANGED_DURING_REVIEW
    except PermissionError:
        return PrivateJournalAnchorState.ACCESS_DENIED
    except (OSError, ValueError, AttributeError, OverflowError):
        return PrivateJournalAnchorState.IO_ERROR
    finally:
        os.close(opened)


class _FileIdInfo(ctypes.Structure):
    _fields_ = [
        ("volume_serial", ctypes.c_uint64),
        ("file_id", ctypes.c_ubyte * 16),
    ]


def _windows_id(kernel: Any, handle: int) -> tuple[int, bytes] | None:
    info = _FileIdInfo()
    # FileIdInfo (FILE_INFO_BY_HANDLE_CLASS 18), FILE_ID_INFO (24 bytes).
    if not kernel.GetFileInformationByHandleEx(
        wintypes.HANDLE(handle), 18, ctypes.byref(info), ctypes.sizeof(info)
    ):
        return None
    return int(info.volume_serial), bytes(info.file_id)


def _windows_open(kernel: Any, path: Path) -> tuple[int | None, int]:
    raw = kernel.CreateFileW(
        str(path),
        0x80 | 0x20000,  # FILE_READ_ATTRIBUTES | READ_CONTROL
        7,  # Share read/write/delete; never claim cloud coordination.
        None,
        3,  # OPEN_EXISTING
        0x02000000 | 0x00200000,  # directory, reparse point not followed
        None,
    )
    value = ctypes.cast(raw, ctypes.c_void_p).value
    if value is None or value == ctypes.c_void_p(-1).value:
        return None, ctypes.get_last_error()
    return value, 0


def _windows_anchor(
    directory: Path, owner: inspection.EffectiveOSOwner
) -> PrivateJournalAnchorState:
    if owner.kind != "windows_token_sid":
        return PrivateJournalAnchorState.OWNER_UNAVAILABLE
    first: int | None = None
    second: int | None = None
    kernel: Any = None
    try:
        kernel, advapi = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, directory):
            return PrivateJournalAnchorState.REFUSED_BACKING
        preliminary = wincheck._native_windows_walk(directory, owner)
        if preliminary is NativePrivatePreflightState.MISSING:
            return PrivateJournalAnchorState.MISSING_DIRECTORY
        if preliminary is NativePrivatePreflightState.ACCESS_DENIED:
            return PrivateJournalAnchorState.ACCESS_DENIED
        if preliminary is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED:
            return PrivateJournalAnchorState.REFUSED_PROTECTION
        first, error = _windows_open(kernel, directory)
        if first is None:
            if error in (2, 3):
                return PrivateJournalAnchorState.MISSING_DIRECTORY
            if error in (5, 32):
                return PrivateJournalAnchorState.ACCESS_DENIED
            return PrivateJournalAnchorState.IO_ERROR
        first_info = descriptor._windows_info(kernel, first)
        if (
            first_info is None
            or first_info[0] & 0x400
            or not first_info[0] & 0x10
            or not first_info[1].directory
            or first_info[1].delete_pending
            or wincheck._handle_dacl_state(kernel, advapi, first, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return PrivateJournalAnchorState.REFUSED_PROTECTION
        first_id = _windows_id(kernel, first)
        if first_id is None or not any(first_id[1]):
            return PrivateJournalAnchorState.UNSUPPORTED
        second, error = _windows_open(kernel, directory)
        if second is None:
            return PrivateJournalAnchorState.CHANGED_DURING_REVIEW
        second_info = descriptor._windows_info(kernel, second)
        second_id = _windows_id(kernel, second)
        if (
            second_info is None
            or second_info[0] & 0x400
            or not second_info[0] & 0x10
            or not second_info[1].directory
            or second_info[1].delete_pending
            or second_id != first_id
            or wincheck._handle_dacl_state(kernel, advapi, second, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or wincheck._native_windows_walk(directory, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, directory)
        ):
            return PrivateJournalAnchorState.CHANGED_DURING_REVIEW
        return PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        return PrivateJournalAnchorState.UNSUPPORTED
    except (AttributeError, OSError, ValueError, TypeError, OverflowError):
        return PrivateJournalAnchorState.IO_ERROR
    finally:
        if kernel is not None:
            if second is not None:
                kernel.CloseHandle(wintypes.HANDLE(second))
            if first is not None:
                kernel.CloseHandle(wintypes.HANDLE(first))


def review_existing_native_journal_anchor(
    existing_private_root: Path, existing_workspace_root: Path
) -> PrivateJournalAnchorReview:
    """Check native journal directory identity while local ordered locks held.

    Does not enumerate entries, inspect pending intent content or prove that
    a journal is empty. Not a currentness token and no handles are returned.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateJournalAnchorState.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateJournalAnchorState.INVALID_REQUEST)
    try:
        with ordered._hold_existing_ordered_coordination(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            directory = existing_private_root / "transactions"
            state = (
                _linux_anchor(directory, first_owner)
                if sys.platform == "linux"
                else _windows_anchor(directory, first_owner)
            )
            if ordered._owner() != first_owner:
                return _result(PrivateJournalAnchorState.OWNER_CHANGED)
            return _result(state)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateJournalAnchorState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateJournalAnchorState.OWNER_UNAVAILABLE)
        return _result(PrivateJournalAnchorState.COORDINATION_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateJournalAnchorState.IO_ERROR)
