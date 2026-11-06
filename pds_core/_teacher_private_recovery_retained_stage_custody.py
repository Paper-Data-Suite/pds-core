"""Retain the prepared stage while the destination's native guard is held (#238 3G37).

The existing descriptor guard holds registry, journal, descriptor and local locks.
This supplementary read-only scope retains the *stage* parent and file, then
checks its native identity at each prepared checkpoint observation. No returned
finding can authorize execution, file replacement, commit or journal retirement.
"""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_windows_preflight as wincheck


class PrivateRetainedStageCustodyState(str, Enum):
    STAGE_AND_DESTINATION_OBSERVED_NO_WRITE = "stage_and_destination_observed_no_write"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    INTENT_UNQUALIFIED = "intent_unqualified"
    ROOT_UNQUALIFIED = "root_unqualified"
    NATIVE_PROTECTION_REFUSED = "native_protection_refused"
    OWNER_CHANGED = "owner_changed"
    BINDING_MISMATCH = "binding_mismatch"
    STAGE_CUSTODY_REFUSED = "stage_custody_refused"
    STAGE_CHANGED_PRESERVE = "stage_changed_preserve"
    DESTINATION_CHANGED_PRESERVE = "destination_changed_preserve"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    UNSUPPORTED = "unsupported"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateRetainedStageCustodyState, str] = {
    PrivateRetainedStageCustodyState.STAGE_AND_DESTINATION_OBSERVED_NO_WRITE: (
        "Existing stage custody and guarded destination evidence remained stable. "
        "Guard released; no production replacement or commit is authorized."
    ),
    PrivateRetainedStageCustodyState.INVALID_REQUEST: "Invalid native custody request.",
    PrivateRetainedStageCustodyState.OPERATION_NOT_ADMITTED: "Only an existing prepared registry stage can be reviewed.",
    PrivateRetainedStageCustodyState.REVISION_MISMATCH_REFUSED: "Prepared revision was refused.",
    PrivateRetainedStageCustodyState.INTENT_UNQUALIFIED: "Canonical transaction intent was refused.",
    PrivateRetainedStageCustodyState.ROOT_UNQUALIFIED: "Private or workspace root was unqualified.",
    PrivateRetainedStageCustodyState.NATIVE_PROTECTION_REFUSED: "Native OS owner or filesystem protection was refused.",
    PrivateRetainedStageCustodyState.OWNER_CHANGED: "Effective OS owner changed during held custody.",
    PrivateRetainedStageCustodyState.BINDING_MISMATCH: "Workspace association or owner binding was unqualified.",
    PrivateRetainedStageCustodyState.STAGE_CUSTODY_REFUSED: "Existing stage handle or parent could not be retained safely.",
    PrivateRetainedStageCustodyState.STAGE_CHANGED_PRESERVE: "Retained stage identity, metadata or pathname changed.",
    PrivateRetainedStageCustodyState.DESTINATION_CHANGED_PRESERVE: "Guarded registry destination identity changed.",
    PrivateRetainedStageCustodyState.NAMESPACE_CONFLICT_PRESERVE: "Pending stage or transaction namespace changed.",
    PrivateRetainedStageCustodyState.IMAGE_CONFLICT_PRESERVE: "Exact transaction or after-image changed under custody.",
    PrivateRetainedStageCustodyState.GUARD_REFUSED: "Native retained guard was refused or failed release.",
    PrivateRetainedStageCustodyState.INTERRUPTED_PRESERVE: "Custody review interrupted; preserve pending artifacts.",
    PrivateRetainedStageCustodyState.UNSUPPORTED: "Native stage custody unsupported for this OS.",
    PrivateRetainedStageCustodyState.IO_ERROR: "Native custody observation could not complete safely.",
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateRetainedStageCustodyReview:
    state: PrivateRetainedStageCustodyState
    message: str
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateRetainedStageCustodyReview(non_authorizing=True)"


def _result(
    state: PrivateRetainedStageCustodyState,
) -> PrivateRetainedStageCustodyReview:
    return PrivateRetainedStageCustodyReview(state, _MESSAGES[state], barrier._REQUIRED)


class _StageRefused(Exception):
    """No native handle, private path or owner is disclosed."""


class _StageChanged(Exception):
    """Protected stage entry did not retain its original identity."""


def _stage_name(tx: str) -> str:
    # The transaction ID is already validated by the strict canonical codec.
    # Never use unchecked text as a file component.
    if (
        type(tx) is not str
        or len(tx) != 36
        or not all(item in "0123456789abcdef-" for item in tx)
    ):
        raise _StageRefused
    return "." + tx + ".registry-stage"


@contextmanager
def _held_linux_stage(
    private_root: Path, name: str, owner: inspection.EffectiveOSOwner, size: int
) -> Iterator[Callable[[], bool]]:
    if owner.kind != "posix_euid" or not getattr(os, "O_NOFOLLOW", 0):
        raise _StageRefused
    if not owner.value.isdecimal() or int(owner.value) <= 0:
        raise _StageRefused
    uid = int(owner.value)
    if getattr(os, "geteuid", lambda: -1)() != uid:
        raise _StageRefused
    parent, failure = posix._open_verified_parent(private_root, uid)
    if failure is not None or parent is None:
        raise _StageRefused
    handle: int | None = None
    try:
        opened: int = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        handle = opened
        parent_signature = registry_guard._linux_signature(os.fstat(parent))
        stage_signature = registry_guard._linux_signature(os.fstat(opened))
        if stage_signature[0:2] == parent_signature[0:2]:
            raise _StageRefused

        def check() -> bool:
            try:
                if getattr(os, "geteuid", lambda: -1)() != uid:
                    return False
                native_parent = os.fstat(parent)
                parent_path = private_root.lstat()
                held_info = os.fstat(opened)
                entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(native_parent.st_mode)
                    or not stat.S_ISDIR(parent_path.st_mode)
                    or not stat.S_ISREG(held_info.st_mode)
                    or not stat.S_ISREG(entry.st_mode)
                    or registry_guard._linux_signature(native_parent)
                    != parent_signature
                    or registry_guard._linux_signature(parent_path) != parent_signature
                    or registry_guard._linux_signature(held_info) != stage_signature
                    or registry_guard._linux_signature(entry) != stage_signature
                    or held_info.st_size != size
                    or held_info.st_nlink != 1
                    or held_info.st_uid != uid
                    or stat.S_IMODE(held_info.st_mode) != 0o600
                    or posix._acl_absent(opened) is not None
                    or not posix._is_known_local_filesystem(opened)
                ):
                    return False
                return True
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                return False

        if not check():
            raise _StageRefused
        yield check
        if not check():
            raise _StageChanged
    finally:
        if handle is not None:
            os.close(handle)
        os.close(parent)


