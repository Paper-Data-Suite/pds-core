"""Core #238 3G99 native Windows owner SID / protected DACL scratch holds."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_windows_owner_acl_review as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


_EXPECTED = {
    "protected_owner": "protected_dacl_shape_observed_hold",
    "unprotected_dacl": "unprotected_dacl_refused",
    "everyone_read_dacl": "everyone_access_refused",
    "spoofed_owner": "owner_mismatch_refused",
    "missing_child": "missing_child_refused",
}


def _non_authorizing(review: probe.PrivateWindowsOwnerAclReview) -> None:
    assert repr(review) == (
        "PrivateWindowsOwnerAclReview(scratch_only=True, non_authorizing=True)"
    )
    for name in (
        "production_mutation_admitted",
        "production_owner_acl_qualified",
        "windows_effective_access_qualified",
        "owner_binding_allowed",
        "automatic_replay_allowed",
        "automatic_retry_allowed",
        "journal_retirement_allowed",
        "notes_records_available",
        "directory_crash_durability_qualified",
        "multi_document_atomic_commit_qualified",
        "noncooperating_writer_exclusion_qualified",
    ):
        assert getattr(review, name) is False


@pytest.mark.parametrize("scenario", list(probe.PrivateWindowsOwnerAclScenario))
def test_native_windows_acl_uses_effective_process_sid_and_holds(
    scenario: probe.PrivateWindowsOwnerAclScenario,
) -> None:
    result = probe.probe_disposable_windows_owner_acl(scenario)
    _non_authorizing(result)
    if sys.platform == "win32":
        assert result.state.value == _EXPECTED[scenario.value]
        assert result.scenario == scenario.value
        assert result.process_token_sid_reobserved
        assert result.negative_evidence_preserved
        if scenario is probe.PrivateWindowsOwnerAclScenario.MISSING_CHILD:
            assert not result.dacl_read_from_native_handle
            assert not result.dacl_protection_control_observed
            assert not result.explicit_acl_shape_classified
            assert not result.native_owner_sid_matches_token
        else:
            assert result.native_owner_sid_matches_token
            assert result.dacl_read_from_native_handle
            assert result.dacl_protection_control_observed
            assert result.explicit_acl_shape_classified
    else:
        assert result.state is probe.PrivateWindowsOwnerAclState.WINDOWS_ONLY_REFUSED
        assert result.scenario == "none"
        assert not result.process_token_sid_reobserved


@pytest.mark.parametrize("invalid", [None, "protected_owner", 0, True, Path("scratch")])
def test_invalid_inputs_refused_without_security_operations(invalid: object) -> None:
    case = cast(probe.PrivateWindowsOwnerAclScenario, invalid)
    result = probe.probe_disposable_windows_owner_acl(case)
    assert result.state is probe.PrivateWindowsOwnerAclState.INVALID_REQUEST_REFUSED
    assert not result.dacl_read_from_native_handle
    _non_authorizing(result)


def test_requirement_drift_refused_before_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = probe.probe_disposable_windows_owner_acl(
        probe.PrivateWindowsOwnerAclScenario.PROTECTED_OWNER
    )
    assert result.state is probe.PrivateWindowsOwnerAclState.REQUIREMENT_DRIFT_REFUSED
    _non_authorizing(result)


def test_unsupported_platform_refused_before_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = probe.probe_disposable_windows_owner_acl(
        probe.PrivateWindowsOwnerAclScenario.PROTECTED_OWNER
    )
    assert result.state is probe.PrivateWindowsOwnerAclState.WINDOWS_ONLY_REFUSED
    _non_authorizing(result)


def test_public_api_and_notes_boundaries() -> None:
    source_path = probe.__file__
    assert source_path is not None
    source = Path(source_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "probe_disposable_windows_owner_acl"
    )
    assert [arg.arg for arg in method.args.args] == ["scenario"]
    assert not method.args.vararg and not method.args.kwarg
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
