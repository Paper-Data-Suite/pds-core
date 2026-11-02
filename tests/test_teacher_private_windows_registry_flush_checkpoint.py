"""Core #238 3G7: protected Windows registry-file flush remains non-authorizing."""

from __future__ import annotations

import ctypes
import sys
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as reader
from pds_core import _teacher_private_stage_absence_checkpoint as absence
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_registry_flush_checkpoint as flush
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = flush.PrivateWindowsRegistryFlushState
Absence = absence.PrivateStageAbsenceCheckpointState
TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"


def _intent() -> intents.PrivateTransactionIntent:
    value = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        value,
        "witness",
        SimpleNamespace(
            transaction_id=TX, operation=witness.PrivateBindingOperation.REBIND_MOVE
        ),
    )
    object.__setattr__(value, "registry_before", b"registry-before")
    object.__setattr__(value, "descriptor_before", b"descriptor-before")
    return value


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    native: bool = True,
    states: tuple[Absence, Absence] = (
        Absence.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        Absence.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
    ),
    inventories: tuple[inventory.PrivateRegistryStageInventoryState, ...] = (
        inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,
    ),
    change_namespace: bool = False,
    owner_changed: bool = False,
    guard_refusal: retained.RetainedDescriptorGuardCode | None = None,
    final_refusal: bool = False,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda _: b"canonical"
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: _INTENT)

    @contextmanager
    def retain(_root: Path, _workspace: Path) -> Iterator[None]:
        events.append("enter")
        if guard_refusal is not None:
            raise retained.RetainedDescriptorGuardError(guard_refusal)
        yield
        if final_refusal:
            raise retained.RetainedDescriptorGuardError(
                retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
            )
        events.append("exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", retain)
    owner = object()
    calls = iter([owner, object()] if owner_changed else [owner, owner])
    monkeypatch.setattr(ordered, "_owner", lambda: next(calls))
    namespace_calls = [0]

    def ns(_root: Path, _tx: str) -> tuple[frozenset[str], frozenset[str]]:
        namespace_calls[0] += 1
        events.append("namespace")
        second = "changed" if change_namespace and namespace_calls[0] > 1 else "stable"
        return frozenset({TX + ".json"}), frozenset({second})

    monkeypatch.setattr(absence, "_namespace", ns)
    state_reads = iter(states)

    def observe(*_args: object) -> Absence:
        events.append("images")
        return next(state_reads)

    monkeypatch.setattr(absence, "_images", observe)
    inventory_reads = iter(inventories if len(inventories) > 1 else inventories * 2)

    def inv(*_args: object) -> inventory.PrivateRegistryStageInventoryState:
        events.append("inventory")
        return next(inventory_reads)

    monkeypatch.setattr(reader, "_inventory", inv)

    def named(_root: Path, _owner: object) -> bool:
        events.append("flush")
        return native

    monkeypatch.setattr(flush, "_flush_named_registry", named)


_INTENT = _intent()


