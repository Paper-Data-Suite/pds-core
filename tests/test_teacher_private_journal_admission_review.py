"""#238 Slice 3D2 — one-lock-scope double-census and metadata preflight."""

from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_admission_review as admission
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_pending_journal_review as pending
from pds_core import _teacher_private_registry_snapshot as registry
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

_ASSOC = "0b283e11-b17b-42ac-8c96-79037b1ea4d9"
_NEW = "ea867513-59c5-4cf2-b7d1-a5c9b203c734"
_TX = "c0bbda1f-41fc-45c8-ab52-94601b2abe9d"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _sample(
    tmp: Path,
) -> tuple[intents.PrivateTransactionIntent, paired.PrivatePairObservation, Path, Path]:
    origin = tmp / "source"
    workspace = tmp / "destination"
    private = tmp / "private"
    owner = _owner()
    who = metadata.PrivateRegistryOwner(owner.kind, owner.value)
    old_desc = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_ASSOC)
    )
    new_desc = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_NEW)
    )
    old_reg = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            who, 5, (metadata.PrivateRegistryBinding(_ASSOC, 3, str(origin)),)
        )
    )
    new_reg = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            who,
            6,
            (
                metadata.PrivateRegistryBinding(_ASSOC, 3, str(origin)),
                metadata.PrivateRegistryBinding(_NEW, 1, str(workspace)),
            ),
        )
    )
    intent = intents.PrivateTransactionIntent(
        witness.PrivateTransactionWitness(
            witness.PrivateBindingOperation.FORK_COPY,
            _TX,
            _ASSOC,
            _NEW,
            5,
            6,
            _sha(old_desc),
            _sha(new_desc),
            _sha(old_reg),
            _sha(new_reg),
        ),
        old_desc,
        new_desc,
        old_reg,
        new_reg,
    )
    prior = paired.PrivatePairObservation(
        paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED,
        "synthetic prior non-authorizing observation",
        5,
        1,
        _ASSOC,
        _sha(old_reg),
        _sha(old_desc),
    )
    return intent, prior, private, workspace


def _fake(
    monkeypatch: pytest.MonkeyPatch,
    prior: paired.PrivatePairObservation,
    trace: list[str],
    *,
    first_journal: pending.PrivatePendingJournalState = pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
    second_journal: pending.PrivatePendingJournalState = pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
    owner_changed: bool = False,
    changed_registry: bool = False,
    bad_preconditions: bool = False,
    lock_refusal: bool = False,
) -> None:
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def locks(private: Path, workspace: Path) -> Iterator[None]:
        trace.append("lock-registry")
        if lock_refusal:
            raise ordered.PrivateOrderedCoordinationError(
                ordered.PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE
            )
        trace.append("lock-workspace")
        try:
            yield
        finally:
            trace.append("unlock-workspace")
            trace.append("unlock-registry")

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", locks)
    owner_reads = 0

    def get_owner() -> inspection.EffectiveOSOwner:
        nonlocal owner_reads
        owner_reads += 1
        trace.append("owner")
        if owner_changed and owner_reads == 2:
            previous = _owner()
            return inspection.EffectiveOSOwner(
                previous.kind,
                "2000" if previous.kind == "posix_euid" else "S-1-5-21-99-22-33-44",
            )
        return _owner()

    monkeypatch.setattr(ordered, "_owner", get_owner)
    journals = iter((first_journal, second_journal))

    def census(
        directory: Path, owner: inspection.EffectiveOSOwner
    ) -> pending.PrivatePendingJournalState:
        assert directory.name == "transactions"
        assert owner == _owner()
        trace.append("journal")
        return next(journals)

    monkeypatch.setattr(pending, "_scan_linux", census)
    monkeypatch.setattr(pending, "_scan_windows", census)
    registry_reads = 0

    def reg(_root: Path) -> registry.PrivateRegistrySnapshot:
        nonlocal registry_reads
        registry_reads += 1
        trace.append("registry")
        return registry.PrivateRegistrySnapshot(
            registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic owner registry",
            prior.registry_revision,
            prior.registry_binding_count,
            "f" * 64
            if changed_registry and registry_reads == 2
            else prior.registry_sha256,
        )

    def desc(_root: Path) -> descriptor.PrivateDescriptorSnapshot:
        trace.append("descriptor")
        return descriptor.PrivateDescriptorSnapshot(
            descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic association sidecar",
            prior.association_id,
            prior.descriptor_sha256,
        )

    monkeypatch.setattr(paired, "_registry_read", reg)
    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", desc)

    def fake_preconditions(
        *_args: object,
    ) -> preconditions.PrivateBindingPreconditionReview:
        trace.append("preconditions")
        return preconditions.PrivateBindingPreconditionReview(
            preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH
            if bad_preconditions
            else preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED,
            "synthetic no-write comparison",
        )

    monkeypatch.setattr(
        preconditions, "review_binding_preconditions", fake_preconditions
    )


