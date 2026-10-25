"""Bounded Linux protected-child creation primitive for Core #238 Slice 3B7.

Requires an existing owner-private parent; never creates parent directories,
lock files, registries, association descriptors or Notes records. A successful
creation is still NOT a qualified private Notes store or an authorization handle.
No caller currently invokes this helper from a teacher-facing service.
"""

from __future__ import annotations

import ctypes
import errno
import os
import re
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PrivateChildCreationState(str, Enum):
    """Refusal/creation statuses; no state grants Notes data access."""

    CREATED_RESTRICTIVE_UNQUALIFIED = "created_restrictive_unqualified"
    ALREADY_EXISTS = "already_exists"
    INVALID_REQUEST = "invalid_request"
    UNSAFE_PATH = "unsafe_path"
    REFUSED_OWNER = "refused_owner"
    REFUSED_MODE = "refused_mode"
    REFUSED_ACL = "refused_acl"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CREATION_UNVERIFIED = "creation_unverified"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateChildCreationState.CREATED_RESTRICTIVE_UNQUALIFIED: "A restrictive child directory was created; private storage remains unqualified.",
    PrivateChildCreationState.ALREADY_EXISTS: "Private child already exists; left untouched.",
    PrivateChildCreationState.INVALID_REQUEST: "Private child request is invalid.",
    PrivateChildCreationState.UNSAFE_PATH: "Private directory ancestry is unsafe.",
    PrivateChildCreationState.REFUSED_OWNER: "Private directory owner is unqualified.",
    PrivateChildCreationState.REFUSED_MODE: "Private directory permissions are unqualified.",
    PrivateChildCreationState.REFUSED_ACL: "Private directory ACL is unqualified.",
    PrivateChildCreationState.REFUSED_BACKING: "Private filesystem backing is unqualified.",
    PrivateChildCreationState.ACCESS_DENIED: "Private directory access is denied.",
    PrivateChildCreationState.CREATION_UNVERIFIED: "Private child creation could not be verified; manual review required.",
    PrivateChildCreationState.UNSUPPORTED: "Protected creation is unsupported here.",
}


@dataclass(frozen=True, slots=True)
class PrivateChildCreationResult:
    """Sanitized outcome: intentionally does not expose a path or writable FD."""

    state: PrivateChildCreationState
    message: str


def _result(state: PrivateChildCreationState) -> PrivateChildCreationResult:
    return PrivateChildCreationResult(state, _MESSAGES[state])


def _acl_absent(directory_fd: int) -> PrivateChildCreationState | None:
    """Refuse extended ACLs and unknown xattr support, not just mode bits."""
    getter = getattr(os, "getxattr", None)
    if getter is None:
        return PrivateChildCreationState.UNSUPPORTED
    try:
        getter(directory_fd, "system.posix_acl_access")
    except OSError as exc:
        if exc.errno == getattr(errno, "ENODATA", -1):
            return None
        if exc.errno in (errno.EACCES, errno.EPERM):
            return PrivateChildCreationState.ACCESS_DENIED
        return PrivateChildCreationState.UNSUPPORTED
    return PrivateChildCreationState.REFUSED_ACL


def _is_known_local_filesystem(directory_fd: int) -> bool:
    """Conservative Linux statfs allowlist, never a cloud/backups guarantee.

    Network, FUSE, overlay and unknown filesystem magics are refused. This
    probe is a prerequisite, not complete backing/retention qualification.
    """
    if sys.platform != "linux":
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        fstatfs = libc.fstatfs
        fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
        fstatfs.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(256)
        if fstatfs(directory_fd, buffer) != 0:
            return False
        magic = ctypes.c_long.from_buffer(buffer).value & 0xFFFFFFFF
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    # ext2/3/4, XFS, Btrfs, F2FS, tmpfs. No overlay or FUSE assumptions.
    return magic in {0xEF53, 0x58465342, 0x9123683E, 0xF2F52010, 0x01021994}


