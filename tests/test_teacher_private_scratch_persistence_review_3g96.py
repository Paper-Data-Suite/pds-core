"""Core #238 3G96: native directory fsync and read-only uncertainty holds."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_persistence_review as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


_EXPECTED = {
    "orphan_checkpoint_temp": "conflict_evidence_hold",
    "registry_rename_not_acknowledged": "uncertain_rename_hold",
    "descriptor_rename_not_acknowledged": "uncertain_rename_hold",
    "both_pending_manual_review": "pending_manual_review_hold",
    "corrupt_canonical_journal": "conflict_evidence_hold",
    "acknowledged_registry_image_mismatch": "conflict_evidence_hold",
    "linux_parent_directory_fsync": (
        "linux_directory_sync_request_observed_hold"
        if sys.platform == "linux"
        else "windows_directory_sync_unqualified"
    ),
}


def _blocked(review: probe.PrivatePersistenceReview) -> None:
    assert repr(review) == (
        "PrivatePersistenceReview(disposable_only=True, non_authorizing=True)"
    )
    for name in (
        "production_mutation_admitted",
        "automatic_replay_allowed",
        "automatic_retry_allowed",
        "journal_retirement_allowed",
        "notes_records_available",
        "directory_crash_durability_qualified",
        "multi_document_atomic_commit_qualified",
        "noncooperating_writer_exclusion_qualified",
        "atomic_content_compare_and_swap_qualified",
    ):
        assert getattr(review, name) is False


@pytest.mark.parametrize("scenario", list(probe.PrivatePersistenceReviewScenario))
@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native Linux/Windows"
)
def test_fresh_process_inspection_holds_without_resume(
    scenario: probe.PrivatePersistenceReviewScenario,
) -> None:
    review = probe.probe_disposable_persistence_review(scenario)
    assert review.state.value == _EXPECTED[scenario.value]
    _blocked(review)
    if (
        sys.platform == "win32"
        and scenario
        is probe.PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC
    ):
        assert not review.independent_producer_hard_exit_observed
        assert not review.parent_directory_fsync_requested
        assert review.independent_interpreters == 0
        return
    assert review.scenario == scenario.value
    assert review.read_only_fresh_inspector_observed
    assert review.independent_producer_hard_exit_observed
    assert review.observed_images_unchanged_by_inspection
    assert review.pending_journal_evidence_preserved
    assert review.conflicting_or_uncertain_evidence_held
    assert review.independent_interpreters == 2
    assert review.parent_directory_fsync_requested is (
        scenario is probe.PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC
    )
    assert review.native_parent_directory_identity_rechecked == (
        scenario is probe.PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC
    )


@pytest.mark.parametrize(
    "invalid", [None, "orphan_checkpoint_temp", True, 0, Path("scratch")]
)
def test_untrusted_scenarios_refused(invalid: object) -> None:
    result = probe.probe_disposable_persistence_review(
        cast(probe.PrivatePersistenceReviewScenario, invalid)
    )
    assert result.state is probe.PrivatePersistenceReviewState.INVALID_REQUEST_REFUSED
    assert result.independent_interpreters == 0
    _blocked(result)


def test_production_requirement_drift_refuses_before_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = probe.probe_disposable_persistence_review(
        probe.PrivatePersistenceReviewScenario.ORPHAN_CHECKPOINT_TEMP
    )
    assert result.state is probe.PrivatePersistenceReviewState.REQUIREMENT_DRIFT_REFUSED
    assert result.independent_interpreters == 0
    _blocked(result)


def test_unsupported_platform_refuses_before_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = probe.probe_disposable_persistence_review(
        probe.PrivatePersistenceReviewScenario.ORPHAN_CHECKPOINT_TEMP
    )
    assert result.state is probe.PrivatePersistenceReviewState.UNSUPPORTED_REFUSED
    assert result.independent_interpreters == 0
    _blocked(result)


def test_public_api_rejects_real_workspace_capabilities() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    location = probe.__file__
    assert location is not None
    source = Path(location).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "probe_disposable_persistence_review"
    )
    assert [arg.arg for arg in fn.args.args] == ["scenario"]
    assert not fn.args.vararg and not fn.args.kwarg
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "ensure_workspace_root(",
        "activate_notes(",
        "_explicit_resume(",
    ):
        assert forbidden not in source
