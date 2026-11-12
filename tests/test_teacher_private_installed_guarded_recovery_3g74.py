"""Core #238 3G74: operation-held native recovery decisions, scratch only."""

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
    / "verify_issue238_installed_guarded_recovery_custody.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g74_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_has_fixed_synthetic_scope_and_permanent_no_write() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    for required in (
        "with _operation_lock(root):",
        "with ExitStack() as stack:",
        "_open_native(stack, path, directory)",
        "_retained_id(opened, directory)",
        "_infer_read_only(root, source)",
        '"cooperative_lock_contention": LOCKED',
        '"production_mutation_admitted": False',
        '"automatic_replay_allowed": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
        '"noncooperating_writer_exclusion_qualified": False',
    ):
        assert required in source
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "os.replace(",
        "shutil.rmtree(",
        "activate_notes(",
        "subprocess.shell=True",
    ):
        assert forbidden not in source


def test_unsupported_root_never_creates_lock(tmp_path: Path) -> None:
    probe = _probe()
    with pytest.raises(probe._CustodyRefused):
        with probe._operation_lock(tmp_path):
            pytest.fail("Unqualified root admitted")
    assert not tuple(tmp_path.parent.glob(tmp_path.name + "*.operation-lock"))


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native OS only")
@pytest.mark.parametrize("mode", ["prepared", "registry", "both"])
def test_guarded_checkpoint_inference_uses_exact_native_custody(
    tmp_path: Path, mode: str
) -> None:
    probe = _probe()
    source = SCRIPT.parents[1]
    triage = probe._load_triage(source)
    harness = triage._load_previous(source)._load_3g71(source)
    root = tmp_path / ("core238_3g74_" + mode)
    root.mkdir()
    expected = probe.STATES[mode]
    assert harness._run_case(root, mode) == expected
    assert probe._guarded_infer(root, source) == expected
    assert (root / "private" / "transactions").is_dir()
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native OS only")
@pytest.mark.parametrize(
    "fault,mode",
    [
        ("corrupt_journal", "prepared"),
        ("unexpected_namespace", "registry"),
        ("changed_descriptor", "both"),
    ],
)
def test_guarded_checkpoint_refuses_corrupt_evidence(
    tmp_path: Path, fault: str, mode: str
) -> None:
    probe = _probe()
    source = SCRIPT.parents[1]
    triage = probe._load_triage(source)
    harness = triage._load_previous(source)._load_3g71(source)
    root = tmp_path / ("core238_3g74_" + fault)
    root.mkdir()
    assert harness._run_case(root, mode) == probe.STATES[mode]
    triage._damage_synthetic(root, fault, source)
    assert probe._guarded_infer(root, source) == probe.CONFLICT
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native OS only")
def test_adversarial_image_change_between_guarded_reads_preserves_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe()
    source = SCRIPT.parents[1]
    triage = probe._load_triage(source)
    harness = triage._load_previous(source)._load_3g71(source)
    root = tmp_path / "core238_3g74_ambiguous"
    root.mkdir()
    assert harness._run_case(root, "prepared") == probe.STATES["prepared"]
    real = triage._infer_read_only
    calls = [0]

    def change_after_first(observed: Path, checkout: Path) -> str:
        outcome = real(observed, checkout)
        calls[0] += 1
        if calls[0] == 1:
            (observed / "private" / "registry.json").write_bytes(
                b"synthetic-mutated-in-place"
            )
        return cast(str, outcome)

    monkeypatch.setattr(triage, "_infer_read_only", change_after_first)
    monkeypatch.setattr(probe, "_load_triage", lambda _source: triage)
    assert probe._guarded_infer(root, source) == probe.CONFLICT
    assert calls[0] == 2
    assert len(tuple((root / "private" / "transactions").iterdir())) == 1


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX advisory locking probe")
def test_cooperative_synthetic_lock_conflicts_and_releases(tmp_path: Path) -> None:
    probe = _probe()
    root = tmp_path / "core238_3g74_lock"
    root.mkdir()
    with probe._operation_lock(root):
        with pytest.raises(probe._LockBusy):
            with probe._operation_lock(root):
                pytest.fail("Concurrent operation entered custody")
    with probe._operation_lock(root):
        pass
