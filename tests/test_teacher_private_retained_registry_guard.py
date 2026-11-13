"""Core #238 3D7: retained registry-file identity; no authorizing outputs."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_journal_guard as journal
from pds_core import _teacher_private_retained_registry_guard as guard
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import (
    NativePrivatePreflightState as State,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _fake_guard(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    exit_failure: bool = False,
    owner_drift: bool = False,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def held_journal(_private: Path, _workspace: Path) -> Iterator[None]:
        events.append("locks+journal-open")
        try:
            yield
        finally:
            events.append("journal+locks-closed")
            if exit_failure:
                raise journal.RetainedJournalGuardError(
                    journal.RetainedJournalGuardCode.CHANGED_DURING_SCOPE
                )

    @contextmanager
    def held_registry(
        _root: Path, _principal: inspection.EffectiveOSOwner
    ) -> Iterator[None]:
        events.append("registry-open")
        try:
            yield
        finally:
            events.append("registry-close")

    counts = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal counts
        counts += 1
        events.append("owner")
        who = _owner()
        if owner_drift and counts == 3:
            return inspection.EffectiveOSOwner(
                who.kind, "9999" if who.kind == "posix_euid" else "S-1-5-21-99-88"
            )
        return who

    monkeypatch.setattr(journal, "_hold_existing_retained_journal_guard", held_journal)
    monkeypatch.setattr(ordered, "_owner", owner)
    monkeypatch.setattr(guard, "_held_linux_registry", held_registry)
    monkeypatch.setattr(guard, "_held_windows_registry", held_registry)


def test_registry_and_journal_lifetimes_are_nested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake_guard(monkeypatch, events)
    with guard._hold_existing_retained_registry_guard(
        tmp_path / "private", tmp_path / "workspace"
    ) as capability:
        assert capability is None
        events.append("body")
    assert events == [
        "locks+journal-open",
        "owner",
        "registry-open",
        "owner",
        "body",
        "owner",
        "registry-close",
        "journal+locks-closed",
    ]
    assert not list(tmp_path.iterdir())


def test_journal_exit_failure_never_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake_guard(monkeypatch, events, exit_failure=True)
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._hold_existing_retained_registry_guard(
            tmp_path / "private", tmp_path / "workspace"
        ):
            events.append("body")
    assert exc.value.code is guard.RetainedRegistryGuardCode.JOURNAL_GUARD_REFUSED
    assert events[-2:] == ["registry-close", "journal+locks-closed"]


def test_owner_drift_refused_after_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake_guard(monkeypatch, events, owner_drift=True)
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._hold_existing_retained_registry_guard(
            tmp_path / "private", tmp_path / "workspace"
        ):
            events.append("body")
    assert exc.value.code is guard.RetainedRegistryGuardCode.OWNER_CHANGED
    assert events[-2:] == ["registry-close", "journal+locks-closed"]


def test_invalid_request_and_unsupported_never_enter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake_guard(monkeypatch, events)
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._hold_existing_retained_registry_guard("bad", tmp_path):  # type: ignore[arg-type]
            pytest.fail("invalid root must refuse")
    assert exc.value.code is guard.RetainedRegistryGuardCode.INVALID_REQUEST
    monkeypatch.setattr(sys, "platform", "freebsd")
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._hold_existing_retained_registry_guard(tmp_path, tmp_path):
            pytest.fail("unsupported platform must refuse")
    assert exc.value.code is guard.RetainedRegistryGuardCode.UNSUPPORTED
    assert events == []


def test_no_notes_or_authority() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(guard, "commit_private_binding")
    assert not hasattr(guard, "admit_journal")
    assert not hasattr(guard, "write_handle")
    assert not hasattr(guard, "commit_token")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux directory FD only")
def test_linux_native_registry_continuity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("non-root user required")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    file = private / "registry.json"
    file.write_bytes(b"synthetic example, not actual private metadata")
    file.chmod(0o600)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    principal = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    with guard._held_linux_registry(private, principal) as capability:
        assert capability is None
    assert file.exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux directory FD only")
def test_linux_native_replacement_and_mode_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("non-root user required")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    file = private / "registry.json"
    file.write_bytes(b"private example")
    file.chmod(0o600)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    principal = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_linux_registry(private, principal):
            file.rename(private / "old.json")
            file.write_bytes(b"replacement")
            file.chmod(0o600)
    assert exc.value.code is guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_linux_registry(private, principal):
            file.chmod(0o640)
    assert exc.value.code is guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE


@pytest.mark.skipif(sys.platform != "linux", reason="Linux directory FD only")
def test_linux_private_root_swap_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("non-root user required")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    file = private / "registry.json"
    file.write_bytes(b"example")
    file.chmod(0o600)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    principal = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_linux_registry(private, principal):
            private.rename(tmp_path / "moved")
            private.mkdir(mode=0o700)
    assert exc.value.code is guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE


def _fake_win(
    monkeypatch: pytest.MonkeyPatch,
    *,
    second_id_drift: bool = False,
    exit_id_drift: bool = False,
    reparse: bool = False,
) -> list[int | None]:
    closed: list[int | None] = []

    class Kernel:
        def CloseHandle(self, handle: object) -> int:
            closed.append(getattr(handle, "value", None))
            return 1

    kernel = Kernel()
    monkeypatch.setattr(wincheck, "_bind_api", lambda: (kernel, object()))
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        wincheck, "_native_windows_walk", lambda *_: State.RESTRICTIVE_UNQUALIFIED
    )
    monkeypatch.setattr(
        wincheck, "_handle_dacl_state", lambda *_: State.RESTRICTIVE_UNQUALIFIED
    )
    opened_count = 0

    def open_file(*_args: object) -> tuple[int, int]:
        nonlocal opened_count
        opened_count += 1
        return (11 if opened_count == 1 else 12), 0

    monkeypatch.setattr(anchor, "_windows_open", open_file)
    counts = 0

    def signature(
        _kernel: object, handle: int
    ) -> tuple[int, bytes, int, int, int] | None:
        nonlocal counts
        counts += 1
        if reparse:
            return None
        if (second_id_drift and counts >= 3) or (exit_id_drift and counts >= 4):
            return (10, b"y" * 16, 44, 20, 30)
        return (10, b"x" * 16, 44, 20, 30)

    monkeypatch.setattr(guard, "_windows_signature", signature)
    return closed


def test_windows_synthetic_handle_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _fake_win(monkeypatch)
    owner = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22")
    with guard._held_windows_registry(tmp_path, owner):
        assert 11 not in closed
    assert closed == [12, 12, 11]


def test_windows_synthetic_replacement_closes_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _fake_win(monkeypatch, second_id_drift=True)
    owner = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22")
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_windows_registry(tmp_path, owner):
            pytest.fail("replacement must refuse on entry")
    assert exc.value.code is guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE
    assert closed == [12, 11]


def test_windows_synthetic_reparse_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _fake_win(monkeypatch, reparse=True)
    owner = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22")
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_windows_registry(tmp_path, owner):
            pytest.fail("reparse must refuse")
    assert exc.value.code is guard.RetainedRegistryGuardCode.REFUSED_PROTECTION
    assert closed == [11]


def test_windows_synthetic_exit_drift_closes_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _fake_win(monkeypatch, exit_id_drift=True)
    owner = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22")
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_windows_registry(tmp_path, owner):
            assert closed == [12]
    assert exc.value.code is guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE
    assert closed == [12, 11]


def test_windows_native_backing_refused_without_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _fake_win(monkeypatch)
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: False)
    owner = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22")
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_windows_registry(tmp_path, owner):
            pytest.fail("unsupported backing must refuse")
    assert exc.value.code is guard.RetainedRegistryGuardCode.REFUSED_BACKING
    assert closed == []


def test_windows_body_exception_preserved_and_handle_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = _fake_win(monkeypatch)
    owner = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22")
    with pytest.raises(ZeroDivisionError):
        with guard._held_windows_registry(tmp_path, owner):
            raise ZeroDivisionError
    assert closed == [12, 11]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux directory FD only")
def test_linux_missing_registry_and_content_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("non-root user required")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    principal = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_linux_registry(private, principal):
            pytest.fail("missing registry must refuse")
    assert exc.value.code is guard.RetainedRegistryGuardCode.MISSING_REGISTRY
    file = private / "registry.json"
    file.write_bytes(b"first")
    file.chmod(0o600)
    with pytest.raises(guard.RetainedRegistryGuardError) as exc:
        with guard._held_linux_registry(private, principal):
            file.write_bytes(b"different content")
    assert exc.value.code is guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE


@pytest.mark.skipif(sys.platform != "linux", reason="Linux directory FD only")
def test_linux_native_body_exception_does_not_discard_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("non-root user required")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    file = private / "registry.json"
    file.write_bytes(b"example")
    file.chmod(0o600)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    principal = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    with pytest.raises(ZeroDivisionError):
        with guard._held_linux_registry(private, principal):
            raise ZeroDivisionError
