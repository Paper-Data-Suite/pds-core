"""Core #238 3G91: native Windows FILE_SHARE_DELETE scratch demonstration.

No untrusted path, payload, handle, transaction or callback enters this diagnostic.
An independent interpreter attempts to open a fixed disposable file with native
DELETE access while the parent holds a CreateFileW handle excluding delete share.
Only after the handle closes does the child open DELETE access and replace the
synthetic registry. This is NOT atomic CAS or any production write authorization.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_native_writer_window as custody


class PrivateWindowsDeleteShareScenario(str, Enum):
    LIVE_HANDLE_DENY_DELETE = "live_handle_deny_delete"
    STAGE_HANDLE_DENY_DELETE = "stage_handle_deny_delete"


class PrivateWindowsDeleteShareState(str, Enum):
    DELETE_SHARE_DENIED_THEN_RELEASED = "delete_share_denied_then_released"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    LINUX_WINDOWS_PROTOCOL_UNQUALIFIED = "linux_windows_protocol_unqualified"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    NATIVE_SHARING_REFUSED = "native_sharing_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateWindowsDeleteShareReview:
    state: PrivateWindowsDeleteShareState
    native_windows_handle_retained: bool = False
    native_directory_handle_retained: bool = False
    cooperating_lock_held: bool = False
    independent_writer_refused_while_handle_held: bool = False
    before_images_preserved_while_handle_held: bool = False
    same_writer_succeeded_after_close: bool = False
    synthetic_afterimage_verified: bool = False
    pending_synthetic_journal_preserved: bool = False
    production_mutation_admitted: bool = False
    windows_production_replace_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    atomic_content_compare_and_swap_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateWindowsDeleteShareReview(disposable_only=True, non_authorizing=True)"


def _answer(
    state: PrivateWindowsDeleteShareState,
    *,
    held: bool = False,
    blocked: bool = False,
    preserved: bool = False,
    released: bool = False,
    verified: bool = False,
    journal: bool = False,
) -> PrivateWindowsDeleteShareReview:
    return PrivateWindowsDeleteShareReview(
        state=state,
        native_windows_handle_retained=held,
        native_directory_handle_retained=held,
        cooperating_lock_held=held,
        independent_writer_refused_while_handle_held=blocked,
        before_images_preserved_while_handle_held=preserved,
        same_writer_succeeded_after_close=released,
        synthetic_afterimage_verified=verified,
        pending_synthetic_journal_preserved=journal,
    )


class _UnsafeScratch(Exception):
    """Synthetic refusal with no user path or OS identity in the result."""


@contextmanager
def _deny_delete_share(path: Path) -> Iterator[None]:
    """Retain an ordinary native Windows file handle without FILE_SHARE_DELETE.

    Desired access FILE_READ_ATTRIBUTES; share flags FILE_SHARE_READ|WRITE only.
    These precise flags are advisory for a future protocol, not sufficient to
    protect production against arbitrary same-owner handle/mutation activity.
    """
    if sys.platform != "win32":
        raise _UnsafeScratch
    from ctypes import wintypes

    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise _UnsafeScratch
    kernel = loader("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x0001, 0x3, None, 3, 0x80, None)
    invalid = ctypes.c_void_p(-1).value
    if handle is None or int(handle) == invalid:
        raise _UnsafeScratch
    try:
        yield
    finally:
        if not kernel.CloseHandle(handle):
            raise _UnsafeScratch


# Child receives only fixed paths created by this invocation's disposable scratch.
# A native DELETE-access request is an exact sharing-mode test; os.replace()
# itself may fail for other reasons and must not be treated as a proof of the
# CreateFileW share contract. Exactly two children run per scenario.
_CHILD = """
import ctypes,os,sys
from ctypes import wintypes
mode,watch,stage,registry=sys.argv[1:]
if mode not in ('held','released'):
    raise SystemExit(3)
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
kernel.CreateFileW.restype=wintypes.HANDLE
kernel.CloseHandle.argtypes=[wintypes.HANDLE]
kernel.CloseHandle.restype=wintypes.BOOL
# DELETE=0x00010000; FILE_SHARE_READ|WRITE|DELETE=0x7; OPEN_EXISTING=3.
handle=kernel.CreateFileW(watch,0x00010000,0x7,None,3,0x80,None)
if handle is None or int(handle)==ctypes.c_void_p(-1).value:
    code=ctypes.get_last_error()
    print('DELETE_ACCESS_SHARING_DENIED' if code==32 else 'OTHER_REFUSAL')