def _open_verified_parent(
    parent: Path, uid: int
) -> tuple[int | None, PrivateChildCreationState | None]:
    """Walk by no-follow directory FDs, retaining the final private parent FD."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY")
        | getattr(os, "O_NOFOLLOW")
        | getattr(os, "O_CLOEXEC", 0)
    )
    fd: int | None = None
    try:
        fd = os.open("/", flags)
        for name in parent.parts[1:]:
            if name in ("", ".", ".."):
                return None, PrivateChildCreationState.UNSAFE_PATH
            next_fd = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            info = os.fstat(fd)
            mode = stat.S_IMODE(info.st_mode)
            if not stat.S_ISDIR(info.st_mode):
                return None, PrivateChildCreationState.UNSAFE_PATH
            # Root-owned sticky /tmp may host private per-user directories.
            if mode & 0o022 and not (info.st_uid == 0 and mode & stat.S_ISVTX):
                return None, PrivateChildCreationState.UNSAFE_PATH
            if info.st_uid not in (0, uid):
                return None, PrivateChildCreationState.UNSAFE_PATH
        info = os.fstat(fd)
        if info.st_uid != uid:
            return None, PrivateChildCreationState.REFUSED_OWNER
        if stat.S_IMODE(info.st_mode) != 0o700:
            return None, PrivateChildCreationState.REFUSED_MODE
        acl = _acl_absent(fd)
        if acl is not None:
            return None, acl
        if not _is_known_local_filesystem(fd):
            return None, PrivateChildCreationState.REFUSED_BACKING
        result_fd = fd
        fd = None
        return result_fd, None
    except PermissionError:
        return None, PrivateChildCreationState.ACCESS_DENIED
    except (FileNotFoundError, NotADirectoryError):
        return None, PrivateChildCreationState.UNSAFE_PATH
    except (OSError, ValueError, OverflowError, AttributeError):
        return None, PrivateChildCreationState.UNSUPPORTED
    finally:
        if fd is not None:
            os.close(fd)


def create_restrictive_child_linux(
    existing_private_parent: Path,
    child_name: str,
) -> PrivateChildCreationResult:
    """Explicit one-level secure mkdir under an already-private Linux parent.

    Never follows symbolic links or overwrites entries. Does not clean up a
    created-but-unverified directory automatically: unexpected content must
    remain untouched for human review. No path/UID is included in results.
    """
    if sys.platform != "linux" or not all(
        hasattr(os, name)
        for name in ("O_DIRECTORY", "O_NOFOLLOW", "mkdir", "getxattr", "geteuid")
    ):
        return _result(PrivateChildCreationState.UNSUPPORTED)
    if not isinstance(existing_private_parent, Path) or type(child_name) is not str:
        return _result(PrivateChildCreationState.INVALID_REQUEST)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", child_name):
        return _result(PrivateChildCreationState.INVALID_REQUEST)
    parent = existing_private_parent
    if (
        not parent.is_absolute()
        or parent.anchor != "/"
        or len(parent.parts) < 3
        or any(part in ("", ".", "..") for part in parent.parts[1:])
        or any(part in (".", "..") for part in str(parent).split("/"))
    ):
        return _result(PrivateChildCreationState.INVALID_REQUEST)
    getuid = getattr(os, "geteuid", None)
    if getuid is None:
        return _result(PrivateChildCreationState.UNSUPPORTED)
    try:
        uid = getuid()
    except OSError:
        return _result(PrivateChildCreationState.UNSUPPORTED)
    if type(uid) is not int or uid <= 0:
        # Root is outside the ordinary other-user private-store trust model.
        return _result(PrivateChildCreationState.UNSUPPORTED)
    fd, failure = _open_verified_parent(parent, uid)
    if failure is not None:
        return _result(failure)
    if fd is None:
        return _result(PrivateChildCreationState.UNSUPPORTED)
    try:
        # Reject any preexisting entry, including dangling symlinks. mkdirat
        # is atomic and mode=0700 cannot be loosened by the process umask.
        try:
            os.mkdir(child_name, mode=0o700, dir_fd=fd)
        except FileExistsError:
            return _result(PrivateChildCreationState.ALREADY_EXISTS)
        except PermissionError:
            return _result(PrivateChildCreationState.ACCESS_DENIED)
        except OSError:
            return _result(PrivateChildCreationState.UNSUPPORTED)
        # Creation succeeded. Every subsequent failure is explicitly a
        # partial-state review, not a claim that no child exists.
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY")
            | getattr(os, "O_NOFOLLOW")
            | getattr(os, "O_CLOEXEC", 0)
        )
        child_fd: int | None = None
        try:
            child_fd = os.open(child_name, flags, dir_fd=fd)
            info = os.fstat(child_fd)
            parent_info = os.fstat(fd)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != uid
                or stat.S_IMODE(info.st_mode) != 0o700
                or info.st_dev != parent_info.st_dev
                or _acl_absent(child_fd) is not None
                or not _is_known_local_filesystem(child_fd)
            ):
                return _result(PrivateChildCreationState.CREATION_UNVERIFIED)
            return _result(PrivateChildCreationState.CREATED_RESTRICTIVE_UNQUALIFIED)
        except (OSError, ValueError, OverflowError):
            return _result(PrivateChildCreationState.CREATION_UNVERIFIED)
        finally:
            if child_fd is not None:
                os.close(child_fd)
    finally:
        os.close(fd)