@pytest.mark.parametrize("platform", ["linux", "darwin", "freebsd"])
def test_non_windows_refuses_before_native_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert (
        flush.flush_pending_private_registry_after_image(
            _INTENT, tmp_path, tmp_path
        ).state
        is State.UNSUPPORTED
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", [None, object(), "value", 15])
def test_invalid_intent_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert (
        flush.flush_pending_private_registry_after_image(
            cast(intents.PrivateTransactionIntent, bad), tmp_path, tmp_path
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("bad", [None, "relative", 0])
def test_invalid_root_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert (
        flush.flush_pending_private_registry_after_image(
            _INTENT, cast(Path, bad), tmp_path
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize(
    "after_state",
    [
        Absence.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        Absence.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED,
    ],
)
def test_only_postmove_stage_absent_image_states_are_flushed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, after_state: Absence
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, states=(after_state, after_state))
    review = flush.flush_pending_private_registry_after_image(
        _INTENT, tmp_path, tmp_path
    )
    assert review.state is State.FILE_FLUSHED_DIRECTORY_DURABILITY_UNQUALIFIED
    assert events == [
        "enter",
        "namespace",
        "inventory",
        "images",
        "flush",
        "images",
        "inventory",
        "namespace",
        "exit",
    ]
    for value in (TX, str(tmp_path)):
        assert value not in repr(review)
        assert value not in review.message
    assert not hasattr(review, "authorized")
    assert not hasattr(review, "commit_token")
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.UNSUPPORTED)


def test_failed_file_flush_is_recovery_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, native=False)
    state = flush.flush_pending_private_registry_after_image(
        _INTENT, tmp_path, tmp_path
    ).state
    assert state is State.FLUSH_UNQUALIFIED_RECOVERY_REQUIRED
    assert events.count("flush") == 1


@pytest.mark.parametrize(
    "bad_state",
    [
        Absence.STAGE_MISSING_BEFORE_REFUSED,
        Absence.STAGE_MISSING_PARTIAL_REFUSED,
        Absence.CHECKPOINT_REFUSED,
    ],
)
def test_no_flush_from_unqualified_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_state: Absence
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, states=(bad_state, bad_state))
    assert (
        flush.flush_pending_private_registry_after_image(
            _INTENT, tmp_path, tmp_path
        ).state
        is State.CHECKPOINT_UNQUALIFIED
    )
    assert "flush" not in events


@pytest.mark.parametrize("change", ["images", "inventory", "namespace", "owner"])
def test_postflush_drift_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    events: list[str] = []
    image_states = (
        (
            Absence.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Absence.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED,
        )
        if change == "images"
        else (
            Absence.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Absence.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        )
    )
    inventory_states = (
        (
            inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED,
        )
        if change == "inventory"
        else (inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,)
    )
    _setup(
        monkeypatch,
        events,
        states=image_states,
        inventories=inventory_states,
        change_namespace=(change == "namespace"),
        owner_changed=(change == "owner"),
    )
    status = flush.flush_pending_private_registry_after_image(
        _INTENT, tmp_path, tmp_path
    ).state
    assert status is (
        State.NAMESPACE_UNQUALIFIED
        if change in {"inventory", "namespace"}
        else State.OWNER_CHANGED
        if change == "owner"
        else State.CHECKPOINT_UNQUALIFIED
    )
    assert "flush" in events


@pytest.mark.parametrize(
    "code",
    [
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
        retained.RetainedDescriptorGuardCode.UNSUPPORTED,
        retained.RetainedDescriptorGuardCode.REFUSED_PATH,
    ],
)
def test_guard_fail_closed_before_native_flush(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: retained.RetainedDescriptorGuardCode,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, guard_refusal=code)
    state = flush.flush_pending_private_registry_after_image(
        _INTENT, tmp_path, tmp_path
    ).state
    assert state is (
        State.OWNER_CHANGED
        if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED
        else State.UNSUPPORTED
        if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED
        else State.GUARD_REFUSED
    )
    assert "flush" not in events


def test_guard_postcondition_prevents_positive_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, final_refusal=True)
    assert (
        flush.flush_pending_private_registry_after_image(
            _INTENT, tmp_path, tmp_path
        ).state
        is State.GUARD_REFUSED
    )
    assert events.count("flush") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows scratch file only")
def test_native_windows_scratch_flush_preserves_bytes_and_id(tmp_path: Path) -> None:
    """Real FlushFileBuffers against synthetic scratch file, never teacher data."""
    path = tmp_path / "scratch.bin"
    path.write_bytes(b"synthetic-Windows-flush" * 16)
    kernel, _ = wincheck._bind_api()
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
    opened = kernel.CreateFileW(
        str(path), 0x40000000 | 0x80, 7, None, 3, 0x00200000, None
    )
    handle = ctypes.cast(opened, ctypes.c_void_p).value
    bad = ctypes.c_void_p(-1).value
    assert handle is not None and handle != bad
    from pds_core import _teacher_private_native_journal_anchor as anchor

    try:
        before = anchor._windows_id(kernel, handle)
        assert before is not None
        assert flush._flush_handle(kernel, handle)
        assert anchor._windows_id(kernel, handle) == before
        assert path.read_bytes() == b"synthetic-Windows-flush" * 16
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def test_no_notes_capability_or_commit_authority() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(flush, "retire_private_journal")
    assert not hasattr(flush, "commit_workspace_association")
    assert not hasattr(flush, "notes_records")
