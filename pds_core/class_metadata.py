"""Shared class-level metadata helpers for Paper Data Suite."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.routes import class_metadata_path as _class_metadata_path
from pds_core.school_years import SchoolYearValidationError, validate_school_year

CLASS_METADATA_SCHEMA_VERSION = "1"
CLASS_METADATA_RECORD_TYPE = "class"
_CLASS_METADATA_KEYS = frozenset(
    {
        "schema_version",
        "record_type",
        "class_id",
        "school_year",
        "created_at",
        "updated_at",
        "module_details",
    }
)


class ClassMetadataError(ValueError):
    """Base exception for shared class metadata operations."""


class ClassMetadataReadError(ClassMetadataError):
    """Raised when class metadata cannot be read."""


class ClassMetadataWriteError(ClassMetadataError):
    """Raised when class metadata cannot be written."""


class ClassMetadataValidationError(ClassMetadataError):
    """Raised when class metadata fails validation."""


@dataclass(frozen=True, slots=True)
class ClassMetadata:
    """Validated class-level metadata."""

    class_id: str
    school_year: str
    created_at: datetime
    updated_at: datetime
    module_details: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "class_id",
            _validate_class_id(self.class_id),
        )
        object.__setattr__(
            self,
            "school_year",
            _validate_class_school_year(self.school_year),
        )
        object.__setattr__(
            self,
            "created_at",
            _validate_aware_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _validate_aware_datetime(self.updated_at, "updated_at"),
        )
        _validate_updated_at_order(self.created_at, self.updated_at)
        object.__setattr__(
            self,
            "module_details",
            _validate_module_details(self.module_details),
        )


def class_metadata_path(workspace_root: str | Path, class_id: str) -> Path:
    """Return the canonical class metadata JSON path."""
    return _class_metadata_path(workspace_root, class_id)


def _validate_class_id(value: object) -> str:
    if not isinstance(value, str):
        raise ClassMetadataValidationError("class_id must be a string.")
    try:
        return validate_identifier(value, "class_id")
    except IdentifierValidationError as error:
        raise ClassMetadataValidationError(str(error)) from error


def _validate_class_school_year(value: object) -> str:
    try:
        return validate_school_year(value)
    except SchoolYearValidationError as error:
        raise ClassMetadataValidationError(str(error)) from error


def _validate_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ClassMetadataValidationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ClassMetadataValidationError(f"{field_name} must be timezone-aware.")
    return value


def _datetime_from_json(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ClassMetadataValidationError(
            f"{field_name} must be an ISO datetime string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ClassMetadataValidationError(
            f"{field_name} must be a valid ISO datetime string."
        ) from error
    return _validate_aware_datetime(parsed, field_name)


def _validate_updated_at_order(created_at: datetime, updated_at: datetime) -> None:
    if updated_at < created_at:
        raise ClassMetadataValidationError(
            "updated_at must not be earlier than created_at."
        )


def _validate_module_details(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ClassMetadataValidationError("module_details must be an object.")
    if any(not isinstance(key, str) for key in value):
        raise ClassMetadataValidationError("module_details keys must be strings.")
    return MappingProxyType(dict(cast(Mapping[str, object], value)))


def _metadata_to_dict(metadata: ClassMetadata) -> dict[str, object]:
    return {
        "schema_version": CLASS_METADATA_SCHEMA_VERSION,
        "record_type": CLASS_METADATA_RECORD_TYPE,
        "class_id": metadata.class_id,
        "school_year": metadata.school_year,
        "created_at": metadata.created_at.isoformat(),
        "updated_at": metadata.updated_at.isoformat(),
        "module_details": dict(metadata.module_details),
    }


def validate_class_metadata(data: Mapping[str, object]) -> ClassMetadata:
    """Validate a class metadata JSON object."""
    if not isinstance(data, Mapping):
        raise ClassMetadataValidationError("class metadata must be an object.")
    if any(not isinstance(key, str) for key in data):
        raise ClassMetadataValidationError("class metadata keys must be strings.")

    metadata_data = data
    unknown_keys = sorted(metadata_data.keys() - _CLASS_METADATA_KEYS)
    if unknown_keys:
        unknown = ", ".join(unknown_keys)
        raise ClassMetadataValidationError(
            f"class metadata contains unknown key(s): {unknown}."
        )

    missing_keys = sorted(_CLASS_METADATA_KEYS - metadata_data.keys())
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise ClassMetadataValidationError(
            f"class metadata is missing required key(s): {missing}."
        )

    if metadata_data["schema_version"] != CLASS_METADATA_SCHEMA_VERSION:
        raise ClassMetadataValidationError("schema_version must be '1'.")
    if metadata_data["record_type"] != CLASS_METADATA_RECORD_TYPE:
        raise ClassMetadataValidationError("record_type must be 'class'.")

    return ClassMetadata(
        class_id=metadata_data["class_id"],  # type: ignore[arg-type]
        school_year=metadata_data["school_year"],  # type: ignore[arg-type]
        created_at=_datetime_from_json(metadata_data["created_at"], "created_at"),
        updated_at=_datetime_from_json(metadata_data["updated_at"], "updated_at"),
        module_details=metadata_data["module_details"],  # type: ignore[arg-type]
    )


def load_class_metadata(path: str | Path) -> ClassMetadata:
    """Load and validate class metadata from a UTF-8 JSON file."""
    source_path = Path(path)
    try:
        with source_path.open(encoding="utf-8") as metadata_file:
            data = json.load(metadata_file)
    except json.JSONDecodeError as error:
        raise ClassMetadataReadError(
            f"Could not read class metadata {source_path}: invalid JSON: {error}"
        ) from error
    except (OSError, UnicodeError) as error:
        raise ClassMetadataReadError(
            f"Could not read class metadata {source_path}: {error}"
        ) from error

    if not isinstance(data, Mapping):
        raise ClassMetadataValidationError("class metadata must be an object.")

    return validate_class_metadata(cast(Mapping[str, object], data))


def write_class_metadata(
    path: str | Path,
    metadata: ClassMetadata,
    *,
    overwrite: bool = False,
) -> None:
    """Atomically write class metadata as UTF-8 JSON."""
    target_path = Path(path)
    target_dir = target_path.parent
    if target_path.exists() and not overwrite:
        raise ClassMetadataWriteError(
            f"Could not write class metadata {target_path}: target file already exists"
        )

    validated = validate_class_metadata(_metadata_to_dict(metadata))
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            _metadata_to_dict(validated),
            indent=2,
            sort_keys=True,
        ) + "\n"
    except (OSError, TypeError, ValueError) as error:
        raise ClassMetadataWriteError(
            f"Could not prepare class metadata for {target_path}: {error}"
        ) from error

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=target_dir,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
        ) as metadata_file:
            temp_path = Path(metadata_file.name)
            metadata_file.write(content)
            metadata_file.flush()
            os.fsync(metadata_file.fileno())

        os.replace(temp_path, target_path)
        temp_path = None
    except (OSError, UnicodeError) as error:
        raise ClassMetadataWriteError(
            f"Could not write class metadata {target_path}: {error}"
        ) from error
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def create_class_metadata(
    class_id: str,
    school_year: str,
    *,
    created_at: datetime,
    updated_at: datetime | None = None,
    module_details: Mapping[str, object] | None = None,
) -> ClassMetadata:
    """Create validated class metadata for a new class record."""
    return ClassMetadata(
        class_id=class_id,
        school_year=school_year,
        created_at=created_at,
        updated_at=created_at if updated_at is None else updated_at,
        module_details={} if module_details is None else module_details,
    )


def load_class_metadata_for_class(
    workspace_root: str | Path,
    class_id: str,
) -> ClassMetadata:
    """Load metadata from the canonical class folder path."""
    expected_class_id = _validate_class_id(class_id)
    metadata = load_class_metadata(class_metadata_path(workspace_root, expected_class_id))
    if metadata.class_id != expected_class_id:
        raise ClassMetadataValidationError(
            "class metadata class_id does not match class folder."
        )
    return metadata


def write_class_metadata_for_class(
    workspace_root: str | Path,
    metadata: ClassMetadata,
    *,
    overwrite: bool = False,
) -> Path:
    """Write metadata to the canonical class folder path."""
    validated = validate_class_metadata(_metadata_to_dict(metadata))
    path = class_metadata_path(workspace_root, validated.class_id)
    write_class_metadata(path, validated, overwrite=overwrite)
    return path
