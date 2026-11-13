"""Protected Windows registry after-image flush checkpoint (Core #238 3G7).

For a separately admitted, still-pending transaction whose native registry
already equals the intended after-image, attempt one FlushFileBuffers on the
protected live file. Retain existing lock and immutable file guards; demand a
stable stage-absent journal/metadata checkpoint before and after the flush.

A successful file flush does NOT establish directory entry persistence,
source-stage rename durability, multi-file CAS, recovery completion, or Notes
access. This module must not be called from public teacher-facing workflows.
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
from pds_core import _teacher_private_metadata as metadata
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
from pds_core import (
    _teacher_private_windows_registry_replacement_guard as replacement_guard,
)
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateWindowsRegistryFlushState(str, Enum):
    FILE_FLUSHED_DIRECTORY_DURABILITY_UNQUALIFIED = (
        "file_flushed_directory_durability_unqualified"
    )
    FLUSH_UNQUALIFIED_RECOVERY_REQUIRED = "flush_unqualified_recovery_required"
    CHECKPOINT_UNQUALIFIED = "checkpoint_unqualified"
    NAMESPACE_UNQUALIFIED = "namespace_unqualified"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"


_MESSAGES = {
    PrivateWindowsRegistryFlushState.FILE_FLUSHED_DIRECTORY_DURABILITY_UNQUALIFIED: "Registry after-image file flush observed; directory entry and transaction durability remain unqualified.",
    PrivateWindowsRegistryFlushState.FLUSH_UNQUALIFIED_RECOVERY_REQUIRED: "Registry file flush failed or could not be verified; preserve pending recovery evidence.",
    PrivateWindowsRegistryFlushState.CHECKPOINT_UNQUALIFIED: "Exact pending journal and stage-absent after-image checkpoint not qualified.",
    PrivateWindowsRegistryFlushState.NAMESPACE_UNQUALIFIED: "Pending journal or stage namespace missing, competing or changed.",
    PrivateWindowsRegistryFlushState.INVALID_REQUEST: "Invalid native registry file flush checkpoint request.",
    PrivateWindowsRegistryFlushState.UNSUPPORTED: "Windows registry file flush checkpoint unsupported.",
    PrivateWindowsRegistryFlushState.OWNER_CHANGED: "Effective OS owner changed during file flush review.",
    PrivateWindowsRegistryFlushState.GUARD_REFUSED: "Retained native checkpoint guard refused review.",
}


@dataclass(frozen=True, slots=True)
class PrivateWindowsRegistryFlushReview:
    """Sanitized advisory status, never an authorization or durability token."""

    state: PrivateWindowsRegistryFlushState
    message: str


def _result(
    state: PrivateWindowsRegistryFlushState,
) -> PrivateWindowsRegistryFlushReview:
    return PrivateWindowsRegistryFlushReview(state, _MESSAGES[state])


def _flush_handle(kernel: Any, handle: int) -> bool:
    """One native file-buffer flush, without a content write or fallback."""
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel.FlushFileBuffers.restype = wintypes.BOOL
    return bool(kernel.FlushFileBuffers(wintypes.HANDLE(handle)))


def _flush_named_registry(root: Path, owner: inspection.EffectiveOSOwner) -> bool:
    """Open protected registry with write access solely for FlushFileBuffers.

    Directory-entry durability is not proven even if this returns True.
    Existing retained locks and parent/registry guards are supplied by caller.
    """
    kernel: Any = None
    handle: int | None = None
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
        raw = kernel.CreateFileW(
            str(root / "registry.json"),
            0x40000000
            | 0x00000080
            | 0x00020000,  # GENERIC_WRITE, attributes, READ_CONTROL
            7,  # FILE_SHARE_READ | WRITE | DELETE; cooperate with retained handles
            None,
            3,  # OPEN_EXISTING, NEVER CREATE
            0x00200000,  # FILE_FLAG_OPEN_REPARSE_POINT
            None,
        )
        handle = ctypes.cast(raw, ctypes.c_void_p).value
        if handle is None or handle == ctypes.c_void_p(-1).value:
            handle = None
            return False
        identity = replacement_guard._native_file_id(kernel, advapi, handle, owner)
        info = descriptor._windows_info(kernel, handle)
        if (
            info is None
            or not 0 < int(info[1].end_of_file) <= metadata.MAX_REGISTRY_BYTES
        ):
            return False
        if not _flush_handle(kernel, handle):
            return False
        if replacement_guard._native_file_id(kernel, advapi, handle, owner) != identity:
            return False
        second, _error = anchor._windows_open(kernel, root / "registry.json")
        if second is None:
            return False
        try:
            if (
                replacement_guard._native_file_id(kernel, advapi, second, owner)
                != identity
            ):
                return False
        finally:
            kernel.CloseHandle(wintypes.HANDLE(second))
        return (
            wincreate._known_fixed_local_volume(kernel, root)
            and wincheck._native_windows_walk(root, owner)
            is NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        )
    except (
        wincheck._NativeUnavailable,
        wincreate._NativeUnavailable,
        replacement_guard.PrivateWindowsRegistryReplacementError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return False
    finally:
        if kernel is not None and handle is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle))


def flush_pending_private_registry_after_image(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateWindowsRegistryFlushReview:
    """Attempt one protected file flush; never retire journal or expose Notes.

    This opt-in INTERNAL primitive is only meaningful after a separate native
    registry-stage replacement. A flush is NOT a crash-durable directory rename.
    The complete native checkpoint and owner are reobserved after the flush.
    """
    state = PrivateWindowsRegistryFlushState
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
            original_namespace = absence._namespace(
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
            flushed = _flush_named_registry(existing_private_root, owner)
            after = absence._images(
                checked, existing_private_root, existing_workspace_root, owner
            )
            if (
                reader._inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
                or absence._namespace(
                    existing_private_root, checked.witness.transaction_id
                )
                != original_namespace
            ):
                return _result(state.NAMESPACE_UNQUALIFIED)
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            if after != before:
                return _result(state.CHECKPOINT_UNQUALIFIED)
            outcome = (
                state.FILE_FLUSHED_DIRECTORY_DURABILITY_UNQUALIFIED
                if flushed
                else state.FLUSH_UNQUALIFIED_RECOVERY_REQUIRED
            )
        # Context-manager postcondition may refuse; only report after normal exit.
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
