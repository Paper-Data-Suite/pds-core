"""Core #238 3G71: exact native two-document scratch restart and no authority."""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_two_document_restart.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g71_probe_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_enforces_non_authorizing_two_document_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    assert source.count("_replace_once(paths[") == 2
    assert source.count("os.replace(source, destination)") == 1
    assert source.count("windows._replace_open_target_posix(source, destination)") == 1
    for token in (
        "_canonical_fork_intent()",
        "_held_file_ids(paths)",
        '_named_id(paths["journal"])',
        '"prepared_hold"',
        '"registry_after_descriptor_pending_hold"',
        '"both_after_journal_pending_hold"',
        '"production_mutation_admitted": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
        '"transaction_commit_qualified": False',
        "production_write_barrier_changed",
    ):
        assert token in source
    for forbidden in (
        "commit_private_workspace_binding",
        "retire_private_journal(",
        "activate_notes(",
        "shutil.rmtree(",
        "os.system(",
    ):
        assert forbidden not in source


def test_exclusive_scratch_create_preserves_existing(tmp_path: Path) -> None:
    probe = _probe()
    target = tmp_path / "synthetic"
    probe._write_new(target, b"synthetic-original")
    with pytest.raises(FileExistsError):
        probe._write_new(target, b"synthetic-replacement")
    assert target.read_bytes() == b"synthetic-original"


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="Native target only")
@pytest.mark.parametrize(
    "mode,checkpoint",
    [
        ("prepared", "prepared_hold"),
        ("registry", "registry_after_descriptor_pending_hold"),
        ("both", "both_after_journal_pending_hold"),
    ],
)
def test_real_native_scratch_two_document_restart(
    tmp_path: Path, mode: str, checkpoint: str
) -> None:
    probe = _probe()
    result = probe._run_case(tmp_path, mode)
    assert result == checkpoint
    journal_files = list((tmp_path / "private" / "transactions").iterdir())
    assert len(journal_files) == 1
    assert journal_files[0].is_file()


def test_invalid_mode_refuses_without_creating_files(tmp_path: Path) -> None:
    probe = _probe()
    with pytest.raises(ValueError, match="unexpected_scratch_phase"):
        probe._run_case(tmp_path, "invalid")
    assert not tuple(tmp_path.iterdir())


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX refusal probe")
def test_mid_two_document_failure_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe()
    calls = 0
    real = os.replace

    def partially_fail(src: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("synthetic descriptor refusal")
        real(src, target)

    monkeypatch.setattr(os, "replace", partially_fail)
    with pytest.raises(PermissionError):
        probe._run_case(tmp_path, "both")
    assert calls == 2
    assert len(list((tmp_path / "private" / "transactions").iterdir())) == 1
    assert (tmp_path / "private" / "registry.json").is_file()
    assert (
        tmp_path / "workspace" / ".pds" / "teacher-private-association.json"
    ).is_file()
