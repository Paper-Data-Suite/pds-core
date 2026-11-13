"""Native Windows read-sharing rehearsal on private synthetic scratch (#238 3G24).

All file paths and bytes are module-owned disposable fixtures. This is NOT a
production registry, descriptor, journal, writer permit, or durability proof.
The native target HANDLE is opened with an explicit Win32 sharing mask; a real
os.replace is attempted while the handle and synthetic advisory lock are held.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Iterator

from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch


class PrivateSyntheticWindowsShareMode(str, Enum):
    NO_DELETE_SHARE = "no_delete_share"
    ALLOW_DELETE_SHARE = "allow_delete_share"


class PrivateSyntheticWindowsShareFault(str, Enum):
    NONE = "none"
    AFTER_GUARD = "after_guard"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_NATIVE_OPEN = "after_native_open"
    AFTER_REPLACE_ATTEMPT = "after_replace_attempt"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_HANDLE_RELEASE = "after_handle_release"


class PrivateSyntheticWindowsShareState(str, Enum):
    NO_DELETE_SHARE_BLOCKED_UNQUALIFIED = "no_delete_share_blocked_unqualified"
    DELETE_SHARED_REPLACEMENT_UNQUALIFIED = "delete_shared_replacement_unqualified"
    DELETE_SHARED_REPLACEMENT_REFUSED = "delete_shared_replacement_refused"
    SHARING_INVARIANT_CONFLICT_PRESERVE = "sharing_invariant_conflict_preserve"
    PREIMAGE_REFUSED = "preimage_refused"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    HANDLE_IDENTITY_CONFLICT_PRESERVE = "handle_identity_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateSyntheticWindowsShareState.NO_DELETE_SHARE_BLOCKED_UNQUALIFIED: "Scratch target HANDLE without delete sharing blocked native replace; no production permission.",
    PrivateSyntheticWindowsShareState.DELETE_SHARED_REPLACEMENT_UNQUALIFIED: "Scratch target HANDLE with delete sharing permitted replacement; durable commit remains unqualified.",
    PrivateSyntheticWindowsShareState.DELETE_SHARED_REPLACEMENT_REFUSED: "Scratch target HANDLE with delete sharing did not permit replacement here; no fallback authority.",
    PrivateSyntheticWindowsShareState.SHARING_INVARIANT_CONFLICT_PRESERVE: "Scratch native replacement outcome violated the selected sharing contract.",
    PrivateSyntheticWindowsShareState.PREIMAGE_REFUSED: "Synthetic preimages or file identities did not qualify.",
    PrivateSyntheticWindowsShareState.POSTIMAGE_CONFLICT_PRESERVE: "Synthetic replacement pathname or byte images changed unexpectedly.",
    PrivateSyntheticWindowsShareState.HANDLE_IDENTITY_CONFLICT_PRESERVE: "Retained scratch HANDLE, lockfile, or fixed file identity changed unexpectedly.",
    PrivateSyntheticWindowsShareState.INTERRUPTED_PRESERVE: "Synthetic Windows sharing rehearsal interrupted; no completed-operation assertion.",
    PrivateSyntheticWindowsShareState.GUARD_REFUSED: "Native scratch advisory guard was refused or could not be released.",
    PrivateSyntheticWindowsShareState.IO_ERROR: "Synthetic Windows sharing rehearsal encountered native I/O refusal.",
    PrivateSyntheticWindowsShareState.INVALID_REQUEST: "Only exact synthetic sharing and interruption enums are accepted.",
    PrivateSyntheticWindowsShareState.UNSUPPORTED: "Windows native sharing rehearsal is unsupported on this platform.",
}


@dataclass(frozen=True, slots=True)
class PrivateSyntheticWindowsShareReview:
    """Only fixed sanitized status; no native HANDLE, bytes, path, or authority."""

    state: PrivateSyntheticWindowsShareState
    message: str


def _result(
    state: PrivateSyntheticWindowsShareState,
) -> PrivateSyntheticWindowsShareReview:
    return PrivateSyntheticWindowsShareReview(state, _MESSAGES[state])


class _InjectedInterruption(Exception):
    pass


def _interrupt(
    selected: PrivateSyntheticWindowsShareFault,
    at: PrivateSyntheticWindowsShareFault,
) -> None:
    if selected is at:
        raise _InjectedInterruption


def _windows() -> bool:
    return sys.platform == "win32"


@contextmanager
def _native_target(
    path: Path, mode: PrivateSyntheticWindowsShareMode
) -> Iterator[BinaryIO]:
    """Open one existing synthetic target using explicit Win32 share flags.

    FILE_SHARE_READ alone denies delete/rename sharing. Adding FILE_SHARE_DELETE
    allows a replace *attempt*, but is not a guarantee that the OS will accept.
    The C runtime takes ownership of the native HANDLE on successful conversion.
    """
    import msvcrt

    kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
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
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    share = 0x1  # FILE_SHARE_READ, explicitly NOT FILE_SHARE_WRITE
    if mode is PrivateSyntheticWindowsShareMode.ALLOW_DELETE_SHARE:
        share |= 0x4  # FILE_SHARE_DELETE
    raw = kernel.CreateFileW(
        str(path),
        0x80000000,  # GENERIC_READ
        share,
        None,
        3,  # OPEN_EXISTING, no creation
        0x00200000,  # FILE_FLAG_OPEN_REPARSE_POINT
        None,
    )
    handle = ctypes.cast(raw, ctypes.c_void_p).value
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise OSError(
            int(getattr(ctypes, "get_last_error")()),
            "synthetic Windows CreateFileW refused",
        )
    try:
        fd = int(getattr(msvcrt, "open_osfhandle")(handle, os.O_RDONLY))
    except BaseException:
        kernel.CloseHandle(wintypes.HANDLE(handle))
        raise
    try:
        stream = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        yield stream


def _held_before(stream: BinaryIO, expected: identity._FileID) -> bool:
    info = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(info.st_mode)
        or (info.st_dev, info.st_ino) != expected
        or info.st_size != len(scratch._BEFORE)
    ):
        return False
    stream.seek(0)
    return stream.read(len(scratch._BEFORE) + 1) == scratch._BEFORE


def _sharing_refusal(error: OSError) -> bool:
    return isinstance(error, PermissionError) or getattr(error, "winerror", None) in (
        5,
        32,
        33,
    )


def _images(
    root: Path,
    previous: identity._IdentitySet,
    lock_id: identity._FileID,
    *,
    replaced: bool,
) -> PrivateSyntheticWindowsShareState | None:
    state = PrivateSyntheticWindowsShareState
    if not scratch._expected(root, stage=not replaced):
        return state.POSTIMAGE_CONFLICT_PRESERVE
    after = identity._identities(root, stage=not replaced)
    if identity._identity(root, scratch._LOCK) != lock_id:
        return state.HANDLE_IDENTITY_CONFLICT_PRESERVE
    if replaced:
        if (
            previous[3] is None
            or after[0] != previous[3]
            or after[0] == previous[0]
            or after[1:3] != previous[1:3]
            or after[3] is not None
        ):
            return state.HANDLE_IDENTITY_CONFLICT_PRESERVE
    elif after != previous:
        return state.HANDLE_IDENTITY_CONFLICT_PRESERVE
    return None


def rehearse_synthetic_private_windows_sharing(
    mode: PrivateSyntheticWindowsShareMode = PrivateSyntheticWindowsShareMode.NO_DELETE_SHARE,
    interruption: PrivateSyntheticWindowsShareFault = PrivateSyntheticWindowsShareFault.NONE,
) -> PrivateSyntheticWindowsShareReview:
    """Bounded native Windows sharing experiment; never production mutation.

    No caller path, payload, handle, native writer, or callback is accepted.
    Any observed success merely documents local scratch HANDLE behavior.
    """
    state = PrivateSyntheticWindowsShareState
    fault = PrivateSyntheticWindowsShareFault
    sharing = PrivateSyntheticWindowsShareMode
    if type(mode) is not sharing or type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if not _windows():
        return _result(state.UNSUPPORTED)
    checked = False
    replaced = False
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g24_sharing_") as temp:
            root = Path(temp)
            scratch._write_new(root, scratch._REGISTRY, scratch._BEFORE)
            scratch._write_new(root, scratch._STAGE, scratch._AFTER)
            scratch._write_new(root, "descriptor.json", scratch._DESCRIPTOR)
            scratch._write_new(root, "transactions.json", scratch._JOURNAL)
            with scratch._scratch_lock(root / scratch._LOCK):
                _interrupt(interruption, fault.AFTER_GUARD)
                if not scratch._expected(root, stage=True):
                    return _result(state.PREIMAGE_REFUSED)
                before = identity._identities(root, stage=True)
                lock_id = identity._identity(root, scratch._LOCK)
                if before[3] is None or before[3] == before[0]:
                    return _result(state.PREIMAGE_REFUSED)
                checked = True
                _interrupt(interruption, fault.AFTER_PREIMAGE)
                with _native_target(root / scratch._REGISTRY, mode) as handle:
                    if not _held_before(handle, before[0]):
                        return _result(state.HANDLE_IDENTITY_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_NATIVE_OPEN)
                    try:
                        os.replace(root / scratch._STAGE, root / scratch._REGISTRY)
                        replaced = True
                    except OSError as error:
                        if not _sharing_refusal(error):
                            raise
                    _interrupt(interruption, fault.AFTER_REPLACE_ATTEMPT)
                    if not _held_before(handle, before[0]):
                        return _result(state.HANDLE_IDENTITY_CONFLICT_PRESERVE)
                    result = _images(root, before, lock_id, replaced=replaced)
                    if result is not None:
                        return _result(result)
                    _interrupt(interruption, fault.AFTER_POSTIMAGE)
                _interrupt(interruption, fault.AFTER_HANDLE_RELEASE)
                result = _images(root, before, lock_id, replaced=replaced)
                if result is not None:
                    return _result(result)
                if mode is sharing.NO_DELETE_SHARE:
                    return _result(
                        state.SHARING_INVARIANT_CONFLICT_PRESERVE
                        if replaced
                        else state.NO_DELETE_SHARE_BLOCKED_UNQUALIFIED
                    )
                return _result(
                    state.DELETE_SHARED_REPLACEMENT_UNQUALIFIED
                    if replaced
                    else state.DELETE_SHARED_REPLACEMENT_REFUSED
                )
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except scratch._GuardRefused:
        return _result(state.GUARD_REFUSED)
    except identity._IdentityUnavailable:
        return _result(
            state.HANDLE_IDENTITY_CONFLICT_PRESERVE
            if checked
            else state.PREIMAGE_REFUSED
        )
    except (scratch._UnsafeImage, FileNotFoundError):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE if checked else state.PREIMAGE_REFUSED
        )
    except (OSError, TypeError, ValueError, OverflowError):
        return _result(state.IO_ERROR)
