"""End-to-end smoke tests for the standards management workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsValidationError,
    load_standards_library,
    load_workspace_standards_library,
    standards_library_path,
)
from pds_core.standards_selection import (
    list_profiles_for_selection,
    list_standards_for_profile_selection,
    list_standards_for_selection,
    load_standards_for_selection,
    resolve_profile_selection,
    resolve_profile_standard_selection,
    resolve_standard_selection,
)
from tests.cli.conftest import run_cli
from tests.cli_menu.conftest import run_menu

PARENT_ID = "njsls-ela:L.KL.11-12.2"
CHILD_A_ID = "njsls-ela:L.KL.11-12.2.A"
CHILD_B_ID = "njsls-ela:L.KL.11-12.2.B"
PROFILE_ID = "english_12_language_synthetic"


def assert_no_management_side_effects(workspace: Path) -> None:
    assert not (workspace / "standards" / "usage").exists()
    assert not (workspace / "classes").exists()
    assert not (workspace / "ScoreForm").exists()
    assert not (workspace / "Quillan").exists()


def add_synthetic_standard(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    standard_id: str,
    code: str,
    short_name: str,
    description: str,
) -> None:
    code_value, out, err = run_cli(
        tmp_path,
        "standards",
        "add",
        "--standard-id",
        standard_id,
        "--code",
        code,
        "--source",
        "NJSLS-ELA 2023",
        "--short-name",
        short_name,
        "--description",
        description,
        "--subject",
        "English Language Arts",
        "--course",
        "English 12",
        "--grade-band",
        "11-12",
        "--domain",
        "Language",
        "--category-path",
        "English Language Arts/Language",
        "--tag",
        "synthetic",
        "--available-module",
        "pds-scoreform",
        "--available-module",
        "pds-quillan",
        capsys=capsys,
    )

    assert code_value == 0
    assert out == f"Added standard {standard_id}.\n"
    assert err == ""


def create_synthetic_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> StandardsLibrary:
    add_synthetic_standard(
        tmp_path,
        capsys,
        standard_id=PARENT_ID,
        code="L.KL.11-12.2",
        short_name="Apply Language in Context",
        description=(
            "Apply knowledge of language to understand how language functions "
            "in different contexts."
        ),
    )
    add_synthetic_standard(
        tmp_path,
        capsys,
        standard_id=CHILD_A_ID,
        code="L.KL.11-12.2.A",
        short_name="Contextual Language Choice",
        description="Analyze how language choices shape meaning in context.",
    )
    add_synthetic_standard(
        tmp_path,
        capsys,
        standard_id=CHILD_B_ID,
        code="L.KL.11-12.2.B",
        short_name="Language Conventions",
        description="Apply language conventions for clarity and style.",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "create",
        "--profile-id",
        PROFILE_ID,
        "--title",
        "English 12 Language Synthetic",
        "--description",
        "Synthetic English 12 language standards.",
        "--subject",
        "English Language Arts",
        "--course",
        "English 12",
        "--source",
        "NJSLS-ELA 2023",
        "--standard",
        PARENT_ID,
        "--standard",
        CHILD_A_ID,
        "--standard",
        CHILD_B_ID,
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Created standards profile {PROFILE_ID}.\n"
    assert err == ""
    return load_standards_library(standards_library_path(tmp_path))


def test_empty_library_read_only_smoke_does_not_create_workspace_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "empty-workspace"

    assert load_workspace_standards_library(workspace) == StandardsLibrary(
        standards=(),
        profiles=(),
    )
    assert load_standards_for_selection(workspace) == StandardsLibrary(
        standards=(),
        profiles=(),
    )

    empty_library = StandardsLibrary(standards=(), profiles=())
    assert list_standards_for_selection(empty_library) == ()
    assert list_profiles_for_selection(empty_library) == ()

    for args, expected in (
        (("standards", "list"), "No standards found.\n"),
        (("standards", "search", "language"), "No standards found.\n"),
        (("standards", "profiles"), "No standards profiles found.\n"),
        (
            ("standards", "validate"),
            (
                "Standards library is valid. No workspace standards library "
                "exists; using empty library.\n"
            ),
        ),
    ):
        code, out, err = run_cli(workspace, *args, capsys=capsys)
        assert code == 0
        assert out == expected
        assert err == ""

    assert not workspace.exists()
    assert not standards_library_path(workspace).exists()
    assert_no_management_side_effects(workspace)


def test_standards_management_power_user_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library_path = standards_library_path(tmp_path)
    assert not library_path.exists()

    library = create_synthetic_library(tmp_path, capsys)

    assert library_path == tmp_path / "standards" / "library.json"
    assert library_path.exists()
    assert tuple(definition.standard_id for definition in library.standards) == (
        PARENT_ID,
        CHILD_A_ID,
        CHILD_B_ID,
    )
    assert library.profiles[0].standards == (PARENT_ID, CHILD_A_ID, CHILD_B_ID)

    for args, expected_text in (
        (("standards", "validate"), "Standards library is valid."),
        (("standards", "list"), "L.KL.11-12.2 - Apply Language in Context"),
        (("standards", "search", "conventions"), CHILD_B_ID),
        (("standards", "show", CHILD_A_ID), "Contextual Language Choice"),
        (("standards", "profiles"), PROFILE_ID),
        (("standards", "profile", "show", PROFILE_ID), CHILD_B_ID),
        (
            ("standards", "profile", "validate", PROFILE_ID),
            f"Standards profile is valid: {PROFILE_ID}",
        ),
    ):
        code, out, err = run_cli(tmp_path, *args, capsys=capsys)
        assert code == 0
        assert expected_text in out
        assert err == ""

    export_path = tmp_path / "exports" / "standards-library.json"
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
    assert export_path.exists()

    imported_workspace = tmp_path / "round-trip-workspace"
    code, out, err = run_cli(
        imported_workspace,
        "standards",
        "import",
        str(export_path),
        "--replace",
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Imported standards library from {export_path}.\n"
    assert err == ""
    round_tripped = load_standards_library(
        standards_library_path(imported_workspace)
    )
    assert round_tripped == library
    assert_no_management_side_effects(tmp_path)
    assert_no_management_side_effects(imported_workspace)


def test_standards_management_import_export_safety_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_library = create_synthetic_library(tmp_path, capsys)
    library_path = standards_library_path(tmp_path)
    before = library_path.read_text(encoding="utf-8")
    export_path = tmp_path / "standards-export.json"

    code, _out, err = run_cli(
        tmp_path,
        "standards",
        "export",
        str(export_path),
        capsys=capsys,
    )

    assert code == 0
    assert err == ""

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
    assert "target file already exists" in err
    assert export_path.read_text(encoding="utf-8") == "keep me"

    invalid_import = tmp_path / "invalid-library.json"
    invalid_import.write_text("{", encoding="utf-8")
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(invalid_import),
        "--replace",
        "--overwrite",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "invalid JSON" in err
    assert library_path.read_text(encoding="utf-8") == before

    valid_import = tmp_path / "valid-library.json"
    valid_import.write_text(
        json.dumps(
            {
                "standards": [],
                "profiles": [],
            }
        ),
        encoding="utf-8",
    )
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(valid_import),
        "--replace",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "already exists" in err
    assert load_standards_library(library_path) == original_library

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "import",
        str(valid_import),
        "--replace",
        "--overwrite",
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Imported standards library from {valid_import}.\n"
    assert err == ""
    assert load_standards_library(library_path) == StandardsLibrary(
        standards=(),
        profiles=(),
    )
    assert_no_management_side_effects(tmp_path)


def test_standards_management_teacher_menu_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = "\n".join(
        (
            "1",
            "4",
            PARENT_ID,
            "L.KL.11-12.2",
            "Apply Language in Context",
            (
                "Apply knowledge of language to understand how language "
                "functions in different contexts."
            ),
            "NJSLS-ELA 2023",
            "English Language Arts",
            "English 12",
            "Language",
            "YES",
            "A",
            "Contextual Language Choice",
            "Analyze how language choices shape meaning in context.",
            "",
            "YES",
            "",
            "1",
            "",
            "0",
            "",
            "2",
            "language",
            "",
            "3",
            CHILD_A_ID,
            "",
            "5",
            "2",
            "3",
            PROFILE_ID,
            "English 12 Language Synthetic",
            "Synthetic English 12 language standards.",
            "English Language Arts",
            "English 12",
            "NJSLS-ELA 2023",
            "1",
            "1",
            "1",
            "1,2",
            "YES",
            "",
            "1",
            "0",
            "",
            "2",
            PROFILE_ID,
            "",
            "7",
            "4",
            "",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    for expected in (
        "PDS Core",
        "Standards Library",
        "Standards",
        "Profiles",
        "Review Standard",
        "Type YES to create this standard.",
        "Search Standards Results",
        "Review Standard Profile",
        "Standards library is valid.",
    ):
        assert expected in out
    assert "Created standard njsls-ela:L.KL.11-12.2." in out
    assert "Created standard njsls-ela:L.KL.11-12.2.A." in out
    assert f"Created standards profile {PROFILE_ID}." in out
    assert CHILD_A_ID in out

    library = load_standards_library(standards_library_path(tmp_path))
    assert tuple(definition.standard_id for definition in library.standards) == (
        PARENT_ID,
        CHILD_A_ID,
    )
    assert library.profiles[0].standards == (PARENT_ID, CHILD_A_ID)
    assert_no_management_side_effects(tmp_path)


def test_standards_management_module_selection_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created_library = create_synthetic_library(tmp_path, capsys)
    library = load_standards_for_selection(tmp_path)

    assert library == created_library
    profiles = list_profiles_for_selection(
        library,
        subject="English Language Arts",
        course="English 12",
    )
    assert [profile.profile_id for profile in profiles] == [PROFILE_ID]
    assert resolve_profile_selection(library, PROFILE_ID).label.startswith(
        f"{PROFILE_ID} | English 12 Language Synthetic"
    )

    standards = list_standards_for_selection(
        library,
        subject="English Language Arts",
        course="English 12",
        available_module="pds-scoreform",
    )
    assert [standard.standard_id for standard in standards] == [
        PARENT_ID,
        CHILD_A_ID,
        CHILD_B_ID,
    ]
    profile_standards = list_standards_for_profile_selection(
        library,
        PROFILE_ID,
        available_module="pds-quillan",
    )
    assert [standard.standard_id for standard in profile_standards] == [
        PARENT_ID,
        CHILD_A_ID,
        CHILD_B_ID,
    ]
    assert resolve_standard_selection(library, CHILD_A_ID).code == "L.KL.11-12.2.A"

    selected = resolve_profile_standard_selection(
        library,
        profile_id=PROFILE_ID,
        selected_standard_ids=(CHILD_B_ID, PARENT_ID),
    )
    assert [standard.standard_id for standard in selected] == [CHILD_B_ID, PARENT_ID]

    with pytest.raises(StandardsValidationError, match="profile_id"):
        resolve_profile_selection(library, "missing_profile")
    with pytest.raises(StandardsValidationError, match="standard_id"):
        resolve_standard_selection(library, "missing:standard")
    with pytest.raises(StandardsValidationError, match="profile_id"):
        resolve_profile_standard_selection(
            library,
            profile_id="missing_profile",
            selected_standard_ids=(PARENT_ID,),
        )
    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        resolve_profile_standard_selection(
            library,
            profile_id=PROFILE_ID,
            selected_standard_ids=("missing:standard",),
        )
    outside_library = StandardsLibrary(
        standards=library.standards
        + (
            StandardDefinition(
                standard_id="local-language:outside_profile",
                code="OUTSIDE",
                source="Synthetic Local",
                short_name="Outside Profile",
                description="Synthetic standard outside the selected profile.",
            ),
        ),
        profiles=library.profiles,
    )
    with pytest.raises(StandardsValidationError, match="belong to profile"):
        resolve_profile_standard_selection(
            outside_library,
            profile_id=PROFILE_ID,
            selected_standard_ids=("local-language:outside_profile",),
        )
    with pytest.raises(StandardsValidationError, match="duplicate standard IDs"):
        resolve_profile_standard_selection(
            library,
            profile_id=PROFILE_ID,
            selected_standard_ids=(PARENT_ID, f" {PARENT_ID} "),
        )

    assert_no_management_side_effects(tmp_path)
