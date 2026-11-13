"""One-shot retained registry/stage transition attempt custody (Core #238 3G44).

Unlike the immutable 3G42 observation guard, this internal guard accepts the
*expected stage-installed native identity* after a caller has marked exactly
one attempt. It never calls os.replace or returns success/durability authority.
The caller is responsible for all canonical, owner, namespace, postimage,
interrupt/recovery and durable commit gates while ordered locks remain held.
This module is NOT a production write API, a Notes feature or a replay token.
"""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_recovery_transition_registry_custody as native
from pds_core import _teacher_private_recovery_retained_stage_custody as stage
from pds_core import _teacher_private_retained_registry_guard as registry
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState


class _AttemptScopeRefused(Exception):
    """Sanitized transition refusal; do not disclose paths, IDs or bytes."""


def _terminal_permitted(
    attempted: bool, state: native.PrivateRegistryTransitionIdentityState
) -> bool:
    """A native identity transition is not a durable commit or safe retry."""
    prepared = native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
    installed = native.PrivateRegistryTransitionIdentityState.EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED
    return (state is installed) if attempted else (state is prepared)


@dataclass(slots=True, repr=False)
class _AttemptWindow:
    """Private held-scope state, not a public mutation permit.

    Marking an attempt does not execute any filesystem operation. Once marked,
    the window never yields an automatic-retry recommendation. A missing stage
    and new registry must agree with the *retained stage native ID*.
    """

    _checker: Callable[[], native.PrivateRegistryTransitionIdentityState]
    attempted: bool = field(default=False, init=False)
    _ended: bool = field(default=False, init=False)

    def __repr__(self) -> str:
        return "_AttemptWindow(native_handles_redacted=True)"

    def observe(self) -> native.PrivateRegistryTransitionIdentityState:
        if self._ended:
            raise _AttemptScopeRefused
        try:
            return self._checker()
        except (OSError, ValueError, TypeError, AttributeError, OverflowError):
            raise _AttemptScopeRefused from None

    def mark_attempt(self) -> None:
        if self._ended or self.attempted:
            raise _AttemptScopeRefused
        if (
            self.observe()
            is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _AttemptScopeRefused
        self.attempted = True

    def _finish(self) -> native.PrivateRegistryTransitionIdentityState:
        if self._ended:
            raise _AttemptScopeRefused
        # Check while native handles are still open. No result proves durability.
        try:
            return self.observe()
        finally:
            self._ended = True


def _linux_key(info: os.stat_result) -> native.NativeKey | None:
    if info.st_ino <= 0:
        return None
    try:
        return native._native_key(info.st_dev, info.st_ino.to_bytes(16, "big"))
    except (OverflowError, ValueError, AttributeError):
        return None


@contextmanager
def _held_linux_pair(
    private_root: Path,
    stage_name: str,
    owner: inspection.EffectiveOSOwner,
    before_size: int,
    after_size: int,
) -> Iterator[_AttemptWindow]:
    if (
        owner.kind != "posix_euid"
        or not owner.value.isdecimal()
        or not getattr(os, "O_NOFOLLOW", 0)
    ):
        raise _AttemptScopeRefused
    uid = int(owner.value)
    if uid <= 0 or getattr(os, "geteuid", lambda: -1)() != uid:
        raise _AttemptScopeRefused
    parent, failure = posix._open_verified_parent(private_root, uid)
    if failure is not None or parent is None:
        raise _AttemptScopeRefused
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
            raise _AttemptScopeRefused
        baseline = native._Identities(parent_key, old_key, staged_key)

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
            or native._transition_state(
                baseline,
                native._Entries(parent_key, old_key, staged_key, old_key, staged_key),
            )
            is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _AttemptScopeRefused

        def _entry(name: str) -> native.NativeKey | None:
            try:
                entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return None
            if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
                raise _AttemptScopeRefused
            return _linux_key(entry)

        def check() -> native.PrivateRegistryTransitionIdentityState:
            state = native.PrivateRegistryTransitionIdentityState
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
                result = native._transition_state(
                    baseline,
                    native._Entries(
                        parent_key,
                        _linux_key(os.fstat(old)),
                        _linux_key(os.fstat(staged)),
                        _entry("registry.json"),
                        _entry(stage_name),
                    ),
                )
                return result
            except _AttemptScopeRefused:
                return state.UNQUALIFIED_NAMESPACE_PRESERVE
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                return state.IO_ERROR

        if (
            check()
            is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _AttemptScopeRefused
        window = _AttemptWindow(check)
        try:
            yield window
        finally:
            # Closure remains held until a final in-scope identity inspection.
            terminal = window._finish()
            if not _terminal_permitted(window.attempted, terminal):
                raise _AttemptScopeRefused
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
) -> Iterator[_AttemptWindow]:
    if owner.kind != "windows_token_sid":
        raise _AttemptScopeRefused
    kernel = None
    handles: list[int] = []
    try:
        kernel, advapi = wincheck._bind_api()
        if (
            not wincreate._known_fixed_local_volume(kernel, private_root)
            or wincheck._native_windows_walk(private_root, owner)
            is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
        ):
            raise _AttemptScopeRefused
        for path in (
            private_root,
            private_root / "registry.json",
            private_root / stage_name,
        ):
            handle, _error = anchor._windows_open(kernel, path)
            if handle is None:
                raise _AttemptScopeRefused
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
            raise _AttemptScopeRefused
        parent_key = native._native_key(*parent_id)
        old_key = native._native_key(old_signature[0], old_signature[1])
        stage_key = native._native_key(staged_signature[0], staged_signature[1])
        if parent_key is None or old_key is None or stage_key is None:
            raise _AttemptScopeRefused
        baseline = native._Identities(parent_key, old_key, stage_key)

        def _entry(name: str) -> native.NativeKey | None:
            handle, error = anchor._windows_open(kernel, private_root / name)
            if handle is None:
                if error in (2, 3):
                    return None
                raise _AttemptScopeRefused
            try:
                signature = registry._windows_signature(kernel, handle)
                if (
                    signature is None
                    or wincheck._handle_dacl_state(kernel, advapi, handle, owner)
                    is not NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                ):
                    raise _AttemptScopeRefused
                return native._native_key(signature[0], signature[1])
            finally:
                kernel.CloseHandle(wintypes.HANDLE(handle))

        def check() -> native.PrivateRegistryTransitionIdentityState:
            state = native.PrivateRegistryTransitionIdentityState
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
                return native._transition_state(
                    baseline,
                    native._Entries(
                        parent_key,
                        native._native_key(old_signature[0], old_signature[1]),
                        native._native_key(staged_signature[0], staged_signature[1]),
                        _entry("registry.json"),
                        _entry(stage_name),
                    ),
                )
            except _AttemptScopeRefused:
                return state.UNQUALIFIED_NAMESPACE_PRESERVE
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                return state.IO_ERROR

        if (
            check()
            is not native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        ):
            raise _AttemptScopeRefused
        window = _AttemptWindow(check)
        try:
            yield window
        finally:
            # Closure remains held until a final in-scope identity inspection.
            terminal = window._finish()
            if not _terminal_permitted(window.attempted, terminal):
                raise _AttemptScopeRefused
    finally:
        if kernel is not None:
            for handle in reversed(handles):
                kernel.CloseHandle(wintypes.HANDLE(handle))


@contextmanager
def _held_one_shot_transition_pair(
    private_root: Path,
    tx: str,
    owner: inspection.EffectiveOSOwner,
    before_size: int,
    after_size: int,
) -> Iterator[_AttemptWindow]:
    if sys.platform not in {"win32", "linux"}:
        raise _AttemptScopeRefused
    if (
        type(before_size) is not int
        or type(after_size) is not int
        or not (0 < before_size <= metadata.MAX_REGISTRY_BYTES)
        or not (0 < after_size <= metadata.MAX_REGISTRY_BYTES)
    ):
        raise _AttemptScopeRefused
    name = stage._stage_name(tx)
    with (
        _held_linux_pair(private_root, name, owner, before_size, after_size)
        if sys.platform == "linux"
        else _held_windows_pair(private_root, name, owner, before_size, after_size)
    ) as window:
        yield window
