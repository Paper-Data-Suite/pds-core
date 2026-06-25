"""Selectable filter and readable formatting tests."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

import pytest

from pds_core.cli_support import screen
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    write_workspace_standards_library,
)
from tests.cli_menu.conftest import assert_durable_standard_id_guidance, run_menu
from tests.test_cli import make_cli_library


def test_menu_browse_search_and_view_standards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
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
            "informational",
            "",
            "3",
            "njsls-ela:RL.CR.11-12.1",
            "",
            "3",
            "missing:standard",
            "",
            "5",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Browse Standards" in out
    assert "Status Filter" in out
    assert "Leave blank for Active only." in out
    assert "Category Filter" in out
    assert "Leave blank for any category." in out
    assert "Source Filter" in out
    assert "NJSLS-ELA" in out
    assert "Search checks IDs, display codes, names" in out
    assert "Example: language or RL.CR.11-12.1" in out
    assert "Enter Durable Standard ID." in out
    assert "Use Browse Standards or Search Standards first if you need to copy IDs." in out
    assert_durable_standard_id_guidance(out)
    assert "RL.CR.11-12.1 - Close Reading Evidence" in out
    assert "RI.CR.11-12.1 - Informational Text Evidence" in out
    assert "ID: njsls-ela:RL.CR.11-12.1" in out
    assert "Standard not found: missing:standard" in err


def test_browse_standards_filters_clear_and_support_skip_remaining(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    def mark_clear(stdout: TextIO) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)
    inputs = "\n".join(("1", "1", "1", "1", "1", "0", "", "5", "5", ""))

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    assert "[clear]\nPDS Core\n\nBrowse Standards\n\nStatus Filter" in out
    assert "[clear]\nPDS Core\n\nBrowse Standards\n\nCategory Filter" in out
    assert "[clear]\nPDS Core\n\nBrowse Standards\n\nSource Filter" in out
    assert "0. Skip remaining filters" in out
    assert "[clear]\nPDS Core\n\nBrowse Standards Results" in out


def test_search_standards_searches_directly_without_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    inputs = "\n".join(("1", "2", "informational", "", "5", "5", ""))

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    prompt_index = out.index("Search Standards")
    query_index = out.index("Enter search text.", prompt_index)
    input_prompt_index = out.index(">", query_index)
    result_index = out.index('Search Standards Results for "informational"')
    assert prompt_index < query_index < input_prompt_index < result_index
    assert "Status Filter" not in out[query_index:result_index]
    assert "Category Filter" not in out[query_index:result_index]
    assert "Choose an option: PDS Core" not in out
    assert ">PDS Core" not in out
    assert "RI.CR.11-12.1 - Informational Text Evidence" in out


def test_empty_available_module_filter_is_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library = StandardsLibrary(
        standards=(
            StandardDefinition(
                standard_id="local:one",
                code="ONE",
                source="Local",
                short_name="One",
                description="One standard.",
                subject="Subject",
                course="Course",
                domain="Domain",
                category_path=("Domain",),
            ),
        )
    )
    write_workspace_standards_library(tmp_path, library)
    inputs = "\n".join(("1", "1", "", "", "", "", "", "", "", "5", "5", ""))

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    assert "Available Module Filter" not in out
    assert "No available module filter values found" not in out
    assert "Browse Standards Results" in out


def test_menu_browse_and_view_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    inputs = "\n".join(
        (
            "2",
            "1",
            "",
            "",
            "",
            "",
            "2",
            "english_12_njsls",
            "",
            "2",
            "missing_profile",
            "",
            "7",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Browse Profiles" in out
    assert "Profile Source Filter" in out
    assert "Leave blank for any source." in out
    assert "View Profile" in out
    assert "Enter Durable Profile ID." in out
    assert "Use Browse Profiles first if you do not know the ID." in out
    assert "English 12 NJSLS" in out
    assert "ID: english_12_njsls" in out
    assert "RL.CR.11-12.1 - Close Reading Evidence" in out
    assert "Standards profile not found: missing_profile" in err


def test_browse_profiles_results_clear_after_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    def mark_clear(stdout: TextIO) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)
    inputs = "\n".join(("2", "1", "0", "", "7", "5", ""))

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    assert "[clear]\nPDS Core\n\nBrowse Profiles\n\nProfile Source Filter" in out
    assert "[clear]\nPDS Core\n\nBrowse Profiles Results" in out
