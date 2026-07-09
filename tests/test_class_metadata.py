"""Tests for shared class metadata helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from pds_core.class_metadata import (
    ClassMetadata,
    ClassMetadataReadError,
    ClassMetadataValidationError,
    ClassMetadataWriteError,
    class_metadata_path,
    create_class_metadata,
    load_class_metadata,
    load_class_metadata_for_class,
    validate_class_metadata,
    write_class_metadata,
    write_class_metadata_for_class,
)

CREATED_AT = datetime(2026, 7, 9, 13, 0, tzinfo=timezone(timedelta(hours=-4)))
UPDATED_AT = datetime(2026, 7, 9, 14, 0, tzinfo=timezone(timedelta(hours=-4)))


def metadata_dict(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": "1",
        "record_type": "class",
        "class_id": "english10_p2",
        "school_year": "2026-2027",
        "created_at": CREATED_AT.isoformat(),
        "updated_at": UPDATED_AT.isoformat(),
        "module_details": {},
    }
    data.update(overrides)
    return data


def test_validate_class_metadata_accepts_valid_metadata() -> None:
    metadata = validate_class_metadata(metadata_dict())

    assert isinstance(metadata, ClassMetadata)
    assert metadata.class_id == "english10_p2"
    assert metadata.school_year == "2026-2027"
    assert metadata.created_at == CREATED_AT
    assert metadata.updated_at == UPDATED_AT
    assert metadata.module_details == {}


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("schema_version", "2"),
        ("record_type", "student"),
        ("class_id", "english 10"),
        ("school_year", ""),
        ("school_year", "2026"),
        ("school_year", "2026-26"),
        ("school_year", "2026-2028"),
        ("created_at", datetime(2026, 7, 9, 13, 0).isoformat()),
        ("updated_at", datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc).isoformat()),
        ("module_details", []),
    ],
)
def test_validate_class_metadata_rejects_invalid_fields(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(ClassMetadataValidationError, match=field_name):
        validate_class_metadata(metadata_dict(**{field_name: value}))


def test_validate_class_metadata_rejects_missing_required_field() -> None:
    data = metadata_dict()
    del data["school_year"]

    with pytest.raises(ClassMetadataValidationError, match="school_year"):
        validate_class_metadata(data)


def test_validate_class_metadata_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ClassMetadataValidationError, match="unknown"):
        validate_class_metadata(metadata_dict(extra=True))


def test_validate_class_metadata_rejects_non_object_data() -> None:
    with pytest.raises(ClassMetadataValidationError, match="object"):
        validate_class_metadata(cast(Any, []))


def test_create_class_metadata_defaults_updated_at_and_module_details() -> None:
    metadata = create_class_metadata(
        "english10_p2",
        "2026-2027",
        created_at=CREATED_AT,
    )

    assert metadata.updated_at == CREATED_AT
    assert metadata.module_details == {}


def test_class_metadata_path_uses_canonical_route(tmp_path: Path) -> None:
    assert class_metadata_path(tmp_path, "english10_p2") == (
        tmp_path / "classes" / "english10_p2" / "class.json"
    )


def test_write_and_load_class_metadata_round_trips(tmp_path: Path) -> None:
    metadata = create_class_metadata(
        "english10_p2",
        "2026-2027",
        created_at=CREATED_AT,
        updated_at=UPDATED_AT,
        module_details={"source": "quillan"},
    )
    path = tmp_path / "classes" / "english10_p2" / "class.json"

    write_class_metadata(path, metadata)
    loaded = load_class_metadata(path)

    assert loaded == metadata
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": "1",
        "record_type": "class",
        "class_id": "english10_p2",
        "school_year": "2026-2027",
        "created_at": CREATED_AT.isoformat(),
        "updated_at": UPDATED_AT.isoformat(),
        "module_details": {"source": "quillan"},
    }
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_write_class_metadata_rejects_overwrite_by_default(tmp_path: Path) -> None:
    metadata = create_class_metadata(
        "english10_p2",
        "2026-2027",
        created_at=CREATED_AT,
    )
    path = tmp_path / "class.json"
    write_class_metadata(path, metadata)

    with pytest.raises(ClassMetadataWriteError, match="already exists"):
        write_class_metadata(path, metadata)

    replacement = create_class_metadata(
        "english10_p2",
        "2027-2028",
        created_at=CREATED_AT,
    )
    write_class_metadata(path, replacement, overwrite=True)

    assert load_class_metadata(path).school_year == "2027-2028"


@pytest.mark.parametrize(
    "raw_content",
    [
        "{not json}",
        "[]",
    ],
)
def test_load_class_metadata_rejects_malformed_files(
    tmp_path: Path,
    raw_content: str,
) -> None:
    path = tmp_path / "class.json"
    path.write_text(raw_content, encoding="utf-8")

    with pytest.raises((ClassMetadataReadError, ClassMetadataValidationError)):
        load_class_metadata(path)


def test_load_class_metadata_rejects_invalid_metadata(tmp_path: Path) -> None:
    path = tmp_path / "class.json"
    path.write_text(json.dumps(metadata_dict(school_year="2026-2028")), encoding="utf-8")

    with pytest.raises(ClassMetadataValidationError, match="school_year"):
        load_class_metadata(path)


def test_canonical_class_helpers_write_and_load_metadata(tmp_path: Path) -> None:
    metadata = create_class_metadata(
        "english10_p2",
        "2026-2027",
        created_at=CREATED_AT,
    )

    path = write_class_metadata_for_class(tmp_path, metadata)
    loaded = load_class_metadata_for_class(tmp_path, "english10_p2")

    assert path == class_metadata_path(tmp_path, "english10_p2")
    assert loaded == metadata


def test_load_class_metadata_for_class_rejects_mismatched_class_id(
    tmp_path: Path,
) -> None:
    metadata = create_class_metadata(
        "english10_p3",
        "2026-2027",
        created_at=CREATED_AT,
    )
    path = class_metadata_path(tmp_path, "english10_p2")
    write_class_metadata(path, metadata)

    with pytest.raises(ClassMetadataValidationError, match="does not match"):
        load_class_metadata_for_class(tmp_path, "english10_p2")
