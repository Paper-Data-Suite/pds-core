"""Core #238 3G96: read-only persistence-window review, disposable scratch only.

A separate producer exits at an exact synthetic journal/mutation checkpoint.
A fresh inspector classifies exact file images without changing them. An
observed Linux directory fsync is only a completed syscall, NOT power-loss
proof. No recovery process, automatic retry, journal retirement, or private
teacher workspace operation is reachable from this fixed-scenario probe.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_checkpoint_protocol as checkpoint
from pds_core import _teacher_private_scratch_fresh_process_checkpoints as fresh


class PrivatePersistenceReviewScenario(str, Enum):
    ORPHAN_CHECKPOINT_TEMP = "orphan_checkpoint_temp"
    REGISTRY_RENAME_NOT_ACKNOWLEDGED = "registry_rename_not_acknowledged"
    DESCRIPTOR_RENAME_NOT_ACKNOWLEDGED = "descriptor_rename_not_acknowledged"
    BOTH_PENDING_MANUAL_REVIEW = "both_pending_manual_review"
    CORRUPT_CANONICAL_JOURNAL = "corrupt_canonical_journal"
    ACKNOWLEDGED_REGISTRY_IMAGE_MISMATCH = "acknowledged_registry_image_mismatch"
    LINUX_PARENT_DIRECTORY_FSYNC = "linux_parent_directory_fsync"


class PrivatePersistenceReviewState(str, Enum):
    UNCERTAIN_RENAME_HOLD = "uncertain_rename_hold"
    PENDING_MANUAL_REVIEW_HOLD = "pending_manual_review_hold"
    CONFLICT_EVIDENCE_HOLD = "conflict_evidence_hold"
    LINUX_DIRECTORY_SYNC_REQUEST_OBSERVED_HOLD = (
        "linux_directory_sync_request_observed_hold"
    )
    WINDOWS_DIRECTORY_SYNC_UNQUALIFIED = "windows_directory_sync_unqualified"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    SCRATCH_CUSTODY_REFUSED = "scratch_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivatePersistenceReview:
    state: PrivatePersistenceReviewState
    scenario: str = "none"
    read_only_fresh_inspector_observed: bool = False
    independent_producer_hard_exit_observed: bool = False
    observed_images_unchanged_by_inspection: bool = False
    pending_journal_evidence_preserved: bool = False
    conflicting_or_uncertain_evidence_held: bool = False
    parent_directory_fsync_requested: bool = False
    native_parent_directory_identity_rechecked: bool = False
    independent_interpreters: int = 0
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    automatic_retry_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    atomic_content_compare_and_swap_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivatePersistenceReview(disposable_only=True, non_authorizing=True)"


class _UnsafeScratch(Exception):
    """Native scratch refusal; private paths or payloads never leave the probe."""


# Each fixed scenario maps to exactly one existing 3G95 producer checkpoint.
_PRODUCER = {
    PrivatePersistenceReviewScenario.ORPHAN_CHECKPOINT_TEMP: "prepared",
    PrivatePersistenceReviewScenario.REGISTRY_RENAME_NOT_ACKNOWLEDGED: "registry_installed",
    PrivatePersistenceReviewScenario.DESCRIPTOR_RENAME_NOT_ACKNOWLEDGED: "descriptor_installed",
    PrivatePersistenceReviewScenario.BOTH_PENDING_MANUAL_REVIEW: "both_pending_review",
    PrivatePersistenceReviewScenario.CORRUPT_CANONICAL_JOURNAL: "prepared",
    PrivatePersistenceReviewScenario.ACKNOWLEDGED_REGISTRY_IMAGE_MISMATCH: "registry_confirmed",
    PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC: "both_pending_review",
}
_EXPECTED = {
    PrivatePersistenceReviewScenario.ORPHAN_CHECKPOINT_TEMP: (
        "conflict_preserve",
        "none",
    ),
    PrivatePersistenceReviewScenario.REGISTRY_RENAME_NOT_ACKNOWLEDGED: (
        "confirm_registry",
        "registry_intent",
    ),
    PrivatePersistenceReviewScenario.DESCRIPTOR_RENAME_NOT_ACKNOWLEDGED: (
        "confirm_descriptor",
        "descriptor_intent",
    ),
    PrivatePersistenceReviewScenario.BOTH_PENDING_MANUAL_REVIEW: (
        "complete_hold",
        "both_pending_review",
    ),
    PrivatePersistenceReviewScenario.CORRUPT_CANONICAL_JOURNAL: (
        "conflict_preserve",
        "none",
    ),
    PrivatePersistenceReviewScenario.ACKNOWLEDGED_REGISTRY_IMAGE_MISMATCH: (
        "conflict_preserve",
        "registry_done",
    ),
    PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC: (
        "complete_hold",
        "both_pending_review",
    ),
}


def _directory_sync_request(parent: Path) -> None:
    """Linux-only opened-directory fsync request, with native identity check.

    There is no Windows fallback and no claim about directory entry survival
    across a power failure or other filesystem implementations.
    """
    if sys.platform != "linux":
        raise _UnsafeScratch
    directory = getattr(os, "O_DIRECTORY", 0)
    if not directory:
        raise _UnsafeScratch
    flags = os.O_RDONLY | directory | getattr(os, "O_CLOEXEC", 0)
    before = os.stat(parent, follow_symlinks=False)
    fd = os.open(parent, flags)
    try:
        observed = os.fstat(fd)
        if not parent.is_dir() or (observed.st_dev, observed.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise _UnsafeScratch
        os.fsync(fd)
        later = os.stat(parent, follow_symlinks=False)
        if (later.st_dev, later.st_ino) != (observed.st_dev, observed.st_ino):
            raise _UnsafeScratch
    finally:
        os.close(fd)


def _inject(parent: Path, scenario: PrivatePersistenceReviewScenario) -> None:
    if scenario is PrivatePersistenceReviewScenario.ORPHAN_CHECKPOINT_TEMP:
        checkpoint._exclusive(
            parent, checkpoint._NEXT, checkpoint._journal_bytes("registry_intent")
        )
    elif scenario is PrivatePersistenceReviewScenario.CORRUPT_CANONICAL_JOURNAL:
        (parent / checkpoint._JOURNAL).write_bytes(b"synthetic-invalid-journal")
    elif (
        scenario
        is PrivatePersistenceReviewScenario.ACKNOWLEDGED_REGISTRY_IMAGE_MISMATCH
    ):
        (parent / checkpoint._REGISTRY).write_bytes(b"synthetic-conflicting-registry")


def _answer(
    state: PrivatePersistenceReviewState,
    *,
    scenario: str = "none",
    inspected: bool = False,
    evidence: bool = False,
    held: bool = False,
    directory_sync: bool = False,
    processes: int = 0,
) -> PrivatePersistenceReview:
    return PrivatePersistenceReview(
        state=state,
        scenario=scenario,
        read_only_fresh_inspector_observed=inspected,
        independent_producer_hard_exit_observed=processes == 2,
        observed_images_unchanged_by_inspection=inspected,
        pending_journal_evidence_preserved=evidence,
        conflicting_or_uncertain_evidence_held=held,
        parent_directory_fsync_requested=directory_sync,
        native_parent_directory_identity_rechecked=directory_sync,
        independent_interpreters=processes,
    )


def probe_disposable_persistence_review(
    scenario: PrivatePersistenceReviewScenario,
) -> PrivatePersistenceReview:
    """Reopen post-stop synthetic evidence; inspect, classify, never resume.

    Unlike 3G95's explicit scratch recovery, this gate intentionally refuses
    to act on a post-rename/unacknowledged window. The classification does not
    establish write ordering or durable journal commit in real storage.
    """
    state = PrivatePersistenceReviewState
    if type(scenario) is not PrivatePersistenceReviewScenario:
        return _answer(state.INVALID_REQUEST_REFUSED)
    if sys.platform not in {"linux", "win32"}:
        return _answer(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _answer(state.REQUIREMENT_DRIFT_REFUSED)
    if (
        scenario is PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC
        and sys.platform == "win32"
    ):
        return _answer(state.WINDOWS_DIRECTORY_SYNC_UNQUALIFIED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g96_sync_review_") as dirname:
            parent = Path(dirname) / "target"
            parent.mkdir(mode=0o700)
            for name, payload in (
                (checkpoint._LOCK, b"0"),
                (checkpoint._REGISTRY, checkpoint._R0),
                (checkpoint._DESCRIPTOR, checkpoint._D0),
                (checkpoint._REGISTRY_STAGE, checkpoint._R1),
                (checkpoint._DESCRIPTOR_STAGE, checkpoint._D1),
                (checkpoint._JOURNAL, checkpoint._journal_bytes("prepared")),
            ):
                checkpoint._exclusive(parent, name, payload)
            # The existing producer acquires a cooperative lock and hard-exits.
            fresh._child(parent, "produce", _PRODUCER[scenario])
            # Only owned fixed synthetic evidence may be deliberately altered.
            with locking.hold_existing_private_lock(parent / checkpoint._LOCK):
                _inject(parent, scenario)
                directory_sync = (
                    scenario
                    is PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC
                )
                if directory_sync:
                    _directory_sync_request(parent)
                before = fresh._snapshot(parent)
            _, inspected = fresh._child(parent, "inspect", _PRODUCER[scenario])
            after = fresh._snapshot(parent)
            expected = _EXPECTED[scenario]
            if (
                before != after
                or inspected != {"decision": expected[0], "phase": expected[1]}
                or checkpoint._entry(parent, checkpoint._JOURNAL) is None
                or checkpoint._entry(parent, checkpoint._LOCK) != b"0"
            ):
                raise _UnsafeScratch
            # Neither inspector nor parent ever invokes explicit recovery.
            # A completed journal stays pending for manual review.
            if directory_sync:
                selected = state.LINUX_DIRECTORY_SYNC_REQUEST_OBSERVED_HOLD
            elif scenario in {
                PrivatePersistenceReviewScenario.REGISTRY_RENAME_NOT_ACKNOWLEDGED,
                PrivatePersistenceReviewScenario.DESCRIPTOR_RENAME_NOT_ACKNOWLEDGED,
            }:
                selected = state.UNCERTAIN_RENAME_HOLD
            elif (
                scenario is PrivatePersistenceReviewScenario.BOTH_PENDING_MANUAL_REVIEW
            ):
                selected = state.PENDING_MANUAL_REVIEW_HOLD
            else:
                selected = state.CONFLICT_EVIDENCE_HOLD
            return _answer(
                selected,
                scenario=scenario.value,
                inspected=True,
                evidence=True,
                held=True,
                directory_sync=directory_sync,
                processes=2,
            )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
        subprocess.TimeoutExpired,
        _UnsafeScratch,
        fresh._UnsafeScratch,
        checkpoint._UnsafeScratch,
    ):
        return _answer(state.SCRATCH_CUSTODY_REFUSED)
