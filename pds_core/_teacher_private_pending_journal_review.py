"""Read-only pending journal census under ordered local locks (Core #238 3D1).

Any existing transaction-directory entry requires independent recovery review.
Even an empty observation is advisory, never journal admission/authority:
lock-honoring local processes alone cannot exclude sync writers, path races,
or a later journal created after these context guards are released.
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivatePendingJournalState(str, Enum):
    EMPTY_REVIEW_REQUIRED = "empty_review_required"
    PENDING_REVIEW_REQUIRED = "pending_review_required"
    MISSING_DIRECTORY = "missing_directory"
    INVALID_REQUEST = "invalid_request"
    COORDINATION_REFUSED = "coordination_refused"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    CHANGED_DURING_REVIEW = "changed_during_review"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED: "No local pending transaction entry was observed; journal writes remain unqualified.",
    PrivatePendingJournalState.PENDING_REVIEW_REQUIRED: "Existing private transaction entries require explicit recovery review.",
    PrivatePendingJournalState.MISSING_DIRECTORY: "Private transactions directory is absent; no journal may be admitted.",
    PrivatePendingJournalState.INVALID_REQUEST: "Invalid pending-journal review request.",
    PrivatePendingJournalState.COORDINATION_REFUSED: "Private local coordination unavailable or unsafe.",
    PrivatePendingJournalState.OWNER_UNAVAILABLE: "Native effective OS principal could not be verified.",
    PrivatePendingJournalState.OWNER_CHANGED: "Effective OS principal changed during pending-journal review.",
    PrivatePendingJournalState.REFUSED_PROTECTION: "Transaction directory protection or ancestry cannot be qualified.",
    PrivatePendingJournalState.REFUSED_BACKING: "Transaction directory backing is unsupported.",
    PrivatePendingJournalState.ACCESS_DENIED: "Transaction directory access denied.",
    PrivatePendingJournalState.CHANGED_DURING_REVIEW: "Private transaction directory changed during the review.",
    PrivatePendingJournalState.UNSUPPORTED: "Pending-journal review unsupported in this environment.",
    PrivatePendingJournalState.IO_ERROR: "Private transaction directory review could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivatePendingJournalReview:
    """Sanitized status, without paths, IDs, entries, principal or authority."""

    state: PrivatePendingJournalState
    message: str


def _result(state: PrivatePendingJournalState) -> PrivatePendingJournalReview:
    return PrivatePendingJournalReview(state, _MESSAGES[state])


def _same_directory(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(first.st_mode)
        and stat.S_ISDIR(second.st_mode)
        and first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_mtime_ns == second.st_mtime_ns
        and first.st_ctime_ns == second.st_ctime_ns
    )


def _scan_linux(
    directory: Path, owner: inspection.EffectiveOSOwner
) -> PrivatePendingJournalState:
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0):
        return PrivatePendingJournalState.UNSUPPORTED
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        return PrivatePendingJournalState.OWNER_UNAVAILABLE
    uid_getter = getattr(os, "geteuid", None)
    if uid_getter is None or uid_getter() != int(owner.value):
        return PrivatePendingJournalState.OWNER_CHANGED
    try:
        initial_path = os.lstat(directory)
    except FileNotFoundError:
        return PrivatePendingJournalState.MISSING_DIRECTORY
    except PermissionError:
        return PrivatePendingJournalState.ACCESS_DENIED
    except OSError:
        return PrivatePendingJournalState.IO_ERROR
    if not stat.S_ISDIR(initial_path.st_mode):
        return PrivatePendingJournalState.REFUSED_PROTECTION
    fd, failure = posix._open_verified_parent(directory, int(owner.value))
    if failure is not None:
        if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
            return PrivatePendingJournalState.REFUSED_BACKING
        if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
            return PrivatePendingJournalState.ACCESS_DENIED
        return PrivatePendingJournalState.REFUSED_PROTECTION
    if fd is None:
        return PrivatePendingJournalState.UNSUPPORTED
    try:
        before = os.fstat(fd)
        first_entries = set(os.listdir(fd))
        second_entries = set(os.listdir(fd))
        after = os.fstat(fd)
        final_path = os.lstat(directory)
        if (
            not _same_directory(before, after)
            or not _same_directory(initial_path, final_path)
            or (before.st_dev, before.st_ino)
            != (initial_path.st_dev, initial_path.st_ino)
            or first_entries != second_entries
        ):
            return PrivatePendingJournalState.CHANGED_DURING_REVIEW
        if first_entries:
            return PrivatePendingJournalState.PENDING_REVIEW_REQUIRED
        return PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED
    except FileNotFoundError:
        return PrivatePendingJournalState.CHANGED_DURING_REVIEW
    except PermissionError:
        return PrivatePendingJournalState.ACCESS_DENIED
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return PrivatePendingJournalState.IO_ERROR
    finally:
        os.close(fd)


def _scan_windows(
    directory: Path, owner: inspection.EffectiveOSOwner
) -> PrivatePendingJournalState:
    if owner.kind != "windows_token_sid":
        return PrivatePendingJournalState.OWNER_UNAVAILABLE
    try:
        kernel, _ = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, directory):
            return PrivatePendingJournalState.REFUSED_BACKING
        native = wincheck._native_windows_walk(directory, owner)
        if native is NativePrivatePreflightState.MISSING:
            return PrivatePendingJournalState.MISSING_DIRECTORY
        if native is NativePrivatePreflightState.ACCESS_DENIED:
            return PrivatePendingJournalState.ACCESS_DENIED
        if native is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED:
            return PrivatePendingJournalState.REFUSED_PROTECTION
        before = os.lstat(directory)
        if (
            not stat.S_ISDIR(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400
        ):
            return PrivatePendingJournalState.REFUSED_PROTECTION
        with os.scandir(directory) as entries:
            first_names = {entry.name for entry in entries}
        with os.scandir(directory) as entries:
            second_names = {entry.name for entry in entries}
        after = os.lstat(directory)
        if (
            not _same_directory(before, after)
            or first_names != second_names
            or wincheck._native_windows_walk(directory, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, directory)
        ):
            return PrivatePendingJournalState.CHANGED_DURING_REVIEW
        if first_names:
            return PrivatePendingJournalState.PENDING_REVIEW_REQUIRED
        return PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED
    except FileNotFoundError:
        return PrivatePendingJournalState.CHANGED_DURING_REVIEW
    except PermissionError:
        return PrivatePendingJournalState.ACCESS_DENIED
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        return PrivatePendingJournalState.UNSUPPORTED
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return PrivatePendingJournalState.IO_ERROR


def review_existing_private_pending_journals(
    existing_private_root: Path, existing_workspace_root: Path
) -> PrivatePendingJournalReview:
    """Review already-existing transaction directory under registry->workspace locks.

    Never creates directories/files, follows entry names, reads transaction
    bodies, clears stale locks, removes journals, or issues an admission token.
    Directory enumeration is not atomic across devices or hostile same-user
    writers. A future journal writer must recheck while *retaining* native
    parent handles, guards, exact-before state and recovery evidence.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivatePendingJournalState.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivatePendingJournalState.INVALID_REQUEST)
    try:
        with ordered._hold_existing_ordered_coordination(
            existing_private_root, existing_workspace_root
        ):
            before = ordered._owner()
            directory = existing_private_root / "transactions"
            if sys.platform == "linux":
                state = _scan_linux(directory, before)
            else:
                state = _scan_windows(directory, before)
            after = ordered._owner()
            if before != after:
                return _result(PrivatePendingJournalState.OWNER_CHANGED)
            return _result(state)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivatePendingJournalState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivatePendingJournalState.OWNER_UNAVAILABLE)
        return _result(PrivatePendingJournalState.COORDINATION_REFUSED)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        return _result(PrivatePendingJournalState.IO_ERROR)
