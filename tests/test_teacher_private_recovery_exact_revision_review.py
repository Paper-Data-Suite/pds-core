"""Core #238 3G12: guarded exact native image and revision review, no mutation."""

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
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = exact.PrivateRecoveryExactRevisionState
Step = actions.PrivateRecoveryProposedStep
TX = "f45a1e57-c3b7-441b-a5c5-9e3a5ea12f5a"


def _intent() -> intents.PrivateTransactionIntent:
    item = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        item,
        "witness",
        SimpleNamespace(
            transaction_id=TX,
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(item, "registry_before", b"synthetic-r7")
    object.__setattr__(item, "registry_after", b"synthetic-r8")
    object.__setattr__(item, "descriptor_before", b"synthetic-descriptor-before")
    object.__setattr__(item, "descriptor_after", b"synthetic-descriptor-after")
    return item


_INTENT = _intent()


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    stage: bool = True,
    drift_at: int = 0,
    changed_owner_at: int = 0,
    bad_inventory_at: int = 0,
    bad_namespace_at: int = 0,
    bad_image: str = "",
    image_error_at: int = 0,
    interrupt_at: int = 0,
    guard_error: retained.RetainedDescriptorGuardCode | None = None,
    guard_exit_error: bool = False,
    revision_override: int = 0,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: b"synthetic-intent"
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: _INTENT
    )

    def registry_decode(data: bytes) -> SimpleNamespace:
        if data == b"synthetic-r7":
            return SimpleNamespace(revision=7)
        if data == b"synthetic-r8":
            return SimpleNamespace(revision=revision_override or 8)
        raise metadata.PrivateMetadataError(
            metadata.PrivateMetadataErrorCode.INVALID_ENCODING
        )

    monkeypatch.setattr(metadata, "decode_private_registry", registry_decode)
    monkeypatch.setattr(
        metadata,
        "encode_private_registry",
        lambda item: b"synthetic-r" + str(item.revision).encode("ascii"),
    )
    owner = object()
    owner_reads = [0]

    def native_owner() -> object:
        calls.append("owner")
        owner_reads[0] += 1
        return object() if owner_reads[0] == changed_owner_at else owner

    monkeypatch.setattr(ordered, "_owner", native_owner)

    @contextmanager
    def guard(_root: Path, _workspace: Path) -> Iterator[None]:
        calls.append("guard-enter")
        if guard_error is not None:
            raise retained.RetainedDescriptorGuardError(guard_error)
        try:
            yield
        finally:
            if guard_exit_error:
                raise retained.RetainedDescriptorGuardError(
                    retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
                )
            calls.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)
    census_reads = [0]

    def census(_root: Path, _tx: str) -> tuple[frozenset[str], frozenset[str], bool]:
        calls.append("namespace")
        census_reads[0] += 1
        entries = (
            frozenset({"private-metadata", "unexpected"})
            if census_reads[0] == bad_namespace_at
            else frozenset({"private-metadata"})
        )
        return frozenset({TX + ".json"}), entries, stage

    monkeypatch.setattr(recovery, "_namespace", census)
    inventory_reads = [0]

    def scan(*_args: object) -> inventory.PrivateRegistryStageInventoryState:
        calls.append("inventory")
        inventory_reads[0] += 1
        if inventory_reads[0] == bad_inventory_at:
            return inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        return (
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            if stage
            else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
        )

    monkeypatch.setattr(readers, "_inventory", scan)
    monkeypatch.setattr(readers, "_journal_failure", lambda *_: None)
    monkeypatch.setattr(readers, "_registry_failure", lambda *_: None)
    monkeypatch.setattr(readers, "_descriptor_failure", lambda *_: None)
    monkeypatch.setattr(readers, "_stage_failure", lambda *_: None)

    image_reads = [0]

    def read_group(name: str, data: bytes) -> SimpleNamespace:
        calls.append(name)
        if name == "journal":
            image_reads[0] += 1
            if image_reads[0] == interrupt_at:
                raise KeyboardInterrupt
            if image_reads[0] == image_error_at:
                raise OSError("private-data-secret")
        if bad_image == name:
            data = b"wrong-image"
        if drift_at == 2 and image_reads[0] == 2 and name == "registry":
            data = b"changed-image"
        if bad_image == "missing" and name == "registry":
            return SimpleNamespace(image=None)
        return SimpleNamespace(image=data)

    monkeypatch.setattr(
        readers, "_journal", lambda *_: read_group("journal", b"synthetic-intent")
    )
    monkeypatch.setattr(
        readers,
        "_registry",
        lambda *_: read_group(
            "registry", b"synthetic-r7" if stage else b"synthetic-r8"
        ),
    )
    monkeypatch.setattr(
        readers,
        "_descriptor",
        lambda *_: read_group(
            "descriptor",
            (
                b"synthetic-descriptor-before"
                if stage or bad_image != "after-descriptor"
                else b"synthetic-descriptor-after"
            ),
        ),
    )
    monkeypatch.setattr(
        readers, "_stage", lambda *_: read_group("stage", b"synthetic-r8")
    )


