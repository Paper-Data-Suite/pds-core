"""Bounded native read of one existing private transaction image (#238 3E4).

Requires existing ordered local coordination and retained journal-directory
identity through the outer private review. A canonical image is *evidence*,
not journal durability, completed binding, authorization to replay/retire, or
proof of coordination across a synced workspace or another OS user.
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
from uuid import UUID

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_provision as provision
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_journal_guard as retained
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateJournalImageState(str, Enum):
    OBSERVED_REVIEW_REQUIRED = "observed_review_required"
    MISSING_REVIEW_REQUIRED = "missing_review_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    RETAINED_GUARD_REFUSED = "retained_guard_refused"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_READ = "changed_during_read"
    INVALID_JOURNAL = "invalid_journal"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED: "Canonical existing journal image read under local guards; recovery requires independent review.",
    PrivateJournalImageState.MISSING_REVIEW_REQUIRED: "Named journal entry was not observed; absence cannot authorize a transaction.",
    PrivateJournalImageState.INVALID_REQUEST: "Private journal image request refused.",
    PrivateJournalImageState.UNSUPPORTED: "Private journal image read unsupported.",
    PrivateJournalImageState.OWNER_UNAVAILABLE: "Native owner could not be verified.",
    PrivateJournalImageState.OWNER_CHANGED: "Native owner changed during journal image read.",
    PrivateJournalImageState.RETAINED_GUARD_REFUSED: "Required native journal guard unavailable or changed.",
    PrivateJournalImageState.REFUSED_PROTECTION: "Private journal entry protection is unqualified.",
    PrivateJournalImageState.REFUSED_BACKING: "Private journal entry backing is unqualified.",
    PrivateJournalImageState.ACCESS_DENIED: "Private journal entry access denied.",
    PrivateJournalImageState.CHANGED_DURING_READ: "Journal identity or metadata changed during read.",
    PrivateJournalImageState.INVALID_JOURNAL: "Existing journal bytes are invalid or unrelated to the requested transaction.",
    PrivateJournalImageState.IO_ERROR: "Private journal image read could not complete reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateJournalImageReview:
    """Internal exact bytes; repr/error messages never expose journal contents."""

    state: PrivateJournalImageState
    message: str
    image: bytes | None = field(default=None, repr=False)


def _result(
    state: PrivateJournalImageState, image: bytes | None = None
) -> PrivateJournalImageReview:
    return PrivateJournalImageReview(state, _MESSAGES[state], image)


def _valid_id(value: object) -> bool:
    if type(value) is not str or len(value) != 36:
        return False
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _checked_image(
    raw: bytes, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> PrivateJournalImageReview:
    """Refuse untrusted, noncanonical or owner-mismatched journal content."""
    if not (0 < len(raw) <= intents.MAX_INTENT_BYTES):
        return _result(PrivateJournalImageState.INVALID_JOURNAL)
    validated = provision._validated_content(raw)
    if validated is None:
        return _result(PrivateJournalImageState.INVALID_JOURNAL)
    _, decoded_id, owner_kind, owner_value = validated
    if decoded_id != transaction_id:
        return _result(PrivateJournalImageState.INVALID_JOURNAL)
    if owner_kind != owner.kind or owner_value != owner.value:
        return _result(PrivateJournalImageState.REFUSED_PROTECTION)
    return _result(PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED, raw)


def _linux_identity(
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
    directory: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> PrivateJournalImageReview:
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0):
        return _result(PrivateJournalImageState.UNSUPPORTED)
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        return _result(PrivateJournalImageState.OWNER_UNAVAILABLE)
    uid = int(owner.value)
    if getattr(os, "geteuid", lambda: -1)() != uid:
        return _result(PrivateJournalImageState.OWNER_CHANGED)
    parent: int | None = None
    opened: int | None = None
    name = transaction_id + ".json"
    try:
        parent, failure = posix._open_verified_parent(directory, uid)
        if failure is not None:
            if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
                return _result(PrivateJournalImageState.REFUSED_BACKING)
            if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
                return _result(PrivateJournalImageState.ACCESS_DENIED)
            return _result(PrivateJournalImageState.REFUSED_PROTECTION)
        if parent is None:
            return _result(PrivateJournalImageState.UNSUPPORTED)
        try:
            opened = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent,
            )
        except FileNotFoundError:
            return _result(PrivateJournalImageState.MISSING_REVIEW_REQUIRED)
        except PermissionError:
            return _result(PrivateJournalImageState.ACCESS_DENIED)
        initial = os.fstat(opened)
        linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
        native_parent = os.fstat(parent)
        path_parent = os.lstat(directory)
        if (
            not stat.S_ISREG(initial.st_mode)
            or not stat.S_ISREG(linked.st_mode)
            or not stat.S_ISDIR(native_parent.st_mode)
            or not stat.S_ISDIR(path_parent.st_mode)
            or _linux_identity(initial) != _linux_identity(linked)
            or (native_parent.st_dev, native_parent.st_ino)
            != (path_parent.st_dev, path_parent.st_ino)
            or initial.st_uid != uid
            or stat.S_IMODE(initial.st_mode) != 0o600
            or initial.st_nlink != 1
            or initial.st_dev != native_parent.st_dev
            or posix._acl_absent(opened) is not None
        ):
            return _result(PrivateJournalImageState.REFUSED_PROTECTION)
        if not posix._is_known_local_filesystem(opened):
            return _result(PrivateJournalImageState.REFUSED_BACKING)
        if not (0 < initial.st_size <= intents.MAX_INTENT_BYTES):
            return _result(PrivateJournalImageState.INVALID_JOURNAL)
        raw = bytearray()
        while len(raw) <= intents.MAX_INTENT_BYTES:
            part = os.read(opened, min(65536, intents.MAX_INTENT_BYTES + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        final = os.fstat(opened)
        final_link = os.stat(name, dir_fd=parent, follow_symlinks=False)
        final_parent = os.fstat(parent)
        if (
            _linux_identity(initial) != _linux_identity(final)
            or _linux_identity(initial) != _linux_identity(final_link)
            or _linux_identity(native_parent) != _linux_identity(final_parent)
            or (final_parent.st_dev, final_parent.st_ino)
            != (os.lstat(directory).st_dev, os.lstat(directory).st_ino)
            or len(raw) != initial.st_size
            or getattr(os, "geteuid", lambda: -1)() != uid
        ):
            return _result(PrivateJournalImageState.CHANGED_DURING_READ)
        return _checked_image(bytes(raw), transaction_id, owner)
    except (FileNotFoundError, NotADirectoryError):
        return _result(PrivateJournalImageState.CHANGED_DURING_READ)
    except PermissionError:
        return _result(PrivateJournalImageState.ACCESS_DENIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateJournalImageState.IO_ERROR)
    finally:
        if opened is not None:
            os.close(opened)
        if parent is not None:
            os.close(parent)


def _read_windows(
    directory: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> PrivateJournalImageReview:
    if owner.kind != "windows_token_sid":
        return _result(PrivateJournalImageState.OWNER_UNAVAILABLE)
    kernel: Any = None
    first: int | None = None
    second: int | None = None
    name = directory / (transaction_id + ".json")
    try:
        kernel, advapi = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, directory):
            return _result(PrivateJournalImageState.REFUSED_BACKING)
        if (
            wincheck._native_windows_walk(directory, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateJournalImageState.REFUSED_PROTECTION)
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
        raw_handle = kernel.CreateFileW(
            str(name),
            0x80000000 | 0x20000,
            0x1,
            None,
            3,
            0x00200000,
            None,  # READ_CONTROL, share read only, no reparse follow
        )
        first = ctypes.cast(raw_handle, ctypes.c_void_p).value
        if first is None or first == ctypes.c_void_p(-1).value:
            first = None
            code = ctypes.get_last_error()
            if code in (2, 3):
                return _result(PrivateJournalImageState.MISSING_REVIEW_REQUIRED)
            if code in (5, 32):
                return _result(PrivateJournalImageState.ACCESS_DENIED)
            return _result(PrivateJournalImageState.IO_ERROR)
        signature = registry_guard._windows_signature(kernel, first)
        info = descriptor._windows_info(kernel, first)
        if (
            signature is None
            or info is None
            or not (0 < info[1].end_of_file <= intents.MAX_INTENT_BYTES)
            or wincheck._handle_dacl_state(kernel, advapi, first, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateJournalImageState.REFUSED_PROTECTION)
        content = ctypes.create_string_buffer(int(info[1].end_of_file))
        length = 0
        while length < info[1].end_of_file:
            got = wintypes.DWORD()
            if (
                not kernel.ReadFile(
                    wintypes.HANDLE(first),
                    ctypes.byref(content, length),
                    int(info[1].end_of_file - length),
                    ctypes.byref(got),
                    None,
                )
                or got.value == 0
            ):
                return _result(PrivateJournalImageState.IO_ERROR)
            length += got.value
        if registry_guard._windows_signature(kernel, first) != signature:
            return _result(PrivateJournalImageState.CHANGED_DURING_READ)
        second, error = anchor._windows_open(kernel, name)
        if second is None:
            if error in (2, 3):
                return _result(PrivateJournalImageState.CHANGED_DURING_READ)
            if error in (5, 32):
                return _result(PrivateJournalImageState.ACCESS_DENIED)
            return _result(PrivateJournalImageState.IO_ERROR)
        if (
            registry_guard._windows_signature(kernel, second) != signature
            or wincheck._handle_dacl_state(kernel, advapi, second, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, directory)
            or wincheck._native_windows_walk(directory, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateJournalImageState.CHANGED_DURING_READ)
        return _checked_image(content.raw, transaction_id, owner)
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        return _result(PrivateJournalImageState.UNSUPPORTED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateJournalImageState.IO_ERROR)
    finally:
        if kernel is not None:
            if second is not None:
                kernel.CloseHandle(wintypes.HANDLE(second))
            if first is not None:
                kernel.CloseHandle(wintypes.HANDLE(first))


def _guard_refusal(code: retained.RetainedJournalGuardCode) -> PrivateJournalImageState:
    if code is retained.RetainedJournalGuardCode.OWNER_CHANGED:
        return PrivateJournalImageState.OWNER_CHANGED
    if code is retained.RetainedJournalGuardCode.OWNER_UNAVAILABLE:
        return PrivateJournalImageState.OWNER_UNAVAILABLE
    if code is retained.RetainedJournalGuardCode.UNSUPPORTED:
        return PrivateJournalImageState.UNSUPPORTED
    return PrivateJournalImageState.RETAINED_GUARD_REFUSED


def inspect_existing_private_transaction_image(
    existing_private_root: Path,
    existing_workspace_root: Path,
    transaction_id: str,
) -> PrivateJournalImageReview:
    """Read one exact canonical journal image under existing local coordination.

    The journal directory and both locks remain retained during the read; no
    storage is created or repaired. A matching result is not a durability
    witness, recovery authorization, commit permission, or a Notes capability.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateJournalImageState.UNSUPPORTED)
    if (
        not _valid_id(transaction_id)
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateJournalImageState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_journal_guard(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            directory = existing_private_root / "transactions"
            if not provision._requested_transactions_dir(directory, sys.platform):
                return _result(PrivateJournalImageState.INVALID_REQUEST)
            observed = (
                _read_linux(directory, transaction_id, first_owner)
                if sys.platform == "linux"
                else _read_windows(directory, transaction_id, first_owner)
            )
            if ordered._owner() != first_owner:
                return _result(PrivateJournalImageState.OWNER_CHANGED)
            return observed
    except retained.RetainedJournalGuardError as error:
        return _result(_guard_refusal(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateJournalImageState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateJournalImageState.OWNER_UNAVAILABLE)
        return _result(PrivateJournalImageState.RETAINED_GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateJournalImageState.IO_ERROR)
