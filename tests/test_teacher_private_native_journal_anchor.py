"""Core #238 Slice 3D3: no-write native transaction-directory anchor review."""

from __future__ import annotations

import ctypes
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import (
    NativePrivatePreflightState as NativeState,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _mock_scope(monkeypatch: pytest.MonkeyPatch, trace: list[str]) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def hold(_private: Path, _workspace: Path) -> Iterator[None]:
        trace.append("lock")
        try:
            yield
        finally:
            trace.append("unlock")

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", hold)
    monkeypatch.setattr(ordered, "_owner", _owner)


def test_states_are_advisory_and_notes_remain_disabled() -> None:
    assert (
        anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED.value.endswith(
            "unqualified"
        )
    )
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(anchor, "commit_private_binding")
    assert not hasattr(anchor.PrivateJournalAnchorReview, "handle")
    assert not hasattr(anchor.PrivateJournalAnchorReview, "admission_token")
    assert ctypes.sizeof(anchor._FileIdInfo) == 24


def test_invalid_request_causes_no_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ordered, "_owner", lambda: pytest.fail("owner queried"))
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: False)
    result = anchor.review_existing_native_journal_anchor(Path("relative"), tmp_path)
    assert result.state is anchor.PrivateJournalAnchorState.INVALID_REQUEST


def test_unsupported_platform_no_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        anchor.review_existing_native_journal_anchor(tmp_path, tmp_path).state
        is anchor.PrivateJournalAnchorState.UNSUPPORTED
    )


def test_review_holds_both_locks_and_never_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _mock_scope(monkeypatch, events)

    def probe(
        _path: Path, _owner: inspection.EffectiveOSOwner
    ) -> anchor.PrivateJournalAnchorState:
        events.append("probe")
        return anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED

    monkeypatch.setattr(
        anchor, "_windows_anchor" if sys.platform == "win32" else "_linux_anchor", probe
    )
    result = anchor.review_existing_native_journal_anchor(tmp_path, tmp_path)
    assert (
        result.state is anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED
    )
    assert events == ["lock", "probe", "unlock"]
    assert list(tmp_path.iterdir()) == []
    assert str(tmp_path) not in repr(result)


def test_owner_change_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _mock_scope(monkeypatch, events)
    other = inspection.EffectiveOSOwner(
        "windows_token_sid" if sys.platform == "win32" else "posix_euid", "2000"
    )
    owners = iter([_owner(), other])
    monkeypatch.setattr(ordered, "_owner", lambda: next(owners))
    monkeypatch.setattr(
        anchor,
        "_windows_anchor" if sys.platform == "win32" else "_linux_anchor",
        lambda *_: anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED,
    )
    assert (
        anchor.review_existing_native_journal_anchor(tmp_path, tmp_path).state
        is anchor.PrivateJournalAnchorState.OWNER_CHANGED
    )
    assert events == ["lock", "unlock"]