def _review(
    root: Path,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    revision: int = 7,
    intent: intents.PrivateTransactionIntent = _INTENT,
) -> exact.PrivateRecoveryExactRevisionReview:
    return exact.review_retained_private_recovery_exact_revision(
        step, revision, intent, root, root
    )


@pytest.mark.parametrize("platform", ["darwin", "freebsd", "plan9", "cygwin"])
def test_unsupported_without_native_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert _review(tmp_path).state is State.UNSUPPORTED
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", [None, "review", object(), 12])
def test_bad_step_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, step=cast(Step, bad)).state is State.INVALID_REQUEST
    assert not calls


@pytest.mark.parametrize("bad", [None, "7", 7.0, True, 0, -1, object()])
def test_bad_revision_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, revision=cast(int, bad)).state is State.INVALID_REQUEST
    assert not calls


@pytest.mark.parametrize("bad", [None, "intent", object(), 55])
def test_bad_intent_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert (
        _review(tmp_path, intent=cast(intents.PrivateTransactionIntent, bad)).state
        is State.INVALID_REQUEST
    )
    assert not calls


@pytest.mark.parametrize("bad", [None, object(), 5, "bad-root"])
def test_bad_root_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert (
        exact.review_retained_private_recovery_exact_revision(
            Step.REVIEW_PREPARED_RESTART, 7, _INTENT, cast(Path, bad), tmp_path
        ).state
        is State.INVALID_REQUEST
    )
    assert not calls


def test_exact_staged_before_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    review = _review(tmp_path)
    assert review.state is State.PREPARED_EXACT_REVIEW_REQUIRED
    assert calls.count("guard-enter") == 1 and calls.count("guard-exit") == 1
    assert (
        calls.count("journal")
        == calls.count("registry")
        == calls.count("descriptor")
        == calls.count("stage")
        == 2
    )
    assert calls[-1] == "guard-exit"
    assert not any(
        private in repr(review) for private in (TX, str(tmp_path), "synthetic-r")
    )
    assert not hasattr(review, "commit_token")
    assert not hasattr(review, "authorization")
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.IO_ERROR)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "step", [Step.REVIEW_DESCRIPTOR_COMPLETION, Step.REVIEW_JOURNAL_RETIREMENT]
)
def test_exact_after_state_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, stage=False, bad_image="after-descriptor")
    result = _review(tmp_path, step, 8)
    assert result.state is (
        State.JOURNAL_PENDING_EXACT_REVIEW_REQUIRED
        if step is Step.REVIEW_JOURNAL_RETIREMENT
        else State.IMAGE_MISMATCH_PRESERVE
    )
    assert calls.count("stage") == 0


def test_exact_descriptor_pending_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, stage=False)
    assert (
        _review(tmp_path, Step.REVIEW_DESCRIPTOR_COMPLETION, 8).state
        is State.DESCRIPTOR_PENDING_EXACT_REVIEW_REQUIRED
    )


@pytest.mark.parametrize(
    "stage,step,bad_revision",
    [
        (True, Step.REVIEW_PREPARED_RESTART, 8),
        (False, Step.REVIEW_DESCRIPTOR_COMPLETION, 7),
        (False, Step.REVIEW_JOURNAL_RETIREMENT, 7),
    ],
)
def test_stale_expected_revision_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stage: bool,
    step: Step,
    bad_revision: int,
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, stage=stage)
    assert (
        _review(tmp_path, step, bad_revision).state is State.REVISION_MISMATCH_REFUSED
    )
    assert not calls


