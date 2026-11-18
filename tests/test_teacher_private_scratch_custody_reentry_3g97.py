"""Core #238 3G97 native parent custody and same-byte file identity holds."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_custody_reentry as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


_EXPECTED = {
    "stable_registry_installed": "stable_uncertain_hold",
    "stable_both_pending": "stable_pending_manual_hold",
    "equal_bytes_live_substitution": "same_bytes_identity_drift_hold",
    "equal_bytes_stage_substitution": "same_bytes_identity_drift_hold",
    "equal_bytes_journal_substitution": "same_bytes_identity_drift_hold",
    "changed_registry_bytes": "content_conflict_hold",
}


def _non_authorizing(review: probe.PrivateCustodyReentryReview) -> None:
    assert repr(review) == (
        "PrivateCustodyReentryReview(scratch_only=True, non_authorizing=True)"
    )
    for field in (
        "production_mutation_admitted",
        "automatic_replay_allowed",
        "automatic_retry_allowed",
        "journal_retirement_allowed",
        "notes_records_available",
        "atomic_content_compare_and_swap_qualified",
        "noncooperating_writer_exclusion_qualified",
        "native_handle_relative_replace_qualified",
        "directory_crash_durability_qualified",
        "multi_document_atomic_commit_qualified",
    ):
        assert getattr(review, field) is False


@pytest.mark.parametrize("scenario", list(probe.PrivateCustodyReentryScenario))
@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native Linux/Windows only"
)
def test_native_parent_custody_preserves_read_only_hold(
    scenario: probe.PrivateCustodyReentryScenario,
) -> None:
    review = probe.probe_disposable_custody_reentry(scenario)
    assert review.state.value == _EXPECTED[scenario.value]
    assert review.scenario == scenario.value
    assert review.native_parent_handle_retained_across_inspection
    assert review.independent_producer_hard_exit_observed
    assert review.independent_read_only_inspector_observed
    assert review.exact_bytes_inspector_unchanged
    assert review.watched_entry_identity_checked
    assert review.pending_journal_retained
    rival = scenario in {
        probe.PrivateCustodyReentryScenario.EQUAL_BYTES_LIVE_SUBSTITUTION,
        probe.PrivateCustodyReentryScenario.EQUAL_BYTES_STAGE_SUBSTITUTION,
        probe.PrivateCustodyReentryScenario.EQUAL_BYTES_JOURNAL_SUBSTITUTION,
        probe.PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES,
    }
    assert review.independent_interpreters == (3 if rival else 2)
    assert review.equal_bytes_identity_substitution_detected == (
        scenario.value.startswith("equal_bytes_")
    )
    assert review.content_conflict_detected == (
        scenario is probe.PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES
    )
    _non_authorizing(review)


@pytest.mark.parametrize("bad", [None, "stable_both_pending", True, 0, Path("scratch")])
def test_reject_untrusted_input(bad: object) -> None:
    review = probe.probe_disposable_custody_reentry(
        cast(probe.PrivateCustodyReentryScenario, bad)
    )
    assert review.state is probe.PrivateCustodyReentryState.INVALID_REQUEST_REFUSED
    assert review.independent_interpreters == 0
    _non_authorizing(review)


def test_requirement_drift_refused_before_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    review = probe.probe_disposable_custody_reentry(
        probe.PrivateCustodyReentryScenario.STABLE_BOTH_PENDING
    )
    assert review.state is probe.PrivateCustodyReentryState.REQUIREMENT_DRIFT_REFUSED
    assert review.independent_interpreters == 0
    _non_authorizing(review)


def test_unsupported_platform_refused_before_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    review = probe.probe_disposable_custody_reentry(
        probe.PrivateCustodyReentryScenario.STABLE_BOTH_PENDING
    )
    assert review.state is probe.PrivateCustodyReentryState.UNSUPPORTED_REFUSED
    assert review.independent_interpreters == 0
    _non_authorizing(review)


def test_public_api_and_no_production_authority() -> None:
    origin = probe.__file__
    assert origin is not None
    source = Path(origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "probe_disposable_custody_reentry"
    )
    assert [arg.arg for arg in fn.args.args] == ["scenario"]
    assert not fn.args.kwarg and not fn.args.vararg
    for forbidden in (
        "commit_private_workspace_binding(",
        "activate_notes(",
        "retire_private_journal(",
        "ensure_workspace_root(",
        "_explicit_resume(",
    ):
        assert forbidden not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
