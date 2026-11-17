"""Core #238 3G93: native Windows ReplaceFileW postcheck race (scratch only)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_windows_postcheck_race as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _blocked(review: probe.PrivateWindowsPostcheckRaceReview) -> None:
    for field in (
        "production_mutation_admitted",
        "windows_handle_relative_replace_qualified",
        "noncooperating_writer_exclusion_qualified",
        "atomic_content_compare_and_swap_qualified",
        "automatic_replay_allowed",
        "journal_retirement_allowed",
        "notes_records_available",
        "directory_crash_durability_qualified",
        "multi_document_atomic_commit_qualified",
    ):
        assert getattr(review, field) is False
    assert repr(review) == (
        "PrivateWindowsPostcheckRaceReview(disposable_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize("bad", [None, "normal", True, 1, Path("fake")])
def test_invalid_scenario_refused(bad: object) -> None:
    review = probe.probe_windows_disposable_postcheck_race(
        cast(probe.PrivateWindowsPostcheckRaceScenario, bad)
    )
    assert (
        review.state is probe.PrivateWindowsPostcheckRaceState.INVALID_REQUEST_REFUSED
    )
    assert not review.native_replacefile_called_after_race
    _blocked(review)


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
@pytest.mark.parametrize(
    "scenario,state",
    [
        (
            probe.PrivateWindowsPostcheckRaceScenario.NORMAL,
            probe.PrivateWindowsPostcheckRaceState.NORMAL_BACKUP_NONAUTHORIZING,
        ),
        (
            probe.PrivateWindowsPostcheckRaceScenario.LIVE_SWAP_AFTER_CHECK,
            probe.PrivateWindowsPostcheckRaceState.LIVE_POSTCHECK_TOCTOU_DEMONSTRATED,
        ),
        (
            probe.PrivateWindowsPostcheckRaceScenario.STAGE_SWAP_AFTER_CHECK,
            probe.PrivateWindowsPostcheckRaceState.STAGE_POSTCHECK_TOCTOU_DEMONSTRATED,
        ),
    ],
)
def test_native_windows_race_and_no_race(
    scenario: probe.PrivateWindowsPostcheckRaceScenario,
    state: probe.PrivateWindowsPostcheckRaceState,
) -> None:
    review = probe.probe_windows_disposable_postcheck_race(scenario)
    assert review.state is state
    assert review.native_directory_handle_retained
    assert review.cooperative_lock_held_during_race
    assert review.final_exact_precheck_before_rival
    assert review.native_replacefile_called_after_race
    assert review.exact_backup_afterimage_verified
    assert review.exact_new_registry_afterimage_verified
    assert review.synthetic_pending_journal_preserved
    expected_rival = scenario is not probe.PrivateWindowsPostcheckRaceScenario.NORMAL
    assert review.independent_uncooperative_interpreter_observed is expected_rival
    assert review.same_bytes_new_file_identity_after_precheck is expected_rival
    _blocked(review)


def test_linux_explicit_refusal_no_native_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    review = probe.probe_windows_disposable_postcheck_race(
        probe.PrivateWindowsPostcheckRaceScenario.NORMAL
    )
    assert (
        review.state
        is probe.PrivateWindowsPostcheckRaceState.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED
    )
    assert not review.native_replacefile_called_after_race
    _blocked(review)


def test_requirement_drift_before_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    review = probe.probe_windows_disposable_postcheck_race(
        probe.PrivateWindowsPostcheckRaceScenario.NORMAL
    )
    assert (
        review.state is probe.PrivateWindowsPostcheckRaceState.REQUIREMENT_DRIFT_REFUSED
    )
    _blocked(review)


def test_fixed_scenario_only_and_negative_capabilities() -> None:
    origin = probe.__file__
    assert origin is not None
    tree = ast.parse(Path(origin).read_text(encoding="utf-8"))
    fn = next(
        f
        for f in tree.body
        if isinstance(f, ast.FunctionDef)
        and f.name == "probe_windows_disposable_postcheck_race"
    )
    assert len(fn.args.args) == 1 and fn.args.args[0].arg == "scenario"
    assert fn.args.vararg is None and fn.args.kwarg is None
    source = Path(origin).read_text(encoding="utf-8")
    for forbidden in (
        "commit_private_workspace_binding(",
        "activate_notes(",
        "retire_private_journal(",
        "ensure_workspace_root(",
    ):
        assert forbidden not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
