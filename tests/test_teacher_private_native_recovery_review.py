"""#238 3E8: exact native journal and both metadata images under one guard."""

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
from pds_core import _teacher_private_native_recovery_review as review
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
JOURNAL = b"synthetic journal bytes"
REGISTRY = b"synthetic registry bytes"
DESCRIPTOR = b"synthetic descriptor bytes"


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _intent() -> intents.PrivateTransactionIntent:
    proposed = object.__new__(intents.PrivateTransactionIntent)
    action = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(action, "operation", witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(action, "transaction_id", TX)
    object.__setattr__(proposed, "witness", action)
    return proposed


def _fake(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    failure_at: str = "",
    changed_at: str = "",
    owner_changed: bool = False,
    guard_enter: retained.RetainedDescriptorGuardCode | None = None,
    guard_exit: retained.RetainedDescriptorGuardCode | None = None,
    triage: checkpoint.PrivateJournalCrashCheckpointState = checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

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
    owner_calls = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal owner_calls
        owner_calls += 1
        events.append("owner")
        if owner_changed and owner_calls == 2:
            old = _owner()
            return inspection.EffectiveOSOwner(
                old.kind, "2000" if old.kind == "posix_euid" else "S-1-5-21-99-22-33-44"
            )
        return _owner()

    monkeypatch.setattr(ordered, "_owner", owner)
    visits = {"journal": 0, "registry": 0, "descriptor": 0}

    def j(
        _dir: Path, tx: str, current: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        assert tx == TX and current == _owner()
        visits["journal"] += 1
        key = "journal" + str(visits["journal"])
        events.append(key)
        if failure_at == key:
            return journal.PrivateJournalImageReview(
                journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED, "synthetic"
            )
        return journal.PrivateJournalImageReview(
            journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            JOURNAL + b"changed" if changed_at == key else JOURNAL,
        )

    def r(
        _root: Path, current: inspection.EffectiveOSOwner
    ) -> registry_image.PrivateRegistryImageReview:
        assert current == _owner()
        visits["registry"] += 1
        key = "registry" + str(visits["registry"])
        events.append(key)
        if failure_at == key:
            return registry_image.PrivateRegistryImageReview(
                registry_image.PrivateRegistryImageState.INVALID_REGISTRY, "synthetic"
            )
        return registry_image.PrivateRegistryImageReview(
            registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            REGISTRY + b"changed" if changed_at == key else REGISTRY,
        )

    def d(_root: Path) -> descriptor_image.PrivateDescriptorImageReview:
        visits["descriptor"] += 1
        key = "descriptor" + str(visits["descriptor"])
        events.append(key)
        if failure_at == key:
            return descriptor_image.PrivateDescriptorImageReview(
                descriptor_image.PrivateDescriptorImageState.REFUSED_PATH, "synthetic"
            )
        return descriptor_image.PrivateDescriptorImageReview(
            descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            DESCRIPTOR + b"changed" if changed_at == key else DESCRIPTOR,
        )

    monkeypatch.setattr(review, "_journal", j)
    monkeypatch.setattr(review, "_registry", r)
    monkeypatch.setattr(review, "_descriptor", d)

    def classify(
        _proposed: intents.PrivateTransactionIntent,
        *,
        observed_journal: bytes | None,
        observed_registry: bytes | None,
        observed_descriptor: bytes | None,
    ) -> checkpoint.PrivateJournalCrashCheckpointReview:
        assert (observed_journal, observed_registry, observed_descriptor) == (
            JOURNAL,
            REGISTRY,
            DESCRIPTOR,
        )
        events.append("checkpoint")
        return checkpoint.PrivateJournalCrashCheckpointReview(triage, "synthetic")

    monkeypatch.setattr(
        checkpoint, "classify_private_journal_crash_checkpoint", classify
    )


def _run(tmp_path: Path) -> review.PrivateNativeRecoveryReview:
    return review.review_native_private_recovery_images(
        _intent(), tmp_path / "private", tmp_path / "workspace"
    )


@pytest.mark.parametrize(
    ("triage", "expected"),
    [
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
            review.PrivateNativeRecoveryReviewState.JOURNALED_BEFORE_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
            review.PrivateNativeRecoveryReviewState.JOURNALED_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED,
            review.PrivateNativeRecoveryReviewState.JOURNALED_REGISTRY_ONLY_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
            review.PrivateNativeRecoveryReviewState.JOURNALED_AFTER_REVIEW_REQUIRED,
        ),
    ],
)
def test_single_guard_exact_image_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    triage: checkpoint.PrivateJournalCrashCheckpointState,
    expected: review.PrivateNativeRecoveryReviewState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, triage=triage)
    result = _run(tmp_path)
    assert result.state is expected
    assert events == [
        "guard-enter",
        "owner",
        "journal1",
        "registry1",
        "descriptor1",
        "descriptor2",
        "registry2",
        "journal2",
        "owner",
        "checkpoint",
        "guard-exit",
    ]
    assert not tmp_path.exists() or not list(tmp_path.iterdir())
    for secret in (TX, _owner().value, "synthetic journal", str(tmp_path)):
        assert secret not in repr(result) and secret not in result.message


@pytest.mark.parametrize(
    ("failure_at", "expected"),
    [
        ("journal1", review.PrivateNativeRecoveryReviewState.JOURNAL_MISSING),
        ("registry1", review.PrivateNativeRecoveryReviewState.REGISTRY_UNQUALIFIED),
        ("descriptor1", review.PrivateNativeRecoveryReviewState.DESCRIPTOR_UNQUALIFIED),
        ("descriptor2", review.PrivateNativeRecoveryReviewState.DESCRIPTOR_UNQUALIFIED),
        ("registry2", review.PrivateNativeRecoveryReviewState.REGISTRY_UNQUALIFIED),
        ("journal2", review.PrivateNativeRecoveryReviewState.JOURNAL_MISSING),
    ],
)
def test_failed_native_image_read_never_classifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_at: str,
    expected: review.PrivateNativeRecoveryReviewState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, failure_at=failure_at)
    assert _run(tmp_path).state is expected
    assert "checkpoint" not in events
    assert events[-1] == "guard-exit"


