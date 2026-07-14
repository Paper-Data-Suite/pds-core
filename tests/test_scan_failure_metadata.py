"""Tests for generic version 2 routing-failure metadata."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from pds_core.module_dispatch import (
    ModuleContractCompatibilityError,
    ModuleRegistrationValidationError,
    ModuleRouteHandlingError,
    RouteDispatchFailure,
    RouteDispatchRequest,
    RouteDispatchRequestError,
    RouteStatusNotDispatchableError,
)
from pds_core.module_profiles import UnsupportedModuleError
from pds_core.route_registrations import (
    RouteRegistrationIntegrityError,
    RouteRegistrationNotFoundError,
    RouteRegistrationReadError,
)
from pds_core.routing_models import (
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RoutingModelError,
)
from pds_core.scan_failure_metadata import (
    ROUTING_FAILURE_CATEGORIES,
    ROUTING_FAILURE_SCHEMA_VERSION,
    RoutingFailureMetadata,
    RoutingFailureMetadataError,
    RoutingFailureMetadataIntegrityError,
    RoutingFailureMetadataNotFoundError,
    RoutingFailureMetadataReadError,
    RoutingFailureMetadataWriteError,
    is_routing_failure_category,
    load_routing_failure_metadata,
    routing_failure_category_for_dispatch_error,
    routing_failure_metadata_from_dict,
    routing_failure_metadata_from_dispatch_failure,
    routing_failure_metadata_path,
    routing_failure_metadata_to_dict,
    routing_failure_stage_for_dispatch_error,
    write_routing_failure_metadata,
)
from pds_core.scan_retention import RetainedSourceScan


def locator(module_id: str = "quillan") -> RouteLocator:
    return RouteLocator(
        schema="PDS2",
        work=ModuleWorkRef(
            module_id=module_id,
            class_id="english9_p2",
            work_id="analysis_essay",
        ),
        route_id="route_001",
    )


def target(module_id: str = "quillan") -> ModuleRecordRef:
    return ModuleRecordRef(
        module_id=module_id,
        record_kind="submission",
        record_id="submission_001",
        contract_version="1",
    )


def make_metadata(**overrides: object) -> RoutingFailureMetadata:
    values: dict[str, object] = {
        "schema_version": ROUTING_FAILURE_SCHEMA_VERSION,
        "failure_id": "failure_20260714_001",
        "scope": "scan",
        "stage": "intake",
        "created_at": "2026-07-14T14:00:00Z",
        "failure_category": "source_unreadable",
        "failure_message": "The selected source could not be read.",
        "source_filename": "scanner export.pdf",
        "source_scan_id": None,
        "source_sha256": None,
        "retained_source_path": None,
        "review_copy_path": None,
        "source_page_number": None,
        "detected_payload": None,
        "route_locator": None,
        "target": None,
        "module_details": {},
    }
    values.update(overrides)
    return RoutingFailureMetadata(**values)  # type: ignore[arg-type]


def page_metadata(**overrides: object) -> RoutingFailureMetadata:
    values: dict[str, object] = {
        "scope": "page",
        "stage": "route_resolution",
        "failure_category": "route_unknown",
        "source_scan_id": "scan_20260714_001",
        "source_sha256": "a" * 64,
        "retained_source_path": "scans/source/2026-07-14/scan.pdf",
        "source_page_number": 2,
        "detected_payload": " PDS2|raw|payload \n",
        "route_locator": locator(),
    }
    values.update(overrides)
    return make_metadata(**values)


def test_exact_category_vocabulary_and_removed_categories() -> None:
    assert ROUTING_FAILURE_CATEGORIES == {
        "source_missing", "source_unreadable", "source_type_unsupported",
        "source_retention_failed", "payload_missing", "payload_unreadable",
        "payload_invalid", "payload_schema_unsupported", "payload_too_large",
        "identifier_invalid", "module_unsupported",
        "module_profile_incompatible", "class_unknown", "work_unknown",
        "route_unknown", "route_inactive", "route_ambiguous",
        "route_mismatch", "route_registration_invalid", "target_unknown",
        "target_incompatible", "page_conflict", "processing_error",
        "evidence_write_failed",
    }
    assert all(is_routing_failure_category(item) for item in ROUTING_FAILURE_CATEGORIES)
    assert not is_routing_failure_category("assignment_unknown")
    assert not is_routing_failure_category("student_unknown")


def test_model_is_frozen_slotted_and_has_no_removed_attributes() -> None:
    metadata = make_metadata()
    assert not hasattr(metadata, "__dict__")
    for name in ("module", "payload_page_number", "class_id", "assignment_id", "student_id"):
        assert not hasattr(metadata, name)
    with pytest.raises(FrozenInstanceError):
        metadata.failure_id = "changed"  # type: ignore[misc]


def test_exact_shape_round_trip_and_raw_payload_preservation() -> None:
    metadata = page_metadata(target=target(), module_details={"candidate": [1, 2]})
    data = routing_failure_metadata_to_dict(metadata)
    assert set(data) == {
        "schema_version", "failure_id", "scope", "stage", "created_at",
        "failure_category", "failure_message", "source_filename",
        "source_scan_id", "source_sha256", "retained_source_path",
        "review_copy_path", "source_page_number", "detected_payload",
        "route_locator", "target", "module_details",
    }
    assert data["detected_payload"] == " PDS2|raw|payload \n"
    assert routing_failure_metadata_from_dict(data) == metadata


@pytest.mark.parametrize("key", ["failure_message", "route_locator", "target"])
def test_from_dict_rejects_missing_keys(key: str) -> None:
    data = routing_failure_metadata_to_dict(make_metadata())
    del data[key]
    with pytest.raises(RoutingFailureMetadataError, match="missing required"):
        routing_failure_metadata_from_dict(data)


def test_from_dict_rejects_unknown_and_non_string_keys() -> None:
    data = routing_failure_metadata_to_dict(make_metadata())
    data["unknown"] = True
    with pytest.raises(RoutingFailureMetadataError, match="unknown key"):
        routing_failure_metadata_from_dict(data)
    data = routing_failure_metadata_to_dict(make_metadata())
    data[1] = True  # type: ignore[index]
    with pytest.raises(RoutingFailureMetadataError, match="keys must be strings"):
        routing_failure_metadata_from_dict(data)


def test_version_one_is_rejected() -> None:
    with pytest.raises(RoutingFailureMetadataError, match='must be "2"'):
        make_metadata(schema_version="1")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"scope": "page", "source_page_number": None}, "positive integer"),
        ({"scope": "page", "source_page_number": True}, "positive integer"),
        ({"source_page_number": 1}, "scan-scoped"),
        ({"stage": "Route_Resolution"}, "lowercase"),
        ({"failure_message": " two "}, "whitespace"),
        ({"failure_message": "two\nlines"}, "single-line"),
        ({"source_filename": "../scan.pdf"}, "filename"),
    ],
)
def test_scope_stage_message_and_filename_invariants(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(RoutingFailureMetadataError, match=message):
        make_metadata(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_scan_id": "scan_001"},
        {"source_sha256": "a" * 64},
        {"retained_source_path": "scans/source/file.pdf"},
        {
            "source_scan_id": "scan_001",
            "source_sha256": "a" * 63,
            "retained_source_path": "scans/source/file.pdf",
        },
        {
            "source_scan_id": "scan_001",
            "source_sha256": "a" * 64,
            "retained_source_path": "../file.pdf",
        },
    ],
)
def test_retained_provenance_is_complete_and_valid(overrides: dict[str, object]) -> None:
    with pytest.raises(RoutingFailureMetadataError):
        make_metadata(**overrides)


def test_target_requires_locator_and_matching_module() -> None:
    with pytest.raises(RoutingFailureMetadataError, match="requires"):
        make_metadata(target=target())
    with pytest.raises(RoutingFailureMetadataError, match="must match"):
        page_metadata(target=target("scoreform"))
    assert page_metadata(route_locator=locator(), target=None).target is None


def test_invalid_nested_locator_and_target_mappings_are_rejected() -> None:
    data = routing_failure_metadata_to_dict(page_metadata())
    assert isinstance(data["route_locator"], dict)
    data["route_locator"]["extra"] = True
    with pytest.raises(RoutingFailureMetadataError, match="routing identity"):
        routing_failure_metadata_from_dict(data)
    data = routing_failure_metadata_to_dict(page_metadata(target=target()))
    assert isinstance(data["target"], dict)
    data["target"]["module_id"] = "scoreform"
    with pytest.raises(RoutingFailureMetadataError, match="must match"):
        routing_failure_metadata_from_dict(data)


def test_module_details_are_deeply_isolated() -> None:
    details = {"nested": {"items": [1, {"value": "original"}]}}
    metadata = make_metadata(module_details=details)
    details["nested"]["items"][1]["value"] = "constructor mutation"  # type: ignore[index]
    exposed: Any = metadata.module_details
    exposed["nested"]["items"][1]["value"] = "exposed mutation"
    serialized = routing_failure_metadata_to_dict(metadata)
    serialized_details = serialized["module_details"]
    assert isinstance(serialized_details, dict)
    serialized_details["new"] = True
    assert metadata.module_details == {
        "nested": {"items": [1, {"value": "original"}]}
    }
    json.dumps(metadata.module_details, allow_nan=False)


@pytest.mark.parametrize(
    "details",
    [{1: "bad"}, {"bad": object()}, {"bad": float("nan")}, {"bad": float("inf")}],
)
def test_module_details_reject_non_json_values(details: dict[Any, object]) -> None:
    with pytest.raises(RoutingFailureMetadataError, match="module_details"):
        make_metadata(module_details=details)


def test_module_details_reject_circular_references() -> None:
    details: dict[str, Any] = {}
    details["self"] = details
    with pytest.raises(RoutingFailureMetadataError, match="circular"):
        make_metadata(module_details=details)


@pytest.mark.parametrize(
    ("error", "category", "stage"),
    [
        (UnsupportedModuleError("unsupported"), "module_unsupported", "module_resolution"),
        (ModuleContractCompatibilityError("profile"), "module_profile_incompatible", "module_resolution"),
        (RouteRegistrationNotFoundError("missing"), "route_unknown", "route_resolution"),
        (RouteRegistrationIntegrityError("mismatch"), "route_mismatch", "route_resolution"),
        (RouteRegistrationReadError("invalid"), "route_registration_invalid", "route_resolution"),
        (RouteStatusNotDispatchableError("inactive"), "route_inactive", "route_resolution"),
        (ModuleRegistrationValidationError("target"), "target_incompatible", "module_validation"),
        (ModuleRouteHandlingError("handler"), "processing_error", "module_handling"),
        (RouteDispatchRequestError("request"), "processing_error", "module_handling"),
        (RoutingModelError("identity"), "identifier_invalid", "route_resolution"),
    ],
)
def test_dispatch_error_mapping(error: Exception, category: str, stage: str) -> None:
    assert routing_failure_category_for_dispatch_error(error) == category
    assert routing_failure_stage_for_dispatch_error(error) == stage


@pytest.mark.parametrize("source_sha256", [123, []])
def test_direct_constructor_rejects_non_string_source_hash(
    source_sha256: object,
) -> None:
    with pytest.raises(RoutingFailureMetadataError, match="source_sha256"):
        make_metadata(
            source_scan_id="scan_001",
            source_sha256=source_sha256,
            retained_source_path="scans/source/2026-07-14/scan.pdf",
        )


@pytest.mark.parametrize("scope", [[], None])
def test_direct_constructor_rejects_non_string_or_unhashable_scope(
    scope: object,
) -> None:
    with pytest.raises(RoutingFailureMetadataError, match="scope"):
        make_metadata(scope=scope)


def test_dispatch_failure_builder_copies_request_and_optional_values(tmp_path: Path) -> None:
    retained = RetainedSourceScan(
        source_scan_id="scan_001",
        source_filename="source.pdf",
        source_sha256="b" * 64,
        retained_source_path=tmp_path / "source.pdf",
        retained_source_relative_path="scans/source/2026-07-14/source.pdf",
        intake_timestamp=datetime(2026, 7, 14, tzinfo=timezone.utc),
        intake_date=date(2026, 7, 14),
    )
    request = RouteDispatchRequest(locator(), retained, 4)
    failure = RouteDispatchFailure(request, RouteRegistrationNotFoundError("missing"))
    metadata = routing_failure_metadata_from_dispatch_failure(
        failure,
        failure_id="failure_001",
        created_at="2026-07-14T15:00:00Z",
        detected_payload="raw payload",
        review_copy_path="scans/review/page-4.pdf",
        target=target(),
        module_details={"attempt": 1},
    )
    assert metadata.route_locator == request.locator
    assert metadata.source_scan_id == retained.source_scan_id
    assert metadata.source_page_number == 4
    assert metadata.detected_payload == "raw payload"
    assert metadata.target == target()


def test_path_helper_is_canonical_and_side_effect_free(tmp_path: Path) -> None:
    path = routing_failure_metadata_path(tmp_path, "failure_001")
    assert path == tmp_path / "scans" / "review" / "failure_001.json"
    assert not path.parent.exists()


def test_writer_loader_stable_exclusive_and_fsynced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr("pds_core.scan_failure_metadata.os.fsync", calls.append)
    metadata = page_metadata(target=target())
    path = write_routing_failure_metadata(tmp_path, metadata)
    expected = json.dumps(
        routing_failure_metadata_to_dict(metadata), indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    assert path.read_text(encoding="utf-8") == expected
    assert calls
    assert load_routing_failure_metadata(tmp_path, metadata.failure_id) == metadata
    with pytest.raises(RoutingFailureMetadataWriteError, match="already exists"):
        write_routing_failure_metadata(tmp_path, metadata)
    assert path.read_text(encoding="utf-8") == expected


def test_concurrent_writers_create_exactly_one_failure(tmp_path: Path) -> None:
    metadata = make_metadata()
    barrier = threading.Barrier(2)

    def attempt() -> str:
        barrier.wait()
        try:
            write_routing_failure_metadata(tmp_path, metadata)
        except RoutingFailureMetadataWriteError:
            return "collision"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["collision", "created"]


def test_partial_failure_write_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("pds_core.scan_failure_metadata.os.fsync", fail_fsync)
    metadata = make_metadata()
    with pytest.raises(RoutingFailureMetadataWriteError, match="simulated"):
        write_routing_failure_metadata(tmp_path, metadata)
    assert not routing_failure_metadata_path(tmp_path, metadata.failure_id).exists()


def test_loader_missing_malformed_non_object_and_invalid_utf8(tmp_path: Path) -> None:
    with pytest.raises(RoutingFailureMetadataNotFoundError):
        load_routing_failure_metadata(tmp_path, "failure_001")
    path = routing_failure_metadata_path(tmp_path, "failure_001")
    path.parent.mkdir(parents=True)
    for content in (b"{", b"[]", b"\xff"):
        path.write_bytes(content)
        with pytest.raises(RoutingFailureMetadataReadError):
            load_routing_failure_metadata(tmp_path, "failure_001")


def test_loader_rejects_duplicate_keys_and_invalid_constants(tmp_path: Path) -> None:
    path = routing_failure_metadata_path(tmp_path, "failure_001")
    path.parent.mkdir(parents=True)
    path.write_text('{"x": 1, "x": 2}', encoding="utf-8")
    with pytest.raises(RoutingFailureMetadataReadError, match="duplicate"):
        load_routing_failure_metadata(tmp_path, "failure_001")
    path.write_text('{"x": NaN}', encoding="utf-8")
    with pytest.raises(RoutingFailureMetadataReadError, match="numeric constant"):
        load_routing_failure_metadata(tmp_path, "failure_001")


def test_loader_checks_requested_failure_id(tmp_path: Path) -> None:
    stored = make_metadata(failure_id="failure_stored")
    path = routing_failure_metadata_path(tmp_path, "failure_requested")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(routing_failure_metadata_to_dict(stored)), encoding="utf-8")
    with pytest.raises(RoutingFailureMetadataIntegrityError):
        load_routing_failure_metadata(tmp_path, "failure_requested")
