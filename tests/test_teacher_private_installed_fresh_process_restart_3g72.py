"""Core #238 3G72: independent synthetic restart with journal pending."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_issue238_installed_separate_process_restart.py"


def _probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("core238_g72_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_is_non_authorizing_and_read_only_child() -> None:
    code = SCRIPT.read_text(encoding="utf-8")
    ast.parse(code)
    assert '"production_mutation_admitted": False' in code
    assert '"journal_retirement_allowed": False' in code
    assert '"directory_crash_durability_qualified": False' in code
    assert '"transaction_commit_qualified": False' in code
    assert '"automatic_replay_allowed": False' in code
    assert '"--child-checkpoint"' in code
    assert '"-I"' in code
    assert "_request_persistence(root, mode)" in code
    assert "_fresh_process(root, mode, source, wheel)" in code
    for forbidden in (
        "def commit_private_workspace_binding",
        "retire_private_journal(",
        "def activate_notes(",
        "os.replace(",
        "shutil.rmtree(",
        "subprocess.Popen(",
    ):
        assert forbidden not in code


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("prepared", "prepared_hold"),
        ("registry", "registry_after_descriptor_pending_hold"),
        ("both", "both_after_journal_pending_hold"),
    ],
)
@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native target")
def test_native_checkpoint_child_read_only(
    tmp_path: Path, mode: str, expected: str
) -> None:
    probe = _probe()
    previous = probe._load_3g71(ROOT)
    assert previous._run_case(tmp_path, mode) == expected
    assert probe._read_only_restart(tmp_path, mode, ROOT) == expected
    journal = tuple((tmp_path / "private" / "transactions").iterdir())
    assert len(journal) == 1 and journal[0].is_file()


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native target")
def test_corrupt_journal_is_refused_without_replay(tmp_path: Path) -> None:
    probe = _probe()
    old = probe._load_3g71(ROOT)
    assert (
        old._run_case(tmp_path, "registry") == "registry_after_descriptor_pending_hold"
    )
    journal = next((tmp_path / "private" / "transactions").iterdir())
    journal.write_bytes(b"synthetic-corrupted-journal")
    with pytest.raises(RuntimeError, match="restarted_image_conflict_preserve"):
        probe._read_only_restart(tmp_path, "registry", ROOT)
    assert journal.read_bytes() == b"synthetic-corrupted-journal"


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native target")
def test_unexpected_directory_entry_refused(tmp_path: Path) -> None:
    probe = _probe()
    old = probe._load_3g71(ROOT)
    assert old._run_case(tmp_path, "both") == "both_after_journal_pending_hold"
    foreign = tmp_path / "private" / "unrecognized-synthetic"
    foreign.write_bytes(b"unexpected")
    with pytest.raises(RuntimeError, match="restarted_namespace_conflict_preserve"):
        probe._read_only_restart(tmp_path, "both", ROOT)
    assert foreign.read_bytes() == b"unexpected"


def test_invalid_mode_refused_before_files(tmp_path: Path) -> None:
    probe = _probe()
    with pytest.raises(ValueError, match="invalid_restart_checkpoint"):
        probe._read_only_restart(tmp_path, "other", ROOT)
    assert not tuple(tmp_path.iterdir())
