"""#238 Slice 3D1: non-mutating, fail-closed pending journal census."""

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
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pending_journal_review as census
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _synthetic(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    scan: census.PrivatePendingJournalState,
    *,
    second_owner: inspection.EffectiveOSOwner | None = None,
    refuse_lock: bool = False,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def locks(private: Path, workspace: Path) -> Iterator[None]:
        events.append("registry-lock")
        if refuse_lock:
            raise ordered.PrivateOrderedCoordinationError(
                ordered.PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE
            )
        events.append("workspace-lock")
        try:
            yield
        finally:
            events.append("workspace-unlock")
            events.append("registry-unlock")

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", locks)
    calls = 0

    def current_owner() -> inspection.EffectiveOSOwner:
        nonlocal calls
        calls += 1
        events.append("owner")
        if calls == 2 and second_owner is not None:
            return second_owner
        return _owner()

    def read_dir(
        directory: Path, owner: inspection.EffectiveOSOwner
    ) -> census.PrivatePendingJournalState:
        events.append("directory")
        assert directory.name == "transactions"
        assert owner == _owner()
        return scan

    monkeypatch.setattr(ordered, "_owner", current_owner)
    monkeypatch.setattr(census, "_scan_linux", read_dir)
    monkeypatch.setattr(census, "_scan_windows", read_dir)


def test_result_is_advisory_and_does_not_advertise_notes() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(census, "commit_private_binding")
    assert not hasattr(census, "admit_journal")
    assert not hasattr(census.PrivatePendingJournalReview, "authorized")
    assert not hasattr(census.PrivatePendingJournalReview, "write_handle")
    assert not hasattr(census.PrivatePendingJournalReview, "plan_token")


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            census.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
            "empty_review_required",
        ),
        (
            census.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED,
            "pending_review_required",
        ),
        (census.PrivatePendingJournalState.MISSING_DIRECTORY, "missing_directory"),
        (
            census.PrivatePendingJournalState.CHANGED_DURING_REVIEW,
            "changed_during_review",
        ),
    ],
)
def test_ordered_review_returns_only_sanitized_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: census.PrivatePendingJournalState,
    expected: str,
) -> None:
    events: list[str] = []
    _synthetic(monkeypatch, events, state)
    outcome = census.review_existing_private_pending_journals(tmp_path, tmp_path)
    assert outcome.state.value == expected
    assert events == [
        "registry-lock",
        "workspace-lock",
        "owner",
        "directory",
        "owner",
        "workspace-unlock",
        "registry-unlock",
    ]
    assert str(tmp_path) not in repr(outcome)
    assert _owner().value not in repr(outcome)
    assert list(tmp_path.iterdir()) == []


def test_owner_drift_refuses_and_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = (
        inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-22-33-44")
        if sys.platform == "win32"
        else inspection.EffectiveOSOwner("posix_euid", "2000")
    )
    trace: list[str] = []
    _synthetic(
        monkeypatch,
        trace,
        census.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
        second_owner=changed,
    )
    assert (
        census.review_existing_private_pending_journals(tmp_path, tmp_path).state
        is census.PrivatePendingJournalState.OWNER_CHANGED
    )
    assert trace[-2:] == ["workspace-unlock", "registry-unlock"]


def test_coordination_refusal_prevents_directory_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace: list[str] = []
    _synthetic(
        monkeypatch,
        trace,
        census.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
        refuse_lock=True,
    )
    assert (
        census.review_existing_private_pending_journals(tmp_path, tmp_path).state
        is census.PrivatePendingJournalState.COORDINATION_REFUSED
    )
    assert trace == ["registry-lock"]


def test_invalid_root_has_no_lock_or_owner_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace: list[str] = []
    _synthetic(
        monkeypatch, trace, census.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED
    )
    # Replace the validator to prove malformed inputs do not reach locks.
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: False)
    assert (
        census.review_existing_private_pending_journals(
            Path("relative"), tmp_path
        ).state
        is census.PrivatePendingJournalState.INVALID_REQUEST
    )
    assert trace == []


def test_windows_observer_empty_pending_and_reparse_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    directory = tmp_path / "transactions"
    directory.mkdir()
    monkeypatch.setattr(wincheck, "_bind_api", lambda: (object(), object()))
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        wincheck,
        "_native_windows_walk",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    assert (
        census._scan_windows(directory, who)
        is census.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED
    )
    (directory / "recovery.json").write_text("synthetic")
    assert (
        census._scan_windows(directory, who)
        is census.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED
    )
    (directory / "recovery.json").unlink()
    monkeypatch.setattr(
        wincheck,
        "_native_windows_walk",
        lambda *_: NativePrivatePreflightState.REFUSED_PATH,
    )
    assert (
        census._scan_windows(directory, who)
        is census.PrivatePendingJournalState.REFUSED_PROTECTION
    )


def test_windows_native_api_unavailable_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")

    def unavailable() -> tuple[object, object]:
        raise wincheck._NativeUnavailable

    monkeypatch.setattr(wincheck, "_bind_api", unavailable)
    assert (
        census._scan_windows(tmp_path, who)
        is census.PrivatePendingJournalState.UNSUPPORTED
    )


@pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only native directory review"
)
def test_linux_native_empty_pending_and_unsafe_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid_getter = getattr(os, "geteuid", None)
    if uid_getter is None or uid_getter() <= 0:
        pytest.skip("requires nonroot OS user")
    directory = (
        tmp_path / "paper-data-suite" / "private" / "notes" / "v1" / "transactions"
    )
    directory.mkdir(parents=True)
    for parent in [directory, *list(directory.parents)[:4]]:
        parent.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda fd: True)
    who = inspection.EffectiveOSOwner("posix_euid", str(uid_getter()))
    assert (
        census._scan_linux(directory, who)
        is census.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED
    )
    pending = directory / "synthetic-abandoned.json"
    pending.write_bytes(b"synthetic")
    assert (
        census._scan_linux(directory, who)
        is census.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED
    )
    pending.unlink()
    other = tmp_path / "destination"
    other.write_text("synthetic")
    pending.symlink_to(other)
    assert (
        census._scan_linux(directory, who)
        is census.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED
    )
    pending.unlink()
    directory.chmod(0o755)
    assert (
        census._scan_linux(directory, who)
        is census.PrivatePendingJournalState.REFUSED_PROTECTION
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only directory review")
def test_linux_missing_directory_is_not_equated_with_empty(tmp_path: Path) -> None:
    who = inspection.EffectiveOSOwner("posix_euid", "1000")
    assert census._scan_linux(tmp_path / "absent", who) in {
        census.PrivatePendingJournalState.MISSING_DIRECTORY,
        census.PrivatePendingJournalState.OWNER_CHANGED,
    }


def test_refuses_owner_kind_without_enumeration(tmp_path: Path) -> None:
    other = inspection.EffectiveOSOwner("posix_euid", "1000")
    assert (
        census._scan_windows(tmp_path, other)
        is census.PrivatePendingJournalState.OWNER_UNAVAILABLE
    )


def test_directory_metadata_comparison_is_not_only_path_spelling(
    tmp_path: Path,
) -> None:
    original = tmp_path.stat()
    assert census._same_directory(original, original)
    from os import stat_result

    altered = list(original)
    altered[1] = original.st_ino + 1
    assert not census._same_directory(original, stat_result(altered))
