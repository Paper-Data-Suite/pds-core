"""Core #238 Slice 3G4 stage-absent native checkpoint synthetic regressions."""

from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_image_snapshot as desc_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal_image
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_stage_absence_checkpoint as checkpoint
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
A = "6fb32a62-83e2-43f6-9823-687801593c8b"
B = "d2f5733a-e471-4865-a070-e943ad20863f"
State = checkpoint.PrivateStageAbsenceCheckpointState


def _sha(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _intent(
    operation: witness.PrivateBindingOperation,
) -> intents.PrivateTransactionIntent:
    old = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner("posix_euid", "1000"),
            2,
            (metadata.PrivateRegistryBinding(A, 1, "/synthetic_a"),),
        )
    )
    old_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(A)
    )
    if operation is witness.PrivateBindingOperation.FORK_COPY:
        next_descriptor = metadata.encode_association_descriptor(
            metadata.PrivateAssociationDescriptor(B)
        )
        bindings: tuple[metadata.PrivateRegistryBinding, ...] = (
            metadata.PrivateRegistryBinding(A, 1, "/synthetic_a"),
            metadata.PrivateRegistryBinding(B, 1, "/synthetic_b"),
        )
        next_id = B
    elif operation is witness.PrivateBindingOperation.REBIND_MOVE:
        next_descriptor = old_descriptor
        bindings = (metadata.PrivateRegistryBinding(A, 2, "/synthetic_b"),)
        next_id = A
    else:
        raise ValueError("Use only existing-binding operations in this fixture.")
    new = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner("posix_euid", "1000"), 3, bindings
        )
    )
    event = witness.PrivateTransactionWitness(
        operation,
        TX,
        A,
        next_id,
        2,
        3,
        _sha(old_descriptor),
        _sha(next_descriptor) or "",
        _sha(old),
        _sha(new) or "",
    )
    return intents.PrivateTransactionIntent(
        event, old_descriptor, next_descriptor, old, new
    )


def _roots(tmp_path: Path, *, stage: bool = False) -> tuple[Path, Path]:
    private = tmp_path / "private"
    private.mkdir()
    (private / "transactions").mkdir()
    (private / "transactions" / (TX + ".json")).write_bytes(b"synthetic")
    if stage:
        (private / ("." + TX + ".registry-stage")).write_bytes(b"synthetic")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return private, workspace


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    proposed: intents.PrivateTransactionIntent,
    events: list[str],
    *,
    registry: bytes | None = None,
    descriptor_image: bytes | None = None,
    change: str = "",
    inventory_state: inventory.PrivateRegistryStageInventoryState = inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,
    guard_error: retained.RetainedDescriptorGuardCode | None = None,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def guard(_root: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        yield
        if guard_error is not None:
            raise retained.RetainedDescriptorGuardError(guard_error)
        events.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")

    def read_owner() -> inspection.EffectiveOSOwner:
        events.append("owner")
        return (
            inspection.EffectiveOSOwner("posix_euid", "1001")
            if change == "owner" and events.count("owner") > 1
            else owner
        )

    monkeypatch.setattr(ordered, "_owner", read_owner)
    counts = {"journal": 0, "registry": 0, "descriptor": 0, "inventory": 0}

    def pick(kind: str, raw: bytes) -> bytes:
        counts[kind] += 1
        events.append(kind)
        if change == kind and counts[kind] == 2:
            return raw + b"modified"
        return raw

    def read_journal(*_unused: object) -> journal_image.PrivateJournalImageReview:
        return journal_image.PrivateJournalImageReview(
            journal_image.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            pick("journal", intents.encode_private_transaction_intent(proposed)),
        )

    def read_registry(*_unused: object) -> registry_image.PrivateRegistryImageReview:
        assert registry is not None
        return registry_image.PrivateRegistryImageReview(
            registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            pick("registry", registry),
        )

    def read_descriptor(*_unused: object) -> desc_image.PrivateDescriptorImageReview:
        assert descriptor_image is not None
        return desc_image.PrivateDescriptorImageReview(
            desc_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            pick("descriptor", descriptor_image),
        )

    def check_inventory(
        *_unused: object,
    ) -> inventory.PrivateRegistryStageInventoryState:
        counts["inventory"] += 1
        events.append("inventory")
        if change == "inventory" and counts["inventory"] == 2:
            return inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
        return inventory_state

    monkeypatch.setattr(readers, "_journal", read_journal)
    monkeypatch.setattr(readers, "_registry", read_registry)
    monkeypatch.setattr(readers, "_descriptor", read_descriptor)
    monkeypatch.setattr(readers, "_inventory", check_inventory)


def _review(
    proposed: intents.PrivateTransactionIntent, roots: tuple[Path, Path]
) -> checkpoint.PrivateStageAbsenceCheckpointReview:
    return checkpoint.review_native_private_stage_absence(proposed, roots[0], roots[1])


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize(
    ("op", "after_descriptor", "expected"),
    [
        (
            witness.PrivateBindingOperation.FORK_COPY,
            False,
            State.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        ),
        (
            witness.PrivateBindingOperation.FORK_COPY,
            True,
            State.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED,
        ),
        (
            witness.PrivateBindingOperation.REBIND_MOVE,
            False,
            State.BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED,
        ),
    ],
)
def test_stage_absent_after_registry_is_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    op: witness.PrivateBindingOperation,
    after_descriptor: bool,
    expected: State,
) -> None:
    proposed = _intent(op)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=(
            proposed.descriptor_after
            if after_descriptor
            else proposed.descriptor_before
        ),
    )
    monkeypatch.setattr(sys, "platform", platform)
    result = _review(proposed, roots)
    assert result.state is expected
    assert events[0] == "guard-enter" and events[-1] == "guard-exit"
    assert events.count("journal") == 2 and events.count("registry") == 2
    assert events.count("descriptor") == 2 and events.count("inventory") == 2
    assert "handle" not in result.__dataclass_fields__
    for value in (TX, str(roots[0]), "1000", "/synthetic_a"):
        assert value not in repr(result) and value not in result.message


