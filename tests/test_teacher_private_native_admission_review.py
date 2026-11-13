"""#238 Slice 3D4 — native anchor and journal/metadata checks under one guard."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_admission_review as review
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_pending_journal_review as pending
from pds_core import _teacher_private_registry_snapshot as registry
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

_ASSOC = "0b283e11-b17b-42ac-8c96-79037b1ea4d9"
_SHA_REG = "a" * 64
_SHA_DESC = "b" * 64


def _principal() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _sample(
    tmp_path: Path,
) -> tuple[intents.PrivateTransactionIntent, paired.PrivatePairObservation, Path, Path]:
    """Synthetic advisory-only intent. The real codec remains a separate gate."""
    proposal = object.__new__(intents.PrivateTransactionIntent)
    operation = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(
        operation, "operation", witness.PrivateBindingOperation.FORK_COPY
    )
    object.__setattr__(proposal, "witness", operation)
    previous = paired.PrivatePairObservation(
        paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED,
        "synthetic observation, never authority",
        5,
        1,
        _ASSOC,
        _SHA_REG,
        _SHA_DESC,
    )
    return proposal, previous, tmp_path / "private", tmp_path / "workspace"


def _fake(
    monkeypatch: pytest.MonkeyPatch,
    previous: paired.PrivatePairObservation,
    trace: list[str],
    *,
    first_anchor: anchor.PrivateJournalAnchorState = anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED,
    second_anchor: anchor.PrivateJournalAnchorState = anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED,
    first_census: pending.PrivatePendingJournalState = pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
    second_census: pending.PrivatePendingJournalState = pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
    owner_changed: bool = False,
    registry_changed: bool = False,
    bad_preconditions: bool = False,
    locked: bool = True,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def lock_pair(_private: Path, _workspace: Path) -> Iterator[None]:
        trace.extend(("lock-registry", "lock-workspace"))
        if not locked:
            raise ordered.PrivateOrderedCoordinationError(
                ordered.PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE
            )
        try:
            yield
        finally:
            trace.extend(("unlock-workspace", "unlock-registry"))

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", lock_pair)
    reads = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal reads
        reads += 1
        trace.append("owner")
        if owner_changed and reads == 2:
            principal = _principal()
            return inspection.EffectiveOSOwner(
                principal.kind,
                "2000" if principal.kind == "posix_euid" else "S-1-5-21-99-22-33-44",
            )
        return _principal()

    monkeypatch.setattr(ordered, "_owner", owner)
    anchors = iter((first_anchor, second_anchor))

    def native_probe(
        directory: Path, principal: inspection.EffectiveOSOwner
    ) -> anchor.PrivateJournalAnchorState:
        assert directory.name == "transactions"
        assert principal == _principal()
        trace.append("anchor")
        return next(anchors)

    monkeypatch.setattr(anchor, "_linux_anchor", native_probe)
    monkeypatch.setattr(anchor, "_windows_anchor", native_probe)
    journal_scans = iter((first_census, second_census))

    def census(
        directory: Path, principal: inspection.EffectiveOSOwner
    ) -> pending.PrivatePendingJournalState:
        assert directory.name == "transactions"
        assert principal == _principal()
        trace.append("census")
        return next(journal_scans)

    monkeypatch.setattr(pending, "_scan_linux", census)
    monkeypatch.setattr(pending, "_scan_windows", census)
    registry_reads = 0

    def reg(_root: Path) -> registry.PrivateRegistrySnapshot:
        nonlocal registry_reads
        registry_reads += 1
        trace.append("registry")
        return registry.PrivateRegistrySnapshot(
            registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic registry observation",
            previous.registry_revision,
            previous.registry_binding_count,
            "f" * 64
            if registry_changed and registry_reads == 2
            else previous.registry_sha256,
        )

    def desc(_root: Path) -> descriptor.PrivateDescriptorSnapshot:
        trace.append("descriptor")
        return descriptor.PrivateDescriptorSnapshot(
            descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic descriptor observation",
            previous.association_id,
            previous.descriptor_sha256,
        )

    def compared(
        _proposal: intents.PrivateTransactionIntent,
        _current: paired.PrivatePairObservation,
        _root: Path,
        _owner: inspection.EffectiveOSOwner,
    ) -> preconditions.PrivateBindingPreconditionReview:
        trace.append("preconditions")
        state = (
            preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH
            if bad_preconditions
            else preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
        )
        return preconditions.PrivateBindingPreconditionReview(
            state, "synthetic comparison"
        )

    monkeypatch.setattr(paired, "_registry_read", reg)
    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", desc)
    monkeypatch.setattr(preconditions, "review_binding_preconditions", compared)


def test_checks_share_continuously_held_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state
        is review.PrivateNativeAdmissionReviewState.RECHECKED_NATIVE_ANCHOR_REVIEW_REQUIRED
    )
    assert trace == [
        "lock-registry",
        "lock-workspace",
        "owner",
        "anchor",
        "census",
        "registry",
        "descriptor",
        "descriptor",
        "registry",
        "census",
        "anchor",
        "owner",
        "preconditions",
        "unlock-workspace",
        "unlock-registry",
    ]
    assert not list(tmp_path.iterdir())
    assert _ASSOC not in repr(outcome)
    assert str(workspace) not in repr(outcome)
    assert _principal().value not in repr(outcome)


@pytest.mark.parametrize(
    "native_state",
    [
        anchor.PrivateJournalAnchorState.CHANGED_DURING_REVIEW,
        anchor.PrivateJournalAnchorState.MISSING_DIRECTORY,
        anchor.PrivateJournalAnchorState.REFUSED_BACKING,
        anchor.PrivateJournalAnchorState.REFUSED_PROTECTION,
        anchor.PrivateJournalAnchorState.ACCESS_DENIED,
        anchor.PrivateJournalAnchorState.UNSUPPORTED,
        anchor.PrivateJournalAnchorState.OWNER_CHANGED,
        anchor.PrivateJournalAnchorState.OWNER_UNAVAILABLE,
    ],
)
def test_initial_native_refusal_prevents_any_metadata_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    native_state: anchor.PrivateJournalAnchorState,
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, first_anchor=native_state)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state
        is not review.PrivateNativeAdmissionReviewState.RECHECKED_NATIVE_ANCHOR_REVIEW_REQUIRED
    )
    assert trace == [
        "lock-registry",
        "lock-workspace",
        "owner",
        "anchor",
        "unlock-workspace",
        "unlock-registry",
    ]


def test_native_change_detected_after_metadata_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(
        monkeypatch,
        prior,
        trace,
        second_anchor=anchor.PrivateJournalAnchorState.CHANGED_DURING_REVIEW,
    )
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state is review.PrivateNativeAdmissionReviewState.NATIVE_ANCHOR_CHANGED
    )
    assert trace.count("anchor") == 2
    assert "preconditions" not in trace
    assert trace[-2:] == ["unlock-workspace", "unlock-registry"]


@pytest.mark.parametrize(
    "journal_state",
    [
        pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED,
        pending.PrivatePendingJournalState.REFUSED_PROTECTION,
        pending.PrivatePendingJournalState.MISSING_DIRECTORY,
        pending.PrivatePendingJournalState.CHANGED_DURING_REVIEW,
    ],
)
def test_first_journal_refusal_prevents_metadata_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    journal_state: pending.PrivatePendingJournalState,
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, first_census=journal_state)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state
        is not review.PrivateNativeAdmissionReviewState.RECHECKED_NATIVE_ANCHOR_REVIEW_REQUIRED
    )
    assert trace == [
        "lock-registry",
        "lock-workspace",
        "owner",
        "anchor",
        "census",
        "unlock-workspace",
        "unlock-registry",
    ]


def test_pending_entry_appears_after_metadata_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(
        monkeypatch,
        prior,
        trace,
        second_census=pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED,
    )
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state
        is review.PrivateNativeAdmissionReviewState.PENDING_RECOVERY_REQUIRED
    )
    assert trace.count("census") == 2
    assert trace.count("anchor") == 1
    assert "preconditions" not in trace


def test_stale_prior_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    stale = replace(prior, registry_sha256="f" * 64)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, stale, private, workspace
    )
    assert outcome.state is review.PrivateNativeAdmissionReviewState.OBSERVATION_STALE
    assert "preconditions" not in trace


def test_registry_changes_during_double_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, registry_changed=True)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state
        is review.PrivateNativeAdmissionReviewState.CURRENT_OBSERVATION_UNQUALIFIED
    )
    assert "preconditions" not in trace


def test_precondition_mismatch_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, bad_preconditions=True)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state is review.PrivateNativeAdmissionReviewState.PRECONDITION_REFUSED
    )
    assert "preconditions" in trace


def test_owner_drift_refuses_and_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, owner_changed=True)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert outcome.state is review.PrivateNativeAdmissionReviewState.OWNER_CHANGED
    assert "preconditions" not in trace
    assert trace[-2:] == ["unlock-workspace", "unlock-registry"]


def test_failed_lock_precedes_all_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace, locked=False)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state is review.PrivateNativeAdmissionReviewState.COORDINATION_REFUSED
    )
    assert trace == ["lock-registry", "lock-workspace"]


def test_initialize_cannot_probe_native_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    object.__setattr__(
        proposal.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    outcome = review.review_native_anchored_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        outcome.state
        is review.PrivateNativeAdmissionReviewState.INITIALIZATION_ABSENCE_REVIEW
    )
    assert trace == []


def test_invalid_and_unsupported_are_non_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    trace: list[str] = []
    _fake(monkeypatch, prior, trace)
    assert (
        review.review_native_anchored_private_journal_preconditions(
            "not-an-intent",  # type: ignore[arg-type]
            prior,
            private,
            workspace,
        ).state
        is review.PrivateNativeAdmissionReviewState.INVALID_REQUEST
    )
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        review.review_native_anchored_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateNativeAdmissionReviewState.UNSUPPORTED
    )
    assert trace == []


def test_no_notes_or_write_authority() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(review, "commit_private_binding")
    assert not hasattr(review, "admit_journal")
    assert not hasattr(review.PrivateNativeAdmissionReview, "write_handle")
    assert not hasattr(review.PrivateNativeAdmissionReview, "authorized")
    assert not hasattr(review.PrivateNativeAdmissionReview, "commit_token")
    assert all(
        "ready" not in state.value for state in review.PrivateNativeAdmissionReviewState
    )
