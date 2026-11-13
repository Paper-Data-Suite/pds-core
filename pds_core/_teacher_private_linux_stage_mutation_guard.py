"""Retain Linux native anchors across one expected registry-stage CREATE_NEW.

Core #238 Slice 3G0. One previously written canonical journal, exact unchanged
metadata before-images, and exactly one new owner-private stage are required.
This internal scope does not write, durably admit, commit, replace, repair, or
expose Notes. Existing immutable read-only guards retain their contracts.
"""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Iterator, NoReturn

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_image_snapshot as stage_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateLinuxStageMutationCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    COORDINATION_REFUSED = "coordination_refused"
    ANCHOR_REFUSED = "anchor_refused"
    REFUSED_PROTECTION = "refused_protection"
    REFUSED_BACKING = "refused_backing"
    ACCESS_DENIED = "access_denied"
    PENDING_RECOVERY_REQUIRED = "pending_recovery_required"
    BEFORE_IMAGE_MISMATCH = "before_image_mismatch"
    JOURNAL_UNQUALIFIED = "journal_unqualified"
    STAGE_INVENTORY_UNQUALIFIED = "stage_inventory_unqualified"
    UNEXPECTED_MUTATION = "unexpected_mutation"
    MISSING_EXPECTED_STAGE = "missing_expected_stage"
    STAGE_UNQUALIFIED = "stage_unqualified"
    IO_ERROR = "io_error"


class PrivateLinuxStageMutationError(RuntimeError):
    """Sanitized refusal: neither path, principal, ID nor bytes are included."""

    def __init__(self, code: PrivateLinuxStageMutationCode) -> None:
        self.code = code
        super().__init__(f"Linux registry-stage mutation guard refused: {code.value}.")


def _refuse(code: PrivateLinuxStageMutationCode) -> NoReturn:
    raise PrivateLinuxStageMutationError(code)


def _directory_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    """Exclude timestamps but retain native identity and protection metadata."""
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink)


def _checked_root(
    fd: int,
    root: Path,
    expected: tuple[int, int, int, int, int],
    uid: int,
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() != uid:
        _refuse(PrivateLinuxStageMutationCode.OWNER_CHANGED)
    opened = os.fstat(fd)
    linked = os.lstat(root)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(linked.st_mode)
        or _directory_identity(opened) != expected
        or _directory_identity(linked) != expected
    ):
        _refuse(PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION)
    if opened.st_uid != uid or stat.S_IMODE(opened.st_mode) != 0o700:
        _refuse(PrivateLinuxStageMutationCode.REFUSED_PROTECTION)
    if posix._acl_absent(fd) is not None:
        _refuse(PrivateLinuxStageMutationCode.REFUSED_PROTECTION)
    if not posix._is_known_local_filesystem(fd):
        _refuse(PrivateLinuxStageMutationCode.REFUSED_BACKING)


def _checked_registry(
    fd: int, parent: int, uid: int, expected: tuple[int, ...]
) -> None:
    """Ensure the original live registry FILE and current dir entry agree."""
    opened = os.fstat(fd)
    linked = os.stat("registry.json", dir_fd=parent, follow_symlinks=False)
    parent_info = os.fstat(parent)
    signature = registry_image._linux_signature
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(linked.st_mode)
        or signature(opened) != expected
        or signature(linked) != expected
        or opened.st_uid != uid
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened.st_nlink != 1
        or opened.st_dev != parent_info.st_dev
        or posix._acl_absent(fd) is not None
    ):
        _refuse(PrivateLinuxStageMutationCode.ANCHOR_REFUSED)
    if not posix._is_known_local_filesystem(fd):
        _refuse(PrivateLinuxStageMutationCode.REFUSED_BACKING)


