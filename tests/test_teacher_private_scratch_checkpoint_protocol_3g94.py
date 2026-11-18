"""#238 3G94: executable checkpoint interruption/recovery, scratch only."""

from __future__ import annotations

import ast
import stat
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_checkpoint_protocol as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


_NO_AUTH = (
    "production_mutation_admitted",
    "automatic_replay_allowed",
    "automatic_retry_allowed",
    "journal_retirement_allowed",
    "notes_records_available",
    "noncooperating_writer_exclusion_qualified",
    "atomic_content_compare_and_swap_qualified",
    "directory_crash_durability_qualified",
    "multi_document_atomic_commit_qualified",
)


def _blocked(result: probe.PrivateCheckpointReview) -> None:
    assert type(result) is probe.PrivateCheckpointReview
    for key in _NO_AUTH:
        assert getattr(result, key) is False
    assert (
        repr(result)
        == "PrivateCheckpointReview(scratch_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize(
    "scenario",
    [
        probe.PrivateCheckpointScenario.PREPARED,
        probe.PrivateCheckpointScenario.REGISTRY_INTENT,
        probe.PrivateCheckpointScenario.REGISTRY_INSTALLED,
        probe.PrivateCheckpointScenario.REGISTRY_CONFIRMED,
        probe.PrivateCheckpointScenario.DESCRIPTOR_INTENT,
        probe.PrivateCheckpointScenario.DESCRIPTOR_INSTALLED,
        probe.PrivateCheckpointScenario.BOTH_PENDING_REVIEW,
    ],
)
def test_interrupted_checkpoint_explicitly_resumes_and_remains_pending(
    scenario: probe.PrivateCheckpointScenario,
) -> None:
    result = probe.probe_disposable_checkpoint_protocol(scenario)
    assert result.state is (
        probe.PrivateCheckpointState.ALREADY_COMPLETE_PENDING_HOLD
        if scenario is probe.PrivateCheckpointScenario.BOTH_PENDING_REVIEW
        else probe.PrivateCheckpointState.EXPLICIT_SYNTHETIC_RESUME_PENDING_HOLD
    )
    assert result.interrupted_checkpoint == scenario.value
    assert result.phase_inferred_from_journal_and_images
    assert result.guarded_explicit_resume_invoked
    assert result.exact_synthetic_afterimages_verified
    assert result.journal_remains_pending
    assert result.resumptions_after_complete == 1
    assert not result.conflict_evidence_unchanged_until_scratch_cleanup
    _blocked(result)


@pytest.mark.parametrize(
    "scenario",
    [
        probe.PrivateCheckpointScenario.CONFLICT_JOURNAL,
        probe.PrivateCheckpointScenario.CONFLICT_REGISTRY,
        probe.PrivateCheckpointScenario.CONFLICT_STAGE,
        probe.PrivateCheckpointScenario.CONFLICT_CHECKPOINT_TEMP,
    ],
)
def test_conflicts_refuse_and_preserve_pending_evidence(
    scenario: probe.PrivateCheckpointScenario,
) -> None:
    result = probe.probe_disposable_checkpoint_protocol(scenario)
    assert result.state is probe.PrivateCheckpointState.CONFLICT_PRESERVED_HOLD
    assert result.interrupted_checkpoint == scenario.value
    assert result.phase_inferred_from_journal_and_images
    assert not result.guarded_explicit_resume_invoked
    assert not result.exact_synthetic_afterimages_verified
    assert result.journal_remains_pending
    assert result.conflict_evidence_unchanged_until_scratch_cleanup
    assert result.resumptions_after_complete == 0
    _blocked(result)


@pytest.mark.parametrize("bad", [None, "prepared", 0, True, Path("sample")])
def test_invalid_scenario_fails_before_any_scratch(bad: object) -> None:
    result = probe.probe_disposable_checkpoint_protocol(
        cast(probe.PrivateCheckpointScenario, bad)
    )
    assert result.state is probe.PrivateCheckpointState.INVALID_REQUEST_REFUSED
    _blocked(result)


def test_unsupported_platform_refuses_before_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = probe.probe_disposable_checkpoint_protocol(
        probe.PrivateCheckpointScenario.PREPARED
    )
    assert result.state is probe.PrivateCheckpointState.UNSUPPORTED_REFUSED
    _blocked(result)


def test_taxonomy_drift_fails_before_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = probe.probe_disposable_checkpoint_protocol(
        probe.PrivateCheckpointScenario.PREPARED
    )
    assert result.state is probe.PrivateCheckpointState.REQUIREMENT_DRIFT_REFUSED
    _blocked(result)


def test_public_api_is_closed_and_no_notes_are_exposed() -> None:
    origin = probe.__file__
    assert origin is not None
    source = Path(origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    public = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "probe_disposable_checkpoint_protocol"
    )
    assert [arg.arg for arg in public.args.args] == ["scenario"]
    assert not public.args.kwarg and not public.args.vararg
    for banned in (
        "commit_private_workspace_binding(",
        "activate_notes(",
        "retire_private_journal(",
        "ensure_workspace_root(",
    ):
        assert banned not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux owner mode")
def test_exclusive_scratch_lock_file_owner_mode_at_creation(tmp_path: Path) -> None:
    # Regression: Path.open("xb") used the process umask and could create a
    # 0644 file, which the Core existing-lock primitive must refuse.
    probe._exclusive(tmp_path, "synthetic.lock", b"0")
    lock = tmp_path / "synthetic.lock"
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    with locking.hold_existing_private_lock(lock):
        assert lock.read_bytes() == b"0"
