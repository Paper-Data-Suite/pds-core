"""Read-only private registry-stage inventory under retained native guards (#238 3F3).

A scan can refuse or require recovery, never authorize deletion, replacement,
CAS, a binding, an empty Notes collection, or journal admission. The registry
stage name is transaction-specific; no stage file is opened for its content.
"""

from __future__ import annotations

import os
import re
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import UUID

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState

_STAGE = re.compile(r"\.([0-9a-f-]{36})\.registry-stage\Z")
_MARKER = "registry-stage"


class PrivateRegistryStageInventoryState(str, Enum):
    EMPTY_REVIEW_REQUIRED = "empty_review_required"
    STAGES_PRESENT_RECOVERY_REQUIRED = "stages_present_recovery_required"
    UNQUALIFIED_STAGE_ENTRY = "unqualified_stage_entry"
    ENTRIES_CHANGED = "entries_changed"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_CHANGED = "owner_changed"
    OWNER_UNAVAILABLE = "owner_unavailable"
    GUARD_REFUSED = "guard_refused"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED: "No local registry-stage filename observed; transaction execution remains unqualified.",
    PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED: "One or more private registry-stage entries require recovery review.",
    PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY: "Malformed or unsafe registry-stage entry requires independent review.",
    PrivateRegistryStageInventoryState.ENTRIES_CHANGED: "Registry-stage directory entries changed during inspection.",
    PrivateRegistryStageInventoryState.INVALID_REQUEST: "Private registry-stage inventory request refused.",
    PrivateRegistryStageInventoryState.UNSUPPORTED: "Private registry-stage inventory unsupported.",
    PrivateRegistryStageInventoryState.OWNER_CHANGED: "Effective OS owner changed during stage inventory.",
    PrivateRegistryStageInventoryState.OWNER_UNAVAILABLE: "Effective OS owner could not be verified.",
    PrivateRegistryStageInventoryState.GUARD_REFUSED: "Native retained guard refused stage inventory.",
    PrivateRegistryStageInventoryState.REFUSED_PROTECTION: "Private registry-stage directory or entry protection refused.",
    PrivateRegistryStageInventoryState.REFUSED_BACKING: "Private registry-stage backing is unqualified.",
    PrivateRegistryStageInventoryState.ACCESS_DENIED: "Private registry-stage access denied.",
    PrivateRegistryStageInventoryState.IO_ERROR: "Private registry-stage inventory failed without mutation.",
}


@dataclass(frozen=True, slots=True)
class PrivateRegistryStageInventoryReview:
    """Sanitized state only; no paths, IDs, filenames, content, or commit token."""

    state: PrivateRegistryStageInventoryState
    message: str


def _result(
    state: PrivateRegistryStageInventoryState,
) -> PrivateRegistryStageInventoryReview:
    return PrivateRegistryStageInventoryReview(state, _MESSAGES[state])


def _qualified_stage_name(value: str) -> bool:
    match = _STAGE.fullmatch(value)
    if match is None:
        return False
    try:
        parsed = UUID(match.group(1))
    except (ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == match.group(1)


def _inventory_names(names: set[str]) -> PrivateRegistryStageInventoryState:
    """Treat any suspicious stage-like filename as unresolved, never absent."""
    encountered: set[str] = set()
    for name in names:
        if _MARKER not in name.casefold():
            continue
        folded = name.casefold()
        if not _qualified_stage_name(name) or folded in encountered:
            return PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        encountered.add(folded)
    return (
        PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
        if encountered
        else PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
    )


def _same_parent(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(first.st_mode)
        and stat.S_ISDIR(second.st_mode)
        and (
            first.st_dev,
            first.st_ino,
            first.st_mode,
            first.st_mtime_ns,
            first.st_ctime_ns,
        )
        == (
            second.st_dev,
            second.st_ino,
            second.st_mode,
            second.st_mtime_ns,
            second.st_ctime_ns,
        )
    )


def _scan_linux(
    root: Path, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryStageInventoryState:
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0):
        return PrivateRegistryStageInventoryState.UNSUPPORTED
    getter = getattr(os, "geteuid", None)
    if not owner.value.isdecimal() or int(owner.value) <= 0 or getter is None:
        return PrivateRegistryStageInventoryState.OWNER_UNAVAILABLE
    uid = int(owner.value)
    if getter() != uid:
        return PrivateRegistryStageInventoryState.OWNER_CHANGED
    fd: int | None = None
    try:
        before_path = os.lstat(root)
        fd, problem = posix._open_verified_parent(root, uid)
        if problem is not None:
            if problem is posix.PrivateChildCreationState.REFUSED_BACKING:
                return PrivateRegistryStageInventoryState.REFUSED_BACKING
            if problem is posix.PrivateChildCreationState.ACCESS_DENIED:
                return PrivateRegistryStageInventoryState.ACCESS_DENIED
            return PrivateRegistryStageInventoryState.REFUSED_PROTECTION
        if fd is None:
            return PrivateRegistryStageInventoryState.UNSUPPORTED
        before = os.fstat(fd)
        first = set(os.listdir(fd))
        second = set(os.listdir(fd))
        after = os.fstat(fd)
        path_after = os.lstat(root)
        if (
            not _same_parent(before_path, before)
            or not _same_parent(before, after)
            or not _same_parent(before_path, path_after)
            or first != second
            or getter() != uid
        ):
            return PrivateRegistryStageInventoryState.ENTRIES_CHANGED
        outcome = _inventory_names(first)
        if outcome is PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY:
            return outcome
        for name in first:
            if _MARKER not in name.casefold():
                continue
            item = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(item.st_mode)
                or item.st_nlink != 1
                or item.st_uid != uid
                or stat.S_IMODE(item.st_mode) != 0o600
                or item.st_dev != before.st_dev
            ):
                return PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        if not _same_parent(before, os.fstat(fd)) or set(os.listdir(fd)) != first:
            return PrivateRegistryStageInventoryState.ENTRIES_CHANGED
        return outcome
    except FileNotFoundError:
        return PrivateRegistryStageInventoryState.ENTRIES_CHANGED
    except PermissionError:
        return PrivateRegistryStageInventoryState.ACCESS_DENIED
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return PrivateRegistryStageInventoryState.IO_ERROR
    finally:
        if fd is not None:
            os.close(fd)


