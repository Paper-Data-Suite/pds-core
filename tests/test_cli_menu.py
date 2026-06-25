"""Tests for the interactive standards management menu."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import TextIO, cast

import pytest

from pds_core.cli import main
from pds_core.cli_support.menu import StandardsMenu
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


def assert_durable_standard_id_guidance(out: str) -> None:
    assert "Use the full durable standard_id, not only the display code." in out
    assert "Correct example: njsls-ela:L.KL.11-12.2" in out
    assert "Not enough: L.KL.11-12.2" in out


def test_menu_opens_and_exits_via_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "12\n")

    assert code == 0
    assert "Standards Management" in out
    assert "4. Add standard" in out
    assert "7. Create Standard Profile" in out
    assert "6. Create profile" not in out
    assert "12. Back" in out
    assert "Back." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_menu_handles_invalid_and_blank_choices_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "nope\n\n12\n")

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
            "12",
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
    assert "Use Browse Standards or Search Standards first if you need to copy IDs." in out
    assert_durable_standard_id_guidance(out)
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
            "5",
            "",
            "",
            "",
            "",
            "6",
            "english_12_njsls",
            "",
            "6",
            "missing_profile",
            "",
            "12",
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
            "7",
            "cancelled_profile",
            "Cancelled",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "no",
            "",
            "7",
            "english_12_new",
            "English 12 New",
            "",
            "English Language Arts",
            "English 12",
            "NJSLS-ELA",
            "English Language Arts",
            "English 12",
            "",
            "2,3",
            "YES",
            "",
            "12",
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
    assert "Filter Standards for Profile Selection" in out
    assert "Select Standards for This Profile" in out
    assert "Enter numbers separated by commas." in out
    assert "RI.CR.11-12.1 - Informational Text Evidence" in out
    assert "RL.CR.11-12.1 - Close Reading Evidence" in out
    assert "Review Standard Profile" in out
    assert "Selected Standards:" in out
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
    ("selection", "expected_error"),
    [
        ("missing:standard", "'missing:standard' is not a menu number"),
        ("99", "99 is outside"),
    ],
)
def test_menu_create_profile_rejects_invalid_selection_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection: str,
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
            "7",
            "bad_profile",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            selection,
            "",
            "no",
            "",
            "12",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Created standards profile bad_profile." not in out
    assert "Invalid selection:" in out
    assert expected_error in out
    assert err == ""
    assert library_file(tmp_path).read_text(encoding="utf-8") == before


def test_menu_create_profile_retries_invalid_selection_without_metadata_restart(
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
            "7",
            "english_12_language_standards",
            "English 12 Language Standards",
            "Language standards for English 12.",
            "English Language Arts",
            "English 12",
            "NJSLS-ELA",
            "English Language Arts",
            "English 12",
            "",
            "RL.CR.11-12.1",
            "3",
            "YES",
            "",
            "12",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert out.count("Enter Durable Profile ID.") == 1
    assert out.count("Enter Profile Title.") == 1
    assert out.count("Select Standards for This Profile") == 2
    assert "Invalid selection:" in out
    assert "'RL.CR.11-12.1' is not a menu number" in out
    assert "Review Standard Profile" in out
    assert "Title: English 12 Language Standards" in out
    assert "Created standards profile english_12_language_standards." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    profile = library.profiles[0]
    assert profile.profile_id == "english_12_language_standards"
    assert profile.title == "English 12 Language Standards"
    assert profile.description == "Language standards for English 12."
    assert profile.standards == ("njsls-ela:RL.CR.11-12.1",)


def test_menu_create_profile_retries_invalid_selection_then_accepts_blank(
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
            "7",
            "empty_language_profile",
            "Empty Language Profile",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "RL.CR.11-12.1",
            "",
            "YES",
            "",
            "12",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Invalid selection:" in out
    assert "Review Standard Profile" in out
    assert "Standards: 0" in out
    assert "Created standards profile empty_language_profile." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert library.profiles[0].standards == ()


def test_menu_add_standard_normalizes_common_dash_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = "\n".join(
        (
            "4",
            "njsls-ela:L.VI.11\u201312.4",
            "L.VI.11-12.4",
            "",
            "Demonstrate understanding of figurative language.",
            "NJSLS-ELA 2023",
            "English Language Arts",
            "English 12",
            "Language",
            "no",
            "YES",
            "",
            "12",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Created standard njsls-ela:L.VI.11-12.4." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert library.standards[0].standard_id == "njsls-ela:L.VI.11-12.4"
    assert library.standards[0].description == (
        "Demonstrate understanding of figurative language."
    )


def test_menu_add_standard_creates_subpart_definitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = "\n".join(
        (
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
            "12",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Review Standard" in out
    assert "Subparts:" in out
    assert "L.VI.11-12.4.A - Figures of Speech" in out
    assert "Created standard njsls-ela:L.VI.11-12.4." in out
    assert "Created standard njsls-ela:L.VI.11-12.4.A." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert tuple(definition.standard_id for definition in library.standards) == (
        "njsls-ela:L.VI.11-12.4",
        "njsls-ela:L.VI.11-12.4.A",
    )
    assert library.standards[1].description == (
        "Interpret figures of speech in context."
    )


def test_menu_create_profile_rejects_duplicate_profile_id_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    before = library_file(tmp_path).read_text(encoding="utf-8")
    inputs = "\n".join(
        (
            "7",
            "english_12_njsls",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "12",
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
            "8",
            "1",
            "english_12_local",
            "1",
            "YES",
            "",
            "2",
            "english_12_local",
            "1",
            "YES",
            "",
            "3",
            "english_12_njsls",
            "English Language Arts",
            "English 12",
            "Writing",
            "1",
            "YES",
            "",
            "4",
            "12",
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
    assert "Available Standards Not In This Profile" in out
    assert "Remove Standard from Profile" in out
    assert "This only changes profile membership. It does not delete the standard." in out
    assert "Current Standards" in out
    assert "Replace Profile Standards" in out
    assert "This will replace only the profile's standards list." in out
    assert "Profile metadata will be preserved." in out
    assert "Select Replacement Standards" in out
    assert "Enter numbers separated by commas." in out
    assert "Added 1 standard(s) to profile english_12_local." in out
    assert "Removed 1 standard(s) from profile english_12_local." in out
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
    ("inputs", "expected_output", "expected_error"),
    [
        (
            ("8", "1", "english_12_njsls", "99", "", "4", "12", ""),
            "Invalid selection: 99 is outside",
            "",
        ),
        (
            ("8", "2", "english_12_local", "99", "", "4", "12", ""),
            "Invalid selection: 99 is outside",
            "",
        ),
        (
            ("8", "1", "missing_profile", "", "4", "12", ""),
            "",
            "standards profile not found",
        ),
    ],
)
def test_menu_membership_failures_do_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    inputs: tuple[str, ...],
    expected_output: str,
    expected_error: str,
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    before = library_file(tmp_path).read_text(encoding="utf-8")
    input_text = "\n".join(inputs)

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, input_text)

    assert code == 0
    if expected_output:
        assert expected_output in out
    if expected_error:
        assert expected_error in err
    assert library_file(tmp_path).read_text(encoding="utf-8") == before


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
            "10",
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
            "12",
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
            "9",
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
            "12",
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
            "9",
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
            "12",
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
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "11\n\n12\n")

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
            "4",
            "",
            "",
            "7",
            "3",
            "",
            "9",
            "1",
            "",
            "",
            "3",
            "10",
            "1",
            "",
            "",
            "3",
            "12",
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
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, f"{choice}\n\n12\n")

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
        ("5", "Profile Source Filter", "Browse Profiles"),
        ("6", "Enter Durable Profile ID", "View Profile"),
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
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, f"{choice}\n\n12\n")

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
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "8\n\n12\n")

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
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "10\n2\n\n3\n12\n")

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
        "8\n4\n9\n3\n10\n3\n12\n",
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

    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "7\n\n12\n")

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
            "5",
            "",
            "",
            "",
            "",
            "6",
            "",
            "",
            "12",
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
            "8",
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
            "9",
            "1",
            "",
            "",
            "2",
            "",
            "",
            "3",
            "10",
            "1",
            "",
            "",
            "2",
            "",
            "",
            "3",
            "12",
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

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "11\n\n12\n")

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
        "\n".join(("1", "3", "", "", "", "", "", "", "", "12", "")),
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

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "11\n12\n")

    assert code == 1
    assert out == ""
    assert "Error:" in err
    assert "Traceback" not in err


def test_menu_does_not_expose_destructive_delete_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "8\n4\n12\n")

    assert code == 0
    assert "delete standard" not in out.lower()
    assert "delete profile" not in out.lower()
    assert err == ""
