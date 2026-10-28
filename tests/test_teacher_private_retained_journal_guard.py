"""#238 Slice 3D5: retained native journal directory handles, no write authority."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_journal_guard as guard
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import (
    NativePrivatePreflightState as State,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _setup(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    monkeypatch.setattr(
        lock_file, "_requested_root", lambda path, *_: path.is_absolute()
    )
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def coordination(_private: Path, _workspace: Path) -> Iterator[None]:
        events.append("locks-open")
        try:
            yield
        finally:
            events.append("locks-closed")

    @contextmanager
    def retained(directory: Path, owner: inspection.EffectiveOSOwner) -> Iterator[None]:
        assert directory.name == "transactions"
        assert owner == _owner()
        events.append("handle-open")
        try:
            yield
        finally:
            events.append("handle-closed")

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", coordination)
    monkeypatch.setattr(ordered, "_owner", _owner)
    monkeypatch.setattr(guard, "_held_linux", retained)
    monkeypatch.setattr(guard, "_held_windows", retained)


def test_continuous_scope_and_reverse_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    with guard._hold_existing_retained_journal_guard(
        tmp_path / "private", tmp_path / "work"
    ) as value:
        assert value is None
        events.append("in-scope")
    assert events == [
        "locks-open",
        "handle-open",
        "in-scope",
        "handle-closed",
        "locks-closed",
    ]


def test_original_body_exception_and_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    with pytest.raises(ZeroDivisionError):
        with guard._hold_existing_retained_journal_guard(
            tmp_path / "private", tmp_path / "work"
        ):
            raise ZeroDivisionError
    assert events[-2:] == ["handle-closed", "locks-closed"]


def test_owner_change_before_body_closes_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    owners = iter(
        (_owner(), inspection.EffectiveOSOwner(_owner().kind, "not-the-same"))
    )
    monkeypatch.setattr(ordered, "_owner", lambda: next(owners))
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._hold_existing_retained_journal_guard(tmp_path, tmp_path):
            pytest.fail("owner changed")
    assert exc.value.code is guard.RetainedJournalGuardCode.OWNER_CHANGED
    assert events == ["locks-open", "handle-open", "handle-closed", "locks-closed"]


def test_owner_change_after_body_closes_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    owners = iter(
        (_owner(), _owner(), inspection.EffectiveOSOwner(_owner().kind, "not-the-same"))
    )
    monkeypatch.setattr(ordered, "_owner", lambda: next(owners))
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._hold_existing_retained_journal_guard(tmp_path, tmp_path):
            events.append("body")
    assert exc.value.code is guard.RetainedJournalGuardCode.OWNER_CHANGED
    assert events[-2:] == ["handle-closed", "locks-closed"]


def test_invalid_request_is_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._hold_existing_retained_journal_guard(Path("relative"), tmp_path):
            pytest.fail("invalid")
    assert exc.value.code is guard.RetainedJournalGuardCode.INVALID_REQUEST
    assert not events


def test_lock_refusal_does_not_open_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)

    @contextmanager
    def fail(_private: Path, _workspace: Path) -> Iterator[None]:
        raise ordered.PrivateOrderedCoordinationError(
            ordered.PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE
        )
        yield

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", fail)
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._hold_existing_retained_journal_guard(tmp_path, tmp_path):
            pytest.fail("unreachable")
    assert exc.value.code is guard.RetainedJournalGuardCode.COORDINATION_REFUSED
    assert not events


def test_no_public_capability_or_write_helpers() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(guard, "commit_private_binding")
    assert not hasattr(guard, "create_private_transaction_intent_file")
    assert not hasattr(guard, "write_records")
    assert not hasattr(guard, "READY")


def test_guard_errors_sanitized(tmp_path: Path) -> None:
    error = guard.RetainedJournalGuardError(
        guard.RetainedJournalGuardCode.CHANGED_DURING_SCOPE
    )
    assert str(tmp_path) not in str(error)
    assert "owner" not in str(error)
    assert "changed_during_scope" in str(error)


def test_windows_handle_lifetime_synthetic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows native handle is retained until after body and final identity check."""
    who = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    events: list[str] = []

    class Kernel:
        def CloseHandle(self, h: object) -> int:
            events.append("close:" + str(getattr(h, "value", None)))
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
    counter = 0

    def open_dir(*_args: object) -> tuple[int, int]:
        nonlocal counter
        counter += 1
        events.append("open:" + str(counter))
        return counter, 0

    monkeypatch.setattr(anchor, "_windows_open", open_dir)
    monkeypatch.setattr(anchor, "_windows_id", lambda *_: (42, b"x" * 16))
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (0x10, SimpleNamespace(directory=True, delete_pending=False)),
    )
    with guard._held_windows(tmp_path / "transactions", who):
        events.append("body")
    assert events == [
        "open:1",
        "open:2",
        "close:2",
        "body",
        "open:3",
        "close:3",
        "close:1",
    ]


