"""Read-only native custody of an EXISTING OS-local private root (#238 3G80).

The public review selects only Core's prospective private-data root, rechecks
current process identity, and retains every native directory handle throughout
both owner/permission inspection and identity continuity verification. Missing
roots are never created. No handle, path, SID, UID, write authority, or token
escapes the review. A passing observation is NOT production admission: it does
not qualify write locks, durable transactions, noncooperating writers or Notes.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from contextlib import ExitStack
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PureWindowsPath

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_native_preflight as preflight


class PrivateRetainedRootState(str, Enum):
    MISSING = "missing"
    RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED = (
        "retained_private_root_observed_unqualified"
    )
    OWNER_UNAVAILABLE = "owner_unavailable"
    ROOT_UNQUALIFIED = "root_unqualified"
    NATIVE_PROTECTION_REFUSED = "native_protection_refused"
    IDENTITY_CHANGED = "identity_changed"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateRetainedRootReview:
    state: PrivateRetainedRootState
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateRetainedRootReview(non_authorizing=True)"


class _CustodyRefused(Exception):
    pass


class _IdentityChanged(Exception):
    pass


def _same_native_owner(owner: inspection.EffectiveOSOwner) -> bool:
    """Re-observe the effective principal, never trust a name/UID hint."""
    if sys.platform not in {"linux", "win32"}:
        return False
    try:
        return inspection._effective_owner(sys.platform) == owner
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        inspection._OwnerUnverifiable,
    ):
        return False


def _linux_held_root(root: Path, owner: inspection.EffectiveOSOwner) -> None:
    """Pin all ancestors with dirfd/no-follow and verify exact live identities.

    Only ``private/notes/v1`` need 0700 and no extended access ACL; the
    public ancestors are still required not to be untrusted-writable. A
    root-owned sticky directory is allowed, as in the existing preflight.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if (
        sys.platform != "linux"
        or owner.kind != "posix_euid"
        or root.anchor != "/"
        or len(root.parts) < 6
        or not nofollow
        or not directory
    ):
        raise _CustodyRefused
    flags = os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)
    components = root.parts[1:]
    if any(part in {"", ".", ".."} for part in components):
        raise _CustodyRefused
    if not _same_native_owner(owner):
        raise _CustodyRefused
    # Keep all directory descriptors, including the starting volume root,
    # until every named component and effective owner has been rechecked.
    with ExitStack() as stack:
        root_fd = os.open("/", flags)
        stack.callback(os.close, root_fd)
        held: list[tuple[int, str, int, tuple[int, int]]] = []
        parent_fd = root_fd
        for index, component in enumerate(components):
            child_fd = os.open(component, flags, dir_fd=parent_fd)
            stack.callback(os.close, child_fd)
            info = os.fstat(child_fd)
            named = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            identity = (info.st_dev, info.st_ino)
            if (
                not stat.S_ISDIR(info.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or identity != (named.st_dev, named.st_ino)
            ):
                raise _IdentityChanged
            mode = stat.S_IMODE(info.st_mode)
            if mode & 0o022 and not (info.st_uid == 0 and mode & stat.S_ISVTX):
                raise _CustodyRefused
            if index >= len(components) - 3:
                if info.st_uid != int(owner.value) or mode != 0o700:
                    raise _CustodyRefused
                if preflight._linux_acl_state(child_fd) is not None:
                    raise _CustodyRefused
            held.append((parent_fd, component, child_fd, identity))
            parent_fd = child_fd
        for index, (fd, component, child_fd, identity) in enumerate(held):
            info = os.fstat(child_fd)
            named = os.stat(component, dir_fd=fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(info.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or identity != (info.st_dev, info.st_ino)
                or identity != (named.st_dev, named.st_ino)
            ):
                raise _IdentityChanged
            mode = stat.S_IMODE(info.st_mode)
            if mode & 0o022 and not (info.st_uid == 0 and mode & stat.S_ISVTX):
                raise _CustodyRefused
            if index >= len(components) - 3:
                if info.st_uid != int(owner.value) or mode != 0o700:
                    raise _CustodyRefused
                if preflight._linux_acl_state(child_fd) is not None:
                    raise _CustodyRefused
        if not _same_native_owner(owner):
            raise _IdentityChanged


def _windows_held_root(root: Path, owner: inspection.EffectiveOSOwner) -> None:
    """Retain all directory HANDLEs through native DACL/identity rechecks."""
    if sys.platform != "win32" or owner.kind != "windows_token_sid":
        raise _CustodyRefused
    from pds_core import _teacher_private_native_journal_anchor as anchor
    from pds_core import _teacher_private_windows_preflight as wincheck

    components = wincheck._windows_drive_components(root)
    if components is None or not _same_native_owner(owner):
        raise _CustodyRefused
    try:
        kernel, advapi = wincheck._bind_api()
    except wincheck._NativeUnavailable as exc:
        raise _CustodyRefused from exc
    held: list[tuple[Path, int, tuple[int, bytes]]] = []
    with ExitStack() as stack:
        current = components[0]
        for index, component in enumerate(components):
            if index:
                current = str(PureWindowsPath(current) / component)
            path = Path(current)
            handle, error = anchor._windows_open(kernel, path)
            if handle is None or error:
                if error in (2, 3):
                    raise FileNotFoundError
                raise _CustodyRefused
            stack.callback(kernel.CloseHandle, wintypes.HANDLE(handle))
            attributes = wincheck._AttributeTagInfo()
            identity = anchor._windows_id(kernel, handle)
            if (
                not kernel.GetFileInformationByHandleEx(
                    wintypes.HANDLE(handle),
                    9,
                    ctypes.byref(attributes),
                    ctypes.sizeof(attributes),
                )
                or identity is None
                or not any(identity[1])
                or (attributes.file_attributes & 0x400)
                or not (attributes.file_attributes & 0x10)
            ):
                raise _CustodyRefused
            if index >= len(components) - 4:
                if (
                    wincheck._handle_dacl_state(kernel, advapi, handle, owner)
                    is not preflight.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                ):
                    raise _CustodyRefused
            held.append((path, handle, identity))
        # The named hierarchy must still point to the same native directory
        # objects; retained HANDLEs are never exported to consumers.
        for index, (path, handle, identity) in enumerate(held):
            current_id = anchor._windows_id(kernel, handle)
            reopened, error = anchor._windows_open(kernel, path)
            if reopened is None or error:
                raise _IdentityChanged
            try:
                reopened_id = anchor._windows_id(kernel, reopened)
                if index >= len(components) - 4:
                    if (
                        wincheck._handle_dacl_state(kernel, advapi, reopened, owner)
                        is not preflight.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                    ):
                        raise _CustodyRefused
            finally:
                kernel.CloseHandle(wintypes.HANDLE(reopened))
            if current_id != identity or reopened_id != identity:
                raise _IdentityChanged
        if not _same_native_owner(owner):
            raise _IdentityChanged


def _probe_existing(
    root: Path, owner: inspection.EffectiveOSOwner
) -> PrivateRetainedRootState:
    """Private, read-only bridge for tests; no path/handle returned."""
    if sys.platform not in {"win32", "linux"}:
        return PrivateRetainedRootState.UNSUPPORTED
    if not isinstance(root, Path) or type(owner) is not inspection.EffectiveOSOwner:
        return PrivateRetainedRootState.ROOT_UNQUALIFIED
    if not _same_native_owner(owner):
        return PrivateRetainedRootState.OWNER_UNAVAILABLE
    try:
        if sys.platform == "linux":
            _linux_held_root(root, owner)
        else:
            _windows_held_root(root, owner)
    except FileNotFoundError:
        return PrivateRetainedRootState.MISSING
    except _IdentityChanged:
        return PrivateRetainedRootState.IDENTITY_CHANGED
    except (
        _CustodyRefused,
        OSError,
        ValueError,
        TypeError,
        OverflowError,
        AttributeError,
    ):
        return PrivateRetainedRootState.NATIVE_PROTECTION_REFUSED
    return PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED


def review_existing_private_root_native_custody() -> PrivateRetainedRootReview:
    """Parameterless, non-mutating OS-root observation; NEVER production READY."""
    if sys.platform not in {"win32", "linux"}:
        return PrivateRetainedRootReview(PrivateRetainedRootState.UNSUPPORTED)
    try:
        first = inspection.inspect_private_root()
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError):
        return PrivateRetainedRootReview(PrivateRetainedRootState.ROOT_UNQUALIFIED)
    if first.state is inspection.PrivateRootState.MISSING:
        return PrivateRetainedRootReview(PrivateRetainedRootState.MISSING)
    if (
        first.state is not inspection.PrivateRootState.PRESENT_UNVERIFIED
        or first.candidate is None
        or first.owner is None
    ):
        return PrivateRetainedRootReview(PrivateRetainedRootState.ROOT_UNQUALIFIED)
    state = _probe_existing(first.candidate, first.owner)
    return PrivateRetainedRootReview(state)
