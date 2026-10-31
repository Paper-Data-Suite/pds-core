"""Core #238 3F3: synthetic stage inventory under retained native guards."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (set(), inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED),
        (
            {"registry.json", ".registry.lock", "v1"},
            inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,
        ),
        (
            {f".{TX}.registry-stage"},
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED,
        ),
        (
            {f".{TX}.registry-stage", "registry.json"},
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED,
        ),
        (
            {".wrong.registry-stage"},
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
        (
            {".bad.registry-stage.backup"},
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
        (
            {".REGISTRY-STAGE"},
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
        (
            {f".{TX.upper()}.registry-stage"},
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
        (
            {".aaaaaaaa-aaaa-1aaa-aaaa-aaaaaaaaaaaa.registry-stage"},
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
        (
            {f".{TX}.registry-stage", f".{TX.upper()}.registry-stage"},
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
    ],
)
def test_stage_name_inventory_is_fail_closed(
    names: set[str], expected: inventory.PrivateRegistryStageInventoryState
) -> None:
    assert inventory._inventory_names(names) is expected


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    state: inventory.PrivateRegistryStageInventoryState = inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,
    guard_enter: retained.RetainedDescriptorGuardCode | None = None,
    guard_exit: retained.RetainedDescriptorGuardCode | None = None,
    owner_changed: bool = False,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def guard(_private: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        if guard_enter is not None:
            raise retained.RetainedDescriptorGuardError(guard_enter)
        try:
            yield
            if guard_exit is not None:
                raise retained.RetainedDescriptorGuardError(guard_exit)
        finally:
            events.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)
    calls = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal calls
        calls += 1
        events.append("owner")
        current = _owner()
        if owner_changed and calls == 2:
            return inspection.EffectiveOSOwner(current.kind, "different")
        return current

    def scan(
        _path: Path, _owner_arg: inspection.EffectiveOSOwner
    ) -> inventory.PrivateRegistryStageInventoryState:
        assert _owner_arg == _owner()
        events.append("scan")
        return state

    monkeypatch.setattr(ordered, "_owner", owner)
    monkeypatch.setattr(inventory, "_scan_linux", scan)
    monkeypatch.setattr(inventory, "_scan_windows", scan)


def _call(tmp_path: Path) -> inventory.PrivateRegistryStageInventoryReview:
    return inventory.review_private_registry_stages(
        tmp_path / "private", tmp_path / "workspace"
    )


@pytest.mark.parametrize("state", list(inventory.PrivateRegistryStageInventoryState))
def test_scan_state_never_promotes_write_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: inventory.PrivateRegistryStageInventoryState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, state=state)
    result = _call(tmp_path)
    assert result.state is state
    assert events == ["guard-enter", "owner", "scan", "owner", "guard-exit"]
    assert list(tmp_path.iterdir()) == []
    assert not hasattr(result, "write_handle")
    assert not hasattr(result, "stage_names")
    assert not hasattr(result, "commit_token")
    assert str(tmp_path) not in repr(result)
    assert TX not in repr(result)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
            inventory.PrivateRegistryStageInventoryState.OWNER_CHANGED,
        ),
        (
            retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE,
            inventory.PrivateRegistryStageInventoryState.OWNER_UNAVAILABLE,
        ),
        (
            retained.RetainedDescriptorGuardCode.UNSUPPORTED,
            inventory.PrivateRegistryStageInventoryState.UNSUPPORTED,
        ),
        (
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
            inventory.PrivateRegistryStageInventoryState.GUARD_REFUSED,
        ),
    ],
)
def test_guard_exit_refusal_overrides_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: retained.RetainedDescriptorGuardCode,
    expected: inventory.PrivateRegistryStageInventoryState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, guard_exit=code)
    assert _call(tmp_path).state is expected
    assert events == ["guard-enter", "owner", "scan", "owner", "guard-exit"]


def test_guard_entry_refuses_before_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        guard_enter=retained.RetainedDescriptorGuardCode.MISSING_DESCRIPTOR,
    )
    assert (
        _call(tmp_path).state
        is inventory.PrivateRegistryStageInventoryState.GUARD_REFUSED
    )
    assert events == ["guard-enter"]


def test_owner_drift_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, owner_changed=True)
    assert (
        _call(tmp_path).state
        is inventory.PrivateRegistryStageInventoryState.OWNER_CHANGED
    )
    assert events == ["guard-enter", "owner", "scan", "owner", "guard-exit"]


def test_invalid_root_refused_before_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: False)
    assert (
        _call(tmp_path).state
        is inventory.PrivateRegistryStageInventoryState.INVALID_REQUEST
    )
    assert events == []
    assert (
        inventory.review_private_registry_stages(cast(Path, "wrong"), tmp_path).state
        is inventory.PrivateRegistryStageInventoryState.INVALID_REQUEST
    )


def test_unsupported_platform_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        _call(tmp_path).state
        is inventory.PrivateRegistryStageInventoryState.UNSUPPORTED
    )
    assert events == []


def test_public_capability_boundary() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(inventory, "commit_private_binding")
    assert not hasattr(inventory, "remove_stale_stage")
    assert not hasattr(inventory, "admit_durable_transaction")
    assert not hasattr(inventory, "create_notes_record")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux directory-fd test")
@pytest.mark.parametrize(
    ("stage_name", "expected"),
    [
        (None, inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED),
        (
            f".{TX}.registry-stage",
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
        (
            ".bad.registry-stage",
            inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        ),
    ],
)
def test_linux_native_directory_fd_scan_refuses_unqualified_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage_name: str | None,
    expected: inventory.PrivateRegistryStageInventoryState,
) -> None:
    import os

    from pds_core import _teacher_private_posix_provision as posix

    if not getattr(os, "O_NOFOLLOW", 0):
        pytest.skip("No native no-follow support")
    root = tmp_path / "private"
    root.mkdir()
    if stage_name is not None:
        (root / stage_name).write_bytes(b"synthetic")
        (root / stage_name).chmod(0o644)  # Intentionally unqualified native stage.
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        posix,
        "_open_verified_parent",
        lambda path, uid: (
            os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)),
            None,
        ),
    )
    assert (
        inventory._scan_linux(root, inspection.EffectiveOSOwner("posix_euid", "1000"))
        is expected
    )
