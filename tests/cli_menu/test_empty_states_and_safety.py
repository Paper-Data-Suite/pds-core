"""Empty-state, cancellation, and artifact-safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli_menu.conftest import library_file, run_menu

def test_menu_validate_missing_library_does_not_create_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "4\n\n6\n")

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
            "1",
            "4",
            "",
            "",
            "5",
            "2",
            "3",
            "3",
            "",
            "7",
            "3",
            "1",
            "",
            "",
            "5",
            "3",
            "2",
            "",
            "",
            "5",
            "6",
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
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "\n".join(("1", choice, "", "5", "6", "")),
    )

    assert code == 0
    assert "No standards found." in out
    assert forbidden_prompt not in out
    assert forbidden_guidance not in out
    assert "Press Enter to return to the Standards menu..." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "ScoreForm").exists()
    assert not (tmp_path / "Quillan").exists()


@pytest.mark.parametrize(
    ("choice", "forbidden_prompt", "forbidden_guidance"),
    [
        ("1", "Profile Source Filter", "Browse Profiles"),
        ("2", "Enter Durable Profile ID", "View Profile"),
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
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "\n".join(("2", choice, "", "7", "6", "")),
    )

    assert code == 0
    assert "No standards profiles found." in out
    assert forbidden_prompt not in out
    assert forbidden_guidance not in out
    assert "Press Enter to return to the Profiles menu..." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_empty_profile_edit_does_not_enter_submenu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "2\n4\n\n7\n6\n")

    assert code == 0
    assert "No standards profiles found." in out
    assert "Edit Profile Standards" not in out
    assert "Press Enter to return to the Profiles menu..." in out
    assert err == ""


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
