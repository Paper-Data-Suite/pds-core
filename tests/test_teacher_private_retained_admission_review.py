"""#238 3D6 — metadata and journal census inside a retained native guard."""

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
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_pending_journal_review as pending
from pds_core import _teacher_private_registry_snapshot as registry
from pds_core import _teacher_private_retained_admission_review as review
from pds_core import _teacher_private_retained_journal_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

_ASSOC = "0b283e11-b17b-42ac-8c96-79037b1ea4d9"
_REGISTRY_SHA = "a" * 64
_DESCRIPTOR_SHA = "b" * 64


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _sample(
    tmp_path: Path,
) -> tuple[intents.PrivateTransactionIntent, paired.PrivatePairObservation, Path, Path]:
    proposal = object.__new__(intents.PrivateTransactionIntent)
    action = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(action, "operation", witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(proposal, "witness", action)
    prior = paired.PrivatePairObservation(
        paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED,
        "synthetic unqualified prior evidence",
        5,
        1,
        _ASSOC,
        _REGISTRY_SHA,
        _DESCRIPTOR_SHA,
    )
    return proposal, prior, tmp_path / "private", tmp_path / "workspace"


def _fake(
    monkeypatch: pytest.MonkeyPatch,
    prior: paired.PrivatePairObservation,
    events: list[str],
    *,
    first_census: pending.PrivatePendingJournalState = pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
    second_census: pending.PrivatePendingJournalState = pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED,
    owner_drift: bool = False,
    stale_registry: bool = False,
    bad_preconditions: bool = False,
    enter_error: retained.RetainedJournalGuardCode | None = None,
    exit_error: retained.RetainedJournalGuardCode | None = None,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def guard(_private: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        if enter_error is not None:
            raise retained.RetainedJournalGuardError(enter_error)
        try:
            yield
            if exit_error is not None:
                raise retained.RetainedJournalGuardError(exit_error)
        finally:
            events.append("guard-exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_journal_guard", guard)
    owner_calls = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal owner_calls
        owner_calls += 1
        events.append("owner")
        if owner_drift and owner_calls == 2:
            principal = _owner()
            return inspection.EffectiveOSOwner(
                principal.kind,
                "2000" if principal.kind == "posix_euid" else "S-1-5-21-88-22-33-44",
            )
        return _owner()

    monkeypatch.setattr(ordered, "_owner", owner)
    scans = iter((first_census, second_census))

    def census(
        directory: Path, owner: inspection.EffectiveOSOwner
    ) -> pending.PrivatePendingJournalState:
        assert directory.name == "transactions"
        assert owner == _owner()
        events.append("census")
        return next(scans)

    monkeypatch.setattr(pending, "_scan_linux", census)
    monkeypatch.setattr(pending, "_scan_windows", census)
    registry_reads = 0

    def reg(_root: Path) -> registry.PrivateRegistrySnapshot:
        nonlocal registry_reads
        registry_reads += 1
        events.append("registry")
        return registry.PrivateRegistrySnapshot(
            registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic registry",
            prior.registry_revision,
            prior.registry_binding_count,
            "f" * 64
            if stale_registry and registry_reads == 2
            else prior.registry_sha256,
        )

    def desc(_root: Path) -> descriptor.PrivateDescriptorSnapshot:
        events.append("descriptor")
        return descriptor.PrivateDescriptorSnapshot(
            descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic descriptor",
            prior.association_id,
            prior.descriptor_sha256,
        )

    def compare(
        _proposed: intents.PrivateTransactionIntent,
        _current: paired.PrivatePairObservation,
        _root: Path,
        _principal: inspection.EffectiveOSOwner,
    ) -> preconditions.PrivateBindingPreconditionReview:
        events.append("preconditions")
        state = (
            preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH
            if bad_preconditions
            else preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
        )
        return preconditions.PrivateBindingPreconditionReview(state, "synthetic")

    monkeypatch.setattr(paired, "_registry_read", reg)
    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", desc)
    monkeypatch.setattr(preconditions, "review_binding_preconditions", compare)


def test_single_retained_guard_spans_all_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events)
    result = review.review_retained_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert (
        result.state
        is review.PrivateRetainedAdmissionState.RECHECKED_RETAINED_REVIEW_REQUIRED
    )
    assert events == [
        "guard-enter",
        "owner",
        "census",
        "registry",
        "descriptor",
        "descriptor",
        "registry",
        "census",
        "owner",
        "preconditions",
        "guard-exit",
    ]
    assert not list(tmp_path.iterdir())
    assert _ASSOC not in repr(result)
    assert _owner().value not in repr(result)
    assert str(workspace) not in repr(result)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED,
            review.PrivateRetainedAdmissionState.PENDING_RECOVERY_REQUIRED,
        ),
        (
            pending.PrivatePendingJournalState.MISSING_DIRECTORY,
            review.PrivateRetainedAdmissionState.JOURNAL_DIRECTORY_UNQUALIFIED,
        ),
        (
            pending.PrivatePendingJournalState.REFUSED_BACKING,
            review.PrivateRetainedAdmissionState.JOURNAL_DIRECTORY_UNQUALIFIED,
        ),
        (
            pending.PrivatePendingJournalState.CHANGED_DURING_REVIEW,
            review.PrivateRetainedAdmissionState.JOURNAL_OBSERVATION_CHANGED,
        ),
        (
            pending.PrivatePendingJournalState.OWNER_CHANGED,
            review.PrivateRetainedAdmissionState.OWNER_CHANGED,
        ),
    ],
)
def test_first_census_refuses_before_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: pending.PrivatePendingJournalState,
    expected: review.PrivateRetainedAdmissionState,
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events, first_census=state)
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is expected
    )
    assert events == ["guard-enter", "owner", "census", "guard-exit"]


