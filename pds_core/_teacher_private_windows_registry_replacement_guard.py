"""Windows native registry-stage replacement scope, *not* commit authority (#238 3G5).

Retains protected original registry, staged after-image and parent handles across
one caller-executed replacement. Verifies pre/post namespace, exact journal and
metadata images, target file IDs and DACLs under already-existing local locks.
This does not rename files, flush directories, admit/replay/retire journals,
authorize a binding, or expose Notes. Interrupted attempts retain all evidence.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from ctypes import wintypes
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, NoReturn

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as exclusive
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_stage_checkpoint_review as reader
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class PrivateWindowsRegistryReplacementCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_CHANGED = "owner_changed"
    COORDINATION_REFUSED = "coordination_refused"
    ANCHOR_REFUSED = "anchor_refused"
    BEFORE_IMAGE_MISMATCH = "before_image_mismatch"
    STAGE_UNQUALIFIED = "stage_unqualified"
    JOURNAL_UNQUALIFIED = "journal_unqualified"
    NAMESPACE_UNQUALIFIED = "namespace_unqualified"
    UNEXPECTED_MUTATION = "unexpected_mutation"
    REPLACEMENT_MISSING = "replacement_missing"
    AFTER_IMAGE_MISMATCH = "after_image_mismatch"
    REFUSED_BACKING = "refused_backing"
    REFUSED_PROTECTION = "refused_protection"
    ACCESS_DENIED = "access_denied"
    IO_ERROR = "io_error"


class PrivateWindowsRegistryReplacementError(RuntimeError):
    """Sanitized error; neither path, owner, stage ID nor bytes are exposed."""

    def __init__(self, code: PrivateWindowsRegistryReplacementCode) -> None:
        self.code = code
        super().__init__(
            f"Private Windows registry replacement guard refused: {code.value}."
        )


def _refuse(code: PrivateWindowsRegistryReplacementCode) -> NoReturn:
    raise PrivateWindowsRegistryReplacementError(code)


def _native_file_id(
    kernel: Any, advapi: Any, handle: int, owner: inspection.EffectiveOSOwner
) -> tuple[int, bytes]:
    identity = anchor._windows_id(kernel, handle)
    info = descriptor._windows_info(kernel, handle)
    if (
        identity is None
        or not any(identity[1])
        or info is None
        or info[0] & (0x10 | 0x400)
        or info[1].directory
        or info[1].delete_pending
        or info[1].number_of_links != 1
        or wincheck._handle_dacl_state(kernel, advapi, handle, owner)
        is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ):
        _refuse(PrivateWindowsRegistryReplacementCode.REFUSED_PROTECTION)
    return identity


@contextmanager
def _held_windows_target_and_stage(
    private_root: Path, stage_name: str, owner: inspection.EffectiveOSOwner
) -> Iterator[None]:
    """Retain three native handles and prove the stage becomes live target.

    Never nest the immutable retained registry guard: replacing registry.json
    necessarily changes its named file identity. File handles opened with
    FILE_SHARE_DELETE allow a cooperating writer's atomic replacement.
    """
    kernel: Any = None
    handles: list[int] = []
    try:
        kernel, advapi = wincheck._bind_api()
        if not wincreate._known_fixed_local_volume(kernel, private_root):
            _refuse(PrivateWindowsRegistryReplacementCode.REFUSED_BACKING)
        if (
            wincheck._native_windows_walk(private_root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            _refuse(PrivateWindowsRegistryReplacementCode.REFUSED_PROTECTION)
        paths = (
            private_root,
            private_root / "registry.json",
            private_root / stage_name,
        )
        for path in paths:
            handle, error = anchor._windows_open(kernel, path)
            if handle is None:
                _refuse(
                    PrivateWindowsRegistryReplacementCode.ACCESS_DENIED
                    if error in (5, 32)
                    else PrivateWindowsRegistryReplacementCode.ANCHOR_REFUSED
                )
            handles.append(handle)
        parent, original, staged = handles
        parent_id = anchor._windows_id(kernel, parent)
        parent_info = descriptor._windows_info(kernel, parent)
        if (
            parent_id is None
            or not any(parent_id[1])
            or parent_info is None
            or not (parent_info[0] & 0x10)
            or parent_info[0] & 0x400
            or not parent_info[1].directory
            or parent_info[1].delete_pending
            or wincheck._handle_dacl_state(kernel, advapi, parent, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            _refuse(PrivateWindowsRegistryReplacementCode.REFUSED_PROTECTION)
        old_id = _native_file_id(kernel, advapi, original, owner)
        staged_id = _native_file_id(kernel, advapi, staged, owner)
        if staged_id == old_id or staged_id[0] != parent_id[0]:
            _refuse(PrivateWindowsRegistryReplacementCode.ANCHOR_REFUSED)
        yield
        # The old handle is allowed to become delete-pending; its FILE_ID must
        # remain unchanged. Do not apply the immutable registry signature.
        if (
            anchor._windows_id(kernel, original) != old_id
            or anchor._windows_id(kernel, staged) != staged_id
            or anchor._windows_id(kernel, parent) != parent_id
            or wincheck._native_windows_walk(private_root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            or not wincreate._known_fixed_local_volume(kernel, private_root)
        ):
            _refuse(PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION)
        parent_now, error = anchor._windows_open(kernel, private_root)
        if parent_now is None:
            _refuse(PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION)
        try:
            if anchor._windows_id(kernel, parent_now) != parent_id:
                _refuse(PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION)
        finally:
            kernel.CloseHandle(wintypes.HANDLE(parent_now))
        new, error = anchor._windows_open(kernel, private_root / "registry.json")
        if new is None:
            _refuse(PrivateWindowsRegistryReplacementCode.REPLACEMENT_MISSING)
        try:
            if _native_file_id(kernel, advapi, new, owner) != staged_id:
                _refuse(PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION)
        finally:
            kernel.CloseHandle(wintypes.HANDLE(new))
        leftover, error = anchor._windows_open(kernel, private_root / stage_name)
        if leftover is not None:
            kernel.CloseHandle(wintypes.HANDLE(leftover))
            _refuse(PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION)
        if error not in (2, 3):
            _refuse(PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION)
    finally:
        if kernel is not None:
            for handle in reversed(handles):
                kernel.CloseHandle(wintypes.HANDLE(handle))


def _namespace(
    root: Path, transaction_id: str, *, stage_present: bool
) -> frozenset[str]:
    pending = exclusive._names(root / "transactions")
    names = exclusive._names(root)
    stage = "." + transaction_id + ".registry-stage"
    expected = frozenset({stage}) if stage_present else frozenset()
    if pending != frozenset({transaction_id + ".json"}):
        _refuse(PrivateWindowsRegistryReplacementCode.NAMESPACE_UNQUALIFIED)
    if frozenset(x for x in names if "registry-stage" in x.casefold()) != expected:
        _refuse(PrivateWindowsRegistryReplacementCode.NAMESPACE_UNQUALIFIED)
    return names


def _check_images(
    proposed: intents.PrivateTransactionIntent,
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
    canonical: bytes,
    *,
    before: bool,
) -> None:
    """Read native images symmetrically; do not reacquire outer ordered locks."""
    tx = proposed.witness.transaction_id
    directory = private_root / "transactions"
    j1 = reader._journal(directory, tx, owner)
    r1 = reader._registry(private_root, owner)
    d1 = reader._descriptor(workspace_root)
    if before:
        s1 = reader._stage(private_root, tx, owner)
        s2 = reader._stage(private_root, tx, owner)
    d2 = reader._descriptor(workspace_root)
    r2 = reader._registry(private_root, owner)
    j2 = reader._journal(directory, tx, owner)
    if (
        reader._journal_failure(j1) is not None
        or reader._journal_failure(j2) is not None
        or reader._registry_failure(r1) is not None
        or reader._registry_failure(r2) is not None
        or reader._descriptor_failure(d1) is not None
        or reader._descriptor_failure(d2) is not None
        or j1.image != j2.image
        or r1.image != r2.image
        or d1.image != d2.image
    ):
        _refuse(PrivateWindowsRegistryReplacementCode.ANCHOR_REFUSED)
    if j1.image != canonical:
        _refuse(PrivateWindowsRegistryReplacementCode.JOURNAL_UNQUALIFIED)
    if d1.image != proposed.descriptor_before:
        _refuse(PrivateWindowsRegistryReplacementCode.BEFORE_IMAGE_MISMATCH)
    if before:
        if (
            reader._stage_failure(s1) is not None
            or reader._stage_failure(s2) is not None
        ):
            _refuse(PrivateWindowsRegistryReplacementCode.STAGE_UNQUALIFIED)
        if s1.image != s2.image or s1.image != proposed.registry_after:
            _refuse(PrivateWindowsRegistryReplacementCode.STAGE_UNQUALIFIED)
        if r1.image != proposed.registry_before:
            _refuse(PrivateWindowsRegistryReplacementCode.BEFORE_IMAGE_MISMATCH)
    elif r1.image != proposed.registry_after:
        _refuse(PrivateWindowsRegistryReplacementCode.AFTER_IMAGE_MISMATCH)


@contextmanager
def _hold_windows_expected_registry_replacement(
    proposed: intents.PrivateTransactionIntent,
    private_root: Path,
    workspace_root: Path,
    canonical: bytes,
) -> Iterator[None]:
    with ordered._hold_existing_ordered_coordination(private_root, workspace_root):
        owner = ordered._owner()
        if owner.kind != "windows_token_sid" or not owner.value:
            _refuse(PrivateWindowsRegistryReplacementCode.OWNER_CHANGED)
        with journal_guard._held_windows(private_root / "transactions", owner):
            with descriptor_guard._held_windows_descriptor(workspace_root):
                tx = proposed.witness.transaction_id
                stage = "." + tx + ".registry-stage"
                with _held_windows_target_and_stage(private_root, stage, owner):
                    before = _namespace(private_root, tx, stage_present=True)
                    if (
                        reader._inventory(private_root, owner)
                        is not inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                    ):
                        _refuse(PrivateWindowsRegistryReplacementCode.STAGE_UNQUALIFIED)
                    _check_images(
                        proposed,
                        private_root,
                        workspace_root,
                        owner,
                        canonical,
                        before=True,
                    )
                    if ordered._owner() != owner:
                        _refuse(PrivateWindowsRegistryReplacementCode.OWNER_CHANGED)
                    yield
                    if ordered._owner() != owner:
                        _refuse(PrivateWindowsRegistryReplacementCode.OWNER_CHANGED)
                    after = _namespace(private_root, tx, stage_present=False)
                    if after != before - {stage}:
                        _refuse(
                            PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION
                        )
                    if (
                        reader._inventory(private_root, owner)
                        is not inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
                    ):
                        _refuse(PrivateWindowsRegistryReplacementCode.STAGE_UNQUALIFIED)
                    _check_images(
                        proposed,
                        private_root,
                        workspace_root,
                        owner,
                        canonical,
                        before=False,
                    )
                    if ordered._owner() != owner:
                        _refuse(PrivateWindowsRegistryReplacementCode.OWNER_CHANGED)


@contextmanager
def hold_expected_windows_private_registry_replacement(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> Iterator[None]:
    """Internal Windows-only scope that observes a single expected rename.

    Caller must separately possess explicit teacher decision, native writer,
    flush ordering, journal admission and crash recovery. Success is a local
    *observation* only. No registry commit, replay or Notes capability results.
    """
    if sys.platform != "win32":
        _refuse(PrivateWindowsRegistryReplacementCode.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, "win32")
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(PrivateWindowsRegistryReplacementCode.INVALID_REQUEST)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
            or checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE
            or type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.registry_after) is not bytes
        ):
            _refuse(PrivateWindowsRegistryReplacementCode.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        _refuse(PrivateWindowsRegistryReplacementCode.INVALID_REQUEST)
    try:
        with _hold_windows_expected_registry_replacement(
            checked, existing_private_root, existing_workspace_root, canonical
        ):
            yield
    except PrivateWindowsRegistryReplacementError:
        raise
    except (
        ordered.PrivateOrderedCoordinationError,
        journal_guard.RetainedJournalGuardError,
        descriptor_guard.RetainedDescriptorGuardError,
    ):
        _refuse(PrivateWindowsRegistryReplacementCode.COORDINATION_REFUSED)
    except exclusive._NamespaceChanged:
        _refuse(PrivateWindowsRegistryReplacementCode.NAMESPACE_UNQUALIFIED)
    except (wincheck._NativeUnavailable, wincreate._NativeUnavailable):
        _refuse(PrivateWindowsRegistryReplacementCode.UNSUPPORTED)
    except FileNotFoundError:
        _refuse(PrivateWindowsRegistryReplacementCode.NAMESPACE_UNQUALIFIED)
    except PermissionError:
        _refuse(PrivateWindowsRegistryReplacementCode.ACCESS_DENIED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        _refuse(PrivateWindowsRegistryReplacementCode.IO_ERROR)
