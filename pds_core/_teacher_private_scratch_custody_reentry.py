"""Core #238 3G97: retained native parent, fresh inspection, identity drift holds.

This is a fixed, disposable filesystem experiment only. The only public input
is an exact scenario enum; no caller path, identity, content, handle or mutable
callback reaches the probe. A retained parent handle cannot authorize a
path-based replacement, make a lock exclude noncooperating code, or provide an
atomic comparison with the identity observed before a competing writer ran.
"""

from __future__ import annotations

import os
import stat
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
from pds_core import _teacher_private_scratch_native_writer_window as custody


class PrivateCustodyReentryScenario(str, Enum):
    STABLE_REGISTRY_INSTALLED = "stable_registry_installed"
    STABLE_BOTH_PENDING = "stable_both_pending"
    EQUAL_BYTES_LIVE_SUBSTITUTION = "equal_bytes_live_substitution"
    EQUAL_BYTES_STAGE_SUBSTITUTION = "equal_bytes_stage_substitution"
    EQUAL_BYTES_JOURNAL_SUBSTITUTION = "equal_bytes_journal_substitution"
    CHANGED_REGISTRY_BYTES = "changed_registry_bytes"


class PrivateCustodyReentryState(str, Enum):
    STABLE_UNCERTAIN_HOLD = "stable_uncertain_hold"
    STABLE_PENDING_MANUAL_HOLD = "stable_pending_manual_hold"
    SAME_BYTES_IDENTITY_DRIFT_HOLD = "same_bytes_identity_drift_hold"
    CONTENT_CONFLICT_HOLD = "content_conflict_hold"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    NATIVE_CUSTODY_REFUSED = "native_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateCustodyReentryReview:
    state: PrivateCustodyReentryState
    scenario: str = "none"
    native_parent_handle_retained_across_inspection: bool = False
    independent_producer_hard_exit_observed: bool = False
    independent_read_only_inspector_observed: bool = False
    exact_bytes_inspector_unchanged: bool = False
    watched_entry_identity_checked: bool = False
    equal_bytes_identity_substitution_detected: bool = False
    content_conflict_detected: bool = False
    pending_journal_retained: bool = False
    independent_interpreters: int = 0
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    automatic_retry_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    atomic_content_compare_and_swap_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    native_handle_relative_replace_qualified: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateCustodyReentryReview(scratch_only=True, non_authorizing=True)"


class _UnsafeScratch(Exception):
    """Sanitized refusal; never leak scratch path or native filesystem metadata."""


_WATCH = (
    checkpoint._REGISTRY,
    checkpoint._DESCRIPTOR,
    checkpoint._REGISTRY_STAGE,
    checkpoint._DESCRIPTOR_STAGE,
    checkpoint._JOURNAL,
)
_SCENARIO_CUT: dict[PrivateCustodyReentryScenario, str] = {
    PrivateCustodyReentryScenario.STABLE_REGISTRY_INSTALLED: "registry_installed",
    PrivateCustodyReentryScenario.STABLE_BOTH_PENDING: "both_pending_review",
    PrivateCustodyReentryScenario.EQUAL_BYTES_LIVE_SUBSTITUTION: "registry_installed",
    PrivateCustodyReentryScenario.EQUAL_BYTES_STAGE_SUBSTITUTION: "prepared",
    PrivateCustodyReentryScenario.EQUAL_BYTES_JOURNAL_SUBSTITUTION: "registry_installed",
    PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES: "registry_installed",
}
_RIVAL_WATCH: dict[PrivateCustodyReentryScenario, str] = {
    PrivateCustodyReentryScenario.EQUAL_BYTES_LIVE_SUBSTITUTION: checkpoint._REGISTRY,
    PrivateCustodyReentryScenario.EQUAL_BYTES_STAGE_SUBSTITUTION: checkpoint._REGISTRY_STAGE,
    PrivateCustodyReentryScenario.EQUAL_BYTES_JOURNAL_SUBSTITUTION: checkpoint._JOURNAL,
    PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES: checkpoint._REGISTRY,
}