@pytest.mark.parametrize(
    "name", ["journal", "registry", "descriptor", "stage", "missing"]
)
def test_bad_native_image_preserve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, bad_image=name)
    assert _review(tmp_path).state is State.IMAGE_MISMATCH_PRESERVE
    assert calls[-1] == "guard-exit"


def test_native_drift_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, drift_at=2)
    assert _review(tmp_path).state is State.IMAGE_DRIFT_PRESERVE
    assert calls.count("journal") == 2


@pytest.mark.parametrize("at", [1, 2, 3])
def test_inventory_refusal_all_checkpoints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, bad_inventory_at=at)
    assert _review(tmp_path).state is State.NAMESPACE_CHANGED_PRESERVE
    assert calls.count("journal") == at - 1


@pytest.mark.parametrize("at", [2, 3, 4])
def test_namespace_change_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, bad_namespace_at=at)
    assert _review(tmp_path).state is State.NAMESPACE_CHANGED_PRESERVE
    assert calls.count("journal") == at - 2


@pytest.mark.parametrize("at", [2, 3, 4])
def test_owner_change_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, changed_owner_at=at)
    assert _review(tmp_path).state is State.OWNER_CHANGED
    assert calls.count("journal") == at - 2


@pytest.mark.parametrize("at", [1, 2])
def test_io_failure_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, image_error_at=at)
    result = _review(tmp_path)
    assert result.state is State.IO_ERROR
    assert "private-data-secret" not in repr(result)
    assert calls[-1] == "guard-exit"


@pytest.mark.parametrize("at", [1, 2])
def test_interrupt_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, interrupt_at=at)
    assert _review(tmp_path).state is State.INTERRUPTED_PRESERVE
    assert calls[-1] == "guard-exit"


@pytest.mark.parametrize(
    "code,expected",
    [
        (retained.RetainedDescriptorGuardCode.OWNER_CHANGED, State.OWNER_CHANGED),
        (retained.RetainedDescriptorGuardCode.UNSUPPORTED, State.UNSUPPORTED),
        (retained.RetainedDescriptorGuardCode.REFUSED_PATH, State.GUARD_REFUSED),
    ],
)
def test_guard_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: retained.RetainedDescriptorGuardCode,
    expected: State,
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, guard_error=code)
    assert _review(tmp_path).state is expected
    assert calls.count("journal") == 0


def test_guard_postcondition_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, guard_exit_error=True)
    assert _review(tmp_path).state is State.GUARD_REFUSED


def test_initialize_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    initialized = _intent()
    object.__setattr__(
        initialized,
        "witness",
        SimpleNamespace(
            transaction_id=TX,
            operation=witness.PrivateBindingOperation.INITIALIZE,
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: initialized
    )
    assert _review(tmp_path, intent=initialized).state is State.INITIALIZATION_REFUSED
    assert not calls


def test_witness_revision_mismatch_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    altered = _intent()
    object.__setattr__(altered.witness, "registry_revision_before", 9)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: altered
    )
    assert _review(tmp_path, intent=altered).state is State.INVALID_REQUEST
    assert not calls


def test_proposal_revision_contract_refuses_forgery_before_native_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, revision_override=9)
    assert _review(tmp_path).state is State.INVALID_REQUEST
    assert not calls


def test_stage_state_mismatch_preserves_without_native_byte_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, stage=False)
    assert _review(tmp_path).state is State.IMAGE_MISMATCH_PRESERVE
    assert calls.count("journal") == 0
    assert calls[-1] == "guard-exit"


def test_system_exit_propagates_after_native_guard_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)

    def abort(*_args: object) -> object:
        raise SystemExit(33)

    monkeypatch.setattr(readers, "_journal", abort)
    with pytest.raises(SystemExit) as error:
        _review(tmp_path)
    assert error.value.code == 33
    assert calls[-1] == "guard-exit"


def test_no_notes_or_writer_api() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(exact, "commit_private_binding")
    assert not hasattr(exact, "retire_private_journal")
    assert not hasattr(exact, "open_notes")