elif not kernel.CloseHandle(handle):
    print('OTHER_REFUSAL')
elif mode=='held':
    print('DELETE_ACCESS_UNEXPECTEDLY_GRANTED')
else:
    try:
        os.replace(stage,registry)
    except OSError:
        print('OTHER_REFUSAL')
    else:
        print('DELETE_ACCESS_GRANTED_AND_REPLACED')
"""


def _child_native_delete_access(
    watch: Path, stage: Path, registry: Path, mode: str
) -> str:
    if mode not in {"held", "released"}:
        raise _UnsafeScratch
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _CHILD,
            mode,
            str(watch),
            str(stage),
            str(registry),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if result.returncode != 0 or result.stderr.strip():
        raise _UnsafeScratch
    token = result.stdout.strip()
    if token not in {
        "DELETE_ACCESS_SHARING_DENIED",
        "DELETE_ACCESS_UNEXPECTEDLY_GRANTED",
        "DELETE_ACCESS_GRANTED_AND_REPLACED",
        "OTHER_REFUSAL",
    }:
        raise _UnsafeScratch
    return token


def probe_windows_disposable_delete_sharing(
    scenario: PrivateWindowsDeleteShareScenario,
) -> PrivateWindowsDeleteShareReview:
    """Observe refusal *while* a delete-denying native file handle is held.

    Any success is restricted to newly allocated scratch. A separate interpreter
    requests native DELETE access while the handle is open, then requests the
    same access and performs a replacement only after the handle closes. The
    latter must succeed to reject false positives from bad paths or ACLs. A native directory HANDLE and an OS
    cooperation lock span the entire experiment. No real workspace is opened.
    """
    state = PrivateWindowsDeleteShareState
    if type(scenario) is not PrivateWindowsDeleteShareScenario:
        return _answer(state.INVALID_REQUEST_REFUSED)
    if sys.platform == "linux":
        return _answer(state.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED)
    if sys.platform != "win32":
        return _answer(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _answer(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g91_winshare_") as name:
            parent = Path(name) / "target"
            parent.mkdir()
            registry = parent / "registry.json"
            stage = parent / "registry.stage"
            journal = parent / "pending-journal.json"
            lock = parent / ".registry.lock"
            before, after, pending = (
                b"synthetic-before-registry",
                b"synthetic-after-registry-2",
                b"synthetic-journal-pending",
            )
            registry.write_bytes(before)
            stage.write_bytes(after)
            journal.write_bytes(pending)
            lock.write_bytes(b"0")
            watch = (
                registry
                if scenario is PrivateWindowsDeleteShareScenario.LIVE_HANDLE_DENY_DELETE
                else stage
            )
            with locking.hold_existing_private_lock(lock):
                with custody._retain_native_parent(parent):
                    if (
                        registry.read_bytes() != before
                        or stage.read_bytes() != after
                        or journal.read_bytes() != pending
                    ):
                        raise _UnsafeScratch
                    with _deny_delete_share(watch):
                        denied = _child_native_delete_access(
                            watch, stage, registry, "held"
                        )
                        preserved = (
                            registry.read_bytes() == before
                            and stage.read_bytes() == after
                            and journal.read_bytes() == pending
                        )
                        if denied != "DELETE_ACCESS_SHARING_DENIED" or not preserved:
                            raise _UnsafeScratch
                    succeeded = _child_native_delete_access(
                        watch, stage, registry, "released"
                    )
                    verified = (
                        succeeded == "DELETE_ACCESS_GRANTED_AND_REPLACED"
                        and registry.read_bytes() == after
                        and not stage.exists()
                        and journal.read_bytes() == pending
                    )
                    if not verified:
                        raise _UnsafeScratch
                    return _answer(
                        state.DELETE_SHARE_DENIED_THEN_RELEASED,
                        held=True,
                        blocked=True,
                        preserved=True,
                        released=True,
                        verified=True,
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
        custody._UnsafeScratch,
    ):
        return _answer(state.NATIVE_SHARING_REFUSED)
