"""#238 Slice 3C9 — deterministic lock ordering without write authorization."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as registry_provision
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _fixture_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".pds").mkdir()
    if sys.platform == "linux":
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        private = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    else:
        private = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
        monkeypatch.setattr(registry_provision, "_requested_root", lambda *_: True)
        monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    private.mkdir(parents=True)
    return private, workspace


def _fake_locks(monkeypatch: pytest.MonkeyPatch, traces: list[str]) -> None:
    @contextmanager
    def hold(file: Path) -> Iterator[None]:
        traces.append("acquire:" + file.name)
        try:
            yield
        finally:
            traces.append("release:" + file.name)

    monkeypatch.setattr(locking, "hold_existing_private_lock", hold)


def test_private_lock_names_and_no_capability_activation() -> None:
    assert ordered._REGISTRY_LOCK == ".registry.lock"
    assert ordered._WORKSPACE_METADATA == ".pds"
    assert ordered._WORKSPACE_LOCK == ".teacher-private-association.lock"
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(ordered, "commit_private_binding")
    assert not hasattr(ordered, "write_private_registry")


def test_invalid_input_prevents_owner_query_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_owner(platform: str) -> inspection.EffectiveOSOwner:
        raise AssertionError("must not sample owner for malformed request")

    monkeypatch.setattr(inspection, "_effective_owner", fail_owner)
    with pytest.raises(ordered.PrivateOrderedCoordinationError) as exc:
        with ordered._hold_existing_ordered_coordination(Path("relative"), tmp_path):
            pytest.fail("unexpected acquisition")
    assert exc.value.code is ordered.PrivateOrderedCoordinationCode.INVALID_REQUEST
    assert str(tmp_path) not in str(exc.value)


def test_ordered_acquire_reverse_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _fixture_paths(tmp_path, monkeypatch)
    traces: list[str] = []
    _fake_locks(monkeypatch, traces)
    owner = (
        inspection.EffectiveOSOwner("posix_euid", "1100")
        if sys.platform == "linux"
        else inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    )
    monkeypatch.setattr(inspection, "_effective_owner", lambda _: owner)
    with ordered._hold_existing_ordered_coordination(private, workspace) as result:
        assert result is None
        traces.append("within")
    assert traces == [
        "acquire:.registry.lock",
        "acquire:.teacher-private-association.lock",
        "within",
        "release:.teacher-private-association.lock",
        "release:.registry.lock",
    ]


def test_second_busy_releases_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _fixture_paths(tmp_path, monkeypatch)
    owner = (
        inspection.EffectiveOSOwner("posix_euid", "1100")
        if sys.platform == "linux"
        else inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    )
    monkeypatch.setattr(inspection, "_effective_owner", lambda _: owner)
    events: list[str] = []

    @contextmanager
    def fake_lock(file: Path) -> Iterator[None]:
        events.append("open:" + file.name)
        if file.name == ordered._WORKSPACE_LOCK:
            raise locking.PrivateExistingFileLockError(
                locking.PrivateExistingFileLockCode.BUSY
            )
        try:
            yield
        finally:
            events.append("close:" + file.name)

    monkeypatch.setattr(locking, "hold_existing_private_lock", fake_lock)
    with pytest.raises(ordered.PrivateOrderedCoordinationError) as exc:
        with ordered._hold_existing_ordered_coordination(private, workspace):
            pytest.fail("both locks never acquired")
    assert (
        exc.value.code
        is ordered.PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE
    )
    assert events == [
        "open:.registry.lock",
        "open:.teacher-private-association.lock",
        "close:.registry.lock",
    ]


def test_owner_drift_refuses_and_unlocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _fixture_paths(tmp_path, monkeypatch)
    calls = (
        iter(
            [
                inspection.EffectiveOSOwner("posix_euid", "1100"),
                inspection.EffectiveOSOwner("posix_euid", "2200"),
            ]
        )
        if sys.platform == "linux"
        else iter(
            [
                inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11"),
                inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-22"),
            ]
        )
    )
    monkeypatch.setattr(inspection, "_effective_owner", lambda _: next(calls))
    events: list[str] = []
    _fake_locks(monkeypatch, events)
    with pytest.raises(ordered.PrivateOrderedCoordinationError) as exc:
        with ordered._hold_existing_ordered_coordination(private, workspace):
            pytest.fail("owner drift must refuse")
    assert exc.value.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED
    assert events[-2:] == [
        "release:.teacher-private-association.lock",
        "release:.registry.lock",
    ]


def test_owner_unavailable_refuses_before_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _fixture_paths(tmp_path, monkeypatch)

    def unavailable(platform: str) -> inspection.EffectiveOSOwner:
        raise inspection._OwnerUnverifiable

    monkeypatch.setattr(inspection, "_effective_owner", unavailable)
    events: list[str] = []
    _fake_locks(monkeypatch, events)
    with pytest.raises(ordered.PrivateOrderedCoordinationError) as exc:
        with ordered._hold_existing_ordered_coordination(private, workspace):
            pytest.fail("no owner")
    assert exc.value.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE
    assert events == []


def test_owner_kind_mismatch_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _fixture_paths(tmp_path, monkeypatch)
    bad = (
        inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
        if sys.platform == "linux"
        else inspection.EffectiveOSOwner("posix_euid", "1100")
    )
    monkeypatch.setattr(inspection, "_effective_owner", lambda _: bad)
    with pytest.raises(ordered.PrivateOrderedCoordinationError) as exc:
        with ordered._hold_existing_ordered_coordination(private, workspace):
            pytest.fail("bad owner kind")
    assert exc.value.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE


def test_callback_exception_keeps_original_exception_and_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _fixture_paths(tmp_path, monkeypatch)
    owner = (
        inspection.EffectiveOSOwner("posix_euid", "1100")
        if sys.platform == "linux"
        else inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11")
    )
    monkeypatch.setattr(inspection, "_effective_owner", lambda _: owner)
    events: list[str] = []
    _fake_locks(monkeypatch, events)
    with pytest.raises(ZeroDivisionError):
        with ordered._hold_existing_ordered_coordination(private, workspace):
            raise ZeroDivisionError
    assert events[-2:] == [
        "release:.teacher-private-association.lock",
        "release:.registry.lock",
    ]


def test_unsupported_platform_is_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    with pytest.raises(ordered.PrivateOrderedCoordinationError) as exc:
        with ordered._hold_existing_ordered_coordination(tmp_path, tmp_path):
            pytest.fail("unsupported")
    assert exc.value.code is ordered.PrivateOrderedCoordinationCode.UNSUPPORTED


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX native coordination only")
def test_nonroot_linux_real_locks_hold_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid_getter = getattr(os, "geteuid", None)
    if uid_getter is None or uid_getter() <= 0:
        pytest.skip("requires a non-root effective UID")
    private, workspace = _fixture_paths(tmp_path, monkeypatch)
    for file in (
        private / ".registry.lock",
        workspace / ".pds" / ".teacher-private-association.lock",
    ):
        file.write_bytes(b"\x00")
        file.chmod(0o600)
    before = [
        (p.read_bytes(), p.stat().st_size)
        for p in (
            private / ".registry.lock",
            workspace / ".pds" / ".teacher-private-association.lock",
        )
    ]
    with ordered._hold_existing_ordered_coordination(private, workspace):
        pass
    after = [
        (p.read_bytes(), p.stat().st_size)
        for p in (
            private / ".registry.lock",
            workspace / ".pds" / ".teacher-private-association.lock",
        )
    ]
    assert after == before
    assert not (workspace / ".pds" / "teacher-private-association.json").exists()
