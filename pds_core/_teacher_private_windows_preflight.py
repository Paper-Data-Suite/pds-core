"""Read-only Windows directory-handle and DACL refusal preflight (#238).

No result authorizes private storage. Handle checks are observations only:
path replacement, backing-store locality and transaction/lock proof remain
unqualified. Nothing is created, opened for writing or ACL-modified here.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path, PureWindowsPath
from typing import Any, Final

from pds_core._teacher_private_inspection import EffectiveOSOwner
from pds_core._teacher_private_native_preflight import (
    NativePrivatePreflightState as State,
)

_FILE_READ_ATTRIBUTES: Final = 0x00000080
_READ_CONTROL: Final = 0x00020000
_FILE_SHARE_ALL: Final = 0x00000007
_OPEN_EXISTING: Final = 3
_FILE_FLAG_BACKUP_SEMANTICS: Final = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT: Final = 0x00200000
_FILE_ATTRIBUTE_DIRECTORY: Final = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT: Final = 0x00000400
_INVALID_HANDLE_VALUE: Final = ctypes.c_void_p(-1).value
_SYSTEM_SID: Final = "S-1-5-18"
_ADMINISTRATORS_SID: Final = "S-1-5-32-544"
_ALLOWED_ACE: Final = 0
_DENIED_ACE: Final = 1


class _AttributeTagInfo(ctypes.Structure):
    _fields_ = [("file_attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD)]


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("ace_count", wintypes.DWORD),
        ("acl_bytes_in_use", wintypes.DWORD),
        ("acl_bytes_free", wintypes.DWORD),
    ]


class _AceHeader(ctypes.Structure):
    _fields_ = [
        ("ace_type", ctypes.c_ubyte),
        ("ace_flags", ctypes.c_ubyte),
        ("ace_size", wintypes.WORD),
    ]


class _NativeUnavailable(Exception):
    """Windows security API did not supply sufficient reliable evidence."""


def _classify_dacl(
    account_sid: str,
    directory_owner_sid: str,
    entries: tuple[tuple[int, int, str], ...],
) -> State:
    """Conservative DACL test, not a full Windows effective-access decision.

    A recognized owner ALLOW must cover basic directory read/write; only the
    owner, SYSTEM and Administrators may receive any ALLOW rights. All other
    ACE types and all DENY ACEs are unqualified. This may refuse legitimate
    folders deliberately; it never grants write authority to them.
    """
    if not account_sid or directory_owner_sid != account_sid:
        return State.REFUSED_OWNER
    trusted = {account_sid, _SYSTEM_SID, _ADMINISTRATORS_SID}
    owner_rights = 0
    for ace_type, mask, sid in entries:
        if type(ace_type) is not int or type(mask) is not int or not sid:
            return State.REFUSED_ACL
        if ace_type != _ALLOWED_ACE or sid not in trusted:
            return State.REFUSED_ACL
        if sid == account_sid:
            owner_rights |= mask
    # FILE_LIST_DIRECTORY (0x1), FILE_ADD_FILE (0x2), READ_CONTROL.
    required = 0x00000003 | _READ_CONTROL
    if (owner_rights & required) != required:
        return State.REFUSED_ACL
    return State.RESTRICTIVE_UNQUALIFIED


def _windows_drive_components(candidate: Path | str) -> tuple[str, ...] | None:
    """Reject device/UNC/relative/ADS/traversal forms before Windows API calls."""
    raw = str(candidate)
    if raw.startswith(("\\\\", "//")) or "\x00" in raw:
        return None
    windows_path = PureWindowsPath(raw)
    if (
        not windows_path.is_absolute()
        or len(windows_path.drive) != 2
        or windows_path.drive[1] != ":"
        or windows_path.root != "\\"
        or any(part in ("", ".", "..") for part in windows_path.parts[1:])
        or len(windows_path.parts) < 6
    ):
        return None
    # Disallow explicit dot components and alternative data streams, which
    # PureWindowsPath may normalize away if used alone.
    components = raw.replace("/", "\\").split("\\")
    if any(part in ("", ".", "..") for part in components[1:]):
        return None
    if any(":" in part for part in components[1:]):
        return None
    return tuple(str(part) for part in windows_path.parts)


def _bind_api() -> tuple[Any, Any]:
    """Acquire typed Windows APIs only when actually running on Windows."""
    loader = getattr(ctypes, "WinDLL", None)
    if sys.platform != "win32" or loader is None:
        raise _NativeUnavailable
    try:
        kernel = loader("kernel32", use_last_error=True)
        advapi = loader("advapi32", use_last_error=True)
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
        kernel.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        advapi.GetSecurityInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetSecurityInfo.restype = wintypes.DWORD
        advapi.GetAclInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_int,
        ]
        advapi.GetAclInformation.restype = wintypes.BOOL
        advapi.GetAce.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetAce.restype = wintypes.BOOL
        advapi.IsValidSid.argtypes = [ctypes.c_void_p]
        advapi.IsValidSid.restype = wintypes.BOOL
        advapi.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.LPWSTR),
        ]
        advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
        return kernel, advapi
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise _NativeUnavailable from exc


def _sid_string(kernel: Any, advapi: Any, ptr: int) -> str:
    if not ptr or not advapi.IsValidSid(ctypes.c_void_p(ptr)):
        raise _NativeUnavailable
    string_pointer = wintypes.LPWSTR()
    if not advapi.ConvertSidToStringSidW(
        ctypes.c_void_p(ptr), ctypes.byref(string_pointer)
    ):
        raise _NativeUnavailable
    try:
        result = string_pointer.value
        if not result or not result.startswith("S-1-"):
            raise _NativeUnavailable
        return result
    finally:
        kernel.LocalFree(ctypes.cast(string_pointer, ctypes.c_void_p))


def _handle_dacl_state(
    kernel: Any, advapi: Any, handle: int, owner: EffectiveOSOwner
) -> State:
    """Read DACL from the opened handle and reject every unrecognized ACE."""
    owner_ptr = ctypes.c_void_p()
    dacl_ptr = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    # SE_FILE_OBJECT=1; OWNER_SECURITY_INFORMATION=1; DACL_SECURITY_INFORMATION=4.
    error = advapi.GetSecurityInfo(
        handle,
        1,
        5,
        ctypes.byref(owner_ptr),
        None,
        ctypes.byref(dacl_ptr),
        None,
        ctypes.byref(descriptor),
    )
    if error:
        if error == 5:
            return State.ACCESS_DENIED
        return State.UNSUPPORTED
    try:
        if not descriptor.value or not dacl_ptr.value or not owner_ptr.value:
            return State.REFUSED_ACL
        dir_sid = _sid_string(kernel, advapi, owner_ptr.value)
        sizes = _AclSizeInformation()
        # AclSizeInformation=2.
        if not advapi.GetAclInformation(
            dacl_ptr, ctypes.byref(sizes), ctypes.sizeof(sizes), 2
        ):
            return State.UNSUPPORTED
        if sizes.ace_count > 4096 or sizes.acl_bytes_in_use > 65536:
            return State.REFUSED_ACL
        entries: list[tuple[int, int, str]] = []
        for index in range(sizes.ace_count):
            ace_ptr = ctypes.c_void_p()
            if not advapi.GetAce(dacl_ptr, index, ctypes.byref(ace_ptr)):
                return State.UNSUPPORTED
            address = ace_ptr.value
            if address is None:
                return State.UNSUPPORTED
            header = ctypes.cast(address, ctypes.POINTER(_AceHeader)).contents
            if header.ace_size < 16 or header.ace_type not in (
                _ALLOWED_ACE,
                _DENIED_ACE,
            ):
                return State.REFUSED_ACL
            # Standard ACCESS_ALLOWED/DENIED_ACE: header[4], mask[4], SID[...].
            mask = ctypes.c_uint32.from_address(address + 4).value
            sid = _sid_string(kernel, advapi, address + 8)
            entries.append((int(header.ace_type), int(mask), sid))
        return _classify_dacl(owner.value, dir_sid, tuple(entries))
    except (_NativeUnavailable, ValueError, OSError, TypeError, OverflowError):
        return State.UNSUPPORTED
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)


def _native_windows_walk(candidate: Path, owner: EffectiveOSOwner) -> State:
    """Inspect each existing ancestor handle, refusing links/unsafe ACLs.

    Handles are not retained; paths can change immediately after return.
    Therefore even RESTRICTIVE_UNQUALIFIED cannot authorize later writes.
    """
    if sys.platform != "win32" or owner.kind != "windows_token_sid":
        return State.UNSUPPORTED
    components = _windows_drive_components(candidate)
    if components is None:
        return State.REFUSED_PATH
    try:
        kernel, advapi = _bind_api()
    except _NativeUnavailable:
        return State.UNSUPPORTED
    current = components[0]
    for index, name in enumerate(components):
        if index:
            current = str(PureWindowsPath(current) / name)
        handle = kernel.CreateFileW(
            current,
            _FILE_READ_ATTRIBUTES | _READ_CONTROL,
            _FILE_SHARE_ALL,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        handle_value = ctypes.cast(handle, ctypes.c_void_p).value
        if handle_value is None or handle_value == _INVALID_HANDLE_VALUE:
            code = ctypes.get_last_error()
            if code in (2, 3):
                return State.MISSING
            if code in (5, 1314):
                return State.ACCESS_DENIED
            return State.UNSUPPORTED
        try:
            attributes = _AttributeTagInfo()
            # FileAttributeTagInfo=9.
            if not kernel.GetFileInformationByHandleEx(
                handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)
            ):
                return State.UNSUPPORTED
            if attributes.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                return State.REFUSED_PATH
            if not (attributes.file_attributes & _FILE_ATTRIBUTE_DIRECTORY):
                return State.REFUSED_PATH
            # Exactly the PDS private subtree, not Windows drive-level ACLs.
            if index >= len(components) - 4:
                state = _handle_dacl_state(kernel, advapi, handle, owner)
                if state is not State.RESTRICTIVE_UNQUALIFIED:
                    return state
        except (AttributeError, OSError, ValueError, TypeError, OverflowError):
            return State.UNSUPPORTED
        finally:
            kernel.CloseHandle(handle)
    return State.RESTRICTIVE_UNQUALIFIED
