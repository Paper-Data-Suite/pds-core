from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from scripts.characterize_issue226_quillan_release import characterization_evidence
from scripts.released_consumer_compatibility import load_compatibility_fixture

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "fixtures" / "released_consumers" / "v1" / "manifest.json"


def test_issue226_current_matrix_pins_exact_quillan_release() -> None:
    quillan = load_compatibility_fixture(MANIFEST).by_component_id()["quillan"]
    assert quillan.version == "0.10.3"
    assert quillan.core_requirement == "pds-core>=0.6.2,<0.7"
    assert quillan.release.sha256 == (
        "eb8f527d2dd43c3961374ac6a3f34a732827ce0bd3260943667160f8d2bf3e3b"
    )
    assert quillan.providers.module_operations == (
        "quillan.pds_operations:get_module_operations_profile"
    )


def test_issue226_characterization_evidence_is_deterministic_and_blocking() -> None:
    probe: dict[str, object] = {
        "candidate_core_version": "0.6.4",
        "fresh_bounded_provenance": "pass",
        "legacy_failure": "retained filename contradicts the Core retention event.",
        "legacy_v063_long_name_provenance": "fail",
        "quillan_version": "0.10.3",
        "release_blocker": True,
    }
    first = characterization_evidence(
        candidate_filename="pds_core-0.6.4-py3-none-any.whl",
        candidate_version="0.6.4",
        candidate_sha256="a" * 64,
        quillan_wheel="quillan-0.10.3-py3-none-any.whl",
        quillan_version="0.10.3",
        quillan_sha256="b" * 64,
        probe=probe,
    )
    second = characterization_evidence(
        candidate_filename="pds_core-0.6.4-py3-none-any.whl",
        candidate_version="0.6.4",
        candidate_sha256="a" * 64,
        quillan_wheel="quillan-0.10.3-py3-none-any.whl",
        quillan_version="0.10.3",
        quillan_sha256="b" * 64,
        probe=probe,
    )
    assert first == second
    parsed = cast(dict[str, object], json.loads(first))
    assert parsed["characterization_status"] == "release_blocker_confirmed"
    assert str(ROOT) not in first.decode("utf-8")


def test_issue226_compatibility_documentation_does_not_misstate_characterization() -> None:
    document = (ROOT / "docs" / "released_consumer_compatibility.md").read_text(
        encoding="utf-8"
    )
    assert "Quillan 0.10.3" in document
    assert "release-blocker evidence" in document
    assert "must not be described as Quillan compatibility" in document
    assert "Core v0.6.4 must not be published" in document
