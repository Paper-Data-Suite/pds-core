"""Installed-artifact acceptance for pds-core issue #226."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final


_LONG_SOURCE_FILENAME: Final[str] = (
    "issue216_physical_regression_scan_with_deliberately_long_"
    "source_filename_for_diagnostic_testing.pdf"
)
_REQUIRED_FIXTURE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "content_text",
        "intake_date",
        "intake_timestamp",
        "retained_filename",
        "retained_source_relative_path",
        "source_filename",
        "source_scan_id",
        "source_sha256",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_fixture(path: Path) -> dict[str, str]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"legacy fixture could not be read: {error}") from error
    if not isinstance(raw, dict):
        raise RuntimeError("legacy fixture must be a JSON object")
    if set(raw) != _REQUIRED_FIXTURE_KEYS:
        raise RuntimeError("legacy fixture keys do not match the issue #226 contract")
    result: dict[str, str] = {}
    for key in sorted(_REQUIRED_FIXTURE_KEYS):
        value = raw[key]
        if not isinstance(value, str):
            raise RuntimeError(f"legacy fixture field {key!r} must be text")
        result[key] = value
    return result


def _assert_installed_distribution(
    expected_version: str,
    source_checkout: Path,
) -> None:
    import pds_core

    installed_version = importlib.metadata.version("pds-core")
    _require(
        installed_version == expected_version,
        "installed pds-core distribution version mismatch: "
        f"{installed_version!r} != {expected_version!r}",
    )
    _require(
        pds_core.__version__ == expected_version,
        "installed pds_core.__version__ mismatch: "
        f"{pds_core.__version__!r} != {expected_version!r}",
    )
    package_file = pds_core.__file__
    if not isinstance(package_file, str):
        raise RuntimeError("pds_core.__file__ is unavailable")
    package_path = Path(package_file).resolve()
    checkout = source_checkout.resolve()
    try:
        package_path.relative_to(checkout)
    except ValueError:
        pass
    else:
        raise RuntimeError(
            "pds_core resolved from the source checkout instead of the installed artifact"
        )


def _deep_workspace(base: Path) -> Path:
    workspace = base / "workspace_for_physical_acceptance"
    while len(str(workspace)) < 119:
        workspace /= "deep_segment_1234567890"
    workspace.mkdir(parents=True)
    return workspace


def _assert_bounded_retention(base: Path) -> None:
    from pds_core.identifiers import is_valid_identifier
    from pds_core.scan_retention import SourceRetentionError, retain_source_scan
    from pds_core.scan_routes import (
        RETAINED_SOURCE_FILENAME_MAX_LENGTH,
        SOURCE_SCAN_ID_MAX_LENGTH,
    )

    base.mkdir(parents=True, exist_ok=True)
    external = base / "external"
    external.mkdir()
    source = external / _LONG_SOURCE_FILENAME
    contents = (
        b"%PDF-1.4\n"
        b"issue226 installed retained source acceptance\n"
        b"%%EOF\n"
    )
    source.write_bytes(contents)
    timestamp = datetime.fromisoformat("2026-09-30T03:18:38.064717+00:00")
    workspace = _deep_workspace(base / "deep-root")

    first = retain_source_scan(
        workspace,
        source,
        intake_timestamp=timestamp,
    )
    _require(first.source_filename == source.name, "source_filename was not preserved")
    _require(first.source_sha256 == _sha256(contents), "source SHA-256 changed")
    _require(first.retained_source_path.read_bytes() == contents, "retained bytes changed")
    _require(source.read_bytes() == contents, "external source bytes changed")
    _require(
        len(first.retained_source_path.name) <= RETAINED_SOURCE_FILENAME_MAX_LENGTH,
        "installed writer exceeded the retained filename bound",
    )
    _require(
        len(first.source_scan_id) <= SOURCE_SCAN_ID_MAX_LENGTH,
        "installed writer exceeded the source_scan_id bound",
    )
    _require(is_valid_identifier(first.source_scan_id), "source_scan_id is invalid")
    _require(
        source.stem not in first.retained_source_path.name,
        "long source stem leaked unbounded into the retained filename",
    )
    try:
        first.retained_source_path.resolve().relative_to(workspace.resolve())
    except ValueError as error:
        raise RuntimeError("retained path escaped the workspace") from error

    second = retain_source_scan(
        workspace,
        source,
        intake_timestamp=timestamp + timedelta(microseconds=1),
    )
    _require(first.source_sha256 == second.source_sha256, "same bytes changed hash")
    _require(first.source_scan_id != second.source_scan_id, "intake identities collapsed")
    _require(
        first.retained_source_path != second.retained_source_path,
        "separate intake events reused one retained path",
    )

    before = first.retained_source_path.read_bytes()
    try:
        retain_source_scan(workspace, source, intake_timestamp=timestamp)
    except SourceRetentionError as error:
        _require("already exists" in str(error), "collision failed for the wrong reason")
    else:
        raise RuntimeError("exact retained destination collision did not fail")
    _require(
        first.retained_source_path.read_bytes() == before,
        "collision overwrote the existing retained source",
    )


def _assert_legacy_fixture(base: Path, fixture_path: Path) -> None:
    from pds_core.module_dispatch import RouteDispatchFailure, RouteDispatchRequest
    from pds_core.route_registrations import RouteRegistrationNotFoundError
    from pds_core.routing_models import ModuleWorkRef, RouteLocator
    from pds_core.scan_failure_metadata import (
        load_routing_failure_metadata,
        routing_failure_metadata_from_dispatch_failure,
        write_routing_failure_metadata,
    )
    from pds_core.scan_resolution_metadata import (
        create_scan_resolution_metadata,
        load_scan_resolution_metadata,
        write_scan_resolution_metadata,
    )
    from pds_core.scan_retention import RetainedSourceScan
    from pds_core.scan_routes import (
        RETAINED_SOURCE_FILENAME_MAX_LENGTH,
        SOURCE_SCAN_ID_MAX_LENGTH,
        build_retained_source_filename,
        retained_source_scan_path,
    )

    fixture = _load_fixture(fixture_path)
    contents = fixture["content_text"].encode("utf-8")
    _require(_sha256(contents) == fixture["source_sha256"], "fixture SHA-256 mismatch")
    _require(
        len(fixture["retained_filename"]) > RETAINED_SOURCE_FILENAME_MAX_LENGTH,
        "legacy fixture no longer exceeds the new writer filename bound",
    )
    _require(
        len(fixture["source_scan_id"]) > SOURCE_SCAN_ID_MAX_LENGTH,
        "legacy fixture no longer exceeds the new writer ID bound",
    )

    workspace = base / "legacy-workspace"
    workspace.mkdir(parents=True)
    retained_path = retained_source_scan_path(
        workspace,
        intake_date=fixture["intake_date"],
        retained_filename=fixture["retained_filename"],
    )
    retained_path.parent.mkdir(parents=True)
    retained_path.write_bytes(contents)
    retained = RetainedSourceScan(
        source_scan_id=fixture["source_scan_id"],
        source_filename=fixture["source_filename"],
        source_sha256=fixture["source_sha256"],
        retained_source_path=retained_path,
        retained_source_relative_path=fixture["retained_source_relative_path"],
        intake_timestamp=datetime.fromisoformat(fixture["intake_timestamp"]),
        intake_date=date.fromisoformat(fixture["intake_date"]),
    )

    bounded_name = build_retained_source_filename(
        intake_timestamp=retained.intake_timestamp,
        original_filename=retained.source_filename,
        sha256_hex=retained.source_sha256,
    )
    _require(
        bounded_name != fixture["retained_filename"],
        "legacy fixture unexpectedly matches the new bounded writer form",
    )
    _require(retained_path.read_bytes() == contents, "legacy retained bytes changed")
    _require(
        not (retained_path.parent / bounded_name).exists(),
        "legacy acceptance migrated or renamed the retained source",
    )

    locator = RouteLocator(
        schema="PDS2",
        work=ModuleWorkRef(
            module_id="scoreform",
            class_id="english12_p2",
            work_id="issue226_legacy",
        ),
        route_id="route_issue226_legacy",
    )
    request = RouteDispatchRequest(locator, retained, 1)
    dispatch_failure = RouteDispatchFailure(
        request,
        RouteRegistrationNotFoundError("legacy fixture route unavailable"),
    )
    failure = routing_failure_metadata_from_dispatch_failure(
        dispatch_failure,
        failure_id="failure_issue226_installed_legacy",
        created_at="2026-09-30T03:19:00Z",
    )
    write_routing_failure_metadata(workspace, failure)
    loaded_failure = load_routing_failure_metadata(
        workspace,
        "failure_issue226_installed_legacy",
    )
    resolution = create_scan_resolution_metadata(
        loaded_failure,
        resolution_id="resolution_issue226_installed_legacy",
        resolution_status="resolved",
        resolution_action="cannot_route",
        resolved_at="2026-09-30T03:20:00Z",
        resolution_message="Legacy retained-source provenance remains readable.",
    )
    write_scan_resolution_metadata(workspace, resolution)
    loaded_resolution = load_scan_resolution_metadata(
        workspace,
        "resolution_issue226_installed_legacy",
    )

    for record in (loaded_failure, loaded_resolution):
        _require(
            record.source_filename == fixture["source_filename"],
            "legacy source_filename changed through Scan Review metadata",
        )
        _require(
            record.source_scan_id == fixture["source_scan_id"],
            "legacy source_scan_id changed through Scan Review metadata",
        )
        _require(
            record.source_sha256 == fixture["source_sha256"],
            "legacy source_sha256 changed through Scan Review metadata",
        )
        _require(
            record.retained_source_path == fixture["retained_source_relative_path"],
            "legacy retained path changed through Scan Review metadata",
        )
    _require(retained_path.read_bytes() == contents, "legacy source was rewritten")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--legacy-fixture", type=Path, required=True)
    args = parser.parse_args()

    _assert_installed_distribution(args.expected_version, args.source_checkout)
    original_cwd = Path.cwd()
    before = set(original_cwd.iterdir())
    with tempfile.TemporaryDirectory(prefix="pds-core-issue226-installed-") as temporary:
        root = Path(temporary)
        _assert_bounded_retention(root / "bounded")
        _assert_legacy_fixture(root / "legacy", args.legacy_fixture)
    after = set(original_cwd.iterdir())
    _require(before == after, "issue #226 installed acceptance created cwd residue")

    print("pds-core Issue #226 installed acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
