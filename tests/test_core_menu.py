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
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "4\n")

    assert code == 0
    assert "PDS Core\n\nMain Menu" in out
    assert "Paper Data Suite Core" not in out
    assert "1. Standards Management" in out
    assert "2. Workspace Settings" in out
    assert "3. Help" in out
    assert out.count("Q. Quit") == 1
    assert "B. Back" not in out
    assert "M. Main Menu" not in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("choice", ["Q", "q", "  q  "])
def test_core_menu_quits_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    choice: str,
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, f"{choice}\n")

    assert code == 0
    assert "Q. Quit" in out
    assert err == ""


def test_nested_navigation_back_main_menu_and_quit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "1\n1\nB\n2\nM\n1\n2\nQ\n",
    )

    assert code == 0
    assert "Standards" in out
    assert "Profiles" in out
    assert out.count("PDS Core\n\nMain Menu") >= 2
    assert "Back." in out
    assert err == ""


def test_core_menu_handles_invalid_blank_and_eof_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "nope\n\n")

    assert code == 0
    assert "Please choose a listed option, B, M, or Q." in out
    assert "Traceback" not in err
    assert err == ""
    assert list(tmp_path.iterdir()) == []

    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "")

    assert code == 0
    assert "PDS Core\n\nMain Menu" in out
    assert "Q. Quit" in out
    assert "Traceback" not in err
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_core_menu_delegates_to_existing_standards_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "1\n6\n4\n")

    assert code == 0
    assert "PDS Core\n\nMain Menu" in out
    assert "Paper Data Suite Core" not in out
    assert "Standards Library" in out
    assert "1. Standards" in out
    assert "2. Profiles" in out
    assert "3. Import / Export" in out
    assert "4. Validate library" in out
    assert "5. Starter Standards" in out
    assert "B. Back" in out
    assert "M. Main Menu" in out
    assert "Q. Quit" in out
    assert "S. Starter Standards" not in out
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

    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "1\n6\n4\n")

    assert code == 0
    assert err == ""
    assert out.count("[clear]\nPDS Core\n\nMain Menu") == 2
    assert "[clear]\nPDS Core\n\nStandards Library" in out
    assert out.rindex("[clear]\nPDS Core\n\nMain Menu") > out.index("Back.")
    assert list(tmp_path.iterdir()) == []


def test_core_workspace_override_reaches_standards_validation_without_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "1\n4\n\n6\n2\n")

    assert code == 0
    assert "using empty library" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "ScoreForm").exists()
    assert not (tmp_path / "Quillan").exists()


def test_workspace_settings_menu_is_reachable_and_back_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "2\n6\n4\n")

    assert code == 0
    assert "Workspace Settings" in out
    assert "1. Show workspace status" in out
    assert "2. Set workspace root" in out
    assert "3. Validate/create current workspace" in out
    assert "4. Reset saved workspace preference" in out
    assert "5. Show workspace paths and precedence" in out
    assert "B. Back" in out
    assert "M. Main Menu" in out
    assert "Q. Quit" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_workspace_status_menu_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "2\n1\n\n6\n4\n")

    assert code == 0
    assert "Show Workspace Status" in out
    assert "Resolved workspace root:" in out
    assert str(tmp_path) in out
    assert "Resolution source:" in out
    assert "explicit" in out
    assert "Workspace marker:" in out
    assert "missing" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_workspace_validate_menu_creates_marker_and_baseline_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace_root = tmp_path / "workspace"
    code, out, err = run_core_menu(
        workspace_root,
        monkeypatch,
        capsys,
        "2\n3\n\n6\n4\n",
    )

    assert code == 0
    assert "Workspace validated successfully:" in out
    assert (workspace_root / ".pds" / "workspace.json").is_file()
    assert not (workspace_root / "standards").exists()
    assert (workspace_root / "classes").is_dir()
    assert (workspace_root / "scans_inbox").is_dir()
    assert (workspace_root / "scans" / "source").is_dir()
    assert (workspace_root / "scans" / "review").is_dir()
    assert not (workspace_root / "ScoreForm").exists()
    assert not (workspace_root / "Quillan").exists()
    assert err == ""


def test_workspace_settings_invalid_choice_then_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_core_menu(tmp_path, monkeypatch, capsys, "2\nnope\n6\n4\n")

    assert code == 0
    assert "Please choose a listed option, B, M, or Q." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_direct_standards_menu_route_still_works(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("6\n"))

    code = pds_core_main(["--workspace", str(tmp_path), "standards", "menu"])
    captured = capsys.readouterr()

    assert code == 0
    assert "Standards Library" in captured.out
    assert "1. Standards" in captured.out
    assert "2. Profiles" in captured.out
    assert "3. Import / Export" in captured.out
    assert "5. Starter Standards" in captured.out
    assert "B. Back" in captured.out
    assert "M. Main Menu" in captured.out
    assert "Q. Quit" in captured.out
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []
