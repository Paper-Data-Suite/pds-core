"""Tests for the pds-core command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.cli import main
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    load_standards_library,
    standard_definition_to_dict,
    standards_library_to_dict,
    standards_profile_from_dict,
    standards_profile_to_dict,
    write_workspace_standards_library,
)


def make_cli_library() -> StandardsLibrary:
    return StandardsLibrary(
        standards=(
            StandardDefinition(
                standard_id="njsls-ela:RL.CR.11-12.1",
                code="RL.CR.11-12.1",
                source="NJSLS-ELA",
                short_name="Close Reading Evidence",
                description="Cite strong and thorough textual evidence.",
                subject="English Language Arts",
                course="English 12",
                grade_band="11-12",
                domain="Reading Literature",
                category_path=(
                    "English Language Arts",
                    "Reading Literature",
                    "Close Reading",
                ),
                tags=("close_reading", "textual_evidence"),
                active=True,
                available_modules=("pds-scoreform", "pds-quillan"),
            ),
            StandardDefinition(
                standard_id="njsls-ela:RI.CR.11-12.1",
                code="RI.CR.11-12.1",
                source="NJSLS-ELA",
                short_name="Informational Text Evidence",
                description="Cite textual evidence from informational text.",
                subject="English Language Arts",
                course="English 12",
                grade_band="11-12",
                domain="Reading Informational Text",
                category_path=(
                    "English Language Arts",
                    "Reading Informational Text",
                    "Close Reading",
                ),
                tags=("informational_text",),
                active=False,
                available_modules=("pds-quillan",),
            ),
            StandardDefinition(
                standard_id="local-writing:evidence_explanation",
                code="evidence_explanation",
                source="Local Writing Rubric",
                short_name="Evidence Explanation",
                description="Explain how evidence supports a claim.",
                subject="English Language Arts",
                course="English 12",
                grade_band="11-12",
                domain="Writing",
                category_path=("English Language Arts", "Writing"),
                tags=("writing",),
                active=True,
                available_modules=("pds-scoreform",),
            ),
            StandardDefinition(
                standard_id="local-misc:unfiled",
                code="unfiled",
                source="Local Misc",
                short_name="Unfiled Skill",
                description="A local skill without subject or domain metadata.",
                active=True,
            ),
        ),
        profiles=(
            StandardsProfile(
                profile_id="english_12_njsls",
                standards=(
                    "njsls-ela:RL.CR.11-12.1",
                    "njsls-ela:RI.CR.11-12.1",
                ),
                subject="English Language Arts",
                course="English 12",
                source="NJSLS-ELA",
                title="English 12 NJSLS",
                description="NJSLS English 12 profile.",
            ),
            StandardsProfile(
                profile_id="english_12_local",
                standards=("local-writing:evidence_explanation",),
                subject="English Language Arts",
                course="English 12",
                source="Local Writing Rubric",
                title="English 12 Local Writing",
                description="Local writing profile.",
            ),
        ),
    )


def run_cli(
    tmp_path: Path,
    *args: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    code = main(["--workspace", str(tmp_path), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_console_script_is_declared() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in pyproject
    assert 'pds-core = "pds_core.cli:main"' in pyproject


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["standards", "--help"],
        ["standards", "validate", "--help"],
        ["standards", "validate-file", "--help"],
        ["standards", "import", "--help"],
        ["standards", "export", "--help"],
        ["standards", "show", "--help"],
        ["standards", "profile", "show", "--help"],
        ["standards", "profile", "import", "--help"],
        ["standards", "profile", "export", "--help"],
    ],
)
def test_help_text_exists_and_distinguishes_ids(
    args: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert "standards" in captured.out
    assert "standard_id" in captured.out or "profile_id" in captured.out
    if "show" in args or "export" in args:
        assert "code" in captured.out or "title" in captured.out
    if "import" in args:
        assert "--replace" in captured.out or "--add" in captured.out
    if "export" in args:
        assert "--overwrite" in captured.out


def test_missing_library_loads_as_empty_without_creating_directories(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(tmp_path, "standards", "list", capsys=capsys)

    assert code == 0
    assert out == "No standards found.\n"
    assert err == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (("standards", "subjects"), "No subjects found."),
        (("standards", "sources"), "No sources found."),
        (("standards", "domains"), "No domains found."),
        (("standards", "categories"), "No categories found."),
        (("standards", "profiles"), "No standards profiles found."),
    ],
)
def test_empty_library_messages(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, ...],
    message: str,
) -> None:
    code, out, err = run_cli(tmp_path, *command, capsys=capsys)

    assert code == 0
    assert out == f"{message}\n"
    assert err == ""


def test_list_show_search_and_browse_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, _err = run_cli(tmp_path, "standards", "list", capsys=capsys)
    assert code == 0
    assert "local-writing:evidence_explanation | evidence_explanation" in out
    assert "njsls-ela:RL.CR.11-12.1 | RL.CR.11-12.1" in out
    assert "njsls-ela:RI.CR.11-12.1" not in out

    code, out, _err = run_cli(
        tmp_path,
        "standards",
        "show",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )
    assert code == 0
    assert "standard_id: njsls-ela:RL.CR.11-12.1\n" in out
    assert "code: RL.CR.11-12.1\n" in out
    assert "category_path: English Language Arts / Reading Literature" in out
    assert "available_modules: pds-scoreform, pds-quillan\n" in out

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
    assert "inactive" in out

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
    assert "english_12_local | English 12 Local Writing" in out
    assert "english_12_njsls | English 12 NJSLS" in out

    code, out, _err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "show",
        "english_12_njsls",
        capsys=capsys,
    )
    assert code == 0
    assert "profile_id: english_12_njsls\n" in out
    assert "njsls-ela:RL.CR.11-12.1 | RL.CR.11-12.1 | Close Reading Evidence" in out
    assert (
        "njsls-ela:RI.CR.11-12.1 | RI.CR.11-12.1 | "
        "Informational Text Evidence"
    ) in out


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


def test_validate_succeeds_for_valid_and_missing_libraries_without_side_effects(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_workspace = tmp_path / "missing"

    code = main(["--workspace", str(missing_workspace), "standards", "validate"])
    captured = capsys.readouterr()

    assert code == 0
    assert (
        captured.out
        == "Standards library is valid. No workspace standards library exists; "
        "using empty library.\n"
    )
    assert captured.err == ""
    assert not missing_workspace.exists()

    write_workspace_standards_library(tmp_path, make_cli_library())
    code, out, err = run_cli(tmp_path, "standards", "validate", capsys=capsys)

    assert code == 0
    assert out == "Standards library is valid.\n"
    assert err == ""


def test_validate_fails_for_malformed_workspace_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library_path = tmp_path / "standards" / "library.json"
    library_path.parent.mkdir()
    library_path.write_text("{", encoding="utf-8")

    code, out, err = run_cli(tmp_path, "standards", "validate", capsys=capsys)

    assert code == 1
    assert out == ""
    assert "invalid JSON" in err
    assert "Traceback" not in err


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
def test_validate_file_reports_invalid_external_files_without_workspace_changes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    content: str,
) -> None:
    source_path = tmp_path / "external.json"
    source_path.write_text(content, encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "validate-file",
        str(source_path),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "Error:" in err
    assert not (tmp_path / "standards").exists()


def test_validate_file_succeeds_for_valid_external_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = tmp_path / "library.json"
    source_path.write_text(
        json.dumps(standards_library_to_dict(make_cli_library())),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "validate-file",
        str(source_path),
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Standards library file is valid: {source_path}\n"
    assert err == ""
    assert not (tmp_path / "standards").exists()


def test_export_writes_deterministic_library_and_refuses_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library = make_cli_library()
    write_workspace_standards_library(tmp_path, library)
    export_path = tmp_path / "exports" / "library.json"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "export",
        str(export_path),
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Exported standards library to {export_path}.\n"
    assert err == ""
    assert load_standards_library(export_path) == library
    assert export_path.read_text(encoding="utf-8") == (
        json.dumps(standards_library_to_dict(library), indent=2, sort_keys=True)
        + "\n"
    )

    export_path.write_text("keep me", encoding="utf-8")
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "export",
        str(export_path),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert f"Error: target file already exists: {export_path}" in err
    assert export_path.read_text(encoding="utf-8") == "keep me"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "export",
        str(export_path),
        "--overwrite",
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Exported standards library to {export_path}.\n"
    assert err == ""
    assert load_standards_library(export_path) == library


def test_export_missing_workspace_library_writes_empty_library_only_to_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    export_path = tmp_path / "library.json"

    code, _out, err = run_cli(
        tmp_path,
        "standards",
        "export",
        str(export_path),
        capsys=capsys,
    )

    assert code == 0
    assert err == ""
    assert load_standards_library(export_path) == StandardsLibrary(
        standards=(),
        profiles=(),
    )
    assert not (tmp_path / "standards").exists()


def test_import_replace_requires_mode_and_overwrite_for_existing_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(standards_library_to_dict(make_cli_library())),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(source_path),
        capsys=capsys,
    )

    assert code == 2
    assert out == ""
    assert "requires an explicit mode" in err
    assert not (tmp_path / "standards").exists()

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(source_path),
        "--replace",
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Imported standards library from {source_path}.\n"
    assert err == ""
    assert load_standards_library(tmp_path / "standards" / "library.json") == (
        make_cli_library()
    )
    assert not (tmp_path / "standards" / "usage").exists()

    existing_content = (tmp_path / "standards" / "library.json").read_text(
        encoding="utf-8"
    )
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(source_path),
        "--replace",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "already exists" in err
    assert (tmp_path / "standards" / "library.json").read_text(
        encoding="utf-8"
    ) == existing_content

    source_path.write_text(
        json.dumps({"standards": [], "profiles": []}),
        encoding="utf-8",
    )
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(source_path),
        "--replace",
        "--overwrite",
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Imported standards library from {source_path}.\n"
    assert err == ""
    assert load_standards_library(tmp_path / "standards" / "library.json") == (
        StandardsLibrary(standards=(), profiles=())
    )


def test_invalid_import_does_not_modify_existing_workspace_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"
    before = library_path.read_text(encoding="utf-8")
    source_path = tmp_path / "invalid.json"
    source_path.write_text("{", encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(source_path),
        "--replace",
        "--overwrite",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "invalid JSON" in err
    assert library_path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "standards" / "usage").exists()


def test_profile_export_writes_deterministic_profile_and_refuses_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library = make_cli_library()
    write_workspace_standards_library(tmp_path, library)
    export_path = tmp_path / "profiles" / "english_12_njsls.json"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "export",
        "english_12_njsls",
        str(export_path),
        capsys=capsys,
    )

    assert code == 0
    assert out == (
        f"Exported standards profile english_12_njsls to {export_path}.\n"
    )
    assert err == ""
    assert standards_profile_from_dict(json.loads(export_path.read_text())) == (
        library.profiles[0]
    )
    assert export_path.read_text(encoding="utf-8") == (
        json.dumps(
            standards_profile_to_dict(library.profiles[0]),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    export_path.write_text("keep me", encoding="utf-8")
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "export",
        "english_12_njsls",
        str(export_path),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert f"Error: target file already exists: {export_path}" in err
    assert export_path.read_text(encoding="utf-8") == "keep me"


def test_profile_export_fails_for_missing_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "export",
        "missing_profile",
        str(tmp_path / "missing.json"),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "Standards profile not found: missing_profile" in err


def test_profile_import_add_validates_references_and_duplicate_ids(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base_library = StandardsLibrary(standards=make_cli_library().standards, profiles=())
    write_workspace_standards_library(tmp_path, base_library)
    profile = make_cli_library().profiles[0]
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(standards_profile_to_dict(profile)),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(profile_path),
        "--add",
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Added standards profile english_12_njsls from {profile_path}.\n"
    assert err == ""
    imported = load_standards_library(tmp_path / "standards" / "library.json")
    assert imported.profiles == (profile,)
    assert not (tmp_path / "standards" / "usage").exists()

    before = (tmp_path / "standards" / "library.json").read_text(encoding="utf-8")
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(profile_path),
        "--add",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "duplicate" in err
    assert (tmp_path / "standards" / "library.json").read_text(
        encoding="utf-8"
    ) == before

    bad_profile_path = tmp_path / "bad_profile.json"
    bad_profile_path.write_text(
        json.dumps(
            {
                **standards_profile_to_dict(
                    StandardsProfile(
                        profile_id="bad_profile",
                        standards=("njsls-ela:RL.CR.11-12.1",),
                    )
                ),
                "standards": ["missing:standard"],
            }
        ),
        encoding="utf-8",
    )
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(bad_profile_path),
        "--add",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "unknown standard IDs" in err
    assert (tmp_path / "standards" / "library.json").read_text(
        encoding="utf-8"
    ) == before


def test_profile_import_requires_explicit_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(standards_profile_to_dict(make_cli_library().profiles[0])),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(profile_path),
        capsys=capsys,
    )

    assert code == 2
    assert out == ""
    assert "profile import requires an explicit mode" in err
