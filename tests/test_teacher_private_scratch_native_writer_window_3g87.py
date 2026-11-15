"""3G87 scratch-only native parent custody and exact pre/postimage exercises."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_native_writer_window as window
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _blocked(result: window.PrivateScratchWindowReview) -> None:
    assert not any(
        (
            result.production_mutation_admitted,
            result.operation_owned_production_guard_qualified,
            result.noncooperating_writer_exclusion_qualified,
            result.native_replace_postimage_production_qualified,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.multi_document_atomic_commit_qualified,
        )
    )
    assert (
        repr(result)
        == "PrivateScratchWindowReview(disposable_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize("bad", [None, "normal", True, 1, Path("relative")])
def test_invalid_scenario_no_mutation_surface(bad: object) -> None:
    result = window.probe_disposable_native_writer_window(
        cast(window.PrivateScratchWindowScenario, bad)
    )
    assert result.state is window.PrivateScratchWindowState.INVALID_REQUEST_REFUSED
    assert not result.synthetic_replace_attempted
    _blocked(result)


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native only")
def test_native_scratch_replace_one_guarded_window() -> None:
    result = window.probe_disposable_native_writer_window(
        window.PrivateScratchWindowScenario.NORMAL
    )
    assert (
        result.state is window.PrivateScratchWindowState.SCRATCH_REPLACED_NONAUTHORIZING
    )
    assert result.synthetic_parent_retained_during_window
    assert result.cooperative_lock_held_during_window
    assert result.preimage_rechecked_during_window
    assert result.synthetic_replace_attempted
    assert result.synthetic_postimage_verified
    assert result.pending_synthetic_journal_preserved
    _blocked(result)


@pytest.mark.parametrize(
    "scenario,expected",
    [
        (
            window.PrivateScratchWindowScenario.PREIMAGE_DRIFT,
            window.PrivateScratchWindowState.PREIMAGE_DRIFT_REFUSED,
        ),
        (
            window.PrivateScratchWindowScenario.STAGE_DRIFT,
            window.PrivateScratchWindowState.STAGE_DRIFT_REFUSED,
        ),
    ],
)
@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native only")
def test_native_drift_before_replace_is_refused(
    scenario: window.PrivateScratchWindowScenario,
    expected: window.PrivateScratchWindowState,
) -> None:
    result = window.probe_disposable_native_writer_window(scenario)
    assert result.state is expected
    assert result.synthetic_parent_retained_during_window
    assert result.cooperative_lock_held_during_window
    assert result.preimage_rechecked_during_window
    assert not result.synthetic_replace_attempted
    assert not result.synthetic_postimage_verified
    assert result.pending_synthetic_journal_preserved
    _blocked(result)


def test_requirements_drift_refuses_before_native_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = window.probe_disposable_native_writer_window(
        window.PrivateScratchWindowScenario.NORMAL
    )
    assert result.state is window.PrivateScratchWindowState.OBSERVATION_REFUSED
    _blocked(result)


def test_source_accepts_no_paths_writers_or_notes_activation() -> None:
    origin = window.__file__
    assert origin is not None
    tree = ast.parse(Path(origin).read_text(encoding="utf-8"))
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "probe_disposable_native_writer_window"
    )
    assert len(fn.args.args) == 1 and fn.args.args[0].arg == "scenario"
    assert not fn.args.kwarg and not fn.args.vararg
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    source = Path(origin).read_text(encoding="utf-8")
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "activate_notes(",
        "ensure_workspace_root(",
        "review_private_production_write_barrier(",
    ):
        assert forbidden not in source
