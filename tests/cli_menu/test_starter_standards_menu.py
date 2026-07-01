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
    code, out, err = run_menu(tmp_path, monkeypatch, capsys, "S\n1\n\n5\n5\n")

    assert code == 0
    assert "Starter Standards" in out
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
        "S\n4\nnjsls_ela_2023\n\n5\n5\n",
    )

    assert code == 0
    assert "Install Starter Standards" in out
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
        "S\n4\nnjsls_ela_2023\nYES\n\n5\n5\n",
    )

    assert code == 0
    assert "Installed starter standards pack: njsls_ela_2023" in out
    assert err == ""
    assert library_file(tmp_path).is_file()
    library = load_standards_library(library_file(tmp_path))
    assert len(library.standards) == 64
    assert len(library.profiles) == 2
    assert not (tmp_path / "standards" / "usage").exists()
