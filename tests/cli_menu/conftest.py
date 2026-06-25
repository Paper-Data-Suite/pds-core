"""Shared helpers for interactive standards menu tests."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pds_core.cli import main


def run_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    input_text: str,
) -> tuple[int, str, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(input_text))
    code = main(["--workspace", str(tmp_path), "standards", "menu"])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def library_file(tmp_path: Path) -> Path:
    return tmp_path / "standards" / "library.json"


def assert_durable_standard_id_guidance(out: str) -> None:
    assert "Use the full durable standard_id, not only the display code." in out
    assert "Correct example: njsls-ela:L.KL.11-12.2" in out
    assert "Not enough: L.KL.11-12.2" in out
