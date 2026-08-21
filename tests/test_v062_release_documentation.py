"""Release-specific documentation and CI assertions for pds-core v0.6.2."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v062_release_notes_cover_surviving_scope_and_boundaries() -> None:
    release = (ROOT / "docs" / "releases" / "v0.6.2.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "pds-core v0.6.2",
        "pds_core.roster_imports",
        "paper_data_suite.module_operations",
        'MODULE_OPERATIONS_CONTRACT_VERSION = "1"',
        "ScoreForm",
        "Quillan",
        "Concord",
        "Meridian",
        "Vitrine",
        "pds-paper-data-suite#38",
        "No workspace migration is required",
        "pds_core-0.6.2-py3-none-any.whl",
        "pds_core-0.6.2.tar.gz",
        "SHA256SUMS.txt",
        "provisional wheel created during #195 is not a",
        "exact merge commit",
    ):
        assert marker in release

    for prohibited_claim in (
        "Core owns suite release composition",
        "operations provider proves launchability",
        "automatic roster replacement",
    ):
        assert prohibited_claim not in release


def test_v062_release_tooling_is_documented_and_ci_uses_real_build() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    compatibility = (ROOT / "docs" / "released_consumer_compatibility.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/verify_v062_release_artifacts.py" in workflow
    assert "scripts/verify_v062_installed_acceptance.py" in workflow
    assert "python -m build --wheel" in workflow
    assert "scripts/qualify_released_consumers.py" in workflow
    assert "scripts/build_v062_provisional_candidate.py" not in workflow
    assert "historical #195" in compatibility.lower()
    assert "normal tracked-version build" in compatibility
