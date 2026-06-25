"""Profile workflow tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import (
    StandardsLibrary,
    load_standards_library,
    write_workspace_standards_library,
)
from tests.cli_menu.conftest import library_file, run_menu
from tests.test_cli import make_cli_library

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
            "2",
            "3",
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
            "3",
            "english_12_new",
            "English 12 New",
            "",
            "English Language Arts",
            "English 12",
            "NJSLS-ELA",
            "1",
            "1",
            "",
            "2,3",
            "YES",
            "",
            "7",
            "5",
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
            "2",
            "3",
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
            "7",
            "5",
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
            "2",
            "3",
            "english_12_language_standards",
            "English 12 Language Standards",
            "Language standards for English 12.",
            "English Language Arts",
            "English 12",
            "NJSLS-ELA",
            "1",
            "1",
            "",
            "RL.CR.11-12.1",
            "3",
            "YES",
            "",
            "7",
            "5",
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
            "2",
            "3",
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
            "7",
            "5",
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


def test_menu_create_profile_rejects_duplicate_profile_id_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    before = library_file(tmp_path).read_text(encoding="utf-8")
    inputs = "\n".join(
        (
            "2",
            "3",
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
            "7",
            "5",
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
            "2",
            "4",
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
            "1",
            "1",
            "3",
            "1",
            "YES",
            "",
            "4",
            "7",
            "5",
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
            ("2", "4", "1", "english_12_njsls", "99", "", "4", "7", "5", ""),
            "Invalid selection: 99 is outside",
            "",
        ),
        (
            ("2", "4", "2", "english_12_local", "99", "", "4", "7", "5", ""),
            "Invalid selection: 99 is outside",
            "",
        ),
        (
            ("2", "4", "1", "missing_profile", "", "4", "7", "5", ""),
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
