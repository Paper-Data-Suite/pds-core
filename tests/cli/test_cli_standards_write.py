"""Standards mutation CLI tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import (
    load_standards_library,
    write_workspace_standards_library,
)
from tests.cli.conftest import make_cli_library, run_cli, standard_mutation_args

def test_standards_add_creates_library_and_supports_optional_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "add",
        *standard_mutation_args(),
        "--subject",
        "English Language Arts",
        "--course",
        "English 12",
        "--grade-band",
        "11-12",
        "--domain",
        "Reading Literature",
        "--category-path",
        "English Language Arts/Reading Literature/Close Reading",
        "--tag",
        "close_reading",
        "--tag",
        "textual_evidence",
        "--available-module",
        "pds-scoreform",
        "--available-module",
        "pds-quillan",
        "--inactive",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Added standard local-reading:close_reading.\n"
    assert err == ""
    library = load_standards_library(tmp_path / "standards" / "library.json")
    assert len(library.standards) == 1
    definition = library.standards[0]
    assert definition.standard_id == "local-reading:close_reading"
    assert definition.category_path == (
        "English Language Arts",
        "Reading Literature",
        "Close Reading",
    )
    assert definition.tags == ("close_reading", "textual_evidence")
    assert definition.available_modules == ("pds-scoreform", "pds-quillan")
    assert definition.active is False
    assert not (tmp_path / "standards" / "usage").exists()


def test_standards_add_preserves_existing_profiles_and_rejects_duplicates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "add",
        *standard_mutation_args(standard_id="local-reading:new"),
        capsys=capsys,
    )

    assert code == 0
    assert out == "Added standard local-reading:new.\n"
    assert err == ""
    library = load_standards_library(library_path)
    assert library.profiles == make_cli_library().profiles
    assert library.standards[-1].standard_id == "local-reading:new"

    before = library_path.read_text(encoding="utf-8")
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "add",
        *standard_mutation_args(standard_id="local-reading:new"),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "duplicate" in err
    assert library_path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "args",
    [
        ("standards", "add", "--standard-id", "local-reading:missing"),
        (
            "standards",
            "add",
            *standard_mutation_args(standard_id="local-reading:bad"),
            "--category-path",
            "English Language Arts//Close Reading",
        ),
        (
            "standards",
            "add",
            *standard_mutation_args(standard_id="local-reading:bad"),
            "--tag",
            "",
        ),
        (
            "standards",
            "add",
            *standard_mutation_args(standard_id="local-reading:bad"),
            "--active",
            "--inactive",
        ),
    ],
)
def test_standards_add_invalid_input_fails_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    args: tuple[str, ...],
) -> None:
    code, out, err = run_cli(tmp_path, *args, capsys=capsys)

    assert code != 0
    assert out == ""
    assert "Traceback" not in err
    assert not (tmp_path / "standards" / "library.json").exists()
    assert not (tmp_path / "standards" / "usage").exists()


def test_standards_replace_succeeds_and_is_full_record_replacement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "replace",
        "njsls-ela:RL.CR.11-12.1",
        *standard_mutation_args(
            include_standard_id=False,
            code="UPDATED",
            short_name="Updated Standard",
            description="Updated description.",
        ),
        capsys=capsys,
    )

    assert code == 0
    assert out == "Replaced standard njsls-ela:RL.CR.11-12.1.\n"
    assert err == ""
    library = load_standards_library(tmp_path / "standards" / "library.json")
    replaced = library.standards[0]
    assert replaced.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert replaced.code == "UPDATED"
    assert replaced.subject is None
    assert replaced.category_path == ()
    assert library.profiles == make_cli_library().profiles


def test_standards_replace_missing_or_invalid_fails_without_modifying_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"
    before = library_path.read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "replace",
        "missing:standard",
        *standard_mutation_args(include_standard_id=False),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "missing" in err
    assert library_path.read_text(encoding="utf-8") == before

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "replace",
        "njsls-ela:RL.CR.11-12.1",
        *standard_mutation_args(include_standard_id=False, description=" "),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "description must not be blank" in err
    assert library_path.read_text(encoding="utf-8") == before


def test_standards_upsert_adds_replaces_and_reports_action(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "upsert",
        "local-reading:new",
        *standard_mutation_args(include_standard_id=False),
        capsys=capsys,
    )

    assert code == 0
    assert out == "Added standard local-reading:new.\n"
    assert err == ""

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "upsert",
        "local-reading:new",
        *standard_mutation_args(
            include_standard_id=False,
            code="CR.2",
            short_name="Updated Reading",
        ),
        "--tag",
        "updated",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Updated standard local-reading:new.\n"
    assert err == ""
    library = load_standards_library(tmp_path / "standards" / "library.json")
    assert library.standards[-1].code == "CR.2"
    assert library.standards[-1].tags == ("updated",)
    assert library.profiles == make_cli_library().profiles


def test_standards_upsert_invalid_input_fails_without_modifying_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"
    before = library_path.read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "upsert",
        "local-reading:new",
        *standard_mutation_args(include_standard_id=False),
        "--available-module",
        "",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "available_modules[0] must not be blank" in err
    assert library_path.read_text(encoding="utf-8") == before


def test_standards_retire_and_reactivate_are_non_destructive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "retire",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Retired standard njsls-ela:RL.CR.11-12.1.\n"
    assert err == ""
    library = load_standards_library(tmp_path / "standards" / "library.json")
    retired = library.standards[0]
    assert retired.active is False
    assert retired.code == make_cli_library().standards[0].code
    assert library.profiles == make_cli_library().profiles
    assert "njsls-ela:RL.CR.11-12.1" in library.profiles[0].standards
    assert not (tmp_path / "standards" / "usage").exists()

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "reactivate",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Reactivated standard njsls-ela:RL.CR.11-12.1.\n"
    assert err == ""
    reactivated = load_standards_library(
        tmp_path / "standards" / "library.json"
    )
    assert reactivated.standards[0].active is True
    assert reactivated.standards[0] == make_cli_library().standards[0]


def test_standards_retire_and_reactivate_fail_clear_noop_cases(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"
    before = library_path.read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "retire",
        "missing:standard",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "standard not found: missing:standard" in err
    assert library_path.read_text(encoding="utf-8") == before

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "retire",
        "njsls-ela:RI.CR.11-12.1",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "standard is already inactive" in err
    assert library_path.read_text(encoding="utf-8") == before

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "reactivate",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "standard is already active" in err
    assert library_path.read_text(encoding="utf-8") == before

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "retire",
        "njsls-ela:RI.CR.11-12.1",
        "--force",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Retired standard njsls-ela:RI.CR.11-12.1.\n"
    assert err == ""


def test_standard_mutations_fail_before_writing_invalid_workspace_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library_path = tmp_path / "standards" / "library.json"
    library_path.parent.mkdir()
    library_path.write_text("{", encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "retire",
        "local-reading:any",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "invalid JSON" in err
    assert library_path.read_text(encoding="utf-8") == "{"


def test_standards_remove_command_is_not_implemented(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    before = (tmp_path / "standards" / "library.json").read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "remove",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )

    assert code == 2
    assert out == ""
    assert "invalid choice" in err
    assert "remove" in err
    assert (tmp_path / "standards" / "library.json").read_text(
        encoding="utf-8"
    ) == before
