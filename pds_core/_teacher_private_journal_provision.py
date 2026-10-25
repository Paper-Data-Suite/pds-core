"""Create-only protected transaction-intent file primitive for Core #238.

An explicitly invoked internal helper for a preexisting, owner-private
transactions directory. This creates one immutable journal-intent candidate,
not a binding transaction, recovery service, writable scope or Notes record.
The required descriptor/registry locks and CAS are NOT implemented here.
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

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as file_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_transaction_intent as intent_codec
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateJournalProvisionState(str, Enum):
    CREATED_RESTRICTIVE_UNQUALIFIED = "created_restrictive_unqualified"
    ALREADY_EXISTS = "already_exists"
    INVALID_REQUEST = "invalid_request"
    REFUSED_OWNER = "refused_owner"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CREATION_UNVERIFIED = "creation_unverified"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED: "Protected intent candidate created; transaction remains unqualified.",
    PrivateJournalProvisionState.ALREADY_EXISTS: "Intent candidate exists and was preserved without changes.",
    PrivateJournalProvisionState.INVALID_REQUEST: "Private transaction intent request refused.",
    PrivateJournalProvisionState.REFUSED_OWNER: "Private transaction intent owner refused.",
    PrivateJournalProvisionState.REFUSED_PROTECTION: "Private transaction directory protection refused.",
    PrivateJournalProvisionState.REFUSED_BACKING: "Private transaction backing refused.",
    PrivateJournalProvisionState.ACCESS_DENIED: "Private transaction directory access denied.",
    PrivateJournalProvisionState.CREATION_UNVERIFIED: "Intent candidate may have been created; manual review required.",
    PrivateJournalProvisionState.UNSUPPORTED: "Private transaction intent persistence unsupported.",
}


@dataclass(frozen=True, slots=True)
class PrivateJournalProvisionResult:
    state: PrivateJournalProvisionState
    message: str


def _result(state: PrivateJournalProvisionState) -> PrivateJournalProvisionResult:
    return PrivateJournalProvisionResult(state, _MESSAGES[state])


def _validated_content(raw: object) -> tuple[bytes, str, str, str] | None:
    """Require canonical, internally valid v1 metadata; never trust a UUID alone."""
    if (
        not isinstance(raw, bytes)
        or type(raw) is not bytes
        or len(raw) > intent_codec.MAX_INTENT_BYTES
    ):
        return None
    try:
        decoded = intent_codec.decode_private_transaction_intent(raw)
        if intent_codec.encode_private_transaction_intent(decoded) != raw:
            return None
        owner = metadata.decode_private_registry(decoded.registry_after).owner
        return raw, decoded.witness.transaction_id, owner.kind, owner.value
    except (intent_codec.PrivateIntentError, metadata.PrivateMetadataError):
        return None


def _requested_transactions_dir(directory: Path, platform: str) -> bool:
    if not isinstance(directory, Path) or not directory.is_absolute():
        return False
    try:
        approved = inspection._candidate_private_root(platform) / "transactions"
    except (OSError, ValueError, RuntimeError):
        return False
    if platform == "win32":
        left = wincheck._windows_drive_components(directory)
        right = wincheck._windows_drive_components(approved)
        return (
            left is not None
            and right is not None
            and tuple(part.casefold() for part in left)
            == tuple(part.casefold() for part in right)
        )
    return directory == approved and all(
        element not in ("", ".", "..") for element in str(directory).split("/")[1:]
    )


def _linux_create(
    directory: Path, raw: bytes, name: str, owner: str
) -> PrivateJournalProvisionResult:
    if not _requested_transactions_dir(directory, "linux"):
        return _result(PrivateJournalProvisionState.INVALID_REQUEST)
    if not hasattr(os, "O_NOFOLLOW"):
        return _result(PrivateJournalProvisionState.UNSUPPORTED)
    getuid = getattr(os, "geteuid", None)
    if getuid is None:
        return _result(PrivateJournalProvisionState.UNSUPPORTED)
    current_uid = getuid()
    if type(current_uid) is not int or current_uid <= 0:
        return _result(PrivateJournalProvisionState.UNSUPPORTED)
    if owner != str(current_uid):
        return _result(PrivateJournalProvisionState.REFUSED_OWNER)
    directory_fd, failure = posix._open_verified_parent(directory, current_uid)
    if failure is not None:
        if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
            return _result(PrivateJournalProvisionState.REFUSED_BACKING)
        if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
            return _result(PrivateJournalProvisionState.ACCESS_DENIED)
        return _result(PrivateJournalProvisionState.REFUSED_PROTECTION)
    if directory_fd is None:
        return _result(PrivateJournalProvisionState.UNSUPPORTED)
    created = False
    fd: int | None = None
    try:
        try:
            fd = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW")
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=directory_fd,
            )
            created = True
        except FileExistsError:
            return _result(PrivateJournalProvisionState.ALREADY_EXISTS)
        except PermissionError:
            return _result(PrivateJournalProvisionState.ACCESS_DENIED)
        except OSError:
            return _result(PrivateJournalProvisionState.UNSUPPORTED)
        written = 0
        while written < len(raw):
            length = os.write(fd, raw[written:])
            if length <= 0:
                return _result(PrivateJournalProvisionState.CREATION_UNVERIFIED)
            written += length
        os.fsync(fd)
        info = os.fstat(fd)
        linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        parent = os.fstat(directory_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != current_uid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size != len(raw)
            or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
            or info.st_dev != parent.st_dev
            or posix._acl_absent(fd) is not None
            or not posix._is_known_local_filesystem(fd)
        ):
            return _result(PrivateJournalProvisionState.CREATION_UNVERIFIED)
        os.fsync(directory_fd)
        return _result(PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED)
    except (OSError, AttributeError, ValueError, OverflowError):
        return _result(
            PrivateJournalProvisionState.CREATION_UNVERIFIED
            if created
            else PrivateJournalProvisionState.UNSUPPORTED
        )
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory_fd)


def _windows_create(
    directory: Path, raw: bytes, name: str, owner: str
) -> PrivateJournalProvisionResult:
    if not _requested_transactions_dir(directory, "win32"):
        return _result(PrivateJournalProvisionState.INVALID_REQUEST)
    try:
        current_owner = inspection._effective_owner("win32")
        if current_owner.kind != "windows_token_sid":
            return _result(PrivateJournalProvisionState.UNSUPPORTED)
        if current_owner.value != owner:
            return _result(PrivateJournalProvisionState.REFUSED_OWNER)
        kernel, advapi = wincreate._windows_api()
    except (inspection._OwnerUnverifiable, wincreate._NativeUnavailable):
        return _result(PrivateJournalProvisionState.UNSUPPORTED)
    if not wincreate._known_fixed_local_volume(kernel, directory):
        return _result(PrivateJournalProvisionState.REFUSED_BACKING)
    if (
        wincheck._native_windows_walk(directory, current_owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        return _result(PrivateJournalProvisionState.REFUSED_PROTECTION)
    try:
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
        kernel.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    except (OSError, AttributeError, ValueError, TypeError):
        return _result(PrivateJournalProvisionState.UNSUPPORTED)
    created = False
    handle_value: int | None = None
    try:
        handle_value, error = file_provision._create_file_explicit_dacl_windows(
            kernel, advapi, directory / name, current_owner.value
        )
        if handle_value is None:
            if error in (80, 183):
                return _result(PrivateJournalProvisionState.ALREADY_EXISTS)
            if error in (5, 1314):
                return _result(PrivateJournalProvisionState.ACCESS_DENIED)
            return _result(PrivateJournalProvisionState.UNSUPPORTED)
        created = True
        handle = wintypes.HANDLE(handle_value)
        content = ctypes.create_string_buffer(raw)
        length = wintypes.DWORD()
        if not kernel.WriteFile(
            handle, content, len(raw), ctypes.byref(length), None
        ) or length.value != len(raw):
            return _result(PrivateJournalProvisionState.CREATION_UNVERIFIED)
        if not kernel.FlushFileBuffers(handle):
            return _result(PrivateJournalProvisionState.CREATION_UNVERIFIED)
        info = file_provision._FileAttributeTagInfo()
        if not kernel.GetFileInformationByHandleEx(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ) or info.attributes & (0x10 | 0x400):
            return _result(PrivateJournalProvisionState.CREATION_UNVERIFIED)
        if (
            wincheck._handle_dacl_state(kernel, advapi, handle_value, current_owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or wincheck._native_windows_walk(directory, current_owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, directory)
        ):
            return _result(PrivateJournalProvisionState.CREATION_UNVERIFIED)
        return _result(PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED)
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
            PrivateJournalProvisionState.CREATION_UNVERIFIED
            if created
            else PrivateJournalProvisionState.UNSUPPORTED
        )
    finally:
        if handle_value is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle_value))


def create_private_transaction_intent_file(
    existing_transactions_directory: Path,
    canonical_intent_bytes: bytes,
) -> PrivateJournalProvisionResult:
    """Create a single protected candidate; never apply the represented intent.

    Caller MUST have its own reviewed transaction coordination. This isolated
    helper has no public dispatch, does not initialize a store, and returns no
    file path, principal, write handle, commit token or READY state.
    """
    if not isinstance(existing_transactions_directory, Path):
        return _result(PrivateJournalProvisionState.INVALID_REQUEST)
    validated = _validated_content(canonical_intent_bytes)
    if validated is None:
        return _result(PrivateJournalProvisionState.INVALID_REQUEST)
    raw, transaction_id, kind, owner = validated
    file_name = f"{transaction_id}.json"
    if sys.platform == "linux":
        if kind != "posix_euid":
            return _result(PrivateJournalProvisionState.REFUSED_OWNER)
        return _linux_create(existing_transactions_directory, raw, file_name, owner)
    if sys.platform == "win32":
        if kind != "windows_token_sid":
            return _result(PrivateJournalProvisionState.REFUSED_OWNER)
        return _windows_create(existing_transactions_directory, raw, file_name, owner)
    return _result(PrivateJournalProvisionState.UNSUPPORTED)
