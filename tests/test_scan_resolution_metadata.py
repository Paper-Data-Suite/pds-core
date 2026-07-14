"""Tests for append-only version 2 scan-resolution metadata."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef, RouteLocator
from pds_core.scan_failure_metadata import (
    ROUTING_FAILURE_SCHEMA_VERSION,
    RoutingFailureMetadata,
    routing_failure_metadata_path,
    routing_failure_metadata_to_dict,
    write_routing_failure_metadata,
)
from pds_core.scan_resolution_metadata import (
    SCAN_RESOLUTION_ACTIONS,
    SCAN_RESOLUTION_SCHEMA_VERSION,
    SCAN_RESOLUTION_STATUSES,
    ScanResolutionMetadata,
    ScanResolutionMetadataError,
    ScanResolutionMetadataIntegrityError,
    ScanResolutionMetadataNotFoundError,
    ScanResolutionMetadataReadError,
    ScanResolutionMetadataWriteError,
    create_scan_resolution_metadata,
    is_scan_resolution_action,
    is_scan_resolution_status,
    load_scan_resolution_metadata,
    scan_resolution_metadata_dir,
    scan_resolution_metadata_from_dict,
    scan_resolution_metadata_path,
    scan_resolution_metadata_to_dict,
    write_scan_resolution_metadata,
)


def locator(module_id: str = "concord") -> RouteLocator:
    return RouteLocator(
        schema="PDS2",
        work=ModuleWorkRef(
            module_id=module_id,
            class_id="science7_p3",
            work_id="ecosystems_lab",
        ),
        route_id="route_001",
    )


def target(module_id: str = "concord") -> ModuleRecordRef:
    return ModuleRecordRef(
        module_id=module_id,
        record_kind="evidence",
        record_id="evidence_001",
        contract_version="1",
    )


def make_failure(**overrides: object) -> RoutingFailureMetadata:
    values: dict[str, object] = {
        "schema_version": ROUTING_FAILURE_SCHEMA_VERSION,
        "failure_id": "failure_20260714_001",
        "scope": "page",
        "stage": "route_resolution",
        "created_at": "2026-07-14T14:00:00Z",
        "failure_category": "route_unknown",
        "failure_message": "No route registration exists.",
        "source_filename": "scanner export.pdf",
        "source_scan_id": "scan_20260714_001",
        "source_sha256": "a" * 64,
        "retained_source_path": "scans/source/2026-07-14/scan.pdf",
        "review_copy_path": "scans/review/page-2.pdf",
        "source_page_number": 2,
        "detected_payload": "PDS2|concord|science7_p3|ecosystems_lab|route_001",
        "route_locator": locator(),
        "target": None,
        "module_details": {},
    }
    values.update(overrides)
    return RoutingFailureMetadata(**values)  # type: ignore[arg-type]


def make_metadata(**overrides: object) -> ScanResolutionMetadata:
    values: dict[str, object] = {
        "schema_version": SCAN_RESOLUTION_SCHEMA_VERSION,
        "resolution_id": "resolution_20260714_001",
        "failure_id": "failure_20260714_001",
        "failure_metadata_path": "scans/review/failure_20260714_001.json",
        "resolution_status": "resolved",
        "resolution_action": "rescan_needed",
        "resolved_at": "2026-07-14T15:00:00Z",
        "resolution_message": "The source page needs to be scanned again.",
        "source_filename": "scanner export.pdf",
        "source_scan_id": "scan_20260714_001",
        "source_sha256": "a" * 64,
        "retained_source_path": "scans/source/2026-07-14/scan.pdf",
        "review_copy_path": "scans/review/page-2.pdf",
        "source_page_number": 2,
        "route_locator": None,
        "target": None,
        "resolution_evidence_path": None,
        "module_details": {},
    }
    values.update(overrides)
    return ScanResolutionMetadata(**values)  # type: ignore[arg-type]


def routed_metadata(**overrides: object) -> ScanResolutionMetadata:
    values: dict[str, object] = {
        "resolution_action": "route_corrected",
        "route_locator": locator(),
        "target": target(),
    }
    values.update(overrides)
    return make_metadata(**values)


def test_exact_status_and_action_vocabularies() -> None:
    assert SCAN_RESOLUTION_STATUSES == {"resolved", "deferred"}
    assert SCAN_RESOLUTION_ACTIONS == {
        "route_selected", "route_corrected", "evidence_filed",
        "rescan_needed", "cannot_route", "dismissed_duplicate", "deferred",
        "other",
    }
    assert all(is_scan_resolution_status(value) for value in SCAN_RESOLUTION_STATUSES)
    assert all(is_scan_resolution_action(value) for value in SCAN_RESOLUTION_ACTIONS)
    for removed in ("manual_entry", "manual_marks", "mixed_assignment"):
        assert not is_scan_resolution_action(removed)


def test_model_is_frozen_slotted_and_has_no_removed_attributes() -> None:
    metadata = make_metadata()
    assert not hasattr(metadata, "__dict__")
    for name in ("module", "class_id", "assignment_id", "student_id"):
        assert not hasattr(metadata, name)
    with pytest.raises(FrozenInstanceError):
        metadata.failure_id = "changed"  # type: ignore[misc]


def test_exact_shape_round_trip_with_locator_and_target() -> None:
    metadata = routed_metadata(module_details={"reviewer": "teacher"})
    data = scan_resolution_metadata_to_dict(metadata)
    assert set(data) == {
        "schema_version", "resolution_id", "failure_id",
        "failure_metadata_path", "resolution_status", "resolution_action",
        "resolved_at", "resolution_message", "source_filename",
        "source_scan_id", "source_sha256", "retained_source_path",
        "review_copy_path", "source_page_number", "route_locator", "target",
        "resolution_evidence_path", "module_details",
    }
    assert scan_resolution_metadata_from_dict(data) == metadata


def test_version_one_missing_unknown_and_non_string_keys_are_rejected() -> None:
    with pytest.raises(ScanResolutionMetadataError, match='must be "2"'):
        make_metadata(schema_version="1")
    data = scan_resolution_metadata_to_dict(make_metadata())
    del data["target"]
    with pytest.raises(ScanResolutionMetadataError, match="missing required"):
        scan_resolution_metadata_from_dict(data)
    data = scan_resolution_metadata_to_dict(make_metadata())
    data["unknown"] = True
    with pytest.raises(ScanResolutionMetadataError, match="unknown key"):
        scan_resolution_metadata_from_dict(data)
    data = scan_resolution_metadata_to_dict(make_metadata())
    data[1] = True  # type: ignore[index]
    with pytest.raises(ScanResolutionMetadataError, match="keys must be strings"):
        scan_resolution_metadata_from_dict(data)


def test_failure_path_must_be_exactly_canonical() -> None:
    with pytest.raises(ScanResolutionMetadataError, match="must equal"):
        make_metadata(failure_metadata_path="scans/review/other.json")


@pytest.mark.parametrize("source_sha256", [123, []])
def test_direct_constructor_rejects_non_string_source_hash(
    source_sha256: object,
) -> None:
    with pytest.raises(ScanResolutionMetadataError, match="source_sha256"):
        make_metadata(source_sha256=source_sha256)


def test_target_requires_locator_and_module_match() -> None:
    with pytest.raises(ScanResolutionMetadataError, match="requires"):
        make_metadata(resolution_action="other", target=target())
    with pytest.raises(ScanResolutionMetadataError, match="must match"):
        make_metadata(
            resolution_action="other",
            route_locator=locator(),
            target=target("quillan"),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"resolution_status": "deferred", "resolution_action": "other"},
        {"resolution_status": "resolved", "resolution_action": "deferred"},
        {
            "resolution_status": "deferred",
            "resolution_action": "deferred",
            "route_locator": locator(),
        },
        {"resolution_action": "route_selected"},
        {"resolution_action": "route_corrected", "route_locator": locator()},
        {"resolution_action": "evidence_filed"},
        {
            "resolution_action": "cannot_route",
            "resolution_evidence_path": "evidence/file.json",
        },
        {"resolution_action": "dismissed_duplicate", "route_locator": locator()},
    ],
)
def test_status_action_invariants(overrides: dict[str, object]) -> None:
    with pytest.raises(ScanResolutionMetadataError):
        make_metadata(**overrides)


def test_valid_deferred_evidence_and_other_actions() -> None:
    assert make_metadata(
        resolution_status="deferred",
        resolution_action="deferred",
    ).resolution_status == "deferred"
    assert make_metadata(
        resolution_action="evidence_filed",
        resolution_evidence_path="classes/science/evidence.json",
    ).resolution_evidence_path is not None
    assert make_metadata(
        resolution_action="other",
        route_locator=locator(),
        resolution_evidence_path="classes/science/note.json",
    ).route_locator is not None


def test_builder_copies_provenance_allows_corrected_route_and_equal_timestamp() -> None:
    failure = make_failure()
    corrected = RouteLocator(
        schema="PDS2",
        work=ModuleWorkRef("concord", "science7_p3", "corrected_lab"),
        route_id="route_corrected",
    )
    corrected_target = ModuleRecordRef("concord", "evidence", "evidence_corrected")
    metadata = create_scan_resolution_metadata(
        failure,
        resolution_id="resolution_equal_time",
        resolution_status="resolved",
        resolution_action="route_corrected",
        resolved_at=failure.created_at,
        resolution_message="The Concord route was corrected.",
        route_locator=corrected,
        target=corrected_target,
    )
    assert metadata.failure_metadata_path == "scans/review/failure_20260714_001.json"
    for field_name in (
        "source_filename", "source_scan_id", "source_sha256",
        "retained_source_path", "review_copy_path", "source_page_number",
    ):
        assert getattr(metadata, field_name) == getattr(failure, field_name)
    assert metadata.route_locator == corrected
    assert failure.route_locator == locator()


def test_builder_rejects_timestamp_before_failure() -> None:
    with pytest.raises(ScanResolutionMetadataError, match="predate"):
        create_scan_resolution_metadata(
            make_failure(),
            resolution_id="resolution_early",
            resolution_status="resolved",
            resolution_action="cannot_route",
            resolved_at="2026-07-14T13:59:59Z",
            resolution_message="No valid route could be selected.",
        )


def test_module_details_are_deeply_isolated_and_json_native() -> None:
    details = {"nested": {"items": [1, {"value": "original"}]}}
    metadata = make_metadata(module_details=details)
    details["nested"]["items"][1]["value"] = "input mutation"  # type: ignore[index]
    exposed: Any = metadata.module_details
    exposed["nested"]["items"][1]["value"] = "output mutation"
    data = scan_resolution_metadata_to_dict(metadata)
    serialized = data["module_details"]
    assert isinstance(serialized, dict)
    serialized["new"] = True
    assert metadata.module_details == {
        "nested": {"items": [1, {"value": "original"}]}
    }
    json.dumps(metadata.module_details, allow_nan=False)


@pytest.mark.parametrize(
    "details",
    [{1: "bad"}, {"bad": object()}, {"bad": float("nan")}, {"bad": float("inf")}],
)
def test_module_details_reject_non_json_values(details: dict[Any, object]) -> None:
    with pytest.raises(ScanResolutionMetadataError, match="module_details"):
        make_metadata(module_details=details)


def test_path_helpers_are_canonical_and_side_effect_free(tmp_path: Path) -> None:
    directory = scan_resolution_metadata_dir(tmp_path)
    path = scan_resolution_metadata_path(tmp_path, "resolution_001")
    assert directory == tmp_path / "scans" / "review" / "resolutions"
    assert path == directory / "resolution_001.json"
    assert not directory.exists()


def test_writer_requires_valid_linked_failure(tmp_path: Path) -> None:
    resolution_path = scan_resolution_metadata_path(
        tmp_path, "resolution_20260714_001"
    )
    with pytest.raises(ScanResolutionMetadataReadError, match="linked routing failure"):
        write_scan_resolution_metadata(tmp_path, make_metadata())
    assert not resolution_path.exists()
    failure_path = routing_failure_metadata_path(tmp_path, "failure_20260714_001")
    failure_path.parent.mkdir(parents=True)
    failure_path.write_text("{", encoding="utf-8")
    with pytest.raises(ScanResolutionMetadataReadError, match="linked routing failure"):
        write_scan_resolution_metadata(tmp_path, make_metadata())
    assert not resolution_path.exists()
    assert not scan_resolution_metadata_dir(tmp_path).exists()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_filename", "other.pdf"),
        ("source_scan_id", "scan_other"),
        ("source_sha256", "b" * 64),
        ("retained_source_path", "scans/source/other.pdf"),
        ("review_copy_path", None),
        ("source_page_number", 3),
    ],
)
def test_writer_rejects_each_provenance_mismatch(
    tmp_path: Path, field_name: str, value: object
) -> None:
    write_routing_failure_metadata(tmp_path, make_failure())
    metadata = make_metadata(**{field_name: value})
    with pytest.raises(ScanResolutionMetadataIntegrityError, match=field_name):
        write_scan_resolution_metadata(tmp_path, metadata)
    assert not scan_resolution_metadata_path(
        tmp_path, metadata.resolution_id
    ).exists()


def test_writer_rejects_timestamp_mismatch_as_integrity_error(
    tmp_path: Path,
) -> None:
    write_routing_failure_metadata(tmp_path, make_failure())
    metadata = make_metadata(resolved_at="2026-07-14T13:59:59Z")
    with pytest.raises(ScanResolutionMetadataIntegrityError, match="predates"):
        write_scan_resolution_metadata(tmp_path, metadata)
    assert not scan_resolution_metadata_path(
        tmp_path, metadata.resolution_id
    ).exists()


def test_writer_is_stable_exclusive_fsynced_and_preserves_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure_path = write_routing_failure_metadata(tmp_path, make_failure())
    failure_bytes = failure_path.read_bytes()
    calls: list[int] = []
    monkeypatch.setattr("pds_core.scan_resolution_metadata.os.fsync", calls.append)
    metadata = routed_metadata()
    path = write_scan_resolution_metadata(tmp_path, metadata)
    expected = json.dumps(
        scan_resolution_metadata_to_dict(metadata), indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    assert path.read_text(encoding="utf-8") == expected
    assert calls
    assert failure_path.read_bytes() == failure_bytes
    with pytest.raises(ScanResolutionMetadataWriteError, match="already exists"):
        write_scan_resolution_metadata(tmp_path, metadata)
    assert failure_path.read_bytes() == failure_bytes


def test_concurrent_writers_append_exactly_one_resolution(tmp_path: Path) -> None:
    write_routing_failure_metadata(tmp_path, make_failure())
    metadata = make_metadata()
    barrier = threading.Barrier(2)

    def attempt() -> str:
        barrier.wait()
        try:
            write_scan_resolution_metadata(tmp_path, metadata)
        except ScanResolutionMetadataWriteError:
            return "collision"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["collision", "created"]


def test_partial_resolution_write_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_routing_failure_metadata(tmp_path, make_failure())

    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("pds_core.scan_resolution_metadata.os.fsync", fail_fsync)
    metadata = make_metadata()
    with pytest.raises(ScanResolutionMetadataWriteError, match="simulated"):
        write_scan_resolution_metadata(tmp_path, metadata)
    assert not scan_resolution_metadata_path(tmp_path, metadata.resolution_id).exists()


def test_multiple_resolution_ids_append_for_one_failure(tmp_path: Path) -> None:
    failure = make_failure()
    write_routing_failure_metadata(tmp_path, failure)
    deferred = create_scan_resolution_metadata(
        failure,
        resolution_id="resolution_001",
        resolution_status="deferred",
        resolution_action="deferred",
        resolved_at="2026-07-14T15:00:00Z",
        resolution_message="Review was deferred.",
    )
    corrected = create_scan_resolution_metadata(
        failure,
        resolution_id="resolution_002",
        resolution_status="resolved",
        resolution_action="route_corrected",
        resolved_at="2026-07-14T16:00:00Z",
        resolution_message="A corrected route was selected.",
        route_locator=locator(),
        target=target(),
    )
    first = write_scan_resolution_metadata(tmp_path, deferred)
    second = write_scan_resolution_metadata(tmp_path, corrected)
    assert first.exists() and second.exists()
    assert not (scan_resolution_metadata_dir(tmp_path) / "current.json").exists()


def test_loader_strict_behavior_and_id_integrity(tmp_path: Path) -> None:
    with pytest.raises(ScanResolutionMetadataNotFoundError):
        load_scan_resolution_metadata(tmp_path, "resolution_001")
    path = scan_resolution_metadata_path(tmp_path, "resolution_001")
    path.parent.mkdir(parents=True)
    for content in (b"{", b"[]", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}'):
        path.write_bytes(content)
        with pytest.raises(ScanResolutionMetadataReadError):
            load_scan_resolution_metadata(tmp_path, "resolution_001")

    stored = make_metadata(resolution_id="resolution_stored")
    path.write_text(json.dumps(scan_resolution_metadata_to_dict(stored)), encoding="utf-8")
    with pytest.raises(ScanResolutionMetadataIntegrityError):
        load_scan_resolution_metadata(tmp_path, "resolution_001")


def test_linked_version_one_failure_prevents_resolution_creation(tmp_path: Path) -> None:
    path = routing_failure_metadata_path(tmp_path, "failure_20260714_001")
    path.parent.mkdir(parents=True)
    data = routing_failure_metadata_to_dict(make_failure())
    data["schema_version"] = "1"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ScanResolutionMetadataReadError):
        write_scan_resolution_metadata(tmp_path, make_metadata())
    assert not scan_resolution_metadata_path(
        tmp_path, "resolution_20260714_001"
    ).exists()
