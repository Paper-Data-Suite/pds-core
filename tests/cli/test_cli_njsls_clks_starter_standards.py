"""CLI coverage for the 2020 NJSLS-CLKS starter pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import load_standards_library, standards_library_path
from tests.cli.conftest import run_cli


PACK_ID = "njsls_clks_2020"


def test_clks_starter_list_preview_and_validate_are_discoverable(
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
    assert "2020 NJSLS-CLKS" in out
    assert "grade bands: K-2, 3-5, 6-8, 9-12" in out
    assert "301 standards" in out
    assert "4 profiles" in out
    assert "frameworks: 1" in out
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
    assert "Personal Financial Literacy" in out
    assert "Life Literacies and Key Skills" in out
    assert "personal_financial_literacy_9_12_2020_njsls_clks" in out
    assert "career_readiness_9_12_2020_njsls_clks" in out
    assert "life_literacies_9_12_2020_njsls_clks" in out
    assert "clks_9_12_2020_njsls_clks" in out
    assert "Framework IDs: njsls_clks_2020" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "starter",
        "validate",
        PACK_ID,
        capsys=capsys,
    )
    assert code == 0
    assert f"Starter standards pack is valid: {PACK_ID}" in out
    assert "(301 standards, 4 profiles, frameworks: 1)" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []


def test_clks_starter_install_reports_expected_counts(
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
    assert "Standards: 301 added, 0 skipped, 0 overwritten." in out
    assert "Profiles: 4 added, 0 skipped, 0 overwritten." in out
    assert "Frameworks: 1 added, 0 skipped, 0 overwritten." in out
    assert "No standards usage events were recorded." in out
    assert err == ""

    library = load_standards_library(standards_library_path(tmp_path))
    assert len(library.standards) == 301
    assert len(library.profiles) == 4
    assert len(library.frameworks) == 1
    assert library.frameworks[0].framework_id == "njsls_clks_2020"


def test_cli_validate_all_reports_three_bundled_packs(
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
    assert "Starter standards pack is valid: njsls_clks_2020" in out
    assert "Starter standards pack is valid: njsls_csdt_2020" in out
    assert "Starter standards pack is valid: njsls_ela_2023" in out
    assert err == ""
    assert list(tmp_path.iterdir()) == []
