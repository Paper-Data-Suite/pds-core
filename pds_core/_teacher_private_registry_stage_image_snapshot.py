"""Qualified native read of one registry after-image *stage* (#238 3F4).

Read-only recovery evidence: never a registry CAS reservation, journal admission,
replay, binding or Notes capability. Both private locks and the registry, journal
and workspace-descriptor anchors are held by an outer retained guard.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateRegistryStageImageState(str, Enum):
    MATCHING_AFTER_REVIEW_REQUIRED = "matching_after_review_required"
    MISSING = "missing"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    GUARD_REFUSED = "guard_refused"
    INVENTORY_UNQUALIFIED = "inventory_unqualified"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_READ = "changed_during_read"
    IMAGES_CHANGED = "images_changed"
    INVALID_STAGE = "invalid_stage"
    AFTER_IMAGE_MISMATCH = "after_image_mismatch"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED: "Native registry stage matches proposed after-image; independent recovery review required.",
    PrivateRegistryStageImageState.MISSING: "Named registry stage missing; no action authorized.",
    PrivateRegistryStageImageState.INVALID_REQUEST: "Stage image request refused before any read.",
    PrivateRegistryStageImageState.INITIALIZATION_REFUSED: "Initial binding requires a separate protected protocol.",
    PrivateRegistryStageImageState.UNSUPPORTED: "Native registry stage reader unsupported.",
    PrivateRegistryStageImageState.OWNER_UNAVAILABLE: "Native OS principal unavailable.",
    PrivateRegistryStageImageState.OWNER_CHANGED: "Native OS principal changed during observation.",
    PrivateRegistryStageImageState.GUARD_REFUSED: "Native retained guard refused or changed.",
    PrivateRegistryStageImageState.INVENTORY_UNQUALIFIED: "Registry-stage inventory requires independent review.",
    PrivateRegistryStageImageState.REFUSED_PROTECTION: "Native registry-stage ownership or file protection unqualified.",
    PrivateRegistryStageImageState.REFUSED_BACKING: "Private registry-stage backing unqualified.",
    PrivateRegistryStageImageState.ACCESS_DENIED: "Native registry-stage read access denied.",
    PrivateRegistryStageImageState.CHANGED_DURING_READ: "Registry-stage file identity or metadata changed during reading.",
    PrivateRegistryStageImageState.IMAGES_CHANGED: "Registry-stage bytes changed across retained observations.",
    PrivateRegistryStageImageState.INVALID_STAGE: "Registry-stage content malformed or noncanonical.",
    PrivateRegistryStageImageState.AFTER_IMAGE_MISMATCH: "Registry-stage bytes do not match the proposed after-image.",
    PrivateRegistryStageImageState.IO_ERROR: "Registry-stage read failed without mutation.",
}


@dataclass(frozen=True, slots=True)
class PrivateRegistryStageImageReview:
    """Internal image stays out of repr; no authority or write handle returned."""

    state: PrivateRegistryStageImageState
    message: str
    image: bytes | None = field(default=None, repr=False)


def _result(
    state: PrivateRegistryStageImageState, image: bytes | None = None
) -> PrivateRegistryStageImageReview:
    return PrivateRegistryStageImageReview(state, _MESSAGES[state], image)


def _stage_name(transaction_id: str) -> str | None:
    name = f".{transaction_id}.registry-stage"
    return name if inventory._qualified_stage_name(name) else None


def _canonical_image(
    raw: bytes, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryStageImageReview:
    checked = registry_image._checked_image(raw, owner)
    if checked.state is registry_image.PrivateRegistryImageState.REFUSED_PROTECTION:
        return _result(PrivateRegistryStageImageState.REFUSED_PROTECTION)
    if (
        checked.state
        is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
    ):
        return _result(PrivateRegistryStageImageState.INVALID_STAGE)
    return _result(PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED, raw)


def _read_linux(
    root: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryStageImageReview:
    getter = getattr(os, "geteuid", None)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    name = _stage_name(transaction_id)
    if owner.kind != "posix_euid" or getter is None or not nofollow or name is None:
        return _result(PrivateRegistryStageImageState.UNSUPPORTED)
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        return _result(PrivateRegistryStageImageState.OWNER_UNAVAILABLE)
    uid = int(owner.value)
    if getter() != uid:
        return _result(PrivateRegistryStageImageState.OWNER_CHANGED)
    directory_fd: int | None = None
    stage_fd: int | None = None
    try:
        directory_fd, failure = posix._open_verified_parent(root, uid)
        if failure is not None:
            if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
                return _result(PrivateRegistryStageImageState.REFUSED_BACKING)
            if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
                return _result(PrivateRegistryStageImageState.ACCESS_DENIED)
            return _result(PrivateRegistryStageImageState.REFUSED_PROTECTION)
        if directory_fd is None:
            return _result(PrivateRegistryStageImageState.UNSUPPORTED)
        parent = os.fstat(directory_fd)
        try:
            stage_fd = os.open(
                name,
                os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return _result(PrivateRegistryStageImageState.MISSING)
        except PermissionError:
            return _result(PrivateRegistryStageImageState.ACCESS_DENIED)
        first = os.fstat(stage_fd)
        path_first = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        signature = registry_image._linux_signature
        if (
            not stat.S_ISREG(first.st_mode)
            or signature(first) != signature(path_first)
            or first.st_uid != uid
            or stat.S_IMODE(first.st_mode) != 0o600
            or first.st_nlink != 1
            or first.st_dev != parent.st_dev
            or posix._acl_absent(stage_fd) is not None
        ):
            return _result(PrivateRegistryStageImageState.REFUSED_PROTECTION)
        if not posix._is_known_local_filesystem(stage_fd):
            return _result(PrivateRegistryStageImageState.REFUSED_BACKING)
        if not (0 < first.st_size <= metadata.MAX_REGISTRY_BYTES):
            return _result(PrivateRegistryStageImageState.INVALID_STAGE)
        raw = bytearray()
        while len(raw) <= metadata.MAX_REGISTRY_BYTES:
            chunk = os.read(
                stage_fd, min(65536, metadata.MAX_REGISTRY_BYTES + 1 - len(raw))
            )
            if not chunk:
                break
            raw.extend(chunk)
        if (
            len(raw) != first.st_size
            or signature(first) != signature(os.fstat(stage_fd))
            or signature(first)
            != signature(os.stat(name, dir_fd=directory_fd, follow_symlinks=False))
            or signature(parent) != signature(os.fstat(directory_fd))
            or getter() != uid
        ):
            return _result(PrivateRegistryStageImageState.CHANGED_DURING_READ)
        return _canonical_image(bytes(raw), owner)
    except (FileNotFoundError, NotADirectoryError):
        return _result(PrivateRegistryStageImageState.CHANGED_DURING_READ)
    except PermissionError:
        return _result(PrivateRegistryStageImageState.ACCESS_DENIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRegistryStageImageState.IO_ERROR)
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _read_windows(
    root: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryStageImageReview:
    name = _stage_name(transaction_id)
    if owner.kind != "windows_token_sid" or name is None:
        return _result(PrivateRegistryStageImageState.OWNER_UNAVAILABLE)
    kernel: Any = None
    first: int | None = None
    second: int | None = None
    try:
        kernel, advapi = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, root):
            return _result(PrivateRegistryStageImageState.REFUSED_BACKING)
        if (
            wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateRegistryStageImageState.REFUSED_PROTECTION)
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
        kernel.ReadFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel.ReadFile.restype = wintypes.BOOL
        destination = root / name
        raw_handle = kernel.CreateFileW(
            str(destination), 0x80000000 | 0x20000, 0x1, None, 3, 0x00200000, None
        )
        first = ctypes.cast(raw_handle, ctypes.c_void_p).value
        if first is None or first == ctypes.c_void_p(-1).value:
            first = None
            code = ctypes.get_last_error()
            if code in (2, 3):
                return _result(PrivateRegistryStageImageState.MISSING)
            if code in (5, 32):
                return _result(PrivateRegistryStageImageState.ACCESS_DENIED)
            return _result(PrivateRegistryStageImageState.IO_ERROR)
        signature = registry_guard._windows_signature(kernel, first)
        if (
            signature is None
            or not (0 < signature[2] <= metadata.MAX_REGISTRY_BYTES)
            or wincheck._handle_dacl_state(kernel, advapi, first, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return _result(PrivateRegistryStageImageState.REFUSED_PROTECTION)
        content = ctypes.create_string_buffer(signature[2])
        consumed = 0
        while consumed < signature[2]:
            got = wintypes.DWORD()
            if (
                not kernel.ReadFile(
                    wintypes.HANDLE(first),
                    ctypes.byref(content, consumed),
                    signature[2] - consumed,
                    ctypes.byref(got),
                    None,
                )
                or got.value == 0
            ):
                return _result(PrivateRegistryStageImageState.IO_ERROR)
            consumed += got.value
        if registry_guard._windows_signature(kernel, first) != signature:
            return _result(PrivateRegistryStageImageState.CHANGED_DURING_READ)
        second, code = anchor._windows_open(kernel, destination)
        if second is None:
            if code in (2, 3):
                return _result(PrivateRegistryStageImageState.CHANGED_DURING_READ)
            if code in (5, 32):
                return _result(PrivateRegistryStageImageState.ACCESS_DENIED)
            return _result(PrivateRegistryStageImageState.IO_ERROR)
        if (
            registry_guard._windows_signature(kernel, second) != signature
            or wincheck._handle_dacl_state(kernel, advapi, second, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, root)
        ):
            return _result(PrivateRegistryStageImageState.CHANGED_DURING_READ)
        return _canonical_image(content.raw, owner)
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        return _result(PrivateRegistryStageImageState.UNSUPPORTED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRegistryStageImageState.IO_ERROR)
    finally:
        if kernel is not None:
            if second is not None:
                kernel.CloseHandle(wintypes.HANDLE(second))
            if first is not None:
                kernel.CloseHandle(wintypes.HANDLE(first))


def _inventory(
    root: Path, owner: inspection.EffectiveOSOwner
) -> inventory.PrivateRegistryStageInventoryState:
    return (
        inventory._scan_linux(root, owner)
        if sys.platform == "linux"
        else inventory._scan_windows(root, owner)
    )


def _native_image(
    root: Path, transaction_id: str, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryStageImageReview:
    return (
        _read_linux(root, transaction_id, owner)
        if sys.platform == "linux"
        else _read_windows(root, transaction_id, owner)
    )


def _guard_failure(
    code: retained.RetainedDescriptorGuardCode,
) -> PrivateRegistryStageImageState:
    if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
        return PrivateRegistryStageImageState.OWNER_CHANGED
    if code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE:
        return PrivateRegistryStageImageState.OWNER_UNAVAILABLE
    if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
        return PrivateRegistryStageImageState.UNSUPPORTED
    return PrivateRegistryStageImageState.GUARD_REFUSED


def inspect_existing_private_registry_stage_image(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRegistryStageImageReview:
    """Double-read stage under native guards and compare to exact intent bytes.

    Never repairs, stages, replaces, admits, deletes, issues handles, or treats
    matching bytes as a reservation. All filesystem observations are local.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRegistryStageImageState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateRegistryStageImageState.INVALID_REQUEST)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(PrivateRegistryStageImageState.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(PrivateRegistryStageImageState.INITIALIZATION_REFUSED)
        if _stage_name(checked.witness.transaction_id) is None:
            return _result(PrivateRegistryStageImageState.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
    ):
        return _result(PrivateRegistryStageImageState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            first_inventory = _inventory(existing_private_root, owner)
            if (
                first_inventory
                is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            ):
                return _result(PrivateRegistryStageImageState.INVENTORY_UNQUALIFIED)
            first = _native_image(
                existing_private_root, checked.witness.transaction_id, owner
            )
            if (
                first.state
                is not PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
                or type(first.image) is not bytes
            ):
                return _result(
                    first.state
                    if first.state
                    is not PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
                    else PrivateRegistryStageImageState.INVALID_STAGE
                )
            second = _native_image(
                existing_private_root, checked.witness.transaction_id, owner
            )
            if (
                second.state
                is not PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
                or type(second.image) is not bytes
            ):
                return _result(
                    second.state
                    if second.state
                    is not PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
                    else PrivateRegistryStageImageState.INVALID_STAGE
                )
            if first.image != second.image:
                return _result(PrivateRegistryStageImageState.IMAGES_CHANGED)
            if first.image != checked.registry_after:
                return _result(PrivateRegistryStageImageState.AFTER_IMAGE_MISMATCH)
            if (
                _inventory(existing_private_root, owner)
                is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            ):
                return _result(PrivateRegistryStageImageState.INVENTORY_UNQUALIFIED)
            if ordered._owner() != owner:
                return _result(PrivateRegistryStageImageState.OWNER_CHANGED)
            return _result(
                PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
            )
    except retained.RetainedDescriptorGuardError as error:
        return _result(_guard_failure(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateRegistryStageImageState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateRegistryStageImageState.OWNER_UNAVAILABLE)
        return _result(PrivateRegistryStageImageState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRegistryStageImageState.IO_ERROR)