@pytest.mark.parametrize(
    ("after_descriptor", "expected"),
    [
        (False, State.STAGE_MISSING_BEFORE_REFUSED),
        (True, State.STAGE_MISSING_PARTIAL_REFUSED),
    ],
)
def test_missing_stage_before_registry_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_descriptor: bool,
    expected: State,
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_before,
        descriptor_image=(
            proposed.descriptor_after
            if after_descriptor
            else proposed.descriptor_before
        ),
    )
    assert _review(proposed, roots).state is expected


@pytest.mark.parametrize(
    "extra",
    ["stage", "second-journal", "fake-stage", "missing-journal", "missing-directory"],
)
def test_competing_or_missing_names_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra: str,
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    private = roots[0]
    if extra == "stage":
        (private / ("." + TX + ".registry-stage")).write_text("synthetic")
    elif extra == "second-journal":
        (private / "transactions" / "other.json").write_text("synthetic")
    elif extra == "fake-stage":
        (private / "weird-registry-stage.tmp").write_text("synthetic")
    elif extra == "missing-journal":
        (private / "transactions" / (TX + ".json")).unlink()
    else:
        (private / "transactions" / (TX + ".json")).unlink()
        (private / "transactions").rmdir()
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=proposed.descriptor_before,
    )
    assert _review(proposed, roots).state is State.NAMESPACE_UNQUALIFIED
    assert "journal" not in events


@pytest.mark.parametrize("change", ["journal", "registry", "descriptor"])
def test_native_byte_drift_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=proposed.descriptor_before,
        change=change,
    )
    assert _review(proposed, roots).state is State.NATIVE_IMAGE_UNQUALIFIED


def test_inventory_change_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=proposed.descriptor_before,
        change="inventory",
    )
    assert _review(proposed, roots).state is State.NAMESPACE_UNQUALIFIED


@pytest.mark.parametrize(
    "error_code",
    [
        retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
        retained.RetainedDescriptorGuardCode.UNSUPPORTED,
    ],
)
def test_guard_exit_failure_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_code: retained.RetainedDescriptorGuardCode,
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=proposed.descriptor_before,
        guard_error=error_code,
    )
    expected = (
        State.OWNER_CHANGED
        if error_code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED
        else State.UNSUPPORTED
        if error_code is retained.RetainedDescriptorGuardCode.UNSUPPORTED
        else State.GUARD_REFUSED
    )
    assert _review(proposed, roots).state is expected


def test_owner_changed_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=proposed.descriptor_before,
        change="owner",
    )
    assert _review(proposed, roots).state is State.OWNER_CHANGED


def test_foreign_metadata_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=b"synthetic-foreign-registry",
        descriptor_image=proposed.descriptor_before,
    )
    assert _review(proposed, roots).state is State.CHECKPOINT_REFUSED


def test_invalid_request_and_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=proposed.descriptor_before,
    )
    assert (
        checkpoint.review_native_private_stage_absence(
            cast(intents.PrivateTransactionIntent, object()), *roots
        ).state
        is State.INVALID_REQUEST
    )
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _review(proposed, roots).state is State.UNSUPPORTED


def test_no_mutation_or_notes_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposed = _intent(witness.PrivateBindingOperation.FORK_COPY)
    roots = _roots(tmp_path)
    events: list[str] = []
    _setup(
        monkeypatch,
        proposed,
        events,
        registry=proposed.registry_after,
        descriptor_image=proposed.descriptor_before,
    )
    before = set(roots[0].rglob("*"))
    result = _review(proposed, roots)
    assert result.state is State.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED
    assert set(roots[0].rglob("*")) == before
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.CHECKPOINT_REFUSED)
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for attribute in ("commit_token", "path", "handle", "authorize", "retire_journal"):
        assert not hasattr(result, attribute)
        assert not hasattr(checkpoint, attribute)
