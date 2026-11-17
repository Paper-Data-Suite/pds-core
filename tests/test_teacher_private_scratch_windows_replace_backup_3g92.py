"""Core #238 3G92: native Windows ReplaceFileW backup is scratch-only."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_windows_replace_backup as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _blocked(result: probe.PrivateWindowsReplaceBackupReview) -> None:
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
        assert getattr(result, field) is False
    assert repr(result) == (
        "PrivateWindowsReplaceBackupReview(disposable_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize("bad", [None, "normal_backup", True, 1, Path("data")])
def test_reject_untrusted_scenario(bad: object) -> None:
    result = probe.probe_windows_disposable_replace_backup(
        cast(probe.PrivateWindowsReplaceBackupScenario, bad)
    )
    assert (
        result.state is probe.PrivateWindowsReplaceBackupState.INVALID_REQUEST_REFUSED
    )
    _blocked(result)


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_backup_preserves_original_and_pending_journal() -> None:
    result = probe.probe_windows_disposable_replace_backup(
        probe.PrivateWindowsReplaceBackupScenario.NORMAL_BACKUP
    )
    assert (
        result.state
        is probe.PrivateWindowsReplaceBackupState.NATIVE_BACKUP_PRESERVED_SCRATCH_ONLY
    )
    assert result.native_parent_retained_during_operation
    assert result.cooperative_lock_held
    assert result.exact_preimages_rechecked
    assert result.native_replacefile_called
    assert result.original_backup_verified
    assert result.new_registry_verified
    assert result.synthetic_journal_preserved
    _blocked(result)


@pytest.mark.parametrize(
    "scenario,expected",
    [
        (
            probe.PrivateWindowsReplaceBackupScenario.LIVE_PREIMAGE_DRIFT,
            probe.PrivateWindowsReplaceBackupState.LIVE_DRIFT_REFUSED,
        ),
        (
            probe.PrivateWindowsReplaceBackupScenario.STAGE_PREIMAGE_DRIFT,
            probe.PrivateWindowsReplaceBackupState.STAGE_DRIFT_REFUSED,
        ),
    ],
)
@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_preimage_drift_refuses_before_replace(
    scenario: probe.PrivateWindowsReplaceBackupScenario,
    expected: probe.PrivateWindowsReplaceBackupState,
) -> None:
    result = probe.probe_windows_disposable_replace_backup(scenario)
    assert result.state is expected
    assert result.native_parent_retained_during_operation
    assert result.exact_preimages_rechecked
    assert not result.native_replacefile_called
    assert not result.original_backup_verified
    assert not result.new_registry_verified
    assert result.synthetic_journal_preserved
    _blocked(result)


def test_non_windows_explicit_refusal_and_no_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    result = probe.probe_windows_disposable_replace_backup(
        probe.PrivateWindowsReplaceBackupScenario.NORMAL_BACKUP
    )
    assert (
        result.state
        is probe.PrivateWindowsReplaceBackupState.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED
    )
    assert not result.native_replacefile_called
    _blocked(result)


def test_requirement_drift_refuses_before_windows_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = probe.probe_windows_disposable_replace_backup(
        probe.PrivateWindowsReplaceBackupScenario.NORMAL_BACKUP
    )
    assert (
        result.state is probe.PrivateWindowsReplaceBackupState.REQUIREMENT_DRIFT_REFUSED
    )
    _blocked(result)


def test_fixed_api_and_production_capability_barrier() -> None:
    origin = probe.__file__
    assert origin is not None
    tree = ast.parse(Path(origin).read_text(encoding="utf-8"))
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "probe_windows_disposable_replace_backup"
    )
    assert len(fn.args.args) == 1 and fn.args.args[0].arg == "scenario"
    assert not fn.args.kwarg and not fn.args.vararg
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