def test_lock_failure_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_scope(monkeypatch, [])

    @contextmanager
    def fail(_a: Path, _b: Path) -> Iterator[None]:
        raise ordered.PrivateOrderedCoordinationError(
            ordered.PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE
        )
        yield

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", fail)
    assert (
        anchor.review_existing_native_journal_anchor(tmp_path, tmp_path).state
        is anchor.PrivateJournalAnchorState.COORDINATION_REFUSED
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only owner evidence")
def test_linux_root_or_wrong_owner_refused() -> None:
    principal = inspection.EffectiveOSOwner("posix_euid", "0")
    assert (
        anchor._linux_anchor(Path("/nonexistent"), principal)
        is anchor.PrivateJournalAnchorState.OWNER_UNAVAILABLE
    )
    other = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    assert (
        anchor._linux_anchor(Path("/nonexistent"), other)
        is anchor.PrivateJournalAnchorState.UNSUPPORTED
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native fd-only test")
def test_linux_real_directory_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("ordinary non-root UID required")
    folder = tmp_path / "transactions"
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _: True)
    monkeypatch.setattr(posix, "_acl_absent", lambda _: None)
    who = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    assert (
        anchor._linux_anchor(folder, who)
        is anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED
    )
    assert list(folder.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native fd-only test")
def test_linux_replaced_path_is_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() <= 0:
        pytest.skip("ordinary non-root UID required")
    folder = tmp_path / "transactions"
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _: True)
    monkeypatch.setattr(posix, "_acl_absent", lambda _: None)
    actual = os.lstat
    calls = 0

    def drift(path: Path) -> os.stat_result:
        nonlocal calls
        result = actual(path)
        if path == folder:
            calls += 1
            if calls > 1:
                return replace_stat(result)
        return result

    def replace_stat(info: os.stat_result) -> os.stat_result:
        # st_ino sits at index 1 in the POSIX stat tuple.
        values = list(info)
        values[1] = info.st_ino + 1
        return os.stat_result(values)

    monkeypatch.setattr(os, "lstat", drift)
    who = inspection.EffectiveOSOwner("posix_euid", str(getter()))
    assert (
        anchor._linux_anchor(folder, who)
        is anchor.PrivateJournalAnchorState.CHANGED_DURING_REVIEW
    )


def test_windows_file_id_record_is_24_bytes_and_checked() -> None:
    class FakeKernel:
        def GetFileInformationByHandleEx(
            self, _handle: object, information_class: int, out: object, length: int
        ) -> int:
            assert information_class == 18
            assert length == 24
            payload = anchor._FileIdInfo()
            payload.volume_serial = 123456
            payload.file_id[0] = 42
            ctypes.memmove(
                cast(ctypes.c_void_p, out),
                ctypes.byref(payload),
                ctypes.sizeof(payload),
            )
            return 1

    assert anchor._windows_id(FakeKernel(), 123) == (123456, bytes([42] + [0] * 15))


def _fake_windows(monkeypatch: pytest.MonkeyPatch, distinct: bool) -> list[int]:
    closed: list[int] = []
    native = NativeState.RESTRICTIVE_UNQUALIFIED

    class Kernel:
        def CloseHandle(self, h: object) -> int:
            if not isinstance(h, ctypes.c_void_p) or h.value is None:
                raise AssertionError("Unexpected synthetic handle")
            closed.append(h.value)
            return 1

    kernel = Kernel()
    monkeypatch.setattr(wincheck, "_bind_api", lambda: (kernel, object()))
    monkeypatch.setattr(wincheck, "_native_windows_walk", lambda *_: native)
    monkeypatch.setattr(wincheck, "_handle_dacl_state", lambda *_: native)
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (0x10, SimpleNamespace(directory=True, delete_pending=False)),
    )
    handles = iter([(11, 0), (12, 0)])
    monkeypatch.setattr(anchor, "_windows_open", lambda *_: next(handles))
    monkeypatch.setattr(
        anchor,
        "_windows_id",
        lambda _, handle: (
            99,
            b"\x11" * 16 if handle == 11 or not distinct else b"\x22" * 16,
        ),
    )
    return closed


def test_windows_same_fileid_observed_and_handles_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed = _fake_windows(monkeypatch, False)
    principal = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    assert (
        anchor._windows_anchor(tmp_path, principal)
        is anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED
    )
    assert closed == [12, 11]


def test_windows_different_fileid_refused_and_handles_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed = _fake_windows(monkeypatch, True)
    principal = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    assert (
        anchor._windows_anchor(tmp_path, principal)
        is anchor.PrivateJournalAnchorState.CHANGED_DURING_REVIEW
    )
    assert closed == [12, 11]


def test_windows_unavailable_native_api_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unavailable() -> tuple[object, object]:
        raise wincheck._NativeUnavailable

    monkeypatch.setattr(wincheck, "_bind_api", unavailable)
    principal = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    assert (
        anchor._windows_anchor(tmp_path, principal)
        is anchor.PrivateJournalAnchorState.UNSUPPORTED
    )


def test_windows_second_open_missing_preserves_first_handle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed = _fake_windows(monkeypatch, False)
    handles = iter([(11, 0), (None, 2)])
    monkeypatch.setattr(anchor, "_windows_open", lambda *_: next(handles))
    principal = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    assert (
        anchor._windows_anchor(tmp_path, principal)
        is anchor.PrivateJournalAnchorState.CHANGED_DURING_REVIEW
    )
    assert closed == [11]


def test_windows_dacl_refusal_closes_first_handle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed = _fake_windows(monkeypatch, False)
    monkeypatch.setattr(
        wincheck, "_handle_dacl_state", lambda *_: NativeState.ACCESS_DENIED
    )
    principal = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    assert (
        anchor._windows_anchor(tmp_path, principal)
        is anchor.PrivateJournalAnchorState.REFUSED_PROTECTION
    )
    assert closed == [11]


def test_windows_unknown_backing_refused_without_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed = _fake_windows(monkeypatch, False)
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: False)
    principal = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    assert (
        anchor._windows_anchor(tmp_path, principal)
        is anchor.PrivateJournalAnchorState.REFUSED_BACKING
    )
    assert closed == []
