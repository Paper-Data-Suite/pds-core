"""Disposable retained-handle vs pathname replacement rehearsal (Core #238 3G23).

Fixed synthetic bytes only; no caller paths, metadata, callbacks, handles, or
private workspace authority. An open target handle and a current pathname are
independent references across a native rename. Windows may deny the replacement
while that handle is open. Either result remains non-authorizing and non-durable.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch


class PrivateSyntheticHandleWindowFault(str, Enum):
    NONE = "none"
    AFTER_GUARD = "after_guard"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_HANDLE_OPEN = "after_handle_open"
    AFTER_REPLACE_ATTEMPT = "after_replace_attempt"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_HANDLE_RELEASE = "after_handle_release"


class PrivateSyntheticHandleWindowState(str, Enum):
    PATH_REPLACED_OLD_HANDLE_UNQUALIFIED = "path_replaced_old_handle_unqualified"
    OPEN_HANDLE_BLOCKED_REPLACE_UNQUALIFIED = "open_handle_blocked_replace_unqualified"
    PREIMAGE_REFUSED = "preimage_refused"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    HANDLE_IDENTITY_CONFLICT_PRESERVE = "handle_identity_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateSyntheticHandleWindowState.PATH_REPLACED_OLD_HANDLE_UNQUALIFIED: "Scratch pathname now names the staged file; the held handle still names the old file. No production custody or durable commit.",
    PrivateSyntheticHandleWindowState.OPEN_HANDLE_BLOCKED_REPLACE_UNQUALIFIED: "Native replacement was blocked by an open scratch target; no production custody or future replacement permit.",
    PrivateSyntheticHandleWindowState.PREIMAGE_REFUSED: "Scratch preimages, namespace, or native file identities were not qualified.",
    PrivateSyntheticHandleWindowState.POSTIMAGE_CONFLICT_PRESERVE: "Scratch pathname or bytes diverged from the native replacement result.",
    PrivateSyntheticHandleWindowState.HANDLE_IDENTITY_CONFLICT_PRESERVE: "Held scratch handle and pathname identities were inconsistent.",
    PrivateSyntheticHandleWindowState.INTERRUPTED_PRESERVE: "Synthetic operation window interrupted; no completed-operation assertion.",
    PrivateSyntheticHandleWindowState.GUARD_REFUSED: "Synthetic advisory guard was refused or changed.",
    PrivateSyntheticHandleWindowState.IO_ERROR: "Scratch native replacement window failed without an authority claim.",
    PrivateSyntheticHandleWindowState.INVALID_REQUEST: "Only an exact synthetic interruption enum is accepted.",
    PrivateSyntheticHandleWindowState.UNSUPPORTED: "Native synthetic handle-window rehearsal is unsupported on this platform.",
}


@dataclass(frozen=True, slots=True)
class PrivateSyntheticHandleWindowReview:
    """Sanitized evidence only; no file IDs, paths, handles, bytes or permits."""

    state: PrivateSyntheticHandleWindowState
    message: str


def _result(
    state: PrivateSyntheticHandleWindowState,
) -> PrivateSyntheticHandleWindowReview:
    return PrivateSyntheticHandleWindowReview(state, _MESSAGES[state])


class _InjectedInterruption(Exception):
    pass


class _UnqualifiedHandle(Exception):
    pass


def _interrupt(
    selected: PrivateSyntheticHandleWindowFault,
    point: PrivateSyntheticHandleWindowFault,
) -> None:
    if selected is point:
        raise _InjectedInterruption


def _held_image(stream: BinaryIO, expected_id: tuple[int, int]) -> bool:
    """Read old opened file by handle even after the pathname may have moved."""
    info = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(info.st_mode)
        or (info.st_dev, info.st_ino) != expected_id
        or info.st_size != len(scratch._BEFORE)
    ):
        return False
    stream.seek(0)
    return stream.read(len(scratch._BEFORE) + 1) == scratch._BEFORE


def _closed_window(
    root: Path,
    previous: identity._IdentitySet,
    *,
    replaced: bool,
) -> bool:
    """Recheck pathname/identity AFTER old target handle closes, still locked."""
    if not scratch._expected(root, stage=not replaced):
        return False
    actual = identity._identities(root, stage=not replaced)
    if replaced:
        return (
            actual[0] == previous[3]
            and actual[0] != previous[0]
            and actual[1:3] == previous[1:3]
            and actual[3] is None
        )
    return actual == previous


def _blocked_open_handle(error: OSError) -> bool:
    """Only a Windows sharing/access denial may count as an expected block."""
    return sys.platform == "win32" and (
        isinstance(error, PermissionError)
        or getattr(error, "winerror", None) in (5, 32, 33)
    )


def rehearse_synthetic_private_handle_window(
    interruption: PrivateSyntheticHandleWindowFault = PrivateSyntheticHandleWindowFault.NONE,
) -> PrivateSyntheticHandleWindowReview:
    """Exercise an open target handle across one os.replace on *own* scratch data.

    A positive answer is never an authorization, durable-persistence proof, or
    statement about production retained descriptor/journal/registry custody.
    """
    state = PrivateSyntheticHandleWindowState
    fault = PrivateSyntheticHandleWindowFault
    if type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    replaced = False
    prechecked = False
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g23_window_") as temporary:
            root = Path(temporary)
            scratch._write_new(root, scratch._REGISTRY, scratch._BEFORE)
            scratch._write_new(root, scratch._STAGE, scratch._AFTER)
            scratch._write_new(root, "descriptor.json", scratch._DESCRIPTOR)
            scratch._write_new(root, "transactions.json", scratch._JOURNAL)
            with scratch._scratch_lock(root / scratch._LOCK):
                _interrupt(interruption, fault.AFTER_GUARD)
                if not scratch._expected(root, stage=True):
                    return _result(state.PREIMAGE_REFUSED)
                previous = identity._identities(root, stage=True)
                if previous[3] is None or previous[0] == previous[3]:
                    return _result(state.PREIMAGE_REFUSED)
                prechecked = True
                _interrupt(interruption, fault.AFTER_PREIMAGE)
                with (root / scratch._REGISTRY).open("rb") as held:
                    if not _held_image(held, previous[0]):
                        return _result(state.HANDLE_IDENTITY_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_HANDLE_OPEN)
                    try:
                        os.replace(root / scratch._STAGE, root / scratch._REGISTRY)
                        replaced = True
                    except OSError as error:
                        if not _blocked_open_handle(error):
                            raise
                    _interrupt(interruption, fault.AFTER_REPLACE_ATTEMPT)
                    if not _held_image(held, previous[0]):
                        return _result(state.HANDLE_IDENTITY_CONFLICT_PRESERVE)
                    if not _closed_window(root, previous, replaced=replaced):
                        return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_POSTIMAGE)
                _interrupt(interruption, fault.AFTER_HANDLE_RELEASE)
                if not _closed_window(root, previous, replaced=replaced):
                    return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
            return _result(
                state.PATH_REPLACED_OLD_HANDLE_UNQUALIFIED
                if replaced
                else state.OPEN_HANDLE_BLOCKED_REPLACE_UNQUALIFIED
            )
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except scratch._GuardRefused:
        return _result(state.GUARD_REFUSED)
    except (identity._IdentityUnavailable, _UnqualifiedHandle):
        return _result(
            state.HANDLE_IDENTITY_CONFLICT_PRESERVE
            if prechecked
            else state.PREIMAGE_REFUSED
        )
    except (scratch._UnsafeImage, FileNotFoundError):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE if prechecked else state.PREIMAGE_REFUSED
        )
    except (OSError, ValueError, TypeError, OverflowError):
        return _result(state.IO_ERROR)
