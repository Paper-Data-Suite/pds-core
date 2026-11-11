"""Core #238 3G11: one continuous retained guard, two classifications, no writes."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_mutation_boundary as boundary
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = boundary.PrivateRecoveryMutationBoundaryState
Observed = recovery.PrivatePostcrashReconciliationState
Step = actions.PrivateRecoveryProposedStep
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
    readings: tuple[Observed, Observed] = (
        Observed.STAGED_BEFORE_REVIEW_REQUIRED,
        Observed.STAGED_BEFORE_REVIEW_REQUIRED,
    ),
    bad_inventory_at: int = 0,
    drift_namespace_at: int = 0,
    changed_owner_at: int = 0,
    guard_code: retained.RetainedDescriptorGuardCode | None = None,
    guard_post_error: bool = False,
    interrupt_at: int = 0,
    system_exit_at: int = 0,
    raise_io_at: int = 0,
    broken_image_type: bool = False,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda _: b"canonical"
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: _INTENT)
    owner = object()
    owner_counter = [0]

    def effective_owner() -> object:
        owner_counter[0] += 1
        events.append("owner")
        return object() if owner_counter[0] == changed_owner_at else owner

    monkeypatch.setattr(ordered, "_owner", effective_owner)

    @contextmanager
    def hold(_root: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        if guard_code is not None:
            raise retained.RetainedDescriptorGuardError(guard_code)
        try:
            yield
        finally:
            if guard_post_error:
                raise retained.RetainedDescriptorGuardError(
                    retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
                )
            events.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", hold)

    namespace = (
        frozenset({"metadata.json", "." + TX + ".registry-stage"})
        if present
        else frozenset({"metadata.json"})
    )
    namespace_reads = [0]

    def names(_root: Path, _tx: str) -> tuple[frozenset[str], frozenset[str], bool]:
        events.append("namespace")
        namespace_reads[0] += 1
        root_names = (
            frozenset({"metadata.json", "changed"})
            if namespace_reads[0] == drift_namespace_at
            else namespace
        )
        return (frozenset({TX + ".json"}), root_names, present)

    monkeypatch.setattr(recovery, "_namespace", names)
    inv_reads = [0]

    def inv(*_args: object) -> inventory.PrivateRegistryStageInventoryState:
        events.append("inventory")
        inv_reads[0] += 1
        if inv_reads[0] == bad_inventory_at:
            return inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        return (
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            if present
            else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
        )

    monkeypatch.setattr(readers, "_inventory", inv)
    image_reads = [0]

    def images(*_args: object) -> Observed:
        image_reads[0] += 1
        events.append("images")
        if image_reads[0] == interrupt_at:
            raise KeyboardInterrupt
        if image_reads[0] == system_exit_at:
            raise SystemExit(37)
        if image_reads[0] == raise_io_at:
            raise OSError("secret-private-path")
        if broken_image_type:
            return cast(Observed, object())
        return readings[image_reads[0] - 1]

    monkeypatch.setattr(recovery, "_classify_present", images)
    monkeypatch.setattr(recovery, "_classify_absent", images)


def _review(
    root: Path,
    requested: Step = Step.REVIEW_PREPARED_RESTART,
    proposed: intents.PrivateTransactionIntent = _INTENT,
) -> boundary.PrivateRecoveryMutationBoundaryReview:
    return boundary.review_retained_private_recovery_mutation_boundary(
        requested, proposed, root, root
    )


@pytest.mark.parametrize("platform", ["darwin", "freebsd", "sunos", "plan9"])
def test_unsupported_platform_before_locks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert _review(tmp_path).state is State.UNSUPPORTED
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", [None, "review", 7, object()])
def test_invalid_step_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    result = _review(tmp_path, cast(Step, bad))
    assert result.state is State.INVALID_REQUEST
    assert not events


@pytest.mark.parametrize("bad", [None, "intent", 99, object()])
def test_invalid_intent_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    assert (
        _review(tmp_path, proposed=cast(intents.PrivateTransactionIntent, bad)).state
        is State.INVALID_REQUEST
    )
    assert not events


@pytest.mark.parametrize("bad", [None, object(), 10, "root"])
def test_invalid_roots_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    assert (
        boundary.review_retained_private_recovery_mutation_boundary(
            Step.REVIEW_PREPARED_RESTART, _INTENT, cast(Path, bad), tmp_path
        ).state
        is State.INVALID_REQUEST
    )
    assert (
        boundary.review_retained_private_recovery_mutation_boundary(
            Step.REVIEW_PREPARED_RESTART, _INTENT, tmp_path, cast(Path, bad)
        ).state
        is State.INVALID_REQUEST
    )
    assert not events


@pytest.mark.parametrize(
    ("present", "seen", "step"),
    [
        (True, Observed.STAGED_BEFORE_REVIEW_REQUIRED, Step.REVIEW_PREPARED_RESTART),
        (
            False,
            Observed.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_DESCRIPTOR_COMPLETION,
        ),
        (
            False,
            Observed.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_JOURNAL_RETIREMENT,
        ),
    ],
)
def test_matching_requires_one_continuous_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    present: bool,
    seen: Observed,
    step: Step,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, present=present, readings=(seen, seen))
    result = _review(tmp_path, step)
    assert result.state is State.MATCHING_RETAINED_REVIEW_REQUIRED
    assert events == [
        "guard-enter",
        "owner",
        "namespace",
        "inventory",
        "namespace",
        "owner",
        "images",
        "inventory",
        "namespace",
        "owner",
        "images",
        "inventory",
        "namespace",
        "owner",
        "guard-exit",
    ]
    assert all(secret not in repr(result) for secret in (TX, str(tmp_path)))
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "commit_token")
    assert not hasattr(result, "path")
    assert not hasattr(result, "writer")
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("seen", "wrong"),
    [
        (Observed.STAGED_BEFORE_REVIEW_REQUIRED, Step.REVIEW_DESCRIPTOR_COMPLETION),
        (Observed.STAGED_BEFORE_REVIEW_REQUIRED, Step.REVIEW_JOURNAL_RETIREMENT),
        (
            Observed.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_PREPARED_RESTART,
        ),
        (
            Observed.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_JOURNAL_RETIREMENT,
        ),
        (
            Observed.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_PREPARED_RESTART,
        ),
        (
            Observed.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            Step.REVIEW_DESCRIPTOR_COMPLETION,
        ),
    ],
)
def test_mismatched_step_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, seen: Observed, wrong: Step
) -> None:
    events: list[str] = []
    _setup(
        monkeypatch,
        events,
        present=seen is Observed.STAGED_BEFORE_REVIEW_REQUIRED,
        readings=(seen, seen),
    )
    assert _review(tmp_path, wrong).state is State.ACTION_MISMATCH_REFUSED
    assert events.count("images") == 2


@pytest.mark.parametrize("at", [1, 2, 3])
def test_inventory_failure_at_every_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, bad_inventory_at=at)
    assert _review(tmp_path).state is State.NAMESPACE_CHANGED_PRESERVE
    assert events.count("images") == at - 1


@pytest.mark.parametrize("at", [2, 3, 4])
def test_namespace_drift_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, drift_namespace_at=at)
    assert _review(tmp_path).state is State.NAMESPACE_CHANGED_PRESERVE
    assert events.count("images") == at - 2


@pytest.mark.parametrize("at", [2, 3, 4])
def test_owner_change_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, changed_owner_at=at)
    assert _review(tmp_path).state is State.OWNER_CHANGED
    assert events.count("images") == at - 2


def test_image_drift_detected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[str] = []
    _setup(
        monkeypatch,
        events,
        readings=(
            Observed.STAGED_BEFORE_REVIEW_REQUIRED,
            Observed.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED,
        ),
    )
    assert _review(tmp_path).state is State.IMAGE_DRIFT_PRESERVE
    assert events.count("images") == 2


@pytest.mark.parametrize(
    "observed",
    [
        Observed.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED,
        Observed.STAGE_MISSING_BEFORE_REFUSED,
        Observed.STAGE_MISSING_PARTIAL_REFUSED,
        Observed.IMAGES_UNQUALIFIED,
        Observed.NAMESPACE_UNQUALIFIED,
        Observed.OWNER_CHANGED,
        Observed.IO_ERROR,
    ],
)
def test_unqualified_and_conflict_images_preserved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, observed: Observed
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, readings=(observed, observed))
    expected = (
        State.STAGED_CONFLICT_PRESERVE
        if observed is Observed.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED
        else State.CHECKPOINT_UNQUALIFIED
    )
    assert _review(tmp_path).state is expected


@pytest.mark.parametrize("at", [1, 2])
def test_keyboard_interrupt_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, interrupt_at=at)
    assert _review(tmp_path).state is State.INTERRUPTED_PRESERVE
    assert events[-1] == "guard-exit"


@pytest.mark.parametrize("at", [1, 2])
def test_native_io_error_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, raise_io_at=at)
    result = _review(tmp_path)
    assert result.state is State.IO_ERROR
    assert "secret-private-path" not in repr(result)
    assert events[-1] == "guard-exit"


def test_unexpected_native_type_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, broken_image_type=True)
    assert _review(tmp_path).state is State.CHECKPOINT_UNQUALIFIED
    assert events.count("images") == 1


@pytest.mark.parametrize(
    "code,expected",
    [
        (retained.RetainedDescriptorGuardCode.OWNER_CHANGED, State.OWNER_CHANGED),
        (retained.RetainedDescriptorGuardCode.UNSUPPORTED, State.UNSUPPORTED),
        (retained.RetainedDescriptorGuardCode.REFUSED_PATH, State.GUARD_REFUSED),
    ],
)
def test_native_guard_refusal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: retained.RetainedDescriptorGuardCode,
    expected: State,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, guard_code=code)
    assert _review(tmp_path).state is expected
    assert events.count("images") == 0


def test_guard_postcondition_refuses_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, guard_post_error=True)
    assert _review(tmp_path).state is State.GUARD_REFUSED
    assert events[-1] != "guard-exit"


def test_initialization_refused_before_guard(
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
    assert _review(tmp_path, proposed=initialized).state is State.INITIALIZATION_REFUSED
    assert not events


def test_system_exit_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, system_exit_at=1)
    with pytest.raises(SystemExit) as error:
        _review(tmp_path)
    assert error.value.code == 37
    assert events[-1] == "guard-exit"


def test_no_public_writer_or_notes() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for name in (
        "commit_private_binding",
        "retire_private_journal",
        "write_descriptor",
        "open_notes",
    ):
        assert not hasattr(boundary, name)
