from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from scripts.qualify_released_consumers import (
    QualificationError,
    ReleaseAssetMetadata,
    _normalize_error,
    download_authenticated_consumer_artifact,
    parse_release_asset_metadata,
    qualification_evidence,
)
from scripts.released_consumer_compatibility import (
    CandidateWheelError,
    ConsumerFixture,
    inspect_consumer_wheel,
    load_compatibility_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "released_consumers" / "v1" / "manifest.json"


def _consumer(component_id: str) -> ConsumerFixture:
    return load_compatibility_fixture(FIXTURE).by_component_id()[component_id]


def _release_payload(
    consumer: ConsumerFixture,
    *,
    digest: str | None = None,
    url: str | None = None,
) -> dict[str, object]:
    effective_digest = digest or consumer.release.sha256 or ("a" * 64)
    return {
        "tag_name": consumer.release.tag,
        "draft": False,
        "assets": [
            {
                "name": consumer.release.wheel,
                "browser_download_url": url or consumer.release.download_url,
                "digest": f"sha256:{effective_digest}",
            }
        ],
    }


def _write_consumer_wheel(
    tmp_path: Path,
    consumer: ConsumerFixture,
    *,
    core_requirement: str | None = None,
    operations_target: str | None = None,
) -> Path:
    wheel = tmp_path / consumer.release.wheel
    normalized = consumer.distribution.replace("-", "_")
    dist_info = f"{normalized}-{consumer.version}.dist-info"
    metadata = "\n".join(
        (
            "Metadata-Version: 2.4",
            f"Name: {consumer.distribution}",
            f"Version: {consumer.version}",
            f"Requires-Python: {consumer.requires_python}",
            f"Requires-Dist: {core_requirement or consumer.core_requirement}",
            "",
        )
    )
    lines = [
        "[console_scripts]",
        f"{consumer.console_script} = {consumer.import_name}.cli:main",
    ]
    if consumer.providers.routing is not None:
        lines.extend(
            (
                "",
                "[paper_data_suite.modules]",
                f"{consumer.component_id} = {consumer.providers.routing}",
            )
        )
    if consumer.providers.publication is not None:
        lines.extend(
            (
                "",
                "[paper_data_suite.publication_producers]",
                f"{consumer.component_id} = {consumer.providers.publication}",
            )
        )
    if operations_target is not None:
        lines.extend(
            (
                "",
                "[paper_data_suite.module_operations]",
                f"{consumer.component_id} = {operations_target}",
            )
        )
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"{dist_info}/METADATA", metadata.encode("utf-8"))
        archive.writestr(
            f"{dist_info}/entry_points.txt",
            ("\n".join(lines) + "\n").encode("utf-8"),
        )
    return wheel


def test_release_metadata_accepts_exact_pinned_asset() -> None:
    consumer = _consumer("scoreform")
    metadata = parse_release_asset_metadata(_release_payload(consumer), consumer)
    assert metadata.name == consumer.release.wheel
    assert metadata.browser_download_url == consumer.release.download_url
    assert metadata.sha256 == consumer.release.sha256


def test_release_metadata_accepts_pinned_meridian_digest() -> None:
    consumer = _consumer("meridian")
    assert consumer.release.sha256 is not None
    metadata = parse_release_asset_metadata(_release_payload(consumer), consumer)
    assert metadata.sha256 == consumer.release.sha256


def test_release_metadata_rejects_pinned_digest_disagreement() -> None:
    consumer = _consumer("scoreform")
    with pytest.raises(QualificationError, match="disagrees"):
        parse_release_asset_metadata(
            _release_payload(consumer, digest="0" * 64),
            consumer,
        )


def test_release_metadata_rejects_wrong_asset_url() -> None:
    consumer = _consumer("quillan")
    with pytest.raises(QualificationError, match="URL"):
        parse_release_asset_metadata(
            _release_payload(consumer, url="https://example.invalid/wheel.whl"),
            consumer,
        )


def test_consumer_wheel_inspection_accepts_exact_declared_surface(tmp_path: Path) -> None:
    consumer = _consumer("concord")
    wheel = _write_consumer_wheel(tmp_path, consumer)
    identity = inspect_consumer_wheel(wheel, consumer)
    assert identity.distribution == "pds-concord"
    assert identity.version == "0.2.0"
    assert identity.routing_target == consumer.providers.routing
    assert identity.publication_target == consumer.providers.publication
    assert identity.module_operations_target is None


