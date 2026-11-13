"""Synthetic native file-ID and advisory-guard custody rehearsal (Core #238 3G20).

The only files touched are fixed synthetic bytes in an internally allocated
TemporaryDirectory. The native file IDs of staged, replaced, descriptor,
journal and lockfile entries are read with open handles before/after a real
replace. A native scratch advisory lock is held for every observation. This
is *not* production teacher-private custody, durable commit or CAS authority.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypeAlias

from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_writer_sequence as sequence


class PrivateSyntheticIdentityInterruption(str, Enum):
    NONE = "none"
    AFTER_GUARD = "after_guard"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_REPLACE = "after_replace"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_SYNC = "after_sync"


class PrivateSyntheticIdentityState(str, Enum):
    IDENTITY_OBSERVED_PERSISTENCE_UNQUALIFIED = (
        "identity_observed_persistence_unqualified"
    )
    PREIMAGE_REFUSED = "preimage_refused"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    IDENTITY_CONFLICT_PRESERVE = "identity_conflict_preserve"
    IDENTITY_UNAVAILABLE = "identity_unavailable"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    NATIVE_GUARD_REFUSED = "native_guard_refused"
    IO_ERROR = "io_error"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateSyntheticIdentityState.IDENTITY_OBSERVED_PERSISTENCE_UNQUALIFIED: (
        "Synthetic native file identity propagated through replacement under one "
        "scratch advisory guard; production custody and durability remain unqualified."
    ),
    PrivateSyntheticIdentityState.PREIMAGE_REFUSED: (
        "Synthetic starting namespace, bytes or file identities were refused."
    ),
    PrivateSyntheticIdentityState.POSTIMAGE_CONFLICT_PRESERVE: (
        "Synthetic postimage bytes or namespace changed; preserve evidence."
    ),
    PrivateSyntheticIdentityState.IDENTITY_CONFLICT_PRESERVE: (
        "Synthetic file identity changed contrary to the guarded replacement plan."
    ),
    PrivateSyntheticIdentityState.IDENTITY_UNAVAILABLE: (
        "A stable native file identity could not be established in scratch."
    ),
    PrivateSyntheticIdentityState.INTERRUPTED_PRESERVE: (
        "Synthetic operation was interrupted; no successful custody claim."
    ),
    PrivateSyntheticIdentityState.NATIVE_GUARD_REFUSED: (
        "Native scratch advisory lock was refused or could not be released."
    ),
    PrivateSyntheticIdentityState.IO_ERROR: (
        "Synthetic native identity rehearsal encountered an I/O error."
    ),
    PrivateSyntheticIdentityState.INVALID_REQUEST: (
        "Only a defined synthetic interruption can be requested."
    ),
    PrivateSyntheticIdentityState.UNSUPPORTED: (
        "Native identity rehearsal unsupported on this platform."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateSyntheticIdentityReview:
    """Sanitized status only; no path, file ID, byte image, token or handle."""

    state: PrivateSyntheticIdentityState
    message: str


def _result(state: PrivateSyntheticIdentityState) -> PrivateSyntheticIdentityReview:
    return PrivateSyntheticIdentityReview(state, _MESSAGES[state])


class _IdentityUnavailable(Exception):
    """Native file ID is missing, non-regular, multiply linked or unstable."""


class _InjectedInterruption(Exception):
    """Cooperative in-process fault injection; never a real power loss."""


# Internal file IDs are opaque and never returned to callers.
_FileID: TypeAlias = tuple[int, int]
_IdentitySet: TypeAlias = tuple[_FileID, _FileID, _FileID, _FileID | None]


def _identity(root: Path, name: str) -> _FileID:
    """Match path lstat with a momentarily opened handle's native identity.

    No registry/descriptor handle remains open across os.replace on Windows.
    This verification cannot defeat a hostile same-user writer or a reparse
    race; the scratch lock coordinates only lock-honoring participants.
    """
    path = root / name
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise _IdentityUnavailable
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        after = path.lstat()
    values = (before, opened, after)
    if any(
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or not isinstance(value.st_ino, int)
        or value.st_ino <= 0
        or not isinstance(value.st_dev, int)
        for value in values
    ):
        raise _IdentityUnavailable
    ids: tuple[_FileID, _FileID, _FileID] = (
        (before.st_dev, before.st_ino),
        (opened.st_dev, opened.st_ino),
        (after.st_dev, after.st_ino),
    )
    if ids[0] != ids[1] or ids[0] != ids[2]:
        raise _IdentityUnavailable
    return ids[0]


def _identities(root: Path, *, stage: bool) -> _IdentitySet:
    registry = _identity(root, scratch._REGISTRY)
    descriptor = _identity(root, "descriptor.json")
    journal = _identity(root, "transactions.json")
    lock = _identity(root, scratch._LOCK)
    staged = _identity(root, scratch._STAGE) if stage else None
    if len({registry, descriptor, journal, lock, staged}) != 5:
        # Includes None when stage is absent. All four real entries must be distinct.
        raise _IdentityUnavailable
    return registry, descriptor, journal, staged


def _interrupt(
    selected: PrivateSyntheticIdentityInterruption,
    point: PrivateSyntheticIdentityInterruption,
) -> None:
    if selected is point:
        raise _InjectedInterruption


def rehearse_synthetic_private_identity_custody(
    interruption: PrivateSyntheticIdentityInterruption = (
        PrivateSyntheticIdentityInterruption.NONE
    ),
) -> PrivateSyntheticIdentityReview:
    """Rehearse native file-ID propagation with only module-owned scratch files.

    No real workspace path, metadata, callbacks, handles or caller bytes accepted.
    Even a positive result proves only a disposable file-replacement observation.
    """
    state = PrivateSyntheticIdentityState
    fault = PrivateSyntheticIdentityInterruption
    phase = sequence.PrivateRecoveryWriterPhase
    if type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    phases: list[sequence.PrivateRecoveryWriterPhase] = []
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g20_identity_") as temp:
            root = Path(temp)
            scratch._write_new(root, scratch._REGISTRY, scratch._BEFORE)
            scratch._write_new(root, scratch._STAGE, scratch._AFTER)
            scratch._write_new(root, "descriptor.json", scratch._DESCRIPTOR)
            scratch._write_new(root, "transactions.json", scratch._JOURNAL)
            with scratch._scratch_lock(root / scratch._LOCK):
                phases.append(phase.GUARD_ACQUIRED)
                _interrupt(interruption, fault.AFTER_GUARD)
                if not scratch._expected(root, stage=True):
                    return _result(state.PREIMAGE_REFUSED)
                pre = _identities(root, stage=True)
                guard_before = _identity(root, scratch._LOCK)
                if pre[0] == pre[3]:
                    return _result(state.PREIMAGE_REFUSED)
                phases.append(phase.PREIMAGE_REVALIDATED)
                _interrupt(interruption, fault.AFTER_PREIMAGE)
                phases.append(phase.OPERATION_INVOKED)
                os.replace(root / scratch._STAGE, root / scratch._REGISTRY)
                phases.append(phase.OPERATION_RETURNED)
                _interrupt(interruption, fault.AFTER_REPLACE)
                if not scratch._expected(root, stage=False):
                    return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
                post = _identities(root, stage=False)
                guard_after = _identity(root, scratch._LOCK)
                if (
                    post[0] != pre[3]
                    or post[0] == pre[0]
                    or post[1:3] != pre[1:3]
                    or post[3] is not None
                    or guard_before != guard_after
                ):
                    return _result(state.IDENTITY_CONFLICT_PRESERVE)
                phases.append(phase.POSTIMAGE_REVALIDATED)
                _interrupt(interruption, fault.AFTER_POSTIMAGE)
                scratch._sync_target(root)
                phases.append(phase.PERSISTENCE_REQUESTED)
                _interrupt(interruption, fault.AFTER_SYNC)
                if not scratch._expected(root, stage=False):
                    return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
                if (
                    _identities(root, stage=False) != post
                    or _identity(root, scratch._LOCK) != guard_before
                    or not sequence._ordered(tuple(phases))
                ):
                    return _result(state.IDENTITY_CONFLICT_PRESERVE)
            phases.append(phase.GUARD_RELEASED)
            if not sequence._ordered(tuple(phases)):
                return _result(state.IDENTITY_CONFLICT_PRESERVE)
            return _result(state.IDENTITY_OBSERVED_PERSISTENCE_UNQUALIFIED)
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except scratch._GuardRefused:
        return _result(state.NATIVE_GUARD_REFUSED)
    except _IdentityUnavailable:
        return _result(state.IDENTITY_UNAVAILABLE)
    except (scratch._UnsafeImage, FileNotFoundError):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE
            if phase.OPERATION_RETURNED in phases
            else state.PREIMAGE_REFUSED
        )
    except (OSError, ValueError, TypeError, OverflowError):
        return _result(state.IO_ERROR)
