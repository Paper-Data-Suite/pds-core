"""Adversarial directory flush contract tests for Core #238 Slice 3G49."""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from pds_core import (
    _teacher_private_recovery_windows_directory_durability_probe as probe,
)

State = probe.PrivateDirectoryFlushState
Kind = probe.PrivateDirectoryFlushObservation


def test_unsupported_platform_does_not_construct_native_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(probe, "_kernel", lambda: pytest.fail("must not use WinAPI"))
    result = probe.probe_private_windows_directory_flush_contract()
    assert result.state is State.UNSUPPORTED_PLATFORM
    assert result.production_writes_blocked and result.journal_retirement_forbidden


def test_native_api_unavailable_refuses_without_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "_kernel", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(
        tempfile, "TemporaryDirectory", lambda **_: pytest.fail("no scratch")
    )
    assert (
        probe.probe_private_windows_directory_flush_contract().state
        is State.NATIVE_UNAVAILABLE
    )


@pytest.mark.parametrize(
    ("value", "opening", "expected"),
    [
        (5, True, Kind.OPEN_ACCESS_DENIED),
        (32, True, Kind.OPEN_ACCESS_DENIED),
        (33, True, Kind.OPEN_ACCESS_DENIED),
        (6, True, Kind.OPEN_UNSUPPORTED),
        (5, False, Kind.FLUSH_ACCESS_DENIED),
        (32, False, Kind.FLUSH_ACCESS_DENIED),
        (1, False, Kind.FLUSH_UNSUPPORTED),
        (6, False, Kind.FLUSH_UNSUPPORTED),
        (50, False, Kind.FLUSH_UNSUPPORTED),
        (87, False, Kind.FLUSH_UNSUPPORTED),
        (12345, False, Kind.FLUSH_OTHER_REFUSAL),
    ],
)
def test_native_error_vocab(value: int, opening: bool, expected: Kind) -> None:
    assert probe._classified(value, opening=opening) is expected


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ((Kind.RETURNED_UNQUALIFIED,) * 3, State.REQUESTS_RETURNED_UNQUALIFIED),
        ((Kind.FLUSH_UNSUPPORTED,) * 3, State.FLUSH_REFUSED),
        (
            (
                Kind.RETURNED_UNQUALIFIED,
                Kind.FLUSH_ACCESS_DENIED,
                Kind.RETURNED_UNQUALIFIED,
            ),
            State.FLUSH_REFUSED,
        ),
        (
            (
                Kind.RETURNED_UNQUALIFIED,
                Kind.OPEN_ACCESS_DENIED,
                Kind.RETURNED_UNQUALIFIED,
            ),
            State.OPEN_REFUSED,
        ),
        (
            (
                Kind.HANDLE_UNQUALIFIED,
                Kind.RETURNED_UNQUALIFIED,
                Kind.RETURNED_UNQUALIFIED,
            ),
            State.IDENTITY_CHANGED,
        ),
    ],
)
def test_three_independent_parent_observations(
    monkeypatch: pytest.MonkeyPatch, sequence: tuple[Kind, Kind, Kind], expected: State
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "_kernel", lambda: object())
    checked: list[str] = []

    def native(_kernel: object, directory: Path) -> Kind:
        checked.append(directory.name)
        return sequence[len(checked) - 1]

    monkeypatch.setattr(probe, "_probe_one", native)
    monkeypatch.setattr(
        os, "replace", lambda *_: pytest.fail("no scratch replacement allowed")
    )
    answer = probe.probe_private_windows_directory_flush_contract()
    assert answer.state is expected
    assert len(checked) == 3
    assert tuple(label for label, _ in answer.observations) == (
        "journal",
        "registry",
        "descriptor",
    )
    assert tuple(result for _, result in answer.observations) == sequence
    assert answer.directory_durability_unqualified
    assert answer.pending_evidence_must_remain
    assert answer.production_writes_blocked
    assert answer.journal_retirement_forbidden


def test_file_flush_fails_closed_before_directory_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "_kernel", lambda: object())
    monkeypatch.setattr(probe, "_prepare", lambda *_: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(
        probe, "_probe_one", lambda *_: pytest.fail("no directory probe")
    )
    assert (
        probe.probe_private_windows_directory_flush_contract().state
        is State.FILE_FLUSH_REFUSED
    )


def test_file_image_drift_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "_kernel", lambda: object())
    monkeypatch.setattr(probe, "_same", lambda *_: False)
    monkeypatch.setattr(probe, "_probe_one", lambda *_: pytest.fail("no native probe"))
    assert (
        probe.probe_private_windows_directory_flush_contract().state
        is State.IDENTITY_CHANGED
    )


def test_probe_parent_closed_handles_on_native_flush_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed: list[int] = []
    handles = iter((101, 102))
    monkeypatch.setattr(probe, "_open", lambda *_: (next(handles), 0))
    monkeypatch.setattr(probe, "_identity", lambda *_: (12, 20, 30))
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 6, raising=False)

    class Kernel:
        def FlushFileBuffers(self, _handle: Any) -> bool:
            return False

        def CloseHandle(self, handle: Any) -> bool:
            closed.append(int(handle.value))
            return True

    assert probe._probe_one(Kernel(), tmp_path) is Kind.FLUSH_UNSUPPORTED
    assert closed == [102, 101]


def test_probe_parent_refuses_identity_drift_and_closes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed: list[int] = []
    calls = iter((101, 102))
    monkeypatch.setattr(probe, "_open", lambda *_: (next(calls), 0))
    monkeypatch.setattr(probe, "_identity", lambda _k, handle: (2, 3, handle))

    class Kernel:
        def FlushFileBuffers(self, _handle: Any) -> bool:
            return True

        def CloseHandle(self, handle: Any) -> bool:
            closed.append(int(handle.value))
            return True

    assert probe._probe_one(Kernel(), tmp_path) is Kind.HANDLE_UNQUALIFIED
    assert closed == [102, 101]


def test_probe_parent_open_refusal_never_flushes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(probe, "_open", lambda *_: (None, 5))

    class Kernel:
        def FlushFileBuffers(self, _handle: Any) -> bool:
            pytest.fail("must not flush an unopened directory")

    assert probe._probe_one(Kernel(), tmp_path) is Kind.OPEN_ACCESS_DENIED


def test_interrupt_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "_kernel", lambda: object())
    monkeypatch.setattr(
        probe, "_probe_one", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    assert (
        probe.probe_private_windows_directory_flush_contract().state
        is State.INTERRUPTED_PRESERVE
    )


def test_no_sensitive_output_or_authorizing_field() -> None:
    value = probe._result(State.FLUSH_REFUSED)
    assert "non_authorizing" in repr(value)
    assert "\\" not in repr(value)
    assert {part.name for part in fields(value)} == {
        "state",
        "message",
        "observations",
        "production_writes_blocked",
        "journal_retirement_forbidden",
        "pending_evidence_must_remain",
        "directory_durability_unqualified",
    }


def test_native_windows_scratch_directory_census() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-native directory handle probe")
    result = probe.probe_private_windows_directory_flush_contract()
    assert result.state in {
        State.REQUESTS_RETURNED_UNQUALIFIED,
        State.OPEN_REFUSED,
        State.FLUSH_REFUSED,
        State.IDENTITY_CHANGED,
        State.FILE_FLUSH_REFUSED,
        State.NATIVE_UNAVAILABLE,
        State.IO_ERROR_PRESERVE,
    }
    assert result.directory_durability_unqualified
    assert result.production_writes_blocked
    assert result.pending_evidence_must_remain
    assert result.journal_retirement_forbidden
