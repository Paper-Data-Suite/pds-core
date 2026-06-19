"""Tests for shared active-scan routing failure metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pds_core.scan_failure_metadata import (
    ROUTING_FAILURE_CATEGORIES,
    RoutingFailureMetadata,
    RoutingFailureMetadataError,
    RoutingFailureMetadataWriteError,
    is_routing_failure_category,
    routing_failure_metadata_from_dict,
    routing_failure_metadata_path,
    routing_failure_metadata_to_dict,
    validate_routing_failure_metadata,
    write_routing_failure_metadata,
)


def make_metadata(**overrides: object) -> RoutingFailureMetadata:
    values: dict[str, object] = {
        "schema_version": "1",
        "failure_id": "failure_20260619_001",
        "scope": "scan",
        "stage": "intake",
        "created_at": "2026-06-19T18:45:12.123456Z",
        "failure_category": "source_unreadable",
        "failure_message": "The selected source could not be read.",
        "source_filename": "scanner export.pdf",
        "module_details": {},
        "module": None,
        "source_scan_id": None,
        "source_sha256": None,
        "retained_source_path": None,
        "review_copy_path": None,
        "source_page_number": None,
        "detected_payload": None,
        "payload_page_number": None,
        "class_id": None,
        "assignment_id": None,
        "student_id": None,
    }
    values.update(overrides)
    return RoutingFailureMetadata(**values)  # type: ignore[arg-type]


def test_all_contract_failure_categories_are_recognized() -> None:
    expected = {
        "source_missing",
        "source_unreadable",
        "source_type_unsupported",
        "source_retention_failed",
        "payload_missing",
        "payload_unreadable",
        "payload_invalid",
        "payload_schema_unsupported",
        "module_unsupported",
        "identifier_invalid",
        "class_unknown",
        "assignment_unknown",
        "student_unknown",
        "route_mismatch",
        "route_ambiguous",
        "page_conflict",
        "processing_error",
        "evidence_write_failed",
    }

    assert ROUTING_FAILURE_CATEGORIES == expected
    assert all(is_routing_failure_category(value) for value in expected)
    assert not is_routing_failure_category("module_specific_error")
    assert not is_routing_failure_category(None)


def test_valid_minimal_scan_metadata_passes() -> None:
    metadata = make_metadata()

    assert validate_routing_failure_metadata(metadata) is metadata


def test_valid_page_metadata_passes_and_round_trips() -> None:
    metadata = make_metadata(
        scope="page",
        stage="routing",
        failure_category="assignment_unknown",
        module="quillan",
        source_scan_id="scan_20260619_001",
        source_sha256="A" * 64,
        retained_source_path=(
            "scans/source/2026-06-19/"
            "20260619T184512123456Z__scan__aaaaaaaaaaaa.pdf"
        ),
        review_copy_path="scans/review/problem-page-2.pdf",
        source_page_number=2,
        detected_payload="PDS1|...",
        payload_page_number=1,
        class_id="english12_p4",
        assignment_id="personal_narrative",
        student_id="1001",
        module_details={"reason_code": "no_match", "candidates": []},
    )

    data = routing_failure_metadata_to_dict(metadata)

    assert routing_failure_metadata_from_dict(data) == metadata
    assert data["source_sha256"] == "A" * 64


def test_dict_conversion_includes_all_required_nullable_keys() -> None:
    data = routing_failure_metadata_to_dict(make_metadata())

    for key in (
        "module",
        "source_scan_id",
        "source_sha256",
        "retained_source_path",
        "review_copy_path",
        "source_page_number",
        "detected_payload",
        "payload_page_number",
        "class_id",
        "assignment_id",
        "student_id",
    ):
        assert key in data
        assert data[key] is None


@pytest.mark.parametrize("missing_key", ["failure_message", "module"])
def test_from_dict_rejects_missing_required_keys(missing_key: str) -> None:
    data = routing_failure_metadata_to_dict(make_metadata())
    del data[missing_key]

    with pytest.raises(RoutingFailureMetadataError, match="missing required"):
        routing_failure_metadata_from_dict(data)


def test_from_dict_rejects_extra_top_level_keys() -> None:
    data = routing_failure_metadata_to_dict(make_metadata())
    data["module_specific"] = "outside extension point"

    with pytest.raises(RoutingFailureMetadataError, match="unknown key"):
        routing_failure_metadata_from_dict(data)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("schema_version", "2"),
        ("scope", "batch"),
        ("stage", ""),
        ("created_at", "not-a-date"),
        ("created_at", "2026-06-19T18:45:12"),
        ("failure_category", "unknown"),
        ("failure_message", ""),
        ("source_filename", "../scan.pdf"),
        ("source_filename", "C:scan.pdf"),
        ("source_page_number", 0),
        ("source_page_number", True),
        ("payload_page_number", -1),
        ("class_id", "bad/id"),
        ("assignment_id", " bad"),
        ("student_id", ""),
        ("source_sha256", "a" * 63),
        ("retained_source_path", "/absolute/scan.pdf"),
        ("retained_source_path", "../scan.pdf"),
        ("retained_source_path", "C:scan.pdf"),
        ("review_copy_path", r"C:\review\scan.pdf"),
    ],
)
def test_invalid_metadata_fields_fail(field_name: str, value: object) -> None:
    with pytest.raises(RoutingFailureMetadataError):
        make_metadata(**{field_name: value})


def test_module_details_must_be_dict() -> None:
    data = routing_failure_metadata_to_dict(make_metadata())
    data["module_details"] = []

    with pytest.raises(RoutingFailureMetadataError, match="must be a dict"):
        routing_failure_metadata_from_dict(data)


@pytest.mark.parametrize(
    "module_details",
    [
        {"bad": object()},
        {"bad": float("nan")},
        {1: "non-string key"},
    ],
)
def test_module_details_must_be_json_serializable(
    module_details: dict[Any, object],
) -> None:
    with pytest.raises(RoutingFailureMetadataError, match="module_details"):
        make_metadata(module_details=module_details)


def test_routing_failure_metadata_path_is_side_effect_free(
    tmp_path: Path,
) -> None:
    path = routing_failure_metadata_path(tmp_path, "failure_001")

    assert path == tmp_path / "scans" / "review" / "failure_001.json"
    assert not path.parent.exists()


@pytest.mark.parametrize("failure_id", ["../failure", "bad/id", "", " bad"])
def test_routing_failure_metadata_path_rejects_unsafe_id(
    tmp_path: Path,
    failure_id: str,
) -> None:
    with pytest.raises(RoutingFailureMetadataError):
        routing_failure_metadata_path(tmp_path, failure_id)


def test_writer_creates_stable_json_and_returns_path(tmp_path: Path) -> None:
    metadata = make_metadata()

    path = write_routing_failure_metadata(tmp_path, metadata)

    assert path == (
        tmp_path / "scans" / "review" / "failure_20260619_001.json"
    )
    content = path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    assert content == (
        json.dumps(
            routing_failure_metadata_to_dict(metadata),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    assert not (tmp_path / "scans" / "source").exists()


def test_writer_refuses_to_overwrite_existing_metadata(
    tmp_path: Path,
) -> None:
    metadata = make_metadata()
    path = write_routing_failure_metadata(tmp_path, metadata)
    original_content = path.read_text(encoding="utf-8")

    with pytest.raises(
        RoutingFailureMetadataWriteError,
        match="already exists",
    ):
        write_routing_failure_metadata(tmp_path, metadata)

    assert path.read_text(encoding="utf-8") == original_content
