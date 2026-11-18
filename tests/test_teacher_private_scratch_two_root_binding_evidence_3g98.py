"""Core #238 3G98: two-root synthetic binding evidence and ACL holds."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_two_root_binding_evidence as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


_EXPECTED = {
    "consistent": "consistent_but_unqualified_hold",
    "association_mismatch": "association_conflict_hold",
    "owner_marker_mismatch": "synthetic_owner_marker_conflict_hold",
    "duplicate_workspace_copy": "duplicate_association_hold",
    "unsupported_descriptor_version": "malformed_metadata_hold",
    "registry_extra_field": "malformed_metadata_hold",
    "posix_private_root_mode_drift": (
        "posix_protection_refused"
        if sys.platform == "linux"
        else "windows_dacl_unqualified"
    ),
}


def _blocked(review: probe.PrivateTwoRootEvidenceReview) -> None:
    assert repr(review) == (
        "PrivateTwoRootEvidenceReview(scratch_only=True, non_authorizing=True)"
    )
    for field in (
        "journal_or_notes_touched",
        "production_mutation_admitted",
        "explicit_binding_allowed",
        "effective_os_owner_acl_qualified",
        "copied_descriptor_authorizes_binding",
        "automatic_replay_allowed",
        "automatic_retry_allowed",
        "journal_retirement_allowed",
        "notes_records_available",
        "directory_crash_durability_qualified",
        "multi_document_atomic_commit_qualified",
        "noncooperating_writer_exclusion_qualified",
        "atomic_content_compare_and_swap_qualified",
    ):
        assert getattr(review, field) is False


@pytest.mark.parametrize("scenario", list(probe.PrivateTwoRootEvidenceScenario))
@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Linux/Windows only")
def test_two_root_evidence_holds_and_never_authorizes(
    scenario: probe.PrivateTwoRootEvidenceScenario,
) -> None:
    result = probe.probe_disposable_two_root_binding_evidence(scenario)
    assert result.state.value == _EXPECTED[scenario.value]
    _blocked(result)
    if scenario is probe.PrivateTwoRootEvidenceScenario.POSIX_PRIVATE_ROOT_MODE_DRIFT:
        assert not result.native_workspace_parent_retained
        assert not result.two_root_file_images_checked
        assert not result.effective_os_owner_acl_qualified
        return
    assert result.native_workspace_parent_retained
    assert result.native_private_parent_retained
    assert result.cooperative_private_lock_held
    assert result.two_root_file_images_checked
    assert result.native_two_root_identities_rechecked
    assert result.posix_owner_mode_observed_scratch_only is (sys.platform == "linux")
    assert result.duplicate_association_detected is (
        scenario is probe.PrivateTwoRootEvidenceScenario.DUPLICATE_WORKSPACE_COPY
    )


@pytest.mark.parametrize("bad", [None, "consistent", 0, True, Path("data")])
def test_invalid_scenarios_refused(bad: object) -> None:
    result = probe.probe_disposable_two_root_binding_evidence(
        cast(probe.PrivateTwoRootEvidenceScenario, bad)
    )
    assert result.state is probe.PrivateTwoRootEvidenceState.INVALID_REQUEST_REFUSED
    assert not result.native_private_parent_retained
    _blocked(result)


def test_requirements_drift_refused_before_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = probe.probe_disposable_two_root_binding_evidence(
        probe.PrivateTwoRootEvidenceScenario.CONSISTENT
    )
    assert result.state is probe.PrivateTwoRootEvidenceState.REQUIREMENT_DRIFT_REFUSED
    _blocked(result)


def test_unsupported_platform_refused_before_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = probe.probe_disposable_two_root_binding_evidence(
        probe.PrivateTwoRootEvidenceScenario.CONSISTENT
    )
    assert result.state is probe.PrivateTwoRootEvidenceState.UNSUPPORTED_REFUSED
    _blocked(result)


def test_narrow_api_and_public_capabilities() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    origin = probe.__file__
    assert origin is not None
    source = Path(origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    entry = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "probe_disposable_two_root_binding_evidence"
    )
    assert [param.arg for param in entry.args.args] == ["scenario"]
    assert not entry.args.kwarg and not entry.args.vararg
    for forbidden in (
        "commit_private_workspace_binding(",
        "activate_notes(",
        "retire_private_journal(",
        "ensure_workspace_root(",
        "_explicit_resume(",
    ):
        assert forbidden not in source
