"""Disposable Windows registry-reader release boundary rehearsal (#238 3G26).

The restrictive registry image-reader share mask excludes FILE_SHARE_DELETE.
A future writer cannot assume that one continuously held read HANDLE can
coexist with target replacement. Every path and byte here is module-owned,
synthetic and disposable; no production path, callback, bytes, or native handle
may be supplied. This is NOT a journal, commit, custody or durability permit.
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


class PrivateReaderReleaseFault(str, Enum):
    NONE = "none"
    AFTER_GUARD = "after_guard"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_READER_OPEN = "after_reader_open"
    AFTER_BLOCKED_ATTEMPT = "after_blocked_attempt"
    AFTER_READER_RELEASE = "after_reader_release"
    AFTER_REPLACE = "after_replace"
    AFTER_POSTIMAGE = "after_postimage"


class PrivateReaderReleaseState(str, Enum):
    RELEASE_ORDER_OBSERVED_UNQUALIFIED = "release_order_observed_unqualified"
    PREIMAGE_REFUSED = "preimage_refused"
    READER_CONFLICT_PRESERVE = "reader_conflict_preserve"
    PRE_RELEASE_REPLACEMENT_CONFLICT_PRESERVE = (
        "pre_release_replacement_conflict_preserve"
    )
    POST_RELEASE_REPLACEMENT_REFUSED = "post_release_replacement_refused"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    IDENTITY_CONFLICT_PRESERVE = "identity_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateReaderReleaseState.RELEASE_ORDER_OBSERVED_UNQUALIFIED: "Scratch restrictive reader refused replace while open; after release, scratch replacement was observed. No production authority or durability.",
    PrivateReaderReleaseState.PREIMAGE_REFUSED: "Synthetic preimage or existing native file IDs unqualified.",
    PrivateReaderReleaseState.READER_CONFLICT_PRESERVE: "Retained scratch reader byte image or file identity unexpectedly changed.",
    PrivateReaderReleaseState.PRE_RELEASE_REPLACEMENT_CONFLICT_PRESERVE: "Replacement unexpectedly proceeded despite a restrictive scratch reader; preserve evidence.",
    PrivateReaderReleaseState.POST_RELEASE_REPLACEMENT_REFUSED: "Replacement was refused after the restrictive scratch reader released; no fallback authorization.",
    PrivateReaderReleaseState.POSTIMAGE_CONFLICT_PRESERVE: "Synthetic namespace or byte images changed unexpectedly; preserve evidence.",
    PrivateReaderReleaseState.IDENTITY_CONFLICT_PRESERVE: "Scratch file or guard identity changed unexpectedly; preserve evidence.",
    PrivateReaderReleaseState.INTERRUPTED_PRESERVE: "Synthetic operation interrupted; recovery review remains required.",
    PrivateReaderReleaseState.GUARD_REFUSED: "Native scratch advisory guard refused or failed to release.",
    PrivateReaderReleaseState.IO_ERROR: "Synthetic Windows reader-release operation encountered an I/O error.",
    PrivateReaderReleaseState.INVALID_REQUEST: "Only an exact synthetic interruption enum may be requested.",
    PrivateReaderReleaseState.UNSUPPORTED: "Windows reader-release rehearsal unsupported on this platform.",
}


@dataclass(frozen=True, slots=True)
class PrivateReaderReleaseReview:
    """Sanitized state only; no path, source bytes, HANDLE or permit."""

    state: PrivateReaderReleaseState
    message: str


def _result(state: PrivateReaderReleaseState) -> PrivateReaderReleaseReview:
    return PrivateReaderReleaseReview(state, _MESSAGES[state])


class _InjectedInterruption(Exception):
    pass


def _interrupt(
    selected: PrivateReaderReleaseFault, at: PrivateReaderReleaseFault
) -> None:
    if selected is at:
        raise _InjectedInterruption


def _windows() -> bool:
    return sys.platform == "win32"


@contextmanager
def _restrictive_reader(path: Path) -> Iterator[BinaryIO]:
    """Open only an internally created scratch file, mirroring reader masks.

    Win32 GENERIC_READ | READ_CONTROL and FILE_SHARE_READ only, no WRITE or
    DELETE sharing. The CRT owns HANDLE immediately after open_osfhandle.
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
    raw = kernel.CreateFileW(
        str(path),
        0x80000000 | 0x20000,  # GENERIC_READ | READ_CONTROL
        0x1,  # FILE_SHARE_READ only; no share DELETE or WRITE
        None,
        3,  # OPEN_EXISTING
        0x00200000,  # OPEN_REPARSE_POINT
        None,
    )
    handle = ctypes.cast(raw, ctypes.c_void_p).value
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise OSError(
            int(getattr(ctypes, "get_last_error")()), "scratch native open refused"
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
    current = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(current.st_mode)
        or current.st_nlink != 1
        or (current.st_dev, current.st_ino) != expected
        or current.st_size != len(scratch._BEFORE)
    ):
        return False
    stream.seek(0)
    return stream.read(len(scratch._BEFORE) + 1) == scratch._BEFORE


