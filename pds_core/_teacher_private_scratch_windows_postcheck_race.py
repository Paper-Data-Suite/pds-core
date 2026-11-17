"""Core #238 3G93: Windows ReplaceFileW postcheck race, scratch-only.

A child process deliberately replaces an equal-content live or staged entry
AFTER the writer's final precheck and BEFORE a path-based ReplaceFileW call.
The successful afterimage and backup cannot establish an atomic content-CAS.
Only fixed synthetic names/bytes in a fresh disposable directory are touched.
No caller path, handle, intent, writer callback or production authority exists.
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
from pds_core import _teacher_private_scratch_native_writer_window as custody
from pds_core import _teacher_private_scratch_windows_replace_backup as replace_native


class PrivateWindowsPostcheckRaceScenario(str, Enum):
    NORMAL = "normal"
    LIVE_SWAP_AFTER_CHECK = "live_swap_after_check"
    STAGE_SWAP_AFTER_CHECK = "stage_swap_after_check"


class PrivateWindowsPostcheckRaceState(str, Enum):
    NORMAL_BACKUP_NONAUTHORIZING = "normal_backup_nonauthorizing"
    LIVE_POSTCHECK_TOCTOU_DEMONSTRATED = "live_postcheck_toctou_demonstrated"
    STAGE_POSTCHECK_TOCTOU_DEMONSTRATED = "stage_postcheck_toctou_demonstrated"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    LINUX_WINDOWS_PROTOCOL_UNQUALIFIED = "linux_windows_protocol_unqualified"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    SCRATCH_CUSTODY_REFUSED = "scratch_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateWindowsPostcheckRaceReview:
    state: PrivateWindowsPostcheckRaceState
    native_directory_handle_retained: bool = False
    cooperative_lock_held_during_race: bool = False
    final_exact_precheck_before_rival: bool = False
    independent_uncooperative_interpreter_observed: bool = False
    same_bytes_new_file_identity_after_precheck: bool = False
    native_replacefile_called_after_race: bool = False
    exact_backup_afterimage_verified: bool = False
    exact_new_registry_afterimage_verified: bool = False
    synthetic_pending_journal_preserved: bool = False
    production_mutation_admitted: bool = False
    windows_handle_relative_replace_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    atomic_content_compare_and_swap_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateWindowsPostcheckRaceReview(disposable_only=True, non_authorizing=True)"


def _result(
    state: PrivateWindowsPostcheckRaceState,
    *,
    retained: bool = False,
    checked: bool = False,
    rival: bool = False,
    drift: bool = False,
    called: bool = False,
    backup: bool = False,
    after: bool = False,
    journal: bool = False,
) -> PrivateWindowsPostcheckRaceReview:
    return PrivateWindowsPostcheckRaceReview(
        state=state,
        native_directory_handle_retained=retained,
        cooperative_lock_held_during_race=retained,
        final_exact_precheck_before_rival=checked,
        independent_uncooperative_interpreter_observed=rival,
        same_bytes_new_file_identity_after_precheck=drift,
        native_replacefile_called_after_race=called,
        exact_backup_afterimage_verified=backup,
        exact_new_registry_afterimage_verified=after,
        synthetic_pending_journal_preserved=journal,
    )


class _UnsafeScratch(Exception):
    """Refusal with no native path or identity in its public result."""


# The child receives only this invocation's freshly allocated scratch parent.
# Its target choice is from a fixed string set, and it ignores the lock file.
_RIVAL = """
import os,sys
from pathlib import Path
parent=Path(sys.argv[1]); kind=sys.argv[2]
if kind not in ('live','stage'):
    raise SystemExit(3)
