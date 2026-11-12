"""Core #238 3G76: bounded scratch-only process-death recovery completion."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_synthetic_recovery_completion.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g76_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _root(tmp_path: Path, mode: str) -> tuple[Any, Path, Path]:
    probe = _probe()
    source = SCRIPT.parents[1]
    death = probe._load_3g75(source)
    guard = death._load_3g74(source)
    harness = guard._load_triage(source)._load_previous(source)._load_3g71(source)
    root = tmp_path / ("core238_3g74_3g75_3g76_" + mode)
    root.mkdir()
    assert harness._run_case(root, mode) == probe._STATES[mode]
    return probe, root, source


def test_source_has_no_production_recovery_or_retirement_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    for needle in (
        "with guard._operation_lock(root):",
        "with ExitStack() as handles:",
        "_native_step(harness, stage, target)",
        "_attempt_directory_persistence(target.parent)",
        "_infer_read_only(root, source)",
        '"caller_phase_hint_accepted": False',
        '"production_mutation_admitted": False',
        '"automatic_replay_allowed": False',
        '"automatic_retry_allowed": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
    ):
        assert needle in source
    assert source.count("_native_step(harness, stage, target)") == 1
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "activate_notes(",
        "shutil.rmtree(",
        "subprocess.shell=True",
        "os.replace(",
        "os._exit(",
    ):
        assert forbidden not in source


def test_reject_unqualified_scratch_root_without_write(tmp_path: Path) -> None:
    probe = _probe()
    before = tuple(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match="outside_disposable_synthetic_scope"):
        probe._recover_one(tmp_path, SCRIPT.parents[1])
    assert tuple(tmp_path.iterdir()) == before


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="Native OS only")
@pytest.mark.parametrize("mode,steps", [("prepared", 2), ("registry", 1), ("both", 0)])
def test_native_scratch_recovery_exact_missing_steps_only(
    tmp_path: Path, mode: str, steps: int
) -> None:
    probe, root, source = _root(tmp_path, mode)
    state, count, request = probe._recover_one(root, source)
    assert state == probe._STATES[mode]
    assert count == steps
    assert type(request) is bool
    guard = probe._load_3g75(source)._load_3g74(source)
    assert guard._guarded_infer(root, source) == probe._COMPLETE
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1
    if mode == "both":
        assert request  # No directory-flush was required; no refusal occurred.


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="Native OS only")
@pytest.mark.parametrize(
    "fault,mode",
    [
        ("corrupt_journal", "registry"),
        ("unexpected_namespace", "both"),
        ("changed_descriptor", "prepared"),
        ("changed_stage", "registry"),
    ],
)
def test_ambiguous_recovery_does_not_mutate_any_files(
    tmp_path: Path, fault: str, mode: str
) -> None:
    probe, root, source = _root(tmp_path, mode)
    death = probe._load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    if fault == "changed_stage":
        from pds_core import (
            _teacher_private_recovery_canonical_journaled_restart as canon,
        )

        reader = triage._load_previous(source)
        paths = reader._paths(
            root, canon._canonical_fork_intent().witness.transaction_id
        )
        paths["descriptor_stage"].write_bytes(b"injected-synthetic-bad-stage")
    else:
        triage._damage_synthetic(root, fault, source)
    before = probe._snapshot(root)
    state, count, _ = probe._recover_one(root, source)
    assert state == probe._CONFLICT and count == 0
    assert probe._snapshot(root) == before


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="Native OS only")
def test_single_native_attempt_refusal_keeps_exact_pending_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe, root, source = _root(tmp_path, "prepared")
    calls: list[tuple[Path, Path]] = []

    def refuse(_harness: Any, stage: Path, target: Path) -> None:
        calls.append((stage, target))
        raise PermissionError("synthetic-native-refusal")

    monkeypatch.setattr(probe, "_native_step", refuse)
    before = probe._snapshot(root)
    with pytest.raises(PermissionError, match="synthetic-native-refusal"):
        probe._recover_one(root, source)
    assert len(calls) == 1
    assert probe._snapshot(root) == before
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX partial native refusal")
def test_second_native_attempt_refusal_preserves_first_step_and_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe, root, source = _root(tmp_path, "prepared")
    calls = [0]

    def partially_refuse(harness: Any, stage: Path, target: Path) -> None:
        calls[0] += 1
        if calls[0] == 2:
            raise PermissionError("second-native-attempt-refused")
        harness._replace_once(stage, target)

    monkeypatch.setattr(probe, "_native_step", partially_refuse)
    with pytest.raises(PermissionError, match="second-native-attempt-refused"):
        probe._recover_one(root, source)
    assert calls[0] == 2
    guard = probe._load_3g75(source)._load_3g74(source)
    assert guard._guarded_infer(root, source) == probe._STATES["registry"]
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1
