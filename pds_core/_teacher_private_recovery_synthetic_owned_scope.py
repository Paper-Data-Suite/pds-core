"""Operation-owned native directory custody during disposable replacement (#238 3G29).

This is an executable synthetic boundary, not a production recovery writer.
One module-owned TemporaryDirectory contains fixed, synthetic byte images. The
parent directory is kept open by a native FD/HANDLE across a real os.replace,
under one scratch advisory lock, and native parent identity is rechecked from
that held handle and independently reopened pathname at every boundary.

No caller path, byte image, proposed intent, callback or native handle enters.
This cannot establish production ACL/backing custody, hostile-writer exclusion,
portable directory durability, journal retirement, or Notes authority.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_recovery_writer_sequence as sequence


class PrivateOwnedScopeFault(str, Enum):
    NONE = "none"
    AFTER_GUARD = "after_guard"
    AFTER_PARENT_RETAINED = "after_parent_retained"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_READER_RELEASE = "after_reader_release"
    AFTER_FINAL_CHECK = "after_final_check"
    AFTER_REPLACE = "after_replace"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_FILE_SYNC = "after_file_sync"


class PrivateOwnedScopeState(str, Enum):
    SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED = (
        "scratch_replacement_observed_unqualified"
    )
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    PREIMAGE_REFUSED = "preimage_refused"
    PARENT_IDENTITY_CONFLICT_PRESERVE = "parent_identity_conflict_preserve"
    READER_CONFLICT_PRESERVE = "reader_conflict_preserve"
    ADMISSION_DRIFT_PRESERVE = "admission_drift_preserve"
    REPLACEMENT_REFUSED_PRESERVE = "replacement_refused_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    FILE_IDENTITY_CONFLICT_PRESERVE = "file_identity_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    NATIVE_GUARD_REFUSED = "native_guard_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateOwnedScopeState.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED: "Disposable replacement observed under one native scratch lock and retained parent handle; no production custody or durability.",
    PrivateOwnedScopeState.OPERATION_NOT_ADMITTED: "Only an existing synthetic stage-to-registry step is supported; no production action admitted.",
    PrivateOwnedScopeState.INVALID_REQUEST: "Only exact synthetic step and interruption enums are accepted.",
    PrivateOwnedScopeState.UNSUPPORTED: "Native scratch parent HANDLE custody is unavailable on this platform.",
    PrivateOwnedScopeState.PREIMAGE_REFUSED: "Synthetic prepared checkpoint is missing, changed or unqualified.",
    PrivateOwnedScopeState.PARENT_IDENTITY_CONFLICT_PRESERVE: "Native retained parent identity or independently reopened pathname drifted; preserve evidence.",
    PrivateOwnedScopeState.READER_CONFLICT_PRESERVE: "Restrictive reader observed unexpected image or file ID; preserve evidence.",
    PrivateOwnedScopeState.ADMISSION_DRIFT_PRESERVE: "Native scratch preimage drifted after reader release or before replacement.",
    PrivateOwnedScopeState.REPLACEMENT_REFUSED_PRESERVE: "Native scratch replacement was refused, without alternate execution authority.",
    PrivateOwnedScopeState.POSTIMAGE_CONFLICT_PRESERVE: "Synthetic postimage or stage namespace was inconsistent; preserve evidence.",
    PrivateOwnedScopeState.FILE_IDENTITY_CONFLICT_PRESERVE: "Native scratch file or guard identity changed unexpectedly; preserve evidence.",
    PrivateOwnedScopeState.INTERRUPTED_PRESERVE: "Synthetic operation was interrupted; no completion, replay or retirement claim.",
    PrivateOwnedScopeState.NATIVE_GUARD_REFUSED: "Native scratch advisory guard could not be acquired or released.",
    PrivateOwnedScopeState.IO_ERROR: "Synthetic native writer-owned scope encountered an I/O error.",
}


@dataclass(frozen=True, slots=True)
class PrivateOwnedScopeReview:
    """Sanitized non-authorizing result: never expose a path, HANDLE or image."""

    state: PrivateOwnedScopeState
    message: str


def _result(state: PrivateOwnedScopeState) -> PrivateOwnedScopeReview:
    return PrivateOwnedScopeReview(state, _MESSAGES[state])


class _ParentUnqualified(Exception):
    """Private native parent custody failed closed."""


class _InjectedInterruption(Exception):
    """Cooperative in-process interruption; not a real power outage."""


def _interrupt(selected: PrivateOwnedScopeFault, point: PrivateOwnedScopeFault) -> None:
    if selected is point:
        raise _InjectedInterruption


def _linux_identity(info: os.stat_result) -> tuple[int, int]:
    if (
        not stat.S_ISDIR(info.st_mode)
        or type(info.st_dev) is not int
        or type(info.st_ino) is not int
        or info.st_ino <= 0
    ):
        raise _ParentUnqualified
    return info.st_dev, info.st_ino


@contextmanager
def _held_native_parent(root: Path) -> Iterator[Callable[[], bool]]:
    """Keep the *directory* FD/HANDLE until after the final postimage check.

    This scope never owns the registry or journal and is deliberately confined
    to a disposable parent, distinct from the production retained guard.
    """
    if sys.platform == "linux":
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
            raise _ParentUnqualified
        fd = os.open(root, flags)
        try:
            expected = _linux_identity(os.fstat(fd))

            def matches() -> bool:
                try:
                    before = _linux_identity(root.lstat())
                    reopened = os.open(root, flags)
                    try:
                        opened = _linux_identity(os.fstat(reopened))
                    finally:
                        os.close(reopened)
                    return (
                        before == expected
                        and opened == expected
                        and _linux_identity(os.fstat(fd)) == expected
                        and _linux_identity(root.lstat()) == expected
                    )
                except (OSError, ValueError, TypeError, _ParentUnqualified):
                    return False

            if not matches():
                raise _ParentUnqualified
            yield matches
        finally:
            os.close(fd)
        return
    if sys.platform != "win32":
        raise _ParentUnqualified
    kernel = descriptor._windows_api()
    held, error = anchor._windows_open(kernel, root)
    if held is None:
        raise _ParentUnqualified from OSError(
            error, "Scratch native parent open refused"
        )
    try:
        expected = anchor._windows_id(kernel, held)
        info = descriptor._windows_info(kernel, held)
        if (
            expected is None
            or not any(expected[1])
            or info is None
            or not info[1].directory
            or info[1].delete_pending
            or bool(info[0] & 0x400)
        ):
            raise _ParentUnqualified

        def matches() -> bool:
            try:
                if anchor._windows_id(kernel, held) != expected:
                    return False
                current, _error = anchor._windows_open(kernel, root)
                if current is None:
                    return False
                try:
                    opened = descriptor._windows_info(kernel, current)
                    return (
                        anchor._windows_id(kernel, current) == expected
                        and opened is not None
                        and bool(opened[1].directory)
                        and not opened[1].delete_pending
                        and not bool(opened[0] & 0x400)
                        and anchor._windows_id(kernel, held) == expected
                    )
                finally:
                    kernel.CloseHandle(wintypes.HANDLE(current))
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                return False

        if not matches():
            raise _ParentUnqualified
        yield matches
    finally:
        kernel.CloseHandle(wintypes.HANDLE(held))


def _preimage(
    root: Path,
    before: identity._IdentitySet,
    lock_id: identity._FileID,
    parent: tuple[int, int],
    still_owned: Callable[[], bool],
) -> bool:
    return still_owned() and admission._starting(root, before, lock_id, parent)


def _postimage(
    root: Path,
    before: identity._IdentitySet,
    lock_id: identity._FileID,
    parent: tuple[int, int],
    still_owned: Callable[[], bool],
) -> PrivateOwnedScopeState | None:
    state = PrivateOwnedScopeState
    if not still_owned():
        return state.PARENT_IDENTITY_CONFLICT_PRESERVE
    conflict = admission._postimage(root, before, lock_id, parent)
    if conflict is admission.PrivateScratchWriterState.POSTIMAGE_CONFLICT_PRESERVE:
        return state.POSTIMAGE_CONFLICT_PRESERVE
    if conflict is not None:
        return state.FILE_IDENTITY_CONFLICT_PRESERVE
    return None


def rehearse_synthetic_native_writer_owned_scope(
    step: admission.PrivateScratchWriterStep = admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
    interruption: PrivateOwnedScopeFault = PrivateOwnedScopeFault.NONE,
) -> PrivateOwnedScopeReview:
    """Run one native scratch stage replacement with retained parent custody.

    The positive state never authorizes protected mutation; the in-process
    directory handle and advisory lock cannot be transferred out of this call.
    """
    state = PrivateOwnedScopeState
    fault = PrivateOwnedScopeFault
    phase = sequence.PrivateRecoveryWriterPhase
    if (
        type(step) is not admission.PrivateScratchWriterStep
        or type(interruption) is not fault
    ):
        return _result(state.INVALID_REQUEST)
    if step is not admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    phases: list[sequence.PrivateRecoveryWriterPhase] = []
    attempted = False
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g29_scope_") as temporary:
            root = Path(temporary)
            scratch._write_new(root, scratch._REGISTRY, scratch._BEFORE)
            scratch._write_new(root, scratch._STAGE, scratch._AFTER)
            scratch._write_new(root, "descriptor.json", scratch._DESCRIPTOR)
            scratch._write_new(root, "transactions.json", scratch._JOURNAL)
            with scratch._scratch_lock(root / scratch._LOCK):
                phases.append(phase.GUARD_ACQUIRED)
                _interrupt(interruption, fault.AFTER_GUARD)
                with _held_native_parent(root) as still_owned:
                    if not still_owned():
                        return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_PARENT_RETAINED)
                    if not scratch._expected(root, stage=True):
                        return _result(state.PREIMAGE_REFUSED)
                    before = identity._identities(root, stage=True)
                    lock_id = identity._identity(root, scratch._LOCK)
                    parent = admission._parent_id(root)
                    if before[3] is None or before[3] == before[0]:
                        return _result(state.PREIMAGE_REFUSED)
                    if not _preimage(root, before, lock_id, parent, still_owned):
                        return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_PREIMAGE)
                    if not admission._read_once(
                        root, before[0], admission.PrivateScratchWriterFault.NONE
                    ):
                        return _result(state.READER_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_READER_RELEASE)
                    for _ in range(3):
                        if not still_owned():
                            return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
                        if not _preimage(root, before, lock_id, parent, still_owned):
                            return _result(state.ADMISSION_DRIFT_PRESERVE)
                    phases.append(phase.PREIMAGE_REVALIDATED)
                    _interrupt(interruption, fault.AFTER_FINAL_CHECK)
                    if not still_owned():
                        return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
                    phases.append(phase.OPERATION_INVOKED)
                    attempted = True
                    try:
                        os.replace(root / scratch._STAGE, root / scratch._REGISTRY)
                    except OSError as error:
                        if isinstance(error, PermissionError) or getattr(
                            error, "winerror", None
                        ) in (5, 32, 33):
                            return _result(state.REPLACEMENT_REFUSED_PRESERVE)
                        raise
                    phases.append(phase.OPERATION_RETURNED)
                    _interrupt(interruption, fault.AFTER_REPLACE)
                    conflict = _postimage(root, before, lock_id, parent, still_owned)
                    if conflict is not None:
                        return _result(conflict)
                    phases.append(phase.POSTIMAGE_REVALIDATED)
                    _interrupt(interruption, fault.AFTER_POSTIMAGE)
                    scratch._sync_target(root)
                    phases.append(phase.PERSISTENCE_REQUESTED)
                    _interrupt(interruption, fault.AFTER_FILE_SYNC)
                    conflict = _postimage(root, before, lock_id, parent, still_owned)
                    if conflict is not None or not sequence._ordered(tuple(phases)):
                        return _result(conflict or state.POSTIMAGE_CONFLICT_PRESERVE)
                    if not still_owned():
                        return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
            phases.append(phase.GUARD_RELEASED)
            if not sequence._ordered(tuple(phases)):
                return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
            return _result(state.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED)
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except scratch._GuardRefused:
        return _result(state.NATIVE_GUARD_REFUSED)
    except _ParentUnqualified:
        return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
    except admission._ParentUnqualified:
        return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
    except identity._IdentityUnavailable:
        return _result(
            state.FILE_IDENTITY_CONFLICT_PRESERVE
            if attempted
            else state.PREIMAGE_REFUSED
        )
    except (scratch._UnsafeImage, FileNotFoundError):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE if attempted else state.PREIMAGE_REFUSED
        )
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(state.IO_ERROR)
