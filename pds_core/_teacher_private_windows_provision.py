"""Explicit Windows-only protected child creation primitive (Core #238).

Requires a preexisting verified private parent under the candidate user-local
Notes root. Uses an explicit protected owner/SYSTEM/Administrators DACL at
creation. Does not initialize a storage root, registry, journal, lock or Notes.
Even a successfully created child is unqualified for use as a Notes store.
"""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from pathlib import Path, PureWindowsPath
from typing import Any

from pds_core import _teacher_private_inspection as initial
from pds_core import _teacher_private_windows_preflight as preflight
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core._teacher_private_posix_provision import (
    PrivateChildCreationResult,
    PrivateChildCreationState as State,
    _result,
)


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class _NativeUnavailable(Exception):
    """Windows native security/volume evidence is unavailable."""


_SID = re.compile(r"S-1-(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*))+\Z")
_CHILD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _valid_child(value: object) -> bool:
    return (
        type(value) is str
        and _CHILD.fullmatch(value) is not None
        and value.upper() not in _RESERVED
    )


def _within_approved_root(parent: str, approved: str) -> bool:
    """Pure syntactic boundary; never itself proof of owner or filesystem."""
    parent_components = preflight._windows_drive_components(parent)
    root_components = preflight._windows_drive_components(approved)
    if parent_components is None or root_components is None:
        return False
    if len(parent_components) < len(root_components):
        return False
    return tuple(x.casefold() for x in parent_components[: len(root_components)]) == (
        tuple(x.casefold() for x in root_components)
    )


def _windows_api() -> tuple[Any, Any]:
    loader = getattr(ctypes, "WinDLL", None)
    if sys.platform != "win32" or loader is None:
        raise _NativeUnavailable
    try:
        kernel = loader("kernel32", use_last_error=True)
        advapi = loader("advapi32", use_last_error=True)
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = (
            wintypes.BOOL
        )
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.CreateDirectoryW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(_SecurityAttributes),
        ]
        kernel.CreateDirectoryW.restype = wintypes.BOOL
        kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
        kernel.GetDriveTypeW.restype = wintypes.UINT
        kernel.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        kernel.GetVolumeInformationW.restype = wintypes.BOOL
        return kernel, advapi
    except (AttributeError, TypeError, OSError, ValueError) as exc:
        raise _NativeUnavailable from exc


def _known_fixed_local_volume(kernel: Any, parent: Path) -> bool:
    """Conservative fixed-volume / NTFS-or-ReFS filter, not sync proof."""
    components = preflight._windows_drive_components(parent)
    if components is None:
        return False
    anchor = str(PureWindowsPath(components[0]))
    if kernel.GetDriveTypeW(anchor) != 3:  # DRIVE_FIXED
        return False
    fsname = ctypes.create_unicode_buffer(64)
    serial = wintypes.DWORD()
    maximum_component = wintypes.DWORD()
    flags = wintypes.DWORD()
    if not kernel.GetVolumeInformationW(
        anchor,
        None,
        0,
        ctypes.byref(serial),
        ctypes.byref(maximum_component),
        ctypes.byref(flags),
        fsname,
        len(fsname),
    ):
        return False
    return fsname.value.upper() in {"NTFS", "REFS"}


def _create_directory_explicit_dacl(
    kernel: Any, advapi: Any, target: Path, account_sid: str
) -> tuple[bool, int]:
    """Create exactly one directory with inheritance-protected DACL.

    Caller must validate effective SID and parent security independently.
    No default inherited DACL window; explicit security attributes are passed
    to the first CreateDirectoryW call. No ACL is repaired after creation.
    """
    if type(account_sid) is not str or _SID.fullmatch(account_sid) is None:
        raise _NativeUnavailable
    # Protected DACL; OI/CI allows future private children to inherit only
    # these three privileged principals. No Everyone/Users/AppPackages ACE.
    sddl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{account_sid})"
    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        raise _NativeUnavailable
    try:
        if not descriptor.value:
            raise _NativeUnavailable
        attrs = _SecurityAttributes(
            ctypes.sizeof(_SecurityAttributes), descriptor, False
        )
        success = bool(kernel.CreateDirectoryW(str(target), ctypes.byref(attrs)))
        return success, 0 if success else ctypes.get_last_error()
    finally:
        kernel.LocalFree(descriptor)