@contextmanager
def _held_windows_stage(
    private_root: Path, name: str, owner: inspection.EffectiveOSOwner, size: int
) -> Iterator[Callable[[], bool]]:
    if owner.kind != "windows_token_sid":
        raise _StageRefused
    kernel = None
    handle: int | None = None
    try:
        kernel, advapi = wincheck._bind_api()
        path = private_root / name
        # FILE_READ_ATTRIBUTES | READ_CONTROL, share read/write/delete;
        # OPEN_EXISTING with reparse-point inspection, no file creation.
        opened, error = anchor._windows_open(kernel, path)
        if opened is None:
            raise _StageRefused from OSError(error, "Stage open refused")
        handle = opened
        signature = registry_guard._windows_signature(kernel, opened)
        if signature is None or signature[2] != size:
            raise _StageRefused
        expected: tuple[int, bytes, int, int, int] = signature

        def check() -> bool:
            try:
                registry_guard._windows_check(
                    kernel, advapi, path, opened, expected, owner
                )
                return registry_guard._windows_signature(kernel, opened) == expected
            except (
                registry_guard.RetainedRegistryGuardError,
                OSError,
                ValueError,
                TypeError,
                AttributeError,
                OverflowError,
            ):
                return False

        if not check():
            raise _StageRefused
        yield check
        if not check():
            raise _StageChanged
    finally:
        if kernel is not None and handle is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle))


@contextmanager
def _held_stage(
    private_root: Path, tx: str, owner: inspection.EffectiveOSOwner, size: int
) -> Iterator[Callable[[], bool]]:
    name = _stage_name(tx)
    if sys.platform not in {"linux", "win32"}:
        raise _StageRefused
    if type(size) is not int or size <= 0:
        raise _StageRefused
    with (
        _held_linux_stage(private_root, name, owner, size)
        if sys.platform == "linux"
        else _held_windows_stage(private_root, name, owner, size)
    ) as still_held:
        yield still_held