def test_double_census_and_metadata_share_one_ordered_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    outcome = admission.review_private_journal_admission_preconditions(
        proposed, prior, private, workspace
    )
    assert (
        outcome.state
        is admission.PrivateJournalAdmissionReviewState.RECHECKED_JOURNAL_FREE_REVIEW_REQUIRED
    )
    assert trace == [
        "lock-registry",
        "lock-workspace",
        "owner",
        "journal",
        "registry",
        "descriptor",
        "descriptor",
        "registry",
        "journal",
        "owner",
        "preconditions",
        "unlock-workspace",
        "unlock-registry",
    ]
    assert list(tmp_path.iterdir()) == []
    assert _ASSOC not in repr(outcome)
    assert str(workspace) not in repr(outcome)
    assert _owner().value not in repr(outcome)


@pytest.mark.parametrize(
    "state",
    [
        pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED,
        pending.PrivatePendingJournalState.MISSING_DIRECTORY,
        pending.PrivatePendingJournalState.REFUSED_BACKING,
        pending.PrivatePendingJournalState.REFUSED_PROTECTION,
        pending.PrivatePendingJournalState.CHANGED_DURING_REVIEW,
        pending.PrivatePendingJournalState.ACCESS_DENIED,
    ],
)
def test_first_journal_refusal_prevents_metadata_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: pending.PrivatePendingJournalState,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, first_journal=state)
    outcome = admission.review_private_journal_admission_preconditions(
        proposed, prior, private, workspace
    )
    assert (
        outcome.state
        is not admission.PrivateJournalAdmissionReviewState.RECHECKED_JOURNAL_FREE_REVIEW_REQUIRED
    )
    assert trace == [
        "lock-registry",
        "lock-workspace",
        "owner",
        "journal",
        "unlock-workspace",
        "unlock-registry",
    ]


def test_pending_entry_appears_after_metadata_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(
        monkeypatch,
        prior,
        trace,
        second_journal=pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED,
    )
    outcome = admission.review_private_journal_admission_preconditions(
        proposed, prior, private, workspace
    )
    assert (
        outcome.state
        is admission.PrivateJournalAdmissionReviewState.PENDING_RECOVERY_REQUIRED
    )
    assert trace.count("journal") == 2
    assert "preconditions" not in trace
    assert trace[-2:] == ["unlock-workspace", "unlock-registry"]


def test_stale_prior_is_not_rebased(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    stale = replace(prior, registry_sha256="f" * 64)
    outcome = admission.review_private_journal_admission_preconditions(
        proposed, stale, private, workspace
    )
    assert (
        outcome.state is admission.PrivateJournalAdmissionReviewState.OBSERVATION_STALE
    )
    assert "preconditions" not in trace


def test_changed_metadata_in_pair_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, changed_registry=True)
    outcome = admission.review_private_journal_admission_preconditions(
        proposed, prior, private, workspace
    )
    assert (
        outcome.state
        is admission.PrivateJournalAdmissionReviewState.CURRENT_OBSERVATION_UNQUALIFIED
    )
    assert "preconditions" not in trace


def test_precondition_mismatch_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, bad_preconditions=True)
    result = admission.review_private_journal_admission_preconditions(
        proposed, prior, private, workspace
    )
    assert (
        result.state
        is admission.PrivateJournalAdmissionReviewState.PRECONDITION_REFUSED
    )
    assert "preconditions" in trace


def test_owner_changed_within_guard_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, owner_changed=True)
    assert (
        admission.review_private_journal_admission_preconditions(
            proposed, prior, private, workspace
        ).state
        is admission.PrivateJournalAdmissionReviewState.OWNER_CHANGED
    )
    assert "preconditions" not in trace


def test_lock_refusal_precedes_journal_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, lock_refusal=True)
    assert (
        admission.review_private_journal_admission_preconditions(
            proposed, prior, private, workspace
        ).state
        is admission.PrivateJournalAdmissionReviewState.COORDINATION_REFUSED
    )
    assert trace == ["lock-registry"]


def test_initialization_refused_before_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    initialize = object.__new__(intents.PrivateTransactionIntent)
    initial_witness = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(
        initial_witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    object.__setattr__(initialize, "witness", initial_witness)
    assert (
        admission.review_private_journal_admission_preconditions(
            initialize, prior, private, workspace
        ).state
        is admission.PrivateJournalAdmissionReviewState.INITIALIZATION_ABSENCE_REVIEW
    )
    assert trace == []


def test_unsupported_or_invalid_without_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: False)
    assert (
        admission.review_private_journal_admission_preconditions(
            proposed, prior, private, workspace
        ).state
        is admission.PrivateJournalAdmissionReviewState.INVALID_REQUEST
    )
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        admission.review_private_journal_admission_preconditions(
            proposed, prior, private, workspace
        ).state
        is admission.PrivateJournalAdmissionReviewState.UNSUPPORTED
    )
    assert trace == []


def test_negative_capability_boundary_and_sanitization() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(admission, "commit_private_binding")
    assert not hasattr(admission, "admit_private_journal")
    assert not hasattr(admission.PrivateJournalAdmissionReview, "commit_token")
    assert not hasattr(admission.PrivateJournalAdmissionReview, "authorized")
    assert not hasattr(admission.PrivateJournalAdmissionReview, "write_handle")
    states = {s.value for s in admission.PrivateJournalAdmissionReviewState}
    assert "ready" not in states and "authorized" not in states
