"""Post-publication identity: Core #232 / v0.6.6."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "35af5d0642e84a625cd143285c4ef6de98dbcca4"
WHEEL_SHA = "d6d21e426092b0329bcfd69b6fbee44c345edc46794a914d847d5ea73a2b7301"
SDIST_SHA = "8917819bcb18c1a16388f161c967ecce7b97161d5bb6fd8acd848254b6c759a9"


def test_published_release_documentation_binds_exact_source_and_assets() -> None:
    notes = (ROOT / "docs/releases/v0.6.6.md").read_text(encoding="utf-8")
    assert "published and verified" in notes
    assert "2026-10-14" in notes
    assert COMMIT in notes
    assert WHEEL_SHA in notes
    assert SDIST_SHA in notes
    assert "releases/tag/v0.6.6" in notes
    assert "## Final publication details" in notes
    assert "**Pending:**" not in notes


def test_current_installation_guidance_points_to_published_version() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Core v0.6.6 is the latest published Core release" in readme
    assert "Core v0.6.5 remains an immutable historical release" in readme
    assert "pds-core>=0.6.6,<0.7" in readme
    assert "directory junction alias" in readme
    assert "do not install the v0.6.6 candidate" not in readme
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [0.6.6] - 2026-10-14" in changelog
    assert "## [0.6.6] - Pending release" not in changelog


def test_v066_compatibility_matrix_active_but_historical_preserved() -> None:
    docs = (ROOT / "docs/released_consumer_compatibility.md").read_text(
        encoding="utf-8"
    )
    assert "## Active Core v0.6.6 qualification (#232)" in docs
    assert "tests/fixtures/released_consumers/v3/manifest.json" in docs
    assert "## Historical Core v0.6.5 qualification (#229)" in docs
    assert "## Historical Core v0.6.4 qualification (#226)" in docs
    assert (ROOT / "tests/fixtures/released_consumers/v1/manifest.json").is_file()
    assert (ROOT / "tests/fixtures/released_consumers/v2/manifest.json").is_file()
    assert (ROOT / "tests/fixtures/released_consumers/v3/manifest.json").is_file()
    with (ROOT / "pyproject.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    assert metadata["project"]["version"] == "0.6.6"
