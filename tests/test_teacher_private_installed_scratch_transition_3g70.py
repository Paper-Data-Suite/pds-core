"""Core #238 3G70: installed candidate scratch-only native acceptance harness."""

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
    / "verify_issue238_installed_scratch_transition.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g70_probe_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_contains_one_windows_native_and_one_posix_attempt() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    assert source.count("replacement._replace_open_target_posix(source, target)") == 1
    assert source.count("os.replace(source, target)") == 1
    assert "--source-checkout" in source
    assert "_verify_permanent_barrier()" in source
    assert '"production_mutation_admitted": False' in source
    assert '"notes_records_available": False' in source
    assert '"transaction_commit_qualified": False' in source
    assert '"journal_retirement_qualified": False' in source
    assert '"directory_crash_durability_qualified": False' in source
    assert "os.system(" not in source
    assert "subprocess.run(" not in source


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX native scratch only")
def test_posix_replaces_only_owned_scratch_pair(tmp_path: Path) -> None:
    probe = _probe()
    probe._native_posix_replace(tmp_path)
    assert not (tmp_path / "stage").exists()
    assert (tmp_path / "registry.json").read_bytes() == probe._AFTER
    assert sorted(p.name for p in tmp_path.iterdir()) == ["registry.json"]


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX native scratch only")
def test_posix_refused_mutation_has_no_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probe = _probe()
    called = 0

    def refuse(_src: Path, _dst: Path) -> None:
        nonlocal called
        called += 1
        raise PermissionError("synthetic refusal")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(PermissionError):
        probe._native_posix_replace(tmp_path)
    assert called == 1
    assert (tmp_path / "stage").read_bytes() == probe._AFTER
    assert (tmp_path / "registry.json").read_bytes() == probe._BEFORE


def test_scratch_probe_contains_no_public_binding_api() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "commit_private_workspace_binding",
        "retire_private_journal",
        "activate_notes",
        "chmod(",
        "chown(",
        "rmtree(",
    ):
        assert forbidden not in script
