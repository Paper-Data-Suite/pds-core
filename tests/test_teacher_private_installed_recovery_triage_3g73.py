"""Core #238 3G73: infer synthetic restart state, refuse tampering, no replay."""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_issue238_installed_recovery_triage.py"


def _probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("core238_3g73_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_is_advisory_and_has_no_recovery_writer() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    for required in (
        '"requires_caller_claimed_checkpoint": False',
        '"production_mutation_admitted": False',
        '"automatic_replay_allowed": False',
        '"automatic_retry_allowed": False',
        '"journal_retirement_allowed": False',
        '"transaction_commit_qualified": False',
        '"directory_crash_durability_qualified": False',
        '"--child-root"',
        '"-I"',
        "_infer_read_only(root, source)",
        "_ask_fresh_interpreter(root, source, wheel)",
    ):
        assert required in source
    for forbidden in (
        "os.replace(",
        "retire_private_journal(",
        "commit_private_workspace_binding(",
        "def activate_notes(",
        "shutil.rmtree(",
        "subprocess.Popen(",
    ):
        assert forbidden not in source
    assert source.count("_damage_synthetic(root, fault, source)") == 1


@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native scratch only"
)
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("prepared", "prepared_hold"),
        ("registry", "registry_after_descriptor_pending_hold"),
        ("both", "both_after_journal_pending_hold"),
    ],
)
def test_infers_without_phase_hint_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: str
) -> None:
    probe = _probe()
    reader = probe._load_previous(ROOT)
    harness = reader._load_3g71(ROOT)
    assert harness._run_case(tmp_path, mode) == expected

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Read-only triage attempted file replacement")

    monkeypatch.setattr(os, "replace", forbidden)
    before = {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert probe._infer_read_only(tmp_path, ROOT) == expected
    after = {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert after == before
    journal = next((tmp_path / "private" / "transactions").iterdir())
    assert journal.read_bytes() == before[journal.relative_to(tmp_path).as_posix()]


@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native scratch only"
)
@pytest.mark.parametrize(
    "fault,mode",
    [
        ("corrupt_journal", "prepared"),
        ("unexpected_namespace", "registry"),
        ("changed_descriptor", "both"),
    ],
)
def test_conflicting_scratch_is_preserved_without_replay(
    tmp_path: Path, fault: str, mode: str
) -> None:
    probe = _probe()
    reader = probe._load_previous(ROOT)
    harness = reader._load_3g71(ROOT)
    assert harness._run_case(tmp_path, mode) == probe.STATES[mode]
    probe._damage_synthetic(tmp_path, fault, ROOT)
    before = {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert probe._infer_read_only(tmp_path, ROOT) == probe.CONFLICT
    after = {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert after == before
    assert len(tuple((tmp_path / "private" / "transactions").iterdir())) == 1


def test_empty_scratch_is_not_mistaken_for_unbound_collection(
    tmp_path: Path,
) -> None:
    probe = _probe()
    assert probe._infer_read_only(tmp_path, ROOT) == probe.CONFLICT
    assert not tuple(tmp_path.iterdir())


def test_invalid_scratch_fault_refused_before_touching_files(tmp_path: Path) -> None:
    probe = _probe()
    with pytest.raises(ValueError, match="unsupported_scratch_fault"):
        probe._damage_synthetic(tmp_path, "unknown", ROOT)
    assert not tuple(tmp_path.iterdir())
