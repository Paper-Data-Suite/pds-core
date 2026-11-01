"""Retain Windows native anchors across one expected registry-stage CREATE_NEW.

Core #238 Slice 3F9. This internal scope verifies a previously written exact
journal, unchanged native before-images and one exclusively created after-image
stage. It neither creates files nor establishes durability, commit or CAS.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from ctypes import wintypes
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, NoReturn

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_image_snapshot as stage_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateWindowsStageMutationCode(str, Enum):
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


class PrivateWindowsStageMutationError(RuntimeError):
    """Sanitized refusal; never includes private paths, identities or bytes."""

    def __init__(self, code: PrivateWindowsStageMutationCode) -> None:
        self.code = code
        super().__init__(f"Windows stage mutation guard refused: {code.value}.")


def _refuse(code: PrivateWindowsStageMutationCode) -> NoReturn:
    raise PrivateWindowsStageMutationError(code)


def _names(directory: Path) -> set[str]:
    with os.scandir(directory) as entries:
        first = {entry.name for entry in entries}
    with os.scandir(directory) as entries:
        second = {entry.name for entry in entries}
    if first != second:
        _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
    return first


def _registry_and_descriptor(
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
    proposed: intents.PrivateTransactionIntent,
) -> None:
    """Native exact-before bytes, in symmetric read order."""
    first_registry = registry_image._read_windows(private_root, owner)
    first_descriptor = descriptor_image._read_windows(workspace_root)
    second_descriptor = descriptor_image._read_windows(workspace_root)
    second_registry = registry_image._read_windows(private_root, owner)
    if (
        first_registry.state
        is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
        or second_registry.state
        is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
        or first_descriptor.state
        is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
        or second_descriptor.state
        is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
        or type(first_registry.image) is not bytes
        or type(second_registry.image) is not bytes
        or type(first_descriptor.image) is not bytes
        or type(second_descriptor.image) is not bytes
    ):
        _refuse(PrivateWindowsStageMutationCode.ANCHOR_REFUSED)
    if (
        first_registry.image != second_registry.image
        or first_descriptor.image != second_descriptor.image
    ):
        _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
    if (
        first_registry.image != proposed.registry_before
        or first_descriptor.image != proposed.descriptor_before
    ):
        _refuse(PrivateWindowsStageMutationCode.BEFORE_IMAGE_MISMATCH)


def _journal(
    private_root: Path,
    transaction_id: str,
    canonical: bytes,
    owner: inspection.EffectiveOSOwner,
) -> None:
    """Existing single canonical journal is required before a stage can appear."""
    directory = private_root / "transactions"
    if _names(directory) != {transaction_id + ".json"}:
        _refuse(PrivateWindowsStageMutationCode.PENDING_RECOVERY_REQUIRED)
    for _ in range(2):
        seen = journal._read_windows(directory, transaction_id, owner)
        if (
            seen.state is not journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
            or type(seen.image) is not bytes
            or seen.image != canonical
        ):
            _refuse(PrivateWindowsStageMutationCode.JOURNAL_UNQUALIFIED)
    if _names(directory) != {transaction_id + ".json"}:
        _refuse(PrivateWindowsStageMutationCode.PENDING_RECOVERY_REQUIRED)


def _inventory(
    private_root: Path, owner: inspection.EffectiveOSOwner
) -> inventory.PrivateRegistryStageInventoryState:
    return inventory._scan_windows(private_root, owner)


def _stage(
    private_root: Path,
    transaction_id: str,
    raw: bytes,
    owner: inspection.EffectiveOSOwner,
) -> None:
    for _ in range(2):
        seen = stage_image._read_windows(private_root, transaction_id, owner)
        if (
            seen.state
            is not stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
            or type(seen.image) is not bytes
            or seen.image != raw
        ):
            _refuse(PrivateWindowsStageMutationCode.STAGE_UNQUALIFIED)


def _root_identity(
    kernel: Any,
    advapi: Any,
    root: Path,
    handle: int,
    owner: inspection.EffectiveOSOwner,
) -> tuple[int, bytes]:
    """Verify retained directory HANDLE and its current path, never timestamps."""
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
        or wincheck._native_windows_walk(root, owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        _refuse(PrivateWindowsStageMutationCode.REFUSED_PROTECTION)
    if not wincreate._known_fixed_local_volume(kernel, root):
        _refuse(PrivateWindowsStageMutationCode.REFUSED_BACKING)
    second, error = anchor._windows_open(kernel, root)
    if second is None:
        if error in (5, 32):
            _refuse(PrivateWindowsStageMutationCode.ACCESS_DENIED)
        _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
    try:
        second_info = descriptor._windows_info(kernel, second)
        if (
            anchor._windows_id(kernel, second) != identity
            or second_info is None
            or not second_info[1].directory
            or not (second_info[0] & 0x10)
            or second_info[0] & 0x400
            or second_info[1].delete_pending
            or wincheck._handle_dacl_state(kernel, advapi, second, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(second))
    return identity


@contextmanager
def _hold_native_root(
    private_root: Path, owner: inspection.EffectiveOSOwner
) -> Iterator[None]:
    """Keep private root HANDLE open through the expected namespace change."""
    kernel: Any = None
    first: int | None = None
    try:
        kernel, advapi = wincheck._bind_api()
        first, error = anchor._windows_open(kernel, private_root)
        if first is None:
            if error in (5, 32):
                _refuse(PrivateWindowsStageMutationCode.ACCESS_DENIED)
            _refuse(PrivateWindowsStageMutationCode.REFUSED_PROTECTION)
        expected = _root_identity(kernel, advapi, private_root, first, owner)
        yield
        if _root_identity(kernel, advapi, private_root, first, owner) != expected:
            _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
    finally:
        if kernel is not None and first is not None:
            kernel.CloseHandle(wintypes.HANDLE(first))


@contextmanager
def _hold_windows_expected_stage_create(
    private_root: Path,
    workspace_root: Path,
    proposed: intents.PrivateTransactionIntent,
    canonical: bytes,
) -> Iterator[None]:
    """Check one named stage addition after an existing qualified journal.

    No file deletion or rollback. A failure after yield may leave a stage.
    Local locks and Windows directory handles do not exclude hostile same-user
    writers or synchronized folders and do not establish crash durability.
    """
    with ordered._hold_existing_ordered_coordination(private_root, workspace_root):
        owner = ordered._owner()
        if owner.kind != "windows_token_sid" or not owner.value:
            _refuse(PrivateWindowsStageMutationCode.OWNER_UNAVAILABLE)
        with registry_guard._held_windows_registry(private_root, owner):
            with descriptor_guard._held_windows_descriptor(workspace_root):
                with journal_guard._held_windows(private_root / "transactions", owner):
                    with _hold_native_root(private_root, owner):
                        before = _names(private_root)
                        if (
                            _inventory(private_root, owner)
                            is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
                        ):
                            _refuse(
                                PrivateWindowsStageMutationCode.STAGE_INVENTORY_UNQUALIFIED
                            )
                        _journal(
                            private_root,
                            proposed.witness.transaction_id,
                            canonical,
                            owner,
                        )
                        _registry_and_descriptor(
                            private_root, workspace_root, owner, proposed
                        )
                        if _names(private_root) != before:
                            _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
                        if ordered._owner() != owner:
                            _refuse(PrivateWindowsStageMutationCode.OWNER_CHANGED)
                        yield
                        if ordered._owner() != owner:
                            _refuse(PrivateWindowsStageMutationCode.OWNER_CHANGED)
                        expected_name = (
                            "." + proposed.witness.transaction_id + ".registry-stage"
                        )
                        final_names = _names(private_root)
                        if final_names == before:
                            _refuse(
                                PrivateWindowsStageMutationCode.MISSING_EXPECTED_STAGE
                            )
                        if (
                            final_names != before | {expected_name}
                            or expected_name in before
                        ):
                            _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
                        if (
                            _inventory(private_root, owner)
                            is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                        ):
                            _refuse(
                                PrivateWindowsStageMutationCode.STAGE_INVENTORY_UNQUALIFIED
                            )
                        _stage(
                            private_root,
                            proposed.witness.transaction_id,
                            proposed.registry_after,
                            owner,
                        )
                        _journal(
                            private_root,
                            proposed.witness.transaction_id,
                            canonical,
                            owner,
                        )
                        _registry_and_descriptor(
                            private_root, workspace_root, owner, proposed
                        )
                        if _names(private_root) != before | {expected_name}:
                            _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
                        if ordered._owner() != owner:
                            _refuse(PrivateWindowsStageMutationCode.OWNER_CHANGED)


@contextmanager
def hold_expected_windows_private_registry_stage_creation(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> Iterator[None]:
    """Internal Windows-only stage-create guard, not a commit authority."""
    if sys.platform != "win32":
        _refuse(PrivateWindowsStageMutationCode.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, "win32")
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(PrivateWindowsStageMutationCode.INVALID_REQUEST)
    try:
        if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            _refuse(PrivateWindowsStageMutationCode.INVALID_REQUEST)
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
            _refuse(PrivateWindowsStageMutationCode.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        _refuse(PrivateWindowsStageMutationCode.INVALID_REQUEST)
    try:
        with _hold_windows_expected_stage_create(
            existing_private_root, existing_workspace_root, proposed, canonical
        ):
            yield
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            _refuse(PrivateWindowsStageMutationCode.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            _refuse(PrivateWindowsStageMutationCode.OWNER_UNAVAILABLE)
        _refuse(PrivateWindowsStageMutationCode.COORDINATION_REFUSED)
    except (
        registry_guard.RetainedRegistryGuardError,
        descriptor_guard.RetainedDescriptorGuardError,
        journal_guard.RetainedJournalGuardError,
    ):
        _refuse(PrivateWindowsStageMutationCode.ANCHOR_REFUSED)
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        _refuse(PrivateWindowsStageMutationCode.UNSUPPORTED)
    except FileNotFoundError:
        _refuse(PrivateWindowsStageMutationCode.UNEXPECTED_MUTATION)
    except PermissionError:
        _refuse(PrivateWindowsStageMutationCode.ACCESS_DENIED)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        _refuse(PrivateWindowsStageMutationCode.IO_ERROR)
