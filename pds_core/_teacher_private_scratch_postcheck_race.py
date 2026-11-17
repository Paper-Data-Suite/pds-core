"""Linux native dirfd precheck-to-replace race counterexample (#238 3G89).

Only fixed, synthetic files under a new owned temporary directory are used.
A separate interpreter ignores the cooperating lock and replaces one file with
an equal-byte but different-inode file *after* native precheck. The scratch
writer deliberately continues, to document why dirfd-relative replacement is
not a kernel content CAS. No production root, workspace, caller path, callback,
intent, owner label, or write permission can be supplied.
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
from pds_core import _teacher_private_scratch_dirfd_replace as native


class PrivatePostcheckRaceScenario(str, Enum):
    NORMAL = "normal"
    LIVE_SWAP_AFTER_CHECK = "live_swap_after_check"
    STAGE_SWAP_AFTER_CHECK = "stage_swap_after_check"


class PrivatePostcheckRaceState(str, Enum):
    NORMAL_SCRATCH_REPLACED_NONAUTHORIZING = "normal_scratch_replaced_nonauthorizing"
    LIVE_POSTCHECK_TOCTOU_DEMONSTRATED = "live_postcheck_toctou_demonstrated"
    STAGE_POSTCHECK_TOCTOU_DEMONSTRATED = "stage_postcheck_toctou_demonstrated"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    WINDOWS_NATIVE_PROTOCOL_UNQUALIFIED = "windows_native_protocol_unqualified"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    SCRATCH_CUSTODY_REFUSED = "scratch_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivatePostcheckRaceReview:
    state: PrivatePostcheckRaceState
    linux_directory_fd_retained: bool = False
    separate_uncooperative_interpreter_observed: bool = False
    cooperative_lock_held_during_race: bool = False
    exact_precheck_before_injected_race: bool = False
    same_byte_entry_identity_replaced_after_check: bool = False
    dirfd_replace_performed_after_race: bool = False
    synthetic_afterimage_verified: bool = False
    pending_synthetic_journal_preserved: bool = False
    production_mutation_admitted: bool = False
    exclusive_operation_owned_guard_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    atomic_content_compare_and_swap_qualified: bool = False
    windows_native_replace_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivatePostcheckRaceReview(disposable_only=True, non_authorizing=True)"


def _result(
    state: PrivatePostcheckRaceState,
    *,
    retained: bool = False,
    rival: bool = False,
    before: bool = False,
    drift: bool = False,
    replaced: bool = False,
    verified: bool = False,
    journal: bool = False,
) -> PrivatePostcheckRaceReview:
    return PrivatePostcheckRaceReview(
        state=state,
        linux_directory_fd_retained=retained,
        separate_uncooperative_interpreter_observed=rival,
        cooperative_lock_held_during_race=retained,
        exact_precheck_before_injected_race=before,
        same_byte_entry_identity_replaced_after_check=drift,
        dirfd_replace_performed_after_race=replaced,
        synthetic_afterimage_verified=verified,
        pending_synthetic_journal_preserved=journal,
    )


class _UnsafeScratch(Exception):
    """A path-free, non-recovering diagnostic refusal."""


# The child receives ONLY this invocation's newly created disposable directory.
# It ignores the lock file and swaps an equal-byte, separate-inode decoy onto
# one fixed scratch entry. It prints no private information or paths.
_UNCOOPERATIVE_CHILD = """
import os
import sys
from pathlib import Path
root = Path(sys.argv[1]); which = sys.argv[2]
if which not in ('live', 'stage'):
    raise SystemExit(3)
src = 'decoy-live' if which == 'live' else 'decoy-stage'
dst = 'registry.json' if which == 'live' else 'registry.stage'
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
fd = os.open(root, flags)
try:
    os.replace(src, dst, src_dir_fd=fd, dst_dir_fd=fd)
finally:
    os.close(fd)
