"""Core #238 3G78: repeated recovery is native no-op, journal remains pending."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any, cast

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_recovery_idempotence.py"
)
_PREFIX = "core238_3g74_3g75_3g76_3g77_3g78_"


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g78_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixtures() -> tuple[Any, Any, Any, Any]:
    probe = _probe()
    recovery = probe._load_previous(SCRIPT.parents[1])
    death = recovery._load_3g75(SCRIPT.parents[1])
    guard = death._load_3g74(SCRIPT.parents[1])
    harness = (
        guard._load_triage(SCRIPT.parents[1])
        ._load_previous(SCRIPT.parents[1])
        ._load_3g71(SCRIPT.parents[1])
    )
    return probe, recovery, guard, harness


def test_source_non_authorizing_and_exact_noop_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    for required in (
        "recovery._ask_recovery(root, source, wheel)",
        "_canonical_snapshot(root, source)",
        "_assert_unchanged(root, source, original)",
        "with guard._operation_lock(root):",
        '"post_completion_repeated_recovery_steps": repeats',
        '"canonical_journal_preserved": True',
        '"production_mutation_admitted": False',
        '"automatic_replay_allowed": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
        '"noncooperating_writer_exclusion_qualified": False',
    ):
        assert required in source
    for forbidden in (
        "os.replace(",
        "retire_private_journal(",
        "commit_private_workspace_binding(",
        "activate_notes(",
        "shutil.rmtree(",
    ):
        assert forbidden not in source


def test_refuse_untrusted_root_before_read_or_write(tmp_path: Path) -> None:
    probe = _probe()
    with pytest.raises(RuntimeError, match="unqualified_disposable_scratch_root"):
        probe._canonical_snapshot(tmp_path, SCRIPT.parents[1])
    with pytest.raises(RuntimeError, match="unqualified_disposable_scratch_root"):
        probe._damage_completed(tmp_path, SCRIPT.parents[1], "changed_registry")
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("invalid", ["", "journal_removed", "stage", "other", None])
def test_invalid_damage_refused_before_scratch_mutation(
    tmp_path: Path, invalid: object
) -> None:
    probe = _probe()
    root = tmp_path / (_PREFIX + "invalid")
    root.mkdir()
    with pytest.raises(ValueError, match="unsupported_completed_scratch_fault"):
        probe._damage_completed(root, SCRIPT.parents[1], cast(str, invalid))
    assert not tuple(root.iterdir())


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native OS only")
def test_completed_checkpoint_recovery_has_zero_native_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe, recovery, guard, harness = _fixtures()
    source = SCRIPT.parents[1]
    root = tmp_path / (_PREFIX + "no-op")
    root.mkdir()
    assert harness._run_case(root, "both") == probe._COMPLETE
    before = probe._canonical_snapshot(root, source)
    writes = [0]

    def forbidden(_harness: Any, _stage: Path, _target: Path) -> None:
        writes[0] += 1
        pytest.fail("Completed synthetic recovery performed duplicate native rename")

    monkeypatch.setattr(recovery, "_native_step", forbidden)
    previous, count, _ = recovery._recover_one(root, source)
    assert previous == probe._COMPLETE
    assert count == 0
    assert writes[0] == 0
    assert guard._guarded_infer(root, source) == probe._COMPLETE
    probe._assert_unchanged(root, source, before)


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native OS only")
@pytest.mark.parametrize(
    "fault",
    [
        "corrupt_journal",
        "unexpected_namespace",
        "changed_descriptor",
        "changed_registry",
    ],
)
def test_corrupt_completed_checkpoint_refuses_without_native_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    probe, recovery, _guard, harness = _fixtures()
    source = SCRIPT.parents[1]
    root = tmp_path / (_PREFIX + fault)
    root.mkdir()
    assert harness._run_case(root, "both") == probe._COMPLETE
    probe._damage_completed(root, source, fault)
    prior = recovery._snapshot(root)
    calls = [0]

    def forbidden(_harness: Any, _stage: Path, _target: Path) -> None:
        calls[0] += 1
        pytest.fail("Corrupted completed checkpoint attempted mutation")

    monkeypatch.setattr(recovery, "_native_step", forbidden)
    for _index in range(2):
        state, steps, _ = recovery._recover_one(root, source)
        assert state == probe._CONFLICT
        assert steps == 0
        assert recovery._snapshot(root) == prior
    assert calls[0] == 0


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native OS only")
def test_concurrent_owner_lock_refuses_and_releases(tmp_path: Path) -> None:
    probe, recovery, guard, harness = _fixtures()
    source = SCRIPT.parents[1]
    root = tmp_path / (_PREFIX + "lock")
    root.mkdir()
    assert harness._run_case(root, "prepared") == "prepared_hold"
    before = recovery._snapshot(root)
    with guard._operation_lock(root):
        with pytest.raises(Exception) as blocked:
            recovery._recover_one(root, source)
        assert type(blocked.value).__name__ == "_LockBusy"
        assert type(blocked.value).__module__.startswith("core238_3g74_")
        assert isinstance(blocked.value.__cause__, (BlockingIOError, PermissionError))
        assert recovery._snapshot(root) == before
    initial, steps, _ = recovery._recover_one(root, source)
    assert initial == "prepared_hold" and steps == 2
    last = probe._canonical_snapshot(root, source)
    again, count, _ = recovery._recover_one(root, source)
    assert again == probe._COMPLETE and count == 0
    probe._assert_unchanged(root, source, last)
