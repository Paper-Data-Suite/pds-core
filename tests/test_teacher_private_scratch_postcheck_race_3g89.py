"""3G89 Linux dirfd precheck/replace race counterexample: disposable only."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_postcheck_race as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _blocked(value: probe.PrivatePostcheckRaceReview) -> None:
    assert not any(
        (
            value.production_mutation_admitted,
            value.exclusive_operation_owned_guard_qualified,
            value.noncooperating_writer_exclusion_qualified,
            value.atomic_content_compare_and_swap_qualified,
            value.windows_native_replace_qualified,
            value.automatic_replay_allowed,
            value.journal_retirement_allowed,
            value.notes_records_available,
            value.directory_crash_durability_qualified,
            value.multi_document_atomic_commit_qualified,
        )
    )
    assert repr(value) == (
        "PrivatePostcheckRaceReview(disposable_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize("invalid", [None, True, "normal", 1, Path("relative")])
def test_untrusted_scenario_has_no_writer_surface(invalid: object) -> None:
    value = probe.probe_linux_disposable_postcheck_race(
        cast(probe.PrivatePostcheckRaceScenario, invalid)
    )
    assert value.state is probe.PrivatePostcheckRaceState.INVALID_REQUEST_REFUSED
    assert not value.dirfd_replace_performed_after_race
    _blocked(value)


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux only")
@pytest.mark.parametrize(
    "scenario,wanted,rival",
    [
        (
            probe.PrivatePostcheckRaceScenario.NORMAL,
            probe.PrivatePostcheckRaceState.NORMAL_SCRATCH_REPLACED_NONAUTHORIZING,
            False,
        ),
        (
            probe.PrivatePostcheckRaceScenario.LIVE_SWAP_AFTER_CHECK,
            probe.PrivatePostcheckRaceState.LIVE_POSTCHECK_TOCTOU_DEMONSTRATED,
            True,
        ),
        (
            probe.PrivatePostcheckRaceScenario.STAGE_SWAP_AFTER_CHECK,
            probe.PrivatePostcheckRaceState.STAGE_POSTCHECK_TOCTOU_DEMONSTRATED,
            True,
        ),
    ],
)
def test_native_postcheck_race_counterexample(
    scenario: probe.PrivatePostcheckRaceScenario,
    wanted: probe.PrivatePostcheckRaceState,
    rival: bool,
) -> None:
    observed = probe.probe_linux_disposable_postcheck_race(scenario)
    assert observed.state is wanted
    assert observed.linux_directory_fd_retained
    assert observed.cooperative_lock_held_during_race
    assert observed.exact_precheck_before_injected_race
    assert observed.separate_uncooperative_interpreter_observed is rival
    assert observed.same_byte_entry_identity_replaced_after_check is rival
    assert observed.dirfd_replace_performed_after_race
    assert observed.synthetic_afterimage_verified
    assert observed.pending_synthetic_journal_preserved
    _blocked(observed)


def test_windows_refuses_without_creating_scratch() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows only")
    observed = probe.probe_linux_disposable_postcheck_race(
        probe.PrivatePostcheckRaceScenario.NORMAL
    )
    assert (
        observed.state
        is probe.PrivatePostcheckRaceState.WINDOWS_NATIVE_PROTOCOL_UNQUALIFIED
    )
    assert not observed.dirfd_replace_performed_after_race
    _blocked(observed)


def test_requirements_mismatch_refuses_early(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "linux":
        pytest.skip("Linux only")
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    observed = probe.probe_linux_disposable_postcheck_race(
        probe.PrivatePostcheckRaceScenario.NORMAL
    )
    assert observed.state is probe.PrivatePostcheckRaceState.REQUIREMENT_DRIFT_REFUSED
    _blocked(observed)


def test_signature_is_fixed_and_no_production_entrypoint() -> None:
    path = probe.__file__
    assert path is not None
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "probe_linux_disposable_postcheck_race"
    )
    assert len(fn.args.args) == 1 and fn.args.args[0].arg == "scenario"
    assert not fn.args.kwarg and not fn.args.vararg
    assert "src_dir_fd=fd, dst_dir_fd=fd" in source
    for forbidden in (
        "commit_private_workspace_binding(",
        "activate_notes(",
        "retire_private_journal(",
        "ensure_workspace_root(",
    ):
        assert forbidden not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {
            "terminal.header.v1",
            "terminal.notes_command.v1",
        }
    )
