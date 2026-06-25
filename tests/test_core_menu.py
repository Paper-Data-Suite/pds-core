"""Tests for the teacher-facing pds-core main menu."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pds_core.cli import main as pds_core_main
from pds_core.cli_support import screen
from pds_core.core_menu import main


def run_core_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    input_text: str,
) -> tuple[int, str, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(input_text))
    code = main(["--workspace", str(tmp_path)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_console_scripts_are_declared() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in pyproject
    assert 'pds-core = "pds_core.cli:main"' in pyproject
    assert 'core = "pds_core.core_menu:main"' in pyproject


def test_core_menu_opens_and_exits_via_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "2\n")

    assert code == 0
    assert "Paper Data Suite Core" in out
    assert "1. Standards Management" in out
    assert "2. Back / Exit" in out
    assert "Back." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_core_menu_handles_invalid_blank_and_eof_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "nope\n\n")

    assert code == 0
    assert "Invalid menu choice. Please try again." in out
    assert "Back." in out
    assert "Traceback" not in err
    assert err == ""
    assert list(tmp_path.iterdir()) == []

    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "")

    assert code == 0
    assert "Paper Data Suite Core" in out
    assert "Back." in out
    assert "Traceback" not in err
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_core_menu_delegates_to_existing_standards_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "1\n12\n2\n")

    assert code == 0
    assert "Paper Data Suite Core" in out
    assert "Standards Management" in out
    assert "4. Add standard" in out
    assert "7. Create Standard Profile" in out
    assert "12. Back" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_core_menu_clears_before_display_and_after_standards_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)

    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "1\n12\n2\n")

    assert code == 0
    assert err == ""
    assert out.count("[clear]\nPaper Data Suite Core") == 2
    assert "[clear]\nStandards Management" in out
    assert out.rindex("[clear]\nPaper Data Suite Core") > out.index("Back.")
    assert list(tmp_path.iterdir()) == []


def test_core_workspace_override_reaches_standards_validation_without_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "1\n11\n\n12\n2\n")

    assert code == 0
    assert "using empty library" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "ScoreForm").exists()
    assert not (tmp_path / "Quillan").exists()


def test_direct_standards_menu_route_still_works(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("12\n"))

    code = pds_core_main(["--workspace", str(tmp_path), "standards", "menu"])
    captured = capsys.readouterr()

    assert code == 0
    assert "Standards Management" in captured.out
    assert "4. Add standard" in captured.out
    assert "7. Create Standard Profile" in captured.out
    assert "12. Back" in captured.out
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []
