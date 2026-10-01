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
    assert quillan.version == "0.10.4"
    assert quillan.core_requirement == "pds-core>=0.6.2,<0.7"
    assert quillan.release.sha256 == (
        "038ebf1874fc347707a61b1ae78d04a49579e1869ec99fb833c8fa407e248fe1"
    )
    assert quillan.providers.module_operations == (
        "quillan.pds_operations:get_module_operations_profile"
    )


def test_issue226_characterization_evidence_is_deterministic_and_compatible() -> None:
    probe: dict[str, object] = {
        "candidate_core_version": "0.6.4",
        "fresh_bounded_provenance": "pass",
        "legacy_failure": None,
        "legacy_v063_long_name_provenance": "pass",
        "quillan_version": "0.10.4",
        "release_blocker": False,
    }
    first = characterization_evidence(
        candidate_filename="pds_core-0.6.4-py3-none-any.whl",
        candidate_version="0.6.4",
        candidate_sha256="a" * 64,
        quillan_wheel="quillan-0.10.4-py3-none-any.whl",
        quillan_version="0.10.4",
        quillan_sha256="b" * 64,
        probe=probe,
    )
    second = characterization_evidence(
        candidate_filename="pds_core-0.6.4-py3-none-any.whl",
        candidate_version="0.6.4",
        candidate_sha256="a" * 64,
        quillan_wheel="quillan-0.10.4-py3-none-any.whl",
        quillan_version="0.10.4",
        quillan_sha256="b" * 64,
        probe=probe,
    )
    assert first == second
    parsed = cast(dict[str, object], json.loads(first))
    assert parsed["characterization_status"] == "compatible"
    assert str(ROOT) not in first.decode("utf-8")


def test_issue226_compatibility_documentation_records_resolved_blocker() -> None:
    document = (ROOT / "docs" / "released_consumer_compatibility.md").read_text(
        encoding="utf-8"
    )
    assert "Quillan 0.10.4" in document
    assert "Quillan 0.10.3" in document
    assert "historical release-blocker evidence" in document
    assert "current passing gate" in document
    assert "Core v0.6.4 must not be published" not in document
