"""Core #238 Slice 3G14: continuously held native recovery evidence fence."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = operation.PrivateRecoveryOperationGuardState
Step = actions.PrivateRecoveryProposedStep
RState = recovery.PrivatePostcrashReconciliationState


def _intent() -> intents.PrivateTransactionIntent:
    i = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        i,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            transaction_id="11111111-1111-4111-8111-111111111111",
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(i, "registry_before", b"private-registry-7")
    object.__setattr__(i, "registry_after", b"private-registry-8")
    object.__setattr__(i, "descriptor_before", b"private-descriptor-7")
    object.__setattr__(i, "descriptor_after", b"private-descriptor-8")
    return i


_INTENT = _intent()
_STEPS = {
    Step.REVIEW_PREPARED_RESTART: (
        7,
        True,
        RState.STAGED_BEFORE_REVIEW_REQUIRED,
        State.PREPARED_ONE_SCOPE_REVIEW_REQUIRED,
    ),
    Step.REVIEW_DESCRIPTOR_COMPLETION: (
        8,
        False,
        RState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        State.DESCRIPTOR_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
    ),
    Step.REVIEW_JOURNAL_RETIREMENT: (
        8,
        False,
        RState.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
        State.JOURNAL_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
    ),
}


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    override_image: list[object] | None = None,
    override_class: list[object] | None = None,
    inventory_values: list[object] | None = None,
    namespace_values: list[object] | None = None,
    owner_values: list[object] | None = None,
    throw: BaseException | None = None,
    throw_at: str = "",
    release_error: BaseException | None = None,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: b"canonical-intent"
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: _INTENT
    )
    monkeypatch.setattr(
        metadata,
        "encode_private_registry",
        lambda v: b"private-registry-" + str(v.revision).encode(),
    )
    monkeypatch.setattr(
        metadata,
        "decode_private_registry",
        lambda raw: SimpleNamespace(
            revision=7 if raw == b"private-registry-7" else 8,
        ),
    )
    active = [False]

    @contextmanager
    def guard(*_args: object) -> Iterator[None]:
        calls.append("acquire")
        assert not active[0]
        active[0] = True
        try:
            yield
        finally:
            active[0] = False
            calls.append("release")
            if release_error is not None:
                raise release_error

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)

    def native(
        label: str, values: list[object] | None, default: object
    ) -> Callable[..., object]:
        it = iter(values) if values is not None else None

        def wrapped(*_args: object) -> object:
            calls.append(label)
            assert active[0], "native evidence escaped operation-owned guard"
            if throw_at == label and throw is not None:
                raise throw
            return next(it) if it is not None else default

        return wrapped

    owner = SimpleNamespace(uid="teacher-local")
    monkeypatch.setattr(ordered, "_owner", native("owner", owner_values, owner))
    stage = _STEPS[step][1]
    ns = (
        frozenset({_INTENT.witness.transaction_id + ".json"}),
        frozenset({"." + _INTENT.witness.transaction_id + ".registry-stage"})
        if stage
        else frozenset(),
        stage,
    )
    monkeypatch.setattr(
        recovery, "_namespace", native("namespace", namespace_values, ns)
    )
    iv = (
        inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
        if stage
        else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
    )
    monkeypatch.setattr(
        readers, "_inventory", native("inventory", inventory_values, iv)
    )
    check = _STEPS[step][2]
    monkeypatch.setattr(
        recovery, "_classify_present", native("classify", override_class, check)
    )
    monkeypatch.setattr(
        recovery, "_classify_absent", native("classify", override_class, check)
    )
    image = (
        b"canonical-intent",
        _INTENT.registry_before if stage else _INTENT.registry_after,
        _INTENT.descriptor_after
        if step is Step.REVIEW_JOURNAL_RETIREMENT
        else _INTENT.descriptor_before,
        _INTENT.registry_after if stage else None,
    )
    monkeypatch.setattr(exact, "_images", native("images", override_image, image))


def _review(
    root: Path,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    revision: int = 7,
    proposal: intents.PrivateTransactionIntent = _INTENT,
) -> operation.PrivateRecoveryOperationGuardReview:
    return operation.review_operation_owned_private_recovery_guard(
        step, revision, proposal, root, root
    )


@pytest.mark.parametrize("step", list(_STEPS))
def test_matching_one_retained_scope_two_rounds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step)
    result = _review(tmp_path, step, _STEPS[step][0])
    assert result.state is _STEPS[step][3]
    assert calls.count("acquire") == calls.count("release") == 1
    assert calls.count("classify") == calls.count("images") == 2
    assert calls[0] == "acquire" and calls[-1] == "release"
    assert calls.count("namespace") >= 5


@pytest.mark.parametrize("step", list(_STEPS))
def test_matching_result_is_frozen_and_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(monkeypatch, [], step=step)
    result = _review(tmp_path, step, _STEPS[step][0])
    with pytest.raises(FrozenInstanceError):
        result.state = State.IO_ERROR  # type: ignore[misc]
    assert "private-" not in repr(result)
    assert not hasattr(result, "permit")
    assert not hasattr(result, "path")
    assert not hasattr(result, "handle")


@pytest.mark.parametrize("step", list(_STEPS))
@pytest.mark.parametrize("wrong", [-1, 0, 1, 9, True, 7.0, "7"])
def test_wrong_requested_revision_refused_without_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step, wrong: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step)
    result = _review(tmp_path, step, cast(int, wrong))
    assert result.state in {State.REVISION_MISMATCH_REFUSED, State.INVALID_REQUEST}
    assert calls == []


@pytest.mark.parametrize("step", list(_STEPS))
@pytest.mark.parametrize(
    "index,wrong",
    [
        (0, b"foreign-journal"),
        (1, b"foreign-registry"),
        (2, b"foreign-descriptor"),
        (3, b"foreign-stage"),
    ],
)
def test_exact_image_byte_mismatch_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step: Step,
    index: int,
    wrong: bytes,
) -> None:
    calls: list[str] = []
    stage = _STEPS[step][1]
    valid = [
        b"canonical-intent",
        _INTENT.registry_before if stage else _INTENT.registry_after,
        _INTENT.descriptor_after
        if step is Step.REVIEW_JOURNAL_RETIREMENT
        else _INTENT.descriptor_before,
        _INTENT.registry_after if stage else None,
    ]
    valid[index] = wrong
    if not stage and index == 3:
        valid[3] = wrong
    _setup(monkeypatch, calls, step=step, override_image=[tuple(valid)] * 2)
    assert (
        _review(tmp_path, step, _STEPS[step][0]).state is State.IMAGE_MISMATCH_PRESERVE
    )
    assert calls.count("release") == 1


@pytest.mark.parametrize("step", list(_STEPS))
def test_checkpoint_conflict_is_preserved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(
        monkeypatch,
        [],
        step=step,
        override_class=[RState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED] * 2,
    )
    assert (
        _review(tmp_path, step, _STEPS[step][0]).state
        is State.CHECKPOINT_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_STEPS))
def test_checkpoint_changed_between_rounds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(
        monkeypatch,
        [],
        step=step,
        override_class=[
            _STEPS[step][2],
            RState.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED,
        ],
    )
    assert _review(tmp_path, step, _STEPS[step][0]).state is State.IMAGE_DRIFT_PRESERVE


@pytest.mark.parametrize("step", list(_STEPS))
def test_images_changed_between_rounds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    stage = _STEPS[step][1]
    good = (
        b"canonical-intent",
        _INTENT.registry_before if stage else _INTENT.registry_after,
        _INTENT.descriptor_after
        if step is Step.REVIEW_JOURNAL_RETIREMENT
        else _INTENT.descriptor_before,
        _INTENT.registry_after if stage else None,
    )
    altered = (b"foreign", *good[1:])
    _setup(monkeypatch, [], step=step, override_image=[good, altered])
    assert _review(tmp_path, step, _STEPS[step][0]).state is State.IMAGE_DRIFT_PRESERVE


@pytest.mark.parametrize("step", list(_STEPS))
def test_missing_or_malformed_image_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(monkeypatch, [], step=step, override_image=[None])
    assert (
        _review(tmp_path, step, _STEPS[step][0]).state is State.IMAGE_MISMATCH_PRESERVE
    )


@pytest.mark.parametrize("step", list(_STEPS))
def test_unexpected_inventory_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    alternative = (
        inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
        if _STEPS[step][1]
        else inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
    )
    _setup(monkeypatch, [], step=step, inventory_values=[alternative])
    assert (
        _review(tmp_path, step, _STEPS[step][0]).state
        is State.NAMESPACE_CHANGED_PRESERVE
    )


@pytest.mark.parametrize("step", list(_STEPS))
def test_namespace_change_mid_guard_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    stage = _STEPS[step][1]
    stable = (
        frozenset({_INTENT.witness.transaction_id + ".json"}),
        frozenset({"." + _INTENT.witness.transaction_id + ".registry-stage"})
        if stage
        else frozenset(),
        stage,
    )
    shifted: tuple[frozenset[str], frozenset[str], bool] = (
        frozenset({"other"}),
        frozenset(),
        False,
    )
    _setup(monkeypatch, [], step=step, namespace_values=[stable, stable, shifted])
    assert (
        _review(tmp_path, step, _STEPS[step][0]).state
        is State.NAMESPACE_CHANGED_PRESERVE
    )


@pytest.mark.parametrize("step", list(_STEPS))
def test_owner_change_mid_guard_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    owner = SimpleNamespace(uid="initial")
    _setup(
        monkeypatch, [], step=step, owner_values=[owner, SimpleNamespace(uid="changed")]
    )
    assert _review(tmp_path, step, _STEPS[step][0]).state is State.OWNER_CHANGED


@pytest.mark.parametrize("step", list(_STEPS))
def test_guard_release_failure_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    error = retained.RetainedDescriptorGuardError(
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED
    )
    _setup(monkeypatch, [], step=step, release_error=error)
    assert _review(tmp_path, step, _STEPS[step][0]).state is State.OWNER_CHANGED


@pytest.mark.parametrize("step", list(_STEPS))
def test_interrupt_mid_native_review_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step, throw=KeyboardInterrupt(), throw_at="images")
    assert _review(tmp_path, step, _STEPS[step][0]).state is State.INTERRUPTED_PRESERVE
    assert calls[-1] == "release"


@pytest.mark.parametrize("platform", ["darwin", "freebsd", "plan9"])
def test_unsupported_platform_does_not_touch_filesystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    monkeypatch.setattr(sys, "platform", platform)
    assert _review(tmp_path).state is State.UNSUPPORTED
    assert calls == []


@pytest.mark.parametrize("invalid_step", [None, "review_prepared_restart", 1, object()])
def test_step_must_be_enum(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid_step: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, cast(Step, invalid_step)).state is State.INVALID_REQUEST
    assert calls == []


def test_initialization_requires_separate_guarded_protocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [])
    new = _intent()
    object.__setattr__(
        new.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: new)
    assert _review(tmp_path, proposal=new).state is State.INITIALIZATION_REFUSED


def test_invalid_canonical_intent_fails_without_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: object()
    )
    assert _review(tmp_path).state is State.INVALID_REQUEST
    assert calls == []


def test_untrusted_native_checkpoint_type_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [], override_class=["staged_before_review_required"])
    assert _review(tmp_path).state is State.IMAGE_MISMATCH_PRESERVE


def test_no_writer_or_notes_authority() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {
            "terminal.header.v1",
            "terminal.notes_command.v1",
        }
    )
    assert not hasattr(operation, "commit_private_workspace_binding")
    assert not hasattr(operation, "retire_private_journal")
    assert not hasattr(operation, "open_notes")
    assert not hasattr(operation, "write_private_registry")


@pytest.mark.parametrize("step", list(_STEPS))
def test_request_does_not_match_actual_stage_presence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(monkeypatch, [], step=step)
    true_step = step
    if true_step is Step.REVIEW_PREPARED_RESTART:
        mismatched: tuple[frozenset[str], frozenset[str], bool] = (
            frozenset({_INTENT.witness.transaction_id + ".json"}),
            frozenset(),
            False,
        )
    else:
        mismatched = (
            frozenset({_INTENT.witness.transaction_id + ".json"}),
            frozenset({"." + _INTENT.witness.transaction_id + ".registry-stage"}),
            True,
        )
    monkeypatch.setattr(recovery, "_namespace", lambda *_: mismatched)
    monkeypatch.setattr(
        readers,
        "_inventory",
        lambda *_: (
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            if mismatched[2]
            else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
        ),
    )
    result = _review(tmp_path, step, _STEPS[step][0])
    assert result.state is State.ACTION_MISMATCH_REFUSED


@pytest.mark.parametrize("step", list(_STEPS))
def test_guard_refusal_before_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(monkeypatch, [], step=step)

    @contextmanager
    def denied(*_args: object) -> Iterator[None]:
        raise retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.REFUSED_PATH
        )
        yield

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", denied)
    assert _review(tmp_path, step, _STEPS[step][0]).state is State.GUARD_REFUSED


@pytest.mark.parametrize("step", list(_STEPS))
def test_os_error_during_checkpoint_preserves_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    events: list[str] = []
    _setup(
        monkeypatch,
        events,
        step=step,
        throw=OSError("synthetic IO"),
        throw_at="classify",
    )
    assert _review(tmp_path, step, _STEPS[step][0]).state is State.IO_ERROR
    assert events[-1] == "release"


@pytest.mark.parametrize("step", list(_STEPS))
def test_garbage_image_shape_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(monkeypatch, [], step=step, override_image=[(b"only", b"two")])
    assert (
        _review(tmp_path, step, _STEPS[step][0]).state is State.IMAGE_MISMATCH_PRESERVE
    )
