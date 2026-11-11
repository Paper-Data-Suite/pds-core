"""Disposable two-document native flush-ordering drill (Core #238 Slice 3G48).

This is deliberately NOT a production writer. All paths, bytes, locks, and
replacement names are generated inside a fresh TemporaryDirectory. It exercises
file and parent-directory flush *requests* around registry and descriptor
replacements while leaving the pending journal in place. The result cannot
certify power-loss durability, OS-owner protection, a multi-file atomic commit,
recovery, or journal retirement. Unsupported directory flushing fails closed.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


class PrivateDurableScratchFault(str, Enum):
    NONE = "none"
    AFTER_PREPARED_FLUSH = "after_prepared_flush"
    BEFORE_REGISTRY_REPLACE = "before_registry_replace"
    AFTER_REGISTRY_REPLACE = "after_registry_replace"
    AFTER_REGISTRY_FLUSH = "after_registry_flush"
    AFTER_REGISTRY_DIRECTORY_FLUSH = "after_registry_directory_flush"
    BEFORE_DESCRIPTOR_REPLACE = "before_descriptor_replace"
    AFTER_DESCRIPTOR_REPLACE = "after_descriptor_replace"
    AFTER_DESCRIPTOR_FLUSH = "after_descriptor_flush"
    AFTER_DESCRIPTOR_DIRECTORY_FLUSH = "after_descriptor_directory_flush"


class PrivateDurableScratchState(str, Enum):
    SCRATCH_FLUSH_SEQUENCE_OBSERVED_UNQUALIFIED = (
        "scratch_flush_sequence_observed_unqualified"
    )
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    PREPARED_IMAGE_CONFLICT_PRESERVE = "prepared_image_conflict_preserve"
    PRE_ATTEMPT_INTERRUPTED_PRESERVE = "pre_attempt_interrupted_preserve"
    POST_ATTEMPT_UNKNOWN_PRESERVE = "post_attempt_unknown_preserve"
    DIRECTORY_FLUSH_UNQUALIFIED_PRESERVE = "directory_flush_unqualified_preserve"
    FILE_FLUSH_REFUSED_PRESERVE = "file_flush_refused_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    GUARD_REFUSED_PRESERVE = "guard_refused_preserve"
    IO_ERROR_PRESERVE = "io_error_preserve"


_MESSAGES: dict[PrivateDurableScratchState, str] = {
    item: "Disposable native durability drill refused; no production completion authority."
    for item in PrivateDurableScratchState
}
_MESSAGES[PrivateDurableScratchState.SCRATCH_FLUSH_SEQUENCE_OBSERVED_UNQUALIFIED] = (
    "Disposable stage/journal and both metadata after-images received file and "
    "directory flush requests; no power-loss or production-commit proof."
)
_MESSAGES[PrivateDurableScratchState.DIRECTORY_FLUSH_UNQUALIFIED_PRESERVE] = (
    "A native parent-directory flush could not be qualified; preserve pending evidence."
)
_MESSAGES[PrivateDurableScratchState.POST_ATTEMPT_UNKNOWN_PRESERVE] = (
    "A replacement may have occurred; preserve the pending journal and never retry blindly."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDurableScratchReview:
    state: PrivateDurableScratchState
    message: str
    replacement_may_have_occurred: bool
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    journal_retirement_forbidden: bool = True
    flush_order: tuple[str, ...] = field(default=(), repr=False)

    def __repr__(self) -> str:
        return "PrivateDurableScratchReview(non_authorizing=True)"


def _result(
    state: PrivateDurableScratchState,
    attempted: bool = False,
    events: tuple[str, ...] = (),
) -> PrivateDurableScratchReview:
    return PrivateDurableScratchReview(
        state, _MESSAGES[state], attempted, True, True, True, events
    )


class _Interrupted(Exception):
    pass


class _DirectoryFlushRefused(Exception):
    pass


class _FileFlushRefused(Exception):
    pass


class _GuardRefused(Exception):
    pass


class _ImageRefused(Exception):
    pass


# Synthetic, fixed bytes. Never load actual registry or teacher data here.
_REG_BEFORE = b"synthetic-private-registry-revision-2\n"
_REG_AFTER = b"synthetic-private-registry-revision-3\n"
_DESC_BEFORE = b"synthetic-association-before\n"
_DESC_AFTER = b"synthetic-association-after\n"
_JOURNAL = b"synthetic-pending-transaction-keep-for-recovery\n"


def _write_new(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)


def _exact(path: Path, content: bytes) -> bool:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return False
        with path.open("rb") as stream:
            return stream.read(len(content) + 1) == content
    except OSError:
        return False


def _file_flush(path: Path) -> None:
    try:
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
    except OSError as exc:
        raise _FileFlushRefused from exc


def _linux_directory_flush(path: Path) -> None:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise _DirectoryFlushRefused
    fd: int | None = None
    try:
        start = path.lstat()
        if not stat.S_ISDIR(start.st_mode):
            raise _DirectoryFlushRefused
        fd = os.open(path, os.O_RDONLY | nofollow | directory)
        held = os.fstat(fd)
        if (start.st_dev, start.st_ino) != (held.st_dev, held.st_ino):
            raise _DirectoryFlushRefused
        os.fsync(fd)
        end = os.fstat(fd)
        reopened = path.lstat()
        if (
            not stat.S_ISDIR(end.st_mode)
            or not stat.S_ISDIR(reopened.st_mode)
            or (held.st_dev, held.st_ino) != (end.st_dev, end.st_ino)
            or (held.st_dev, held.st_ino) != (reopened.st_dev, reopened.st_ino)
        ):
            raise _DirectoryFlushRefused
    except (OSError, ValueError, OverflowError) as exc:
        raise _DirectoryFlushRefused from exc
    finally:
        if fd is not None:
            os.close(fd)


def _windows_directory_flush(path: Path) -> None:
    """Try an actual Windows directory flush; never substitute a file flush.

    Windows may refuse FlushFileBuffers on directory handles, even on local
    NTFS. Report unsupported instead of claiming directory-entry durability.
    """
    kernel: Any = None
    handle: int | None = None
    try:
        kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        raw = create(
            str(path),
            0x40000000 | 0x80,
            7,
            None,
            3,
            0x02000000 | 0x00200000,
            None,
        )
        handle = ctypes.cast(raw, ctypes.c_void_p).value
        if handle is None or handle == ctypes.c_void_p(-1).value:
            handle = None
            raise _DirectoryFlushRefused
        flush = kernel.FlushFileBuffers
        flush.argtypes = [wintypes.HANDLE]
        flush.restype = wintypes.BOOL
        if not flush(wintypes.HANDLE(handle)):
            raise _DirectoryFlushRefused
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise _DirectoryFlushRefused from exc
    finally:
        if kernel is not None and handle is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle))


def _directory_flush(path: Path) -> None:
    if sys.platform == "linux":
        _linux_directory_flush(path)
    elif sys.platform == "win32":
        _windows_directory_flush(path)
    else:
        raise _DirectoryFlushRefused


@contextmanager
def _scratch_lock(path: Path) -> Iterator[None]:
    """Synthetic guard; body errors are NOT lock-acquisition failures."""
    with path.open("x+b") as stream:
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            elif sys.platform == "linux":
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                raise _GuardRefused
        except (BlockingIOError, PermissionError) as exc:
            raise _GuardRefused from exc
        try:
            yield
        finally:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except OSError as exc:
                raise _GuardRefused from exc


def _interrupt(
    selected: PrivateDurableScratchFault, at: PrivateDurableScratchFault
) -> None:
    if selected is at:
        raise _Interrupted


def rehearse_synthetic_two_document_flush_order(
    interruption: PrivateDurableScratchFault = PrivateDurableScratchFault.NONE,
) -> PrivateDurableScratchReview:
    """Run one two-document transaction flush drill on exclusively owned scratch.

    The existing registry, pending journal and stage are *synthetic* and all
    created here. Crash injection is in-process only. A success means only that
    OS flush requests returned, not that they survived an actual power loss.
    """
    state = PrivateDurableScratchState
    fault = PrivateDurableScratchFault
    if type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    attempted = False
    events: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g48_durable_") as temp:
            private = Path(temp) / "private"
            transactions = private / "transactions"
            descriptor_dir = Path(temp) / "workspace" / ".pds"
            transactions.mkdir(parents=True)
            descriptor_dir.mkdir(parents=True)
            registry = private / "registry.json"
            registry_stage = private / ".synthetic.registry-stage"
            journal = transactions / "synthetic-pending.json"
            descriptor = descriptor_dir / "teacher-private-association.json"
            descriptor_stage = descriptor_dir / ".synthetic.descriptor-stage"
            _write_new(registry, _REG_BEFORE)
            _write_new(registry_stage, _REG_AFTER)
            _write_new(journal, _JOURNAL)
            _write_new(descriptor, _DESC_BEFORE)
            _write_new(descriptor_stage, _DESC_AFTER)
            with _scratch_lock(private / ".native-lock"):
                if not all(
                    _exact(path, data)
                    for path, data in (
                        (registry, _REG_BEFORE),
                        (registry_stage, _REG_AFTER),
                        (journal, _JOURNAL),
                        (descriptor, _DESC_BEFORE),
                        (descriptor_stage, _DESC_AFTER),
                    )
                ):
                    return _result(state.PREPARED_IMAGE_CONFLICT_PRESERVE)
                # Persist the prepared intent, both stage contents and each
                # containing namespace BEFORE any replacement is attempted.
                for label, path in (
                    ("journal_file", journal),
                    ("registry_stage_file", registry_stage),
                    ("descriptor_stage_file", descriptor_stage),
                ):
                    _file_flush(path)
                    events.append(label)
                for label, path in (
                    ("journal_directory", transactions),
                    ("registry_prepared_directory", private),
                    ("descriptor_prepared_directory", descriptor_dir),
                ):
                    _directory_flush(path)
                    events.append(label)
                _interrupt(interruption, fault.AFTER_PREPARED_FLUSH)
                if not _exact(registry, _REG_BEFORE) or not _exact(journal, _JOURNAL):
                    return _result(state.PREPARED_IMAGE_CONFLICT_PRESERVE)
                _interrupt(interruption, fault.BEFORE_REGISTRY_REPLACE)
                attempted = True
                os.replace(registry_stage, registry)
                events.append("registry_replace")
                _interrupt(interruption, fault.AFTER_REGISTRY_REPLACE)
                if not _exact(registry, _REG_AFTER) or registry_stage.exists():
                    return _result(
                        state.POSTIMAGE_CONFLICT_PRESERVE, attempted, tuple(events)
                    )
                _file_flush(registry)
                events.append("registry_file")
                _interrupt(interruption, fault.AFTER_REGISTRY_FLUSH)
                _directory_flush(private)
                events.append("registry_directory")
                _interrupt(interruption, fault.AFTER_REGISTRY_DIRECTORY_FLUSH)
                if not _exact(journal, _JOURNAL) or not _exact(
                    descriptor, _DESC_BEFORE
                ):
                    return _result(
                        state.POSTIMAGE_CONFLICT_PRESERVE, attempted, tuple(events)
                    )
                _interrupt(interruption, fault.BEFORE_DESCRIPTOR_REPLACE)
                os.replace(descriptor_stage, descriptor)
                events.append("descriptor_replace")
                _interrupt(interruption, fault.AFTER_DESCRIPTOR_REPLACE)
                if not _exact(descriptor, _DESC_AFTER) or descriptor_stage.exists():
                    return _result(
                        state.POSTIMAGE_CONFLICT_PRESERVE, attempted, tuple(events)
                    )
                _file_flush(descriptor)
                events.append("descriptor_file")
                _interrupt(interruption, fault.AFTER_DESCRIPTOR_FLUSH)
                _directory_flush(descriptor_dir)
                events.append("descriptor_directory")
                _interrupt(interruption, fault.AFTER_DESCRIPTOR_DIRECTORY_FLUSH)
                if not (
                    _exact(registry, _REG_AFTER)
                    and _exact(descriptor, _DESC_AFTER)
                    and _exact(journal, _JOURNAL)
                    and not registry_stage.exists()
                    and not descriptor_stage.exists()
                ):
                    return _result(
                        state.POSTIMAGE_CONFLICT_PRESERVE, attempted, tuple(events)
                    )
            return _result(
                state.SCRATCH_FLUSH_SEQUENCE_OBSERVED_UNQUALIFIED,
                attempted,
                tuple(events),
            )
    except _DirectoryFlushRefused:
        return _result(
            state.DIRECTORY_FLUSH_UNQUALIFIED_PRESERVE, attempted, tuple(events)
        )
    except _FileFlushRefused:
        return _result(state.FILE_FLUSH_REFUSED_PRESERVE, attempted, tuple(events))
    except _GuardRefused:
        return _result(state.GUARD_REFUSED_PRESERVE, attempted, tuple(events))
    except (_Interrupted, KeyboardInterrupt):
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE
            if attempted
            else state.PRE_ATTEMPT_INTERRUPTED_PRESERVE,
            attempted,
            tuple(events),
        )
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE
            if attempted
            else state.IO_ERROR_PRESERVE,
            attempted,
            tuple(events),
        )
