"""Core #229 Slice 6: local wheel qualification preflight and evidence guards."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.qualify_issue229_reader_metadata_wheel import (
    RECORD_TYPE,
    Candidate,
    QualificationError,
    inspect_candidate_wheel,
    qualification_record,
)


@pytest.fixture
def candidate_wheel(tmp_path: Path) -> Path:
    path = tmp_path / "pds_core-0.6.4-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "pds_core-0.6.4.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: pds-core\nVersion: 0.6.4\n",
        )
        archive.writestr("pds_core/__init__.py", '__version__ = "0.6.4"\n')
        archive.writestr("pds_core/publication_compatibility.py", "# simulated\n")
    return path


def test_exact_local_candidate_preflight(candidate_wheel: Path) -> None:
    candidate = inspect_candidate_wheel(candidate_wheel)
    assert candidate.path == candidate_wheel.resolve()
    assert candidate.version == "0.6.4"
    assert len(candidate.sha256) == 64


def test_malformed_wheel_path_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(QualificationError, match="existing pds_core"):
        inspect_candidate_wheel(tmp_path / "missing.whl")
    wrong_name = tmp_path / "other-0.6.4-py3-none-any.whl"
    wrong_name.write_bytes(b"not a wheel")
    with pytest.raises(QualificationError, match="existing pds_core"):
        inspect_candidate_wheel(wrong_name)


def test_corrupt_zip_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "pds_core-0.6.4-py3-none-any.whl"
    path.write_bytes(b"not a zip")
    with pytest.raises(QualificationError, match="inspected safely"):
        inspect_candidate_wheel(path)


def test_package_version_disagreement_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "pds_core-0.6.4-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr("pds_core-0.6.4.dist-info/METADATA", "Name: pds-core\nVersion: 0.6.5\n")
        archive.writestr("pds_core/__init__.py", "")
        archive.writestr("pds_core/publication_compatibility.py", "")
    with pytest.raises(QualificationError, match="disagree"):
        inspect_candidate_wheel(path)


def test_missing_public_metadata_module_rejected(tmp_path: Path) -> None:
    path = tmp_path / "pds_core-0.6.4-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr("pds_core-0.6.4.dist-info/METADATA", "Name: pds-core\nVersion: 0.6.4\n")
        archive.writestr("pds_core/__init__.py", "")
    with pytest.raises(QualificationError, match="public reader-metadata module"):
        inspect_candidate_wheel(path)


def test_duplicate_wheel_members_rejected(tmp_path: Path) -> None:
    path = tmp_path / "pds_core-0.6.4-py3-none-any.whl"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(path, "w") as archive:
            archive.writestr("pds_core-0.6.4.dist-info/METADATA", "Name: pds-core\nVersion: 0.6.4\n")
            archive.writestr("pds_core/__init__.py", "")
            archive.writestr("pds_core/publication_compatibility.py", "")
            archive.writestr("pds_core/publication_compatibility.py", "")
    with pytest.raises(QualificationError, match="duplicate ZIP members"):
        inspect_candidate_wheel(path)


def test_qualification_record_is_deterministic_and_is_not_a_release_claim(tmp_path: Path) -> None:
    candidate = Candidate(tmp_path / "pds_core-0.6.5-py3-none-any.whl", "0.6.5", "0" * 64)
    probe: dict[str, object] = {
        "status": "pass",
        "core_distribution_version": "0.6.5",
        "import_source": "installed_wheel_outside_checkout",
        "producer_profiles": "synthetic_contract_fixtures_not_installed_producer_releases",
    }
    first = qualification_record(candidate, probe)
    assert first == qualification_record(candidate, probe)
    payload = json.loads(first)
    assert payload["record_type"] == RECORD_TYPE
    assert payload["qualification_stage"] == "pre_release_development_candidate"
    assert payload["candidate_wheel"]["sha256"] == "0" * 64
    assert payload["released_consumer_matrix"] == "not_executed_by_this_probe"
    assert "0.6.4" not in first.decode("utf-8")
    assert str(tmp_path) not in first.decode("utf-8")


def test_installed_probe_uses_isolated_interpreter_and_has_portia_coverage() -> None:
    probe = Path(__file__).resolve().parents[1] / "scripts/issue229_reader_contract_wheel_probe.py"
    runner = Path(__file__).resolve().parents[1] / "scripts/qualify_issue229_reader_metadata_wheel.py"
    assert probe.is_file() and runner.is_file()
    content = probe.read_text(encoding="utf-8")
    executable = runner.read_text(encoding="utf-8")
    assert "portia_intervention_reader_v1" in content
    assert "intervention_record_set" in content
    assert "academic_work_registration_revision=None" in content
    assert '"-I"' in executable
    assert '"--no-index"' in executable
    assert '"--no-deps"' in executable
    assert "TemporaryDirectory" in executable
    assert "forbidden_root" in content
    assert "not_executed_by_this_probe" in executable


def test_qualification_documentation_is_explicit_about_release_scope() -> None:
    doc = Path(__file__).resolve().parents[1] / "docs/validation/issue-229-installed-reader-contract-qualification.md"
    contents = doc.read_text(encoding="utf-8")
    for token in (
        "Core #229",
        "Meridian #111",
        "Vitrine #103",
        "Portia #66",
        "pre-release",
        "qualify_issue229_reader_metadata_wheel.py",
        "qualify_released_consumers.py",
        "0.6.4",
        "SHA-256",
        "no Academic Work Registration",
    ):
        assert token in contents