@pytest.mark.parametrize("changed_at", ["journal2", "registry2", "descriptor2"])
def test_changed_native_bytes_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_at: str
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, changed_at=changed_at)
    assert (
        _run(tmp_path).state is review.PrivateNativeRecoveryReviewState.IMAGES_CHANGED
    )
    assert "checkpoint" not in events


@pytest.mark.parametrize(
    "triage",
    [
        checkpoint.PrivateJournalCrashCheckpointState.FOREIGN_METADATA_REFUSED,
        checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_IMAGE_REFUSED,
        checkpoint.PrivateJournalCrashCheckpointState.INTENT_REFUSED,
        checkpoint.PrivateJournalCrashCheckpointState.UNJOURNALED_AFTER_REFUSED,
    ],
)
def test_invalid_checkpoint_cannot_be_promoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    triage: checkpoint.PrivateJournalCrashCheckpointState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, triage=triage)
    assert (
        _run(tmp_path).state
        is review.PrivateNativeRecoveryReviewState.CHECKPOINT_REFUSED
    )


def test_owner_drift_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, owner_changed=True)
    assert _run(tmp_path).state is review.PrivateNativeRecoveryReviewState.OWNER_CHANGED
    assert "checkpoint" not in events


@pytest.mark.parametrize(
    "guard_code",
    [
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
        retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE,
        retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
    ],
)
def test_guard_exit_refusal_overrides_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    guard_code: retained.RetainedDescriptorGuardCode,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, guard_exit=guard_code)
    state = _run(tmp_path).state
    assert state is (
        review.PrivateNativeRecoveryReviewState.OWNER_CHANGED
        if guard_code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED
        else review.PrivateNativeRecoveryReviewState.OWNER_UNAVAILABLE
        if guard_code is retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE
        else review.PrivateNativeRecoveryReviewState.GUARD_REFUSED
    )
    assert "checkpoint" in events


def test_bad_guard_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _fake(
        monkeypatch,
        events,
        guard_enter=retained.RetainedDescriptorGuardCode.REFUSED_PATH,
    )
    assert _run(tmp_path).state is review.PrivateNativeRecoveryReviewState.GUARD_REFUSED
    assert events == ["guard-enter"]


def test_no_initialize_or_wrong_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events)
    assert (
        review.review_native_private_recovery_images(
            cast(intents.PrivateTransactionIntent, "invalid"),
            tmp_path / "private",
            tmp_path / "workspace",
        ).state
        is review.PrivateNativeRecoveryReviewState.INVALID_REQUEST
    )
    proposed = _intent()
    object.__setattr__(
        proposed.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    assert (
        review.review_native_private_recovery_images(
            proposed, tmp_path / "private", tmp_path / "workspace"
        ).state
        is review.PrivateNativeRecoveryReviewState.INITIALIZATION_REVIEW_REQUIRED
    )
    assert events == []


def test_unsupported_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _fake(monkeypatch, events)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert _run(tmp_path).state is review.PrivateNativeRecoveryReviewState.UNSUPPORTED
    assert events == []


def test_no_notes_or_mutation_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(review, "commit_private_binding")
    assert not hasattr(review, "admit_journal")
    assert not hasattr(review, "recover_private_transaction")
    assert all(
        "ready" not in state.value for state in review.PrivateNativeRecoveryReviewState
    )
    assert not hasattr(review.PrivateNativeRecoveryReview, "image")
