"""#238 3E5 — one native journal read twice under triple retained advisory guards."""

from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_crash_checkpoint as checkpoint
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_registry_snapshot as registry
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_journal_checkpoint_review as review
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
ASSOCIATION = "6fb32a62-83e2-43f6-9823-687801593c8b"
REGISTRY_BYTES = b"synthetic canonical registry image"
DESCRIPTOR_BYTES = b"synthetic canonical descriptor image"
JOURNAL_BYTES = b"synthetic canonical journal image"


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _proposal() -> intents.PrivateTransactionIntent:
    proposal = object.__new__(intents.PrivateTransactionIntent)
    action = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(action, "operation", witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(action, "transaction_id", TX)
    object.__setattr__(proposal, "witness", action)
    return proposal


def _journal(image: bytes | None = JOURNAL_BYTES) -> journal.PrivateJournalImageReview:
    state = (
        journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
        if image is not None
        else journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED
    )
    return journal.PrivateJournalImageReview(state, "synthetic", image)


def _fake(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    first_state: journal.PrivateJournalImageState = journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
    second_state: journal.PrivateJournalImageState = journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
    changed_journal: bool = False,
    changed_registry: bool = False,
    refused_registry: bool = False,
    refused_descriptor: bool = False,
    changed_owner: bool = False,
    enter_code: retained.RetainedDescriptorGuardCode | None = None,
    exit_code: retained.RetainedDescriptorGuardCode | None = None,
    checkpoint_state: checkpoint.PrivateJournalCrashCheckpointState = checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def guard(_private: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        if enter_code is not None:
            raise retained.RetainedDescriptorGuardError(enter_code)
        try:
            yield
            if exit_code is not None:
                raise retained.RetainedDescriptorGuardError(exit_code)
        finally:
            events.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)
    owner_count = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal owner_count
        owner_count += 1
        events.append("owner")
        if changed_owner and owner_count == 2:
            original = _owner()
            return inspection.EffectiveOSOwner(
                original.kind,
                "2000" if original.kind == "posix_euid" else "S-1-5-21-88-22-33-44",
            )
        return _owner()

    monkeypatch.setattr(ordered, "_owner", owner)
    read_count = 0

    def image(
        _dir: Path, transaction_id: str, current: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        nonlocal read_count
        assert transaction_id == TX
        assert current == _owner()
        read_count += 1
        events.append("journal")
        state = first_state if read_count == 1 else second_state
        raw = (
            JOURNAL_BYTES + b"x"
            if changed_journal and read_count == 2
            else JOURNAL_BYTES
        )
        return journal.PrivateJournalImageReview(
            state,
            "synthetic",
            raw
            if state is journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
            else None,
        )

    monkeypatch.setattr(review, "_native_image", image)
    registry_reads = 0

    def reg(_root: Path) -> registry.PrivateRegistrySnapshot:
        nonlocal registry_reads
        registry_reads += 1
        events.append("registry")
        state = (
            registry.PrivateRegistrySnapshotState.CORRUPT_METADATA
            if refused_registry
            else registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
        )
        digest = hashlib.sha256(REGISTRY_BYTES).hexdigest()
        if changed_registry and registry_reads == 2:
            digest = "a" * 64
        return registry.PrivateRegistrySnapshot(state, "synthetic", 4, 1, digest)

    def desc(_root: Path) -> descriptor.PrivateDescriptorSnapshot:
        events.append("descriptor")
        state = (
            descriptor.PrivateDescriptorSnapshotState.CORRUPT_METADATA
            if refused_descriptor
            else descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
        )
        return descriptor.PrivateDescriptorSnapshot(
            state,
            "synthetic",
            ASSOCIATION,
            hashlib.sha256(DESCRIPTOR_BYTES).hexdigest(),
        )

    monkeypatch.setattr(paired, "_registry_read", reg)
    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", desc)

    def classify(
        _proposed: intents.PrivateTransactionIntent,
        *,
        observed_journal: bytes | None,
        observed_registry: bytes | None,
        observed_descriptor: bytes | None,
    ) -> checkpoint.PrivateJournalCrashCheckpointReview:
        assert observed_journal == JOURNAL_BYTES
        assert observed_registry == REGISTRY_BYTES
        assert observed_descriptor == DESCRIPTOR_BYTES
        events.append("checkpoint")
        return checkpoint.PrivateJournalCrashCheckpointReview(
            checkpoint_state, "synthetic"
        )

    monkeypatch.setattr(
        checkpoint, "classify_private_journal_crash_checkpoint", classify
    )


def _call(
    tmp_path: Path,
    *,
    registry_image: bytes = REGISTRY_BYTES,
    descriptor_image: bytes = DESCRIPTOR_BYTES,
) -> review.PrivateRetainedJournalCheckpointReview:
    return review.review_retained_private_journal_checkpoint(
        _proposal(),
        tmp_path / "private",
        tmp_path / "workspace",
        observed_registry=registry_image,
        observed_descriptor=descriptor_image,
    )


@pytest.mark.parametrize(
    ("checkpoint_state", "expected"),
    [
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED,
            review.PrivateRetainedJournalCheckpointState.JOURNALED_BEFORE_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
            review.PrivateRetainedJournalCheckpointState.JOURNALED_DESCRIPTOR_ONLY_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED,
            review.PrivateRetainedJournalCheckpointState.JOURNALED_REGISTRY_ONLY_REVIEW_REQUIRED,
        ),
        (
            checkpoint.PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED,
            review.PrivateRetainedJournalCheckpointState.JOURNALED_AFTER_REVIEW_REQUIRED,
        ),
    ],
)
def test_native_guarded_sequence_is_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkpoint_state: checkpoint.PrivateJournalCrashCheckpointState,
    expected: review.PrivateRetainedJournalCheckpointState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, checkpoint_state=checkpoint_state)
    result = _call(tmp_path)
    assert result.state is expected
    assert events == [
        "guard-enter",
        "owner",
        "journal",
        "registry",
        "descriptor",
        "descriptor",
        "registry",
        "journal",
        "owner",
        "checkpoint",
        "guard-exit",
    ]
    assert list(tmp_path.iterdir()) == []
    for private in (
        TX,
        ASSOCIATION,
        _owner().value,
        str(tmp_path),
        "synthetic canonical",
    ):
        assert private not in repr(result) and private not in result.message


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED,
            review.PrivateRetainedJournalCheckpointState.JOURNAL_MISSING,
        ),
        (
            journal.PrivateJournalImageState.OWNER_CHANGED,
            review.PrivateRetainedJournalCheckpointState.OWNER_CHANGED,
        ),
        (
            journal.PrivateJournalImageState.OWNER_UNAVAILABLE,
            review.PrivateRetainedJournalCheckpointState.OWNER_UNAVAILABLE,
        ),
        (
            journal.PrivateJournalImageState.INVALID_JOURNAL,
            review.PrivateRetainedJournalCheckpointState.JOURNAL_UNQUALIFIED,
        ),
        (
            journal.PrivateJournalImageState.CHANGED_DURING_READ,
            review.PrivateRetainedJournalCheckpointState.JOURNAL_CHANGED,
        ),
        (
            journal.PrivateJournalImageState.REFUSED_BACKING,
            review.PrivateRetainedJournalCheckpointState.JOURNAL_UNQUALIFIED,
        ),
    ],
)
def test_first_native_journal_refusal_stops_early(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: journal.PrivateJournalImageState,
    expected: review.PrivateRetainedJournalCheckpointState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, first_state=state)
    assert _call(tmp_path).state is expected
    assert events == ["guard-enter", "owner", "journal", "guard-exit"]


