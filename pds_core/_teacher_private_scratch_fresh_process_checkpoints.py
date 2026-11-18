"""Core #238 Slice 3G95: fresh-interpreter checkpoint recovery, scratch-only.

Only an exact enum is accepted. Every child receives internally constructed
paths to a newly allocated synthetic scratch directory and a trusted Python
module root. Producer exits via os._exit; independent inspector and explicit
recovery processes re-open the journal and files. No teacher workspace, private
root, user data, credential, callback, live journal or production permit exists.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_checkpoint_protocol as previous


class PrivateFreshCheckpointScenario(str, Enum):
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


class PrivateFreshCheckpointState(str, Enum):
    EXPLICIT_FRESH_PROCESS_RESUMED_PENDING_HOLD = (
        "explicit_fresh_process_resumed_pending_hold"
    )
    ALREADY_COMPLETE_PENDING_HOLD = "already_complete_pending_hold"
    CONFLICT_EVIDENCE_PRESERVED_HOLD = "conflict_evidence_preserved_hold"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    SCRATCH_CUSTODY_REFUSED = "scratch_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateFreshCheckpointReview:
    state: PrivateFreshCheckpointState
    interrupted_checkpoint: str = "none"
    independent_producer_hard_exit_observed: bool = False
    independent_read_only_inspector_observed: bool = False
    inspector_left_evidence_unchanged: bool = False
    independent_explicit_recovery_observed: bool = False
    exact_synthetic_afterimages_verified: bool = False
    second_recovery_noop: bool = False
    conflict_evidence_preserved: bool = False
    journal_remains_pending: bool = False
    independent_python_interpreters: int = 0
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
        return "PrivateFreshCheckpointReview(scratch_only=True, non_authorizing=True)"


class _UnsafeScratch(Exception):
    """Never disclose a scratch pathname, OS identity or payload in results."""


_CUTS = tuple(s.value for s in previous._CUTS)
_CONFLICTS = frozenset(
    (
        "conflict_journal",
        "conflict_registry",
        "conflict_stage",
        "conflict_checkpoint_temp",
    )
)
_FILES = (
    previous._REGISTRY,
    previous._DESCRIPTOR,
    previous._REGISTRY_STAGE,
    previous._DESCRIPTOR_STAGE,
    previous._JOURNAL,
    previous._NEXT,
)
_INSPECTION = (
    ("ready_registry", "prepared"),
    ("ready_registry", "registry_intent"),
    ("confirm_registry", "registry_intent"),
    ("ready_descriptor", "registry_done"),
    ("ready_descriptor", "descriptor_intent"),
    ("confirm_descriptor", "descriptor_intent"),
    ("complete_hold", "both_pending_review"),
)

# -I disables unsafe interpreter search paths; the package root is derived from
# this module's own __file__ (never from a caller argument). Child output is a
# fixed, bounded JSON decision; no path or private contents are ever printed.
_CHILD = r"""
import json,os,sys
from pathlib import Path
module_root,operation,parent_path,scenario=sys.argv[1:]
if operation not in ('produce','inspect','recover') or scenario not in (
    'prepared','registry_intent','registry_installed','registry_confirmed',
    'descriptor_intent','descriptor_installed','both_pending_review',
    'conflict_journal','conflict_registry','conflict_stage','conflict_checkpoint_temp'):
    raise SystemExit(3)
sys.path.insert(0,module_root)
from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_scratch_checkpoint_protocol as p
parent=Path(parent_path)
with locking.hold_existing_private_lock(parent/p._LOCK):
    if operation=='produce':
        if p._observed(parent)!=('ready_registry','prepared'):
            raise SystemExit(4)
        cut=(
            ('prepared','registry_intent','registry_installed','registry_confirmed',
             'descriptor_intent','descriptor_installed','both_pending_review')
        )
        index=cut.index(scenario) if scenario in cut else 0
        for i in range(index):
            p._one_step(parent,i)
        # Hard process exit: context managers do not finish, unlike a return.
        os._exit(80+index)
    elif operation=='inspect':
        decision,phase=p._observed(parent)
        print(json.dumps({'decision':decision,'phase':phase},sort_keys=True),flush=True)
    else:
        steps,complete=p._explicit_resume(parent)
        decision,phase=p._observed(parent)
        print(json.dumps({'steps':steps,'complete':complete,'decision':decision,
                          'phase':phase},sort_keys=True),flush=True)
