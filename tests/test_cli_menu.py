"""Tests for the interactive standards management menu."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from pds_core.cli import main
from pds_core.cli_support import screen
from pds_core.standards import (
    StandardsLibrary,
    StandardsProfile,
    load_standards_library,
    standards_library_to_dict,
    standards_profile_to_dict,
    write_workspace_standards_library,
)
from tests.test_cli import make_cli_library


def run_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    input_text: str,
) -> tuple[int, str, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(input_text))
    code = main(["--workspace", str(tmp_path), "standards", "menu"])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def library_file(tmp_path: Path) -> Path:
    return tmp_path / "standards" / "library.json"


def test_menu_opens_and_exits_via_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "11\n")

    assert code == 0
    assert "Standards Management" in out
    assert "6. Create Standard Profile" in out
    assert "6. Create profile" not in out
    assert "11. Back" in out
    assert "Back." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_menu_handles_invalid_and_blank_choices_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "nope\n\n11\n")

    assert code == 0
    assert out.count("Invalid menu choice. Please try again.") == 2
    assert "Traceback" not in err


def test_menu_browse_search_and_view_standards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    inputs = "\n".join(
        (
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
            "3",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "3",
            "njsls-ela:RL.CR.11-12.1",
            "",
            "3",
            "missing:standard",
            "",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Browse Standards" in out
    assert "Status Filter." in out
    assert "Leave blank for active only." in out
    assert "Category Filter." in out
    assert "Leave blank for any category." in out
    assert "Search checks IDs, display codes, names" in out
    assert "Example: language or RL.CR.11-12.1" in out
    assert "Enter Durable Standard ID." in out
    assert "Use Browse or Search first if you do not know the ID." in out
    assert "njsls-ela:RL.CR.11-12.1 | RL.CR.11-12.1" in out
    assert "njsls-ela:RI.CR.11-12.1 | RI.CR.11-12.1" in out
    assert "standard_id: njsls-ela:RL.CR.11-12.1" in out
    assert "Standard not found: missing:standard" in err


def test_menu_browse_and_view_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    inputs = "\n".join(
        (
            "4",
            "",
            "",
            "",
            "",
            "5",
            "english_12_njsls",
            "",
            "5",
            "missing_profile",
            "",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Browse Profiles" in out
    assert "Profile Source Filter." in out
    assert "Leave blank for any source." in out
    assert "View Profile" in out
    assert "Enter Durable Profile ID." in out
    assert "Use Browse Profiles first if you do not know the ID." in out
    assert "english_12_njsls | English 12 NJSLS" in out
    assert "profile_id: english_12_njsls" in out
    assert "njsls-ela:RL.CR.11-12.1 | RL.CR.11-12.1" in out
    assert "Standards profile not found: missing_profile" in err


def test_menu_create_profile_with_standards_and_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base_library = StandardsLibrary(
        standards=make_cli_library().standards,
        profiles=(),
    )
    write_workspace_standards_library(tmp_path, base_library)
    inputs = "\n".join(
        (
            "6",
            "cancelled_profile",
            "Cancelled",
            "",
            "",
            "",
            "",
            "",
            "no",
            "",
            "6",
            "english_12_new",
            "English 12 New",
            "",
            "English Language Arts",
            "English 12",
            "NJSLS-ELA",
            "njsls-ela:RI.CR.11-12.1, njsls-ela:RL.CR.11-12.1",
            "YES",
            "",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Create Standard Profile" in out
    assert "Enter Durable Profile ID." in out
    assert "Example: english_12_language_standards" in out
    assert "Enter Profile Title." in out
    assert "Enter Profile Description." in out
    assert "Enter Subject." in out
    assert "Enter Course." in out
    assert "Enter Source." in out
    assert "Enter Standard IDs for this profile." in out
    assert "Review Standard Profile" in out
    assert "Type YES to create this standard profile." in out
    assert "Required: durable profile_id." not in out
    assert "Optional: title, description, subject, course, source" not in out
    assert "Create Profile" not in out
    assert "Cancelled." in out
    assert "Created standards profile english_12_new." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert [profile.profile_id for profile in library.profiles] == ["english_12_new"]
    assert library.profiles[0].standards == (
        "njsls-ela:RI.CR.11-12.1",
        "njsls-ela:RL.CR.11-12.1",
    )
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "ScoreForm").exists()
    assert not (tmp_path / "Quillan").exists()


@pytest.mark.parametrize(
    ("standards", "expected_error"),
    [
        ("missing:standard", "unknown standard IDs"),
        (
            "njsls-ela:RL.CR.11-12.1, njsls-ela:RL.CR.11-12.1",
            "duplicate standard IDs",
        ),
    ],
)
def test_menu_create_profile_rejects_invalid_membership_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    standards: str,
    expected_error: str,
) -> None:
    base_library = StandardsLibrary(
        standards=make_cli_library().standards,
        profiles=(),
    )
    write_workspace_standards_library(tmp_path, base_library)
    before = library_file(tmp_path).read_text(encoding="utf-8")
    inputs = "\n".join(
        (
            "6",
            "bad_profile",
            "",
            "",
            "",
            "",
            "",
            standards,
            "",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Created standards profile bad_profile." not in out
    assert expected_error in err
    assert library_file(tmp_path).read_text(encoding="utf-8") == before


def test_menu_create_profile_rejects_duplicate_profile_id_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    before = library_file(tmp_path).read_text(encoding="utf-8")
    inputs = "\n".join(
        (
            "6",
            "english_12_njsls",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Created standards profile english_12_njsls." not in out
    assert "duplicate" in err
    assert library_file(tmp_path).read_text(encoding="utf-8") == before


def test_menu_profile_membership_editing_preserves_metadata_and_definitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    inputs = "\n".join(
        (
            "7",
            "1",
            "english_12_local",
            "njsls-ela:RL.CR.11-12.1",
            "YES",
            "",
            "2",
            "english_12_local",
            "local-writing:evidence_explanation",
            "YES",
            "",
            "3",
            "english_12_njsls",
            "local-writing:evidence_explanation",
            "YES",
            "",
            "4",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert (
        "This changes which existing standards belong to an existing standards "
        "profile."
    ) in out
    assert "It does not create, edit, or delete standard definitions." in out
    assert "It does not delete profiles." in out
    assert "Add Standard to Profile" in out
    assert "This profile will receive the standard." in out
    assert "Enter Durable Standard ID to Add." in out
    assert "Remove Standard from Profile" in out
    assert "This only changes profile membership. It does not delete the standard." in out
    assert "Enter Durable Standard ID to Remove." in out
    assert "Replace Profile Standards" in out
    assert "This will replace only the profile's standards list." in out
    assert "Profile metadata will be preserved." in out
    assert "Added standard njsls-ela:RL.CR.11-12.1 to profile english_12_local." in out
    assert (
        "Removed standard local-writing:evidence_explanation from profile "
        "english_12_local."
    ) in out
    assert "Replaced standards for profile english_12_njsls." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    local_profile = library.profiles[1]
    njsls_profile = library.profiles[0]
    assert local_profile.standards == ("njsls-ela:RL.CR.11-12.1",)
    assert njsls_profile.standards == ("local-writing:evidence_explanation",)
    assert njsls_profile.title == "English 12 NJSLS"
    assert tuple(definition.standard_id for definition in library.standards) == (
        tuple(definition.standard_id for definition in make_cli_library().standards)
    )


@pytest.mark.parametrize(
    ("submenu_choice", "profile_id", "standard_id", "expected_error"),
    [
        ("1", "english_12_njsls", "njsls-ela:RL.CR.11-12.1", "already contains"),
        ("1", "english_12_njsls", "missing:standard", "standard not found"),
        ("2", "english_12_local", "njsls-ela:RL.CR.11-12.1", "does not contain"),
    ],
)
def test_menu_membership_failures_do_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    submenu_choice: str,
    profile_id: str,
    standard_id: str,
    expected_error: str,
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    before = library_file(tmp_path).read_text(encoding="utf-8")
    inputs = "\n".join(
        ("7", submenu_choice, profile_id, standard_id, "", "4", "11", "")
    )

    code, _out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert expected_error in err
    assert library_file(tmp_path).read_text(encoding="utf-8") == before


def test_menu_export_library_and_profile_refuse_overwrite_unless_confirmed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_export = tmp_path / "library-export.json"
    profile_export = tmp_path / "profile-export.json"
    library_export.write_text("keep me", encoding="utf-8")
    profile_export.write_text("keep me too", encoding="utf-8")
    inputs = "\n".join(
        (
            "9",
            "1",
            str(library_export),
            "no",
            "",
            "1",
            str(library_export),
            "YES",
            "YES",
            "",
            "2",
            "english_12_njsls",
            str(profile_export),
            "no",
            "",
            "2",
            "english_12_njsls",
            str(profile_export),
            "YES",
            "YES",
            "",
            "3",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Export writes standards data to JSON files." in out
    assert "Existing files are not overwritten unless you confirm." in out
    assert "Export Full Standards Library" in out
    assert "Enter Target JSON Path." in out
    assert "standards-library-export.json" in out
    assert "Export Standards Profile" in out
    assert "Use Browse Profiles first if you do not know the ID." in out
    assert "english-12-language-standards.json" in out
    assert out.count("Cancelled.") == 2
    assert err == ""
    assert load_standards_library(library_export) == make_cli_library()
    assert json.loads(profile_export.read_text(encoding="utf-8")) == (
        standards_profile_to_dict(make_cli_library().profiles[0])
    )


def test_menu_import_full_library_requires_confirmation_and_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    source_path = tmp_path / "empty-library.json"
    source_path.write_text(
        json.dumps(standards_library_to_dict(StandardsLibrary(standards=()))),
        encoding="utf-8",
    )
    invalid_path = tmp_path / "invalid-library.json"
    invalid_path.write_text("{", encoding="utf-8")
    before = library_file(tmp_path).read_text(encoding="utf-8")
    inputs = "\n".join(
        (
            "8",
            "1",
            str(invalid_path),
            "",
            "1",
            str(source_path),
            "no",
            "",
            "1",
            str(source_path),
            "YES",
            "YES",
            "",
            "3",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Import reads standards data from JSON files." in out
    assert "Files are validated before writing." in out
    assert "Replacement requires confirmation." in out
    assert "Import Full Standards Library" in out
    assert "Enter Source JSON Path." in out
    assert "This should be a full standards library JSON file." in out
    assert "standards-library.json" in out
    assert "invalid JSON" in err
    assert "Cancelled." in out
    assert before != library_file(tmp_path).read_text(encoding="utf-8")
    assert load_standards_library(library_file(tmp_path)) == StandardsLibrary(
        standards=()
    )


def test_menu_import_profile_add_and_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base_library = StandardsLibrary(
        standards=make_cli_library().standards,
        profiles=(),
    )
    write_workspace_standards_library(tmp_path, base_library)
    add_path = tmp_path / "add-profile.json"
    add_path.write_text(
        json.dumps(standards_profile_to_dict(make_cli_library().profiles[0])),
        encoding="utf-8",
    )
    replace_profile = StandardsProfile(
        profile_id="english_12_njsls",
        standards=("local-writing:evidence_explanation",),
        title="Replacement Title",
    )
    replace_path = tmp_path / "replace-profile.json"
    replace_path.write_text(
        json.dumps(standards_profile_to_dict(replace_profile)),
        encoding="utf-8",
    )
    inputs = "\n".join(
        (
            "8",
            "2",
            str(add_path),
            "1",
            "YES",
            "",
            "2",
            str(replace_path),
            "2",
            "YES",
            "",
            "3",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Import Standards Profile" in out
    assert "This should be one standalone standards profile JSON file." in out
    assert "Choose Import Mode." in out
    assert "1 = add only, 2 = replace existing profile." in out
    assert f"Added standards profile english_12_njsls from {add_path}." in out
    assert f"Replaced standards profile english_12_njsls from {replace_path}." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert library.profiles == (replace_profile,)


def test_menu_validate_missing_library_does_not_create_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "10\n\n11\n")

    assert code == 0
    assert "Validate Standards Library" in out
    assert "Checking the active workspace standards library." in out
    assert "This does not write files." in out
    assert "using empty library" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_opening_and_cancelling_guidance_workflows_does_not_create_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = "\n".join(
        (
            "6",
            "",
            "",
            "8",
            "1",
            "",
            "",
            "3",
            "9",
            "1",
            "",
            "",
            "3",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Create Standard Profile" in out
    assert "Import Full Standards Library" in out
    assert "Export Full Standards Library" in out
    assert "Cancelled." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []
    assert not library_file(tmp_path).exists()
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "ScoreForm").exists()
    assert not (tmp_path / "Quillan").exists()


@pytest.mark.parametrize(
    ("choice", "forbidden_prompt", "forbidden_guidance"),
    [
        ("1", "Status filter", "Browse Standards"),
        ("2", "Enter search text", "Search Standards"),
        ("3", "Enter Durable Standard ID", "View Standard"),
    ],
)
def test_empty_standards_actions_return_before_irrelevant_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    choice: str,
    forbidden_prompt: str,
    forbidden_guidance: str,
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, f"{choice}\n\n11\n")

    assert code == 0
    assert "No standards found." in out
    assert forbidden_prompt not in out
    assert forbidden_guidance not in out
    assert "Press Enter to continue..." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "ScoreForm").exists()
    assert not (tmp_path / "Quillan").exists()


@pytest.mark.parametrize(
    ("choice", "forbidden_prompt", "forbidden_guidance"),
    [
        ("4", "Profile Source Filter", "Browse Profiles"),
        ("5", "Enter Durable Profile ID", "View Profile"),
    ],
)
def test_empty_profile_actions_return_before_irrelevant_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    choice: str,
    forbidden_prompt: str,
    forbidden_guidance: str,
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, f"{choice}\n\n11\n")

    assert code == 0
    assert "No standards profiles found." in out
    assert forbidden_prompt not in out
    assert forbidden_guidance not in out
    assert "Press Enter to continue..." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_empty_profile_edit_does_not_enter_submenu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "7\n\n11\n")

    assert code == 0
    assert "No standards profiles found." in out
    assert "Edit Profile Standards" not in out
    assert "Press Enter to continue..." in out
    assert err == ""


def test_empty_export_profile_returns_before_profile_id_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "9\n2\n\n3\n11\n")

    assert code == 0
    assert "Export Standards Profile" not in out
    assert "No standards profiles found." in out
    assert "Enter Durable Profile ID" not in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


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
        "7\n4\n8\n3\n9\n3\n11\n",
    )

    assert code == 0
    assert err == ""
    assert "[clear]\nStandards Management" in out
    assert "[clear]\nEdit Profile Standards" in out
    assert "[clear]\nImport Standards Data" in out
    assert "[clear]\nExport Standards Data" in out
    assert out.count("[clear]") >= 4


def test_create_profile_clears_before_first_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "6\n\n\n11\n")

    assert code == 0
    assert err == ""
    workflow_index = out.index("[clear]\nCreate Standard Profile")
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
            "4",
            "",
            "",
            "",
            "",
            "5",
            "",
            "",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    assert "[clear]\nBrowse Standards" in out
    assert "[clear]\nSearch Standards" in out
    assert "[clear]\nView Standard" in out
    assert "[clear]\nBrowse Profiles" in out
    assert "[clear]\nView Profile" in out


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
            "7",
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
            "8",
            "1",
            "",
            "",
            "2",
            "",
            "",
            "3",
            "9",
            "1",
            "",
            "",
            "2",
            "",
            "",
            "3",
            "11",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    assert "[clear]\nAdd Standard to Profile" in out
    assert "[clear]\nRemove Standard from Profile" in out
    assert "[clear]\nReplace Profile Standards" in out
    assert "[clear]\nImport Full Standards Library" in out
    assert "[clear]\nImport Standards Profile" in out
    assert "[clear]\nExport Full Standards Library" in out
    assert "[clear]\nExport Standards Profile" in out


def test_validate_clears_before_validation_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mark_clear(stdout: io.TextIOBase) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "10\n\n11\n")

    assert code == 0
    assert err == ""
    assert "[clear]\nValidate Standards Library" in out


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
        "\n".join(("1", "3", "", "", "", "", "", "", "", "11", "")),
    )

    assert code == 0
    assert err == ""
    result_index = out.index("njsls-ela:RL.CR.11-12.1 | RL.CR.11-12.1")
    pause_index = out.index("Press Enter to continue...")
    next_menu_index = out.index("[clear]\nStandards Management", pause_index)
    assert result_index < pause_index < next_menu_index


def test_menu_invalid_existing_library_reports_handled_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library_file(tmp_path).parent.mkdir()
    library_file(tmp_path).write_text("{", encoding="utf-8")

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "10\n11\n")

    assert code == 1
    assert out == ""
    assert "Error:" in err
    assert "Traceback" not in err


def test_menu_does_not_expose_destructive_delete_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "7\n4\n11\n")

    assert code == 0
    assert "delete standard" not in out.lower()
    assert "delete profile" not in out.lower()
    assert err == ""