def test_windows_identity_drift_closes_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    closed: list[int | None] = []

    class Kernel:
        def CloseHandle(self, h: object) -> int:
            closed.append(getattr(h, "value", None))
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
    sequence = iter(((1, 0), (2, 0)))
    monkeypatch.setattr(anchor, "_windows_open", lambda *_: next(sequence))
    monkeypatch.setattr(
        anchor,
        "_windows_id",
        lambda _kernel, handle: (42, b"x" * 16 if handle == 1 else b"y" * 16),
    )
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (0x10, SimpleNamespace(directory=True, delete_pending=False)),
    )
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._held_windows(tmp_path, who):
            pytest.fail("must refuse before body")
    assert exc.value.code is guard.RetainedJournalGuardCode.CHANGED_DURING_SCOPE
    assert closed == [2, 1]


def test_windows_unsupported_native_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")

    def fail() -> tuple[object, object]:
        raise wincheck._NativeUnavailable

    monkeypatch.setattr(wincheck, "_bind_api", fail)
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._held_windows(tmp_path, who):
            pytest.fail("must refuse")
    assert exc.value.code is guard.RetainedJournalGuardCode.UNSUPPORTED


def test_windows_body_exception_still_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    closed: list[int | None] = []

    class Kernel:
        def CloseHandle(self, h: object) -> int:
            closed.append(getattr(h, "value", None))
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
    monkeypatch.setattr(anchor, "_windows_open", lambda *_: (1, 0))
    monkeypatch.setattr(anchor, "_windows_id", lambda *_: (1, b"x" * 16))
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (0x10, SimpleNamespace(directory=True, delete_pending=False)),
    )
    with pytest.raises(ZeroDivisionError):
        with guard._held_windows(tmp_path, who):
            raise ZeroDivisionError
    assert closed == [1, 1]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory fd only")
def test_real_linux_retention_and_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("ordinary non-root Linux user required")
    private = tmp_path / "private"
    directory = private / "transactions"
    directory.mkdir(parents=True, mode=0o700)
    private.chmod(0o700)
    directory.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    uid = getter()
    who = inspection.EffectiveOSOwner("posix_euid", str(uid))
    with guard._held_linux(directory, who):
        assert directory.is_dir()
    # The guard must detect replacement even while the original FD remains open.
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._held_linux(directory, who):
            directory.rename(private / "moved")
            directory.mkdir(mode=0o700)
    assert exc.value.code is guard.RetainedJournalGuardCode.CHANGED_DURING_SCOPE


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory fd only")
def test_real_linux_mode_drift_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("ordinary non-root Linux user required")
    directory = tmp_path / "private" / "transactions"
    directory.mkdir(parents=True, mode=0o700)
    directory.parent.chmod(0o700)
    directory.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    who = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._held_linux(directory, who):
            directory.chmod(0o750)
    assert exc.value.code is guard.RetainedJournalGuardCode.CHANGED_DURING_SCOPE


def test_windows_reparse_refused_and_handles_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    closed: list[int | None] = []

    class Kernel:
        def CloseHandle(self, h: object) -> int:
            closed.append(getattr(h, "value", None))
            return 1

    monkeypatch.setattr(wincheck, "_bind_api", lambda: (Kernel(), object()))
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        wincheck, "_native_windows_walk", lambda *_: State.RESTRICTIVE_UNQUALIFIED
    )
    monkeypatch.setattr(
        wincheck, "_handle_dacl_state", lambda *_: State.RESTRICTIVE_UNQUALIFIED
    )
    monkeypatch.setattr(anchor, "_windows_open", lambda *_: (10, 0))
    monkeypatch.setattr(anchor, "_windows_id", lambda *_: (42, b"x" * 16))
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (
            0x400 | 0x10,
            SimpleNamespace(directory=True, delete_pending=False),
        ),
    )
    with pytest.raises(guard.RetainedJournalGuardError) as exc:
        with guard._held_windows(tmp_path / "transactions", who):
            pytest.fail("reparse should refuse before the body")
    assert exc.value.code is guard.RetainedJournalGuardCode.REFUSED_PROTECTION
    assert closed == [10]
