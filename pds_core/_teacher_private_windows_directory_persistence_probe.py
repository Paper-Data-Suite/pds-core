"""Windows parent-directory persistence probe (Core #238 Slice 3G8).

Attempts one native directory-handle FlushFileBuffers ONLY inside the already
qualified local pending-journal + stage-absent observation. Windows and some
filesystems cannot flush a directory handle. Even a successful syscall cannot
prove power-loss durability of a prior registry rename or any multi-file CAS.

This is internal, opt-in, non-authorizing and must never retire a journal,
write private records, grant a binding, or expose Notes. No path/bytes/handle
or principal leaves this module.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as exclusive
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as reader
from pds_core import _teacher_private_stage_absence_checkpoint as absence
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateWindowsDirectoryPersistenceState(str, Enum):
    DIRECTORY_FLUSH_OBSERVED_DURABILITY_UNQUALIFIED = (
        "directory_flush_observed_durability_unqualified"
    )
    DIRECTORY_FLUSH_UNAVAILABLE_RECOVERY_REQUIRED = (
        "directory_flush_unavailable_recovery_required"
    )
    CHECKPOINT_UNQUALIFIED = "checkpoint_unqualified"
    NAMESPACE_UNQUALIFIED = "namespace_unqualified"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"


_MESSAGES = {
    PrivateWindowsDirectoryPersistenceState.DIRECTORY_FLUSH_OBSERVED_DURABILITY_UNQUALIFIED: (
        "Directory handle flush returned success; rename and crash durability remain unqualified."
    ),
    PrivateWindowsDirectoryPersistenceState.DIRECTORY_FLUSH_UNAVAILABLE_RECOVERY_REQUIRED: (
        "Directory flush was unsupported, refused or unverified; preserve pending recovery evidence."
    ),
    PrivateWindowsDirectoryPersistenceState.CHECKPOINT_UNQUALIFIED: (
        "Exact pending stage-absent registry after-image checkpoint not qualified."
    ),
    PrivateWindowsDirectoryPersistenceState.NAMESPACE_UNQUALIFIED: (
        "Pending transaction or registry-stage namespace changed or is unqualified."
    ),
    PrivateWindowsDirectoryPersistenceState.INVALID_REQUEST: "Invalid directory persistence probe request.",
    PrivateWindowsDirectoryPersistenceState.UNSUPPORTED: "Directory persistence probe unsupported.",
    PrivateWindowsDirectoryPersistenceState.OWNER_CHANGED: "Effective OS owner changed during probe.",
    PrivateWindowsDirectoryPersistenceState.GUARD_REFUSED: "Retained native guard refused the probe.",
}


@dataclass(frozen=True, slots=True)
class PrivateWindowsDirectoryPersistenceReview:
    """Sanitized, read-only advisory: never a durability token."""

    state: PrivateWindowsDirectoryPersistenceState
    message: str


def _result(
    state: PrivateWindowsDirectoryPersistenceState,
) -> PrivateWindowsDirectoryPersistenceReview:
    return PrivateWindowsDirectoryPersistenceReview(state, _MESSAGES[state])


def _directory_identity(
    kernel: Any, advapi: Any, handle: int, owner: inspection.EffectiveOSOwner
) -> tuple[int, bytes] | None:
    """Verify a native protected directory; no reparse point or delete-pending entry."""
    identity = anchor._windows_id(kernel, handle)
    info = descriptor._windows_info(kernel, handle)
    if (
        identity is None
        or not any(identity[1])
        or info is None
        or not (info[0] & 0x10)
        or info[0] & 0x400
        or not info[1].directory
        or info[1].delete_pending
        or wincheck._handle_dacl_state(kernel, advapi, handle, owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        return None
    return identity


def _try_flush_qualified_directory(
    root: Path, owner: inspection.EffectiveOSOwner
) -> bool:
    """Attempt one Win32 directory flush; no fallback and no durability claim.

    Some Windows filesystems return ERROR_INVALID_FUNCTION or ACCESS_DENIED
    when flushing a directory. Preserve that refusal, never open a less secure
    alternative or silently substitute a registry-file flush.
    """
    kernel: Any = None
    opened: int | None = None
    try:
        kernel, advapi = wincheck._bind_api()
        if (
            not wincreate._known_fixed_local_volume(kernel, root)
            or wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return False
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        kernel.FlushFileBuffers.restype = wintypes.BOOL
        raw = kernel.CreateFileW(
            str(root),
            0x00000002
            | 0x00000080
            | 0x00020000,  # FILE_WRITE_DATA, attributes, READ_CONTROL
            7,  # Share read/write/delete; no exclusive lock claim
            None,
            3,  # OPEN_EXISTING
            0x02000000 | 0x00200000,  # BACKUP_SEMANTICS and OPEN_REPARSE_POINT
            None,
        )
        opened = ctypes.cast(raw, ctypes.c_void_p).value
        if opened is None or opened == ctypes.c_void_p(-1).value:
            opened = None
            return False
        before = _directory_identity(kernel, advapi, opened, owner)
        if before is None:
            return False
        flushed = bool(kernel.FlushFileBuffers(wintypes.HANDLE(opened)))
        if _directory_identity(kernel, advapi, opened, owner) != before:
            return False
        second, _error = anchor._windows_open(kernel, root)
        if second is None:
            return False
        try:
            if _directory_identity(kernel, advapi, second, owner) != before:
                return False
        finally:
            kernel.CloseHandle(wintypes.HANDLE(second))
        return bool(
            flushed
            and wincreate._known_fixed_local_volume(kernel, root)
            and wincheck._native_windows_walk(root, owner)
            is NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        )
    except (
        wincheck._NativeUnavailable,
        wincreate._NativeUnavailable,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return False
    finally:
        if kernel is not None and opened is not None:
            kernel.CloseHandle(wintypes.HANDLE(opened))


def probe_pending_private_registry_directory_persistence(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateWindowsDirectoryPersistenceReview:
    """Probe native parent-directory flush beneath an exact pending checkpoint.

    A successful probe is NOT a durable-success verdict. This operation does
    not attest prior registry-file flush or a completed MoveFile/rename. It
    merely records an additional Windows filesystem observation while the
    existing locks, journal, descriptor and live registry anchors are held.
    """
    state = PrivateWindowsDirectoryPersistenceState
    if sys.platform != "win32":
        return _result(state.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, "win32")
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(state.INVALID_REQUEST)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
            or checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE
            or type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(state.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)

    accepted = frozenset(
        {
            absence.PrivateStageAbsenceCheckpointState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            absence.PrivateStageAbsenceCheckpointState.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED,
        }
    )
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            namespace_before = absence._namespace(
                existing_private_root, checked.witness.transaction_id
            )
            if (
                reader._inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
            ):
                return _result(state.NAMESPACE_UNQUALIFIED)
            before = absence._images(
                checked, existing_private_root, existing_workspace_root, owner
            )
            if before not in accepted:
                return _result(state.CHECKPOINT_UNQUALIFIED)
            flushed = _try_flush_qualified_directory(existing_private_root, owner)
            after = absence._images(
                checked, existing_private_root, existing_workspace_root, owner
            )
            if (
                reader._inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
                or absence._namespace(
                    existing_private_root, checked.witness.transaction_id
                )
                != namespace_before
            ):
                return _result(state.NAMESPACE_UNQUALIFIED)
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            if after != before:
                return _result(state.CHECKPOINT_UNQUALIFIED)
            outcome = (
                state.DIRECTORY_FLUSH_OBSERVED_DURABILITY_UNQUALIFIED
                if flushed
                else state.DIRECTORY_FLUSH_UNAVAILABLE_RECOVERY_REQUIRED
            )
        return _result(outcome)
    except exclusive._NamespaceChanged:
        return _result(state.NAMESPACE_UNQUALIFIED)
    except retained.RetainedDescriptorGuardError as error:
        if error.code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
            return _result(state.OWNER_CHANGED)
        if error.code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
            return _result(state.UNSUPPORTED)
        return _result(state.GUARD_REFUSED)
    except (
        ordered.PrivateOrderedCoordinationError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.GUARD_REFUSED)
