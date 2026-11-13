"""Transition-aware native registry/stage identity custody (Core #238 3G42).

Retains *both* native file handles inside the 3G41 journal/descriptor guard.
A detached old registry handle is not itself a conflict after a future rename:
only the retained stage ID may become the new registry entry. This reader
never renames, exposes a writer/handle, permits recovery, or proves durability.
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
from typing import Callable, Iterator, TypeAlias

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_retained_stage_custody as stage
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_retained_registry_guard as registry
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


NativeKey: TypeAlias = tuple[int, bytes]


class PrivateRegistryTransitionIdentityState(str, Enum):
    PREPARED_IDENTITIES_OBSERVED_NO_WRITE = "prepared_identities_observed_no_write"
    EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED = (
        "expected_stage_installed_recovery_required"
    )
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_OR_PROTECTION_REFUSED = "owner_or_protection_refused"
    OWNER_CHANGED = "owner_changed"
    BINDING_UNQUALIFIED = "binding_unqualified"
    NATIVE_HANDLE_REFUSED = "native_handle_refused"
    PARENT_CHANGED_PRESERVE = "parent_changed_preserve"
    OLD_HANDLE_CHANGED_PRESERVE = "old_handle_changed_preserve"
    STAGE_HANDLE_CHANGED_PRESERVE = "stage_handle_changed_preserve"
    REGISTRY_MISSING_PRESERVE = "registry_missing_preserve"
    STAGE_MISSING_BEFORE_PRESERVE = "stage_missing_before_preserve"
    REGISTRY_FOREIGN_PRESERVE = "registry_foreign_preserve"
    STAGE_FOREIGN_PRESERVE = "stage_foreign_preserve"
    IDENTITY_ALIAS_PRESERVE = "identity_alias_preserve"
    UNQUALIFIED_NAMESPACE_PRESERVE = "unqualified_namespace_preserve"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateRegistryTransitionIdentityState, str] = {
    item: "Private registry transition identity requires protected recovery review; no write permitted."
    for item in PrivateRegistryTransitionIdentityState
}
_MESSAGES[
    PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
] = "Retained old-registry and staged identities remained prepared under one guard; no write."
_MESSAGES[
    PrivateRegistryTransitionIdentityState.EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED
] = "Stage native identity appears at registry entry; canonical bytes and durability remain unqualified."


@dataclass(frozen=True, slots=True, repr=False)
class PrivateRegistryTransitionIdentityReview:
    state: PrivateRegistryTransitionIdentityState
    message: str
    pending_evidence_must_remain: bool = True
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(default=barrier._REQUIRED, repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateRegistryTransitionIdentityReview(non_authorizing=True)"


def _result(
    state: PrivateRegistryTransitionIdentityState,
) -> PrivateRegistryTransitionIdentityReview:
    return PrivateRegistryTransitionIdentityReview(state, _MESSAGES[state])


@dataclass(frozen=True, slots=True, repr=False)
class _Identities:
    parent: NativeKey
    old: NativeKey
    staged: NativeKey

    def __repr__(self) -> str:
        return "_Identities(redacted=True)"


@dataclass(frozen=True, slots=True, repr=False)
class _Entries:
    parent: NativeKey | None
    old_held: NativeKey | None
    staged_held: NativeKey | None
    registry: NativeKey | None
    stage: NativeKey | None

    def __repr__(self) -> str:
        return "_Entries(redacted=True)"


def _native_key(volume: int, identifier: bytes) -> NativeKey | None:
    if (
        type(volume) is not int
        or volume < 0
        or type(identifier) is not bytes
        or len(identifier) != 16
        or not any(identifier)
    ):
        return None
    return volume, identifier


def _transition_state(
    baseline: _Identities,
    observed: _Entries,
) -> PrivateRegistryTransitionIdentityState:
    """Classify only native identities; NEVER infer bytes, owner or durability.

    Distinct old/stage IDs and an unchanged parent are mandatory. Stage may be
    consumed only when its exact original native ID becomes the registry ID.
    The retained old/stage handles must themselves retain their IDs. A separate
    journal/descriptor/canonical-image protocol remains necessary for writes.
    """
    state = PrivateRegistryTransitionIdentityState
    if type(baseline) is not _Identities or type(observed) is not _Entries:
        return state.INVALID_REQUEST
    native = (baseline.parent, baseline.old, baseline.staged)
    if any(_native_key(*key) != key for key in native):
        return state.INVALID_REQUEST
    if len(set(native)) != 3:
        return state.IDENTITY_ALIAS_PRESERVE
    if observed.parent != baseline.parent:
        return state.PARENT_CHANGED_PRESERVE
    if observed.old_held != baseline.old:
        return state.OLD_HANDLE_CHANGED_PRESERVE
    if observed.staged_held != baseline.staged:
        return state.STAGE_HANDLE_CHANGED_PRESERVE
    if observed.registry is None:
        return state.REGISTRY_MISSING_PRESERVE
    if observed.registry == baseline.old:
        if observed.stage is None:
            return state.STAGE_MISSING_BEFORE_PRESERVE
        if observed.stage != baseline.staged:
            return state.STAGE_FOREIGN_PRESERVE
        return state.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
    if observed.registry == baseline.staged:
        if observed.stage is not None:
            return state.STAGE_FOREIGN_PRESERVE
        return state.EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED
    return state.REGISTRY_FOREIGN_PRESERVE


class _IdentityRefused(Exception):
    """No identifying metadata is disclosed in failure messages."""


def _linux_key(info: os.stat_result) -> NativeKey | None:
    if info.st_ino <= 0:
        return None
    try:
        return _native_key(info.st_dev, info.st_ino.to_bytes(16, "big"))
    except (OverflowError, ValueError, AttributeError):
        return None


@contextmanager
def _held_linux_pair(
    private_root: Path,
    stage_name: str,
    owner: inspection.EffectiveOSOwner,
    before_size: int,
    after_size: int,
) -> Iterator[Callable[[], PrivateRegistryTransitionIdentityState]]:
    if (
        owner.kind != "posix_euid"
        or not owner.value.isdecimal()
        or not getattr(os, "O_NOFOLLOW", 0)
    ):
        raise _IdentityRefused
    uid = int(owner.value)
    if uid <= 0 or getattr(os, "geteuid", lambda: -1)() != uid:
        raise _IdentityRefused
    parent, failure = posix._open_verified_parent(private_root, uid)
    if failure is not None or parent is None:
        raise _IdentityRefused
    opened: list[int] = []
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        for name in ("registry.json", stage_name):
            opened.append(os.open(name, flags, dir_fd=parent))
        old, staged = opened
        parent_info = os.fstat(parent)
        old_info = os.fstat(old)
        staged_info = os.fstat(staged)
        parent_key = _linux_key(parent_info)
        old_key = _linux_key(old_info)
        staged_key = _linux_key(staged_info)
        if parent_key is None or old_key is None or staged_key is None:
            raise _IdentityRefused
        baseline = _Identities(parent_key, old_key, staged_key)

        def _protected(fd: int, info: os.stat_result, size: int) -> bool:
            return (
                stat.S_ISREG(info.st_mode)
                and info.st_size == size
                and info.st_uid == uid
                and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_dev == parent_info.st_dev
                and posix._acl_absent(fd) is None
                and posix._is_known_local_filesystem(fd)
            )

        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or not _protected(old, old_info, before_size)
            or not _protected(staged, staged_info, after_size)
            or _linux_key(
                os.stat("registry.json", dir_fd=parent, follow_symlinks=False)
            )
            != old_key
            or _linux_key(os.stat(stage_name, dir_fd=parent, follow_symlinks=False))
            != staged_key
            or _transition_state(
                baseline, _Entries(parent_key, old_key, staged_key, old_key, staged_key)
            )
            is not PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _IdentityRefused

        def _entry(name: str) -> NativeKey | None:
            try:
                entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return None
            if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
                raise _IdentityRefused
            return _linux_key(entry)

        def check() -> PrivateRegistryTransitionIdentityState:
            state = PrivateRegistryTransitionIdentityState
            try:
                if getattr(os, "geteuid", lambda: -1)() != uid:
                    return state.OWNER_CHANGED
                actual_parent = os.fstat(parent)
                path_parent = private_root.lstat()
                if (
                    _linux_key(actual_parent) != parent_key
                    or _linux_key(path_parent) != parent_key
                ):
                    return state.PARENT_CHANGED_PRESERVE
                if (
                    not stat.S_ISDIR(actual_parent.st_mode)
                    or not stat.S_ISDIR(path_parent.st_mode)
                    or not _protected(old, os.fstat(old), before_size)
                    or not _protected(staged, os.fstat(staged), after_size)
                ):
                    return state.OWNER_OR_PROTECTION_REFUSED
                result = _transition_state(
                    baseline,
                    _Entries(
                        parent_key,
                        _linux_key(os.fstat(old)),
                        _linux_key(os.fstat(staged)),
                        _entry("registry.json"),
                        _entry(stage_name),
                    ),
                )
                return result
            except _IdentityRefused:
                return state.UNQUALIFIED_NAMESPACE_PRESERVE
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                return state.IO_ERROR

        if (
            check()
            is not PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _IdentityRefused
        yield check
        if (
            check()
            is not PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _IdentityRefused
    finally:
        for fd in reversed(opened):
            os.close(fd)
        os.close(parent)


@contextmanager
def _held_windows_pair(
    private_root: Path,
    stage_name: str,
    owner: inspection.EffectiveOSOwner,
    before_size: int,
    after_size: int,
) -> Iterator[Callable[[], PrivateRegistryTransitionIdentityState]]:
    if owner.kind != "windows_token_sid":
        raise _IdentityRefused
    kernel = None
    handles: list[int] = []
    try:
        kernel, advapi = wincheck._bind_api()
        if (
            not wincreate._known_fixed_local_volume(kernel, private_root)
            or wincheck._native_windows_walk(private_root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            raise _IdentityRefused
        for path in (
            private_root,
            private_root / "registry.json",
            private_root / stage_name,
        ):
            handle, _error = anchor._windows_open(kernel, path)
            if handle is None:
                raise _IdentityRefused
            handles.append(handle)
        parent, old, staged = handles
        parent_info = descriptor._windows_info(kernel, parent)
        parent_id = anchor._windows_id(kernel, parent)
        old_signature = registry._windows_signature(kernel, old)
        staged_signature = registry._windows_signature(kernel, staged)
        if (
            parent_info is None
            or not parent_info[1].directory
            or parent_info[1].delete_pending
            or parent_id is None
            or old_signature is None
            or staged_signature is None
            or old_signature[2] != before_size
            or staged_signature[2] != after_size
            or wincheck._handle_dacl_state(kernel, advapi, parent, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            raise _IdentityRefused
        parent_key = _native_key(*parent_id)
        old_key = _native_key(old_signature[0], old_signature[1])
        stage_key = _native_key(staged_signature[0], staged_signature[1])
        if parent_key is None or old_key is None or stage_key is None:
            raise _IdentityRefused
        baseline = _Identities(parent_key, old_key, stage_key)

        def _entry(name: str) -> NativeKey | None:
            handle, error = anchor._windows_open(kernel, private_root / name)
            if handle is None:
                if error in (2, 3):
                    return None
                raise _IdentityRefused
            try:
                signature = registry._windows_signature(kernel, handle)
                if (
                    signature is None
                    or wincheck._handle_dacl_state(kernel, advapi, handle, owner)
                    is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                ):
                    raise _IdentityRefused
                return _native_key(signature[0], signature[1])
            finally:
                kernel.CloseHandle(wintypes.HANDLE(handle))

        def check() -> PrivateRegistryTransitionIdentityState:
            state = PrivateRegistryTransitionIdentityState
            try:
                if ordered._owner() != owner:
                    return state.OWNER_CHANGED
                if (
                    anchor._windows_id(kernel, parent) != parent_id
                    or not wincreate._known_fixed_local_volume(kernel, private_root)
                    or wincheck._native_windows_walk(private_root, owner)
                    is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                ):
                    return state.PARENT_CHANGED_PRESERVE
                if (
                    anchor._windows_id(kernel, old) != old_signature[:2]
                    or anchor._windows_id(kernel, staged) != staged_signature[:2]
                ):
                    return state.OLD_HANDLE_CHANGED_PRESERVE
                if (
                    wincheck._handle_dacl_state(kernel, advapi, old, owner)
                    is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                    or wincheck._handle_dacl_state(kernel, advapi, staged, owner)
                    is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                ):
                    return state.OWNER_OR_PROTECTION_REFUSED
                return _transition_state(
                    baseline,
                    _Entries(
                        parent_key,
                        _native_key(old_signature[0], old_signature[1]),
                        _native_key(staged_signature[0], staged_signature[1]),
                        _entry("registry.json"),
                        _entry(stage_name),
                    ),
                )
            except _IdentityRefused:
                return state.UNQUALIFIED_NAMESPACE_PRESERVE
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                return state.IO_ERROR

        if (
            check()
            is not PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _IdentityRefused
        yield check
        if (
            check()
            is not PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _IdentityRefused
    finally:
        if kernel is not None:
            for handle in reversed(handles):
                kernel.CloseHandle(wintypes.HANDLE(handle))


@contextmanager
def _held_registry_stage_pair(
    private_root: Path,
    tx: str,
    owner: inspection.EffectiveOSOwner,
    before_size: int,
    after_size: int,
) -> Iterator[Callable[[], PrivateRegistryTransitionIdentityState]]:
    if sys.platform not in {"win32", "linux"}:
        raise _IdentityRefused
    if (
        type(before_size) is not int
        or type(after_size) is not int
        or not (0 < before_size <= metadata.MAX_REGISTRY_BYTES)
        or not (0 < after_size <= metadata.MAX_REGISTRY_BYTES)
    ):
        raise _IdentityRefused
    name = stage._stage_name(tx)
    with (
        _held_linux_pair(private_root, name, owner, before_size, after_size)
        if sys.platform == "linux"
        else _held_windows_pair(private_root, name, owner, before_size, after_size)
    ) as check:
        yield check


def review_native_registry_transition_identity_custody(
    existing_private_root: Path,
    existing_workspace_root: Path,
    tx: str,
    before_size: int,
    after_size: int,
) -> PrivateRegistryTransitionIdentityReview:
    """Read-only native custody inside the 3G41 guard; not canonical admission.

    Caller sizes and transaction ID are untrusted. Positive outcomes mean
    native IDs only, never a valid transaction, matching bytes or write permit.
    The transitional AFTER outcome is modeled and tested by the private state
    classifier; the live entrypoint performs NO mutation and accepts only the
    stable PREPARED state, deferring actual replacement to a future protocol.
    """
    state = PrivateRegistryTransitionIdentityState
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
        or type(before_size) is not int
        or not (0 < before_size <= metadata.MAX_REGISTRY_BYTES)
        or type(after_size) is not int
        or not (0 < after_size <= metadata.MAX_REGISTRY_BYTES)
    ):
        return _result(state.INVALID_REQUEST)
    try:
        stage._stage_name(tx)
    except (stage._StageRefused, ValueError, TypeError, AttributeError):
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    try:
        refusal, owner = preflight._native_observation(existing_private_root)
        if refusal is not None or owner is None:
            return _result(state.OWNER_OR_PROTECTION_REFUSED)
        with transition._hold_transitionable_journal_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            fresh_refusal, fresh_owner = preflight._native_observation(
                existing_private_root, owner
            )
            if fresh_refusal is not None or fresh_owner is None:
                return _result(state.OWNER_OR_PROTECTION_REFUSED)
            with _held_registry_stage_pair(
                existing_private_root, tx, owner, before_size, after_size
            ) as check:
                for _ in range(4):
                    if ordered._owner() != owner:
                        return _result(state.OWNER_CHANGED)
                    observation = check()
                    if observation is not state.PREPARED_IDENTITIES_OBSERVED_NO_WRITE:
                        return _result(observation)
                observation = check()
                if observation is not state.PREPARED_IDENTITIES_OBSERVED_NO_WRITE:
                    return _result(observation)
        return _result(state.PREPARED_IDENTITIES_OBSERVED_NO_WRITE)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except (transition._WriterGuardRefused, _IdentityRefused):
        return _result(state.GUARD_REFUSED)
    except PermissionError:
        return _result(state.NATIVE_HANDLE_REFUSED)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