def _scan_windows(
    root: Path, owner: inspection.EffectiveOSOwner
) -> PrivateRegistryStageInventoryState:
    if owner.kind != "windows_token_sid":
        return PrivateRegistryStageInventoryState.OWNER_UNAVAILABLE
    try:
        kernel, _ = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, root):
            return PrivateRegistryStageInventoryState.REFUSED_BACKING
        if (
            wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            return PrivateRegistryStageInventoryState.REFUSED_PROTECTION
        before = os.lstat(root)
        if (
            not stat.S_ISDIR(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400
        ):
            return PrivateRegistryStageInventoryState.REFUSED_PROTECTION
        with os.scandir(root) as entries:
            first = {entry.name for entry in entries}
        with os.scandir(root) as entries:
            second = {entry.name for entry in entries}
        after = os.lstat(root)
        if not _same_parent(before, after) or first != second:
            return PrivateRegistryStageInventoryState.ENTRIES_CHANGED
        outcome = _inventory_names(first)
        if outcome is PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY:
            return outcome
        with os.scandir(root) as entries:
            final = {
                entry.name: entry
                for entry in entries
                if _MARKER in entry.name.casefold()
            }
            if set(final) != {name for name in first if _MARKER in name.casefold()}:
                return PrivateRegistryStageInventoryState.ENTRIES_CHANGED
            for entry in final.values():
                info = entry.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or getattr(info, "st_file_attributes", 0) & 0x400
                ):
                    return PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        if (
            not _same_parent(before, os.lstat(root))
            or wincheck._native_windows_walk(root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, root)
        ):
            return PrivateRegistryStageInventoryState.ENTRIES_CHANGED
        return outcome
    except FileNotFoundError:
        return PrivateRegistryStageInventoryState.ENTRIES_CHANGED
    except PermissionError:
        return PrivateRegistryStageInventoryState.ACCESS_DENIED
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        return PrivateRegistryStageInventoryState.UNSUPPORTED
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return PrivateRegistryStageInventoryState.IO_ERROR


def _guard_failure(
    code: retained.RetainedDescriptorGuardCode,
) -> PrivateRegistryStageInventoryState:
    if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
        return PrivateRegistryStageInventoryState.OWNER_CHANGED
    if code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE:
        return PrivateRegistryStageInventoryState.OWNER_UNAVAILABLE
    if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
        return PrivateRegistryStageInventoryState.UNSUPPORTED
    return PrivateRegistryStageInventoryState.GUARD_REFUSED


def review_private_registry_stages(
    existing_private_root: Path, existing_workspace_root: Path
) -> PrivateRegistryStageInventoryReview:
    """Inventory stage-like names while retaining private and workspace anchors.

    No stage content is interpreted here, and observed absence is advisory.
    Same-user hostile writers and remote/cloud synchronization remain outside
    a guaranteed mutual-exclusion boundary. Never use a result as CAS authority.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRegistryStageInventoryState.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateRegistryStageInventoryState.INVALID_REQUEST)
    try:
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            owner = ordered._owner()
            state = (
                _scan_linux(existing_private_root, owner)
                if sys.platform == "linux"
                else _scan_windows(existing_private_root, owner)
            )
            if ordered._owner() != owner:
                return _result(PrivateRegistryStageInventoryState.OWNER_CHANGED)
            return _result(state)
    except retained.RetainedDescriptorGuardError as error:
        return _result(_guard_failure(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateRegistryStageInventoryState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateRegistryStageInventoryState.OWNER_UNAVAILABLE)
        return _result(PrivateRegistryStageInventoryState.GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRegistryStageInventoryState.IO_ERROR)
