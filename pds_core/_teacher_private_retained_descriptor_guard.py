"""Retain native workspace descriptor identity inside private ordered guards.

Core #238 Slice 3E0. Both private locks, private journal directory and
registry handles are retained by the enclosing guard. This additional scope
retains the untrusted workspace .pds directory and association sidecar handles.
Neither cloud synchronization nor owner binding is proved by these handles.
No file is created, altered, or opened for writing; no handle is exposed.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from contextlib import contextmanager
from ctypes import wintypes
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, NoReturn

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_retained_registry_guard as registry_guard


class RetainedDescriptorGuardCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    REGISTRY_GUARD_REFUSED = "registry_guard_refused"
    MISSING_DESCRIPTOR = "missing_descriptor"
    REFUSED_PATH = "refused_path"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_SCOPE = "changed_during_scope"
    IO_ERROR = "io_error"


class RetainedDescriptorGuardError(RuntimeError):
    """Bounded, non-sensitive refusal: no workspace or owner string."""

    def __init__(self, code: RetainedDescriptorGuardCode) -> None:
        self.code = code
        super().__init__(f"Retained workspace descriptor guard refused: {code.value}.")


def _refuse(code: RetainedDescriptorGuardCode) -> NoReturn:
    raise RetainedDescriptorGuardError(code)


def _linux_signature(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _linux_check(
    parent_fd: int,
    file_fd: int,
    directory: Path,
    parent_expected: tuple[int, int, int, int, int, int, int, int],
    expected: tuple[int, int, int, int, int, int, int, int],
) -> None:
    """Inspect the retained file/parent and their CURRENT path entries."""
    try:
        parent = os.fstat(parent_fd)
        directory_entry = os.lstat(directory)
        opened = os.fstat(file_fd)
        file_entry = os.stat(
            "teacher-private-association.json",
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(parent.st_mode)
            or not stat.S_ISDIR(directory_entry.st_mode)
            or _linux_signature(parent) != parent_expected
            or _linux_signature(directory_entry) != parent_expected
            or not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(file_entry.st_mode)
            or _linux_signature(opened) != expected
            or _linux_signature(file_entry) != expected
        ):
            _refuse(RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE)
        if opened.st_nlink != 1 or not (
            1 <= opened.st_size <= metadata.MAX_ASSOCIATION_BYTES
        ):
            _refuse(RetainedDescriptorGuardCode.REFUSED_PATH)
    except (FileNotFoundError, NotADirectoryError):
        _refuse(RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE)
    except PermissionError:
        _refuse(RetainedDescriptorGuardCode.ACCESS_DENIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        _refuse(RetainedDescriptorGuardCode.IO_ERROR)


@contextmanager
def _held_linux_descriptor(workspace_root: Path) -> Iterator[None]:
    """Walk existing ancestors without following symlinks; retain final FDs."""
    if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
        _refuse(RetainedDescriptorGuardCode.UNSUPPORTED)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY")
        | getattr(os, "O_NOFOLLOW")
        | getattr(os, "O_CLOEXEC", 0)
    )
    parent_fd: int | None = None
    file_fd: int | None = None
    try:
        try:
            parent_fd = os.open("/", flags)
            for component in (*workspace_root.parts[1:], ".pds"):
                new = os.open(component, flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = new
            try:
                file_fd = os.open(
                    "teacher-private-association.json",
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW")
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=parent_fd,
                )
            except FileNotFoundError:
                _refuse(RetainedDescriptorGuardCode.MISSING_DESCRIPTOR)
            if parent_fd is None or file_fd is None:
                _refuse(RetainedDescriptorGuardCode.IO_ERROR)
            parent_expected = _linux_signature(os.fstat(parent_fd))
            expected = _linux_signature(os.fstat(file_fd))
            directory = workspace_root / ".pds"
            _linux_check(parent_fd, file_fd, directory, parent_expected, expected)
        except RetainedDescriptorGuardError:
            raise
        except FileNotFoundError:
            _refuse(RetainedDescriptorGuardCode.MISSING_DESCRIPTOR)
        except PermissionError:
            _refuse(RetainedDescriptorGuardCode.ACCESS_DENIED)
        except (NotADirectoryError, IsADirectoryError):
            _refuse(RetainedDescriptorGuardCode.REFUSED_PATH)
        except (OSError, ValueError, TypeError, AttributeError, OverflowError):
            _refuse(RetainedDescriptorGuardCode.IO_ERROR)
        yield
        # Caller exceptions propagate unchanged; only successful exit is rechecked.
        _linux_check(parent_fd, file_fd, directory, parent_expected, expected)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


class _FileBasicInfo(ctypes.Structure):
    _fields_ = [
        ("creation_time", ctypes.c_int64),
        ("access_time", ctypes.c_int64),
        ("write_time", ctypes.c_int64),
        ("change_time", ctypes.c_int64),
        ("attributes", wintypes.DWORD),
    ]


def _windows_signature(
    kernel: Any, handle: int, *, directory: bool
) -> tuple[int, bytes, int, int, int] | None:
    """FileIdInfo, file metadata, and no-reparse file type on an open HANDLE."""
    identity = anchor._windows_id(kernel, handle)
    info = descriptor._windows_info(kernel, handle)
    basic = _FileBasicInfo()
    if (
        identity is None
        or not any(identity[1])
        or info is None
        or bool(info[0] & 0x400)
        or bool(info[0] & 0x10) != directory
        or bool(info[1].directory) != directory
        or info[1].delete_pending
        or (not directory and info[1].number_of_links != 1)
        or not kernel.GetFileInformationByHandleEx(
            wintypes.HANDLE(handle), 0, ctypes.byref(basic), ctypes.sizeof(basic)
        )
        or bool(basic.attributes & 0x400)
        or bool(basic.attributes & 0x10) != directory
    ):
        return None
    size = int(info[1].end_of_file)
    if not directory and not (1 <= size <= metadata.MAX_ASSOCIATION_BYTES):
        return None
    return (
        identity[0],
        identity[1],
        size,
        int(basic.write_time),
        int(basic.change_time),
    )


def _windows_check(
    kernel: Any,
    workspace_root: Path,
    parent_handle: int,
    file_handle: int,
    parent_expected: tuple[int, bytes, int, int, int],
    expected: tuple[int, bytes, int, int, int],
) -> None:
    """Compare retained handles to independently opened current paths."""
    if (
        _windows_signature(kernel, parent_handle, directory=True) != parent_expected
        or _windows_signature(kernel, file_handle, directory=False) != expected
    ):
        _refuse(RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE)
    if descriptor._windows_ancestry(kernel, workspace_root) is not None:
        _refuse(RetainedDescriptorGuardCode.REFUSED_PATH)
    directory = workspace_root / ".pds"
    file = directory / "teacher-private-association.json"
    for candidate, is_directory, expected_value in (
        (directory, True, parent_expected),
        (file, False, expected),
    ):
        reopened, error = descriptor._windows_open(
            kernel, str(candidate), directory=is_directory
        )
        if reopened is None:
            if error in (2, 3):
                _refuse(RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE)
            if error in (5, 32):
                _refuse(RetainedDescriptorGuardCode.ACCESS_DENIED)
            _refuse(RetainedDescriptorGuardCode.IO_ERROR)
        try:
            if (
                _windows_signature(kernel, reopened, directory=is_directory)
                != expected_value
            ):
                _refuse(RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE)
        finally:
            kernel.CloseHandle(wintypes.HANDLE(reopened))


@contextmanager
def _held_windows_descriptor(workspace_root: Path) -> Iterator[None]:
    """Retain a directory and descriptor HANDLE; never grant write access."""
    kernel: Any = None
    parent: int | None = None
    opened: int | None = None
    try:
        try:
            kernel = descriptor._windows_api()
            if descriptor._windows_ancestry(kernel, workspace_root) is not None:
                _refuse(RetainedDescriptorGuardCode.REFUSED_PATH)
            parent, error = descriptor._windows_open(
                kernel, str(workspace_root / ".pds"), directory=True
            )
            if parent is None:
                if error in (2, 3):
                    _refuse(RetainedDescriptorGuardCode.MISSING_DESCRIPTOR)
                if error in (5, 32):
                    _refuse(RetainedDescriptorGuardCode.ACCESS_DENIED)
                _refuse(RetainedDescriptorGuardCode.IO_ERROR)
            opened, error = descriptor._windows_open(
                kernel,
                str(workspace_root / ".pds" / "teacher-private-association.json"),
                directory=False,
            )
            if opened is None:
                if error in (2, 3):
                    _refuse(RetainedDescriptorGuardCode.MISSING_DESCRIPTOR)
                if error in (5, 32):
                    _refuse(RetainedDescriptorGuardCode.ACCESS_DENIED)
                _refuse(RetainedDescriptorGuardCode.IO_ERROR)
            parent_expected = _windows_signature(kernel, parent, directory=True)
            expected = _windows_signature(kernel, opened, directory=False)
            if parent_expected is None or expected is None:
                _refuse(RetainedDescriptorGuardCode.REFUSED_PATH)
            _windows_check(
                kernel, workspace_root, parent, opened, parent_expected, expected
            )
        except RetainedDescriptorGuardError:
            raise
        except (OSError, ValueError, TypeError, AttributeError, OverflowError):
            _refuse(RetainedDescriptorGuardCode.IO_ERROR)
        yield
        try:
            _windows_check(
                kernel, workspace_root, parent, opened, parent_expected, expected
            )
        except (OSError, ValueError, TypeError, AttributeError, OverflowError):
            _refuse(RetainedDescriptorGuardCode.IO_ERROR)
    finally:
        if opened is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(opened))
        if parent is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(parent))


@contextmanager
def _hold_existing_retained_descriptor_guard(
    existing_private_root: Path, existing_workspace_root: Path
) -> Iterator[None]:
    """Retain workspace descriptor inside both local locks and private handles.

    Read-only identity observations are NOT binding authority, a content CAS,
    or proof of distributed coordination. The context yields only None.
    """
    if sys.platform not in {"linux", "win32"}:
        _refuse(RetainedDescriptorGuardCode.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(RetainedDescriptorGuardCode.INVALID_REQUEST)
    try:
        with registry_guard._hold_existing_retained_registry_guard(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            held = (
                _held_linux_descriptor(existing_workspace_root)
                if sys.platform == "linux"
                else _held_windows_descriptor(existing_workspace_root)
            )
            with held:
                if first_owner != ordered._owner():
                    _refuse(RetainedDescriptorGuardCode.OWNER_CHANGED)
                yield
                if first_owner != ordered._owner():
                    _refuse(RetainedDescriptorGuardCode.OWNER_CHANGED)
    except registry_guard.RetainedRegistryGuardError as error:
        if error.code is registry_guard.RetainedRegistryGuardCode.OWNER_CHANGED:
            _refuse(RetainedDescriptorGuardCode.OWNER_CHANGED)
        if error.code is registry_guard.RetainedRegistryGuardCode.OWNER_UNAVAILABLE:
            _refuse(RetainedDescriptorGuardCode.OWNER_UNAVAILABLE)
        _refuse(RetainedDescriptorGuardCode.REGISTRY_GUARD_REFUSED)