def create_restrictive_child_windows(
    existing_private_parent: Path, child_name: str
) -> PrivateChildCreationResult:
    """Opt-in native Windows mkdir under an *already verified* Notes parent.

    No directory is created if any precondition is uncertain. After successful
    native mkdir an unverified postcondition requires manual review, never
    automatic deletion or Notes activation. No path/SID/handle is returned.
    """
    if sys.platform != "win32":
        return _result(State.UNSUPPORTED)
    if not isinstance(existing_private_parent, Path) or not _valid_child(child_name):
        return _result(State.INVALID_REQUEST)
    parent = existing_private_parent
    try:
        approved = initial._candidate_private_root("win32")
    except (ValueError, OSError, RuntimeError):
        return _result(State.UNSUPPORTED)
    if not _within_approved_root(str(parent), str(approved)):
        return _result(State.INVALID_REQUEST)
    if not parent.is_absolute() or not parent.exists():
        return _result(State.UNSAFE_PATH)
    try:
        owner = initial._effective_owner("win32")
        if owner.kind != "windows_token_sid" or _SID.fullmatch(owner.value) is None:
            return _result(State.UNSUPPORTED)
        kernel, advapi = _windows_api()
    except (initial._OwnerUnverifiable, _NativeUnavailable):
        return _result(State.UNSUPPORTED)
    created_once = False
    try:
        if not _known_fixed_local_volume(kernel, parent):
            return _result(State.REFUSED_BACKING)
        parent_state = preflight._native_windows_walk(parent, owner)
        if parent_state is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED:
            return _result(_map_preflight_state(parent_state))
        # The parent lives in the per-user private tree. Other normal local
        # accounts must lack permission to rename it; same-user hostile code
        # and admin/root remain outside this discretionary OS boundary.
        child = parent / child_name
        created, error = _create_directory_explicit_dacl(
            kernel, advapi, child, owner.value
        )
        if not created:
            if error in {80, 183}:  # ERROR_FILE_EXISTS, ERROR_ALREADY_EXISTS
                return _result(State.ALREADY_EXISTS)
            if error in {5, 1314}:  # ACCESS_DENIED, PRIVILEGE_NOT_HELD
                return _result(State.ACCESS_DENIED)
            return _result(State.UNSUPPORTED)
        created_once = True
        # Once CreateDirectoryW succeeds, do not return a pre-creation refusal.
        # Inconclusive postchecks leave a real directory for manual review.
        if (
            preflight._native_windows_walk(parent, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or preflight._native_windows_walk(child, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not _known_fixed_local_volume(kernel, parent)
        ):
            return _result(State.CREATION_UNVERIFIED)
        return _result(State.CREATED_RESTRICTIVE_UNQUALIFIED)
    except (
        _NativeUnavailable,
        AttributeError,
        OSError,
        ValueError,
        OverflowError,
        TypeError,
    ):
        return _result(State.CREATION_UNVERIFIED if created_once else State.UNSUPPORTED)


def _map_preflight_state(state: NativePrivatePreflightState) -> State:
    return {
        NativePrivatePreflightState.MISSING: State.UNSAFE_PATH,
        NativePrivatePreflightState.REFUSED_PATH: State.UNSAFE_PATH,
        NativePrivatePreflightState.REFUSED_OWNER: State.REFUSED_OWNER,
        NativePrivatePreflightState.REFUSED_MODE: State.REFUSED_MODE,
        NativePrivatePreflightState.REFUSED_ACL: State.REFUSED_ACL,
        NativePrivatePreflightState.ACCESS_DENIED: State.ACCESS_DENIED,
        NativePrivatePreflightState.UNSUPPORTED: State.UNSUPPORTED,
        NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED: State.UNSUPPORTED,
    }[state]