@contextmanager
def _hold_native_root(root: Path, owner: inspection.EffectiveOSOwner) -> Iterator[None]:
    """Keep dirfd and live registry fd; allow only root timestamp drift."""
    getter = getattr(os, "geteuid", None)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if owner.kind != "posix_euid" or not owner.value.isdecimal() or not nofollow:
        _refuse(PrivateLinuxStageMutationCode.UNSUPPORTED)
    uid = int(owner.value)
    if uid <= 0 or getter is None or getter() != uid:
        _refuse(PrivateLinuxStageMutationCode.OWNER_CHANGED)
    parent: int | None = None
    live: int | None = None
    try:
        parent, problem = posix._open_verified_parent(root, uid)
        if problem is not None:
            if problem is posix.PrivateChildCreationState.REFUSED_BACKING:
                _refuse(PrivateLinuxStageMutationCode.REFUSED_BACKING)
            if problem is posix.PrivateChildCreationState.ACCESS_DENIED:
                _refuse(PrivateLinuxStageMutationCode.ACCESS_DENIED)
            _refuse(PrivateLinuxStageMutationCode.REFUSED_PROTECTION)
        if parent is None:
            _refuse(PrivateLinuxStageMutationCode.UNSUPPORTED)
        expected_parent = _directory_identity(os.fstat(parent))
        _checked_root(parent, root, expected_parent, uid)
        live = os.open(
            "registry.json",
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        expected_file = registry_image._linux_signature(os.fstat(live))
        _checked_registry(live, parent, uid, expected_file)
        yield
        _checked_root(parent, root, expected_parent, uid)
        _checked_registry(live, parent, uid, expected_file)
    finally:
        if live is not None:
            os.close(live)
        if parent is not None:
            os.close(parent)


def _names(path: Path) -> set[str]:
    """Two directory observations, never a mutation reservation."""
    with os.scandir(path) as entries:
        first = {entry.name for entry in entries}
    with os.scandir(path) as entries:
        second = {entry.name for entry in entries}
    if first != second:
        _refuse(PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION)
    return first


def _journal(
    private_root: Path,
    transaction_id: str,
    canonical: bytes,
    owner: inspection.EffectiveOSOwner,
) -> None:
    directory = private_root / "transactions"
    if _names(directory) != {transaction_id + ".json"}:
        _refuse(PrivateLinuxStageMutationCode.PENDING_RECOVERY_REQUIRED)
    for _ in range(2):
        observed = journal._read_linux(directory, transaction_id, owner)
        if (
            observed.state
            is not journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
            or type(observed.image) is not bytes
            or observed.image != canonical
        ):
            _refuse(PrivateLinuxStageMutationCode.JOURNAL_UNQUALIFIED)
    if _names(directory) != {transaction_id + ".json"}:
        _refuse(PrivateLinuxStageMutationCode.PENDING_RECOVERY_REQUIRED)


def _metadata(
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
    proposed: intents.PrivateTransactionIntent,
) -> None:
    first_r = registry_image._read_linux(private_root, owner)
    first_d = descriptor_image._read_linux(workspace_root)
    second_d = descriptor_image._read_linux(workspace_root)
    second_r = registry_image._read_linux(private_root, owner)
    if (
        first_r.state
        is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
        or second_r.state
        is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
        or first_d.state
        is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
        or second_d.state
        is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
        or type(first_r.image) is not bytes
        or type(second_r.image) is not bytes
        or type(first_d.image) is not bytes
        or type(second_d.image) is not bytes
    ):
        _refuse(PrivateLinuxStageMutationCode.ANCHOR_REFUSED)
    if first_r.image != second_r.image or first_d.image != second_d.image:
        _refuse(PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION)
    if (
        first_r.image != proposed.registry_before
        or first_d.image != proposed.descriptor_before
    ):
        _refuse(PrivateLinuxStageMutationCode.BEFORE_IMAGE_MISMATCH)


def _stage(
    private_root: Path,
    transaction_id: str,
    raw: bytes,
    owner: inspection.EffectiveOSOwner,
) -> None:
    for _ in range(2):
        observed = stage_image._read_linux(private_root, transaction_id, owner)
        if (
            observed.state
            is not stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
            or type(observed.image) is not bytes
            or observed.image != raw
        ):
            _refuse(PrivateLinuxStageMutationCode.STAGE_UNQUALIFIED)


@contextmanager
def _hold_linux_expected_stage_create(
    private_root: Path,
    workspace_root: Path,
    proposed: intents.PrivateTransactionIntent,
    canonical: bytes,
) -> Iterator[None]:
    """Expected one stage creation. No rollback or cleanup on any refusal."""
    with ordered._hold_existing_ordered_coordination(private_root, workspace_root):
        owner = ordered._owner()
        if owner.kind != "posix_euid" or not owner.value.isdecimal():
            _refuse(PrivateLinuxStageMutationCode.OWNER_UNAVAILABLE)
        uid = int(owner.value)
        if uid <= 0 or getattr(os, "geteuid", lambda: -1)() != uid:
            _refuse(PrivateLinuxStageMutationCode.OWNER_CHANGED)
        # Do not enter immutable _held_linux_registry: adding a stage changes
        # private-root mtime/ctime. Retain its native target independently.
        with journal_guard._held_linux(private_root / "transactions", owner):
            with descriptor_guard._held_linux_descriptor(workspace_root):
                with _hold_native_root(private_root, owner):
                    before = _names(private_root)
                    if (
                        inventory._scan_linux(private_root, owner)
                        is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
                    ):
                        _refuse(
                            PrivateLinuxStageMutationCode.STAGE_INVENTORY_UNQUALIFIED
                        )
                    _journal(
                        private_root, proposed.witness.transaction_id, canonical, owner
                    )
                    _metadata(private_root, workspace_root, owner, proposed)
                    if _names(private_root) != before:
                        _refuse(PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION)
                    if ordered._owner() != owner:
                        _refuse(PrivateLinuxStageMutationCode.OWNER_CHANGED)
                    yield
                    if ordered._owner() != owner:
                        _refuse(PrivateLinuxStageMutationCode.OWNER_CHANGED)
                    expected_name = (
                        "." + proposed.witness.transaction_id + ".registry-stage"
                    )
                    after = _names(private_root)
                    if after == before:
                        _refuse(PrivateLinuxStageMutationCode.MISSING_EXPECTED_STAGE)
                    if after != before | {expected_name} or expected_name in before:
                        _refuse(PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION)
                    if (
                        inventory._scan_linux(private_root, owner)
                        is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                    ):
                        _refuse(
                            PrivateLinuxStageMutationCode.STAGE_INVENTORY_UNQUALIFIED
                        )
                    _stage(
                        private_root,
                        proposed.witness.transaction_id,
                        proposed.registry_after,
                        owner,
                    )
                    _journal(
                        private_root, proposed.witness.transaction_id, canonical, owner
                    )
                    _metadata(private_root, workspace_root, owner, proposed)
                    if _names(private_root) != before | {expected_name}:
                        _refuse(PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION)
                    if ordered._owner() != owner:
                        _refuse(PrivateLinuxStageMutationCode.OWNER_CHANGED)


@contextmanager
def hold_expected_linux_private_registry_stage_creation(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> Iterator[None]:
    """Internal Linux-only staged after-image scope, not commit authority."""
    if sys.platform != "linux":
        _refuse(PrivateLinuxStageMutationCode.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, "linux")
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(PrivateLinuxStageMutationCode.INVALID_REQUEST)
    try:
        if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            _refuse(PrivateLinuxStageMutationCode.INVALID_REQUEST)
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
            or type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.registry_after) is not bytes
            or stage_image._stage_name(checked.witness.transaction_id) is None
        ):
            _refuse(PrivateLinuxStageMutationCode.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        _refuse(PrivateLinuxStageMutationCode.INVALID_REQUEST)
    try:
        with _hold_linux_expected_stage_create(
            existing_private_root, existing_workspace_root, proposed, canonical
        ):
            yield
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            _refuse(PrivateLinuxStageMutationCode.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            _refuse(PrivateLinuxStageMutationCode.OWNER_UNAVAILABLE)
        _refuse(PrivateLinuxStageMutationCode.COORDINATION_REFUSED)
    except (
        journal_guard.RetainedJournalGuardError,
        descriptor_guard.RetainedDescriptorGuardError,
    ):
        _refuse(PrivateLinuxStageMutationCode.ANCHOR_REFUSED)
    except FileNotFoundError:
        _refuse(PrivateLinuxStageMutationCode.UNEXPECTED_MUTATION)
    except PermissionError:
        _refuse(PrivateLinuxStageMutationCode.ACCESS_DENIED)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        _refuse(PrivateLinuxStageMutationCode.IO_ERROR)
