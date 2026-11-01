"""Single expected Linux journal creation under mutation-aware retained guards.

Core #238 Slice 3F7: internal, explicitly invoked, no write authority token.
Read-only retained guards are unchanged. A caller can create one journal
candidate inside this scope using the independent create-only native helper;
this scope does not itself create files or admit a transaction. Windows is
fail-closed pending an equivalent native parent/entry continuity protocol.
"""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Iterator, NoReturn

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateJournalMutationGuardCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    COORDINATION_REFUSED = "coordination_refused"
    RETAINED_ANCHOR_REFUSED = "retained_anchor_refused"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    PENDING_RECOVERY_REQUIRED = "pending_recovery_required"
    UNEXPECTED_MUTATION = "unexpected_mutation"
    MISSING_EXPECTED_ENTRY = "missing_expected_entry"
    FILE_UNQUALIFIED = "file_unqualified"
    IO_ERROR = "io_error"


class PrivateJournalMutationGuardError(RuntimeError):
    """Only sanitized refusal reason, never path, transaction ID or bytes."""

    def __init__(self, code: PrivateJournalMutationGuardCode) -> None:
        self.code = code
        super().__init__(f"Journal mutation guard refused: {code.value}.")


def _refuse(code: PrivateJournalMutationGuardCode) -> NoReturn:
    raise PrivateJournalMutationGuardError(code)


def _directory_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    """Retain identity and protection, intentionally not namespace timestamps."""
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink)


def _verified_directory(
    fd: int,
    directory: Path,
    expected: tuple[int, int, int, int, int],
    uid: int,
) -> None:
    """Recheck original handle AND independently resolved current path."""
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() != uid:
        _refuse(PrivateJournalMutationGuardCode.OWNER_CHANGED)
    opened = os.fstat(fd)
    at_path = os.lstat(directory)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(at_path.st_mode)
        or _directory_identity(opened) != expected
        or _directory_identity(at_path) != expected
    ):
        _refuse(PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION)
    if opened.st_uid != uid or stat.S_IMODE(opened.st_mode) != 0o700:
        _refuse(PrivateJournalMutationGuardCode.REFUSED_PROTECTION)
    if posix._acl_absent(fd) is not None:
        _refuse(PrivateJournalMutationGuardCode.REFUSED_PROTECTION)
    if not posix._is_known_local_filesystem(fd):
        _refuse(PrivateJournalMutationGuardCode.REFUSED_BACKING)


def _expected_entry(
    fd: int,
    directory: Path,
    transaction_id: str,
    raw: bytes,
    owner: inspection.EffectiveOSOwner,
) -> None:
    """Require exactly one new protected file and two identical native reads."""
    name = transaction_id + ".json"
    first = set(os.listdir(fd))
    if first != {name}:
        _refuse(PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION)
    linked = os.stat(name, dir_fd=fd, follow_symlinks=False)
    parent = os.fstat(fd)
    if (
        not stat.S_ISREG(linked.st_mode)
        or linked.st_nlink != 1
        or linked.st_dev != parent.st_dev
        or linked.st_uid != int(owner.value)
        or stat.S_IMODE(linked.st_mode) != 0o600
        or linked.st_size != len(raw)
    ):
        _refuse(PrivateJournalMutationGuardCode.FILE_UNQUALIFIED)
    for _ in range(2):
        observed = journal._read_linux(directory, transaction_id, owner)
        if (
            observed.state
            is not journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
            or observed.image != raw
        ):
            _refuse(PrivateJournalMutationGuardCode.FILE_UNQUALIFIED)
    if set(os.listdir(fd)) != {name}:
        _refuse(PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION)


@contextmanager
def _hold_linux_expected_journal_create(
    private_root: Path,
    workspace_root: Path,
    proposed: intents.PrivateTransactionIntent,
    canonical: bytes,
) -> Iterator[None]:
    """Internal scope: one candidate entry, no replay or write capability.

    The caller is responsible for invoking the existing native *create-only*
    primitive inside this scope. On any post-yield refusal, the candidate is
    preserved; no rollback, retry, cleanup or commit is performed here.
    """
    with ordered._hold_existing_ordered_coordination(private_root, workspace_root):
        owner = ordered._owner()
        if owner.kind != "posix_euid" or not owner.value.isdecimal():
            _refuse(PrivateJournalMutationGuardCode.OWNER_UNAVAILABLE)
        uid = int(owner.value)
        if uid <= 0 or getattr(os, "geteuid", lambda: -1)() != uid:
            _refuse(PrivateJournalMutationGuardCode.OWNER_CHANGED)
        # Call *private native scopes* directly: public wrappers would nest the
        # immutable journal guard and reject the expected directory ctime delta.
        with registry_guard._held_linux_registry(private_root, owner):
            with descriptor_guard._held_linux_descriptor(workspace_root):
                directory = private_root / "transactions"
                fd: int | None = None
                try:
                    fd, failure = posix._open_verified_parent(directory, uid)
                    if failure is not None:
                        if failure is posix.PrivateChildCreationState.REFUSED_BACKING:
                            _refuse(PrivateJournalMutationGuardCode.REFUSED_BACKING)
                        if failure is posix.PrivateChildCreationState.ACCESS_DENIED:
                            _refuse(PrivateJournalMutationGuardCode.ACCESS_DENIED)
                        _refuse(PrivateJournalMutationGuardCode.REFUSED_PROTECTION)
                    if fd is None:
                        _refuse(PrivateJournalMutationGuardCode.UNSUPPORTED)
                    expected = _directory_identity(os.fstat(fd))
                    _verified_directory(fd, directory, expected, uid)
                    before_first = set(os.listdir(fd))
                    before_second = set(os.listdir(fd))
                    if before_first != before_second:
                        _refuse(PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION)
                    if before_first:
                        _refuse(
                            PrivateJournalMutationGuardCode.PENDING_RECOVERY_REQUIRED
                        )
                    _verified_directory(fd, directory, expected, uid)
                    yield
                    _verified_directory(fd, directory, expected, uid)
                    final = set(os.listdir(fd))
                    if not final:
                        _refuse(PrivateJournalMutationGuardCode.MISSING_EXPECTED_ENTRY)
                    if final != {proposed.witness.transaction_id + ".json"}:
                        _refuse(PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION)
                    _expected_entry(
                        fd, directory, proposed.witness.transaction_id, canonical, owner
                    )
                    _verified_directory(fd, directory, expected, uid)
                    if ordered._owner() != owner:
                        _refuse(PrivateJournalMutationGuardCode.OWNER_CHANGED)
                finally:
                    if fd is not None:
                        os.close(fd)


@contextmanager
def hold_expected_private_journal_creation(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> Iterator[None]:
    """Retain locks/anchors for precisely one Linux journal CREATE_NEW entry.

    Explicitly internal Linux-only foundation. Successful exit only verifies
    one protected candidate, not durable Windows/POSIX admission or a binding.
    This scope does not make an unsafe caller into a safe transaction writer.
    """
    if sys.platform != "linux":
        _refuse(PrivateJournalMutationGuardCode.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, "linux")
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(PrivateJournalMutationGuardCode.INVALID_REQUEST)
    try:
        if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            _refuse(PrivateJournalMutationGuardCode.INVALID_REQUEST)
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            _refuse(PrivateJournalMutationGuardCode.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        AttributeError,
        TypeError,
        OverflowError,
    ):
        _refuse(PrivateJournalMutationGuardCode.INVALID_REQUEST)
    try:
        with _hold_linux_expected_journal_create(
            existing_private_root, existing_workspace_root, proposed, canonical
        ):
            yield
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            _refuse(PrivateJournalMutationGuardCode.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            _refuse(PrivateJournalMutationGuardCode.OWNER_UNAVAILABLE)
        _refuse(PrivateJournalMutationGuardCode.COORDINATION_REFUSED)
    except (
        registry_guard.RetainedRegistryGuardError,
        descriptor_guard.RetainedDescriptorGuardError,
    ):
        _refuse(PrivateJournalMutationGuardCode.RETAINED_ANCHOR_REFUSED)
    except FileNotFoundError:
        _refuse(PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION)
    except PermissionError:
        _refuse(PrivateJournalMutationGuardCode.ACCESS_DENIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        _refuse(PrivateJournalMutationGuardCode.IO_ERROR)
