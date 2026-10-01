"""Release-specific documentation and CI assertions for pds-core v0.6.4."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v064_release_notes_cover_issue226_scope_and_boundaries() -> None:
    release = (ROOT / "docs" / "releases" / "v0.6.4.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "pds-core v0.6.4",
        "#226",
        "107 characters",
        "RetainedSourceScan.source_filename",
        "LongPathsEnabled = 1",
        "No workspace migration is required",
        "pds_core-0.6.4-py3-none-any.whl",
        "pds_core-0.6.4.tar.gz",
        "SHA256SUMS.txt",
        "exact merge commit",
        "ScoreForm",
        "0.11.0",
        "Quillan",
        "0.10.4",
        "Paper Data Suite",
        "historical release blocker",
        "Portia",
    ):
        assert marker in release

    for prohibited_claim in (
        "existing retained scans are renamed",
        "Core modifies LongPathsEnabled",
        "Portia 0.",
    ):
        assert prohibited_claim not in release


def test_v064_tracked_version_and_release_tooling_are_active() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = (ROOT / "pds_core" / "__init__.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    compatibility = (ROOT / "scripts" / "released_consumer_compatibility.py").read_text(
        encoding="utf-8"
    )
    fixture = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "released_consumers"
            / "v1"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert project["project"]["version"] == "0.6.4"
    assert '__version__ = "0.6.4"' in runtime
    assert 'EXPECTED_CORE_VERSION: Final[str] = "0.6.4"' in compatibility
    assert fixture["candidate_core_version"] == "0.6.4"
    assert "scripts/verify_v064_release_artifacts.py" in workflow
    assert "scripts/verify_v064_installed_acceptance.py" in workflow
    assert "scripts/verify_issue226_installed_acceptance.py" in workflow
    assert "pds_core-0.6.4-py3-none-any.whl" in workflow
    assert "PDS_CORE_SDIST_VENV" in workflow
    assert "Install sdist and run v0.6.4 acceptance" in workflow
    assert "python -m build --wheel" in workflow
