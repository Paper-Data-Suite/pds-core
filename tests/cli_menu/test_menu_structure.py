"""Menu structure and screen-clearing tests."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
from typing import TextIO, cast

import pytest

from pds_core.cli_support import screen
from pds_core.cli_support.menu import StandardsMenu
from pds_core.standards import StandardsLibrary, write_workspace_standards_library
from tests.cli_menu.conftest import run_menu
from tests.test_cli import make_cli_library


def assert_no_prompt_header_fusion(out: str) -> None:
    forbidden = (
        "Choose an option: PDS Core",
        "Choose an option: \033[32mPDS Core",
        ">PDS Core",
        "> PDS Core",
        ">\033[32mPDS Core",
        "> \033[32mPDS Core",
    )
    for text in forbidden:
        assert text not in out


def test_menu_opens_and_exits_via_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "5\n")

    assert code == 0
    assert out.index("PDS Core") < out.index("Standards Library")
    assert "Standards Library" in out
    assert "1. Standards" in out
    assert "2. Profiles" in out
    assert "3. Import / Export" in out
    assert "4. Validate library" in out
    assert "5. Back" in out
    assert "Standards Management" not in out
    assert "12. Back" not in out
    assert "6. Create profile" not in out
    assert "6. Create profile" not in out
    assert "Back." in out
    assert_no_prompt_header_fusion(out)
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_pds_core_header_helper_supports_plain_and_green() -> None:
    assert screen.app_header(color=False) == "PDS Core"
    assert screen.app_header(color=True) == "\033[32mPDS Core\033[0m"


def test_menu_prompt_order_keeps_prompt_at_bottom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "5\n")

    assert code == 0
    assert err == ""
    header_index = out.index("PDS Core")
    title_index = out.index("Standards Library")
    option_index = out.index("1. Standards")
    prompt_index = out.index("Choose an option:")
    assert header_index < title_index < option_index < prompt_index
    assert_no_prompt_header_fusion(out)


def test_menu_handles_invalid_and_blank_choices_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "nope\n\n5\n")

    assert code == 0
    assert out.count("Invalid menu choice. Please try again.") == 2
    assert "Traceback" not in err


def test_menu_prompt_flushes_before_reading() -> None:
    events: list[str] = []

    class RecordingStdout(io.StringIO):
        def write(self, text: str) -> int:
            events.append(f"write:{text}")
            return super().write(text)

        def flush(self) -> None:
            events.append("flush")
            super().flush()

    class RecordingStdin:
        def __init__(self, text: str) -> None:
            self._stdin = io.StringIO(text)

        def readline(self) -> str:
            events.append("readline")
            return self._stdin.readline()

    stdout = RecordingStdout()
    stdin = cast(TextIO, RecordingStdin("value\n"))
    menu = StandardsMenu(
        argparse.Namespace(workspace_root=Path(".")),
        StandardsLibrary(standards=()),
        stdin,
        stdout,
        io.StringIO(),
    )

    assert menu._prompt("> ") == "value"
    assert events.index("flush") < events.index("readline")


def test_standards_menu_and_nested_menus_clear_before_display(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)

    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "2\n4\n4\n7\n3\n5\n5\n",
    )

    assert code == 0
    assert err == ""
    assert "[clear]\nPDS Core\n\nStandards Library" in out
    assert "[clear]\nPDS Core\n\nProfiles" in out
    assert "[clear]\nPDS Core\n\nEdit Profile Standards" in out
    assert "[clear]\nPDS Core\n\nImport / Export" in out
    assert out.count("[clear]") >= 4


def test_create_profile_clears_before_first_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)

    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "2\n3\n\n7\n5\n")

    assert code == 0
    assert err == ""
    workflow_index = out.index("[clear]\nPDS Core\n\nCreate Standard Profile")
    prompt_index = out.index("Enter Durable Profile ID.", workflow_index)
    assert workflow_index < prompt_index


def test_browse_search_view_workflows_clear_before_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)
    inputs = "\n".join(
        (
            "1",
            "1",
            "3",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "2",
            "",
            "",
            "3",
            "",
            "",
            "5",
            "2",
            "1",
            "",
            "",
            "",
            "",
            "2",
            "",
            "",
            "7",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    assert "[clear]\nPDS Core\n\nBrowse Standards" in out
    assert "[clear]\nPDS Core\n\nSearch Standards" in out
    assert "[clear]\nPDS Core\n\nView Standard" in out
    assert "[clear]\nPDS Core\n\nBrowse Profiles" in out
    assert "[clear]\nPDS Core\n\nView Profile" in out
    assert_no_prompt_header_fusion(out)


def test_nested_workflow_actions_clear_before_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)
    inputs = "\n".join(
        (
            "8",
            "2",
            "4",
            "1",
            "",
            "",
            "2",
            "",
            "",
            "3",
            "",
            "",
            "4",
            "7",
            "3",
            "1",
            "",
            "",
            "3",
            "",
            "",
            "5",
            "3",
            "2",
            "",
            "",
            "4",
            "",
            "",
            "5",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    assert "[clear]\nPDS Core\n\nAdd Standard to Profile" in out
    assert "[clear]\nPDS Core\n\nRemove Standard from Profile" in out
    assert "[clear]\nPDS Core\n\nReplace Profile Standards" in out
    assert "[clear]\nPDS Core\n\nImport Full Standards Library" in out
    assert "[clear]\nPDS Core\n\nImport Standards Profile" in out
    assert "[clear]\nPDS Core\n\nExport Full Standards Library" in out
    assert "[clear]\nPDS Core\n\nExport Standards Profile" in out


def test_validate_clears_before_validation_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "4\n\n5\n")

    assert code == 0
    assert err == ""
    assert "[clear]\nPDS Core\n\nValidate Standards Library" in out


def test_results_pause_before_returning_to_clean_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)

    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "\n".join(("1", "1", "3", "", "", "", "", "", "", "", "5", "5", "")),
    )

    assert code == 0
    assert err == ""
    result_index = out.index("RL.CR.11-12.1 - Close Reading Evidence")
    pause_index = out.index("Press Enter to return to the Standards menu...")
    next_menu_index = out.index("[clear]\nPDS Core\n\nStandards", pause_index)
    assert result_index < pause_index < next_menu_index
    assert_no_prompt_header_fusion(out)


def test_menu_does_not_expose_destructive_delete_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "8\n4\n12\n")

    assert code == 0
    assert "delete standard" not in out.lower()
