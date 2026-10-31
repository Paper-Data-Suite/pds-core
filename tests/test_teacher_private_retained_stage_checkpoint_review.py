"""Core #238 3F5: non-authorizing joint journal/live/stage native review."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_crash_checkpoint as checkpoint
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_image_snapshot as stage_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as review
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
JOURNAL = b"synthetic journal"
REGISTRY = b"synthetic registry before"
DESCRIPTOR = b"synthetic descriptor before"
STAGE = b"synthetic registry after"


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _proposal() -> intents.PrivateTransactionIntent:
    action = object.__new__(witness.PrivateTransactionWitness)
    for name, value in {
        "operation": witness.PrivateBindingOperation.FORK_COPY,
        "transaction_id": TX,
        "association_before": "6fb32a62-83e2-43f6-9823-687801593c8b",
        "association_after": "e3c6f36c-2a12-4420-96ce-1f137a312c18",
        "registry_revision_before": 1,
        "registry_revision_after": 2,
        "descriptor_sha256_before": "a" * 64,
        "descriptor_sha256_after": "b" * 64,
        "registry_sha256_before": "c" * 64,
        "registry_sha256_after": "d" * 64,
    }.items():
        object.__setattr__(action, name, value)
    proposed = object.__new__(intents.PrivateTransactionIntent)
    for name, value in {
        "witness": action,
        "registry_before": REGISTRY,
        "registry_after": STAGE,
        "descriptor_before": DESCRIPTOR,
        "descriptor_after": b"synthetic descriptor after",
    }.items():
        object.__setattr__(proposed, name, value)
    return proposed


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    scan: inventory.PrivateRegistryStageInventoryState = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED,
    scan_second: inventory.PrivateRegistryStageInventoryState | None = None,
    journal_state: journal.PrivateJournalImageState = journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
    registry_state: registry_image.PrivateRegistryImageState = registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
    descriptor_state: descriptor_image.PrivateDescriptorImageState = descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
    stage_state: stage_image.PrivateRegistryStageImageState = stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED,
    changed: str = "",
    stage_data: bytes = STAGE,
    checkpoint_state: checkpoint.PrivateJournalCrashCheckpointState = checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
    guard_enter: retained.RetainedDescriptorGuardCode | None = None,
    guard_exit: retained.RetainedDescriptorGuardCode | None = None,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda _: JOURNAL)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: _proposal()
    )

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
    reads: dict[str, int] = {
        key: 0 for key in ("inventory", "journal", "registry", "descriptor", "stage")
    }
    count = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal count
        count += 1
        events.append("owner")
        result = _owner()
        if changed == "owner" and count == 2:
            return inspection.EffectiveOSOwner(result.kind, "different")
        return result

    def data(key: str, raw: bytes) -> bytes:
        reads[key] += 1
        events.append(key)
        return raw + b"x" if changed == key and reads[key] == 2 else raw

    def scan_fn(
        _root: Path, actor: inspection.EffectiveOSOwner
    ) -> inventory.PrivateRegistryStageInventoryState:
        assert actor == _owner()
        data("inventory", b"")
        return (
            scan_second if scan_second is not None and reads["inventory"] == 2 else scan
        )

    def journal_fn(
        _root: Path, tx: str, actor: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        assert tx == TX and actor == _owner()
        return journal.PrivateJournalImageReview(
            journal_state,
            "synthetic",
            data("journal", JOURNAL)
            if journal_state
            is journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
            else None,
        )

    def registry_fn(
        _root: Path, actor: inspection.EffectiveOSOwner
    ) -> registry_image.PrivateRegistryImageReview:
        assert actor == _owner()
        return registry_image.PrivateRegistryImageReview(
            registry_state,
            "synthetic",
            data("registry", REGISTRY)
            if registry_state
            is registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
            else None,
        )

    def descriptor_fn(_root: Path) -> descriptor_image.PrivateDescriptorImageReview:
        return descriptor_image.PrivateDescriptorImageReview(
            descriptor_state,
            "synthetic",
            data("descriptor", DESCRIPTOR)
            if descriptor_state
            is descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
            else None,
        )

    def stage_fn(
        _root: Path, tx: str, actor: inspection.EffectiveOSOwner
    ) -> stage_image.PrivateRegistryStageImageReview:
        assert tx == TX and actor == _owner()
        return stage_image.PrivateRegistryStageImageReview(
            stage_state,
            "synthetic",
            data("stage", stage_data)
            if stage_state
            is stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
            else None,
        )

    def classify(
        _proposed: intents.PrivateTransactionIntent,
        *,
        observed_journal: bytes | None,
        observed_registry: bytes | None,
        observed_descriptor: bytes | None,
    ) -> checkpoint.PrivateJournalCrashCheckpointReview:
        events.append("checkpoint")
        assert (observed_journal, observed_registry, observed_descriptor) == (
            JOURNAL,
            REGISTRY,
            DESCRIPTOR,
        )
        return checkpoint.PrivateJournalCrashCheckpointReview(
            checkpoint_state, "synthetic"
        )

    monkeypatch.setattr(ordered, "_owner", owner)
    monkeypatch.setattr(review, "_inventory", scan_fn)
    monkeypatch.setattr(review, "_journal", journal_fn)
    monkeypatch.setattr(review, "_registry", registry_fn)
    monkeypatch.setattr(review, "_descriptor", descriptor_fn)
    monkeypatch.setattr(review, "_stage", stage_fn)
    monkeypatch.setattr(
        checkpoint, "classify_private_journal_crash_checkpoint", classify
    )


def _call(tmp_path: Path) -> review.PrivateRetainedStageCheckpointReview:
    return review.review_retained_registry_stage_checkpoint(
        _proposal(), tmp_path / "private", tmp_path / "workspace"
    )


def test_symmetric_native_observation_is_non_authorizing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    result = _call(tmp_path)
    assert (
        result.state
        is review.PrivateRetainedStageCheckpointState.MATCHING_BEFORE_STAGE_REVIEW_REQUIRED
    )
    assert events == [
        "guard-enter",
        "owner",
        "inventory",
        "journal",
        "registry",
        "descriptor",
        "stage",
        "stage",
        "descriptor",
        "registry",
        "journal",
        "inventory",
        "owner",
        "checkpoint",
        "guard-exit",
    ]
    assert list(tmp_path.iterdir()) == []
    assert not hasattr(result, "image") and not hasattr(result, "write_handle")
    for forbidden in (TX, str(tmp_path), JOURNAL.decode(), _owner().value):
        assert forbidden not in repr(result) and forbidden not in result.message


@pytest.mark.parametrize(
    ("classified", "expected"),
    [
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
            review.PrivateRetainedStageCheckpointState.MATCHING_BEFORE_STAGE_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
            review.PrivateRetainedStageCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED,
            review.PrivateRetainedStageCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
            review.PrivateRetainedStageCheckpointState.OTHER_CHECKPOINT_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.FOREIGN_METADATA_REFUSED,
            review.PrivateRetainedStageCheckpointState.CHECKPOINT_REFUSED,
        ),
    ],
)
def test_checkpoint_states_remain_review_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    classified: checkpoint.PrivateJournalCrashCheckpointState,
    expected: review.PrivateRetainedStageCheckpointState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, checkpoint_state=classified)
    assert _call(tmp_path).state is expected


@pytest.mark.parametrize("change", ["journal", "registry", "descriptor", "stage"])
def test_changed_native_image_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, changed=change)
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedStageCheckpointState.IMAGES_CHANGED
    )
    assert "checkpoint" not in events


def test_wrong_stage_after_bytes_refused_before_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, stage_data=STAGE + b"foreign")
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedStageCheckpointState.STAGE_MISMATCH
    )
    assert "checkpoint" not in events


@pytest.mark.parametrize(
    ("kind", "code", "expected"),
    [
        (
            "journal",
            journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED,
            review.PrivateRetainedStageCheckpointState.JOURNAL_UNQUALIFIED,
        ),
        (
            "journal",
            journal.PrivateJournalImageState.OWNER_CHANGED,
            review.PrivateRetainedStageCheckpointState.OWNER_CHANGED,
        ),
        (
            "registry",
            registry_image.PrivateRegistryImageState.INVALID_REGISTRY,
            review.PrivateRetainedStageCheckpointState.REGISTRY_UNQUALIFIED,
        ),
        (
            "registry",
            registry_image.PrivateRegistryImageState.OWNER_UNAVAILABLE,
            review.PrivateRetainedStageCheckpointState.OWNER_UNAVAILABLE,
        ),
        (
            "descriptor",
            descriptor_image.PrivateDescriptorImageState.INVALID_DESCRIPTOR,
            review.PrivateRetainedStageCheckpointState.DESCRIPTOR_UNQUALIFIED,
        ),
        (
            "stage",
            stage_image.PrivateRegistryStageImageState.MISSING,
            review.PrivateRetainedStageCheckpointState.STAGE_UNQUALIFIED,
        ),
        (
            "stage",
            stage_image.PrivateRegistryStageImageState.OWNER_CHANGED,
            review.PrivateRetainedStageCheckpointState.OWNER_CHANGED,
        ),
    ],
)
def test_failed_native_read_stops_without_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    code: object,
    expected: review.PrivateRetainedStageCheckpointState,
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        journal_state=cast(journal.PrivateJournalImageState, code)
        if kind == "journal"
        else journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
        registry_state=cast(registry_image.PrivateRegistryImageState, code)
        if kind == "registry"
        else registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
        descriptor_state=cast(descriptor_image.PrivateDescriptorImageState, code)
        if kind == "descriptor"
        else descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
        stage_state=cast(stage_image.PrivateRegistryStageImageState, code)
        if kind == "stage"
        else stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED,
    )
    assert _call(tmp_path).state is expected
    assert "checkpoint" not in events
    assert events[-1] == "guard-exit"


@pytest.mark.parametrize(
    "scan",
    [
        inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,
        inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        inventory.PrivateRegistryStageInventoryState.ENTRIES_CHANGED,
    ],
)
def test_first_inventory_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scan: inventory.PrivateRegistryStageInventoryState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, scan=scan)
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedStageCheckpointState.STAGE_INVENTORY_UNQUALIFIED
    )
    assert events == ["guard-enter", "owner", "inventory", "guard-exit"]


def test_last_inventory_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        scan_second=inventory.PrivateRegistryStageInventoryState.ENTRIES_CHANGED,
    )
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedStageCheckpointState.STAGE_INVENTORY_UNQUALIFIED
    )
    assert "checkpoint" not in events


def test_owner_drift_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, changed="owner")
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedStageCheckpointState.OWNER_CHANGED
    )
    assert "checkpoint" not in events


@pytest.mark.parametrize(
    "code",
    [
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
        retained.RetainedDescriptorGuardCode.UNSUPPORTED,
        retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
    ],
)
def test_guard_exit_overrides_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: retained.RetainedDescriptorGuardCode,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, guard_exit=code)
    expected = review._guard_failure(code)
    assert _call(tmp_path).state is expected
    assert events[-1] == "guard-exit"


def test_guard_entry_prevents_all_reads(
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
        is review.PrivateRetainedStageCheckpointState.GUARD_REFUSED
    )
    assert events == ["guard-enter"]


def test_reject_initialization_and_wrong_input_before_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    proposed = _proposal()
    object.__setattr__(
        proposed.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: proposed
    )
    assert (
        review.review_retained_registry_stage_checkpoint(
            proposed, tmp_path, tmp_path
        ).state
        is review.PrivateRetainedStageCheckpointState.INITIALIZATION_REFUSED
    )
    assert (
        review.review_retained_registry_stage_checkpoint(
            cast(intents.PrivateTransactionIntent, "invalid"), tmp_path, tmp_path
        ).state
        is review.PrivateRetainedStageCheckpointState.INVALID_REQUEST
    )
    assert events == []


def test_unsupported_platform_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        _call(tmp_path).state is review.PrivateRetainedStageCheckpointState.UNSUPPORTED
    )
    assert events == []


def test_capabilities_unchanged() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(review, "commit_private_binding")
    assert not hasattr(review, "admit_durable_transaction")
    assert not hasattr(review, "replace_private_registry")
    assert not hasattr(review, "create_notes_record")