@pytest.mark.parametrize(
    "state",
    [
        journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED,
        journal.PrivateJournalImageState.REFUSED_PROTECTION,
        journal.PrivateJournalImageState.CHANGED_DURING_READ,
    ],
)
def test_second_native_journal_refusal_blocks_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: journal.PrivateJournalImageState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, second_state=state)
    assert _call(tmp_path).state not in {
        review.PrivateRetainedJournalCheckpointState.JOURNALED_BEFORE_REVIEW_REQUIRED,
        review.PrivateRetainedJournalCheckpointState.JOURNALED_AFTER_REVIEW_REQUIRED,
    }
    assert events.count("journal") == 2
    assert "checkpoint" not in events


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        (
            "changed_journal",
            review.PrivateRetainedJournalCheckpointState.JOURNAL_CHANGED,
        ),
        (
            "changed_registry",
            review.PrivateRetainedJournalCheckpointState.OBSERVATIONS_CHANGED,
        ),
        (
            "refused_registry",
            review.PrivateRetainedJournalCheckpointState.METADATA_UNQUALIFIED,
        ),
        (
            "refused_descriptor",
            review.PrivateRetainedJournalCheckpointState.METADATA_UNQUALIFIED,
        ),
        ("changed_owner", review.PrivateRetainedJournalCheckpointState.OWNER_CHANGED),
    ],
)
def test_drift_refused_before_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    expected: review.PrivateRetainedJournalCheckpointState,
) -> None:
    events: list[str] = []
    _fake(
        monkeypatch,
        events,
        changed_journal=setting == "changed_journal",
        changed_registry=setting == "changed_registry",
        refused_registry=setting == "refused_registry",
        refused_descriptor=setting == "refused_descriptor",
        changed_owner=setting == "changed_owner",
    )
    assert _call(tmp_path).state is expected
    assert "checkpoint" not in events


