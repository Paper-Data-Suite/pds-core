"""Bounded two-root native prepared-stage replacement (Core #238 Slice 3G31).

Exercise one existing *synthetic* stage-to-registry recovery transition with
independent private and workspace roots, held native parent FD/HANDLEs, one
local scratch lock, and an exact pending journal. All paths and bytes are
created internally beneath TemporaryDirectory. No caller-supplied path, intent,
content, handle, callback, or production writing capability is accepted.

This does NOT acquire production ACL/owner/backing custody, exclude other
same-user writers, prove directory-entry durability, retire the pending journal,
or activate Notes. The outcome never authorizes a protected filesystem write.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Iterator, cast

from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_owned_scope as owned
from pds_core import _teacher_private_recovery_synthetic_windows_share as winshare
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission


class PrivateTwoRootFault(str, Enum):
    NONE = "none"
    AFTER_LOCK = "after_lock"
    AFTER_PARENT_HANDLES = "after_parent_handles"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_READER_RELEASE = "after_reader_release"
    BEFORE_NATIVE_REPLACE = "before_native_replace"
    AFTER_NATIVE_REPLACE = "after_native_replace"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_FILE_SYNC = "after_file_sync"
    AFTER_HANDLE_RELEASE = "after_handle_release"


class PrivateTwoRootState(str, Enum):
    SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED = (
        "scratch_two_root_replacement_unqualified"
    )
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    PREIMAGE_REFUSED = "preimage_refused"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    PARENT_IDENTITY_CONFLICT_PRESERVE = "parent_identity_conflict_preserve"
    FILE_IDENTITY_CONFLICT_PRESERVE = "file_identity_conflict_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    READER_CONFLICT_PRESERVE = "reader_conflict_preserve"
    ADMISSION_DRIFT_PRESERVE = "admission_drift_preserve"
    REPLACEMENT_REFUSED_PRESERVE = "replacement_refused_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateTwoRootState, str] = {
    PrivateTwoRootState.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED: "Fixed synthetic two-root stage replacement observed; no production mutation or durable commit.",
    PrivateTwoRootState.OPERATION_NOT_ADMITTED: "Only an existing prepared stage-to-registry operation is exercised.",
    PrivateTwoRootState.INVALID_REQUEST: "Only exact operation and interruption enums are accepted.",
    PrivateTwoRootState.UNSUPPORTED: "Native two-root rehearsal is unsupported on this operating system.",
    PrivateTwoRootState.PREIMAGE_REFUSED: "Synthetic prepared images or file identities were unqualified.",
    PrivateTwoRootState.NAMESPACE_CONFLICT_PRESERVE: "Synthetic private, journal, stage, or descriptor namespace drifted.",
    PrivateTwoRootState.PARENT_IDENTITY_CONFLICT_PRESERVE: "One of four retained native parent identities did not match its current path.",
    PrivateTwoRootState.FILE_IDENTITY_CONFLICT_PRESERVE: "Registry, journal, descriptor, stage, or lock identity drifted.",
    PrivateTwoRootState.IMAGE_CONFLICT_PRESERVE: "Expected synthetic registry, journal, descriptor, or stage bytes changed.",
    PrivateTwoRootState.READER_CONFLICT_PRESERVE: "Restrictive registry reader failed exact native ID or byte check.",
    PrivateTwoRootState.ADMISSION_DRIFT_PRESERVE: "Pre-replacement protected-like synthetic evidence changed under the lock.",
    PrivateTwoRootState.REPLACEMENT_REFUSED_PRESERVE: "Native synthetic stage replacement was refused; no fallback permission.",
    PrivateTwoRootState.POSTIMAGE_CONFLICT_PRESERVE: "Synthetic after-image or expected stage removal did not qualify.",
    PrivateTwoRootState.INTERRUPTED_PRESERVE: "In-process interruption: preserve pending recovery evidence; no completed-operation assertion.",
    PrivateTwoRootState.GUARD_REFUSED: "Scratch native lock or retained parent custody refused.",
    PrivateTwoRootState.IO_ERROR: "Synthetic filesystem observation or native replacement failed.",
}


@dataclass(frozen=True, slots=True)
class PrivateTwoRootReview:
    state: PrivateTwoRootState
    message: str


def _result(state: PrivateTwoRootState) -> PrivateTwoRootReview:
    return PrivateTwoRootReview(state, _MESSAGES[state])


class _InjectedInterruption(Exception):
    pass


class _NamespaceConflict(Exception):
    pass


class _ImageConflict(Exception):
    pass


class _IdentityConflict(Exception):
    pass


class _ParentConflict(Exception):
    pass


class _ReaderConflict(Exception):
    pass


_TX = "pending-transaction.json"
_ASSOC = "teacher-private-association.json"


@dataclass(frozen=True, slots=True)
class _Paths:
    private: Path
    transactions: Path
    workspace: Path
    association_dir: Path


_FileID = tuple[int, int]
_ParentIDs = tuple[_FileID, _FileID, _FileID, _FileID]


@dataclass(frozen=True, slots=True)
class _Evidence:
    parent_ids: _ParentIDs
    registry_id: _FileID
    journal_id: _FileID
    descriptor_id: _FileID
    lock_id: _FileID
    stage_id: _FileID | None


def _interrupt(selected: PrivateTwoRootFault, point: PrivateTwoRootFault) -> None:
    if selected is point:
        raise _InjectedInterruption


def _parents(paths: _Paths) -> tuple[Path, Path, Path, Path]:
    return paths.private, paths.transactions, paths.workspace, paths.association_dir


def _names(path: Path, wanted: set[str]) -> bool:
    parts = list(path.iterdir())
    return (
        {item.name for item in parts} == wanted
        and len(parts) == len(wanted)
        and not any(item.is_symlink() for item in parts)
    )


def _namespace(paths: _Paths, *, stage: bool) -> bool:
    private_names = {scratch._REGISTRY, scratch._LOCK, "transactions"}
    if stage:
        private_names.add(scratch._STAGE)
    return (
        _names(paths.private, private_names)
        and _names(paths.transactions, {_TX})
        and _names(paths.workspace, {".pds"})
        and _names(paths.association_dir, {_ASSOC})
    )


def _exact(path: Path, expected: bytes) -> bool:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        return False
    with path.open("rb") as stream:
        return stream.read(len(expected) + 1) == expected


def _locked_file_shape(path: Path) -> bool:
    """Inspect lock metadata without reading Windows' actively locked byte.

    ``scratch._scratch_lock`` writes the fixed single byte *before* acquiring
    its byte-range lock. On Windows, a second descriptor cannot read that byte
    during the protected scope. Retain the byte-range lock; check regular-file
    shape, one link and exact size, then include its native identity in each
    evidence census. This is NOT an exclusive production ownership proof.
    """
    details = path.lstat()
    return (
        stat.S_ISREG(details.st_mode) and details.st_nlink == 1 and details.st_size == 1
    )


def _evidence(paths: _Paths, *, stage: bool) -> _Evidence:
    if not _namespace(paths, stage=stage):
        raise _NamespaceConflict
    expected: tuple[tuple[Path, bytes], ...] = (
        (
            paths.private / scratch._REGISTRY,
            scratch._BEFORE if stage else scratch._AFTER,
        ),
        (paths.transactions / _TX, scratch._JOURNAL),
        (paths.association_dir / _ASSOC, scratch._DESCRIPTOR),
    )
    if stage:
        expected += ((paths.private / scratch._STAGE, scratch._AFTER),)
    if not _locked_file_shape(paths.private / scratch._LOCK) or not all(
        _exact(path, raw) for path, raw in expected
    ):
        raise _ImageConflict
    parent_ids = cast(
        _ParentIDs, tuple(admission._parent_id(parent) for parent in _parents(paths))
    )
    if len(set(parent_ids)) != 4:
        raise _ParentConflict
    registry_id = identity._identity(paths.private, scratch._REGISTRY)
    journal_id = identity._identity(paths.transactions, _TX)
    descriptor_id = identity._identity(paths.association_dir, _ASSOC)
    lock_id = identity._identity(paths.private, scratch._LOCK)
    stage_id = identity._identity(paths.private, scratch._STAGE) if stage else None
    unique_ids = {registry_id, journal_id, descriptor_id, lock_id}
    if stage_id is not None:
        unique_ids.add(stage_id)
    if len(unique_ids) != (5 if stage else 4):
        raise _IdentityConflict
    return _Evidence(
        parent_ids, registry_id, journal_id, descriptor_id, lock_id, stage_id
    )


@contextmanager
def _reader(path: Path, expected: _FileID) -> Iterator[None]:
    """Restrictive native Windows reader is released before any replacement."""
    if sys.platform == "win32":
        with winshare._native_target(
            path, winshare.PrivateSyntheticWindowsShareMode.NO_DELETE_SHARE
        ) as stream:
            if not winshare._held_before(stream, expected):
                raise _ReaderConflict
            yield
    else:
        with path.open("rb") as stream:
            if not _held_regular(stream, expected):
                raise _ReaderConflict
            yield


def _held_regular(stream: BinaryIO, expected: _FileID) -> bool:
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != expected:
        return False
    stream.seek(0)
    return stream.read(len(scratch._BEFORE) + 1) == scratch._BEFORE


def _still_held(checks: tuple[object, ...]) -> bool:
    return len(checks) == 4 and all(
        callable(check) and check() is True for check in checks
    )


def _precheck(paths: _Paths, expected: _Evidence, checks: tuple[object, ...]) -> bool:
    if not _still_held(checks):
        raise _ParentConflict
    return _evidence(paths, stage=True) == expected


def _postcheck(paths: _Paths, expected: _Evidence, checks: tuple[object, ...]) -> None:
    if not _still_held(checks):
        raise _ParentConflict
    observed = _evidence(paths, stage=False)
    if (
        observed.parent_ids != expected.parent_ids
        or observed.registry_id != expected.stage_id
        or observed.registry_id == expected.registry_id
        or observed.journal_id != expected.journal_id
        or observed.descriptor_id != expected.descriptor_id
        or observed.lock_id != expected.lock_id
        or observed.stage_id is not None
    ):
        raise _IdentityConflict


def _make_layout(base: Path) -> _Paths:
    private = base / "private"
    transactions = private / "transactions"
    workspace = base / "workspace"
    association = workspace / ".pds"
    transactions.mkdir(parents=True)
    association.mkdir(parents=True)
    scratch._write_new(private, scratch._REGISTRY, scratch._BEFORE)
    scratch._write_new(private, scratch._STAGE, scratch._AFTER)
    scratch._write_new(transactions, _TX, scratch._JOURNAL)
    scratch._write_new(association, _ASSOC, scratch._DESCRIPTOR)
    return _Paths(private, transactions, workspace, association)


def rehearse_synthetic_private_two_root_replace(
    step: admission.PrivateScratchWriterStep = admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
    interruption: PrivateTwoRootFault = PrivateTwoRootFault.NONE,
) -> PrivateTwoRootReview:
    """Execute one prepared stage replace only on internally created scratch.

    A positive observation still preserves the pending journal; it never proves
    actual protected owner/ACL validation, crash safety or permission to write.
    """
    state = PrivateTwoRootState
    fault = PrivateTwoRootFault
    if (
        type(step) is not admission.PrivateScratchWriterStep
        or type(interruption) is not fault
    ):
        return _result(state.INVALID_REQUEST)
    if step is not admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    started = False
    replaced = False
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g31_two_root_") as temporary:
            paths = _make_layout(Path(temporary))
            with scratch._scratch_lock(paths.private / scratch._LOCK):
                _interrupt(interruption, fault.AFTER_LOCK)
                with ExitStack() as held:
                    checks = tuple(
                        held.enter_context(owned._held_native_parent(path))
                        for path in _parents(paths)
                    )
                    if not _still_held(checks):
                        raise _ParentConflict
                    _interrupt(interruption, fault.AFTER_PARENT_HANDLES)
                    before = _evidence(paths, stage=True)
                    if before.stage_id is None or before.stage_id == before.registry_id:
                        raise _IdentityConflict
                    started = True
                    if not _precheck(paths, before, checks):
                        return _result(state.PREIMAGE_REFUSED)
                    _interrupt(interruption, fault.AFTER_PREIMAGE)
                    with _reader(paths.private / scratch._REGISTRY, before.registry_id):
                        if not _precheck(paths, before, checks):
                            return _result(state.ADMISSION_DRIFT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_READER_RELEASE)
                    for _ in range(3):
                        if not _precheck(paths, before, checks):
                            return _result(state.ADMISSION_DRIFT_PRESERVE)
                    _interrupt(interruption, fault.BEFORE_NATIVE_REPLACE)
                    try:
                        os.replace(
                            paths.private / scratch._STAGE,
                            paths.private / scratch._REGISTRY,
                        )
                    except OSError as error:
                        if isinstance(error, PermissionError) or getattr(
                            error, "winerror", None
                        ) in (5, 32, 33):
                            return _result(state.REPLACEMENT_REFUSED_PRESERVE)
                        raise
                    replaced = True
                    _interrupt(interruption, fault.AFTER_NATIVE_REPLACE)
                    _postcheck(paths, before, checks)
                    _interrupt(interruption, fault.AFTER_POSTIMAGE)
                    scratch._sync_target(paths.private)
                    _interrupt(interruption, fault.AFTER_FILE_SYNC)
                    _postcheck(paths, before, checks)
                _interrupt(interruption, fault.AFTER_HANDLE_RELEASE)
                # No journal retirement. File sync does not prove directory durability.
                return _result(state.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED)
    except (_InjectedInterruption, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except (scratch._GuardRefused, owned._ParentUnqualified):
        return _result(state.GUARD_REFUSED)
    except _NamespaceConflict:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except _ParentConflict:
        return _result(state.PARENT_IDENTITY_CONFLICT_PRESERVE)
    except (identity._IdentityUnavailable, _IdentityConflict):
        return _result(
            state.FILE_IDENTITY_CONFLICT_PRESERVE if started else state.PREIMAGE_REFUSED
        )
    except (_ImageConflict, scratch._UnsafeImage):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE
            if replaced
            else state.IMAGE_CONFLICT_PRESERVE
            if started
            else state.PREIMAGE_REFUSED
        )
    except _ReaderConflict:
        return _result(state.READER_CONFLICT_PRESERVE)
    except FileNotFoundError:
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE if replaced else state.PREIMAGE_REFUSED
        )
    except (OSError, TypeError, ValueError, OverflowError, AttributeError):
        return _result(state.IO_ERROR)