def review_retained_production_stage_and_destination(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRetainedStageCustodyReview:
    """Read-only, operation-owned two-file evidence; result is not a write permit.

    Core owns the native guard for the entire observation. Registry/descriptor/
    journal handles remain held by the inherited guard, stage is held here.
    Neither any native handle nor a callback crosses the public return boundary.
    """
    state = PrivateRetainedStageCustodyState
    if (
        type(step) is not scratch.PrivateScratchWriterStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(state.INVALID_REQUEST)
    if step is not scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if not lock_file._requested_root(
        existing_private_root, sys.platform
    ) or not descriptor._valid_root(existing_workspace_root):
        return _result(state.ROOT_UNQUALIFIED)
    try:
        candidate = barrier.review_private_production_write_barrier(
            step, expected_revision, proposed
        )
        if type(candidate) is not barrier.PrivateProductionWriteBarrierReview:
            return _result(state.INTENT_UNQUALIFIED)
        if (
            candidate.state
            is barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ):
            return _result(state.REVISION_MISMATCH_REFUSED)
        if (
            candidate.state
            is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ):
            return _result(state.INTENT_UNQUALIFIED)
        raw = intents.encode_private_transaction_intent(proposed)
        if type(raw) is not bytes or len(raw) > intents.MAX_INTENT_BYTES:
            return _result(state.INTENT_UNQUALIFIED)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
            or type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        before = checked.registry_before
        after = checked.registry_after
        sidecar = checked.descriptor_before
        if (
            type(before) is not bytes
            or type(after) is not bytes
            or type(sidecar) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        tx = checked.witness.transaction_id
        refusal, owner = preflight._native_observation(existing_private_root)
        if refusal is not None or owner is None:
            return _result(state.NATIVE_PROTECTION_REFUSED)
        binding = preflight._intent_owner_and_binding(
            checked, owner, existing_workspace_root
        )
        if binding is not None:
            return _result(state.BINDING_MISMATCH)
        with retained._hold_existing_retained_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            fresh = intents.decode_private_transaction_intent(raw)
            if (
                type(fresh) is not intents.PrivateTransactionIntent
                or fresh != checked
                or intents.encode_private_transaction_intent(fresh) != raw
            ):
                return _result(state.INTENT_UNQUALIFIED)
            expected_namespace = recovery._namespace(existing_private_root, tx)
            if (
                type(expected_namespace) is not tuple
                or len(expected_namespace) != 3
                or expected_namespace[2] is not True
            ):
                return _result(state.NAMESPACE_CONFLICT_PRESERVE)
            wanted = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            expected_images: parents._Image = (raw, before, sidecar, after)
            with _held_stage(
                existing_private_root, tx, owner, len(after)
            ) as stage_still_held:
                baseline: scope._Frame | None = None
                for _ in range(3):
                    again, same_owner = preflight._native_observation(
                        existing_private_root, owner
                    )
                    if (
                        again is not None
                        or same_owner is None
                        or ordered._owner() != owner
                    ):
                        return _result(state.OWNER_CHANGED)
                    if not stage_still_held():
                        return _result(state.STAGE_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root, tx, owner, expected_namespace, wanted
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    frame = scope._observe(
                        existing_private_root,
                        existing_workspace_root,
                        fresh,
                        owner,
                        len(raw),
                    )
                    if not stage_still_held():
                        return _result(state.STAGE_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root, tx, owner, expected_namespace, wanted
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    refusal_code = scope._frame_state(frame, baseline, expected_images)
                    if refusal_code is not None:
                        if (
                            refusal_code
                            is scope.PrivateProtectedWriterScopeState.FILE_CONFLICT_PRESERVE
                        ):
                            return _result(state.DESTINATION_CHANGED_PRESERVE)
                        return _result(state.IMAGE_CONFLICT_PRESERVE)
                    if baseline is None:
                        baseline = frame
                last_refusal, last_owner = preflight._native_observation(
                    existing_private_root, owner
                )
                if (
                    last_refusal is not None
                    or last_owner is None
                    or ordered._owner() != owner
                ):
                    return _result(state.OWNER_CHANGED)
                if not stage_still_held():
                    return _result(state.STAGE_CHANGED_PRESERVE)
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, expected_namespace, wanted
                ):
                    return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                if (
                    baseline is None
                    or parents._parents(existing_private_root, existing_workspace_root)
                    != baseline.parent_stamps
                ):
                    return _result(state.DESTINATION_CHANGED_PRESERVE)
        # Return only after both native contexts release successfully.
        return _result(state.STAGE_AND_DESTINATION_OBSERVED_NO_WRITE)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except _StageChanged:
        return _result(state.STAGE_CHANGED_PRESERVE)
    except _StageRefused:
        return _result(state.STAGE_CUSTODY_REFUSED)
    except (
        scope._ImageUnqualified,
        parents._ParentUnqualified,
        bridge._IdentityUnqualified,
    ):
        return _result(state.IMAGE_CONFLICT_PRESERVE)
    except pair._NamespaceChanged:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except retained.RetainedDescriptorGuardError as error:
        if error.code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
            return _result(state.OWNER_CHANGED)
        if error.code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
            return _result(state.UNSUPPORTED)
        return _result(state.GUARD_REFUSED)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(state.OWNER_CHANGED)
        return _result(state.GUARD_REFUSED)
    except FileNotFoundError:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except PermissionError:
        return _result(state.GUARD_REFUSED)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        intents.PrivateIntentError,
        registry_guard.RetainedRegistryGuardError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
