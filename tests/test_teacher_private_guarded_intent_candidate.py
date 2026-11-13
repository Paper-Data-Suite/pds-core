"""Core #238 Slice 3E9 — guarded, exclusive intent candidate only."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_guarded_intent_candidate as candidate
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_journal_provision as provision
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pending_journal_review as pending
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
INTENT = b"synthetic canonical intent bytes"
REGISTRY = b"synthetic canonical registry before image"
DESCRIPTOR = b"synthetic canonical descriptor before image"


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _proposal() -> intents.PrivateTransactionIntent:
    proposed = object.__new__(intents.PrivateTransactionIntent)
    action = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(action, "operation", witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(action, "transaction_id", TX)
    object.__setattr__(
        action, "association_before", "6fb32a62-83e2-43f6-9823-687801593c8b"
    )
    object.__setattr__(
        action, "association_after", "0e6ef6ea-e641-4b32-88ca-23d6d4932d1f"
    )
    object.__setattr__(action, "registry_revision_before", 1)
    object.__setattr__(action, "registry_revision_after", 2)
    object.__setattr__(action, "descriptor_sha256_before", "a" * 64)
    object.__setattr__(action, "descriptor_sha256_after", "b" * 64)
    object.__setattr__(action, "registry_sha256_before", "c" * 64)
    object.__setattr__(action, "registry_sha256_after", "d" * 64)
    object.__setattr__(proposed, "witness", action)
    object.__setattr__(proposed, "registry_before", REGISTRY)
    object.__setattr__(proposed, "descriptor_before", DESCRIPTOR)
    object.__setattr__(proposed, "registry_after", REGISTRY + b" next")
    object.__setattr__(proposed, "descriptor_after", DESCRIPTOR + b" next")
    return proposed


def _fixture(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    census: str = "",
    change: str = "",
    fail: str = "",
    creation_state: provision.PrivateJournalProvisionState = provision.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED,
    owner_change: int = 0,
    guard_enter: retained.RetainedDescriptorGuardCode | None = None,
    guard_exit: retained.RetainedDescriptorGuardCode | None = None,
) -> None:
    proposed = _proposal()
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda _: INTENT)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: proposed
    )
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(provision, "_requested_transactions_dir", lambda *_: True)

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
        if owner_calls == owner_change:
            original = _owner()
            return inspection.EffectiveOSOwner(
                original.kind,
                "2000" if original.kind == "posix_euid" else "S-1-5-21-88-22-33-44",
            )
        return _owner()

    monkeypatch.setattr(ordered, "_owner", owner)
    census_calls = 0

    def scan(
        _dir: Path, _os_owner: inspection.EffectiveOSOwner
    ) -> pending.PrivatePendingJournalState:
        nonlocal census_calls
        census_calls += 1
        events.append("census" + str(census_calls))
        if census == "pending" or census == "pending-second" and census_calls == 2:
            return pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED
        if census == "bad" or census == "bad-second" and census_calls == 2:
            return pending.PrivatePendingJournalState.CHANGED_DURING_REVIEW
        return pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED

    monkeypatch.setattr(candidate, "_census", scan)
    count_r = 0
    count_d = 0

    def reg(
        _root: Path, _os_owner: inspection.EffectiveOSOwner
    ) -> registry_image.PrivateRegistryImageReview:
        nonlocal count_r
        count_r += 1
        key = "registry" + str(count_r)
        events.append(key)
        if fail == key:
            return registry_image.PrivateRegistryImageReview(
                registry_image.PrivateRegistryImageState.INVALID_REGISTRY, "synthetic"
            )
        return registry_image.PrivateRegistryImageReview(
            registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            (
                REGISTRY + b"other"
                if change == key
                else b"foreign"
                if change == "foreign-registry"
                else REGISTRY
            ),
        )

    def desc(_root: Path) -> descriptor_image.PrivateDescriptorImageReview:
        nonlocal count_d
        count_d += 1
        key = "descriptor" + str(count_d)
        events.append(key)
        if fail == key:
            return descriptor_image.PrivateDescriptorImageReview(
                descriptor_image.PrivateDescriptorImageState.REFUSED_PATH, "synthetic"
            )
        return descriptor_image.PrivateDescriptorImageReview(
            descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            (
                DESCRIPTOR + b"other"
                if change == key
                else b"foreign"
                if change == "foreign-descriptor"
                else DESCRIPTOR
            ),
        )

    monkeypatch.setattr(candidate, "_registry", reg)
    monkeypatch.setattr(candidate, "_descriptor", desc)

    def create(_directory: Path, raw: bytes) -> provision.PrivateJournalProvisionResult:
        events.append("create")
        assert raw == INTENT
        return provision.PrivateJournalProvisionResult(creation_state, "synthetic")

    monkeypatch.setattr(provision, "create_private_transaction_intent_file", create)
    read_count = 0

    def read(
        _directory: Path, transaction_id: str, _os_owner: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        nonlocal read_count
        read_count += 1
        key = "journal" + str(read_count)
        events.append(key)
        assert transaction_id == TX
        if fail == key:
            return journal.PrivateJournalImageReview(
                journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED, "synthetic"
            )
        return journal.PrivateJournalImageReview(
            journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            INTENT + b"other" if change == key else INTENT,
        )

    monkeypatch.setattr(candidate, "_journal", read)


def _run(tmp_path: Path) -> candidate.PrivateGuardedIntentCandidateReview:
    return candidate.create_guarded_private_intent_candidate(
        _proposal(), tmp_path / "private", tmp_path / "workspace"
    )


def test_guarded_exclusive_create_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events)
    actual = _run(tmp_path)
    assert (
        actual.state is candidate.PrivateGuardedIntentCandidateState.CREATED_UNQUALIFIED
    )
    assert events == [
        "guard-enter",
        "owner",
        "census1",
        "registry1",
        "descriptor1",
        "descriptor2",
        "registry2",
        "owner",
        "census2",
        "create",
        "journal1",
        "journal2",
        "owner",
        "guard-exit",
    ]
    assert not list(tmp_path.iterdir())
    assert "ready" not in actual.state.value
    for secret in (TX, _owner().value, "synthetic canonical", str(tmp_path)):
        assert secret not in repr(actual) and secret not in actual.message


@pytest.mark.parametrize("kind", ["pending", "pending-second", "bad", "bad-second"])
def test_journal_census_refusal_precedes_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, census=kind)
    actual = _run(tmp_path)
    if kind.startswith("pending"):
        assert (
            actual.state
            is candidate.PrivateGuardedIntentCandidateState.PENDING_RECOVERY_REQUIRED
        )
    else:
        assert (
            actual.state
            is candidate.PrivateGuardedIntentCandidateState.JOURNAL_DIRECTORY_UNQUALIFIED
        )
    assert "create" not in events


@pytest.mark.parametrize("at", ["registry1", "registry2", "descriptor1", "descriptor2"])
def test_unqualified_native_metadata_prevents_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, at: str
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, fail=at)
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.METADATA_UNQUALIFIED
    )
    assert "create" not in events


@pytest.mark.parametrize("at", ["registry1", "registry2", "descriptor1", "descriptor2"])
def test_changed_images_prevent_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, at: str
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, change=at)
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.IMAGES_CHANGED
    )
    assert "create" not in events


@pytest.mark.parametrize("kind", ["foreign-registry", "foreign-descriptor"])
def test_wrong_before_bytes_prevent_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, change=kind)
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.BEFORE_IMAGE_MISMATCH
    )
    assert "create" not in events


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            provision.PrivateJournalProvisionState.ALREADY_EXISTS,
            candidate.PrivateGuardedIntentCandidateState.PROVISION_REFUSED,
        ),
        (
            provision.PrivateJournalProvisionState.REFUSED_BACKING,
            candidate.PrivateGuardedIntentCandidateState.PROVISION_REFUSED,
        ),
        (
            provision.PrivateJournalProvisionState.ACCESS_DENIED,
            candidate.PrivateGuardedIntentCandidateState.PROVISION_REFUSED,
        ),
        (
            provision.PrivateJournalProvisionState.CREATION_UNVERIFIED,
            candidate.PrivateGuardedIntentCandidateState.CREATION_UNVERIFIED,
        ),
    ],
)
def test_provision_refusal_never_attempts_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: provision.PrivateJournalProvisionState,
    expected: candidate.PrivateGuardedIntentCandidateState,
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, creation_state=status)
    assert _run(tmp_path).state is expected
    assert events.count("create") == 1 and "journal1" not in events


@pytest.mark.parametrize("kind", ["journal1", "journal2"])
def test_postcreate_read_refusal_preserves_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, fail=kind)
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.CREATION_UNVERIFIED
    )
    assert "create" in events
    if kind == "journal1":
        assert "journal2" not in events
    else:
        assert "journal2" in events


@pytest.mark.parametrize("kind", ["journal1", "journal2"])
def test_postcreate_changed_bytes_cannot_qualify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, change=kind)
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.CREATION_UNVERIFIED
    )
    assert events.count("create") == 1


def test_owner_drift_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, owner_change=2)
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.OWNER_CHANGED
    )
    assert "create" not in events


def test_owner_drift_after_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, owner_change=3)
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.OWNER_CHANGED
    )
    assert "create" in events


@pytest.mark.parametrize(
    "guard_code",
    [
        retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
        retained.RetainedDescriptorGuardCode.UNSUPPORTED,
    ],
)
def test_guard_exit_overrides_candidate_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    guard_code: retained.RetainedDescriptorGuardCode,
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events, guard_exit=guard_code)
    actual = _run(tmp_path)
    assert (
        actual.state
        is not candidate.PrivateGuardedIntentCandidateState.CREATED_UNQUALIFIED
    )
    assert "create" in events and events[-1] == "guard-exit"


def test_guard_entry_refusal_never_creates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fixture(
        monkeypatch,
        events,
        guard_enter=retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
    )
    assert (
        _run(tmp_path).state
        is candidate.PrivateGuardedIntentCandidateState.GUARD_REFUSED
    )
    assert "create" not in events


def test_initialization_requires_separate_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events)
    proposed = _proposal()
    object.__setattr__(
        proposed.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    assert (
        candidate.create_guarded_private_intent_candidate(
            proposed, tmp_path / "private", tmp_path / "workspace"
        ).state
        is candidate.PrivateGuardedIntentCandidateState.INITIALIZATION_REQUIRES_SEPARATE_PROTOCOL
    )
    assert events == []


def test_invalid_request_refused_without_creating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events)
    actual = candidate.create_guarded_private_intent_candidate(
        cast(intents.PrivateTransactionIntent, "invalid"),
        tmp_path / "private",
        tmp_path / "workspace",
    )
    assert actual.state is candidate.PrivateGuardedIntentCandidateState.INVALID_REQUEST
    assert events == []


def test_unsupported_platform_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fixture(monkeypatch, events)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        _run(tmp_path).state is candidate.PrivateGuardedIntentCandidateState.UNSUPPORTED
    )
    assert events == []


def test_capability_boundary() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(candidate, "commit_private_binding")
    assert not hasattr(candidate, "recover_private_transaction")
    assert not hasattr(candidate.PrivateGuardedIntentCandidateReview, "write_handle")
    assert all(
        "ready" not in state.value
        for state in candidate.PrivateGuardedIntentCandidateState
    )