# The child receives only an internally created disposable directory and one
# fixed entry name. It intentionally ignores the cooperative lock. The child
# must never receive real user-supplied file paths or content.
_RIVAL = r"""
import os,sys
from pathlib import Path
root=Path(sys.argv[1]); name=sys.argv[2]; kind=sys.argv[3]
if name not in ('registry.json','registry.stage','pending-journal.json'):
    raise SystemExit(3)
if kind not in ('equal_bytes','different_bytes'):
    raise SystemExit(3)
target=root/name
if kind=='equal_bytes':
    image=target.read_bytes()
    decoy=root/'rival-fixed-decoy'
    with decoy.open('xb') as stream:
        stream.write(image)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(decoy,target)
    print('RIVAL_EQUAL_BYTES_SWAPPED')
else:
    target.write_bytes(b'synthetic-conflicting-entry-3g97')
    print('RIVAL_CONTENT_CHANGED')
"""


def _independent_rival(parent: Path, entry: str, *, equal_bytes: bool) -> None:
    if entry not in {
        checkpoint._REGISTRY,
        checkpoint._REGISTRY_STAGE,
        checkpoint._JOURNAL,
    }:
        raise _UnsafeScratch
    kind = "equal_bytes" if equal_bytes else "different_bytes"
    result = subprocess.run(
        [sys.executable, "-I", "-c", _RIVAL, str(parent), entry, kind],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    expected = "RIVAL_EQUAL_BYTES_SWAPPED" if equal_bytes else "RIVAL_CONTENT_CHANGED"
    if (
        result.returncode != 0
        or result.stdout.strip() != expected
        or result.stderr.strip()
    ):
        raise _UnsafeScratch


def _fingerprint(parent: Path) -> tuple[tuple[str, tuple[int, int, int] | None], ...]:
    """Native file ID from an opened fd, checked against the current entry.

    This pins neither the original file's name nor the directory namespace.
    It deliberately has no production API and refuses symlinks/unsafe aliases.
    """
    observed: list[tuple[str, tuple[int, int, int] | None]] = []
    for name in _WATCH:
        path = parent / name
        try:
            initial = path.lstat()
        except FileNotFoundError:
            observed.append((name, None))
            continue
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or initial.st_size <= 0
            or initial.st_size > 4096
            or getattr(initial, "st_file_attributes", 0) & 0x400
        ):
            raise _UnsafeScratch
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if sys.platform == "linux":
            flags |= getattr(os, "O_NOFOLLOW", 0)
            if not getattr(os, "O_NOFOLLOW", 0):
                raise _UnsafeScratch
        else:
            flags |= getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags)
        try:
            held = os.fstat(fd)
            opened = (int(held.st_dev), int(held.st_ino), int(held.st_size))
            path_id = (int(initial.st_dev), int(initial.st_ino), int(initial.st_size))
            if opened != path_id or opened[1] <= 0:
                raise _UnsafeScratch
            if os.read(fd, 4097) != checkpoint._entry(parent, name):
                raise _UnsafeScratch
        finally:
            os.close(fd)
        observed.append((name, opened))
    return tuple(observed)


def _answer(
    state: PrivateCustodyReentryState,
    *,
    scenario: str = "none",
    stable: bool = False,
    identity: bool = False,
    changed: bool = False,
    processes: int = 0,
) -> PrivateCustodyReentryReview:
    return PrivateCustodyReentryReview(
        state=state,
        scenario=scenario,
        native_parent_handle_retained_across_inspection=stable,
        independent_producer_hard_exit_observed=stable,
        independent_read_only_inspector_observed=stable,
        exact_bytes_inspector_unchanged=stable,
        watched_entry_identity_checked=stable,
        equal_bytes_identity_substitution_detected=identity,
        content_conflict_detected=changed,
        pending_journal_retained=stable,
        independent_interpreters=processes,
    )


