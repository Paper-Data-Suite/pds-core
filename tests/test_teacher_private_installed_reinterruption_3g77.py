"""Core #238 3G77: recovery-of-recovery process-death refusal contract."""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, cast

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_recovery_reinterruption.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g77_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthetic_scoped_process_death_never_enables_production() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    for token in (
        "os._exit(_CASES[fault][0])",
        'setattr(recovery, "_native_step", _interrupted_step)',
        "recovery._recover_one(root, source)",
        "guard._ask_child(root, source, wheel)",
        "recovery._ask_recovery(root, source, wheel)",
        '"journal_retirement_allowed": False',
        '"automatic_retry_allowed": False',
        '"automatic_replay_allowed": False',
        '"production_mutation_admitted": False',
        '"directory_crash_durability_qualified": False',
        '"noncooperating_writer_exclusion_qualified": False',
    ):
        assert token in source
    assert source.count("original(harness, stage, target)") == 1
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "activate_notes(",
        "os.replace(",
        "shutil.rmtree(",
        "subprocess.shell=True",
    ):
        assert forbidden not in source


class _ProcessExit(Exception):
    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__("test_injected_hard_exit")


@pytest.mark.parametrize(
    "fault,exit_code,writes",
    [
        ("before_registry", 81, ()),
        ("after_registry", 82, ("registry.json",)),
        ("after_descriptor", 83, ("registry.json", "teacher-private-association.json")),
    ],
)
def test_exact_bounded_recovery_crash_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    exit_code: int,
    writes: tuple[str, ...],
) -> None:
    """Intercept the hard exit; real processes in installed gate never unwind."""
    probe = _probe()
    root = tmp_path / ("core238_3g74_3g75_3g76_3g77_" + fault)
    root.mkdir()
    fake = ModuleType("synthetic_previous_recovery")
    completed: list[str] = []

    def native(_harness: ModuleType, stage: Path, target: Path) -> None:
        completed.append(target.name)

    def recover(_root: Path, _source: Path) -> tuple[str, int, bool]:
        native_step = getattr(fake, "_native_step")
        native_step(fake, root / "a.registry-stage", root / "registry.json")
        native_step(
            fake,
            root / "b.descriptor-stage",
            root / "teacher-private-association.json",
        )
        return "prepared_hold", 2, True

    setattr(fake, "_native_step", native)
    setattr(fake, "_recover_one", recover)
    monkeypatch.setattr(probe, "_load_previous", lambda _source: fake)

    def terminate(code: int) -> NoReturn:
        raise _ProcessExit(code)

    monkeypatch.setattr(os, "_exit", terminate)
    with pytest.raises(_ProcessExit) as found:
        probe._die_in_recovery(root, SCRIPT.parents[1], fault)
    assert found.value.code == exit_code
    assert tuple(completed) == writes
    assert getattr(fake, "_native_step") is native
    assert not tuple(root.iterdir())


@pytest.mark.parametrize("invalid", ["", "registry", "none", "after_unknown", None])
def test_invalid_fault_refused_before_any_synthetic_io(
    tmp_path: Path, invalid: object
) -> None:
    probe = _probe()
    with pytest.raises(ValueError, match="invalid_synthetic_recovery_fault"):
        probe._die_in_recovery(tmp_path, SCRIPT.parents[1], cast(str, invalid))
    assert not tuple(tmp_path.iterdir())


def test_unqualified_root_refused_before_recovery_entry(tmp_path: Path) -> None:
    probe = _probe()
    with pytest.raises(RuntimeError, match="non_disposable_recovery_scope"):
        probe._die_in_recovery(tmp_path, SCRIPT.parents[1], "after_registry")
    assert not tuple(tmp_path.iterdir())


def test_force_crash_requires_exact_exit_and_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe()
    root = tmp_path / "core238_3g74_3g75_3g76_3g77_check"
    root.mkdir()
    observed: list[tuple[str, ...]] = []

    def fake_run(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        observed.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 82, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    probe._force_crash(
        root, SCRIPT.parents[1], tmp_path / "wheel.whl", "after_registry"
    )
    assert len(observed) == 1 and "--child-fault" in observed[0]
    assert "--child-root" in observed[0] and "-I" in observed[0]

    def wrong_code(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", wrong_code)
    with pytest.raises(RuntimeError, match="recovery_death_not_qualified"):
        probe._force_crash(
            root, SCRIPT.parents[1], tmp_path / "wheel.whl", "after_registry"
        )


def test_full_installed_gate_does_not_rely_on_test_interception() -> None:
    probe = _probe()
    assert probe._CASES == {
        "before_registry": (81, "prepared_hold", 2),
        "after_registry": (82, "registry_after_descriptor_pending_hold", 1),
        "after_descriptor": (83, "both_after_journal_pending_hold", 0),
    }
    assert sys.platform
