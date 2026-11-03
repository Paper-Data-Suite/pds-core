"""Disposable, native-locked filesystem rehearsal for Core #238 Slice 3G19.

The entry point creates its own isolated synthetic scratch directory. It
accepts NO private metadata, filesystem path, caller callback, handle or writer
permit. A real local os.replace occurs under an exclusive advisory native lock,
followed by exact image checks and a bounded file-sync request. Deliberate
interruption injection exercises fail-closed observations. This cannot prove
teacher-private native guard custody, distributed CAS, directory durability,
crash recovery, or permission to mutate production metadata.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

from pds_core import _teacher_private_recovery_writer_sequence as sequence


class PrivateSyntheticWriterInterruption(str, Enum):
    NONE = "none"
    AFTER_GUARD = "after_guard"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_NATIVE_REPLACE = "after_native_replace"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_FILE_SYNC = "after_file_sync"


class PrivateSyntheticWriterState(str, Enum):
    PERSISTENCE_UNQUALIFIED = "persistence_unqualified"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    PREIMAGE_REFUSED = "preimage_refused"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    NATIVE_GUARD_REFUSED = "native_guard_refused"
    IO_ERROR = "io_error"
    UNSUPPORTED = "unsupported"
    INVALID_REQUEST = "invalid_request"


_MESSAGES = {
    PrivateSyntheticWriterState.PERSISTENCE_UNQUALIFIED: (
        "Synthetic native replacement and exact postimage checks completed under a "
        "scratch lock; filesystem durability and production custody remain unqualified."
    ),
    PrivateSyntheticWriterState.INTERRUPTED_PRESERVE: (
        "Controlled synthetic interruption; no production action or durability claim."
    ),
    PrivateSyntheticWriterState.PREIMAGE_REFUSED: (
        "Synthetic starting images or isolated namespace did not match expectations."
    ),
    PrivateSyntheticWriterState.POSTIMAGE_CONFLICT_PRESERVE: (
        "Synthetic native operation returned but exact postimages were unqualified."
    ),
    PrivateSyntheticWriterState.NATIVE_GUARD_REFUSED: (
        "Synthetic native advisory guard could not be acquired or released."
    ),
    PrivateSyntheticWriterState.IO_ERROR: (
        "Synthetic native filesystem rehearsal could not complete safely."
    ),
    PrivateSyntheticWriterState.UNSUPPORTED: (
        "Native synthetic writer rehearsal is unsupported on this platform."
    ),
    PrivateSyntheticWriterState.INVALID_REQUEST: (
        "Synthetic rehearsal accepts only a defined interruption injection."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateSyntheticWriterReview:
    """Only a sanitized result; no paths, bytes, handles or capabilities."""

    state: PrivateSyntheticWriterState
    message: str


def _result(state: PrivateSyntheticWriterState) -> PrivateSyntheticWriterReview:
    return PrivateSyntheticWriterReview(state, _MESSAGES[state])


class _InjectedInterruption(Exception):
    """Controlled test interruption, not an actual process crash."""


class _GuardRefused(Exception):
    pass


class _UnsafeImage(Exception):
    pass


# Fixed literals: the module never copies a real registry, journal or descriptor.
_BEFORE = b"synthetic-registry-before\n"
_AFTER = b"synthetic-registry-after\n"
_DESCRIPTOR = b"synthetic-descriptor-before\n"
_JOURNAL = b"synthetic-journal-pending\n"
_STAGE = ".synthetic.registry-stage"
_REGISTRY = "registry.json"
_LOCK = ".synthetic.lock"
_PHASES = sequence.PrivateRecoveryWriterPhase


def _write_new(root: Path, filename: str, value: bytes) -> None:
    path = root / filename
    with path.open("xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _exact_regular(root: Path, name: str, expected: bytes) -> bool:
    path = root / name
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise _UnsafeImage
    # A bounded, exact read; no untrusted payloads enter this rehearsal.
    with path.open("rb") as stream:
        content = stream.read(len(expected) + 1)
    return content == expected


def _namespace(root: Path, *, stage: bool) -> bool:
    expected = {_REGISTRY, "descriptor.json", "transactions.json", _LOCK}
    if stage:
        expected.add(_STAGE)
    return {part.name for part in root.iterdir()} == expected and not any(
        part.is_symlink() for part in root.iterdir()
    )


def _expected(root: Path, *, stage: bool) -> bool:
    return (
        _namespace(root, stage=stage)
        and _exact_regular(root, _REGISTRY, _BEFORE if stage else _AFTER)
        and _exact_regular(root, "descriptor.json", _DESCRIPTOR)
        and _exact_regular(root, "transactions.json", _JOURNAL)
        and (
            _exact_regular(root, _STAGE, _AFTER)
            if stage
            else not (root / _STAGE).exists()
        )
    )


@contextmanager
def _scratch_lock(path: Path) -> Iterator[None]:
    """Lock a single synthetic byte throughout all pre/replace/post checks."""
    with path.open("w+b") as stream:
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        locked = False
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            elif sys.platform == "linux":
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                raise _GuardRefused
            locked = True
            yield
        except (BlockingIOError, PermissionError) as error:
            raise _GuardRefused from error
        finally:
            if locked:
                try:
                    if sys.platform == "win32":
                        import msvcrt

                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except OSError as error:
                    raise _GuardRefused from error


def _interrupt(
    selected: PrivateSyntheticWriterInterruption,
    at: PrivateSyntheticWriterInterruption,
) -> None:
    if selected is at:
        raise _InjectedInterruption


def _sync_target(root: Path) -> None:
    # File-only sync request; DOES NOT prove durable directory entry or crash safety.
    with (root / _REGISTRY).open("r+b") as stream:
        os.fsync(stream.fileno())


def rehearse_synthetic_private_native_replace(
    interruption: PrivateSyntheticWriterInterruption = PrivateSyntheticWriterInterruption.NONE,
) -> PrivateSyntheticWriterReview:
    """Perform ONE real native replacement on module-owned disposable bytes.

    All traces and locks remain internal. No caller paths, bytes, callback,
    journal retirement, teacher-private data or transaction capability accepted.
    An injected interruption never grants a completed-operation outcome.
    """
    state = PrivateSyntheticWriterState
    if type(interruption) is not PrivateSyntheticWriterInterruption:
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    phases: list[sequence.PrivateRecoveryWriterPhase] = []
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g19_synthetic_") as tmp:
            root = Path(tmp)
            _write_new(root, _REGISTRY, _BEFORE)
            _write_new(root, _STAGE, _AFTER)
            _write_new(root, "descriptor.json", _DESCRIPTOR)
            _write_new(root, "transactions.json", _JOURNAL)
            with _scratch_lock(root / _LOCK):
                phases.append(_PHASES.GUARD_ACQUIRED)
                _interrupt(interruption, PrivateSyntheticWriterInterruption.AFTER_GUARD)
                if not _expected(root, stage=True):
                    return _result(state.PREIMAGE_REFUSED)
                phases.append(_PHASES.PREIMAGE_REVALIDATED)
                _interrupt(
                    interruption, PrivateSyntheticWriterInterruption.AFTER_PREIMAGE
                )
                phases.append(_PHASES.OPERATION_INVOKED)
                os.replace(root / _STAGE, root / _REGISTRY)
                phases.append(_PHASES.OPERATION_RETURNED)
                _interrupt(
                    interruption,
                    PrivateSyntheticWriterInterruption.AFTER_NATIVE_REPLACE,
                )
                if not _expected(root, stage=False):
                    return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
                phases.append(_PHASES.POSTIMAGE_REVALIDATED)
                _interrupt(
                    interruption, PrivateSyntheticWriterInterruption.AFTER_POSTIMAGE
                )
                _sync_target(root)
                phases.append(_PHASES.PERSISTENCE_REQUESTED)
                _interrupt(
                    interruption, PrivateSyntheticWriterInterruption.AFTER_FILE_SYNC
                )
                if not _expected(root, stage=False):
                    return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
                if not sequence._ordered(tuple(phases)):
                    return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
            phases.append(_PHASES.GUARD_RELEASED)
            if not sequence._ordered(tuple(phases)):
                return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
            return _result(state.PERSISTENCE_UNQUALIFIED)
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except _GuardRefused:
        return _result(state.NATIVE_GUARD_REFUSED)
    except (_UnsafeImage, FileNotFoundError):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE
            if _PHASES.OPERATION_RETURNED in phases
            else state.PREIMAGE_REFUSED
        )
    except (OSError, ValueError, TypeError, OverflowError):
        return _result(state.IO_ERROR)
