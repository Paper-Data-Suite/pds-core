"""Issue #226 legacy retained-source compatibility and path-budget tests."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import TypedDict, cast

import pytest

from pds_core.identifiers import is_valid_identifier
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
from pds_core.scan_retention import (
    RetainedSourceScan,
    SourceRetentionError,
    retain_source_scan,
)
from pds_core.scan_routes import (
    RETAINED_SOURCE_FILENAME_MAX_LENGTH,
    SOURCE_SCAN_ID_MAX_LENGTH,
    build_retained_source_filename,
    retained_source_scan_path,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "issue226"
    / "legacy_retained_source_v063.json"
)


class LegacyRetainedSourceFixture(TypedDict):
    source_filename: str
    source_sha256: str
    source_scan_id: str
    intake_timestamp: str
    intake_date: str
    retained_filename: str
    retained_source_relative_path: str
    content_text: str


def _fixture() -> LegacyRetainedSourceFixture:
    return cast(
        LegacyRetainedSourceFixture,
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    )


def _fixture_bytes(fixture: LegacyRetainedSourceFixture) -> bytes:
    return fixture["content_text"].encode("utf-8")


def _materialize_legacy_retained_source(
    workspace: Path,
) -> tuple[LegacyRetainedSourceFixture, RetainedSourceScan]:
    fixture = _fixture()
    retained_path = retained_source_scan_path(
        workspace,
        intake_date=fixture["intake_date"],
        retained_filename=fixture["retained_filename"],
    )
    retained_path.parent.mkdir(parents=True, exist_ok=True)
    retained_path.write_bytes(_fixture_bytes(fixture))
    return fixture, RetainedSourceScan(
        source_scan_id=fixture["source_scan_id"],
        source_filename=fixture["source_filename"],
        source_sha256=fixture["source_sha256"],
        retained_source_path=retained_path,
        retained_source_relative_path=fixture["retained_source_relative_path"],
        intake_timestamp=datetime.fromisoformat(fixture["intake_timestamp"]),
        intake_date=date.fromisoformat(fixture["intake_date"]),
    )


def _locator() -> RouteLocator:
    return RouteLocator(
        schema="PDS2",
        work=ModuleWorkRef(
            module_id="scoreform",
            class_id="english12_p2",
            work_id="issue226_legacy",
        ),
        route_id="route_issue226_legacy",
    )


def test_v063_fixture_is_internally_consistent_and_exceeds_new_writer_bounds() -> None:
    fixture = _fixture()
    contents = _fixture_bytes(fixture)

    assert hashlib.sha256(contents).hexdigest() == fixture["source_sha256"]
    assert fixture["retained_filename"] == Path(
        fixture["retained_source_relative_path"]
    ).name
    assert fixture["source_scan_id"] == (
        f"scan_{Path(fixture['retained_filename']).stem}"
    )
    assert len(fixture["retained_filename"]) > RETAINED_SOURCE_FILENAME_MAX_LENGTH
    assert len(fixture["source_scan_id"]) > SOURCE_SCAN_ID_MAX_LENGTH
    assert is_valid_identifier(fixture["source_scan_id"])


def test_v063_legacy_path_resolves_without_migration_or_rename(tmp_path: Path) -> None:
    fixture, retained = _materialize_legacy_retained_source(tmp_path)
    original_bytes = retained.retained_source_path.read_bytes()

    bounded_name = build_retained_source_filename(
        intake_timestamp=retained.intake_timestamp,
        original_filename=retained.source_filename,
        sha256_hex=retained.source_sha256,
    )
    bounded_path = retained_source_scan_path(
        tmp_path,
        intake_date=retained.intake_date,
        retained_filename=bounded_name,
    )

    assert retained.retained_source_path.name == fixture["retained_filename"]
    assert retained.retained_source_relative_path == (
        fixture["retained_source_relative_path"]
    )
    assert bounded_name != fixture["retained_filename"]
    assert retained.retained_source_path.exists()
    assert retained.retained_source_path.read_bytes() == original_bytes
    assert not bounded_path.exists()


def test_v063_legacy_provenance_round_trips_through_review_metadata(
    tmp_path: Path,
) -> None:
    fixture, retained = _materialize_legacy_retained_source(tmp_path)
    request = RouteDispatchRequest(_locator(), retained, 1)
    dispatch_failure = RouteDispatchFailure(
        request,
        RouteRegistrationNotFoundError("legacy fixture route unavailable"),
    )
    failure = routing_failure_metadata_from_dispatch_failure(
        dispatch_failure,
        failure_id="failure_issue226_legacy",
        created_at="2026-09-30T03:19:00Z",
    )

    write_routing_failure_metadata(tmp_path, failure)
    loaded_failure = load_routing_failure_metadata(
        tmp_path, "failure_issue226_legacy"
    )
    resolution = create_scan_resolution_metadata(
        loaded_failure,
        resolution_id="resolution_issue226_legacy",
        resolution_status="resolved",
        resolution_action="cannot_route",
        resolved_at="2026-09-30T03:20:00Z",
        resolution_message="Legacy retained-source provenance remains readable.",
    )
    write_scan_resolution_metadata(tmp_path, resolution)
    loaded_resolution = load_scan_resolution_metadata(
        tmp_path, "resolution_issue226_legacy"
    )

    for record in (loaded_failure, loaded_resolution):
        assert record.source_filename == fixture["source_filename"]
        assert record.source_scan_id == fixture["source_scan_id"]
        assert record.source_sha256 == fixture["source_sha256"]
        assert record.retained_source_path == (
            fixture["retained_source_relative_path"]
        )
    assert retained.retained_source_path.read_bytes() == _fixture_bytes(fixture)


def test_deep_windows_path_budget_matches_physical_regression_shape() -> None:
    fixture = _fixture()
    timestamp = datetime.fromisoformat(fixture["intake_timestamp"])
    windows_workspace = PureWindowsPath(
        r"C:\Users\teacher\OneDrive - Hillside Public Schools\2026-2027"
        r"\Paper-Data-Suite\workspace_for_physical_acceptance\active"
    )
    legacy_path = (
        windows_workspace
        / "scans"
        / "source"
        / fixture["intake_date"]
        / fixture["retained_filename"]
    )
    bounded_filename = build_retained_source_filename(
        intake_timestamp=timestamp,
        original_filename=fixture["source_filename"],
        sha256_hex=fixture["source_sha256"],
    )
    bounded_path = (
        windows_workspace
        / "scans"
        / "source"
        / fixture["intake_date"]
        / bounded_filename
    )

    assert len(str(windows_workspace)) == 119
    assert len(str(legacy_path)) == 281
    assert len(str(bounded_path)) < 260
    assert len(bounded_filename) <= RETAINED_SOURCE_FILENAME_MAX_LENGTH
    assert fixture["source_filename"][:-4] not in bounded_filename


def test_same_bytes_are_distinct_when_intake_timestamp_differs(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    source = tmp_path / fixture["source_filename"]
    source.write_bytes(_fixture_bytes(fixture))
    first_timestamp = datetime.fromisoformat(fixture["intake_timestamp"])

    first = retain_source_scan(
        tmp_path,
        source,
        intake_timestamp=first_timestamp,
    )
    second = retain_source_scan(
        tmp_path,
        source,
        intake_timestamp=first_timestamp + timedelta(microseconds=1),
    )

    assert first.source_sha256 == second.source_sha256 == fixture["source_sha256"]
    assert first.source_filename == second.source_filename == fixture["source_filename"]
    assert first.source_scan_id != second.source_scan_id
    assert first.retained_source_path != second.retained_source_path
    assert first.retained_source_path.read_bytes() == second.retained_source_path.read_bytes()


def test_compacted_writer_remains_create_only_on_exact_destination_collision(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    source = tmp_path / fixture["source_filename"]
    source.write_bytes(_fixture_bytes(fixture))
    timestamp = datetime.fromisoformat(fixture["intake_timestamp"])
    first = retain_source_scan(tmp_path, source, intake_timestamp=timestamp)
    retained_bytes = first.retained_source_path.read_bytes()

    with pytest.raises(SourceRetentionError, match="already exists"):
        retain_source_scan(tmp_path, source, intake_timestamp=timestamp)

    assert first.retained_source_path.read_bytes() == retained_bytes
    assert source.read_bytes() == _fixture_bytes(fixture)