def probe_disposable_custody_reentry(
    scenario: PrivateCustodyReentryScenario,
) -> PrivateCustodyReentryReview:
    """Retain a real parent handle through fresh inspection; NEVER recover.

    A noncooperating same-byte substitution is detected against the identity
    observed after producer exit. The journal is always held; no production
    mutation, replay or retirement is reachable from this diagnostic.
    """
    state = PrivateCustodyReentryState
    if type(scenario) is not PrivateCustodyReentryScenario:
        return _answer(state.INVALID_REQUEST_REFUSED)
    if sys.platform not in {"linux", "win32"}:
        return _answer(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _answer(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g97_custody_") as dirname:
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
            fresh._child(parent, "produce", _SCENARIO_CUT[scenario])
            with locking.hold_existing_private_lock(parent / checkpoint._LOCK):
                before_bytes = fresh._snapshot(parent)
                before_ids = _fingerprint(parent)
                if checkpoint._entry(parent, checkpoint._JOURNAL) is None:
                    raise _UnsafeScratch
            with custody._retain_native_parent(parent):
                target = _RIVAL_WATCH.get(scenario)
                if target is not None:
                    _independent_rival(
                        parent,
                        target,
                        equal_bytes=scenario
                        is not PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES,
                    )
                after_rival = fresh._snapshot(parent)
                after_ids = _fingerprint(parent)
                _, inspected = fresh._child(parent, "inspect", _SCENARIO_CUT[scenario])
                if (
                    fresh._snapshot(parent) != after_rival
                    or _fingerprint(parent) != after_ids
                ):
                    raise _UnsafeScratch
                if checkpoint._entry(parent, checkpoint._JOURNAL) is None:
                    raise _UnsafeScratch
                expected_phase = (
                    ("complete_hold", "both_pending_review")
                    if scenario is PrivateCustodyReentryScenario.STABLE_BOTH_PENDING
                    else ("ready_registry", "prepared")
                    if scenario
                    is PrivateCustodyReentryScenario.EQUAL_BYTES_STAGE_SUBSTITUTION
                    else ("conflict_preserve", "registry_intent")
                    if scenario is PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES
                    else ("confirm_registry", "registry_intent")
                )
                if (inspected["decision"], inspected["phase"]) != expected_phase:
                    raise _UnsafeScratch
                same_bytes = before_bytes == after_rival
                # Content changes can change st_size without changing the
                # underlying file identity. Compare (device, inode) only.
                different_id = tuple(
                    (name, None if item is None else item[:2])
                    for name, item in before_ids
                ) != tuple(
                    (name, None if item is None else item[:2])
                    for name, item in after_ids
                )
                if scenario in {
                    PrivateCustodyReentryScenario.EQUAL_BYTES_LIVE_SUBSTITUTION,
                    PrivateCustodyReentryScenario.EQUAL_BYTES_STAGE_SUBSTITUTION,
                    PrivateCustodyReentryScenario.EQUAL_BYTES_JOURNAL_SUBSTITUTION,
                }:
                    if not same_bytes or not different_id:
                        raise _UnsafeScratch
                    selected = state.SAME_BYTES_IDENTITY_DRIFT_HOLD
                elif scenario is PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES:
                    if same_bytes or different_id:
                        raise _UnsafeScratch
                    selected = state.CONTENT_CONFLICT_HOLD
                else:
                    if not same_bytes or different_id:
                        raise _UnsafeScratch
                    selected = (
                        state.STABLE_PENDING_MANUAL_HOLD
                        if scenario is PrivateCustodyReentryScenario.STABLE_BOTH_PENDING
                        else state.STABLE_UNCERTAIN_HOLD
                    )
            return _answer(
                selected,
                scenario=scenario.value,
                stable=True,
                identity=selected is state.SAME_BYTES_IDENTITY_DRIFT_HOLD,
                changed=selected is state.CONTENT_CONFLICT_HOLD,
                processes=3 if target is not None else 2,
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
        custody._UnsafeScratch,
        locking.PrivateExistingFileLockError,
    ):
        return _answer(state.NATIVE_CUSTODY_REFUSED)
