"""Canonical two-document scratch restart WITH four retained native parents (#238 3G53).

Internally generated FORK_COPY transaction; no caller paths, data, owner claims,
handles, callbacks, or write permissions. One disposable operation lock retains
private, journal, workspace and association parent FD/HANDLE identities through
both replacements and flushes. A separate lock and newly opened native parents
observe restart. Every outcome preserves journal/recovery evidence and NEVER
establishes production owner/ACL custody, power-loss durability, replay,
retirement, completed commit or Notes activation.
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as restart
from pds_core import _teacher_private_recovery_synthetic_owned_scope as owned
from pds_core import _teacher_private_transaction_intent as intents


class PrivateCanonicalNativeParentFault(str, Enum):
    NONE = "none"
    AFTER_PARENTS_RETAINED = "after_parents_retained"
    AFTER_PREPARED_FLUSH = "after_prepared_flush"
    AFTER_REGISTRY_REPLACE = "after_registry_replace"
    AFTER_REGISTRY_FLUSH = "after_registry_flush"
    AFTER_DESCRIPTOR_REPLACE = "after_descriptor_replace"
    AFTER_DESCRIPTOR_FLUSH = "after_descriptor_flush"
    AFTER_OPERATION_RELEASE = "after_operation_release"
    AFTER_RESTART_PARENTS_RETAINED = "after_restart_parents_retained"


class PrivateCanonicalNativeParentState(str, Enum):
    SCRATCH_NATIVE_CUSTODY_RESTART_UNQUALIFIED = (
        "scratch_native_custody_restart_unqualified"
    )
    INJECTED_INTERRUPTION_HOLD = "injected_interruption_hold"
    FLUSH_REFUSED_HOLD = "flush_refused_hold"
    REPLACE_OUTCOME_UNKNOWN_HOLD = "replace_outcome_unknown_hold"
    OPERATION_NATIVE_PARENT_REFUSED = "operation_native_parent_refused"
    OPERATION_NATIVE_PARENT_CHANGED = "operation_native_parent_changed"
    RESTART_NATIVE_PARENT_REFUSED = "restart_native_parent_refused"
    RESTART_GUARD_REFUSED = "restart_guard_refused"
    CANONICAL_IMAGE_CONFLICT_PRESERVE = "canonical_image_conflict_preserve"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    SCRATCH_IO_REFUSED = "scratch_io_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateCanonicalNativeParentReview:
    state: PrivateCanonicalNativeParentState
    checkpoint: canonical.PrivateCanonicalRestartCheckpoint
    replacement_may_have_occurred: bool
    journal_seen_at_restart: bool
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    automatic_replay_forbidden: bool = True
    journal_retirement_forbidden: bool = True
    durability_unqualified: bool = True
    phases: tuple[str, ...] = field(default=(), repr=False)

    def __repr__(self) -> str:
        return "PrivateCanonicalNativeParentReview(non_authorizing=True)"


def _result(
    status: PrivateCanonicalNativeParentState,
    checkpoint: canonical.PrivateCanonicalRestartCheckpoint = (
        canonical.PrivateCanonicalRestartCheckpoint.OBSERVATION_REFUSED
    ),
    *,
    attempted: bool = False,
    journal_seen: bool = False,
    phases: tuple[str, ...] = (),
) -> PrivateCanonicalNativeParentReview:
    return PrivateCanonicalNativeParentReview(
        status,
        checkpoint,
        attempted,
        journal_seen,
        True,
        True,
        True,
        True,
        True,
        phases,
    )


class _ParentDrift(Exception):
    pass


class _Interrupted(Exception):
    pass


_Check = Callable[[], bool]


def _parent_roots(private: Path, association: Path) -> tuple[Path, ...]:
    """All four owned roots must be native-retained; never a prior review token."""
    return (private, private / "transactions", association.parent, association)


def _still_held(checks: tuple[_Check, ...]) -> bool:
    return len(checks) == 4 and all(check() is True for check in checks)


@contextmanager
def _hold_four_parents(roots: tuple[Path, ...]) -> Iterator[tuple[_Check, ...]]:
    if len(roots) != 4 or len(set(roots)) != 4:
        raise _ParentDrift
    with ExitStack() as stack:
        checks = tuple(
            stack.enter_context(owned._held_native_parent(root)) for root in roots
        )
        if not _still_held(checks):
            raise _ParentDrift
        try:
            yield checks
        finally:
            if not _still_held(checks):
                raise _ParentDrift


def _require_held(checks: tuple[_Check, ...]) -> None:
    if not _still_held(checks):
        raise _ParentDrift


def _inject(
    selected: PrivateCanonicalNativeParentFault,
    point: PrivateCanonicalNativeParentFault,
) -> None:
    if selected is point:
        raise _Interrupted


def rehearse_canonical_native_parent_restart(
    interruption: PrivateCanonicalNativeParentFault = PrivateCanonicalNativeParentFault.NONE,
) -> PrivateCanonicalNativeParentReview:
    """Exercise one canonical FORK_COPY on self-owned scratch with native custody.

    The pending journal is NOT retired. A fresh restart observes current bytes
    after all operation-owned handles have been closed. No positive result is
    transferable native custody or production write permission.
    """
    status = PrivateCanonicalNativeParentState
    checkpoint = canonical.PrivateCanonicalRestartCheckpoint
    point = PrivateCanonicalNativeParentFault
    if type(interruption) is not point:
        return _result(status.INVALID_REQUEST)
    if sys.platform not in {"win32", "linux"}:
        return _result(status.UNSUPPORTED)
    attempted = False
    phases: list[str] = []
    try:
        checked = canonical._canonical_fork_intent()
        journal_image = intents.encode_private_transaction_intent(checked)
        with tempfile.TemporaryDirectory(prefix="core238_3g53_native_parents_") as temp:
            root = Path(temp)
            private = root / "private"
            transactions = private / "transactions"
            workspace = root / "workspace"
            association = workspace / ".pds"
            transactions.mkdir(parents=True)
            association.mkdir(parents=True)
            registry, registry_stage, descriptor, descriptor_stage, journal = (
                canonical._paths(private, association)
            )
            roots = _parent_roots(private, association)
            failure: PrivateCanonicalNativeParentState | None = None
            try:
                with durable._scratch_lock(private / ".native-lock"):
                    with _hold_four_parents(roots) as checks:
                        phases.append("four_native_parents_held")
                        _inject(interruption, point.AFTER_PARENTS_RETAINED)
                        for path, image in (
                            (registry, checked.registry_before),
                            (registry_stage, checked.registry_after),
                            (descriptor, checked.descriptor_before),
                            (descriptor_stage, checked.descriptor_after),
                            (journal, journal_image),
                        ):
                            if type(image) is not bytes:
                                raise ValueError("Unqualified canonical image")
                            durable._write_new(path, image)
                        _require_held(checks)
                        if (
                            canonical._checkpoint(private, association, checked)
                            is not checkpoint.PREPARED_HOLD
                        ):
                            failure = status.CANONICAL_IMAGE_CONFLICT_PRESERVE
                        else:
                            for path in (journal, registry_stage, descriptor_stage):
                                durable._file_flush(path)
                            for path in (transactions, private, association):
                                durable._directory_flush(path)
                            _require_held(checks)
                            phases.append("prepared_images_and_parents_flushed")
                            _inject(interruption, point.AFTER_PREPARED_FLUSH)
                            if (
                                canonical._checkpoint(private, association, checked)
                                is not checkpoint.PREPARED_HOLD
                            ):
                                failure = status.CANONICAL_IMAGE_CONFLICT_PRESERVE
                            else:
                                _require_held(checks)
                                attempted = True
                                os.replace(registry_stage, registry)
                                phases.append("registry_replaced")
                                _require_held(checks)
                                _inject(interruption, point.AFTER_REGISTRY_REPLACE)
                                if (
                                    canonical._checkpoint(private, association, checked)
                                    is not checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
                                ):
                                    failure = status.CANONICAL_IMAGE_CONFLICT_PRESERVE
                                else:
                                    durable._file_flush(registry)
                                    durable._directory_flush(private)
                                    _require_held(checks)
                                    phases.append("registry_flush_requested")
                                    _inject(interruption, point.AFTER_REGISTRY_FLUSH)
                                    if (
                                        canonical._checkpoint(
                                            private, association, checked
                                        )
                                        is not checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
                                    ):
                                        failure = (
                                            status.CANONICAL_IMAGE_CONFLICT_PRESERVE
                                        )
                                    else:
                                        _require_held(checks)
                                        os.replace(descriptor_stage, descriptor)
                                        phases.append("descriptor_replaced")
                                        _require_held(checks)
                                        _inject(
                                            interruption, point.AFTER_DESCRIPTOR_REPLACE
                                        )
                                        if (
                                            canonical._checkpoint(
                                                private, association, checked
                                            )
                                            is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                                        ):
                                            failure = (
                                                status.CANONICAL_IMAGE_CONFLICT_PRESERVE
                                            )
                                        else:
                                            durable._file_flush(descriptor)
                                            durable._directory_flush(association)
                                            _require_held(checks)
                                            phases.append("descriptor_flush_requested")
                                            _inject(
                                                interruption,
                                                point.AFTER_DESCRIPTOR_FLUSH,
                                            )
                                            if (
                                                canonical._checkpoint(
                                                    private, association, checked
                                                )
                                                is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                                            ):
                                                failure = status.CANONICAL_IMAGE_CONFLICT_PRESERVE
            except (_Interrupted, KeyboardInterrupt):
                failure = status.INJECTED_INTERRUPTION_HOLD
            except (owned._ParentUnqualified, _ParentDrift):
                failure = (
                    status.OPERATION_NATIVE_PARENT_CHANGED
                    if phases
                    else status.OPERATION_NATIVE_PARENT_REFUSED
                )
            except (durable._DirectoryFlushRefused, durable._FileFlushRefused):
                failure = status.FLUSH_REFUSED_HOLD
            except durable._GuardRefused:
                failure = status.OPERATION_NATIVE_PARENT_REFUSED
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                failure = (
                    status.REPLACE_OUTCOME_UNKNOWN_HOLD
                    if attempted
                    else status.SCRATCH_IO_REFUSED
                )
            # Native operation handles have closed here, even on interruption.
            phases.append("operation_handles_released")
            try:
                _inject(interruption, point.AFTER_OPERATION_RELEASE)
            except _Interrupted:
                failure = status.INJECTED_INTERRUPTION_HOLD
            observed = checkpoint.OBSERVATION_REFUSED
            journal_seen = False
            try:
                with restart._held_existing_restart_lock(private / ".native-lock"):
                    with _hold_four_parents(roots) as fresh:
                        phases.append("fresh_restart_native_parents_held")
                        _inject(interruption, point.AFTER_RESTART_PARENTS_RETAINED)
                        _require_held(fresh)
                        observed = canonical._checkpoint(private, association, checked)
                        journal_seen = durable._exact(journal, journal_image)
                        _require_held(fresh)
            except (_Interrupted, KeyboardInterrupt):
                return _result(
                    status.INJECTED_INTERRUPTION_HOLD,
                    attempted=attempted,
                    phases=tuple(phases),
                )
            except (owned._ParentUnqualified, _ParentDrift):
                return _result(
                    status.RESTART_NATIVE_PARENT_REFUSED,
                    attempted=attempted,
                    phases=tuple(phases),
                )
            except (
                restart._RestartGuardRefused,
                OSError,
                ValueError,
                TypeError,
                AttributeError,
            ):
                return _result(
                    status.RESTART_GUARD_REFUSED,
                    attempted=attempted,
                    phases=tuple(phases),
                )
            if not journal_seen or observed in (
                checkpoint.CONFLICT_PRESERVE,
                checkpoint.OBSERVATION_REFUSED,
            ):
                failure = status.CANONICAL_IMAGE_CONFLICT_PRESERVE
            if failure is None:
                failure = (
                    status.SCRATCH_NATIVE_CUSTODY_RESTART_UNQUALIFIED
                    if observed is checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                    else status.CANONICAL_IMAGE_CONFLICT_PRESERVE
                )
            return _result(
                failure,
                observed,
                attempted=attempted,
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
            status.REPLACE_OUTCOME_UNKNOWN_HOLD
            if attempted
            else status.SCRATCH_IO_REFUSED,
            attempted=attempted,
            phases=tuple(phases),
        )