"""


def _snapshot(parent: Path) -> tuple[tuple[str, bytes | None], ...]:
    """Exact bounded scratch evidence; missing names are explicit None values."""
    names = {item.name for item in parent.iterdir()}
    if not names.issubset(set(_FILES) | {previous._LOCK}):
        raise _UnsafeScratch
    return tuple((name, previous._entry(parent, name)) for name in _FILES)


def _child(parent: Path, operation: str, scenario: str) -> tuple[int, dict[str, Any]]:
    if operation not in {"produce", "inspect", "recover"} or scenario not in (
        set(_CUTS) | _CONFLICTS
    ):
        raise _UnsafeScratch
    module_root = Path(__file__).resolve(strict=True).parent.parent
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _CHILD,
            str(module_root),
            operation,
            str(parent),
            scenario,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=20,
    )
    if proc.stderr.strip() or len(proc.stdout) > 256:
        raise _UnsafeScratch
    if operation == "produce":
        expected = 80 + (_CUTS.index(scenario) if scenario in _CUTS else 0)
        if proc.returncode != expected or proc.stdout:
            raise _UnsafeScratch
        return proc.returncode, {}
    if proc.returncode != 0:
        raise _UnsafeScratch
    try:
        data: Any = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise _UnsafeScratch from exc
    fields = (
        {"decision", "phase"}
        if operation == "inspect"
        else {"decision", "phase", "steps", "complete"}
    )
    if type(data) is not dict or set(data) != fields:
        raise _UnsafeScratch
    if data["decision"] not in {
        "ready_registry",
        "confirm_registry",
        "ready_descriptor",
        "confirm_descriptor",
        "complete_hold",
        "conflict_preserve",
    } or data["phase"] not in set(previous._PHASES) | {"none"}:
        raise _UnsafeScratch
    if operation == "recover" and (
        type(data["steps"]) is not int
        or not 0 <= data["steps"] <= 6
        or type(data["complete"]) is not bool
    ):
        raise _UnsafeScratch
    return proc.returncode, data


def _inject_conflict(parent: Path, scenario: PrivateFreshCheckpointScenario) -> None:
    if scenario is PrivateFreshCheckpointScenario.CONFLICT_JOURNAL:
        (parent / previous._JOURNAL).write_bytes(b"corrupt-journal")
    elif scenario is PrivateFreshCheckpointScenario.CONFLICT_REGISTRY:
        (parent / previous._REGISTRY).write_bytes(b"wrong-registry")
    elif scenario is PrivateFreshCheckpointScenario.CONFLICT_STAGE:
        (parent / previous._REGISTRY_STAGE).write_bytes(b"wrong-stage")
    elif scenario is PrivateFreshCheckpointScenario.CONFLICT_CHECKPOINT_TEMP:
        previous._exclusive(
            parent, previous._NEXT, previous._journal_bytes("registry_intent")
        )
    else:
        raise _UnsafeScratch


def _answer(
    state: PrivateFreshCheckpointState,
    *,
    cut: str = "none",
    inspect: bool = False,
    recovery: bool = False,
    complete: bool = False,
    noop: bool = False,
    conflict: bool = False,
    pending: bool = False,
    processes: int = 0,
) -> PrivateFreshCheckpointReview:
    return PrivateFreshCheckpointReview(
        state=state,
        interrupted_checkpoint=cut,
        independent_producer_hard_exit_observed=processes >= 1,
        independent_read_only_inspector_observed=inspect,
        inspector_left_evidence_unchanged=inspect,
        independent_explicit_recovery_observed=recovery,
        exact_synthetic_afterimages_verified=complete,
        second_recovery_noop=noop,
        conflict_evidence_preserved=conflict,
        journal_remains_pending=pending,
        independent_python_interpreters=processes,
    )


def probe_disposable_fresh_process_checkpoints(
    scenario: PrivateFreshCheckpointScenario,
) -> PrivateFreshCheckpointReview:
    """Fresh producer/inspector/recoverer on exact synthetic scratch evidence.

    The only public argument is a fixed scenario enum. No caller-selected paths,
    credentials, journal records, content, handles, or callback can enter.
    """
    state = PrivateFreshCheckpointState
    if type(scenario) is not PrivateFreshCheckpointScenario:
        return _answer(state.INVALID_REQUEST_REFUSED)
    if sys.platform not in {"linux", "win32"}:
        return _answer(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _answer(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        with tempfile.TemporaryDirectory(
            prefix="pds238_3g95_fresh_checkpoint_"
        ) as dirname:
            parent = Path(dirname) / "target"
            parent.mkdir(mode=0o700)
            for name, payload in (
                (previous._LOCK, b"0"),
                (previous._REGISTRY, previous._R0),
                (previous._DESCRIPTOR, previous._D0),
                (previous._REGISTRY_STAGE, previous._R1),
                (previous._DESCRIPTOR_STAGE, previous._D1),
                (previous._JOURNAL, previous._journal_bytes("prepared")),
            ):
                previous._exclusive(parent, name, payload)
            cut = scenario.value
            _child(parent, "produce", cut)
            if cut in _CONFLICTS:
                _inject_conflict(parent, scenario)
            before = _snapshot(parent)
            _, inspected = _child(parent, "inspect", cut)
            after_inspect = _snapshot(parent)
            if after_inspect != before:
                raise _UnsafeScratch
            expected = (
                (
                    "conflict_preserve",
                    "none"
                    if cut in {"conflict_journal", "conflict_checkpoint_temp"}
                    else "prepared",
                )
                if cut in _CONFLICTS
                else (_INSPECTION[_CUTS.index(cut)])
            )
            # A corrupt journal may still have a valid surrounding filesystem
            # but never authorizes mutation or interpretation as a new state.
            if (inspected["decision"], inspected["phase"]) != expected:
                raise _UnsafeScratch
            _, resumed = _child(parent, "recover", cut)
            if cut in _CONFLICTS:
                if resumed != {
                    "decision": expected[0],
                    "phase": expected[1],
                    "steps": 0,
                    "complete": False,
                }:
                    raise _UnsafeScratch
                if (
                    _snapshot(parent) != before
                    or previous._entry(parent, previous._JOURNAL) is None
                ):
                    raise _UnsafeScratch
                return _answer(
                    state.CONFLICT_EVIDENCE_PRESERVED_HOLD,
                    cut=cut,
                    inspect=True,
                    recovery=True,
                    conflict=True,
                    pending=True,
                    processes=3,
                )
            index = _CUTS.index(cut)
            if resumed != {
                "decision": "complete_hold",
                "phase": "both_pending_review",
                "steps": 6 - index,
                "complete": True,
            }:
                raise _UnsafeScratch
            if previous._observed(parent) != (
                "complete_hold",
                "both_pending_review",
            ) or (
                previous._entry(parent, previous._REGISTRY) != previous._R1
                or previous._entry(parent, previous._DESCRIPTOR) != previous._D1
                or previous._entry(parent, previous._REGISTRY_STAGE) is not None
                or previous._entry(parent, previous._DESCRIPTOR_STAGE) is not None
                or previous._entry(parent, previous._NEXT) is not None
                or previous._entry(parent, previous._JOURNAL)
                != previous._journal_bytes("both_pending_review")
            ):
                raise _UnsafeScratch
            first = _snapshot(parent)
            _, repeated = _child(parent, "recover", cut)
            if (
                repeated
                != {
                    "decision": "complete_hold",
                    "phase": "both_pending_review",
                    "steps": 0,
                    "complete": True,
                }
                or _snapshot(parent) != first
            ):
                raise _UnsafeScratch
            return _answer(
                state.ALREADY_COMPLETE_PENDING_HOLD
                if index == 6
                else state.EXPLICIT_FRESH_PROCESS_RESUMED_PENDING_HOLD,
                cut=cut,
                inspect=True,
                recovery=True,
                complete=True,
                noop=True,
                pending=True,
                processes=4,
            )
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        subprocess.TimeoutExpired,
        _UnsafeScratch,
        previous._UnsafeScratch,
    ):
        return _answer(state.SCRATCH_CUSTODY_REFUSED)
