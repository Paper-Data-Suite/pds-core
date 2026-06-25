"""Standards library validation/import/export CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.cli import main
from pds_core.standards import (
    StandardsLibrary,
    load_standards_library,
    standard_definition_to_dict,
    standards_library_to_dict,
    standards_profile_to_dict,
    write_workspace_standards_library,
)
from tests.cli.conftest import make_cli_library, run_cli

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
