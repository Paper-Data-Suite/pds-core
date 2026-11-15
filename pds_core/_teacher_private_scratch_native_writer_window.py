"""Isolated native writer-window *scratch rehearsal* (Core #238, 3G87).

This diagnostic accepts NO paths, transaction intents, handles, bytes or callbacks.
It creates a random temporary directory under the running user's temp area,
retains an actual native parent-directory identity, holds the existing local
coordination lock, and attempts exactly one disposable registry replacement.
It never opens the production private root or a workspace, cannot create a
production binding and NEVER issues writer authority. An uncooperative writer
can still change a path between two path-based checks: this is NOT a native
compare-and-swap, durability guarantee or noncooperator exclusion mechanism.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness


class PrivateScratchWindowScenario(str, Enum):
    NORMAL = "normal"
    PREIMAGE_DRIFT = "preimage_drift"
    STAGE_DRIFT = "stage_drift"


class PrivateScratchWindowState(str, Enum):
    SCRATCH_REPLACED_NONAUTHORIZING = "scratch_replaced_nonauthorizing"
    PREIMAGE_DRIFT_REFUSED = "preimage_drift_refused"
    STAGE_DRIFT_REFUSED = "stage_drift_refused"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    NATIVE_CUSTODY_REFUSED = "native_custody_refused"
    OBSERVATION_REFUSED = "observation_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateScratchWindowReview:
    state: PrivateScratchWindowState
    synthetic_parent_retained_during_window: bool = False
    cooperative_lock_held_during_window: bool = False
    preimage_rechecked_during_window: bool = False
    synthetic_replace_attempted: bool = False
    synthetic_postimage_verified: bool = False
    pending_synthetic_journal_preserved: bool = False
    production_mutation_admitted: bool = False
    operation_owned_production_guard_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    native_replace_postimage_production_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateScratchWindowReview(disposable_only=True, non_authorizing=True)"


def _answer(
    state: PrivateScratchWindowState,
    *,
    retained: bool = False,
    guarded: bool = False,
    checked: bool = False,
    attempted: bool = False,
    verified: bool = False,
    journal: bool = False,
) -> PrivateScratchWindowReview:
    return PrivateScratchWindowReview(
        state=state,
        synthetic_parent_retained_during_window=retained,
        cooperative_lock_held_during_window=guarded,
        preimage_rechecked_during_window=checked,
        synthetic_replace_attempted=attempted,
        synthetic_postimage_verified=verified,
        pending_synthetic_journal_preserved=journal,
    )


class _UnsafeScratch(Exception):
    """Sanitized in-scratch failure with no sensitive filesystem details."""


def _same_native_directory(path: Path, expected: tuple[int, int]) -> bool:
    """No user-supplied paths enter this private, diagnostic-only helper."""
    if sys.platform == "linux":
        observed = os.lstat(path)
        return (
            stat.S_ISDIR(observed.st_mode)
            and (observed.st_dev, observed.st_ino) == expected
        )
    if sys.platform == "win32":
        return _windows_identity(path) == expected
    return False


def _windows_identity(path: Path, *, held_handle: int | None = None) -> tuple[int, int]:
    """Native BY_HANDLE_FILE_INFORMATION identity, not a path-string check."""
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_time_low", wintypes.DWORD),
            ("creation_time_high", wintypes.DWORD),
            ("access_time_low", wintypes.DWORD),
            ("access_time_high", wintypes.DWORD),
            ("write_time_low", wintypes.DWORD),
            ("write_time_high", wintypes.DWORD),
            ("volume_serial", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    ]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = (
        held_handle
        if held_handle is not None
        else kernel.CreateFileW(
            str(path), 0x80, 0x7, None, 3, 0x02000000 | 0x00200000, None
        )
    )
    invalid = ctypes.c_void_p(-1).value
    if handle is None or int(handle) == invalid:
        raise _UnsafeScratch
    try:
        info = ByHandleFileInformation()
        if (
            not kernel.GetFileInformationByHandle(handle, ctypes.byref(info))
            or not (info.attributes & 0x10)
            or (info.attributes & 0x400)
        ):
            raise _UnsafeScratch
        return (
            int(info.volume_serial),
            (int(info.file_index_high) << 32) | int(info.file_index_low),
        )
    finally:
        if held_handle is None:
            kernel.CloseHandle(handle)


@contextmanager
def _retain_native_parent(path: Path) -> Iterator[None]:
    """Retain a Linux directory fd or Windows directory HANDLE for the window."""
    if sys.platform == "linux":
        flags = (
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            identity = (opened.st_dev, opened.st_ino)
            if not stat.S_ISDIR(opened.st_mode) or not _same_native_directory(
                path, identity
            ):
                raise _UnsafeScratch
            yield
            if not _same_native_directory(path, identity):
                raise _UnsafeScratch
        finally:
            os.close(descriptor)
        return
    if sys.platform == "win32":
        # The identity getter independently opens the same directory; retain
        # an original DIRECTORY HANDLE across the entire synthetic operation.
        from ctypes import wintypes

        kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateFileW(
            str(path), 0x80, 0x7, None, 3, 0x02000000 | 0x00200000, None
        )
        invalid = ctypes.c_void_p(-1).value
        if handle is None or int(handle) == invalid:
            raise _UnsafeScratch
        try:
            # On Windows a retained directory handle does not turn os.replace
            # into a handle-relative atomic compare-and-swap operation.
            first = _windows_identity(path, held_handle=handle)
            if _windows_identity(path) != first:
                raise _UnsafeScratch
            yield
            if (
                _windows_identity(path) != first
                or _windows_identity(path, held_handle=handle) != first
            ):
                raise _UnsafeScratch
        finally:
            kernel.CloseHandle(handle)
        return
    raise _UnsafeScratch


def _image(file: Path) -> bytes:
    info = os.lstat(file)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or not 1 <= info.st_size <= 1024
    ):
        raise _UnsafeScratch
    data = file.read_bytes()
    again = os.lstat(file)
    if len(data) != info.st_size or (info.st_dev, info.st_ino, info.st_size) != (
        again.st_dev,
        again.st_ino,
        again.st_size,
    ):
        raise _UnsafeScratch
    return data


def probe_disposable_native_writer_window(
    scenario: PrivateScratchWindowScenario,
) -> PrivateScratchWindowReview:
    """Exercise native parent custody and a SINGLE replacement in private scratch.

    The caller cannot supply a path or a writer callback. Even a successful
    scratch transition cannot authorize an analogous operation in the private
    registry because the actual owner/ACL, binding, journal, stage and recovery
    scope have not been qualified as an indivisible native transaction.
    """
    state = PrivateScratchWindowState
    if type(scenario) is not PrivateScratchWindowScenario:
        return _answer(state.INVALID_REQUEST_REFUSED)
    if sys.platform not in {"linux", "win32"}:
        return _answer(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _answer(state.OBSERVATION_REFUSED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g87_native_") as name:
            directory = Path(name)
            if directory.is_symlink() or not directory.is_dir():
                raise _UnsafeScratch
            if (
                sys.platform == "linux"
                and stat.S_IMODE(os.stat(directory).st_mode) != 0o700
            ):
                raise _UnsafeScratch
            registry = directory / "registry.json"
            stage = directory / "registry.stage"
            journal = directory / "pending-journal.json"
            lock = directory / ".registry.lock"
            registry.write_bytes(b"registry-before-v1")
            stage.write_bytes(b"registry-after-v2")
            journal.write_bytes(b"journal-pending")
            lock.write_bytes(b"0")
            if sys.platform == "linux":
                lock.chmod(0o600)
            with locking.hold_existing_private_lock(lock):
                with _retain_native_parent(directory):
                    if _image(journal) != b"journal-pending":
                        raise _UnsafeScratch
                    before = _image(registry)
                    after = _image(stage)
                    if before != b"registry-before-v1" or after != b"registry-after-v2":
                        raise _UnsafeScratch
                    if scenario is PrivateScratchWindowScenario.PREIMAGE_DRIFT:
                        registry.write_bytes(b"changed-preimage")
                    elif scenario is PrivateScratchWindowScenario.STAGE_DRIFT:
                        stage.write_bytes(b"changed-stage")
                    # All observations and the replacement are performed with
                    # the same live coordination lock and retained parent.
                    if _image(registry) != before:
                        return _answer(
                            state.PREIMAGE_DRIFT_REFUSED,
                            retained=True,
                            guarded=True,
                            checked=True,
                            journal=True,
                        )
                    if _image(stage) != after:
                        return _answer(
                            state.STAGE_DRIFT_REFUSED,
                            retained=True,
                            guarded=True,
                            checked=True,
                            journal=True,
                        )
                    os.replace(stage, registry)
                    verified = (
                        _image(registry) == after
                        and not stage.exists()
                        and _image(journal) == b"journal-pending"
                    )
                    if not verified:
                        return _answer(
                            state.NATIVE_CUSTODY_REFUSED,
                            retained=True,
                            guarded=True,
                            checked=True,
                            attempted=True,
                        )
                    return _answer(
                        state.SCRATCH_REPLACED_NONAUTHORIZING,
                        retained=True,
                        guarded=True,
                        checked=True,
                        attempted=True,
                        verified=True,
                        journal=True,
                    )
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        _UnsafeScratch,
    ):
        return _answer(state.NATIVE_CUSTODY_REFUSED)
