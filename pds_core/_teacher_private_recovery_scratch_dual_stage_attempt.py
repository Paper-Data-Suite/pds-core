"""Disposable canonical FORK_COPY two-stage one-shot attempt (#238 3G57).

This is a deliberate *scratch-only* execution drill, NOT an extension of the
production writer. The function accepts no paths, owner claims, handles, data,
callbacks or recovery permits. Four native parent handles and BOTH prepared
stage-file native identities stay retained across replacement and flush requests.
Each native stage must become the corresponding destination identity after its
single marked replacement. All handles/locks are discarded before a separately
guarded restart classification. No result asserts crash-durability, atomicity,
replay authority, journal retirement or Notes access.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import (
    _teacher_private_recovery_canonical_native_parent_restart as parents,
)
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as restart
from pds_core import _teacher_private_recovery_synthetic_owned_scope as owned
from pds_core import _teacher_private_transaction_intent as intents


class PrivateScratchDualStageFault(str, Enum):
    NONE = "none"
    AFTER_PREPARED = "after_prepared"
    AFTER_REGISTRY_MARK = "after_registry_mark"
    AFTER_REGISTRY_REPLACE = "after_registry_replace"
    AFTER_REGISTRY_FLUSH = "after_registry_flush"
    AFTER_DESCRIPTOR_MARK = "after_descriptor_mark"
    AFTER_DESCRIPTOR_REPLACE = "after_descriptor_replace"
    AFTER_DESCRIPTOR_FLUSH = "after_descriptor_flush"
    AFTER_RELEASE = "after_release"
    AFTER_RESTART_HANDLES = "after_restart_handles"


class PrivateScratchDualStageState(str, Enum):
    SCRATCH_BOTH_STAGE_IDENTITIES_REOBSERVED_UNQUALIFIED = (
        "scratch_both_stage_identities_reobserved_unqualified"
    )
    INJECTED_INTERRUPTION_HOLD = "injected_interruption_hold"
    STAGE_NATIVE_CUSTODY_REFUSED = "stage_native_custody_refused"
    STAGE_NATIVE_IDENTITY_CHANGED = "stage_native_identity_changed"
    PARENT_NATIVE_CUSTODY_REFUSED = "parent_native_custody_refused"
    PREPARATION_FLUSH_REFUSED_HOLD = "preparation_flush_refused_hold"
    REPLACEMENT_OUTCOME_UNKNOWN_HOLD = "replacement_outcome_unknown_hold"
    CANONICAL_CHECKPOINT_CONFLICT_PRESERVE = "canonical_checkpoint_conflict_preserve"
    RESTART_GUARD_REFUSED = "restart_guard_refused"
    RESTART_NATIVE_PARENT_REFUSED = "restart_native_parent_refused"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    SCRATCH_IO_REFUSED = "scratch_io_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateScratchDualStageReview:
    state: PrivateScratchDualStageState
    checkpoint: canonical.PrivateCanonicalRestartCheckpoint
    replacement_may_have_occurred: bool
    journal_seen_at_restart: bool
    attempted_registry: bool
    attempted_descriptor: bool
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    automatic_retry_forbidden: bool = True
    automatic_replay_forbidden: bool = True
    journal_retirement_forbidden: bool = True
    durability_unqualified: bool = True
    phases: tuple[str, ...] = field(default=(), repr=False)

    def __repr__(self) -> str:
        return "PrivateScratchDualStageReview(non_authorizing=True)"


def _result(
    state: PrivateScratchDualStageState,
    checkpoint: canonical.PrivateCanonicalRestartCheckpoint = canonical.PrivateCanonicalRestartCheckpoint.OBSERVATION_REFUSED,
    *,
    registry: bool = False,
    descriptor_attempt: bool = False,
    journal_seen: bool = False,
    phases: tuple[str, ...] = (),
) -> PrivateScratchDualStageReview:
    return PrivateScratchDualStageReview(
        state,
        checkpoint,
        registry or descriptor_attempt,
        journal_seen,
        registry,
        descriptor_attempt,
        True,
        True,
        True,
        True,
        True,
        True,
        phases,
    )


class _StageRefused(Exception):
    pass


class _StageChanged(Exception):
    pass


class _Interrupted(Exception):
    pass


@dataclass(slots=True, repr=False)
class _NativeStage:
    path: Path
    identity: tuple[int, bytes] | tuple[int, int]
    expected: bytes
    _fd: int | None = None
    _handle: int | None = None
    _kernel: Any | None = None

    def _current_identity(
        self, path: Path
    ) -> tuple[int, bytes] | tuple[int, int] | None:
        if sys.platform == "linux":
            try:
                entry = os.stat(path, follow_symlinks=False)
            except FileNotFoundError:
                return None
            if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
                raise _StageChanged
            return (entry.st_dev, entry.st_ino)
        if sys.platform == "win32":
            if self._kernel is None:
                raise _StageChanged
            kernel = self._kernel
            handle, _ = descriptor._windows_open(kernel, str(path), directory=False)
            if handle is None:
                return None
            try:
                info = descriptor._windows_info(kernel, handle)
                key = anchor._windows_id(kernel, handle)
                if (
                    info is None
                    or key is None
                    or bool(info[0] & 0x400)
                    or bool(info[1].directory)
                    or info[1].delete_pending
                    or info[1].number_of_links != 1
                ):
                    raise _StageChanged
                return key
            finally:
                kernel.CloseHandle(wintypes.HANDLE(handle))
        raise _StageChanged

    def _retained_identity(self) -> tuple[int, bytes] | tuple[int, int] | None:
        if sys.platform == "linux":
            if self._fd is None:
                return None
            info = os.fstat(self._fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                return None
            return (info.st_dev, info.st_ino)
        if self._kernel is None or self._handle is None:
            return None
        info = descriptor._windows_info(self._kernel, self._handle)
        key = anchor._windows_id(self._kernel, self._handle)
        if (
            info is None
            or key is None
            or bool(info[0] & 0x400)
            or bool(info[1].directory)
            or info[1].number_of_links != 1
        ):
            return None
        return key

    def check_prepared(self) -> bool:
        return (
            self._retained_identity()
            == self.identity
            == self._current_identity(self.path)
            and self.path.read_bytes() == self.expected
        )

    def check_installed(self, destination: Path) -> bool:
        return (
            self._retained_identity() == self.identity
            and self._current_identity(self.path) is None
            and self._current_identity(destination) == self.identity
            and destination.read_bytes() == self.expected
        )

    def check_retained(self) -> bool:
        return self._retained_identity() == self.identity


@contextmanager
def _hold_stage(path: Path, expected: bytes) -> Iterator[_NativeStage]:
    """Retain a no-follow native stage identity; scratch namespace only.

    Windows uses read-attribute access with share-delete; it must not block the
    drill's own native replacement, and the retained HANDLE survives rename.
    """
    if type(expected) is not bytes or not expected or path.is_symlink():
        raise _StageRefused
    fd: int | None = None
    handle: int | None = None
    kernel: Any | None = None
    active = False
    try:
        if sys.platform == "linux":
            nofollow = getattr(os, "O_NOFOLLOW", 0)
            if not nofollow:
                raise _StageRefused
            fd = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0))
            value = os.fstat(fd)
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_nlink != 1
                or value.st_size != len(expected)
            ):
                raise _StageRefused
            identity: tuple[int, bytes] | tuple[int, int] = (value.st_dev, value.st_ino)
            if os.read(fd, len(expected) + 1) != expected:
                raise _StageRefused
        elif sys.platform == "win32":
            kernel = descriptor._windows_api()
            handle, _ = descriptor._windows_open(kernel, str(path), directory=False)
            if handle is None:
                raise _StageRefused from None
            info = descriptor._windows_info(kernel, handle)
            key = anchor._windows_id(kernel, handle)
            if (
                info is None
                or key is None
                or bool(info[0] & 0x400)
                or bool(info[1].directory)
                or info[1].delete_pending
                or info[1].number_of_links != 1
                or info[1].end_of_file != len(expected)
            ):
                raise _StageRefused
            identity = key
            if path.read_bytes() != expected:
                raise _StageRefused
        else:
            raise _StageRefused
        retained = _NativeStage(path, identity, expected, fd, handle, kernel)
        if not retained.check_prepared():
            raise _StageRefused
        active = True
        try:
            yield retained
        finally:
            if not retained.check_retained():
                raise _StageChanged
    except (OSError, ValueError, TypeError, AttributeError, OverflowError) as exc:
        if active:
            raise
        raise _StageRefused from exc
    finally:
        if fd is not None:
            os.close(fd)
        if handle is not None and kernel is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle))


def _inject(
    selected: PrivateScratchDualStageFault, point: PrivateScratchDualStageFault
) -> None:
    if selected is point:
        raise _Interrupted


def rehearse_canonical_dual_stage_one_shot(
    interruption: PrivateScratchDualStageFault = PrivateScratchDualStageFault.NONE,
) -> PrivateScratchDualStageReview:
    """Mark at most one attempt per document, always preserving pending journal."""
    state = PrivateScratchDualStageState
    point = PrivateScratchDualStageFault
    checkpoint = canonical.PrivateCanonicalRestartCheckpoint
    if type(interruption) is not point:
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    registry_marked = False
    descriptor_marked = False
    phases: list[str] = []
    try:
        checked = canonical._canonical_fork_intent()
        raw = intents.encode_private_transaction_intent(checked)
        with tempfile.TemporaryDirectory(prefix="core238_3g57_dual_stage_") as temp:
            root = Path(temp)
            private = root / "private"
            transactions = private / "transactions"
            workspace = root / "workspace"
            association = workspace / ".pds"
            transactions.mkdir(parents=True)
            association.mkdir(parents=True)
            registry, registry_stage, descriptor_file, descriptor_stage, journal = (
                canonical._paths(private, association)
            )
            roots = parents._parent_roots(private, association)
            failure: PrivateScratchDualStageState | None = None
            try:
                with durable._scratch_lock(private / ".native-lock"):
                    with parents._hold_four_parents(roots) as checks:
                        for path, image in (
                            (registry, checked.registry_before),
                            (registry_stage, checked.registry_after),
                            (descriptor_file, checked.descriptor_before),
                            (descriptor_stage, checked.descriptor_after),
                            (journal, raw),
                        ):
                            if type(image) is not bytes:
                                raise _StageRefused
                            durable._write_new(path, image)
                        for path in (journal, registry_stage, descriptor_stage):
                            durable._file_flush(path)
                        for directory in (transactions, private, association):
                            durable._directory_flush(directory)
                        parents._require_held(checks)
                        if (
                            canonical._checkpoint(private, association, checked)
                            is not checkpoint.PREPARED_HOLD
                        ):
                            failure = state.CANONICAL_CHECKPOINT_CONFLICT_PRESERVE
                        else:
                            with ExitStack() as stack:
                                first = stack.enter_context(
                                    _hold_stage(registry_stage, checked.registry_after)
                                )
                                second = stack.enter_context(
                                    _hold_stage(
                                        descriptor_stage, checked.descriptor_after
                                    )
                                )
                                if (
                                    not first.check_prepared()
                                    or not second.check_prepared()
                                ):
                                    raise _StageChanged
                                phases.append("both_stage_file_handles_held")
                                _inject(interruption, point.AFTER_PREPARED)
                                if (
                                    not first.check_prepared()
                                    or not second.check_prepared()
                                ):
                                    raise _StageChanged
                                parents._require_held(checks)
                                registry_marked = True
                                phases.append("registry_attempt_marked_once")
                                _inject(interruption, point.AFTER_REGISTRY_MARK)
                                os.replace(registry_stage, registry)
                                phases.append("registry_replace_returned")
                                _inject(interruption, point.AFTER_REGISTRY_REPLACE)
                                if (
                                    not first.check_installed(registry)
                                    or not second.check_prepared()
                                ):
                                    raise _StageChanged
                                if (
                                    canonical._checkpoint(private, association, checked)
                                    is not checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
                                ):
                                    raise _StageChanged
                                durable._file_flush(registry)
                                durable._directory_flush(private)
                                parents._require_held(checks)
                                phases.append("registry_flush_requested")
                                _inject(interruption, point.AFTER_REGISTRY_FLUSH)
                                if (
                                    not first.check_installed(registry)
                                    or not second.check_prepared()
                                ):
                                    raise _StageChanged
                                descriptor_marked = True
                                phases.append("descriptor_attempt_marked_once")
                                _inject(interruption, point.AFTER_DESCRIPTOR_MARK)
                                os.replace(descriptor_stage, descriptor_file)
                                phases.append("descriptor_replace_returned")
                                _inject(interruption, point.AFTER_DESCRIPTOR_REPLACE)
                                if not first.check_installed(
                                    registry
                                ) or not second.check_installed(descriptor_file):
                                    raise _StageChanged
                                if (
                                    canonical._checkpoint(private, association, checked)
                                    is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                                ):
                                    raise _StageChanged
                                durable._file_flush(descriptor_file)
                                durable._directory_flush(association)
                                parents._require_held(checks)
                                phases.append("descriptor_flush_requested")
                                _inject(interruption, point.AFTER_DESCRIPTOR_FLUSH)
                                if not first.check_installed(
                                    registry
                                ) or not second.check_installed(descriptor_file):
                                    raise _StageChanged
            except (_Interrupted, KeyboardInterrupt):
                failure = state.INJECTED_INTERRUPTION_HOLD
            except (_StageRefused, _StageChanged):
                failure = (
                    state.STAGE_NATIVE_IDENTITY_CHANGED
                    if registry_marked or descriptor_marked
                    else state.STAGE_NATIVE_CUSTODY_REFUSED
                )
            except (
                parents._ParentDrift,
                owned._ParentUnqualified,
                durable._GuardRefused,
            ):
                failure = state.PARENT_NATIVE_CUSTODY_REFUSED
            except (durable._DirectoryFlushRefused, durable._FileFlushRefused):
                failure = state.PREPARATION_FLUSH_REFUSED_HOLD
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                failure = (
                    state.REPLACEMENT_OUTCOME_UNKNOWN_HOLD
                    if registry_marked or descriptor_marked
                    else state.SCRATCH_IO_REFUSED
                )
            # No previous native HANDLE or lock survives past this boundary.
            phases.append("operation_handles_released")
            try:
                _inject(interruption, point.AFTER_RELEASE)
            except _Interrupted:
                failure = state.INJECTED_INTERRUPTION_HOLD
            observed = checkpoint.OBSERVATION_REFUSED
            journal_seen = False
            try:
                with restart._held_existing_restart_lock(private / ".native-lock"):
                    with parents._hold_four_parents(roots) as fresh:
                        phases.append("fresh_restart_native_parents_held")
                        _inject(interruption, point.AFTER_RESTART_HANDLES)
                        parents._require_held(fresh)
                        observed = canonical._checkpoint(private, association, checked)
                        journal_seen = durable._exact(journal, raw)
                        parents._require_held(fresh)
            except (_Interrupted, KeyboardInterrupt):
                return _result(
                    state.INJECTED_INTERRUPTION_HOLD,
                    registry=registry_marked,
                    descriptor_attempt=descriptor_marked,
                    phases=tuple(phases),
                )
            except (parents._ParentDrift, owned._ParentUnqualified):
                return _result(
                    state.RESTART_NATIVE_PARENT_REFUSED,
                    registry=registry_marked,
                    descriptor_attempt=descriptor_marked,
                    phases=tuple(phases),
                )
            except (
                restart._RestartGuardRefused,
                OSError,
                TypeError,
                AttributeError,
                ValueError,
            ):
                return _result(
                    state.RESTART_GUARD_REFUSED,
                    registry=registry_marked,
                    descriptor_attempt=descriptor_marked,
                    phases=tuple(phases),
                )
            if not journal_seen or observed in (
                checkpoint.CONFLICT_PRESERVE,
                checkpoint.OBSERVATION_REFUSED,
            ):
                failure = state.CANONICAL_CHECKPOINT_CONFLICT_PRESERVE
            if failure is None:
                failure = (
                    state.SCRATCH_BOTH_STAGE_IDENTITIES_REOBSERVED_UNQUALIFIED
                    if observed is checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                    else state.CANONICAL_CHECKPOINT_CONFLICT_PRESERVE
                )
            return _result(
                failure,
                observed,
                registry=registry_marked,
                descriptor_attempt=descriptor_marked,
                journal_seen=journal_seen,
                phases=tuple(phases),
            )
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        KeyboardInterrupt,
    ):
        return _result(
            state.REPLACEMENT_OUTCOME_UNKNOWN_HOLD
            if registry_marked or descriptor_marked
            else state.SCRATCH_IO_REFUSED,
            registry=registry_marked,
            descriptor_attempt=descriptor_marked,
            phases=tuple(phases),
        )