def test_pending_entry_after_metadata_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(
        monkeypatch,
        prior,
        events,
        second_census=pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED,
    )
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateRetainedAdmissionState.PENDING_RECOVERY_REQUIRED
    )
    assert events.count("registry") == 2
    assert "preconditions" not in events
    assert events[-1] == "guard-exit"


def test_replaced_metadata_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events, stale_registry=True)
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateRetainedAdmissionState.CURRENT_OBSERVATION_UNQUALIFIED
    )
    assert "preconditions" not in events


def test_stale_prior_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events)
    stale = replace(prior, registry_sha256="f" * 64)
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, stale, private, workspace
        ).state
        is review.PrivateRetainedAdmissionState.OBSERVATION_STALE
    )
    assert "preconditions" not in events


def test_precondition_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events, bad_preconditions=True)
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateRetainedAdmissionState.PRECONDITION_REFUSED
    )
    assert events[-2:] == ["preconditions", "guard-exit"]


def test_owner_drift_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events, owner_drift=True)
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateRetainedAdmissionState.OWNER_CHANGED
    )
    assert "preconditions" not in events
    assert events[-1] == "guard-exit"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            retained.RetainedJournalGuardCode.MISSING_DIRECTORY,
            review.PrivateRetainedAdmissionState.RETAINED_GUARD_REFUSED,
        ),
        (
            retained.RetainedJournalGuardCode.OWNER_CHANGED,
            review.PrivateRetainedAdmissionState.OWNER_CHANGED,
        ),
        (
            retained.RetainedJournalGuardCode.OWNER_UNAVAILABLE,
            review.PrivateRetainedAdmissionState.OWNER_UNAVAILABLE,
        ),
        (
            retained.RetainedJournalGuardCode.UNSUPPORTED,
            review.PrivateRetainedAdmissionState.UNSUPPORTED,
        ),
    ],
)
def test_retained_guard_entry_refusals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: retained.RetainedJournalGuardCode,
    expected: review.PrivateRetainedAdmissionState,
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events, enter_error=code)
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is expected
    )
    assert events == ["guard-enter"]


def test_guard_exit_failure_overrides_matched_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(
        monkeypatch,
        prior,
        events,
        exit_error=retained.RetainedJournalGuardCode.CHANGED_DURING_SCOPE,
    )
    result = review.review_retained_private_journal_preconditions(
        proposal, prior, private, workspace
    )
    assert result.state is review.PrivateRetainedAdmissionState.RETAINED_GUARD_REFUSED
    assert "preconditions" in events
    assert events[-1] == "guard-exit"


def test_initialize_and_invalid_inputs_do_not_enter_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fake(monkeypatch, prior, events)
    object.__setattr__(
        proposal.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateRetainedAdmissionState.INITIALIZATION_ABSENCE_REVIEW
    )
    assert (
        review.review_retained_private_journal_preconditions(
            "not-an-intent",  # type: ignore[arg-type]
            prior,
            private,
            workspace,
        ).state
        is review.PrivateRetainedAdmissionState.INVALID_REQUEST
    )
    assert events == []


def test_unsupported_platform_and_no_notes_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        review.review_retained_private_journal_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateRetainedAdmissionState.UNSUPPORTED
    )
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(review, "commit_private_binding")
    assert not hasattr(review, "admit_journal")
    assert not hasattr(review.PrivateRetainedAdmissionReview, "write_handle")
    assert not hasattr(review.PrivateRetainedAdmissionReview, "commit_token")
    assert all(
        "ready" not in state.value for state in review.PrivateRetainedAdmissionState
    )
