"""Read-only standards CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.cli import main
from pds_core.standards import (
    standard_definition_to_dict,
    standards_profile_to_dict,
    write_workspace_standards_library,
)
from tests.cli.conftest import make_cli_library, run_cli

def test_list_show_search_and_browse_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, _err = run_cli(tmp_path, "standards", "list", capsys=capsys)
    assert code == 0
    assert not out.startswith("PDS Core")
    assert "evidence_explanation - Evidence Explanation" in out
    assert "ID: local-writing:evidence_explanation" in out
    assert "RL.CR.11-12.1 - Close Reading Evidence" in out
    assert "ID: njsls-ela:RL.CR.11-12.1" in out
    assert "njsls-ela:RI.CR.11-12.1" not in out

    code, out, _err = run_cli(
        tmp_path,
        "standards",
        "show",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )
    assert code == 0
    assert "ID: njsls-ela:RL.CR.11-12.1\n" in out
    assert "Code: RL.CR.11-12.1\n" in out
    assert "Category: English Language Arts / Reading Literature" in out
    assert "Available modules: pds-scoreform, pds-quillan\n" in out

    code, out, _err = run_cli(
        tmp_path,
        "standards",
        "search",
        "informational",
        "--all",
        capsys=capsys,
    )
    assert code == 0
    assert "njsls-ela:RI.CR.11-12.1" in out
    assert "Inactive" in out

    code, out, _err = run_cli(tmp_path, "standards", "subjects", capsys=capsys)
    assert code == 0
    assert out == "English Language Arts\n"

    code, out, _err = run_cli(tmp_path, "standards", "sources", capsys=capsys)
    assert code == 0
    assert out.splitlines() == [
        "Local Misc",
        "Local Writing Rubric",
        "NJSLS-ELA",
    ]

    code, out, _err = run_cli(tmp_path, "standards", "domains", capsys=capsys)
    assert code == 0
    assert out.splitlines() == ["Reading Literature", "Writing"]

    code, out, _err = run_cli(tmp_path, "standards", "categories", capsys=capsys)
    assert code == 0
    assert out.splitlines() == [
        "English Language Arts / Reading Literature / Close Reading",
        "English Language Arts / Writing",
    ]

    code, out, _err = run_cli(tmp_path, "standards", "profiles", capsys=capsys)
    assert code == 0
    assert "English 12 Local Writing" in out
    assert "ID: english_12_local" in out
    assert "English 12 NJSLS" in out
    assert "ID: english_12_njsls" in out

    code, out, _err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "show",
        "english_12_njsls",
        capsys=capsys,
    )
    assert code == 0
    assert "ID: english_12_njsls\n" in out
    assert "RL.CR.11-12.1 - Close Reading Evidence" in out
    assert "ID: njsls-ela:RL.CR.11-12.1" in out
    assert "RI.CR.11-12.1 - Informational Text Evidence" in out
    assert "ID: njsls-ela:RI.CR.11-12.1" in out


@pytest.mark.parametrize(
    ("args", "expected", "unexpected"),
    [
        (
            ("standards", "list", "--source", "Local Writing Rubric"),
            "local-writing:evidence_explanation",
            "njsls-ela:RL.CR.11-12.1",
        ),
        (
            ("standards", "list", "--subject", "English Language Arts"),
            "local-writing:evidence_explanation",
            "local-misc:unfiled",
        ),
        (
            ("standards", "list", "--course", "English 12"),
            "njsls-ela:RL.CR.11-12.1",
            "local-misc:unfiled",
        ),
        (
            ("standards", "list", "--domain", "Writing"),
            "local-writing:evidence_explanation",
            "njsls-ela:RL.CR.11-12.1",
        ),
        (
            (
                "standards",
                "list",
                "--category",
                "English Language Arts/Reading Literature",
            ),
            "njsls-ela:RL.CR.11-12.1",
            "local-writing:evidence_explanation",
        ),
        (
            ("standards", "list", "--available-module", "pds-scoreform"),
            "local-writing:evidence_explanation",
            "njsls-ela:RI.CR.11-12.1",
        ),
        (
            ("standards", "list", "--inactive"),
            "njsls-ela:RI.CR.11-12.1",
            "njsls-ela:RL.CR.11-12.1",
        ),
        (
            ("standards", "list", "--all"),
            "njsls-ela:RI.CR.11-12.1",
            "No standards found.",
        ),
    ],
)
def test_standard_filters(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    args: tuple[str, ...],
    expected: str,
    unexpected: str,
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_cli(tmp_path, *args, capsys=capsys)

    assert code == 0
    assert expected in out
    assert unexpected not in out
    assert err == ""


def test_profile_filters(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profiles",
        "--source",
        "NJSLS-ELA",
        capsys=capsys,
    )

    assert code == 0
    assert "english_12_njsls" in out
    assert "english_12_local" not in out
    assert err == ""


def test_missing_ids_return_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, _out, err = run_cli(
        tmp_path,
        "standards",
        "show",
        "missing:standard",
        capsys=capsys,
    )
    assert code == 1
    assert "Standard not found: missing:standard" in err

    code, _out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "show",
        "missing_profile",
        capsys=capsys,
    )
    assert code == 1
    assert "Standards profile not found: missing_profile" in err


@pytest.mark.parametrize(
    "content",
    [
        "{",
        "[]",
        json.dumps({"standards": [{"standard_id": "local:missing"}]}),
        json.dumps(
            {
                "standards": [
                    standard_definition_to_dict(make_cli_library().standards[0]),
                    standard_definition_to_dict(make_cli_library().standards[0]),
                ]
            }
        ),
        json.dumps(
            {
                "standards": [standard_definition_to_dict(make_cli_library().standards[0])],
                "profiles": [
                    {
                        **standards_profile_to_dict(make_cli_library().profiles[0]),
                        "standards": ["missing:standard"],
                    }
                ],
            }
        ),
    ],
)
def test_invalid_libraries_return_readable_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    content: str,
) -> None:
    library_path = tmp_path / "standards" / "library.json"
    library_path.parent.mkdir()
    library_path.write_text(content, encoding="utf-8")

    code, out, err = run_cli(tmp_path, "standards", "list", capsys=capsys)

    assert code == 1
    assert out == ""
    assert "Error:" in err
    assert "Traceback" not in err


def test_read_only_commands_do_not_create_workspace_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_workspace = tmp_path / "missing" / "workspace"

    code = main(
        [
            "--workspace",
            str(missing_workspace),
            "standards",
            "search",
            "anything",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out == "No standards found.\n"
    assert captured.err == ""
    assert not missing_workspace.exists()
    assert not (missing_workspace / "standards").exists()
    assert not (missing_workspace / ".pds").exists()


def standard_mutation_args(
    *,
    include_standard_id: bool = True,
    standard_id: str = "local-reading:close_reading",
    code: str = "CR.1",
    short_name: str = "Close Reading",
    description: str = "Use evidence from a text.",
) -> list[str]:
    args = []
    if include_standard_id:
        args.extend(["--standard-id", standard_id])
    args.extend(
        [
            "--code",
            code,
            "--source",
            "Local Reading",
            "--short-name",
            short_name,
            "--description",
            description,
        ]
    )
    return args
