"""Internal Windows stage-to-registry replacement attempt (#238 Slice 3G6).

The *only* mutation is one same-directory FileRenameInfoEx of the previously
prepared registry after-image onto registry.json, within the existing 3G5
mutation-aware retained guard. A completed rename is NOT a durable binding,
not multi-file CAS, not a completed journal, and never Notes authorization.

This API is deliberately internal and is not a public teacher operation. It
requires a separately admitted/approved intent and recovery controller before
integration into any production workflow. No such controller is enabled here.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_registry_replacement_guard as guard
from pds_core import _teacher_private_transaction_intent as intents

_FILE_RENAME_INFO_EX = 22
_FILE_RENAME_REPLACE_IF_EXISTS = 0x00000001
_FILE_RENAME_POSIX_SEMANTICS = 0x00000002
_DELETE = 0x00010000
_FILE_READ_ATTRIBUTES = 0x00000080
_READ_CONTROL = 0x00020000
_SHARE_ALL = 0x7
_OPEN_EXISTING = 3
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
# Explicit zero WCHAR tail for Windows variants that read beyond FileNameLength.
_RENAME_NAME_TAIL_BYTES = 64


class _FileRenameInfo(ctypes.Structure):
    """Win32 FILE_RENAME_INFO prefix; FileName is a variable-length UTF-16 array."""

    _fields_ = [
        ("flags", wintypes.DWORD),
        ("root_directory", wintypes.HANDLE),
        ("file_name_length", wintypes.DWORD),
        ("file_name", wintypes.WCHAR * 1),
    ]


class PrivateWindowsReplaceAttemptState(str, Enum):
    REPLACED_RECOVERY_REQUIRED = "replaced_recovery_required"
    REFUSED_RECOVERY_REQUIRED = "refused_recovery_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    GUARD_REFUSED = "guard_refused"
    NATIVE_MOVE_FAILED_RECOVERY_REQUIRED = "native_move_failed_recovery_required"


_MESSAGES = {
    PrivateWindowsReplaceAttemptState.REPLACED_RECOVERY_REQUIRED: (
        "Registry target now matches the prepared after-image; durability, descriptor and journal recovery are still required."
    ),
    PrivateWindowsReplaceAttemptState.REFUSED_RECOVERY_REQUIRED: (
        "Registry replacement outcome requires independent recovery; all evidence was preserved."
    ),
    PrivateWindowsReplaceAttemptState.INVALID_REQUEST: "Registry replacement request invalid.",
    PrivateWindowsReplaceAttemptState.UNSUPPORTED: "Windows native registry replacement unsupported.",
    PrivateWindowsReplaceAttemptState.GUARD_REFUSED: (
        "Native registry replacement was refused by the retained guard."
    ),
    PrivateWindowsReplaceAttemptState.NATIVE_MOVE_FAILED_RECOVERY_REQUIRED: (
        "Native handle-based replacement failed or is unsupported; preserve journal, stage and metadata for recovery review."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateWindowsReplaceAttemptReview:
    """Sanitized result. Never a commit token, handle, principal or path."""

    state: PrivateWindowsReplaceAttemptState
    message: str


def _result(
    state: PrivateWindowsReplaceAttemptState,
) -> PrivateWindowsReplaceAttemptReview:
    return PrivateWindowsReplaceAttemptReview(state, _MESSAGES[state])


def _replace_open_target_posix(source: Path, target: Path) -> bool:
    """Rename the already qualified stage over an open registry on Win10+.

    The 3G5 guard must hold both original and stage handles sharing DELETE.
    Legacy MoveFileExW may refuse an open destination even with that sharing;
    use FILE_RENAME_INFO_EX + POSIX_SEMANTICS instead. Refuse unsupported
    volumes rather than closing guard handles or using a copy/delete fallback.
    Success is NOT directory-entry crash durability or transaction commit.
    """
    if (
        not isinstance(source, Path)
        or not isinstance(target, Path)
        or source.parent != target.parent
        or source == target
    ):
        return False
    kernel, _ = wincheck._bind_api()
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
    kernel.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL

    handle = kernel.CreateFileW(
        str(source),
        _DELETE | _FILE_READ_ATTRIBUTES | _READ_CONTROL,
        _SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    value = ctypes.cast(handle, ctypes.c_void_p).value
    if value is None or value == ctypes.c_void_p(-1).value:
        return False
    try:
        name = str(target).encode("utf-16-le", errors="strict")
        if not name or len(name) > 32760 or "\x00" in str(target):
            return False
        # CI Windows 3.12/3.13 appended two variable WCHARs to an exactly
        # sized target. The protocol permits trailing padding, so preserve
        # FileNameLength while supplying zeroed extra WCHAR storage.
        size = max(
            ctypes.sizeof(_FileRenameInfo),
            _FileRenameInfo.file_name.offset + len(name) + _RENAME_NAME_TAIL_BYTES,
        )
        raw = ctypes.create_string_buffer(size)
        header = _FileRenameInfo.from_buffer(raw)
        header.flags = _FILE_RENAME_REPLACE_IF_EXISTS | _FILE_RENAME_POSIX_SEMANTICS
        header.root_directory = None
        header.file_name_length = len(name)
        ctypes.memmove(
            ctypes.addressof(raw) + _FileRenameInfo.file_name.offset, name, len(name)
        )
        return bool(
            kernel.SetFileInformationByHandle(
                wintypes.HANDLE(value), _FILE_RENAME_INFO_EX, ctypes.byref(raw), size
            )
        )
    finally:
        kernel.CloseHandle(wintypes.HANDLE(value))


def attempt_windows_private_registry_stage_replacement(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateWindowsReplaceAttemptReview:
    """Perform at most one guarded rename, never claim binding authorization.

    This low-level helper is NOT a complete transaction coordinator. Callers
    must not expose it as a public action or treat a result as consent,
    admission, durable CAS, journal retirement, completed binding or Notes
    availability. Failed post-checks preserve all remaining on-disk evidence.
    """
    if sys.platform != "win32":
        return _result(PrivateWindowsReplaceAttemptState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(PrivateWindowsReplaceAttemptState.INVALID_REQUEST)
    moved = False
    move_failed = False
    try:
        # The 3G5 guard checks canonical intent, ordered locks, qualified
        # Windows owner, exact journal/before/stage/descriptor images, and
        # retained native parent/target/stage identities across this call.
        with guard.hold_expected_windows_private_registry_replacement(
            proposed, existing_private_root, existing_workspace_root
        ):
            source = existing_private_root / (
                "." + proposed.witness.transaction_id + ".registry-stage"
            )
            target = existing_private_root / "registry.json"
            moved = _replace_open_target_posix(source, target)
            move_failed = not moved
    except guard.PrivateWindowsRegistryReplacementError as error:
        if move_failed:
            return _result(
                PrivateWindowsReplaceAttemptState.NATIVE_MOVE_FAILED_RECOVERY_REQUIRED
            )
        if moved:
            return _result(PrivateWindowsReplaceAttemptState.REFUSED_RECOVERY_REQUIRED)
        if error.code is guard.PrivateWindowsRegistryReplacementCode.UNSUPPORTED:
            return _result(PrivateWindowsReplaceAttemptState.UNSUPPORTED)
        if error.code is guard.PrivateWindowsRegistryReplacementCode.INVALID_REQUEST:
            return _result(PrivateWindowsReplaceAttemptState.INVALID_REQUEST)
        return _result(PrivateWindowsReplaceAttemptState.GUARD_REFUSED)
    except (
        wincheck._NativeUnavailable,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivateWindowsReplaceAttemptState.REFUSED_RECOVERY_REQUIRED)
    return _result(
        PrivateWindowsReplaceAttemptState.REPLACED_RECOVERY_REQUIRED
        if moved
        else PrivateWindowsReplaceAttemptState.REFUSED_RECOVERY_REQUIRED
    )
