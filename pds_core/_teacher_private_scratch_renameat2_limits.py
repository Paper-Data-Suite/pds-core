"""Core #238 3G90: Linux renameat2 limits, disposable synthetic files only.

No public path, handle, payload, transaction or callback is accepted. Both
RENAME_NOREPLACE and RENAME_EXCHANGE are native filename conditions, not an
atomic assertion about previously observed file identity or content. Never
qualifies production mutation or Notes availability.
"""

from __future__ import annotations

import ctypes
import errno
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


class PrivateRenameat2Scenario(str, Enum):
    NOREPLACE_EXISTING = "noreplace_existing"
    EXCHANGE_TWO_PRESENT = "exchange_two_present"
    EXCHANGE_AFTER_RIVAL = "exchange_after_rival"


class PrivateRenameat2State(str, Enum):
    NOREPLACE_EXISTING_REFUSED = "noreplace_existing_refused"
    EXCHANGE_SCRATCH_ONLY = "exchange_scratch_only"
    EXCHANGE_AFTER_RIVAL_NO_CAS = "exchange_after_rival_no_cas"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    WINDOWS_PROTOCOL_UNQUALIFIED = "windows_protocol_unqualified"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    SCRATCH_REFUSED = "scratch_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateRenameat2Review:
    state: PrivateRenameat2State
    native_linux_flags_exercised: bool = False
    directory_fd_retained: bool = False
    expected_native_condition_observed: bool = False
    independent_same_owner_swap_observed: bool = False
    exact_disposable_postimages_verified: bool = False
    synthetic_journal_preserved: bool = False
    atomic_content_cas_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    production_mutation_admitted: bool = False
    native_windows_replace_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateRenameat2Review(disposable_only=True, non_authorizing=True)"


def _result(
    state: PrivateRenameat2State,
    *,
    exercised: bool = False,
    retained: bool = False,
    condition: bool = False,
    rival: bool = False,
    verified: bool = False,
    journal: bool = False,
) -> PrivateRenameat2Review:
    return PrivateRenameat2Review(
        state=state,
        native_linux_flags_exercised=exercised,
        directory_fd_retained=retained,
        expected_native_condition_observed=condition,
        independent_same_owner_swap_observed=rival,
        exact_disposable_postimages_verified=verified,
        synthetic_journal_preserved=journal,
    )


class _UnsafeScratch(Exception):
    """Sanitized refusal: never embed a native path or owner identifier."""


_RENAME_NOREPLACE = 1
_RENAME_EXCHANGE = 2


def _renameat2(fd: int, source: bytes, target: bytes, flag: int) -> int:
    """Call glibc renameat2 with two retained dirfds, return 0 or errno."""
    if flag not in {_RENAME_NOREPLACE, _RENAME_EXCHANGE}:
        raise _UnsafeScratch
    libc = ctypes.CDLL(None, use_errno=True)
    fn = getattr(libc, "renameat2", None)
    if fn is None:
        raise _UnsafeScratch
    fn.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    fn.restype = ctypes.c_int
    ctypes.set_errno(0)
    status = fn(fd, source, fd, target, flag)
    if status == 0:
        return 0
    code = ctypes.get_errno()
    if code in {errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL}:
        raise _UnsafeScratch
    return code


_RIVAL = """
import os,sys
from pathlib import Path
p=Path(sys.argv[1]); fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
    os.replace('decoy','registry.json',src_dir_fd=fd,dst_dir_fd=fd)
finally:
    os.close(fd)
print('SCRATCH_RIVAL_EXCHANGED')
"""


def _rival(parent: Path) -> None:
    child = subprocess.run(
        [sys.executable, "-I", "-c", _RIVAL, str(parent)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if (
        child.returncode != 0
        or child.stdout.strip() != "SCRATCH_RIVAL_EXCHANGED"
        or child.stderr
    ):
        raise _UnsafeScratch


def probe_linux_renameat2_limits(
    scenario: PrivateRenameat2Scenario,
) -> PrivateRenameat2Review:
    """Measure native filename flag guarantees without granting any write permit."""
    state = PrivateRenameat2State
    if type(scenario) is not PrivateRenameat2Scenario:
        return _result(state.INVALID_REQUEST_REFUSED)
    if sys.platform == "win32":
        return _result(state.WINDOWS_PROTOCOL_UNQUALIFIED)
    if sys.platform != "linux" or not (
        hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")
    ):
        return _result(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _result(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        native._effective_uid()  # ordinary effective OS user, root refused
        with tempfile.TemporaryDirectory(prefix="pds238_3g90_renameat2_") as dirname:
            parent = Path(dirname) / "target"
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
                    ):
                        native._write_exclusive(fd, name, payload)
                    live = native._read_entry(fd, native._LIVE)
                    staged = native._read_entry(fd, native._STAGE)
                    journal = native._read_entry(fd, native._JOURNAL)
                    if (live[1], staged[1], journal[1]) != (
                        native._BEFORE,
                        native._AFTER,
                        native._PENDING,
                    ):
                        raise _UnsafeScratch
                    rival = scenario is PrivateRenameat2Scenario.EXCHANGE_AFTER_RIVAL
                    if rival:
                        native._write_exclusive(fd, "decoy", native._BEFORE)
                        _rival(parent)
                        changed = native._read_entry(fd, native._LIVE)
                        if changed[1] != live[1] or changed[0][:2] == live[0][:2]:
                            raise _UnsafeScratch
                    if not native._parent_ok(fd, parent):
                        raise _UnsafeScratch
                    flag = (
                        _RENAME_NOREPLACE
                        if scenario is PrivateRenameat2Scenario.NOREPLACE_EXISTING
                        else _RENAME_EXCHANGE
                    )
                    code = _renameat2(fd, b"registry.stage", b"registry.json", flag)
                    if not native._parent_ok(fd, parent):
                        raise _UnsafeScratch
                    if native._read_entry(fd, native._JOURNAL) != journal:
                        raise _UnsafeScratch
                    if flag == _RENAME_NOREPLACE:
                        if code != errno.EEXIST or (
                            native._read_entry(fd, native._LIVE) != live
                            or native._read_entry(fd, native._STAGE) != staged
                        ):
                            raise _UnsafeScratch
                        return _result(
                            state.NOREPLACE_EXISTING_REFUSED,
                            exercised=True,
                            retained=True,
                            condition=True,
                            verified=True,
                            journal=True,
                        )
                    if code != 0:
                        raise _UnsafeScratch
                    now_live = native._read_entry(fd, native._LIVE)
                    now_stage = native._read_entry(fd, native._STAGE)
                    if now_live != staged or now_stage[1] != native._BEFORE:
                        raise _UnsafeScratch
                    if rival:
                        if now_stage[0][:2] == live[0][:2]:
                            raise _UnsafeScratch
                    elif now_stage != live:
                        raise _UnsafeScratch
                    return _result(
                        state.EXCHANGE_AFTER_RIVAL_NO_CAS
                        if rival
                        else state.EXCHANGE_SCRATCH_ONLY,
                        exercised=True,
                        retained=True,
                        condition=True,
                        rival=rival,
                        verified=True,
                        journal=True,
                    )
                finally:
                    os.close(fd)
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        subprocess.TimeoutExpired,
        _UnsafeScratch,
        native._UnsafeScratch,
    ):
        return _result(state.SCRATCH_REFUSED)
