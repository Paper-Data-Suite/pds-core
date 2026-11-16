"""3G88: POSIX directory-FD replacement and entry-drift refusals, scratch only."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_dirfd_replace as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _blocked(result: probe.PrivateDirfdScratchReview) -> None:
    assert not any(
        (
            result.production_mutation_admitted,
            result.noncooperating_writer_exclusion_qualified,
            result.atomic_content_compare_and_swap_qualified,
            result.native_windows_replace_qualified,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.multi_document_atomic_commit_qualified,
        )
    )
    assert repr(result) == (
        "PrivateDirfdScratchReview(disposable_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize("bad", [None, True, "normal", 1, Path("relative")])
def test_bad_scenario_cannot_start_scratch(bad: object) -> None:
    result = probe.probe_linux_disposable_dirfd_replace(
        cast(probe.PrivateDirfdScratchScenario, bad)
    )
    assert result.state is probe.PrivateDirfdScratchState.INVALID_REQUEST_REFUSED
    assert not result.replacement_called_dirfd_relative
    _blocked(result)


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux dirfd only")
def test_linux_real_handle_relative_single_registry_replace() -> None:
    result = probe.probe_linux_disposable_dirfd_replace(
        probe.PrivateDirfdScratchScenario.NORMAL
    )
    assert result.state is (
        probe.PrivateDirfdScratchState.LINUX_DIRFD_SCRATCH_REPLACED_NONAUTHORIZING
    )
    assert result.linux_directory_fd_retained
    assert result.both_entries_checked_by_fd
    assert result.replacement_called_dirfd_relative
    assert result.exact_scratch_postimage_verified
    assert result.pending_synthetic_journal_preserved
    _blocked(result)


@pytest.mark.parametrize(
    "scenario,wanted",
    [
        (
            probe.PrivateDirfdScratchScenario.LIVE_ENTRY_DRIFT,
            probe.PrivateDirfdScratchState.LIVE_ENTRY_DRIFT_REFUSED,
        ),
        (
            probe.PrivateDirfdScratchScenario.STAGE_ENTRY_DRIFT,
            probe.PrivateDirfdScratchState.STAGE_ENTRY_DRIFT_REFUSED,
        ),
        (
            probe.PrivateDirfdScratchScenario.PARENT_RELINK,
            probe.PrivateDirfdScratchState.PARENT_RELINK_REFUSED,
        ),
    ],
)
@pytest.mark.skipif(sys.platform != "linux", reason="native Linux dirfd only")
def test_linux_pre_replace_drift_refused(
    scenario: probe.PrivateDirfdScratchScenario,
    wanted: probe.PrivateDirfdScratchState,
) -> None:
    result = probe.probe_linux_disposable_dirfd_replace(scenario)
    assert result.state is wanted
    assert result.linux_directory_fd_retained
    assert not result.replacement_called_dirfd_relative
    assert not result.exact_scratch_postimage_verified
    assert result.pending_synthetic_journal_preserved
    if scenario is probe.PrivateDirfdScratchScenario.PARENT_RELINK:
        assert result.linux_parent_relink_refused
    _blocked(result)


def test_native_windows_is_explicitly_unqualified() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-only fail-closed gate")
    result = probe.probe_linux_disposable_dirfd_replace(
        probe.PrivateDirfdScratchScenario.NORMAL
    )
    assert result.state is (
        probe.PrivateDirfdScratchState.WINDOWS_NATIVE_PROTOCOL_UNQUALIFIED
    )
    assert not result.linux_directory_fd_retained
    _blocked(result)


def test_requirement_drift_refused_without_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform != "linux":
        pytest.skip("Linux requirement gate")
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = probe.probe_linux_disposable_dirfd_replace(
        probe.PrivateDirfdScratchScenario.NORMAL
    )
    assert result.state is probe.PrivateDirfdScratchState.REQUIREMENT_DRIFT_REFUSED
    _blocked(result)


def test_no_caller_path_callbacks_or_notes_capabilities() -> None:
    source_path = probe.__file__
    assert source_path is not None
    source = Path(source_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "probe_linux_disposable_dirfd_replace"
    )
    assert len(fn.args.args) == 1 and fn.args.args[0].arg == "scenario"
    assert not fn.args.kwarg and not fn.args.vararg
    assert "os.replace(_STAGE, _LIVE, src_dir_fd=fd, dst_dir_fd=fd)" in source
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
