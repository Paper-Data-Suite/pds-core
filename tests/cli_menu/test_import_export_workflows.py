"""Import and export workflow tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.standards import (
    StandardsLibrary,
    StandardsProfile,
    load_standards_library,
    standards_library_to_dict,
    standards_profile_to_dict,
    write_workspace_standards_library,
)
from tests.cli_menu.conftest import library_file, run_menu
from tests.test_cli import make_cli_library

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
            "3",
            "2",
            str(library_export),
            "no",
            "",
            "2",
            str(library_export),
            "YES",
            "YES",
            "",
            "4",
            "english_12_njsls",
            str(profile_export),
            "no",
            "",
            "4",
            "english_12_njsls",
            str(profile_export),
            "YES",
            "YES",
            "",
            "5",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Import / Export" in out
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
            "3",
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
            "5",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Import / Export" in out
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
            "3",
            "3",
            str(add_path),
            "1",
            "YES",
            "",
            "3",
            str(replace_path),
            "2",
            "YES",
            "",
            "5",
            "5",
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


def test_empty_export_profile_returns_before_profile_id_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "3\n4\n\n5\n5\n")

    assert code == 0
    assert "Export Standards Profile" not in out
    assert "No standards profiles found." in out
    assert "Enter Durable Profile ID" not in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []
