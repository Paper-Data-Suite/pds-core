"""Core #238 3G2: exclusive read-only pair checkpoint, synthetic native reads."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as review
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_crash_checkpoint as checkpoint
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_image_snapshot as stage_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as stage_review
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
JOURNAL = b"synthetic-intent"
REGISTRY = b"synthetic-before"
DESCRIPTOR = b"synthetic-descriptor"
STAGE = b"synthetic-after"
State = review.PrivateExclusivePairCheckpointState


def _intent() -> intents.PrivateTransactionIntent:
    candidate = object.__new__(intents.PrivateTransactionIntent)
    op = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(op, "operation", witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(op, "transaction_id", TX)
    object.__setattr__(candidate, "witness", op)
    object.__setattr__(candidate, "registry_before", REGISTRY)
    object.__setattr__(candidate, "registry_after", STAGE)
    object.__setattr__(candidate, "descriptor_before", DESCRIPTOR)
    return candidate


def _owner() -> inspection.EffectiveOSOwner:
    return inspection.EffectiveOSOwner("windows_token_sid", "synthetic-owner")


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "private"
    private.mkdir()
    (private / "transactions").mkdir()
    (private / "transactions" / (TX + ".json")).write_bytes(JOURNAL)
    (private / ("." + TX + ".registry-stage")).write_bytes(STAGE)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return private, workspace


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    proposed: intents.PrivateTransactionIntent,
    events: list[str],
    *,
    stage_data: bytes = STAGE,
    journal_data: bytes = JOURNAL,
    owner_changes: bool = False,
    wrong_image: str = "",
    inventory_state: inventory.PrivateRegistryStageInventoryState = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED,
    classified: checkpoint.PrivateJournalCrashCheckpointState = checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
    guard_exit: retained.RetainedDescriptorGuardCode | None = None,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda _: JOURNAL)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: proposed
    )

    @contextmanager
    def guard(_private: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        yield
        if guard_exit is not None:
            raise retained.RetainedDescriptorGuardError(guard_exit)
        events.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)
    count = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal count
        count += 1
        events.append("owner")
        if owner_changes and count > 1:
            return inspection.EffectiveOSOwner("windows_token_sid", "different")
        return _owner()

    monkeypatch.setattr(ordered, "_owner", owner)
    counts = {kind: 0 for kind in ("journal", "registry", "descriptor", "stage")}

    def payload(kind: str, raw: bytes) -> bytes:
        counts[kind] += 1
        events.append(kind)
        if wrong_image == kind and counts[kind] == 2:
            return raw + b"unexpected"
        return raw

    monkeypatch.setattr(stage_review, "_inventory", lambda *_: inventory_state)

    def read_journal(*_args: object) -> journal.PrivateJournalImageReview:
        return journal.PrivateJournalImageReview(
            journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            payload("journal", journal_data),
        )

    def read_registry(*_args: object) -> registry_image.PrivateRegistryImageReview:
        return registry_image.PrivateRegistryImageReview(
            registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            payload("registry", REGISTRY),
        )

    def read_descriptor(
        *_args: object,
    ) -> descriptor_image.PrivateDescriptorImageReview:
        return descriptor_image.PrivateDescriptorImageReview(
            descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            payload("descriptor", DESCRIPTOR),
        )

    def read_stage(*_args: object) -> stage_image.PrivateRegistryStageImageReview:
        return stage_image.PrivateRegistryStageImageReview(
            stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED,
            "synthetic",
            payload("stage", stage_data),
        )

    monkeypatch.setattr(stage_review, "_journal", read_journal)
    monkeypatch.setattr(stage_review, "_registry", read_registry)
    monkeypatch.setattr(stage_review, "_descriptor", read_descriptor)
    monkeypatch.setattr(stage_review, "_stage", read_stage)

    def classify(
        *_args: object, **_kwargs: object
    ) -> checkpoint.PrivateJournalCrashCheckpointReview:
        events.append("classify")
        return checkpoint.PrivateJournalCrashCheckpointReview(classified, "synthetic")

    monkeypatch.setattr(
        checkpoint, "classify_private_journal_crash_checkpoint", classify
    )


def _call(
    proposed: intents.PrivateTransactionIntent, roots: tuple[Path, Path]
) -> review.PrivateExclusivePairCheckpointReview:
    return review.review_exclusive_prepared_private_pair(proposed, roots[0], roots[1])


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_matching_pair_review_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposed, events)
    monkeypatch.setattr(sys, "platform", platform)
    result = _call(proposed, roots)
    assert result.state is State.MATCHING_BEFORE_REVIEW_REQUIRED
    assert events[0] == "guard-enter" and events[-1] == "guard-exit"
    assert events.count("journal") == 2
    assert events.count("stage") == 2
    assert events.count("classify") == 1
    assert not hasattr(result, "commit_token") and not hasattr(result, "file_path")
    for forbidden in (TX, str(roots[0]), JOURNAL.decode(), _owner().value):
        assert forbidden not in repr(result) and forbidden not in result.message


@pytest.mark.parametrize(
    "extra",
    [
        "second_journal",
        "other_stage",
        "marker_collision",
        "missing_journal",
        "missing_stage",
    ],
)
def test_exact_namespace_refuses_competing_or_missing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: str
) -> None:
    roots = _roots(tmp_path)
    private = roots[0]
    if extra == "second_journal":
        (private / "transactions" / "foreign.json").write_text("synthetic")
    elif extra == "other_stage":
        (private / ".abcd.registry-stage").write_text("synthetic")
    elif extra == "marker_collision":
        (private / "fake-registry-stage.tmp").write_text("synthetic")
    elif extra == "missing_journal":
        (private / "transactions" / (TX + ".json")).unlink()
    else:
        (private / ("." + TX + ".registry-stage")).unlink()
    proposed = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposed, events)
    assert _call(proposed, roots).state is State.NAMESPACE_UNQUALIFIED
    assert "classify" not in events
    assert (private / "transactions").exists()


@pytest.mark.parametrize("change", ["journal", "registry", "descriptor", "stage"])
def test_native_image_drift_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposed, events, wrong_image=change)
    assert _call(proposed, roots).state is State.NATIVE_IMAGE_UNQUALIFIED
    assert "classify" not in events


@pytest.mark.parametrize("kind", ["journal", "stage"])
def test_exact_byte_mismatch_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(
        monkeypatch,
        proposed,
        events,
        journal_data=b"foreign" if kind == "journal" else JOURNAL,
        stage_data=b"foreign" if kind == "stage" else STAGE,
    )
    assert _call(proposed, roots).state is State.CHECKPOINT_REFUSED
    assert "classify" not in events


@pytest.mark.parametrize(
    "checkpoint_state",
    [
        checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
        checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED,
        checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
    ],
)
def test_other_metadata_checkpoints_still_review_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkpoint_state: checkpoint.PrivateJournalCrashCheckpointState,
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposed, events, classified=checkpoint_state)
    assert _call(proposed, roots).state is State.OTHER_CHECKPOINT_REVIEW_REQUIRED


def test_guard_exit_overrides_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(
        monkeypatch,
        proposed,
        events,
        guard_exit=retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
    )
    assert _call(proposed, roots).state is State.GUARD_REFUSED


def test_owner_change_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposed, events, owner_changes=True)
    assert _call(proposed, roots).state is State.OWNER_CHANGED


def test_unqualified_stage_inventory_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(
        monkeypatch,
        proposed,
        events,
        inventory_state=inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
    )
    assert _call(proposed, roots).state is State.NAMESPACE_UNQUALIFIED


def test_mutation_between_censuses_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposed, events)
    scan = review._census
    calls = 0

    def changed(root: Path, tx: str) -> tuple[frozenset[str], frozenset[str]]:
        nonlocal calls
        calls += 1
        if calls == 2:
            (root / "new-entry").write_bytes(b"synthetic")
        return scan(root, tx)

    monkeypatch.setattr(review, "_census", changed)
    assert _call(proposed, roots).state is State.NAMESPACE_UNQUALIFIED


def test_initialization_invalid_and_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _roots(tmp_path)
    proposed = _intent()
    events: list[str] = []
    _configure(monkeypatch, proposed, events)
    object.__setattr__(
        proposed.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    assert _call(proposed, roots).state is State.INITIALIZATION_REFUSED
    assert (
        review.review_exclusive_prepared_private_pair(
            cast(intents.PrivateTransactionIntent, object()), roots[0], roots[1]
        ).state
        is State.INVALID_REQUEST
    )
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _call(proposed, roots).state is State.UNSUPPORTED
    assert events == []


def test_negative_capability_and_read_only_import() -> None:
    caps = get_teacher_experience_capabilities()
    assert "notes.records.v1" not in caps
    assert "notes.menu.v1" not in caps
    assert "notes.cli.v1" not in caps
    assert not hasattr(review, "create_private_notes")