print('SCRATCH_RIVAL_REPLACED')
"""


def _run_rival(parent: Path, target: str) -> bool:
    if target not in {"live", "stage"}:
        raise _UnsafeScratch
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _UNCOOPERATIVE_CHILD, str(parent), target],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    return (
        completed.returncode == 0
        and completed.stdout.strip() == "SCRATCH_RIVAL_REPLACED"
        and not completed.stderr.strip()
    )


def probe_linux_disposable_postcheck_race(
    scenario: PrivatePostcheckRaceScenario,
) -> PrivatePostcheckRaceReview:
    """Show the final-check-to-syscall race in bounded Linux synthetic scratch.

    In the adversarial cases the parent intentionally DOES NOT recheck after
    the rival's independent process: that is the weakness being characterized.
    The private root, actual registry and any teacher workspace are unreachable.
    Even a successful synthetic probe is a refusal of production write authority.
    """
    state = PrivatePostcheckRaceState
    if type(scenario) is not PrivatePostcheckRaceScenario:
        return _result(state.INVALID_REQUEST_REFUSED)
    if sys.platform == "win32":
        return _result(state.WINDOWS_NATIVE_PROTOCOL_UNQUALIFIED)
    if sys.platform != "linux" or not (
        hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")
    ):
        return _result(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _result(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        # The OS-user locality boundary is the same as 3G88: root is refused.
        native._effective_uid()
        with tempfile.TemporaryDirectory(prefix="pds238_3g89_postcheck_") as dirname:
            outer = Path(dirname)
            parent = outer / "target"
            parent.mkdir(mode=0o700)
            lock = parent / ".registry.lock"
            lock.write_bytes(b"0")
            lock.chmod(0o600)
            with locking.hold_existing_private_lock(lock):
                fd = os.open(
                    parent,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY")
                    | getattr(os, "O_NOFOLLOW")
                    | getattr(os, "O_CLOEXEC", 0),
                )
                try:
                    if not native._parent_ok(fd, parent):
                        raise _UnsafeScratch
                    for name, payload in (
                        (native._LIVE, native._BEFORE),
                        (native._STAGE, native._AFTER),
                        (native._JOURNAL, native._PENDING),
                        ("decoy-live", native._BEFORE),
                        ("decoy-stage", native._AFTER),
                    ):
                        native._write_exclusive(fd, name, payload)
                    first_live = native._read_entry(fd, native._LIVE)
                    first_stage = native._read_entry(fd, native._STAGE)
                    first_journal = native._read_entry(fd, native._JOURNAL)
                    if (
                        first_live[1] != native._BEFORE
                        or first_stage[1] != native._AFTER
                        or first_journal[1] != native._PENDING
                        or not native._parent_ok(fd, parent)
                    ):
                        raise _UnsafeScratch
                    # LAST trusted precheck: entries, identities and bytes all
                    # match before the separate process is allowed to race.
                    if (
                        native._read_entry(fd, native._LIVE) != first_live
                        or native._read_entry(fd, native._STAGE) != first_stage
                        or native._read_entry(fd, native._JOURNAL) != first_journal
                        or not native._parent_ok(fd, parent)
                    ):
                        raise _UnsafeScratch
                    target = (
                        "live"
                        if scenario
                        is PrivatePostcheckRaceScenario.LIVE_SWAP_AFTER_CHECK
                        else "stage"
                        if scenario
                        is PrivatePostcheckRaceScenario.STAGE_SWAP_AFTER_CHECK
                        else None
                    )
                    rival_observed = target is not None
                    changed = False
                    if target is not None:
                        if not _run_rival(parent, target):
                            raise _UnsafeScratch
                        entry_name = native._LIVE if target == "live" else native._STAGE
                        initial = first_live if target == "live" else first_stage
                        changed_entry = native._read_entry(fd, entry_name)
                        changed = changed_entry[1] == initial[1] and (
                            changed_entry[0][:2] != initial[0][:2]
                        )
                        if not changed:
                            raise _UnsafeScratch
                    # Deliberately continue (scratch only) after the rival's
                    # switch. This demonstrates the missing kernel CAS.
                    os.replace(
                        native._STAGE,
                        native._LIVE,
                        src_dir_fd=fd,
                        dst_dir_fd=fd,
                    )
                    os.fsync(fd)  # Request only; no durability claim.
                    final_live = native._read_entry(fd, native._LIVE)
                    final_journal = native._read_entry(fd, native._JOURNAL)
                    if (
                        not native._parent_ok(fd, parent)
                        or final_live[1] != native._AFTER
                        or final_journal != first_journal
                    ):
                        raise _UnsafeScratch
                    if target == "stage":
                        if final_live[0][:2] == first_stage[0][:2]:
                            raise _UnsafeScratch
                    elif final_live[0][:2] != first_stage[0][:2]:
                        raise _UnsafeScratch
                    try:
                        os.stat(native._STAGE, dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        raise _UnsafeScratch
                    observed_state = (
                        state.LIVE_POSTCHECK_TOCTOU_DEMONSTRATED
                        if target == "live"
                        else state.STAGE_POSTCHECK_TOCTOU_DEMONSTRATED
                        if target == "stage"
                        else state.NORMAL_SCRATCH_REPLACED_NONAUTHORIZING
                    )
                    return _result(
                        observed_state,
                        retained=True,
                        rival=rival_observed,
                        before=True,
                        drift=changed,
                        replaced=True,
                        verified=True,
                        journal=True,
                    )
                finally:
                    os.close(fd)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
        subprocess.TimeoutExpired,
        _UnsafeScratch,
        native._UnsafeScratch,
    ):
        return _result(state.SCRATCH_CUSTODY_REFUSED)