def _same_images(
    root: Path,
    expected: identity._IdentitySet,
    lock_id: identity._FileID,
    *,
    replaced: bool,
) -> PrivateReaderReleaseState | None:
    state = PrivateReaderReleaseState
    if not scratch._expected(root, stage=not replaced):
        return state.POSTIMAGE_CONFLICT_PRESERVE
    after = identity._identities(root, stage=not replaced)
    if identity._identity(root, scratch._LOCK) != lock_id:
        return state.IDENTITY_CONFLICT_PRESERVE
    if not replaced:
        if after != expected:
            return state.IDENTITY_CONFLICT_PRESERVE
    elif (
        expected[3] is None
        or after[0] != expected[3]
        or after[0] == expected[0]
        or after[1:3] != expected[1:3]
        or after[3] is not None
    ):
        return state.IDENTITY_CONFLICT_PRESERVE
    return None


def rehearse_synthetic_registry_reader_release(
    interruption: PrivateReaderReleaseFault = PrivateReaderReleaseFault.NONE,
) -> PrivateReaderReleaseReview:
    """Test read-HANDLE closure before a synthetic native replacement.

    No caller-supplied paths, bytes, handles, callbacks, or authority tokens.
    Native I/O takes place solely in this call's allocated TemporaryDirectory.
    A favorable observation does not establish a production write protocol.
    """
    state = PrivateReaderReleaseState
    fault = PrivateReaderReleaseFault
    if type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if not _windows():
        return _result(state.UNSUPPORTED)
    acquired = False
    replaced = False
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g26_reader_") as temporary:
            root = Path(temporary)
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
                _interrupt(interruption, fault.AFTER_PREIMAGE)
                with _restrictive_reader(root / scratch._REGISTRY) as reader:
                    acquired = True
                    if not _held_before(reader, before[0]):
                        return _result(state.READER_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_READER_OPEN)
                    try:
                        os.replace(root / scratch._STAGE, root / scratch._REGISTRY)
                        replaced = True
                    except OSError as error:
                        # Sharing error is an observation, not proof of cause or ACL.
                        if not isinstance(error, PermissionError) and getattr(
                            error, "winerror", None
                        ) not in (5, 32, 33):
                            raise
                    _interrupt(interruption, fault.AFTER_BLOCKED_ATTEMPT)
                    if replaced:
                        return _result(state.PRE_RELEASE_REPLACEMENT_CONFLICT_PRESERVE)
                    if not _held_before(reader, before[0]):
                        return _result(state.READER_CONFLICT_PRESERVE)
                    conflict = _same_images(root, before, lock_id, replaced=False)
                    if conflict is not None:
                        return _result(conflict)
                _interrupt(interruption, fault.AFTER_READER_RELEASE)
                conflict = _same_images(root, before, lock_id, replaced=False)
                if conflict is not None:
                    return _result(conflict)
                try:
                    os.replace(root / scratch._STAGE, root / scratch._REGISTRY)
                except OSError as error:
                    if isinstance(error, PermissionError) or getattr(
                        error, "winerror", None
                    ) in (5, 32, 33):
                        return _result(state.POST_RELEASE_REPLACEMENT_REFUSED)
                    raise
                _interrupt(interruption, fault.AFTER_REPLACE)
                conflict = _same_images(root, before, lock_id, replaced=True)
                if conflict is not None:
                    return _result(conflict)
                _interrupt(interruption, fault.AFTER_POSTIMAGE)
            return _result(state.RELEASE_ORDER_OBSERVED_UNQUALIFIED)
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except scratch._GuardRefused:
        return _result(state.GUARD_REFUSED)
    except identity._IdentityUnavailable:
        return _result(
            state.IDENTITY_CONFLICT_PRESERVE if acquired else state.PREIMAGE_REFUSED
        )
    except (scratch._UnsafeImage, FileNotFoundError):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE if acquired else state.PREIMAGE_REFUSED
        )
    except (OSError, TypeError, ValueError, OverflowError):
        return _result(state.IO_ERROR)
