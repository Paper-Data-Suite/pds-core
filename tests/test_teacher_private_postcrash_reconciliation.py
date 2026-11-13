"""Core #238 3G9: single-lock post-crash reconciliation is strictly advisory."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as reconciliation
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_stage_absence_checkpoint as absence
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = reconciliation.PrivatePostcrashReconciliationState
TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"


def _intent() -> intents.PrivateTransactionIntent:
    candidate = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(candidate, "descriptor_after", b"synthetic-fixture")
    object.__setattr__(
        candidate,
        "witness",
        SimpleNamespace(
            transaction_id=TX, operation=witness.PrivateBindingOperation.REBIND_MOVE
        ),
    )
    object.__setattr__(candidate, "registry_before", b"before")
    object.__setattr__(candidate, "registry_after", b"after")
    object.__setattr__(candidate, "descriptor_before", b"descriptor")
    return candidate


_INTENT = _intent()


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    present: bool = True,
    pair_state: pair.PrivateExclusivePairCheckpointState = (
        pair.PrivateExclusivePairCheckpointState.MATCHING_BEFORE_REVIEW_REQUIRED
    ),
    absence_state: absence.PrivateStageAbsenceCheckpointState = (
        absence.PrivateStageAbsenceCheckpointState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED
    ),
    inventory_bad: bool = False,
    namespace_drift: bool = False,
    owner_changed: bool = False,
    post_guard: bool = False,
    guard_code: retained.RetainedDescriptorGuardCode | None = None,
    namespace_error: bool = False,
    foreign_stage: bool = False,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda _: b"canonical"
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: _INTENT)
    owner = object()
    owner_reads = iter([owner, object()] if owner_changed else [owner, owner])
    monkeypatch.setattr(ordered, "_owner", lambda: next(owner_reads))

    @contextmanager
    def hold(_root: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        if guard_code is not None:
            raise retained.RetainedDescriptorGuardError(guard_code)
        yield
        if post_guard:
            raise retained.RetainedDescriptorGuardError(
                retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
            )
        events.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", hold)
    call_count = [0]

    def entries(path: Path) -> frozenset[str]:
        events.append("names")
        if namespace_error:
            raise pair._NamespaceChanged
        if path.name == "transactions":
            return frozenset({TX + ".json"})
        call_count[0] += 1
        if foreign_stage:
            return frozenset({".unexpected.registry-stage"})
        if namespace_drift and call_count[0] > 1:
            return frozenset({"metadata.json", "unexpected"})
        return (
            frozenset({"metadata.json", "." + TX + ".registry-stage"})
            if present
            else frozenset({"metadata.json"})
        )

    monkeypatch.setattr(pair, "_names", entries)

    def inv(*_args: object) -> inventory.PrivateRegistryStageInventoryState:
        events.append("inventory")
        if inventory_bad:
            return inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        return (
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            if present
            else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
        )

    monkeypatch.setattr(readers, "_inventory", inv)

    def present_images(*_args: object) -> pair.PrivateExclusivePairCheckpointState:
        events.append("present-images")
        return pair_state

    def absent_images(*_args: object) -> absence.PrivateStageAbsenceCheckpointState:
        events.append("absent-images")
        return absence_state

    monkeypatch.setattr(pair, "_review_images", present_images)
    monkeypatch.setattr(absence, "_images", absent_images)


def _review(root: Path) -> reconciliation.PrivatePostcrashReconciliationReview:
    return reconciliation.reconcile_native_private_pending_registry_after_interruption(
        _INTENT, root, root
    )


@pytest.mark.parametrize("platform", ["darwin", "freebsd", "plan9"])
def test_unsupported_platform_has_no_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert _review(tmp_path).state is State.UNSUPPORTED
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", [None, 7, object(), "bad"])
def test_invalid_intent_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert (
        reconciliation.reconcile_native_private_pending_registry_after_interruption(
            cast(intents.PrivateTransactionIntent, bad), tmp_path, tmp_path
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("bad", [None, 123, "path"])
def test_invalid_roots_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert (
        reconciliation.reconcile_native_private_pending_registry_after_interruption(
            _INTENT, cast(Path, bad), tmp_path
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize(
    "seen,expected",
    [
        (
            pair.PrivateExclusivePairCheckpointState.MATCHING_BEFORE_REVIEW_REQUIRED,
            State.STAGED_BEFORE_REVIEW_REQUIRED,
        ),
        (
            pair.PrivateExclusivePairCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED,
            State.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED,
        ),
        (
            pair.PrivateExclusivePairCheckpointState.NATIVE_IMAGE_UNQUALIFIED,
            State.IMAGES_UNQUALIFIED,
        ),
        (
            pair.PrivateExclusivePairCheckpointState.CHECKPOINT_REFUSED,
            State.IMAGES_UNQUALIFIED,
        ),
        (
            pair.PrivateExclusivePairCheckpointState.NAMESPACE_UNQUALIFIED,
            State.NAMESPACE_UNQUALIFIED,
        ),
        (pair.PrivateExclusivePairCheckpointState.OWNER_CHANGED, State.OWNER_CHANGED),
    ],
)
def test_stage_present_native_classification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    seen: pair.PrivateExclusivePairCheckpointState,
    expected: State,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, pair_state=seen)
    result = _review(tmp_path)
    assert result.state is expected
    assert events.count("present-images") == 1
    assert "absent-images" not in events
    assert events.count("inventory") == 2
    assert events[-1] == "guard-exit"
    for secret in (TX, str(tmp_path)):
        assert secret not in repr(result)
        assert secret not in result.message
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "commit_token")
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


@pytest.mark.parametrize(
    "seen,expected",
    [
        (
            absence.PrivateStageAbsenceCheckpointState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            State.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        ),
        (
            absence.PrivateStageAbsenceCheckpointState.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED,
            State.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
        ),
        (
            absence.PrivateStageAbsenceCheckpointState.STAGE_MISSING_BEFORE_REFUSED,
            State.STAGE_MISSING_BEFORE_REFUSED,
        ),
        (
            absence.PrivateStageAbsenceCheckpointState.STAGE_MISSING_PARTIAL_REFUSED,
            State.STAGE_MISSING_PARTIAL_REFUSED,
        ),
        (
            absence.PrivateStageAbsenceCheckpointState.CHECKPOINT_REFUSED,
            State.IMAGES_UNQUALIFIED,
        ),
        (
            absence.PrivateStageAbsenceCheckpointState.NATIVE_IMAGE_UNQUALIFIED,
            State.IMAGES_UNQUALIFIED,
        ),
        (
            absence.PrivateStageAbsenceCheckpointState.NAMESPACE_UNQUALIFIED,
            State.NAMESPACE_UNQUALIFIED,
        ),
    ],
)
def test_stage_absent_native_classification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    seen: absence.PrivateStageAbsenceCheckpointState,
    expected: State,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, present=False, absence_state=seen)
    assert _review(tmp_path).state is expected
    assert events.count("absent-images") == 1
    assert "present-images" not in events
    assert events[-1] == "guard-exit"


@pytest.mark.parametrize("problem", ["inventory", "foreign", "drift", "names"])
def test_competing_or_changed_namespace_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, problem: str
) -> None:
    events: list[str] = []
    _setup(
        monkeypatch,
        events,
        inventory_bad=problem == "inventory",
        foreign_stage=problem == "foreign",
        namespace_drift=problem == "drift",
        namespace_error=problem == "names",
    )
    assert _review(tmp_path).state is State.NAMESPACE_UNQUALIFIED
    if problem in {"inventory", "foreign", "names"}:
        assert "present-images" not in events


@pytest.mark.parametrize(
    "code,expected",
    [
        (retained.RetainedDescriptorGuardCode.OWNER_CHANGED, State.OWNER_CHANGED),
        (retained.RetainedDescriptorGuardCode.UNSUPPORTED, State.UNSUPPORTED),
        (retained.RetainedDescriptorGuardCode.REFUSED_PATH, State.GUARD_REFUSED),
    ],
)
def test_guard_refusal_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: retained.RetainedDescriptorGuardCode,
    expected: State,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, guard_code=code)
    assert _review(tmp_path).state is expected
    assert "present-images" not in events


def test_guard_postcondition_blocks_advisory_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, post_guard=True)
    assert _review(tmp_path).state is State.GUARD_REFUSED
    assert "guard-exit" not in events


def test_changed_owner_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, owner_changed=True)
    assert _review(tmp_path).state is State.OWNER_CHANGED


def test_initialization_refused_before_locks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    initialized = _intent()
    object.__setattr__(
        initialized,
        "witness",
        SimpleNamespace(
            transaction_id=TX, operation=witness.PrivateBindingOperation.INITIALIZE
        ),
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: initialized
    )
    assert (
        reconciliation.reconcile_native_private_pending_registry_after_interruption(
            initialized, tmp_path, tmp_path
        ).state
        is State.INITIALIZATION_REFUSED
    )
    assert not events


def test_no_writer_and_notes_capabilities() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for name in (
        "retire_journal",
        "replay_registry",
        "commit_private_binding",
        "notes_records",
    ):
        assert not hasattr(reconciliation, name)
