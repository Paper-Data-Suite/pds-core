"""Core #238 3G8: native Windows directory flush probe remains non-authorizing."""

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
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as reader
from pds_core import _teacher_private_stage_absence_checkpoint as absence
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_directory_persistence_probe as probe
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = probe.PrivateWindowsDirectoryPersistenceState
Absence = absence.PrivateStageAbsenceCheckpointState
TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"


def _intent() -> intents.PrivateTransactionIntent:
    value = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(value, "descriptor_after", b"synthetic-fixture")
    object.__setattr__(value, "registry_after", b"synthetic-fixture")
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
        events.append("probe")
        return native

    monkeypatch.setattr(probe, "_try_flush_qualified_directory", named)


_INTENT = _intent()


@pytest.mark.parametrize("platform", ["linux", "darwin", "freebsd"])
def test_non_windows_refuses_before_native_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert (
        probe.probe_pending_private_registry_directory_persistence(
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
        probe.probe_pending_private_registry_directory_persistence(
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
        probe.probe_pending_private_registry_directory_persistence(
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
def test_only_after_image_states_allow_directory_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, after_state: Absence
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, states=(after_state, after_state))
    review = probe.probe_pending_private_registry_directory_persistence(
        _INTENT, tmp_path, tmp_path
    )
    assert review.state is State.DIRECTORY_FLUSH_OBSERVED_DURABILITY_UNQUALIFIED
    assert events == [
        "enter",
        "namespace",
        "inventory",
        "images",
        "probe",
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


def test_failed_directory_flush_preserves_recovery_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, native=False)
    state = probe.probe_pending_private_registry_directory_persistence(
        _INTENT, tmp_path, tmp_path
    ).state
    assert state is State.DIRECTORY_FLUSH_UNAVAILABLE_RECOVERY_REQUIRED
    assert events.count("probe") == 1


@pytest.mark.parametrize(
    "bad_state",
    [
        Absence.STAGE_MISSING_BEFORE_REFUSED,
        Absence.STAGE_MISSING_PARTIAL_REFUSED,
        Absence.CHECKPOINT_REFUSED,
    ],
)
def test_no_probe_from_unqualified_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_state: Absence
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, states=(bad_state, bad_state))
    assert (
        probe.probe_pending_private_registry_directory_persistence(
            _INTENT, tmp_path, tmp_path
        ).state
        is State.CHECKPOINT_UNQUALIFIED
    )
    assert "probe" not in events


@pytest.mark.parametrize("change", ["images", "inventory", "namespace", "owner"])
def test_postprobe_drift_is_refused(
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
    status = probe.probe_pending_private_registry_directory_persistence(
        _INTENT, tmp_path, tmp_path
    ).state
    assert status is (
        State.NAMESPACE_UNQUALIFIED
        if change in {"inventory", "namespace"}
        else State.OWNER_CHANGED
        if change == "owner"
        else State.CHECKPOINT_UNQUALIFIED
    )
    assert "probe" in events


@pytest.mark.parametrize(
    "code",
    [
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
        retained.RetainedDescriptorGuardCode.UNSUPPORTED,
        retained.RetainedDescriptorGuardCode.REFUSED_PATH,
    ],
)
def test_guard_fail_closed_before_directory_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: retained.RetainedDescriptorGuardCode,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, guard_refusal=code)
    state = probe.probe_pending_private_registry_directory_persistence(
        _INTENT, tmp_path, tmp_path
    ).state
    assert state is (
        State.OWNER_CHANGED
        if code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED
        else State.UNSUPPORTED
        if code is retained.RetainedDescriptorGuardCode.UNSUPPORTED
        else State.GUARD_REFUSED
    )
    assert "probe" not in events


def test_guard_postcondition_refuses_directory_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, final_refusal=True)
    assert (
        probe.probe_pending_private_registry_directory_persistence(
            _INTENT, tmp_path, tmp_path
        ).state
        is State.GUARD_REFUSED
    )
    assert events.count("probe") == 1


@pytest.mark.skipif(
    sys.platform != "win32", reason="native Windows scratch directory only"
)
def test_native_windows_scratch_directory_flush_never_claims_durability(
    tmp_path: Path,
) -> None:
    """Exercise real kernel directory flush against disposable files only.

    Windows may refuse directory FlushFileBuffers; refusal is a tested valid
    outcome, NOT an excuse to weaken protection on any teacher-private root.
    """
    marker = tmp_path / "synthetic-marker.bin"
    marker.write_bytes(b"unchanged-scratch-evidence")
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
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel.FlushFileBuffers.restype = wintypes.BOOL
    opened = kernel.CreateFileW(
        str(tmp_path),
        0x2 | 0x80 | 0x20000,
        7,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    handle = ctypes.cast(opened, ctypes.c_void_p).value
    if handle is not None and handle != ctypes.c_void_p(-1).value:
        try:
            before = anchor._windows_id(kernel, handle)
            assert before is not None
            assert bool(kernel.FlushFileBuffers(wintypes.HANDLE(handle))) in {
                True,
                False,
            }
            assert anchor._windows_id(kernel, handle) == before
        finally:
            kernel.CloseHandle(wintypes.HANDLE(handle))
    assert marker.read_bytes() == b"unchanged-scratch-evidence"
    assert sorted(p.name for p in tmp_path.iterdir()) == [marker.name]


@pytest.mark.parametrize("native_success", [True, False])
def test_directory_probe_native_api_has_no_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, native_success: bool
) -> None:
    """Require one directory FlushFileBuffers and retained file-ID continuity."""

    calls: list[object] = []

    class Create:
        argtypes: object = None
        restype: object = None

        def __call__(
            self,
            path: str,
            access: int,
            share: int,
            sec: object,
            mode: int,
            flags: int,
            template: object,
        ) -> ctypes.c_void_p:
            calls.append((path, access, share, mode, flags))
            assert sec is None and template is None
            return ctypes.c_void_p(777)

    class Flush:
        argtypes: object = None
        restype: object = None

        def __call__(self, handle: object) -> int:
            assert isinstance(handle, ctypes.c_void_p)
            assert handle.value == 777
            calls.append("flush")
            return int(native_success)

    class Close:
        def __call__(self, handle: object) -> int:
            assert isinstance(handle, ctypes.c_void_p)
            calls.append(("close", handle.value))
            return 1

    class Kernel:
        CreateFileW = Create()
        FlushFileBuffers = Flush()
        CloseHandle = Close()

    owner = object()
    monkeypatch.setattr(wincheck, "_bind_api", lambda: (Kernel(), object()))
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        wincheck,
        "_native_windows_walk",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    monkeypatch.setattr(
        wincheck,
        "_handle_dacl_state",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    monkeypatch.setattr(anchor, "_windows_id", lambda *_: (12, b"a" * 16))
    monkeypatch.setattr(anchor, "_windows_open", lambda *_: (888, 0))
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (0x10, SimpleNamespace(directory=True, delete_pending=False)),
    )
    assert (
        probe._try_flush_qualified_directory(
            tmp_path, cast(inspection.EffectiveOSOwner, owner)
        )
        is native_success
    )
    assert calls == [
        (str(tmp_path), 0x2 | 0x80 | 0x20000, 7, 3, 0x02000000 | 0x00200000),
        "flush",
        ("close", 888),
        ("close", 777),
    ]


def test_directory_probe_rejects_unprotected_native_handle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:

    class Create:
        argtypes: object = None
        restype: object = None

        def __call__(self, *_: object) -> ctypes.c_void_p:
            return ctypes.c_void_p(777)

    class Flush:
        argtypes: object = None
        restype: object = None

        def __call__(self, *_: object) -> int:
            raise AssertionError("Unprotected directory must never be flushed")

    class Close:
        def __call__(self, _handle: object) -> int:
            return 1

    class Kernel:
        CreateFileW = Create()
        FlushFileBuffers = Flush()
        CloseHandle = Close()

    monkeypatch.setattr(wincheck, "_bind_api", lambda: (Kernel(), object()))
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        wincheck,
        "_native_windows_walk",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    monkeypatch.setattr(anchor, "_windows_id", lambda *_: (12, b"a" * 16))
    monkeypatch.setattr(descriptor, "_windows_info", lambda *_: None)
    assert not probe._try_flush_qualified_directory(
        tmp_path, cast(inspection.EffectiveOSOwner, object())
    )


def test_no_notes_capability_or_commit_authority() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(probe, "retire_private_journal")
    assert not hasattr(probe, "commit_workspace_association")
    assert not hasattr(probe, "notes_records")
