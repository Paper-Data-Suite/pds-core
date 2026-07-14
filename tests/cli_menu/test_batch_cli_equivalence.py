"""Canonical JSON equivalence tests for compound menu and CLI mutations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.cli import main
from pds_core.standards import write_workspace_standards_library
from tests.cli.conftest import make_cli_library
from tests.cli_menu.conftest import library_file, run_menu


def menu_input(*values: str) -> str:
    return "\n".join((*values, ""))


@pytest.mark.parametrize(
    "operation",
    ["add-definitions", "add-members", "remove-members", "set-members", "clear-members"],
)
def test_compound_menu_and_cli_operations_produce_identical_canonical_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
) -> None:
    menu_workspace = tmp_path / "menu-workspace"
    cli_workspace = tmp_path / "cli-workspace"
    request_path = tmp_path / "definitions-request.json"
    cli_arguments: tuple[str, ...]

    if operation == "add-definitions":
        request_path.write_text(
            json.dumps(
                {
                    "standards": [
                        {
                            "standard_id": "njsls-ela:L.VI.11-12.4",
                            "code": "L.VI.11-12.4",
                            "source": "NJSLS-ELA 2023",
                            "short_name": "Figurative Language and Word Relationships",
                            "description": (
                                "Demonstrate understanding of figurative language."
                            ),
                            "subject": "English Language Arts",
                            "course": "English 12",
                            "domain": "Language",
                            "category_path": ["Language"],
                        },
                        {
                            "standard_id": "njsls-ela:L.VI.11-12.4.A",
                            "code": "L.VI.11-12.4.A",
                            "source": "NJSLS-ELA 2023",
                            "short_name": "Figures of Speech",
                            "description": "Interpret figures of speech in context.",
                            "subject": "English Language Arts",
                            "course": "English 12",
                            "domain": "Language",
                            "category_path": ["Language"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        inputs = menu_input(
            "1",
            "4",
            "njsls-ela:L.VI.11-12.4",
            "L.VI.11-12.4",
            "Figurative Language and Word Relationships",
            "Demonstrate understanding of figurative language.",
            "NJSLS-ELA 2023",
            "English Language Arts",
            "English 12",
            "Language",
            "YES",
            "A",
            "Figures of Speech",
            "Interpret figures of speech in context.",
            "",
            "YES",
            "",
            "5",
            "6",
        )
        cli_arguments = ("standards", "add-batch", str(request_path))
    else:
        initial = make_cli_library()
        write_workspace_standards_library(menu_workspace, initial)
        write_workspace_standards_library(cli_workspace, initial)
        if operation == "add-members":
            inputs = menu_input(
                "2", "4", "1", "english_12_local", "1,3", "YES", "", "4", "7", "6"
            )
            cli_arguments = (
                "standards",
                "profile",
                "add-standards",
                "english_12_local",
                "njsls-ela:RL.CR.11-12.1",
                "local-misc:unfiled",
            )
        elif operation == "remove-members":
            inputs = menu_input(
                "2", "4", "2", "english_12_njsls", "1,2", "YES", "", "4", "7", "6"
            )
            cli_arguments = (
                "standards",
                "profile",
                "remove-standards",
                "english_12_njsls",
                "njsls-ela:RL.CR.11-12.1",
                "njsls-ela:RI.CR.11-12.1",
            )
        elif operation == "set-members":
            inputs = menu_input(
                "2", "4", "3", "english_12_njsls", "0", "2,4", "YES", "", "4", "7", "6"
            )
            cli_arguments = (
                "standards",
                "profile",
                "set-standards",
                "english_12_njsls",
                "--standard",
                "local-writing:evidence_explanation",
                "--standard",
                "njsls-ela:RL.CR.11-12.1",
            )
        else:
            inputs = menu_input(
                "2", "4", "3", "english_12_njsls", "0", "", "YES", "", "4", "7", "6"
            )
            cli_arguments = (
                "standards",
                "profile",
                "set-standards",
                "english_12_njsls",
            )

    menu_code, _menu_out, menu_err = run_menu(
        menu_workspace, monkeypatch, capsys, inputs
    )
    cli_code = main(["--workspace", str(cli_workspace), *cli_arguments])
    cli_capture = capsys.readouterr()

    assert menu_code == 0
    assert menu_err == ""
    assert cli_code == 0
    assert cli_capture.err == ""
    assert library_file(menu_workspace).read_bytes() == library_file(
        cli_workspace
    ).read_bytes()