src='decoy-live' if kind=='live' else 'decoy-stage'
dst='registry.json' if kind=='live' else 'registry.stage'
os.replace(parent/src,parent/dst)
print('SCRATCH_RIVAL_REPLACED')
"""


def _run_rival(parent: Path, kind: str) -> None:
    if kind not in {"live", "stage"}:
        raise _UnsafeScratch
    result = subprocess.run(
        [sys.executable, "-I", "-c", _RIVAL, str(parent), kind],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if (
        result.returncode != 0
        or result.stdout.strip() != "SCRATCH_RIVAL_REPLACED"
        or result.stderr.strip()
    ):
        raise _UnsafeScratch


def _identity(path: Path) -> tuple[int, int]:
    info = os.stat(path, follow_symlinks=False)
    if not path.is_file() or path.is_symlink() or info.st_ino <= 0:
        raise _UnsafeScratch
    return info.st_dev, info.st_ino


def probe_windows_disposable_postcheck_race(
    scenario: PrivateWindowsPostcheckRaceScenario,
) -> PrivateWindowsPostcheckRaceReview:
    """Demonstrate a Windows path-based ReplaceFileW precheck race in scratch.

    Deliberately continues after observing changed identity in the adversarial
    cases to demonstrate the non-CAS property. This is NEVER a recovery writer.
    """
    state = PrivateWindowsPostcheckRaceState
    if type(scenario) is not PrivateWindowsPostcheckRaceScenario:
        return _result(state.INVALID_REQUEST_REFUSED)
    if sys.platform == "linux":
        return _result(state.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED)
    if sys.platform != "win32":
        return _result(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _result(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g93_winrace_") as dirname:
            parent = Path(dirname) / "target"
            parent.mkdir()
            live = parent / "registry.json"
            stage = parent / "registry.stage"
            backup = parent / "registry.previous"
            journal = parent / "pending-journal.json"
            lock = parent / ".registry.lock"
            before = b"synthetic-registry-before-3g93"
            after = b"synthetic-registry-after-3g93"
            pending = b"synthetic-journal-pending-3g93"
            live.write_bytes(before)
            stage.write_bytes(after)
            journal.write_bytes(pending)
            lock.write_bytes(b"0")
            if backup.exists() or backup.is_symlink():
                raise _UnsafeScratch
            with locking.hold_existing_private_lock(lock):
                with custody._retain_native_parent(parent):
                    first_live = _identity(live)
                    first_stage = _identity(stage)
                    if (
                        custody._image(live) != before
                        or custody._image(stage) != after
                        or custody._image(journal) != pending
                    ):
                        raise _UnsafeScratch
                    # The last trusted observations happen before the child.
                    if (
                        _identity(live) != first_live
                        or _identity(stage) != first_stage
                        or custody._image(live) != before
                        or custody._image(stage) != after
                        or custody._image(journal) != pending
                    ):
                        raise _UnsafeScratch
                    target = (
                        "live"
                        if scenario
                        is PrivateWindowsPostcheckRaceScenario.LIVE_SWAP_AFTER_CHECK
                        else "stage"
                        if scenario
                        is PrivateWindowsPostcheckRaceScenario.STAGE_SWAP_AFTER_CHECK
                        else None
                    )
                    changed = False
                    if target is not None:
                        decoy = parent / (
                            "decoy-live" if target == "live" else "decoy-stage"
                        )
                        decoy.write_bytes(before if target == "live" else after)
                        target_path = live if target == "live" else stage
                        old_identity = first_live if target == "live" else first_stage
                        if _identity(decoy) == old_identity:
                            raise _UnsafeScratch
                        _run_rival(parent, target)
                        changed = _identity(
                            target_path
                        ) != old_identity and custody._image(target_path) == (
                            before if target == "live" else after
                        )
                        if not changed or decoy.exists():
                            raise _UnsafeScratch
                    # Deliberately no new qualifying precheck (scratch only).
                    replace_native._replace_with_native_backup(live, stage, backup)
                    if (
                        custody._image(live) != after
                        or stage.exists()
                        or custody._image(backup) != before
                        or custody._image(journal) != pending
                    ):
                        raise _UnsafeScratch
                    return _result(
                        state.LIVE_POSTCHECK_TOCTOU_DEMONSTRATED
                        if target == "live"
                        else state.STAGE_POSTCHECK_TOCTOU_DEMONSTRATED
                        if target == "stage"
                        else state.NORMAL_BACKUP_NONAUTHORIZING,
                        retained=True,
                        checked=True,
                        rival=target is not None,
                        drift=changed,
                        called=True,
                        backup=True,
                        after=True,
                        journal=True,
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
        replace_native._UnsafeScratch,
        custody._UnsafeScratch,
    ):
        return _result(state.SCRATCH_CUSTODY_REFUSED)
