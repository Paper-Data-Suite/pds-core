"""One-operation, two-document interruption/restart drill on disposable files (#238 3G51).

This module never takes caller-owned paths, data, handles or callbacks.  It
creates its own fixed, *synthetic* journal, registry, descriptor and stages,
issues file/parent flush requests, then intentionally releases its operation
lock and independently reacquires it before observing the actual checkpoint.
Every observation is a HOLD, not a replay, retirement, commit or Notes permit.
Power-loss survival, private ACL custody and multi-document atomicity are NOT
proved by an in-process interruption or successful Windows flush request.
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator

from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable


class PrivateJournaledRestartFault(str, Enum):
    NONE = "none"
    AFTER_PREPARATION = "after_preparation"
    AFTER_REGISTRY_REPLACE = "after_registry_replace"
    AFTER_REGISTRY_PERSIST_REQUEST = "after_registry_persist_request"
    AFTER_DESCRIPTOR_REPLACE = "after_descriptor_replace"
    AFTER_DESCRIPTOR_PERSIST_REQUEST = "after_descriptor_persist_request"
    AFTER_OPERATION_GUARD_RELEASE = "after_operation_guard_release"


class PrivateJournaledRestartCheckpoint(str, Enum):
    PREPARED_STAGE_HOLD = "prepared_stage_hold"
    REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD = "registry_after_descriptor_pending_hold"
    BOTH_AFTER_JOURNAL_PENDING_HOLD = "both_after_journal_pending_hold"
    CONFLICT_PRESERVE = "conflict_preserve"
    OBSERVATION_REFUSED = "observation_refused"


class PrivateJournaledRestartState(str, Enum):
    SCRATCH_RESTART_BOTH_AFTER_UNQUALIFIED = "scratch_restart_both_after_unqualified"
    INJECTED_INTERRUPTION_HOLD = "injected_interruption_hold"
    NATIVE_PERSISTENCE_REFUSED_HOLD = "native_persistence_refused_hold"
    REPLACEMENT_OUTCOME_UNKNOWN_HOLD = "replacement_outcome_unknown_hold"
    RESTART_GUARD_REFUSED = "restart_guard_refused"
    RESTART_EVIDENCE_CONFLICT = "restart_evidence_conflict"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    SCRATCH_IO_REFUSED = "scratch_io_refused"


_MESSAGES: dict[PrivateJournaledRestartState, str] = {
    item: "Disposable journaled transaction requires review; no production authority."
    for item in PrivateJournaledRestartState
}
_MESSAGES[PrivateJournaledRestartState.SCRATCH_RESTART_BOTH_AFTER_UNQUALIFIED] = (
    "Scratch after-images were reobserved under a freshly acquired lock. "
    "Durability and production commit remain unqualified."
)
_MESSAGES[PrivateJournaledRestartState.RESTART_EVIDENCE_CONFLICT] = (
    "Restart evidence conflicted with the exact synthetic transaction; no replay."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateJournaledRestartReview:
    state: PrivateJournaledRestartState
    checkpoint: PrivateJournaledRestartCheckpoint
    message: str
    replacement_may_have_occurred: bool
    journal_seen_at_restart: bool
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    automatic_replay_forbidden: bool = True
    journal_retirement_forbidden: bool = True
    durability_unqualified: bool = True
    phases: tuple[str, ...] = field(default=(), repr=False)

    def __repr__(self) -> str:
        return "PrivateJournaledRestartReview(non_authorizing=True)"


def _result(
    state: PrivateJournaledRestartState,
    checkpoint: PrivateJournaledRestartCheckpoint = (
        PrivateJournaledRestartCheckpoint.OBSERVATION_REFUSED
    ),
    *,
    attempted: bool = False,
    journal_seen: bool = False,
    phases: tuple[str, ...] = (),
) -> PrivateJournaledRestartReview:
    return PrivateJournaledRestartReview(
        state,
        checkpoint,
        _MESSAGES[state],
        attempted,
        journal_seen,
        True,
        True,
        True,
        True,
        True,
        phases,
    )


class _Interrupted(Exception):
    pass


class _RestartGuardRefused(Exception):
    pass


@contextmanager
def _held_existing_restart_lock(path: Path) -> Iterator[None]:
    """Reacquire the scratch guard in a *new* scope, never use prior handles."""
    try:
        with path.open("r+b") as stream:
            if stream.read(2) != b"0":
                raise _RestartGuardRefused
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
                    raise _RestartGuardRefused
                locked = True
                yield
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
                    except OSError as exc:
                        raise _RestartGuardRefused from exc
    except (OSError, BlockingIOError, PermissionError) as exc:
        raise _RestartGuardRefused from exc


def _names(directory: Path, expected: frozenset[str]) -> bool:
    """Fail closed on extra entries, symlinks and the wrong entry types."""
    try:
        paths = tuple(directory.iterdir())
        return (
            {path.name for path in paths} == expected
            and len(paths) == len(expected)
            and all(not path.is_symlink() for path in paths)
        )
    except OSError:
        return False


def _checkpoint(
    private: Path, descriptor_dir: Path
) -> PrivateJournaledRestartCheckpoint:
    """Reopen and compare all exact synthetic images, with NO mutation."""
    checkpoint = PrivateJournaledRestartCheckpoint
    transactions = private / "transactions"
    registry = private / "registry.json"
    registry_stage = private / ".synthetic.registry-stage"
    descriptor = descriptor_dir / "teacher-private-association.json"
    descriptor_stage = descriptor_dir / ".synthetic.descriptor-stage"
    pending = transactions / "synthetic-pending.json"
    try:
        if (
            not _names(transactions, frozenset({"synthetic-pending.json"}))
            or not _names(
                private,
                frozenset({"registry.json", "transactions", ".native-lock"})
                | (
                    frozenset({".synthetic.registry-stage"})
                    if registry_stage.exists()
                    else frozenset()
                ),
            )
            or not _names(
                descriptor_dir,
                frozenset({"teacher-private-association.json"})
                | (
                    frozenset({".synthetic.descriptor-stage"})
                    if descriptor_stage.exists()
                    else frozenset()
                ),
            )
            or not durable._exact(pending, durable._JOURNAL)
        ):
            return checkpoint.CONFLICT_PRESERVE
        reg_before = durable._exact(registry, durable._REG_BEFORE)
        reg_after = durable._exact(registry, durable._REG_AFTER)
        desc_before = durable._exact(descriptor, durable._DESC_BEFORE)
        desc_after = durable._exact(descriptor, durable._DESC_AFTER)
        has_registry_stage = registry_stage.exists()
        has_descriptor_stage = descriptor_stage.exists()
        if has_registry_stage and not durable._exact(
            registry_stage, durable._REG_AFTER
        ):
            return checkpoint.CONFLICT_PRESERVE
        if has_descriptor_stage and not durable._exact(
            descriptor_stage, durable._DESC_AFTER
        ):
            return checkpoint.CONFLICT_PRESERVE
        if reg_before and desc_before and has_registry_stage and has_descriptor_stage:
            return checkpoint.PREPARED_STAGE_HOLD
        if (
            reg_after
            and desc_before
            and not has_registry_stage
            and has_descriptor_stage
        ):
            return checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
        if (
            reg_after
            and desc_after
            and not has_registry_stage
            and not has_descriptor_stage
        ):
            return checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
        return checkpoint.CONFLICT_PRESERVE
    except (OSError, ValueError, TypeError, AttributeError):
        return checkpoint.CONFLICT_PRESERVE


def _inject(
    requested: PrivateJournaledRestartFault, point: PrivateJournaledRestartFault
) -> None:
    if requested is point:
        raise _Interrupted


def rehearse_disposable_journaled_restart(
    interruption: PrivateJournaledRestartFault = PrivateJournaledRestartFault.NONE,
) -> PrivateJournaledRestartReview:
    """Rehearse one journaled synthetic attempt and independent restart read.

    Journal retention lasts through restart inspection INSIDE TemporaryDirectory;
    afterward all owned test files are intentionally disposed. A positive
    outcome proves neither cross-process crash persistence nor durable commit.
    """
    state = PrivateJournaledRestartState
    checkpoint = PrivateJournaledRestartCheckpoint
    fault = PrivateJournaledRestartFault
    if type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    attempted = False
    phases: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g51_journaled_") as temp:
            private = Path(temp) / "private"
            transactions = private / "transactions"
            descriptor_dir = Path(temp) / "workspace" / ".pds"
            transactions.mkdir(parents=True)
            descriptor_dir.mkdir(parents=True)
            registry = private / "registry.json"
            registry_stage = private / ".synthetic.registry-stage"
            descriptor = descriptor_dir / "teacher-private-association.json"
            descriptor_stage = descriptor_dir / ".synthetic.descriptor-stage"
            pending = transactions / "synthetic-pending.json"
            failure: PrivateJournaledRestartState | None = None
            try:
                with durable._scratch_lock(private / ".native-lock"):
                    for path, raw in (
                        (registry, durable._REG_BEFORE),
                        (registry_stage, durable._REG_AFTER),
                        (descriptor, durable._DESC_BEFORE),
                        (descriptor_stage, durable._DESC_AFTER),
                        (pending, durable._JOURNAL),
                    ):
                        durable._write_new(path, raw)
                    if (
                        _checkpoint(private, descriptor_dir)
                        is not checkpoint.PREPARED_STAGE_HOLD
                    ):
                        failure = state.RESTART_EVIDENCE_CONFLICT
                    else:
                        for path in (pending, registry_stage, descriptor_stage):
                            durable._file_flush(path)
                        phases.append("prepared_file_flushes")
                        for path in (transactions, private, descriptor_dir):
                            durable._directory_flush(path)
                        phases.append("prepared_directory_flushes")
                        _inject(interruption, fault.AFTER_PREPARATION)
                        if (
                            _checkpoint(private, descriptor_dir)
                            is not checkpoint.PREPARED_STAGE_HOLD
                        ):
                            failure = state.RESTART_EVIDENCE_CONFLICT
                        else:
                            attempted = True
                            os.replace(registry_stage, registry)
                            phases.append("registry_replaced")
                            _inject(interruption, fault.AFTER_REGISTRY_REPLACE)
                            if (
                                _checkpoint(private, descriptor_dir)
                                is not checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
                            ):
                                failure = state.RESTART_EVIDENCE_CONFLICT
                            else:
                                durable._file_flush(registry)
                                durable._directory_flush(private)
                                phases.append("registry_persist_requested")
                                _inject(
                                    interruption, fault.AFTER_REGISTRY_PERSIST_REQUEST
                                )
                                if (
                                    _checkpoint(private, descriptor_dir)
                                    is not checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
                                ):
                                    failure = state.RESTART_EVIDENCE_CONFLICT
                                else:
                                    attempted = True
                                    os.replace(descriptor_stage, descriptor)
                                    phases.append("descriptor_replaced")
                                    _inject(
                                        interruption, fault.AFTER_DESCRIPTOR_REPLACE
                                    )
                                    if (
                                        _checkpoint(private, descriptor_dir)
                                        is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                                    ):
                                        failure = state.RESTART_EVIDENCE_CONFLICT
                                    else:
                                        durable._file_flush(descriptor)
                                        durable._directory_flush(descriptor_dir)
                                        phases.append("descriptor_persist_requested")
                                        _inject(
                                            interruption,
                                            fault.AFTER_DESCRIPTOR_PERSIST_REQUEST,
                                        )
                                        if (
                                            _checkpoint(private, descriptor_dir)
                                            is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                                        ):
                                            failure = state.RESTART_EVIDENCE_CONFLICT
            except (_Interrupted, KeyboardInterrupt):
                failure = state.INJECTED_INTERRUPTION_HOLD
            except (durable._DirectoryFlushRefused, durable._FileFlushRefused):
                failure = state.NATIVE_PERSISTENCE_REFUSED_HOLD
            except durable._GuardRefused:
                failure = state.RESTART_GUARD_REFUSED
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                failure = (
                    state.REPLACEMENT_OUTCOME_UNKNOWN_HOLD
                    if attempted
                    else state.SCRATCH_IO_REFUSED
                )
            # Operation scope is now GONE. This is a new lock/open/checkpoint.
            try:
                _inject(interruption, fault.AFTER_OPERATION_GUARD_RELEASE)
            except (_Interrupted, KeyboardInterrupt):
                failure = state.INJECTED_INTERRUPTION_HOLD
            try:
                with _held_existing_restart_lock(private / ".native-lock"):
                    observed = _checkpoint(private, descriptor_dir)
                    journal_seen = durable._exact(pending, durable._JOURNAL)
            except (_RestartGuardRefused, KeyboardInterrupt, OSError, ValueError):
                return _result(
                    state.RESTART_GUARD_REFUSED,
                    attempted=attempted,
                    phases=tuple(phases),
                )
            if not journal_seen or observed is checkpoint.CONFLICT_PRESERVE:
                failure = state.RESTART_EVIDENCE_CONFLICT
            if failure is None:
                if observed is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD:
                    failure = state.RESTART_EVIDENCE_CONFLICT
                else:
                    failure = state.SCRATCH_RESTART_BOTH_AFTER_UNQUALIFIED
            return _result(
                failure,
                observed,
                attempted=attempted,
                journal_seen=journal_seen,
                phases=tuple(phases),
            )
    except (
        KeyboardInterrupt,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(
            state.REPLACEMENT_OUTCOME_UNKNOWN_HOLD
            if attempted
            else state.SCRATCH_IO_REFUSED,
            attempted=attempted,
            phases=tuple(phases),
        )
