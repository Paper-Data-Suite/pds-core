"""Tests for shared active-scan resolution metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pds_core.scan_resolution_metadata import (
    SCAN_RESOLUTION_ACTIONS,
    SCAN_RESOLUTION_STATUSES,
    ScanResolutionMetadata,
    ScanResolutionMetadataError,
    ScanResolutionMetadataWriteError,
    is_scan_resolution_action,
    is_scan_resolution_status,
    scan_resolution_metadata_dir,
    scan_resolution_metadata_from_dict,
    scan_resolution_metadata_path,
    scan_resolution_metadata_to_dict,
    validate_scan_resolution_metadata,
    write_scan_resolution_metadata,
)


def make_metadata(**overrides: object) -> ScanResolutionMetadata:
    values: dict[str, object] = {
        "schema_version": "1",
        "resolution_id": "resolution_20260711_001",
        "failure_id": "failure_20260711_001",
        "failure_metadata_path": "scans/review/failure_20260711_001.json",
        "resolution_status": "resolved",
        "resolution_action": "rescan_needed",
        "resolved_at": "2026-07-11T15:05:00.000000Z",
        "resolution_message": "Teacher marked this scan for rescan.",
        "module_details": {"teacher_choice": "rescan_needed"},
        "module": "scoreform",
        "source_scan_id": "scan_20260711_001",
        "source_sha256": "a" * 64,
        "source_filename": "scanner export.pdf",
        "retained_source_path": "scans/source/2026-07-11/scan.pdf",
        "review_copy_path": None,
        "resolution_evidence_path": (
            "classes/english9_p2/assignments/rj_act1_quiz/scans/rescan.pdf"
        ),
        "source_page_number": None,
        "class_id": "english9_p2",
        "assignment_id": "rj_act1_quiz",
        "student_id": None,
    }
    values.update(overrides)
    return ScanResolutionMetadata(**values)  # type: ignore[arg-type]


def test_valid_full_metadata_validates() -> None:
    metadata = make_metadata()
    assert validate_scan_resolution_metadata(metadata) is metadata


def test_dict_conversion_has_exact_shape_and_round_trips() -> None:
    metadata = make_metadata()
    data = scan_resolution_metadata_to_dict(metadata)
    assert set(data) == {
        "schema_version", "resolution_id", "failure_id",
        "failure_metadata_path", "resolution_status", "resolution_action",
        "resolved_at", "resolution_message", "module_details", "module",
        "source_scan_id", "source_sha256", "source_filename",
        "retained_source_path", "review_copy_path",
        "resolution_evidence_path", "source_page_number", "class_id",
        "assignment_id", "student_id",
    }
    assert scan_resolution_metadata_from_dict(data) == metadata


@pytest.mark.parametrize("missing_key", ["resolution_message", "module"])
def test_from_dict_rejects_missing_keys(missing_key: str) -> None:
    data = scan_resolution_metadata_to_dict(make_metadata())
    del data[missing_key]
    with pytest.raises(ScanResolutionMetadataError, match="missing required"):
        scan_resolution_metadata_from_dict(data)


def test_from_dict_rejects_extra_keys() -> None:
    data = scan_resolution_metadata_to_dict(make_metadata())
    data["extra"] = True
    with pytest.raises(ScanResolutionMetadataError, match="unknown key"):
        scan_resolution_metadata_from_dict(data)


def test_status_vocabulary() -> None:
    assert SCAN_RESOLUTION_STATUSES == {"resolved", "deferred"}
    assert all(is_scan_resolution_status(value) for value in SCAN_RESOLUTION_STATUSES)
    for value in ("unresolved", "archived", "complete", "pending", ""):
        assert not is_scan_resolution_status(value)
        with pytest.raises(ScanResolutionMetadataError):
            make_metadata(resolution_status=value)


def test_action_vocabulary() -> None:
    expected = {
        "manual_entry", "manual_marks", "rescan_needed", "cannot_route",
        "mixed_assignment", "evidence_filed", "dismissed_duplicate", "other",
    }
    assert SCAN_RESOLUTION_ACTIONS == expected
    assert all(is_scan_resolution_action(value) for value in expected)
    for value in ("archive", "archived", "delete", "move_to_trash", ""):
        assert not is_scan_resolution_action(value)
        with pytest.raises(ScanResolutionMetadataError):
            make_metadata(resolution_action=value)


@pytest.mark.parametrize(
    "field_name",
    ["resolution_id", "failure_id", "module", "class_id", "assignment_id", "student_id"],
)
@pytest.mark.parametrize("value", ["../secret", "classes/foo", r"C:\Users\Teacher", ""])
def test_identifiers_reject_unsafe_values(field_name: str, value: str) -> None:
    with pytest.raises(ScanResolutionMetadataError):
        make_metadata(**{field_name: value})


def test_nullable_identity_fields_are_accepted() -> None:
    metadata = make_metadata(
        module=None, class_id=None, assignment_id=None, student_id=None
    )
    assert validate_scan_resolution_metadata(metadata) is metadata


@pytest.mark.parametrize("value", ["not-a-date", "", "2026/07/11"])
def test_invalid_timestamp_is_rejected(value: str) -> None:
    with pytest.raises(ScanResolutionMetadataError):
        make_metadata(resolved_at=value)


@pytest.mark.parametrize(
    "field_name",
    [
        "failure_metadata_path", "retained_source_path", "review_copy_path",
        "resolution_evidence_path",
    ],
)
@pytest.mark.parametrize(
    "value",
    ["../secret.json", "/scans/review/failure.json", r"C:\Users\Teacher\scan.pdf", "scans/review/../secret.json"],
)
def test_paths_reject_unsafe_values(field_name: str, value: str) -> None:
    with pytest.raises(ScanResolutionMetadataError):
        make_metadata(**{field_name: value})


def test_path_helpers_are_side_effect_free(tmp_path: Path) -> None:
    directory = scan_resolution_metadata_dir(tmp_path)
    path = scan_resolution_metadata_path(tmp_path, "resolution_001")
    assert directory == tmp_path / "scans" / "review" / "resolutions"
    assert path == directory / "resolution_001.json"
    assert not directory.exists()


@pytest.mark.parametrize("resolution_id", ["../secret", "bad/id", "", " bad"])
def test_path_helper_rejects_unsafe_resolution_id(
    tmp_path: Path, resolution_id: str
) -> None:
    with pytest.raises(ScanResolutionMetadataError):
        scan_resolution_metadata_path(tmp_path, resolution_id)


def test_writer_creates_stable_json_and_refuses_overwrite(tmp_path: Path) -> None:
    metadata = make_metadata()
    path = write_scan_resolution_metadata(tmp_path, metadata)
    expected = json.dumps(
        scan_resolution_metadata_to_dict(metadata),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    assert path == (
        tmp_path / "scans" / "review" / "resolutions"
        / "resolution_20260711_001.json"
    )
    assert path.read_text(encoding="utf-8") == expected
    with pytest.raises(ScanResolutionMetadataWriteError, match="already exists"):
        write_scan_resolution_metadata(tmp_path, metadata)
    assert path.read_text(encoding="utf-8") == expected


def test_nullable_fields_serialize_as_null() -> None:
    metadata = make_metadata(
        failure_metadata_path=None, module=None, source_scan_id=None,
        source_sha256=None, source_filename=None, retained_source_path=None,
        review_copy_path=None, resolution_evidence_path=None,
        source_page_number=None, class_id=None, assignment_id=None,
        student_id=None,
    )
    data = scan_resolution_metadata_to_dict(metadata)
    nullable = set(data) - {
        "schema_version", "resolution_id", "failure_id", "resolution_status",
        "resolution_action", "resolved_at", "resolution_message", "module_details",
    }
    assert all(data[key] is None for key in nullable)


@pytest.mark.parametrize("value", [[], "details"])
def test_module_details_must_be_a_dict(value: object) -> None:
    data = scan_resolution_metadata_to_dict(make_metadata())
    data["module_details"] = value
    with pytest.raises(ScanResolutionMetadataError, match="must be a dict"):
        scan_resolution_metadata_from_dict(data)


@pytest.mark.parametrize(
    "details", [{1: "bad key"}, {"bad": object()}, {"bad": float("nan")}]
)
def test_module_details_must_be_json_compatible(details: dict[Any, object]) -> None:
    with pytest.raises(ScanResolutionMetadataError, match="module_details"):
        make_metadata(module_details=details)
