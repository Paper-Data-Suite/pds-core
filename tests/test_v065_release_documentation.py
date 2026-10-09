"""Issue #229: v0.6.5 release identity, versioned CI and neutrality."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v065_candidate_version_is_consistent_and_has_no_sibling_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = (ROOT / "pds_core/__init__.py").read_text(encoding="utf-8")
    assert project["project"]["version"] == "0.6.5"
    assert '__version__ = "0.6.5"' in runtime
    assert project["project"]["dependencies"] == []


def test_v065_active_ci_uses_new_artifacts_and_exact_v2_matrix() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for required in (
        "verify_v065_release_artifacts.py",
        "verify_v065_installed_acceptance.py",
        "qualify_issue229_reader_metadata_wheel.py",
        "pds_core-0.6.5-py3-none-any.whl",
        "tests/fixtures/released_consumers/v2/manifest.json",
        "scripts/qualify_released_consumers.py",
        "scripts/verify_issue226_installed_acceptance.py",
    ):
        assert required in workflow
    assert "verify_v064_release_artifacts.py" not in workflow
    assert "verify_v064_installed_acceptance.py" not in workflow
    fixture = json.loads((ROOT / "tests/fixtures/released_consumers/v2/manifest.json").read_text(encoding="utf-8"))
    assert fixture["candidate_core_version"] == "0.6.5"


def test_v064_historical_scripts_and_fixture_remain_accessible() -> None:
    for path in (
        "scripts/verify_v064_release_artifacts.py",
        "scripts/verify_v064_installed_acceptance.py",
        "scripts/write_v064_release_checksums.py",
        "docs/releases/v0.6.4.md",
        "tests/fixtures/released_consumers/v1/manifest.json",
    ):
        assert (ROOT / path).is_file()
    assert (ROOT / "scripts/verify_v064_release_artifacts.py").read_text(encoding="utf-8").find('VERSION: Final[str] = "0.6.4"') > 0


def test_v065_release_notes_and_candidate_label_are_accurate() -> None:
    notes = (ROOT / "docs/releases/v0.6.5.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plan = (ROOT / "docs/validation/issue-229-v065-release-plan.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "v0.6.5" in notes
    assert "merged to main" in notes.lower()
    assert "pr #230" in notes.lower()
    assert "has not yet been tagged or published" in notes.lower()
    assert "not yet tagged, merged or released" not in notes.lower()
    assert "v0.6.5" in readme and "candidate" in readme.lower()
    assert "merged onto `main` via #230" in readme
    assert "on the #229 release-preparation branch" not in readme
    assert "v0.6.5" in changelog or "0.6.5" in changelog
    assert "version is now set to 0.6.5" in plan
    assert "0.6.4" in plan
    assert "No tag or GitHub Release" in plan
    assert "03246532a6f35b5561729ad377240b9927217f73" in plan
    compatibility = (ROOT / "docs/released_consumer_compatibility.md").read_text(encoding="utf-8")
    assert "## Active Core v0.6.5 qualification (#229)" in compatibility
    assert "tests/fixtures/released_consumers/v2/manifest.json" in compatibility
    assert "**Target version:** v0.6.5 (Core #229)\n" in notes
    assert "**Release date:** Not yet set\n" in notes