@pytest.mark.parametrize("which", ["registry", "descriptor"])
def test_supplied_images_must_match_native_snapshot_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events)
    actual = _call(
        tmp_path,
        registry_image=b"foreign" if which == "registry" else REGISTRY_BYTES,
        descriptor_image=b"foreign" if which == "descriptor" else DESCRIPTOR_BYTES,
    )
    assert (
        actual.state
        is review.PrivateRetainedJournalCheckpointState.PROVIDED_IMAGES_UNQUALIFIED
    )
    assert "checkpoint" not in events


@pytest.mark.parametrize(
    "state",
    [
        checkpoint.PrivateJournalCrashCheckpointState.FOREIGN_METADATA_REFUSED,
        checkpoint.PrivateJournalCrashCheckpointState.UNJOURNALED_AFTER_REFUSED,
        checkpoint.PrivateJournalCrashCheckpointState.INTENT_REFUSED,
    ],
)
def test_classifier_refusal_cannot_be_promoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: checkpoint.PrivateJournalCrashCheckpointState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, checkpoint_state=state)
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedJournalCheckpointState.CHECKPOINT_REFUSED
    )


@pytest.mark.parametrize(
    ("guard_code", "expected"),
    [
        (
            retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
            review.PrivateRetainedJournalCheckpointState.OWNER_CHANGED,
        ),
        (
            retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE,
            review.PrivateRetainedJournalCheckpointState.OWNER_UNAVAILABLE,
        ),
        (
            retained.RetainedDescriptorGuardCode.UNSUPPORTED,
            review.PrivateRetainedJournalCheckpointState.UNSUPPORTED,
        ),
        (
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
            review.PrivateRetainedJournalCheckpointState.GUARD_REFUSED,
        ),
    ],
)
def test_guard_exit_overrides_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    guard_code: retained.RetainedDescriptorGuardCode,
    expected: review.PrivateRetainedJournalCheckpointState,
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events, exit_code=guard_code)
    assert _call(tmp_path).state is expected
    assert "checkpoint" in events and events[-1] == "guard-exit"


def test_guard_entry_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _fake(
        monkeypatch,
        events,
        enter_code=retained.RetainedDescriptorGuardCode.MISSING_DESCRIPTOR,
    )
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedJournalCheckpointState.GUARD_REFUSED
    )
    assert events == ["guard-enter"]


def test_initialize_refused_before_any_native_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events)
    proposal = _proposal()
    object.__setattr__(
        proposal.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    result = review.review_retained_private_journal_checkpoint(
        proposal,
        tmp_path / "private",
        tmp_path / "workspace",
        observed_registry=REGISTRY_BYTES,
        observed_descriptor=DESCRIPTOR_BYTES,
    )
    assert (
        result.state
        is review.PrivateRetainedJournalCheckpointState.INITIALIZATION_REVIEW_REQUIRED
    )
    assert events == []


def test_invalid_and_unsupported_requests_are_nonmutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fake(monkeypatch, events)
    assert (
        review.review_retained_private_journal_checkpoint(
            cast(intents.PrivateTransactionIntent, "invalid"),
            tmp_path / "private",
            tmp_path / "workspace",
            observed_registry=REGISTRY_BYTES,
            observed_descriptor=DESCRIPTOR_BYTES,
        ).state
        is review.PrivateRetainedJournalCheckpointState.INVALID_REQUEST
    )
    assert (
        review.review_retained_private_journal_checkpoint(
            _proposal(),
            tmp_path / "private",
            tmp_path / "workspace",
            observed_registry=b"",
            observed_descriptor=DESCRIPTOR_BYTES,
        ).state
        is review.PrivateRetainedJournalCheckpointState.INVALID_REQUEST
    )
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        _call(tmp_path).state
        is review.PrivateRetainedJournalCheckpointState.UNSUPPORTED
    )
    assert events == []


def test_capability_boundary() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(review, "commit_private_binding")
    assert not hasattr(review, "admit_journal")
    assert not hasattr(review, "recover_private_transaction")
    assert not hasattr(review.PrivateRetainedJournalCheckpointReview, "write_handle")
    assert all(
        "ready" not in item.value
        for item in review.PrivateRetainedJournalCheckpointState
    )
