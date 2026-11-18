"""Core #238 3G95: independent producer, inspector and explicit recovery."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_fresh_process_checkpoints as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


_CUTS = (
    "prepared",
    "registry_intent",
    "registry_installed",
    "registry_confirmed",
    "descriptor_intent",
    "descriptor_installed",
    "both_pending_review",
)
_CONFLICTS = (
    "conflict_journal",
    "conflict_registry",
    "conflict_stage",
    "conflict_checkpoint_temp",
)


def _non_authorizing(review: probe.PrivateFreshCheckpointReview) -> None:
    assert (
        repr(review)
        == "PrivateFreshCheckpointReview(scratch_only=True, non_authorizing=True)"
    )
    for field in (
        "production_mutation_admitted",
        "automatic_replay_allowed",
        "automatic_retry_allowed",
        "journal_retirement_allowed",
        "notes_records_available",
        "noncooperating_writer_exclusion_qualified",
        "atomic_content_compare_and_swap_qualified",
        "directory_crash_durability_qualified",
        "multi_document_atomic_commit_qualified",
    ):
        assert getattr(review, field) is False


@pytest.mark.parametrize("scenario", list(_CUTS))
@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Windows/Linux only")
def test_independent_fresh_process_resume_and_idempotence(scenario: str) -> None:
    value = probe.PrivateFreshCheckpointScenario(scenario)
    review = probe.probe_disposable_fresh_process_checkpoints(value)
    assert review.state is (
        probe.PrivateFreshCheckpointState.ALREADY_COMPLETE_PENDING_HOLD
        if scenario == "both_pending_review"
        else probe.PrivateFreshCheckpointState.EXPLICIT_FRESH_PROCESS_RESUMED_PENDING_HOLD
    )
    assert review.interrupted_checkpoint == scenario
    assert review.independent_producer_hard_exit_observed
    assert review.independent_read_only_inspector_observed
    assert review.inspector_left_evidence_unchanged
    assert review.independent_explicit_recovery_observed
    assert review.exact_synthetic_afterimages_verified
    assert review.second_recovery_noop
    assert review.journal_remains_pending
    assert not review.conflict_evidence_preserved
    assert review.independent_python_interpreters == 4
    _non_authorizing(review)


@pytest.mark.parametrize("scenario", list(_CONFLICTS))
@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Windows/Linux only")
def test_fresh_process_conflicts_preserve_exact_evidence(scenario: str) -> None:
    value = probe.PrivateFreshCheckpointScenario(scenario)
    review = probe.probe_disposable_fresh_process_checkpoints(value)
    assert (
        review.state
        is probe.PrivateFreshCheckpointState.CONFLICT_EVIDENCE_PRESERVED_HOLD
    )
    assert review.interrupted_checkpoint == scenario
    assert review.independent_producer_hard_exit_observed
    assert review.independent_read_only_inspector_observed
    assert review.inspector_left_evidence_unchanged
    assert review.independent_explicit_recovery_observed
    assert review.conflict_evidence_preserved
    assert review.journal_remains_pending
    assert not review.exact_synthetic_afterimages_verified
    assert not review.second_recovery_noop
    assert review.independent_python_interpreters == 3
    _non_authorizing(review)


@pytest.mark.parametrize("bad", [None, "prepared", 0, True, Path("scratch")])
def test_invalid_scenario_refused(bad: object) -> None:
    value = cast(probe.PrivateFreshCheckpointScenario, bad)
    review = probe.probe_disposable_fresh_process_checkpoints(value)
    assert review.state is probe.PrivateFreshCheckpointState.INVALID_REQUEST_REFUSED
    assert review.independent_python_interpreters == 0
    _non_authorizing(review)


def test_requirement_drift_refused_before_process_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    review = probe.probe_disposable_fresh_process_checkpoints(
        probe.PrivateFreshCheckpointScenario.PREPARED
    )
    assert review.state is probe.PrivateFreshCheckpointState.REQUIREMENT_DRIFT_REFUSED
    assert review.independent_python_interpreters == 0
    _non_authorizing(review)


def test_unsupported_platform_refused_before_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    review = probe.probe_disposable_fresh_process_checkpoints(
        probe.PrivateFreshCheckpointScenario.PREPARED
    )
    assert review.state is probe.PrivateFreshCheckpointState.UNSUPPORTED_REFUSED
    assert review.independent_python_interpreters == 0
    _non_authorizing(review)


def test_narrow_public_input_and_notes_capability_barrier() -> None:
    origin = probe.__file__
    assert origin is not None
    text = Path(origin).read_text(encoding="utf-8")
    tree = ast.parse(text)
    fn = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "probe_disposable_fresh_process_checkpoints"
    )
    assert len(fn.args.args) == 1 and fn.args.args[0].arg == "scenario"
    assert not fn.args.kwarg and not fn.args.vararg
    for forbidden in (
        "commit_private_workspace_binding(",
        "activate_notes(",
        "retire_private_journal(",
        "ensure_workspace_root(",
    ):
        assert forbidden not in text
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
