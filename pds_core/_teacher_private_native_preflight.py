"""Read-only, fail-closed native directory preflight for Core #238.

This internal probe can REJECT unsuitable candidate directories. It cannot
authorize a private Notes store: it deliberately returns no READY state,
opened directory handle, storage credential, or path to a consumer. In
particular, Windows DACL, local backing, locking and write-race qualification
are still required before protected creation is enabled.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_inspection as preliminary


class NativePrivatePreflightState(str, Enum):
    """Conservative observation; not a permission to create or use files."""

    MISSING = "missing"
    RESTRICTIVE_UNQUALIFIED = "restrictive_unqualified"
    REFUSED_PATH = "refused_path"
    REFUSED_OWNER = "refused_owner"
    REFUSED_MODE = "refused_mode"
    REFUSED_ACL = "refused_acl"
    ACCESS_DENIED = "access_denied"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    NativePrivatePreflightState.MISSING: "Private-data directory is absent; no setup performed.",
    NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED: (
        "Restrictive native directory attributes observed; store remains unqualified."
    ),
    NativePrivatePreflightState.REFUSED_PATH: "Private-data path is unsafe.",
    NativePrivatePreflightState.REFUSED_OWNER: "Private-data directory owner is not qualified.",
    NativePrivatePreflightState.REFUSED_MODE: "Private-data directory mode is unsafe.",
    NativePrivatePreflightState.REFUSED_ACL: "Private-data directory has an unqualified access ACL.",
    NativePrivatePreflightState.ACCESS_DENIED: "Private-data directory access is denied.",
    NativePrivatePreflightState.UNSUPPORTED: "Native private-data protection is not qualified.",
}


@dataclass(frozen=True, slots=True)
class NativePrivatePreflight:
    """Sanitized summary. Does not expose effective principal or candidate path."""

    state: NativePrivatePreflightState
    message: str


def _outcome(state: NativePrivatePreflightState) -> NativePrivatePreflight:
    return NativePrivatePreflight(state, _MESSAGES[state])


def _linux_acl_state(directory_fd: int) -> NativePrivatePreflightState | None:
    """Reject all POSIX extended ACLs until their effective rights are reviewed.

    ENODATA means no *access* ACL attribute on a filesystem supporting the
    query. ENOTSUP/EOPNOTSUPP and all unknown failures never prove absence.
    """
    getter = getattr(os, "getxattr", None)
    if getter is None:
        return NativePrivatePreflightState.UNSUPPORTED
    try:
        raw_acl = getter(directory_fd, "system.posix_acl_access")
    except OSError as exc:
        if exc.errno == getattr(errno, "ENODATA", -1):
            return None
        if exc.errno in (errno.EACCES, errno.EPERM):
            return NativePrivatePreflightState.ACCESS_DENIED
        return NativePrivatePreflightState.UNSUPPORTED
    # Even a redundant ACL is not considered qualified without an effective
    # access calculation. This conservative refusal is intentional.
    if isinstance(raw_acl, bytes):
        return NativePrivatePreflightState.REFUSED_ACL
    return NativePrivatePreflightState.UNSUPPORTED


def _native_linux_walk(
    candidate: Path, owner: preliminary.EffectiveOSOwner
) -> NativePrivatePreflightState:
    """Inspect path components through directory FDs, never following links.

    This is a *read-only* snapshot; FDs are closed before return. A later
    writer must independently re-check and retain guarded handles/locks.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if (
        sys.platform != "linux"
        or not nofollow
        or not directory
        or owner.kind != "posix_euid"
        or candidate.anchor != "/"
        or len(candidate.parts) < 5
    ):
        return NativePrivatePreflightState.UNSUPPORTED
    try:
        uid = int(owner.value)
    except (TypeError, ValueError):
        return NativePrivatePreflightState.UNSUPPORTED
    flags = os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)
    opened: list[int] = []
    try:
        parent_fd = os.open("/", flags)
        opened.append(parent_fd)
        components = candidate.parts[1:]
        for index, component in enumerate(components):
            if component in ("", ".", ".."):
                return NativePrivatePreflightState.REFUSED_PATH
            try:
                child_fd = os.open(component, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                return NativePrivatePreflightState.MISSING
            except PermissionError:
                return NativePrivatePreflightState.ACCESS_DENIED
            except OSError:
                # ELOOP, ENOTDIR and any unrecognized failure are not safe.
                return NativePrivatePreflightState.REFUSED_PATH
            opened.append(child_fd)
            info = os.fstat(child_fd)
            if not stat.S_ISDIR(info.st_mode):
                return NativePrivatePreflightState.REFUSED_PATH
            mode = stat.S_IMODE(info.st_mode)
            # Traversal parents must not be replaceable by untrusted users.
            # A root-owned sticky /tmp-style directory is an exception.
            if mode & 0o022 and not (info.st_uid == 0 and mode & stat.S_ISVTX):
                return NativePrivatePreflightState.REFUSED_PATH
            if index >= len(components) - 3:
                # Only the owned /private/notes/v1 suffix is required to be
                # private. $HOME/.local/share may legitimately be 0755.
                if info.st_uid != uid:
                    return NativePrivatePreflightState.REFUSED_OWNER
                if (mode & 0o777) != 0o700:
                    return NativePrivatePreflightState.REFUSED_MODE
                acl_problem = _linux_acl_state(child_fd)
                if acl_problem is not None:
                    return acl_problem
            parent_fd = child_fd
        # No native filesystem-locality or write-lock guarantee is made here.
        return NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    except PermissionError:
        return NativePrivatePreflightState.ACCESS_DENIED
    except (OSError, OverflowError):
        return NativePrivatePreflightState.UNSUPPORTED
    finally:
        for fd in reversed(opened):
            os.close(fd)


def inspect_native_private_preflight() -> NativePrivatePreflight:
    """Non-mutating native refusal layer on top of Slice 2's inspection.

    Only Linux has a bounded native no-follow/ACL probe here; it still cannot
    return READY. Windows ACL/security descriptor and macOS ACL verification
    are deliberately UNSUPPORTED rather than inferred from POSIX-like modes.
    """
    try:
        initial = preliminary.inspect_private_root()
    except (OSError, ValueError, RuntimeError, TypeError):
        return _outcome(NativePrivatePreflightState.UNSUPPORTED)
    state = initial.state
    if state is preliminary.PrivateRootState.MISSING:
        return _outcome(NativePrivatePreflightState.MISSING)
    if state is preliminary.PrivateRootState.UNSAFE_PATH:
        return _outcome(NativePrivatePreflightState.REFUSED_PATH)
    if state is preliminary.PrivateRootState.ACCESS_DENIED:
        return _outcome(NativePrivatePreflightState.ACCESS_DENIED)
    if state is not preliminary.PrivateRootState.PRESENT_UNVERIFIED:
        return _outcome(NativePrivatePreflightState.UNSUPPORTED)
    if sys.platform != "linux" or initial.candidate is None or initial.owner is None:
        return _outcome(NativePrivatePreflightState.UNSUPPORTED)
    return _outcome(_native_linux_walk(initial.candidate, initial.owner))