def test_consumer_wheel_inspection_accepts_absent_optional_providers(tmp_path: Path) -> None:
    consumer = _consumer("vitrine")
    wheel = _write_consumer_wheel(tmp_path, consumer)
    identity = inspect_consumer_wheel(wheel, consumer)
    assert identity.routing_target is None
    assert identity.publication_target is None
    assert identity.module_operations_target is None


def test_consumer_wheel_rejects_unexpected_module_operations_provider(
    tmp_path: Path,
) -> None:
    consumer = _consumer("scoreform")
    wheel = _write_consumer_wheel(
        tmp_path,
        consumer,
        operations_target="scoreform.operations:get_profile",
    )
    with pytest.raises(CandidateWheelError, match="unexpectedly declares"):
        inspect_consumer_wheel(wheel, consumer)


def test_consumer_wheel_rejects_core_requirement_mismatch(tmp_path: Path) -> None:
    consumer = _consumer("quillan")
    wheel = _write_consumer_wheel(
        tmp_path,
        consumer,
        core_requirement="pds-core>=0.6.1,<0.7",
    )
    with pytest.raises(CandidateWheelError, match="does not match"):
        inspect_consumer_wheel(wheel, consumer)


def test_download_authentication_uses_exact_github_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import qualify_released_consumers as qualification

    pinned = _consumer("meridian")
    data = b"synthetic released wheel bytes"
    digest = hashlib.sha256(data).hexdigest()
    consumer = replace(
        pinned,
        release=replace(pinned.release, sha256=digest),
    )
    monkeypatch.setattr(
        qualification,
        "fetch_release_asset_metadata",
        lambda _consumer: ReleaseAssetMetadata(
            name=consumer.release.wheel,
            browser_download_url=consumer.release.download_url,
            sha256=digest,
        ),
    )
    monkeypatch.setattr(qualification, "_urlopen_bytes", lambda _request: data)
    artifact = download_authenticated_consumer_artifact(consumer, tmp_path)
    assert artifact.sha256 == digest
    assert artifact.github_sha256 == digest
    assert artifact.path.read_bytes() == data


def test_download_authentication_removes_tampered_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import qualify_released_consumers as qualification

    consumer = _consumer("meridian")
    expected = hashlib.sha256(b"expected").hexdigest()
    monkeypatch.setattr(
        qualification,
        "fetch_release_asset_metadata",
        lambda _consumer: ReleaseAssetMetadata(
            name=consumer.release.wheel,
            browser_download_url=consumer.release.download_url,
            sha256=expected,
        ),
    )
    monkeypatch.setattr(
        qualification,
        "_urlopen_bytes",
        lambda _request: b"tampered",
    )
    with pytest.raises(QualificationError, match="failed GitHub SHA-256"):
        download_authenticated_consumer_artifact(consumer, tmp_path)
    assert not (tmp_path / consumer.release.wheel).exists()


def test_qualification_evidence_is_deterministic_and_preserves_individual_failure() -> None:
    results: list[dict[str, object]] = [
        {
            "component_id": "concord",
            "status": "pass",
            "failure": None,
        },
        {
            "component_id": "meridian",
            "status": "fail",
            "failure": {"stage": "pip_check", "message": "synthetic failure"},
        },
    ]
    first = qualification_evidence(
        candidate_filename="pds_core-0.6.3-py3-none-any.whl",
        candidate_version="0.6.3",
        candidate_sha256="a" * 64,
        consumers=results,
    )
    second = qualification_evidence(
        candidate_filename="pds_core-0.6.3-py3-none-any.whl",
        candidate_version="0.6.3",
        candidate_sha256="a" * 64,
        consumers=results,
    )
    assert first == second
    payload = cast(dict[str, object], json.loads(first))
    assert payload["overall_status"] == "fail"
    consumers = cast(list[dict[str, object]], payload["consumers"])
    assert consumers[0]["status"] == "pass"
    assert consumers[1]["status"] == "fail"


def test_normalized_failure_redacts_environment_paths(tmp_path: Path) -> None:
    home = tmp_path / "teacher-home"
    checkout = home / "pds-core"
    message = _normalize_error(
        RuntimeError(f"failure under {checkout} and {home}"),
        replacements=(
            (str(checkout), "<core-checkout>"),
            (str(home), "<home>"),
        ),
    )
    assert str(tmp_path) not in message
    assert "<core-checkout>" in message
