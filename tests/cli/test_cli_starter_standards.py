"""Starter standards CLI tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import load_standards_library, standards_library_path
from tests.cli.conftest import run_cli


PACK_ID = "njsls_ela_2023"


def test_starter_list_and_preview_do_not_touch_workspace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "list",
        capsys=capsys,
    )

    assert code == 0
    assert PACK_ID in out
    assert "2023 NJSLS-ELA" in out
    assert "grade bands: 9-10, 11-12" in out
    assert "64 standards" in out
    assert "2 profiles" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "preview",
        PACK_ID,
        capsys=capsys,
    )

    assert code == 0
    assert "English 10" in out
    assert "english10_2023_njsls_ela" in out
    assert "english12_2023_njsls_ela" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_starter_validate_reports_success_without_workspace_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "validate",
        capsys=capsys,
    )

    assert code == 0
    assert f"Starter standards pack is valid: {PACK_ID}" in out
    assert "(64 standards, 2 profiles)" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_starter_install_writes_expected_library_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "install",
        PACK_ID,
        capsys=capsys,
    )

    assert code == 0
    assert f"Installed starter standards pack: {PACK_ID}" in out
    assert "Standards: 64 added, 0 skipped, 0 overwritten." in out
    assert "Profiles: 2 added, 0 skipped, 0 overwritten." in out
    assert "No standards usage events were recorded." in out
    assert err == ""
    assert standards_library_path(tmp_path).is_file()
    library = load_standards_library(standards_library_path(tmp_path))
    assert len(library.standards) == 64
    assert len(library.profiles) == 2
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "classes").exists()
    assert not (tmp_path / "assignments").exists()
    assert not (tmp_path / "pds-quillan").exists()
    assert not (tmp_path / "pds-scoreform").exists()


def test_starter_install_repeated_run_is_clear_and_idempotent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(
        tmp_path,
        "standards",
        "starter",
        "install",
        PACK_ID,
        capsys=capsys,
    )
    before = standards_library_path(tmp_path).read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "install",
        PACK_ID,
        capsys=capsys,
    )

    assert code == 0
    assert "Standards: 0 added, 64 skipped, 0 overwritten." in out
    assert "Profiles: 0 added, 2 skipped, 0 overwritten." in out
    assert "No workspace changes were needed." in out
    assert err == ""
    assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before


def test_starter_install_refuses_conflicts_without_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(
        tmp_path,
        "standards",
        "starter",
        "install",
        PACK_ID,
        capsys=capsys,
    )
    library_path = standards_library_path(tmp_path)
    content = library_path.read_text(encoding="utf-8")
    library_path.write_text(
        content.replace(
            "Language System and Structure",
            "Teacher Edited Language Standard",
        ),
        encoding="utf-8",
    )
    before = library_path.read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "install",
        PACK_ID,
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "conflicts with existing workspace standards data" in err
    assert "njsls-ela:L.SS.9-10.1" in err
    assert library_path.read_text(encoding="utf-8") == before


def test_starter_install_overwrite_requires_explicit_flag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(
        tmp_path,
        "standards",
        "starter",
        "install",
        PACK_ID,
        capsys=capsys,
    )
    library_path = standards_library_path(tmp_path)
    content = library_path.read_text(encoding="utf-8")
    library_path.write_text(
        content.replace(
            "Language System and Structure",
            "Teacher Edited Language Standard",
        ),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "install",
        PACK_ID,
        "--overwrite",
        capsys=capsys,
    )

    assert code == 0
    assert "Standards: 0 added, 62 skipped, 2 overwritten." in out
    assert err == ""
    assert load_standards_library(library_path).standards[0].short_name == (
        "Language System and Structure"
    )
