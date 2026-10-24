"""Read-only OS-owner and prospective private data-root inspection (#238).

This private module intentionally does not qualify a writable Notes store.
No caller can obtain a READY storage handle from this preliminary inspection.
Native effective ACL, filesystem-locality and race-resistant handle checks
remain mandatory in later #238 slices before any durable private writes.
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
from typing import Literal


class PrivateRootState(str, Enum):
    """Conservative results; no value authorizes private data access."""

    MISSING = "missing"
    PRESENT_UNVERIFIED = "present_unverified"
    INVALID_CONFIGURATION = "invalid_configuration"
    UNSAFE_PATH = "unsafe_path"
    ACCESS_DENIED = "access_denied"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class EffectiveOSOwner:
    """Native principal evidence, never a teacher identity or authentication API."""

    kind: Literal["windows_token_sid", "posix_euid"]
    value: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PrivateRootInspection:
    """Internal observation only; never a validated storage handle."""

    state: PrivateRootState
    owner: EffectiveOSOwner | None = field(repr=False)
    candidate: Path | None = field(repr=False)
    message: str


class _OwnerUnverifiable(Exception):
    """Native OS owner evidence could not be obtained."""


def _windows_effective_sid() -> str:
    """Query the current process *token* SID (not the username or logon label)."""
    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        raise _OwnerUnverifiable
    try:
        advapi = win_dll("advapi32", use_last_error=True)
        kernel = win_dll("kernel32", use_last_error=True)

        class SidAndAttributes(ctypes.Structure):
            _fields_ = [
                ("sid", ctypes.c_void_p),
                ("attributes", wintypes.DWORD),
            ]

        class TokenUser(ctypes.Structure):
            _fields_ = [("user", SidAndAttributes)]

        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetCurrentThread.restype = wintypes.HANDLE
        advapi.OpenThreadToken.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.BOOL,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        advapi.OpenThreadToken.restype = wintypes.BOOL
        advapi.OpenProcessToken.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        advapi.OpenProcessToken.restype = wintypes.BOOL
        advapi.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.GetTokenInformation.restype = wintypes.BOOL
        advapi.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.LPWSTR),
        ]
        advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL

        # Do not claim the primary process SID when a thread impersonates a
        # different security principal. This version refuses impersonation.
        impersonation_token = wintypes.HANDLE()
        if advapi.OpenThreadToken(
            kernel.GetCurrentThread(), 0x0008, True, ctypes.byref(impersonation_token)
        ):
            kernel.CloseHandle(impersonation_token)
            raise _OwnerUnverifiable
        if ctypes.get_last_error() != 1008:  # ERROR_NO_TOKEN
            raise _OwnerUnverifiable

        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(
            kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)
        ):
            raise _OwnerUnverifiable
        try:
            size = wintypes.DWORD()
            # Initial failure due to insufficient buffer is expected.
            advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if size.value < ctypes.sizeof(TokenUser) or size.value > 65536:
                raise _OwnerUnverifiable
            buffer = ctypes.create_string_buffer(size.value)
            if not advapi.GetTokenInformation(
                token, 1, buffer, size, ctypes.byref(size)
            ):
                raise _OwnerUnverifiable
            token_user = ctypes.cast(buffer, ctypes.POINTER(TokenUser)).contents
            if not token_user.user.sid:
                raise _OwnerUnverifiable
            sid_ptr = wintypes.LPWSTR()
            if not advapi.ConvertSidToStringSidW(
                token_user.user.sid, ctypes.byref(sid_ptr)
            ):
                raise _OwnerUnverifiable
            try:
                sid = sid_ptr.value
                if not sid or not sid.startswith("S-1-"):
                    raise _OwnerUnverifiable
                return sid
            finally:
                kernel.LocalFree(ctypes.cast(sid_ptr, ctypes.c_void_p))
        finally:
            kernel.CloseHandle(token)
    except (AttributeError, OSError, ValueError, TypeError) as exc:
        raise _OwnerUnverifiable from exc


def _effective_owner(platform: str) -> EffectiveOSOwner:
    if platform == "win32":
        return EffectiveOSOwner("windows_token_sid", _windows_effective_sid())
    if platform in {"linux", "darwin"}:
        get_euid = getattr(os, "geteuid", None)
        if get_euid is None:
            raise _OwnerUnverifiable
        try:
            euid = get_euid()
        except OSError as exc:
            raise _OwnerUnverifiable from exc
        if type(euid) is not int or euid < 0:
            raise _OwnerUnverifiable
        return EffectiveOSOwner("posix_euid", str(euid))
    raise _OwnerUnverifiable


def _candidate_private_root(platform: str) -> Path:
    home = Path.home()
    if platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            raise ValueError("LOCALAPPDATA unavailable")
        base = Path(local_appdata)
        suffix = ("Paper Data Suite", "private", "notes", "v1")
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
        suffix = ("Paper Data Suite", "private", "notes", "v1")
    elif platform == "linux":
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data is not None else home / ".local" / "share"
        suffix = ("paper-data-suite", "private", "notes", "v1")
    else:
        raise ValueError("unsupported platform")
    candidate = base.joinpath(*suffix)
    # Do not normalize away traversal; Windows forms are checked on Windows.
    if not base.is_absolute() or ".." in base.parts or ".." in candidate.parts:
        raise ValueError("private data-root location is not an absolute safe path")
    return candidate


def _scan_existing_components(path: Path, owner: EffectiveOSOwner) -> PrivateRootState:
    """Lstat existing path components; do not follow links or create parents.

    This is a preliminary rejection filter, NOT race-resistant validation.
    Later slices must re-open/validate native directory handles under locks.
    """
    chain = (path, *path.parents)
    # Scan outermost first, including the nearest existing ancestor.
    for component in reversed(chain):
        try:
            info = component.lstat()
        except FileNotFoundError:
            return PrivateRootState.MISSING
        except PermissionError:
            return PrivateRootState.ACCESS_DENIED
        except OSError:
            return PrivateRootState.UNSUPPORTED
        if stat.S_ISLNK(info.st_mode):
            return PrivateRootState.UNSAFE_PATH
        if not stat.S_ISDIR(info.st_mode):
            return PrivateRootState.UNSAFE_PATH
        if getattr(info, "st_file_attributes", 0) & 0x400:
            # Windows FILE_ATTRIBUTE_REPARSE_POINT (incl. junctions).
            return PrivateRootState.UNSAFE_PATH
        if component == path and owner.kind == "posix_euid":
            if info.st_uid != int(owner.value):
                return PrivateRootState.ACCESS_DENIED
            if stat.S_IMODE(info.st_mode) & 0o077:
                return PrivateRootState.UNSAFE_PATH
    return PrivateRootState.PRESENT_UNVERIFIED


def inspect_private_root() -> PrivateRootInspection:
    """Non-mutating, sanitized preview of current OS owner/private location.

    PRESENT_UNVERIFIED is deliberately *not* READY. Never pass its candidate
    to a caller for writes. No lock file, metadata, workspace or directory is
    created by this function.
    """
    platform = sys.platform
    try:
        owner = _effective_owner(platform)
    except _OwnerUnverifiable:
        return PrivateRootInspection(
            PrivateRootState.UNSUPPORTED,
            None,
            None,
            "Native effective OS account could not be verified.",
        )
    try:
        candidate = _candidate_private_root(platform)
    except (ValueError, OSError, RuntimeError):
        return PrivateRootInspection(
            PrivateRootState.INVALID_CONFIGURATION,
            owner,
            None,
            "Local private-data root configuration is not qualified.",
        )
    state = _scan_existing_components(candidate, owner)
    messages = {
        PrivateRootState.MISSING: (
            "Private-data location does not exist; no setup performed."
        ),
        PrivateRootState.PRESENT_UNVERIFIED: (
            "Private-data location exists; native security is not yet qualified."
        ),
        PrivateRootState.INVALID_CONFIGURATION: (
            "Local data-root configuration is invalid."
        ),
        PrivateRootState.UNSAFE_PATH: "Private-data path contains an unsafe component.",
        PrivateRootState.ACCESS_DENIED: (
            "Private-data location is not accessible to the effective owner."
        ),
        PrivateRootState.UNSUPPORTED: (
            "Private-data filesystem security cannot be verified."
        ),
    }
    return PrivateRootInspection(state, owner, candidate, messages[state])
