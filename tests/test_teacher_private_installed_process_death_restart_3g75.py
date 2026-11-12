"""Core #238 3G75: hard-death native scratch checkpoints remain non-authorizing."""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_process_death_restart.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g75_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_limits_hard_exit_to_synthetic_native_custody() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    for token in (
        "os._exit(DEATH_CODES[mode])",
        "with guarded._operation_lock(root):",
        "with harness._held_file_ids(paths) as held:",
        "harness._replace_once(paths[",
        "guarded._ask_child(root, source, wheel)",
        '"journal_retirement_allowed": False',
        '"automatic_replay_allowed": False',
        '"automatic_retry_allowed": False',
        '"production_mutation_admitted": False',
        '"directory_crash_durability_qualified": False',
        '"noncooperating_writer_exclusion_qualified": False',
    ):
        assert token in source
    assert source.count("harness._replace_once(paths[") == 2
    assert source.count("os._exit(") == 1
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "os.replace(",
        "shutil.rmtree(",
        "activate_notes(",
        "subprocess.shell=True",
    ):
        assert forbidden not in source


def test_bad_phase_never_enters_scratch(tmp_path: Path) -> None:
    probe = _probe()
    original = tuple(tmp_path.iterdir())
    with pytest.raises(ValueError, match="invalid_forced_death_phase"):
        probe._run_child(tmp_path, SCRIPT.parents[1], "invalid")
    with pytest.raises(ValueError, match="invalid_forced_death_phase"):
        probe._force_death(tmp_path, SCRIPT.parents[1], tmp_path, "invalid")
    assert tuple(tmp_path.iterdir()) == original


def test_bad_root_never_enters_native_mutation(tmp_path: Path) -> None:
    probe = _probe()
    with pytest.raises(RuntimeError, match="not_disposable_synthetic_root"):
        probe._run_child(tmp_path, SCRIPT.parents[1], "registry")
    assert not tuple(tmp_path.iterdir())


class _SyntheticDeath(Exception):
    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__("synthetic-hard-exit-intercepted")


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native platform")
@pytest.mark.parametrize(
    "mode",
    ["prepared", "registry", "both"],
)
def test_writer_holds_native_custody_to_forced_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Intercept hard exit so pytest never terminates; inspect real file state."""
    probe = _probe()
    source = SCRIPT.parents[1]
    guarded = probe._load_3g74(source)
    harness = guarded._load_triage(source)._load_previous(source)._load_3g71(source)
    root = tmp_path / ("core238_3g74_3g75_" + mode)
    root.mkdir()
    assert harness._run_case(root, "prepared") == probe.STATES["prepared"]

    def intercepted(code: int) -> NoReturn:
        raise _SyntheticDeath(code)

    monkeypatch.setattr(os, "_exit", intercepted)
    with pytest.raises(_SyntheticDeath) as caught:
        probe._run_child(root, source, mode)
    assert caught.value.code == probe.DEATH_CODES[mode]
    assert guarded._guarded_infer(root, source) == probe.STATES[mode]
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native platform")
def test_changed_pending_journal_after_intercepted_death_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe()
    source = SCRIPT.parents[1]
    guarded = probe._load_3g74(source)
    triage = guarded._load_triage(source)
    harness = triage._load_previous(source)._load_3g71(source)
    root = tmp_path / "core238_3g74_3g75_corrupt"
    root.mkdir()
    assert harness._run_case(root, "prepared") == probe.STATES["prepared"]

    def intercepted(code: int) -> NoReturn:
        raise _SyntheticDeath(code)

    monkeypatch.setattr(os, "_exit", intercepted)
    with pytest.raises(_SyntheticDeath):
        probe._run_child(root, source, "registry")
    triage._damage_synthetic(root, "corrupt_journal", source)
    assert guarded._guarded_infer(root, source) == probe.CONFLICT
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1
