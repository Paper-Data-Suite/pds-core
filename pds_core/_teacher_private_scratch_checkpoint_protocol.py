"""#238 Slice 3G94: interrupted checkpoint-journal transitions in owned scratch.

Runs fixed synthetic bytes/names, an explicitly invoked guarded resume and
strict conflict holds. No workspace/root/handle/payload/transaction supplied.
Not production journal recovery, durable commit, hostile writer isolation, or
Notes authority. The public probe accepts one exact scenario enum only.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness


class PrivateCheckpointScenario(str, Enum):
    PREPARED = "prepared"
    REGISTRY_INTENT = "registry_intent"
    REGISTRY_INSTALLED = "registry_installed"
    REGISTRY_CONFIRMED = "registry_confirmed"
    DESCRIPTOR_INTENT = "descriptor_intent"
    DESCRIPTOR_INSTALLED = "descriptor_installed"
    BOTH_PENDING_REVIEW = "both_pending_review"
    CONFLICT_JOURNAL = "conflict_journal"
    CONFLICT_REGISTRY = "conflict_registry"
    CONFLICT_STAGE = "conflict_stage"
    CONFLICT_CHECKPOINT_TEMP = "conflict_checkpoint_temp"


class PrivateCheckpointState(str, Enum):
    EXPLICIT_SYNTHETIC_RESUME_PENDING_HOLD = "explicit_synthetic_resume_pending_hold"
    ALREADY_COMPLETE_PENDING_HOLD = "already_complete_pending_hold"
    CONFLICT_PRESERVED_HOLD = "conflict_preserved_hold"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    SCRATCH_CUSTODY_REFUSED = "scratch_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateCheckpointReview:
    state: PrivateCheckpointState
    interrupted_checkpoint: str = "none"
    phase_inferred_from_journal_and_images: bool = False
    guarded_explicit_resume_invoked: bool = False
    exact_synthetic_afterimages_verified: bool = False
    journal_remains_pending: bool = False
    conflict_evidence_unchanged_until_scratch_cleanup: bool = False
    resumptions_after_complete: int = 0
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    automatic_retry_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    atomic_content_compare_and_swap_qualified: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateCheckpointReview(scratch_only=True, non_authorizing=True)"


class _UnsafeScratch(Exception):
    """Fixed, sanitized refusal; no private path or bytes in return value."""


_REGISTRY = "registry.json"
_DESCRIPTOR = "descriptor.json"
_REGISTRY_STAGE = "registry.stage"
_DESCRIPTOR_STAGE = "descriptor.stage"
_JOURNAL = "pending-journal.json"
_NEXT = "pending-journal.next"
_LOCK = ".registry.lock"
_R0 = b"synthetic-registry-before-3g94"
_R1 = b"synthetic-registry-after-3g94"
_D0 = b"synthetic-descriptor-before-3g94"
_D1 = b"synthetic-descriptor-after-3g94"
_PHASES = (
    "prepared",
    "registry_intent",
    "registry_done",
    "descriptor_intent",
    "both_pending_review",
)
_CUTS = (
    PrivateCheckpointScenario.PREPARED,
    PrivateCheckpointScenario.REGISTRY_INTENT,
    PrivateCheckpointScenario.REGISTRY_INSTALLED,
    PrivateCheckpointScenario.REGISTRY_CONFIRMED,
    PrivateCheckpointScenario.DESCRIPTOR_INTENT,
    PrivateCheckpointScenario.DESCRIPTOR_INSTALLED,
    PrivateCheckpointScenario.BOTH_PENDING_REVIEW,
)


def _journal_bytes(phase: str) -> bytes:
    if phase not in _PHASES:
        raise _UnsafeScratch
    return (
        json.dumps(
            {
                "schema": "pds.core.issue238.synthetic-checkpoint.v1",
                "operation": "fixed-synthetic-3g94",
                "phase": phase,
                "registry_before": _R0.hex(),
                "registry_after": _R1.hex(),
                "descriptor_before": _D0.hex(),
                "descriptor_after": _D1.hex(),
                "journal_retirement": "prohibited",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")


def _exclusive(parent: Path, name: str, payload: bytes) -> None:
    with (parent / name).open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _entry(parent: Path, name: str) -> bytes | None:
    path = parent / name
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4096:
        raise _UnsafeScratch
    # This is synthetic-only. A separate same-owner writer can race this read.
    with path.open("rb") as handle:
        payload = handle.read(4097)
        next_info = os.fstat(handle.fileno())
    if (
        len(payload) != info.st_size
        or len(payload) > 4096
        or (next_info.st_dev, next_info.st_ino, next_info.st_size)
        != (info.st_dev, info.st_ino, info.st_size)
    ):
        raise _UnsafeScratch
    return payload


def _phase(parent: Path) -> str:
    raw = _entry(parent, _JOURNAL)
    for phase in _PHASES:
        if raw == _journal_bytes(phase):
            return phase
    raise _UnsafeScratch


def _checkpoint(parent: Path, phase: str) -> None:
    if _entry(parent, _NEXT) is not None:
        raise _UnsafeScratch
    _exclusive(parent, _NEXT, _journal_bytes(phase))
    os.replace(parent / _NEXT, parent / _JOURNAL)
    # File fsync before replace is requested, not a crash-durability guarantee.


def _observed(parent: Path) -> tuple[str, str]:
    """Classify exact names+images, not a caller phase hint or metadata alone."""
    if _entry(parent, _NEXT) is not None:
        return "conflict_preserve", "none"
    try:
        names = {p.name for p in parent.iterdir()}
        if not names.issubset(
            {
                _LOCK,
                _REGISTRY,
                _DESCRIPTOR,
                _REGISTRY_STAGE,
                _DESCRIPTOR_STAGE,
                _JOURNAL,
            }
        ):
            return "conflict_preserve", "none"
        phase = _phase(parent)
        images = (
            _entry(parent, _REGISTRY),
            _entry(parent, _DESCRIPTOR),
            _entry(parent, _REGISTRY_STAGE),
            _entry(parent, _DESCRIPTOR_STAGE),
        )
    except (OSError, _UnsafeScratch):
        return "conflict_preserve", "none"
    if images == (_R0, _D0, _R1, _D1) and phase in {"prepared", "registry_intent"}:
        return "ready_registry", phase
    if images == (_R1, _D0, None, _D1) and phase in {
        "registry_intent",
        "registry_done",
        "descriptor_intent",
    }:
        return (
            "confirm_registry" if phase == "registry_intent" else "ready_descriptor"
        ), phase
    if images == (_R1, _D1, None, None) and phase in {
        "descriptor_intent",
        "both_pending_review",
    }:
        return (
            "confirm_descriptor" if phase == "descriptor_intent" else "complete_hold"
        ), phase
    return "conflict_preserve", phase


def _one_step(parent: Path, phase_index: int) -> None:
    """Seven fixed steps; stage writes never come from caller-controlled data."""
    if phase_index == 0:
        if _observed(parent) != ("ready_registry", "prepared"):
            raise _UnsafeScratch
        _checkpoint(parent, "registry_intent")
    elif phase_index == 1:
        if _observed(parent) != ("ready_registry", "registry_intent"):
            raise _UnsafeScratch
        os.replace(parent / _REGISTRY_STAGE, parent / _REGISTRY)
    elif phase_index == 2:
        if _observed(parent) != ("confirm_registry", "registry_intent"):
            raise _UnsafeScratch
        _checkpoint(parent, "registry_done")
    elif phase_index == 3:
        if _observed(parent) != ("ready_descriptor", "registry_done"):
            raise _UnsafeScratch
        _checkpoint(parent, "descriptor_intent")
    elif phase_index == 4:
        if _observed(parent) != ("ready_descriptor", "descriptor_intent"):
            raise _UnsafeScratch
        os.replace(parent / _DESCRIPTOR_STAGE, parent / _DESCRIPTOR)
    elif phase_index == 5:
        if _observed(parent) != ("confirm_descriptor", "descriptor_intent"):
            raise _UnsafeScratch
        _checkpoint(parent, "both_pending_review")
    else:
        raise _UnsafeScratch


def _explicit_resume(parent: Path) -> tuple[int, bool]:
    """Explicit synthetic-only completion; refuses corruption without retries."""
    steps = 0
    for _ in range(7):
        decision, phase = _observed(parent)
        if decision == "conflict_preserve":
            return steps, False
        if decision == "complete_hold":
            return steps, True
        mapping = {
            ("ready_registry", "prepared"): 0,
            ("ready_registry", "registry_intent"): 1,
            ("confirm_registry", "registry_intent"): 2,
            ("ready_descriptor", "registry_done"): 3,
            ("ready_descriptor", "descriptor_intent"): 4,
            ("confirm_descriptor", "descriptor_intent"): 5,
        }
        index = mapping.get((decision, phase))
        if index is None:
            return steps, False
        _one_step(parent, index)
        steps += 1
    return steps, _observed(parent) == ("complete_hold", "both_pending_review")


def _result(
    state: PrivateCheckpointState,
    *,
    cut: str = "none",
    inferred: bool = False,
    invoked: bool = False,
    verified: bool = False,
    pending: bool = False,
    conflict: bool = False,
    repeats: int = 0,
) -> PrivateCheckpointReview:
    return PrivateCheckpointReview(
        state=state,
        interrupted_checkpoint=cut,
        phase_inferred_from_journal_and_images=inferred,
        guarded_explicit_resume_invoked=invoked,
        exact_synthetic_afterimages_verified=verified,
        journal_remains_pending=pending,
        conflict_evidence_unchanged_until_scratch_cleanup=conflict,
        resumptions_after_complete=repeats,
    )


def probe_disposable_checkpoint_protocol(
    scenario: PrivateCheckpointScenario,
) -> PrivateCheckpointReview:
    """Simulate interrupted journal checkpoints and explicit recovery in scratch.

    Caller cannot supply paths or mutable content. Automatic production recovery
    and journal retirement are always disabled, even after synthetic completion.
    """
    state = PrivateCheckpointState
    if type(scenario) is not PrivateCheckpointScenario:
        return _result(state.INVALID_REQUEST_REFUSED)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _result(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g94_checkpoint_") as dirname:
            parent = Path(dirname) / "target"
            parent.mkdir(mode=0o700)
            for name, payload in (
                (_LOCK, b"0"),
                (_REGISTRY, _R0),
                (_DESCRIPTOR, _D0),
                (_REGISTRY_STAGE, _R1),
                (_DESCRIPTOR_STAGE, _D1),
                (_JOURNAL, _journal_bytes("prepared")),
            ):
                _exclusive(parent, name, payload)
            with locking.hold_existing_private_lock(parent / _LOCK):
                if _observed(parent) != ("ready_registry", "prepared"):
                    raise _UnsafeScratch
                index = _CUTS.index(scenario) if scenario in _CUTS else 0
                for step in range(index):
                    _one_step(parent, step)
                # Interrupt right here: lock is released before review/resume.
            with locking.hold_existing_private_lock(parent / _LOCK):
                if scenario is PrivateCheckpointScenario.CONFLICT_JOURNAL:
                    (parent / _JOURNAL).write_bytes(b"corrupt-journal")
                elif scenario is PrivateCheckpointScenario.CONFLICT_REGISTRY:
                    (parent / _REGISTRY).write_bytes(b"wrong-registry")
                elif scenario is PrivateCheckpointScenario.CONFLICT_STAGE:
                    (parent / _REGISTRY_STAGE).write_bytes(b"wrong-stage")
                elif scenario is PrivateCheckpointScenario.CONFLICT_CHECKPOINT_TEMP:
                    _exclusive(parent, _NEXT, _journal_bytes("registry_intent"))
                decision, phase = _observed(parent)
                if scenario not in _CUTS:
                    evidence = {
                        name: _entry(parent, name)
                        for name in (
                            _REGISTRY,
                            _DESCRIPTOR,
                            _REGISTRY_STAGE,
                            _DESCRIPTOR_STAGE,
                            _JOURNAL,
                            _NEXT,
                        )
                    }
                    steps, completed = _explicit_resume(parent)
                    after = {name: _entry(parent, name) for name in evidence}
                    if (
                        decision != "conflict_preserve"
                        or steps
                        or completed
                        or evidence != after
                    ):
                        raise _UnsafeScratch
                    return _result(
                        state.CONFLICT_PRESERVED_HOLD,
                        cut=scenario.value,
                        inferred=True,
                        pending=_entry(parent, _JOURNAL) is not None,
                        conflict=True,
                    )
                if decision == "conflict_preserve" or phase not in _PHASES:
                    raise _UnsafeScratch
                steps, completed = _explicit_resume(parent)
                if not completed or steps != 6 - index:
                    raise _UnsafeScratch
                if (
                    _observed(parent) != ("complete_hold", "both_pending_review")
                    or _entry(parent, _REGISTRY) != _R1
                    or _entry(parent, _DESCRIPTOR) != _D1
                    or _entry(parent, _REGISTRY_STAGE) is not None
                    or _entry(parent, _DESCRIPTOR_STAGE) is not None
                    or _entry(parent, _NEXT) is not None
                    or _entry(parent, _JOURNAL) != _journal_bytes("both_pending_review")
                ):
                    raise _UnsafeScratch
                repeated, stable = _explicit_resume(parent)
                if repeated or not stable:
                    raise _UnsafeScratch
                return _result(
                    state.ALREADY_COMPLETE_PENDING_HOLD
                    if index == 6
                    else state.EXPLICIT_SYNTHETIC_RESUME_PENDING_HOLD,
                    cut=scenario.value,
                    inferred=True,
                    invoked=True,
                    verified=True,
                    pending=True,
                    repeats=1,
                )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
        _UnsafeScratch,
    ):
        return _result(state.SCRATCH_CUSTODY_REFUSED)
