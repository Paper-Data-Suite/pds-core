"""Native descriptor-after-stage prerequisite for canonical FORK_COPY (#238 3G55).

This is an INTERNAL read-only security boundary. The 3G54 protected handoff
covers a pending journal, registry before-image and registry stage, but a
FORK_COPY also needs a prepared descriptor after-image. Observe that *other*
stage while the existing ordered journal+descriptor scope remains held, using
no-follow native file reads and two equal identity+byte observations.

No result is a write token, staged writer, retirement/commit certificate,
proof of sync durability or Notes capability. No paths or handles escape.
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
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateDescriptorStageState(str, Enum):
    STAGE_PRESENT_BARRIER_BLOCKED = "stage_present_barrier_blocked"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    INTENT_UNQUALIFIED = "intent_unqualified"
    FORK_REQUIRED = "fork_required"
    REVISION_MISMATCH = "revision_mismatch"
    ROOT_UNQUALIFIED = "root_unqualified"
    BARRIER_UNQUALIFIED = "barrier_unqualified"
    OWNER_OR_BINDING_REFUSED = "owner_or_binding_refused"
    OWNER_CHANGED = "owner_changed"
    CHECKPOINT_CONFLICT_PRESERVE = "checkpoint_conflict_preserve"
    STAGE_MISSING_PRESERVE = "stage_missing_preserve"
    STAGE_UNSAFE_PRESERVE = "stage_unsafe_preserve"
    STAGE_IMAGE_CONFLICT_PRESERVE = "stage_image_conflict_preserve"
    STAGE_CHANGED_PRESERVE = "stage_changed_preserve"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateDescriptorStageState, str] = {
    item: "Descriptor-stage native custody is unqualified; preserve pending transaction evidence."
    for item in PrivateDescriptorStageState
}
_MESSAGES[PrivateDescriptorStageState.STAGE_PRESENT_BARRIER_BLOCKED] = (
    "Canonical descriptor after-stage was read twice under an existing protected "
    "journal/descriptor scope. Production writing remains blocked."
)
_MESSAGES[PrivateDescriptorStageState.STAGE_MISSING_PRESERVE] = (
    "Prepared descriptor after-stage is absent. No registry replacement is permitted."
)
_MESSAGES[PrivateDescriptorStageState.STAGE_IMAGE_CONFLICT_PRESERVE] = (
    "Prepared descriptor stage differs from the canonical after-image."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDescriptorStageReview:
    state: PrivateDescriptorStageState
    message: str
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    automatic_retry_forbidden: bool = True
    journal_retirement_forbidden: bool = True
    durability_unqualified: bool = True
    native_custody_expires_on_release: bool = True
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(default=barrier._REQUIRED, repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateDescriptorStageReview(non_authorizing=True)"


def _result(state: PrivateDescriptorStageState) -> PrivateDescriptorStageReview:
    return PrivateDescriptorStageReview(state, _MESSAGES[state])


class _ReadState(str, Enum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNSAFE = "unsafe"
    REFUSED = "refused"


_Fingerprint = tuple[int, ...] | tuple[int, bytes, int, int, int]


@dataclass(frozen=True, slots=True, repr=False)
class _StageRead:
    state: _ReadState
    image: bytes | None = field(default=None, repr=False)
    identity: _Fingerprint | None = field(default=None, repr=False)


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_linux(root: Path, stage_name: str) -> _StageRead:
    """Read through a no-follow dirfd walk; never follow a workspace symlink."""
    if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
        return _StageRead(_ReadState.REFUSED)
    directory: int | None = None
    opened: int | None = None
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW")
        | getattr(os, "O_DIRECTORY")
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory = os.open("/", flags)
        for item in (*root.parts[1:], ".pds"):
            following = os.open(item, flags, dir_fd=directory)
            os.close(directory)
            directory = following
        parent = _signature(os.fstat(directory))
        if parent != _signature(os.lstat(root / ".pds")):
            return _StageRead(_ReadState.UNSAFE)
        opened = os.open(
            stage_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory,
        )
        first = os.fstat(opened)
        same_entry = os.stat(stage_name, dir_fd=directory, follow_symlinks=False)
        if (
            not stat.S_ISREG(first.st_mode)
            or first.st_nlink != 1
            or _signature(first) != _signature(same_entry)
            or not 0 < first.st_size <= metadata.MAX_ASSOCIATION_BYTES
        ):
            return _StageRead(_ReadState.UNSAFE)
        data = bytearray()
        while len(data) <= metadata.MAX_ASSOCIATION_BYTES:
            chunk = os.read(
                opened, min(4096, metadata.MAX_ASSOCIATION_BYTES + 1 - len(data))
            )
            if not chunk:
                break
            data.extend(chunk)
        if (
            len(data) != first.st_size
            or _signature(os.fstat(opened)) != _signature(first)
            or _signature(os.stat(stage_name, dir_fd=directory, follow_symlinks=False))
            != _signature(first)
            or _signature(os.fstat(directory)) != parent
            or _signature(os.lstat(root / ".pds")) != parent
        ):
            return _StageRead(_ReadState.UNSAFE)
        return _StageRead(_ReadState.OBSERVED, bytes(data), _signature(first))
    except FileNotFoundError:
        return _StageRead(_ReadState.MISSING)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _StageRead(_ReadState.REFUSED)
    finally:
        if opened is not None:
            os.close(opened)
        if directory is not None:
            os.close(directory)


def _read_windows(root: Path, stage_name: str) -> _StageRead:
    """Read using non-following Win32 HANDLE and stable FileIdInfo signature."""
    kernel: Any = None
    original: int | None = None
    reopened: int | None = None
    path = root / ".pds" / stage_name
    try:
        kernel = descriptor._windows_api()
        if descriptor._windows_ancestry(kernel, root) is not None:
            return _StageRead(_ReadState.UNSAFE)
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
        raw = kernel.CreateFileW(str(path), 0x80000000, 0x1, None, 3, 0x00200000, None)
        original = ctypes.cast(raw, ctypes.c_void_p).value
        if original is None or original == ctypes.c_void_p(-1).value:
            original = None
            return _StageRead(
                _ReadState.MISSING
                if ctypes.get_last_error() in (2, 3)
                else _ReadState.REFUSED
            )
        signature = retained._windows_signature(kernel, original, directory=False)
        if signature is None:
            return _StageRead(_ReadState.UNSAFE)
        size = signature[2]
        buffer = ctypes.create_string_buffer(size)
        offset = 0
        while offset < size:
            received = wintypes.DWORD()
            if (
                not kernel.ReadFile(
                    wintypes.HANDLE(original),
                    ctypes.byref(buffer, offset),
                    size - offset,
                    ctypes.byref(received),
                    None,
                )
                or received.value == 0
            ):
                return _StageRead(_ReadState.REFUSED)
            offset += received.value
        if retained._windows_signature(kernel, original, directory=False) != signature:
            return _StageRead(_ReadState.UNSAFE)
        reopened, _error = descriptor._windows_open(kernel, str(path), directory=False)
        if (
            reopened is None
            or retained._windows_signature(kernel, reopened, directory=False)
            != signature
            or descriptor._windows_ancestry(kernel, root) is not None
        ):
            return _StageRead(_ReadState.UNSAFE)
        return _StageRead(_ReadState.OBSERVED, buffer.raw, signature)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _StageRead(_ReadState.REFUSED)
    finally:
        if kernel is not None:
            if reopened is not None:
                kernel.CloseHandle(wintypes.HANDLE(reopened))
            if original is not None:
                kernel.CloseHandle(wintypes.HANDLE(original))


def _barrier_blocked(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    checked: intents.PrivateTransactionIntent,
) -> bool:
    reviewed = barrier.review_private_production_write_barrier(
        step, expected_revision, checked
    )
    return (
        type(reviewed) is barrier.PrivateProductionWriteBarrierReview
        and reviewed.state
        is barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        and reviewed.unqualified_requirements == barrier._REQUIRED
    )


def _read_stage(root: Path, name: str) -> _StageRead:
    if sys.platform == "linux":
        return _read_linux(root, name)
    return _read_windows(root, name)


def review_prepared_canonical_descriptor_stage(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateDescriptorStageReview:
    """Qualify only a READ-ONLY descriptor-stage observation under native guards.

    The transaction-specific descriptor stage must be prepared in advance by a
    separately qualified writer; this function never creates it. The journal,
    original workspace descriptor and ordered local locks are retained by the
    transition guard. The registry transition still requires independent full
    operation-owned admission, native CAS and crash recovery before writing.
    """
    state = PrivateDescriptorStageState
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
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(state.INTENT_UNQUALIFIED)
        if checked.witness.operation is not witness.PrivateBindingOperation.FORK_COPY:
            return _result(state.FORK_REQUIRED)
        if (
            type(checked.descriptor_before) is not bytes
            or type(checked.descriptor_after) is not bytes
            or checked.descriptor_before == checked.descriptor_after
            or type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or checked.registry_before == checked.registry_after
        ):
            return _result(state.INTENT_UNQUALIFIED)
        if expected_revision != checked.witness.registry_revision_before:
            return _result(state.REVISION_MISMATCH)
        if not lock_file._requested_root(
            existing_private_root, sys.platform
        ) or not descriptor._valid_root(existing_workspace_root):
            return _result(state.ROOT_UNQUALIFIED)
        if not _barrier_blocked(step, expected_revision, checked):
            return _result(state.BARRIER_UNQUALIFIED)
        stage_name = "." + checked.witness.transaction_id + ".descriptor-stage"
        refusal, owner = preflight._native_observation(existing_private_root)
        if refusal is not None or owner is None:
            return _result(state.OWNER_OR_BINDING_REFUSED)
        if (
            preflight._intent_owner_and_binding(checked, owner, existing_workspace_root)
            is not None
        ):
            return _result(state.OWNER_OR_BINDING_REFUSED)
        with transition._hold_transitionable_journal_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            first: _StageRead | None = None
            for _ in range(2):
                if (
                    recovery._classify_present(
                        checked, existing_private_root, existing_workspace_root, owner
                    )
                    is not recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED
                ):
                    return _result(state.CHECKPOINT_CONFLICT_PRESERVE)
                observed = _read_stage(existing_workspace_root, stage_name)
                if observed.state is _ReadState.MISSING:
                    return _result(state.STAGE_MISSING_PRESERVE)
                if (
                    observed.state is not _ReadState.OBSERVED
                    or type(observed.image) is not bytes
                    or observed.identity is None
                ):
                    return _result(state.STAGE_UNSAFE_PRESERVE)
                if observed.image != checked.descriptor_after:
                    return _result(state.STAGE_IMAGE_CONFLICT_PRESERVE)
                if first is None:
                    first = observed
                elif observed != first:
                    return _result(state.STAGE_CHANGED_PRESERVE)
                if ordered._owner() != owner:
                    return _result(state.OWNER_CHANGED)
            if not _barrier_blocked(step, expected_revision, checked):
                return _result(state.BARRIER_UNQUALIFIED)
        return _result(state.STAGE_PRESENT_BARRIER_BLOCKED)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except transition._WriterGuardRefused:
        return _result(state.GUARD_REFUSED)
    except intents.PrivateIntentError:
        return _result(state.INTENT_UNQUALIFIED)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
