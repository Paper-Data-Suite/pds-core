from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path
from typing import cast

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

from scripts.released_consumer_compatibility import (
    CandidateWheelError,
    CompatibilityFixtureError,
    EXPECTED_CORE_VERSION,
    REQUIRED_CONSUMERS,
    REQUIRED_QUALIFICATION_PROBES,
    SOURCE_CORE_VERSION,
    build_provisional_candidate,
    inspect_candidate_wheel,
    load_compatibility_fixture,
    provisional_result_json,
    runtime_tree_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "released_consumers" / "v1" / "manifest.json"


def _fixture_payload(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    raw = cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path, raw


def _consumers(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["consumers"])


def _write_candidate_wheel(
    tmp_path: Path,
    *,
    version: str = EXPECTED_CORE_VERSION,
    distribution: str = "pds-core",
    include_core_script: bool = True,
    runtime_requirement: str | None = None,
) -> Path:
    wheel = tmp_path / f"pds_core-{version}-py3-none-any.whl"
    dist_info = f"pds_core-{version}.dist-info"
    scripts = ["[console_scripts]", "core = pds_core.core_menu:main"]
    if include_core_script:
        scripts.append("pds-core = pds_core.cli:main")
    metadata_lines = [
        "Metadata-Version: 2.4",
        f"Name: {distribution}",
        f"Version: {version}",
        "Requires-Python: >=3.11",
    ]
    if runtime_requirement is not None:
        metadata_lines.append(f"Requires-Dist: {runtime_requirement}")
    metadata = "\n".join((*metadata_lines, "")).encode("utf-8")
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"{dist_info}/METADATA", metadata)
        archive.writestr(
            f"{dist_info}/entry_points.txt", "\n".join(scripts).encode("utf-8")
        )
        archive.writestr(
            "pds_core/__init__.py",
            f'__version__ = "{version}"\n'.encode("utf-8"),
        )
        for required in (
            "pds_core/roster_imports.py",
            "pds_core/provider_diagnostics.py",
            "pds_core/module_operations.py",
            "pds_core/cli_support/roster_imports.py",
        ):
            archive.writestr(required, b"# synthetic candidate\n")
        archive.writestr(
            "pds_core/starter_data/standards/synthetic.json", b"{}\n"
        )
    return wheel


def test_fixture_contains_exact_released_consumer_matrix() -> None:
    fixture = load_compatibility_fixture(FIXTURE)
    assert fixture.candidate_core_version == "0.6.2"
    assert frozenset(fixture.by_component_id()) == REQUIRED_CONSUMERS
    assert tuple(item.component_id for item in fixture.consumers) == (
        "concord",
        "meridian",
        "quillan",
        "scoreform",
        "vitrine",
    )


def test_fixture_core_requirements_accept_candidate_by_packaging_semantics() -> None:
    fixture = load_compatibility_fixture(FIXTURE)
    candidate = Version(fixture.candidate_core_version)
    for consumer in fixture.consumers:
        requirement = Requirement(consumer.core_requirement)
        assert requirement.name == "pds-core"
        assert candidate in requirement.specifier


def test_fixture_records_explicit_probes_and_intentional_exclusions() -> None:
    fixture = load_compatibility_fixture(FIXTURE).by_component_id()
    for consumer in fixture.values():
        assert consumer.qualification_probes == REQUIRED_QUALIFICATION_PROBES
        assert consumer.intentional_exclusions
        assert any("module_operations" in item for item in consumer.intentional_exclusions)
    for component_id in ("meridian", "vitrine"):
        exclusions = fixture[component_id].intentional_exclusions
        assert any("routing provider" in item for item in exclusions)
        assert any("publication_producers" in item for item in exclusions)


def test_fixture_pins_authenticated_meridian_release_digest() -> None:
    meridian = load_compatibility_fixture(FIXTURE).by_component_id()["meridian"]
    assert meridian.release.sha256 == (
        "7114cc153f7a884041374f0ad88be8ce871b0f79dbfa7ff4869a03b24257f00a"
    )
    assert meridian.release.sha256_source == "github-release-asset-digest"


def test_fixture_records_consumer_specific_provider_expectations() -> None:
    fixture = load_compatibility_fixture(FIXTURE).by_component_id()
    for component_id in ("scoreform", "quillan", "concord"):
        assert fixture[component_id].providers.routing is not None
        assert fixture[component_id].providers.publication is not None
        assert fixture[component_id].providers.module_operations is None
    for component_id in ("meridian", "vitrine"):
        assert fixture[component_id].providers.routing is None
        assert fixture[component_id].providers.publication is None
        assert fixture[component_id].providers.module_operations is None


def test_fixture_rejects_incomplete_probe_sequence(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    consumer = _consumers(payload)[0]
    consumer["qualification_probes"] = ["release_asset_authentication"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="complete deterministic"):
        load_compatibility_fixture(path)


def test_fixture_rejects_duplicate_intentional_exclusion(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    consumer = _consumers(payload)[0]
    exclusions = cast(list[str], consumer["intentional_exclusions"])
    exclusions.append(exclusions[0])
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="must not contain duplicates"):
        load_compatibility_fixture(path)


def test_fixture_rejects_duplicate_consumer(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    consumers = _consumers(payload)
    consumers.append(dict(consumers[0]))
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="duplicate component_id"):
        load_compatibility_fixture(path)


def test_fixture_rejects_missing_required_consumer(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    payload["consumers"] = _consumers(payload)[:-1]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="exactly ScoreForm"):
        load_compatibility_fixture(path)


def test_fixture_rejects_bad_pinned_digest(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    release = cast(dict[str, object], _consumers(payload)[0]["release"])
    release["sha256"] = "ABC"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="lowercase SHA-256"):
        load_compatibility_fixture(path)


def test_fixture_requires_digest_authority_when_hash_is_unpinned(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    meridian = next(
        item for item in _consumers(payload) if item["component_id"] == "meridian"
    )
    release = cast(dict[str, object], meridian["release"])
    release["sha256"] = None
    release["sha256_source"] = "unknown"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="GitHub asset digest"):
        load_compatibility_fixture(path)




def test_fixture_rejects_release_url_that_does_not_match_repository(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    release = cast(dict[str, object], _consumers(payload)[0]["release"])
    release["download_url"] = str(release["download_url"]).replace(
        "Paper-Data-Suite/pds-concord", "Paper-Data-Suite/pds-quillan"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="exact pinned release asset"):
        load_compatibility_fixture(path)


def test_fixture_rejects_wheel_distribution_mismatch(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    consumer = _consumers(payload)[0]
    release = cast(dict[str, object], consumer["release"])
    release["wheel"] = "other-0.2.0-py3-none-any.whl"
    release["download_url"] = (
        "https://github.com/Paper-Data-Suite/pds-concord/releases/download/"
        "v0.2.0/other-0.2.0-py3-none-any.whl"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="wheel distribution"):
        load_compatibility_fixture(path)


def test_fixture_rejects_core_requirement_that_excludes_candidate(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    _consumers(payload)[0]["core_requirement"] = "pds-core>=0.6,<0.6.2"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="does not accept Core 0.6.2"):
        load_compatibility_fixture(path)


def test_fixture_rejects_marker_or_extra_in_core_requirement(tmp_path: Path) -> None:
    path, payload = _fixture_payload(tmp_path)
    _consumers(payload)[0]["core_requirement"] = "pds-core[dev]>=0.6,<0.7"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CompatibilityFixtureError, match="direct unmarked"):
        load_compatibility_fixture(path)


def test_candidate_wheel_inspection_accepts_expected_identity(tmp_path: Path) -> None:
    wheel = _write_candidate_wheel(tmp_path)
    identity = inspect_candidate_wheel(wheel)
    assert identity.filename == "pds_core-0.6.2-py3-none-any.whl"
    assert identity.distribution == "pds-core"
    assert identity.version == "0.6.2"
    assert identity.requires_python == ">=3.11"
    assert len(identity.sha256) == 64
    assert dict(identity.console_scripts) == {
        "core": "pds_core.core_menu:main",
        "pds-core": "pds_core.cli:main",
    }
    assert identity.runtime_requirements == ()


def test_candidate_wheel_rejects_wrong_distribution(tmp_path: Path) -> None:
    wheel = _write_candidate_wheel(tmp_path, distribution="other")
    with pytest.raises(CandidateWheelError, match="distribution must be pds-core"):
        inspect_candidate_wheel(wheel)


def test_candidate_wheel_rejects_wrong_version(tmp_path: Path) -> None:
    wheel = _write_candidate_wheel(tmp_path, version="0.6.3")
    with pytest.raises(CandidateWheelError, match="filename must be"):
        inspect_candidate_wheel(wheel)


def test_candidate_wheel_rejects_missing_console_script(tmp_path: Path) -> None:
    wheel = _write_candidate_wheel(tmp_path, include_core_script=False)
    with pytest.raises(CandidateWheelError, match="missing expected console script pds-core"):
        inspect_candidate_wheel(wheel)




def test_candidate_wheel_rejects_new_runtime_dependency(tmp_path: Path) -> None:
    wheel = _write_candidate_wheel(tmp_path, runtime_requirement="requests>=2")
    with pytest.raises(CandidateWheelError, match="runtime dependencies"):
        inspect_candidate_wheel(wheel)


def test_runtime_tree_digest_is_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "pds_core").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("project\n", encoding="utf-8")
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    (repo / "LICENSE").write_text("license\n", encoding="utf-8")
    (repo / "pds_core" / "__init__.py").write_text("package\n", encoding="utf-8")
    first = runtime_tree_sha256(repo)
    second = runtime_tree_sha256(repo)
    assert first == second
    assert len(first) == 64


def test_provisional_result_json_is_deterministic_and_bounded(tmp_path: Path) -> None:
    from scripts.released_consumer_compatibility import ProvisionalCandidateResult

    result = ProvisionalCandidateResult(
        wheel=tmp_path / "pds_core-0.6.2-py3-none-any.whl",
        wheel_sha256="a" * 64,
        source_commit="b" * 40,
        source_runtime_tree_sha256="c" * 64,
        source_version=SOURCE_CORE_VERSION,
        effective_version=EXPECTED_CORE_VERSION,
    )
    first = provisional_result_json(result)
    second = provisional_result_json(result)
    assert first == second
    payload = cast(dict[str, object], json.loads(first))
    assert payload["artifact_status"] == "provisional-non-release"
    assert payload["wheel"] == "pds_core-0.6.2-py3-none-any.whl"
    assert str(tmp_path) not in first.decode("utf-8")


def test_provisional_builder_changes_only_temporary_version_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "pds_core").mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "pds-core"\nversion = "0.6.1"\n', encoding="utf-8"
    )
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    (repo / "LICENSE").write_text("license\n", encoding="utf-8")
    (repo / "pds_core" / "__init__.py").write_text(
        '__version__ = "0.6.1"\n', encoding="utf-8"
    )
    before_project = (repo / "pyproject.toml").read_bytes()
    before_init = (repo / "pds_core" / "__init__.py").read_bytes()

    def fake_git(_repo_root: Path, *args: str) -> str:
        assert args == ("rev-parse", "HEAD")
        return "d" * 40

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        text: bool,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, text, stdout, stderr, check
        build_root = Path(command[-1])
        assert 'version = "0.6.2"' in (build_root / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        assert '__version__ = "0.6.2"' in (
            build_root / "pds_core" / "__init__.py"
        ).read_text(encoding="utf-8")
        outdir = Path(command[command.index("--outdir") + 1])
        _write_candidate_wheel(outdir)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr("scripts.released_consumer_compatibility._git", fake_git)
    monkeypatch.setattr(
        "scripts.released_consumer_compatibility.subprocess.run", fake_run
    )
    result = build_provisional_candidate(repo, tmp_path / "dist")
    assert result.source_commit == "d" * 40
    assert result.source_version == "0.6.1"
    assert result.effective_version == "0.6.2"
    assert result.wheel.name == "pds_core-0.6.2-py3-none-any.whl"
    assert (repo / "pyproject.toml").read_bytes() == before_project
    assert (repo / "pds_core" / "__init__.py").read_bytes() == before_init

def test_compatibility_documentation_records_release_handoff() -> None:
    documentation = (ROOT / "docs" / "released_consumer_compatibility.md").read_text(
        encoding="utf-8"
    )
    assert "provisional-non-release" in documentation
    assert "#196" in documentation
    assert "pds-paper-data-suite#38" in documentation
    assert "ScoreForm" in documentation
    assert "Meridian" in documentation
    assert "Portia" in documentation

