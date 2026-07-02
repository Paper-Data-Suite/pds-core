"""Interactive menu coverage for starter standards workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import load_standards_library
from tests.cli_menu.conftest import library_file, run_menu


def test_menu_starter_list_and_back_do_not_create_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "5\n1\n\n5\n6\n")

    assert code == 0
    assert "Starter Standards" in out
    assert "1. 2023 NJSLS ELA High School Starter Standards" in out
    assert "njsls_ela_2023" in out
    assert "This does not write files." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_menu_starter_install_requires_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "5\n4\n1\n\n5\n6\n",
    )

    assert code == 0
    assert "Install Starter Standards" in out
    assert "Choose a starter standards pack:" in out
    assert "Pack ID: njsls_ela_2023" in out
    assert "Cancelled." in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_menu_starter_install_writes_library_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "5\n4\n1\nYES\n\n5\n6\n",
    )

    assert code == 0
    assert "Choose a starter standards pack:" in out
    assert "Confirm Starter Standards Install" in out
    assert "Installed starter standards pack: njsls_ela_2023" in out
    assert err == ""
    assert library_file(tmp_path).is_file()
    library = load_standards_library(library_file(tmp_path))
    assert len(library.standards) == 64
    assert len(library.profiles) == 2
    assert not (tmp_path / "standards" / "usage").exists()


def test_menu_starter_preview_uses_numbered_pack_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "5\n2\n1\n\n5\n6\n",
    )

    assert code == 0
    assert "Preview Starter Standards" in out
    assert "Choose a starter standards pack:" in out
    assert "1. 2023 NJSLS ELA High School Starter Standards" in out
    assert "Pack ID: njsls_ela_2023" in out
    assert "Profile IDs: english10_2023_njsls_ela, english12_2023_njsls_ela" in out
    assert "Enter Starter Standards Pack ID" not in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_menu_starter_validate_can_choose_all_or_one_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "5\n3\n1\n\n3\n2\n1\n\n5\n6\n",
    )

    assert code == 0
    assert "1. Validate all starter standards packs" in out
    assert "2. Choose a starter standards pack to validate" in out
    assert "Starter standards pack is valid: njsls_ela_2023" in out
    assert out.count("Starter standards pack is valid: njsls_ela_2023") == 2
    assert err == ""
    assert list(tmp_path.iterdir()) == []
