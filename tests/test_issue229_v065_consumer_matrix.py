"""Core #229 release-preparation: preserve 0.6.4 and qualify 0.6.5 matrix."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

from scripts.released_consumer_compatibility import (
    EXPECTED_CORE_VERSION,
    SUPPORTED_RELEASE_CANDIDATE_VERSIONS,
    CompatibilityFixtureError,
    load_compatibility_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "tests/fixtures/released_consumers/v1/manifest.json"
NEW = ROOT / "tests/fixtures/released_consumers/v2/manifest.json"
GIT_BLOB_V064 = "6d9cc300e8336c6a1dd5de75abde3c3557f3fd58"
RELEASES = {
    "scoreform": ("0.12.1", "0f71b709eafe351052eac3e4f0d474b7bef36aeec347df05361b0a8995d44d32"),
    "quillan": ("0.10.5", "031e5a5455c222da6b9a7d8f72e7823dd4c61acde7d90ddce94b49d9bcbe123f"),
    "concord": ("0.3.0", "dd827f7059c91c79bd69b6190b3c673d6b3bbc02bc25fa666286bbf5883c5e12"),
    "meridian": ("0.3.1", "9238a70a71a6ca41330ac3c33fc445b8028bf5bed501975daebe9ff771290a69"),
    "vitrine": ("0.3.0", "69d2d1ea8a90b5d25c813da3c852232a0e0a9e7094e2b4d217f22662022596b8"),
    "paper_data_suite": ("0.1.0", "4830a3cbffad7c2a6ad237df8730e8da1acb78c7f462bfef683d8d889ee162b9"),
}


def _raw(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_v064_fixture_is_byte_identical_to_historical_reviewed_git_blob() -> None:
    raw = OLD.read_bytes()
    canonical = raw.replace(b"\r\n", b"\n")
    actual = hashlib.sha1(
        f"blob {len(canonical)}\0".encode("ascii") + canonical
    ).hexdigest()
    assert actual == GIT_BLOB_V064
    assert EXPECTED_CORE_VERSION == "0.6.4"  # Historical default remains stable.
    assert load_compatibility_fixture(OLD).candidate_core_version == "0.6.4"


def test_v065_is_explicit_addition_and_both_versions_supported() -> None:
    assert SUPPORTED_RELEASE_CANDIDATE_VERSIONS == frozenset({"0.6.4", "0.6.5"})
    assert load_compatibility_fixture(NEW).candidate_core_version == "0.6.5"
    assert load_compatibility_fixture(OLD).candidate_core_version == "0.6.4"


def test_v065_exact_verified_published_consumer_matrix() -> None:
    current = load_compatibility_fixture(NEW)
    assert len(current.consumers) == 6
    assert set(current.by_component_id()) == set(RELEASES)
    for item in current.consumers:
        version, digest = RELEASES[item.component_id]
        assert item.version == version
        assert item.release.tag == f"v{version}"
        assert item.release.sha256 == digest
        assert item.release.sha256_source == "github-release-asset-digest"
        assert item.release.wheel.endswith(f"-{version}-py3-none-any.whl")
        assert item.release.download_url == (
            f"https://github.com/{item.repository}/releases/download/"
            f"{item.release.tag}/{item.release.wheel}"
        )
        assert Version("0.6.5") in Requirement(item.core_requirement).specifier


def test_v065_changes_only_explicit_candidate_and_refreshed_release_rows() -> None:
    older = _raw(OLD)
    newer = _raw(NEW)
    assert newer["candidate_core_version"] == "0.6.5"
    older["candidate_core_version"] = "0.6.5"
    for old, new in zip(older["consumers"], newer["consumers"], strict=True):
        assert old["component_id"] == new["component_id"]
        if old["component_id"] in {"scoreform", "quillan", "meridian"}:
            for field in ("version", "core_requirement"):
                old[field] = new[field]
            for field in ("tag", "wheel", "download_url", "sha256"):
                old["release"][field] = new["release"][field]
    assert older == newer


@pytest.mark.parametrize("unsupported", ["0.6.3", "0.6.6", "1.0.0"])
def test_version_scope_rejects_unreviewed_candidates(
    tmp_path: Path, unsupported: str
) -> None:
    value = _raw(NEW)
    value["candidate_core_version"] = unsupported
    path = tmp_path / "unreviewed.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="fixture must target Core"):
        load_compatibility_fixture(path)


def test_consumer_matrix_is_a_frozen_qualification_snapshot_not_a_dependency() -> None:
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dependencies"] == []
    plan = (ROOT / "docs/validation/issue-229-v065-release-plan.md").read_text(
        encoding="utf-8"
    )
    assert "frozen qualification snapshot" in plan
    assert "does **not** require any Core change" in plan
    assert "not** installed or imported by Core" in plan


def test_release_candidate_notes_do_not_claim_final_release() -> None:
    release = (ROOT / "docs/releases/v0.6.5.md").read_text(encoding="utf-8")
    plan = (ROOT / "docs/validation/issue-229-v065-release-plan.md").read_text(encoding="utf-8")
    for marker in ("v0.6.5", "#229", "Meridian #111", "Vitrine #103", "Portia #66"):
        assert marker in release
    for marker in ("not released", "exact merge commit", "Core 0.6.4", "0.6.5"):
        assert marker in plan
    assert "candidate" in release.lower()
    assert "historical" in plan.lower()
