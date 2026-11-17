"""Core #238 Slice 3G90: native Linux filename conditions are not content CAS."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_renameat2_limits as gate
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _blocked(result: gate.PrivateRenameat2Review) -> None:
    assert not any(
        (
            result.atomic_content_cas_qualified,
            result.noncooperating_writer_exclusion_qualified,
            result.production_mutation_admitted,
            result.native_windows_replace_qualified,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.multi_document_atomic_commit_qualified,
        )
    )
    assert (
        repr(result)
        == "PrivateRenameat2Review(disposable_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize(
    "wrong", [None, True, 1, "exchange_two_present", Path("other")]
)
def test_invalid_request_refused(wrong: object) -> None:
    result = gate.probe_linux_renameat2_limits(
        cast(gate.PrivateRenameat2Scenario, wrong)
    )
    assert result.state is gate.PrivateRenameat2State.INVALID_REQUEST_REFUSED
    assert not result.native_linux_flags_exercised
    _blocked(result)


@pytest.mark.parametrize(
    "scenario,expected",
    [
        (
            gate.PrivateRenameat2Scenario.NOREPLACE_EXISTING,
            gate.PrivateRenameat2State.NOREPLACE_EXISTING_REFUSED,
        ),
        (
            gate.PrivateRenameat2Scenario.EXCHANGE_TWO_PRESENT,
            gate.PrivateRenameat2State.EXCHANGE_SCRATCH_ONLY,
        ),
        (
            gate.PrivateRenameat2Scenario.EXCHANGE_AFTER_RIVAL,
            gate.PrivateRenameat2State.EXCHANGE_AFTER_RIVAL_NO_CAS,
        ),
    ],
)
def test_linux_native_semantics_or_windows_refusal(
    scenario: gate.PrivateRenameat2Scenario, expected: gate.PrivateRenameat2State
) -> None:
    result = gate.probe_linux_renameat2_limits(scenario)
    if sys.platform == "win32":
        assert result.state is gate.PrivateRenameat2State.WINDOWS_PROTOCOL_UNQUALIFIED
    elif sys.platform == "linux":
        assert result.state is expected
        assert result.native_linux_flags_exercised
        assert result.directory_fd_retained
        assert result.expected_native_condition_observed
        assert result.exact_disposable_postimages_verified
        assert result.synthetic_journal_preserved
        assert result.independent_same_owner_swap_observed is (
            scenario is gate.PrivateRenameat2Scenario.EXCHANGE_AFTER_RIVAL
        )
    else:
        pytest.skip("unsupported native platform")
    _blocked(result)


def test_requirements_drift_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = gate.probe_linux_renameat2_limits(
        gate.PrivateRenameat2Scenario.EXCHANGE_TWO_PRESENT
    )
    if sys.platform == "linux":
        assert result.state is gate.PrivateRenameat2State.REQUIREMENT_DRIFT_REFUSED
    else:
        assert result.state in {
            gate.PrivateRenameat2State.WINDOWS_PROTOCOL_UNQUALIFIED,
            gate.PrivateRenameat2State.UNSUPPORTED_REFUSED,
        }
    _blocked(result)


def test_no_production_path_callback_or_capability() -> None:
    origin = gate.__file__
    assert origin is not None
    source = Path(origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "probe_linux_renameat2_limits"
    )
    assert len(fn.args.args) == 1
    assert not fn.args.kwarg and not fn.args.vararg
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for forbidden in (
        "commit_private_workspace_binding(",
        "activate_notes(",
        "retire_private_journal(",
        "ensure_workspace_root(",
    ):
        assert forbidden not in source
