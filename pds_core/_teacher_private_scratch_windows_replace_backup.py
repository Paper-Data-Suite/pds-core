"""Core #238 Slice 3G92: Windows ReplaceFileW backup, disposable-only.

This diagnostic creates its own random scratch directory, fixed filenames and
fixed synthetic byte images. The caller supplies only one fixed scenario enum;
no real workspace, private root, intent, payload, handle or callback enters.
ReplaceFileW creates a backup on the same volume, but remains path-based and
is neither a kernel content-CAS nor a multi-document durable transaction.
"""

from __future__ import annotations

import ctypes
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_native_writer_window as custody


class PrivateWindowsReplaceBackupScenario(str, Enum):
    NORMAL_BACKUP = "normal_backup"
    LIVE_PREIMAGE_DRIFT = "live_preimage_drift"
    STAGE_PREIMAGE_DRIFT = "stage_preimage_drift"


class PrivateWindowsReplaceBackupState(str, Enum):
    NATIVE_BACKUP_PRESERVED_SCRATCH_ONLY = "native_backup_preserved_scratch_only"
    LIVE_DRIFT_REFUSED = "live_drift_refused"
    STAGE_DRIFT_REFUSED = "stage_drift_refused"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    LINUX_WINDOWS_PROTOCOL_UNQUALIFIED = "linux_windows_protocol_unqualified"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    NATIVE_BACKUP_REFUSED = "native_backup_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateWindowsReplaceBackupReview:
    state: PrivateWindowsReplaceBackupState
    native_parent_retained_during_operation: bool = False
    cooperative_lock_held: bool = False
    exact_preimages_rechecked: bool = False
    native_replacefile_called: bool = False
    original_backup_verified: bool = False
    new_registry_verified: bool = False
    synthetic_journal_preserved: bool = False
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
        return "PrivateWindowsReplaceBackupReview(disposable_only=True, non_authorizing=True)"


def _result(
    state: PrivateWindowsReplaceBackupState,
    *,
    retained: bool = False,
    checked: bool = False,
    called: bool = False,
    backup: bool = False,
    new: bool = False,
    journal: bool = False,
) -> PrivateWindowsReplaceBackupReview:
    return PrivateWindowsReplaceBackupReview(
        state=state,
        native_parent_retained_during_operation=retained,
        cooperative_lock_held=retained,
        exact_preimages_rechecked=checked,
        native_replacefile_called=called,
        original_backup_verified=backup,
        new_registry_verified=new,
        synthetic_journal_preserved=journal,
    )


class _UnsafeScratch(Exception):
    """Refuse a synthetic operation without disclosing a native path or SID."""


def _replace_with_native_backup(registry: Path, stage: Path, backup: Path) -> None:
    """Windows-only ReplaceFileW, with an explicit backup name, no fallback."""
    if sys.platform != "win32":
        raise _UnsafeScratch
    from ctypes import wintypes

    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise _UnsafeScratch
    kernel = loader("kernel32", use_last_error=True)
    kernel.ReplaceFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    kernel.ReplaceFileW.restype = wintypes.BOOL
    # 0 flags: preserve the documented failure behavior. The three paths
    # have fixed names within one freshly created disposable directory.
    if not kernel.ReplaceFileW(str(registry), str(stage), str(backup), 0, None, None):
        # ReplaceFileW has several partial-failure states (1175/1176/1177).
        # Never interpret an error as an unchanged directory or retry here.
        raise _UnsafeScratch


def probe_windows_disposable_replace_backup(
    scenario: PrivateWindowsReplaceBackupScenario,
) -> PrivateWindowsReplaceBackupReview:
    """Measure a native backup and exact images in scratch, never live storage.

    The operation intentionally retains a native parent identity and a
    cooperative lock, but uses path-named ReplaceFileW. Neither a successful
    backup nor exact postimages proves content-CAS or crash recoverability.
    """
    state = PrivateWindowsReplaceBackupState
    if type(scenario) is not PrivateWindowsReplaceBackupScenario:
        return _result(state.INVALID_REQUEST_REFUSED)
    if sys.platform == "linux":
        return _result(state.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED)
    if sys.platform != "win32":
        return _result(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _result(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g92_winbackup_") as name:
            parent = Path(name) / "target"
            parent.mkdir()
            registry = parent / "registry.json"
            stage = parent / "registry.stage"
            backup = parent / "registry.previous"
            journal = parent / "pending-journal.json"
            lock = parent / ".registry.lock"
            before = b"synthetic-registry-before-3g92"
            after = b"synthetic-registry-after-3g92"
            pending = b"synthetic-journal-pending-3g92"
            registry.write_bytes(before)
            stage.write_bytes(after)
            journal.write_bytes(pending)
            lock.write_bytes(b"0")
            if backup.exists() or backup.is_symlink():
                raise _UnsafeScratch
            with locking.hold_existing_private_lock(lock):
                with custody._retain_native_parent(parent):
                    if (
                        custody._image(registry) != before
                        or custody._image(stage) != after
                        or custody._image(journal) != pending
                    ):
                        raise _UnsafeScratch
                    if (
                        scenario
                        is PrivateWindowsReplaceBackupScenario.LIVE_PREIMAGE_DRIFT
                    ):
                        registry.write_bytes(b"synthetic-conflicting-registry")
                    elif (
                        scenario
                        is PrivateWindowsReplaceBackupScenario.STAGE_PREIMAGE_DRIFT
                    ):
                        stage.write_bytes(b"synthetic-conflicting-stage")
                    if custody._image(registry) != before:
                        return _result(
                            state.LIVE_DRIFT_REFUSED,
                            retained=True,
                            checked=True,
                            journal=custody._image(journal) == pending,
                        )
                    if custody._image(stage) != after:
                        return _result(
                            state.STAGE_DRIFT_REFUSED,
                            retained=True,
                            checked=True,
                            journal=custody._image(journal) == pending,
                        )
                    if custody._image(journal) != pending or backup.exists():
                        raise _UnsafeScratch
                    _replace_with_native_backup(registry, stage, backup)
                    verified = (
                        custody._image(registry) == after
                        and not stage.exists()
                        and custody._image(backup) == before
                        and custody._image(journal) == pending
                    )
                    if not verified:
                        raise _UnsafeScratch
                    return _result(
                        state.NATIVE_BACKUP_PRESERVED_SCRATCH_ONLY,
                        retained=True,
                        checked=True,
                        called=True,
                        backup=True,
                        new=True,
                        journal=True,
                    )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
        _UnsafeScratch,
        custody._UnsafeScratch,
    ):
        return _result(state.NATIVE_BACKUP_REFUSED)
