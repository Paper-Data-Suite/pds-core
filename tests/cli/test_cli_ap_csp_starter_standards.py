"""CLI coverage for the AP CSP Fall 2023 framework-reference starter pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import load_standards_library, standards_library_path
from tests.cli.conftest import run_cli

PACK_ID = "ap_csp_fall_2023"


def test_ap_csp_list_preview_and_validate_are_reference_friendly(
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
    assert "College Board AP CSP Fall 2023" in out
    assert "grade bands: not specified" in out
    assert "95 standards" in out
    assert "3 profiles" in out
    assert err == ""

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "preview",
        PACK_ID,
        capsys=capsys,
    )
    assert code == 0
    assert "Grade bands: not specified" in out
    assert "AP Computer Science Principles" in out
    assert "ap_csp_course_content_fall_2023" in out
    assert "ap_csp_computational_thinking_fall_2023" in out
    assert "Framework IDs: ap_csp_fall_2023" in out
    assert "Protected College Board framework prose is not bundled" in out
    assert err == ""

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "validate",
        PACK_ID,
        capsys=capsys,
    )
    assert code == 0
    assert "(95 standards, 3 profiles, frameworks: 1)" in out
    assert err == ""


def test_ap_csp_install_reports_reference_counts(
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
    assert "Standards: 95 added, 0 skipped, 0 overwritten." in out
    assert "Profiles: 3 added, 0 skipped, 0 overwritten." in out
    assert "Frameworks: 1 added, 0 skipped, 0 overwritten." in out
    assert err == ""
    library = load_standards_library(standards_library_path(tmp_path))
    assert len(library.standards) == 95
    assert len(library.profiles) == 3
    assert library.frameworks[0].framework_id == "ap_csp_fall_2023"


def test_cli_validate_all_reports_four_bundled_packs(
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
    for pack_id in (
        "ap_csp_fall_2023",
        "njsls_clks_2020",
        "njsls_csdt_2020",
        "njsls_ela_2023",
    ):
        assert f"Starter standards pack is valid: {pack_id}" in out
    assert err == ""
