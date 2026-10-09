"""Release-specific documentation and CI assertions for pds-core v0.6.3."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v063_release_notes_cover_standards_scope_and_boundaries() -> None:
    release = (ROOT / "docs" / "releases" / "v0.6.3.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "pds-core v0.6.3",
        "StandardsFrameworkMetadata",
        "ap_csp_fall_2023",
        "njsls_clks_2020",
        "njsls_csdt_2020",
        "njsls_ela_2023",
        "694",
        "12 profiles",
        "4 frameworks",
        "english11_2023_njsls_ela",
        "pds-paper-data-suite#44",
        "No workspace migration is required",
        "pds_core-0.6.3-py3-none-any.whl",
        "pds_core-0.6.3.tar.gz",
        "SHA256SUMS.txt",
        "exact merge commit",
    ):
        assert marker in release

    for prohibited_claim in (
        "Core owns suite release composition",
        "AP CSP framework prose is redistributed",
        "Core automatically selects framework currentness",
    ):
        assert prohibited_claim not in release


def test_v063_release_tooling_remains_historical_while_ci_uses_v065() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    compatibility = (ROOT / "docs" / "released_consumer_compatibility.md").read_text(
        encoding="utf-8"
    )

    assert (ROOT / "scripts/verify_v064_release_artifacts.py").is_file()
    assert (ROOT / "scripts/verify_v064_installed_acceptance.py").is_file()
    assert "scripts/verify_v065_release_artifacts.py" in workflow
    assert "scripts/verify_v065_installed_acceptance.py" in workflow
    assert "scripts/verify_v064_release_artifacts.py" not in workflow
    assert "scripts/verify_v064_installed_acceptance.py" not in workflow
    assert "pds_core-0.6.5-py3-none-any.whl" in workflow
    assert "tests/fixtures/released_consumers/v2/manifest.json" in workflow
    assert "python -m build --wheel" in workflow
    assert "scripts/qualify_released_consumers.py" in workflow
    assert "scripts/build_v062_provisional_candidate.py" not in workflow
    qualifier = (ROOT / "scripts" / "qualify_released_consumers.py").read_text(
        encoding="utf-8"
    )
    assert "against one explicit pds-core candidate wheel and release fixture" in qualifier
    assert 'f"{core_wheel.stem}-released-consumer-qualification.json"' in qualifier
    assert "pds-core 0.6.2 candidate wheel" not in qualifier
    assert "pds_core-0.6.2-released-consumer-qualification.json" not in qualifier
    assert "Core v0.6.4" in compatibility
    assert "normal tracked-version build" in compatibility
    assert "pds-paper-data-suite#44" in compatibility
