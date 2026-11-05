"""Single-scope synthetic recovery writer admission rehearsal (Core #238 3G27).

One fixed stage-to-registry operation may run ONLY on module-owned disposable
bytes inside a native scratch advisory lock. The restrictive registry reader
is closed before the final native preimage/identity check and real replacement.
This never accepts a teacher path, content, native handle, callback or token.
No positive state proves production custody, durable directory persistence,
protected CAS, a safe restart, journal retirement or Notes availability.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from pds_core import _teacher_private_recovery_reader_release_window as reader
from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_writer_sequence as sequence


class PrivateScratchWriterStep(str, Enum):
    STAGE_TO_REGISTRY = "stage_to_registry"
    INITIALIZE = "initialize"
    DESCRIPTOR_COMPLETION = "descriptor_completion"
    JOURNAL_RETIREMENT = "journal_retirement"


class PrivateScratchWriterFault(str, Enum):
    NONE = "none"
    AFTER_GUARD = "after_guard"
    AFTER_PREIMAGE = "after_preimage"
    WHILE_READER_HELD = "while_reader_held"
    AFTER_READER_RELEASE = "after_reader_release"
    AFTER_FINAL_ADMISSION = "after_final_admission"
    AFTER_REPLACE = "after_replace"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_FILE_SYNC = "after_file_sync"


class PrivateScratchWriterState(str, Enum):
    REPLACEMENT_OBSERVED_PERSISTENCE_UNQUALIFIED = (
        "replacement_observed_persistence_unqualified"
    )
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    PREIMAGE_REFUSED = "preimage_refused"
    READER_CONFLICT_PRESERVE = "reader_conflict_preserve"
    ADMISSION_DRIFT_PRESERVE = "admission_drift_preserve"
    REPLACEMENT_REFUSED_PRESERVE = "replacement_refused_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    IDENTITY_CONFLICT_PRESERVE = "identity_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateScratchWriterState.REPLACEMENT_OBSERVED_PERSISTENCE_UNQUALIFIED: "Scratch stage replacement, bounded postimage and file sync request observed; no production authority or durability.",
    PrivateScratchWriterState.OPERATION_NOT_ADMITTED: "Only an existing synthetic stage-to-registry operation is admitted; initialization, descriptor completion and journal retirement refused.",
    PrivateScratchWriterState.INVALID_REQUEST: "Only exact synthetic operation and interruption enum values are accepted.",
    PrivateScratchWriterState.UNSUPPORTED: "Native scratch writer admission unsupported on this platform.",
    PrivateScratchWriterState.PREIMAGE_REFUSED: "Synthetic namespace, starting bytes or native identities unqualified.",
    PrivateScratchWriterState.READER_CONFLICT_PRESERVE: "Restrictive scratch reader returned unexpected contents or identity.",
    PrivateScratchWriterState.ADMISSION_DRIFT_PRESERVE: "Scratch starting evidence changed after reader observation or before replacement.",
    PrivateScratchWriterState.REPLACEMENT_REFUSED_PRESERVE: "Native scratch replace was refused; pending stage evidence must be preserved.",
    PrivateScratchWriterState.POSTIMAGE_CONFLICT_PRESERVE: "Scratch postimage bytes, stage absence or operation sequence conflicted.",
    PrivateScratchWriterState.IDENTITY_CONFLICT_PRESERVE: "Scratch parent, guard, registry, descriptor or journal identity conflicted.",
    PrivateScratchWriterState.INTERRUPTED_PRESERVE: "Synthetic operation interrupted; no completion or retry permission.",
    PrivateScratchWriterState.GUARD_REFUSED: "Native scratch advisory guard was refused or could not release.",
    PrivateScratchWriterState.IO_ERROR: "Synthetic native writer admission could not complete reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateScratchWriterReview:
    """Sanitized status only: no bytes, paths, handles or write capabilities."""

    state: PrivateScratchWriterState
    message: str


def _result(state: PrivateScratchWriterState) -> PrivateScratchWriterReview:
    return PrivateScratchWriterReview(state, _MESSAGES[state])


class _InjectedInterruption(Exception):
    pass


class _ParentUnqualified(Exception):
    pass


def _interrupt(
    selected: PrivateScratchWriterFault, point: PrivateScratchWriterFault
) -> None:
    if selected is point:
        raise _InjectedInterruption


def _parent_id(root: Path) -> tuple[int, int]:
    before = root.lstat()
    after = root.lstat()
    if (
        not stat.S_ISDIR(before.st_mode)
        or not stat.S_ISDIR(after.st_mode)
        or type(before.st_dev) is not int
        or type(before.st_ino) is not int
        or before.st_ino <= 0
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise _ParentUnqualified
    return before.st_dev, before.st_ino


def _starting(
    root: Path,
    expected: identity._IdentitySet,
    lock_id: identity._FileID,
    parent: tuple[int, int],
) -> bool:
    """Exact scratch preimage and all existing IDs must still match."""
    return (
        _parent_id(root) == parent
        and scratch._expected(root, stage=True)
        and identity._identities(root, stage=True) == expected
        and identity._identity(root, scratch._LOCK) == lock_id
    )


def _reader_good(stream: BinaryIO, old: identity._FileID) -> bool:
    """Use the existing held-file checker, not only pathname observations."""
    return reader._held_before(stream, old)


def _read_once(
    root: Path, old: identity._FileID, interruption: PrivateScratchWriterFault
) -> bool:
    path = root / scratch._REGISTRY
    # On Win32 use the EXACT restrictive CreateFileW mask rehearsed in 3G26.
    # No registry reader handle survives this function on either platform.
    if sys.platform == "win32":
        with reader._restrictive_reader(path) as stream:
            good = _reader_good(stream, old)
            _interrupt(interruption, PrivateScratchWriterFault.WHILE_READER_HELD)
            return good
    with path.open("rb") as stream:
        good = _reader_good(stream, old)
        _interrupt(interruption, PrivateScratchWriterFault.WHILE_READER_HELD)
        return good


def _postimage(
    root: Path,
    before: identity._IdentitySet,
    lock_id: identity._FileID,
    parent: tuple[int, int],
) -> PrivateScratchWriterState | None:
    state = PrivateScratchWriterState
    if not scratch._expected(root, stage=False):
        return state.POSTIMAGE_CONFLICT_PRESERVE
    after = identity._identities(root, stage=False)
    if _parent_id(root) != parent or identity._identity(root, scratch._LOCK) != lock_id:
        return state.IDENTITY_CONFLICT_PRESERVE
    if (
        before[3] is None
        or after[0] != before[3]
        or after[0] == before[0]
        or after[1:] != (before[1], before[2], None)
    ):
        return state.IDENTITY_CONFLICT_PRESERVE
    return None


def rehearse_synthetic_writer_owned_admission(
    step: PrivateScratchWriterStep = PrivateScratchWriterStep.STAGE_TO_REGISTRY,
    interruption: PrivateScratchWriterFault = PrivateScratchWriterFault.NONE,
) -> PrivateScratchWriterReview:
    """Admit and observe one native synthetic replace in one held scratch scope.

    No caller filesystem path, byte image, proposed transaction or callback is
    accepted. Positive result merely witnesses in-process disposable behavior.
    """
    state = PrivateScratchWriterState
    fault = PrivateScratchWriterFault
    if type(step) is not PrivateScratchWriterStep or type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if step is not PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in ("linux", "win32"):
        return _result(state.UNSUPPORTED)
    phase = sequence.PrivateRecoveryWriterPhase
    phases: list[sequence.PrivateRecoveryWriterPhase] = []
    reached_operation = False
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g27_admission_") as temporary:
            root = Path(temporary)
            scratch._write_new(root, scratch._REGISTRY, scratch._BEFORE)
            scratch._write_new(root, scratch._STAGE, scratch._AFTER)
            scratch._write_new(root, "descriptor.json", scratch._DESCRIPTOR)
            scratch._write_new(root, "transactions.json", scratch._JOURNAL)
            with scratch._scratch_lock(root / scratch._LOCK):
                phases.append(phase.GUARD_ACQUIRED)
                _interrupt(interruption, fault.AFTER_GUARD)
                if not scratch._expected(root, stage=True):
                    return _result(state.PREIMAGE_REFUSED)
                before = identity._identities(root, stage=True)
                lock_id = identity._identity(root, scratch._LOCK)
                parent = _parent_id(root)
                if before[3] is None or before[3] == before[0]:
                    return _result(state.PREIMAGE_REFUSED)
                _interrupt(interruption, fault.AFTER_PREIMAGE)
                if not _read_once(root, before[0], interruption):
                    return _result(state.READER_CONFLICT_PRESERVE)
                _interrupt(interruption, fault.AFTER_READER_RELEASE)
                # Three independent admission frames; final one directly before
                # the native mutation. The restrictive reader is already closed.
                for _ in range(3):
                    if not _starting(root, before, lock_id, parent):
                        return _result(state.ADMISSION_DRIFT_PRESERVE)
                phases.append(phase.PREIMAGE_REVALIDATED)
                _interrupt(interruption, fault.AFTER_FINAL_ADMISSION)
                phases.append(phase.OPERATION_INVOKED)
                reached_operation = True
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
                conflict = _postimage(root, before, lock_id, parent)
                if conflict is not None:
                    return _result(conflict)
                phases.append(phase.POSTIMAGE_REVALIDATED)
                _interrupt(interruption, fault.AFTER_POSTIMAGE)
                scratch._sync_target(root)
                phases.append(phase.PERSISTENCE_REQUESTED)
                _interrupt(interruption, fault.AFTER_FILE_SYNC)
                conflict = _postimage(root, before, lock_id, parent)
                if conflict is not None or not sequence._ordered(tuple(phases)):
                    return _result(conflict or state.POSTIMAGE_CONFLICT_PRESERVE)
            phases.append(phase.GUARD_RELEASED)
            if not sequence._ordered(tuple(phases)):
                return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
            return _result(state.REPLACEMENT_OBSERVED_PERSISTENCE_UNQUALIFIED)
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except scratch._GuardRefused:
        return _result(state.GUARD_REFUSED)
    except (identity._IdentityUnavailable, _ParentUnqualified):
        return _result(
            state.IDENTITY_CONFLICT_PRESERVE
            if reached_operation
            else state.PREIMAGE_REFUSED
        )
    except (scratch._UnsafeImage, FileNotFoundError):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE
            if reached_operation
            else state.PREIMAGE_REFUSED
        )
    except (OSError, ValueError, TypeError, OverflowError):
        return _result(state.IO_ERROR)
