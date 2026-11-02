"""Core #238 Slice 3G5: synthetic Windows native replacement scope contract."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as desc_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_stage_checkpoint_review as reader
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_provision as wincreate
from pds_core import _teacher_private_windows_registry_replacement_guard as guard
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "c41f1bde-962e-4250-a2b1-09a4144e6125"
JOURNAL = b"synthetic-journal"
BEFORE = b"synthetic-registry-before"
AFTER = b"synthetic-registry-after"
DESCRIPTOR = b"synthetic-descriptor"
State = guard.PrivateWindowsRegistryReplacementCode


def _intent() -> intents.PrivateTransactionIntent:
    proposed = object.__new__(intents.PrivateTransactionIntent)
    operation = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(
        operation, "operation", witness.PrivateBindingOperation.FORK_COPY
    )
    object.__setattr__(operation, "transaction_id", TX)
    object.__setattr__(proposed, "witness", operation)
    object.__setattr__(proposed, "registry_before", BEFORE)
    object.__setattr__(proposed, "registry_after", AFTER)
    object.__setattr__(proposed, "descriptor_before", DESCRIPTOR)
    return proposed


def _owner() -> inspection.EffectiveOSOwner:
    return inspection.EffectiveOSOwner("windows_token_sid", "synthetic-os-owner")


def _review(raw: bytes) -> SimpleNamespace:
    return SimpleNamespace(image=raw)


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    fail: str = "",
    drift: str = "",
    owner_change: bool = False,
) -> None:
    owner_count = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal owner_count
        owner_count += 1
        if owner_change and owner_count > 1:
            return inspection.EffectiveOSOwner("windows_token_sid", "other")
        return _owner()

    @contextmanager
    def scope(*_args: object) -> Iterator[None]:
        events.append("lock-enter")
        yield
        events.append("lock-exit")

    @contextmanager
    def native(*_args: object) -> Iterator[None]:
        events.append("native-enter")
        yield
        if fail == "native":
            raise guard.PrivateWindowsRegistryReplacementError(
                State.UNEXPECTED_MUTATION
            )
        events.append("native-exit")

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", scope)
    monkeypatch.setattr(ordered, "_owner", owner)
    monkeypatch.setattr(journal_guard, "_held_windows", scope)
    monkeypatch.setattr(desc_guard, "_held_windows_descriptor", scope)
    monkeypatch.setattr(guard, "_held_windows_target_and_stage", native)
    calls = {
        "namespace": 0,
        "inventory": 0,
        "journal": 0,
        "registry": 0,
        "descriptor": 0,
        "stage": 0,
    }

    def names(_root: Path, _tx: str, *, stage_present: bool) -> frozenset[str]:
        calls["namespace"] += 1
        if fail == "namespace" and calls["namespace"] == 2:
            raise guard.PrivateWindowsRegistryReplacementError(
                State.NAMESPACE_UNQUALIFIED
            )
        if drift == "namespace" and not stage_present:
            return frozenset({"foreign"})
        return (
            frozenset({"registry.json", "other", "." + TX + ".registry-stage"})
            if stage_present
            else frozenset({"registry.json", "other"})
        )

    def stages(*_args: object) -> inventory.PrivateRegistryStageInventoryState:
        calls["inventory"] += 1
        if fail == "inventory":
            return inventory.PrivateRegistryStageInventoryState.UNSUPPORTED
        return (
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            if calls["inventory"] == 1
            else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
        )

    def read(kind: str) -> SimpleNamespace:
        calls[kind] += 1
        events.append(kind)
        raw = {
            "journal": JOURNAL,
            "registry": BEFORE if calls["inventory"] == 1 else AFTER,
            "descriptor": DESCRIPTOR,
            "stage": AFTER,
        }[kind]
        if drift == kind and calls[kind] == (
            3 if kind in ("journal", "registry", "descriptor") else 2
        ):
            raw = b"foreign"
        if fail == kind:
            raw = b"foreign"
        return _review(raw)

    monkeypatch.setattr(guard, "_namespace", names)
    monkeypatch.setattr(reader, "_inventory", stages)
    monkeypatch.setattr(reader, "_journal", lambda *_: read("journal"))
    monkeypatch.setattr(reader, "_registry", lambda *_: read("registry"))
    monkeypatch.setattr(reader, "_descriptor", lambda *_: read("descriptor"))
    monkeypatch.setattr(reader, "_stage", lambda *_: read("stage"))
    for kind in ("journal", "registry", "descriptor", "stage"):
        monkeypatch.setattr(reader, "_" + kind + "_failure", lambda *_: None)


def test_expected_scope_reads_both_images_and_preserves_lock_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    with guard._hold_windows_expected_registry_replacement(
        _intent(), tmp_path, tmp_path, JOURNAL
    ):
        events.append("caller")
    assert events.count("lock-enter") == 3
    assert events.count("lock-exit") == 3
    assert (
        events.index("native-enter")
        < events.index("caller")
        < events.index("native-exit")
    )
    assert events.count("stage") == 2
    assert events.count("registry") == 4
    assert events.count("descriptor") == 4
    assert events.count("journal") == 4


@pytest.mark.parametrize(
    "fail",
    ["namespace", "inventory", "journal", "registry", "descriptor", "stage", "native"],
)
def test_guards_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fail: str
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, fail=fail)
    with pytest.raises(guard.PrivateWindowsRegistryReplacementError):
        with guard._hold_windows_expected_registry_replacement(
            _intent(), tmp_path, tmp_path, JOURNAL
        ):
            events.append("caller")
    if fail in {"namespace", "inventory", "journal", "registry", "descriptor", "stage"}:
        assert events.count("native-enter") == 1


@pytest.mark.parametrize(
    "drift", ["namespace", "journal", "registry", "descriptor", "stage"]
)
def test_interference_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, drift: str
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, drift=drift)
    with pytest.raises(guard.PrivateWindowsRegistryReplacementError):
        with guard._hold_windows_expected_registry_replacement(
            _intent(), tmp_path, tmp_path, JOURNAL
        ):
            events.append("caller")


def test_owner_switch_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, owner_change=True)
    with pytest.raises(guard.PrivateWindowsRegistryReplacementError) as found:
        with guard._hold_windows_expected_registry_replacement(
            _intent(), tmp_path, tmp_path, JOURNAL
        ):
            pass
    assert found.value.code is State.OWNER_CHANGED


def test_unsupported_platform_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(guard.PrivateWindowsRegistryReplacementError) as found:
        with guard.hold_expected_windows_private_registry_replacement(
            _intent(), tmp_path, tmp_path
        ):
            pass
    assert found.value.code is State.UNSUPPORTED


def test_invalid_proposal_refused_before_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    with pytest.raises(guard.PrivateWindowsRegistryReplacementError) as found:
        with guard.hold_expected_windows_private_registry_replacement(
            cast(intents.PrivateTransactionIntent, None), tmp_path, tmp_path
        ):
            pass
    assert found.value.code is State.INVALID_REQUEST


def test_initialize_refused_before_native_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    proposed = _intent()
    object.__setattr__(
        proposed.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: JOURNAL
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: proposed
    )
    with pytest.raises(guard.PrivateWindowsRegistryReplacementError) as found:
        with guard.hold_expected_windows_private_registry_replacement(
            proposed, tmp_path, tmp_path
        ):
            pass
    assert found.value.code is State.INVALID_REQUEST


def test_no_authorization_or_records_exposed() -> None:
    for forbidden in (
        "commit_private_binding",
        "retire_journal",
        "apply_recovery",
        "create_note",
        "replace_registry",
    ):
        assert not hasattr(guard, forbidden)
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    result = guard.PrivateWindowsRegistryReplacementError(State.ANCHOR_REFUSED)
    assert TX not in str(result) and "synthetic" not in str(result)


def test_native_file_identity_rejects_missing_or_insecure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_kernel: Any = object()
    owner = _owner()
    info = SimpleNamespace(directory=False, delete_pending=False, number_of_links=1)
    monkeypatch.setattr(anchor, "_windows_id", lambda *_: (1, b"a" * 16))
    monkeypatch.setattr(descriptor, "_windows_info", lambda *_: (0, info))
    monkeypatch.setattr(
        wincheck,
        "_handle_dacl_state",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    assert guard._native_file_id(mock_kernel, object(), 42, owner) == (1, b"a" * 16)
    monkeypatch.setattr(anchor, "_windows_id", lambda *_: None)
    with pytest.raises(guard.PrivateWindowsRegistryReplacementError):
        guard._native_file_id(mock_kernel, object(), 42, owner)


def test_public_scope_does_not_mutate_when_caller_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    proposed = _intent()
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: JOURNAL
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: proposed
    )
    events: list[str] = []
    _setup(monkeypatch, events)
    before = tuple(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        with guard.hold_expected_windows_private_registry_replacement(
            proposed, tmp_path, tmp_path
        ):
            raise RuntimeError("synthetic interruption")
    assert tuple(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    "variation",
    [
        "success",
        "wrong-target",
        "stage-remains",
        "parent-swapped",
        "old-handle-swapped",
        "acl-denied",
    ],
)
def test_native_handles_pin_stage_and_target_file_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variation: str
) -> None:
    """Synthetic native handle substitution must fail before a success claim."""
    state = {"renamed": False}
    closed: list[int] = []

    class Kernel:
        def CloseHandle(self, handle: Any) -> None:
            closed.append(int(handle.value))

    kernel = Kernel()
    monkeypatch.setattr(wincheck, "_bind_api", lambda: (kernel, object()))
    monkeypatch.setattr(
        wincheck,
        "_native_windows_walk",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)

    def opened(_kernel: Any, path: Path) -> tuple[int | None, int]:
        name = path.name
        if path == tmp_path:
            return 14 if state["renamed"] and variation == "parent-swapped" else 11, 0
        if name == "registry.json":
            if not state["renamed"]:
                return 12, 0
            return (12 if variation == "wrong-target" else 13), 0
        if name == "." + TX + ".registry-stage":
            if not state["renamed"] or variation == "stage-remains":
                return 13, 0
            return None, 2
        return None, 2

    monkeypatch.setattr(anchor, "_windows_open", opened)

    def file_id(_kernel: Any, handle: int) -> tuple[int, bytes]:
        actual = (
            14
            if state["renamed"] and handle == 11 and variation == "parent-swapped"
            else handle
        )
        if state["renamed"] and handle == 12 and variation == "old-handle-swapped":
            actual = 14
        return (1, bytes([actual]) * 16)

    monkeypatch.setattr(anchor, "_windows_id", file_id)

    def info(_kernel: Any, handle: int) -> tuple[int, SimpleNamespace]:
        directory = handle in (11, 14)
        return (
            0x10 if directory else 0,
            SimpleNamespace(
                directory=directory, delete_pending=False, number_of_links=1
            ),
        )

    monkeypatch.setattr(descriptor, "_windows_info", info)

    def acl(
        _kernel: Any, _advapi: Any, handle: int, _owner: inspection.EffectiveOSOwner
    ) -> NativePrivatePreflightState:
        if variation == "acl-denied" and handle == 13:
            return NativePrivatePreflightState.MISSING
        return NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED

    monkeypatch.setattr(wincheck, "_handle_dacl_state", acl)
    if variation == "success":
        with guard._held_windows_target_and_stage(
            tmp_path, "." + TX + ".registry-stage", _owner()
        ):
            state["renamed"] = True
    else:
        with pytest.raises(guard.PrivateWindowsRegistryReplacementError):
            with guard._held_windows_target_and_stage(
                tmp_path, "." + TX + ".registry-stage", _owner()
            ):
                state["renamed"] = True
    assert len(closed) >= (0 if variation == "acl-denied" else 3)
