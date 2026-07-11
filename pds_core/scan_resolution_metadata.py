"""Shared resolution metadata helpers for active scan review items."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.scan_routes import routing_review_dir


SCAN_RESOLUTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"resolved", "deferred"}
)
SCAN_RESOLUTION_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "manual_entry",
        "manual_marks",
        "rescan_needed",
        "cannot_route",
        "mixed_assignment",
        "evidence_filed",
        "dismissed_duplicate",
        "other",
    }
)

_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Fa-f]{64}$")
_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "resolution_id",
        "failure_id",
        "failure_metadata_path",
        "resolution_status",
        "resolution_action",
        "resolved_at",
        "resolution_message",
        "module_details",
        "module",
        "source_scan_id",
        "source_sha256",
        "source_filename",
        "retained_source_path",
        "review_copy_path",
        "resolution_evidence_path",
        "source_page_number",
        "class_id",
        "assignment_id",
        "student_id",
    }
)


class ScanResolutionMetadataError(ValueError):
    """Raised when scan resolution metadata is invalid."""


class ScanResolutionMetadataWriteError(RuntimeError):
    """Raised when scan resolution metadata cannot be written safely."""


@dataclass(frozen=True, slots=True)
class ScanResolutionMetadata:
    """One immutable active-scan resolution record."""

    schema_version: str
    resolution_id: str
    failure_id: str
    failure_metadata_path: str | None
    resolution_status: str
    resolution_action: str
    resolved_at: str
    resolution_message: str
    module_details: dict[str, object]
    module: str | None = None
    source_scan_id: str | None = None
    source_sha256: str | None = None
    source_filename: str | None = None
    retained_source_path: str | None = None
    review_copy_path: str | None = None
    resolution_evidence_path: str | None = None
    source_page_number: int | None = None
    class_id: str | None = None
    assignment_id: str | None = None
    student_id: str | None = None

    def __post_init__(self) -> None:
        _validate_metadata_fields(self)


def is_scan_resolution_status(value: object) -> bool:
    """Return whether a value is a shared scan resolution status."""
    return isinstance(value, str) and value in SCAN_RESOLUTION_STATUSES


def is_scan_resolution_action(value: object) -> bool:
    """Return whether a value is a shared scan resolution action."""
    return isinstance(value, str) and value in SCAN_RESOLUTION_ACTIONS


def validate_scan_resolution_metadata(
    metadata: ScanResolutionMetadata | Mapping[str, object],
) -> ScanResolutionMetadata:
    """Validate and return shared scan resolution metadata."""
    if isinstance(metadata, ScanResolutionMetadata):
        _validate_metadata_fields(metadata)
        return metadata
    if not isinstance(metadata, Mapping):
        raise ScanResolutionMetadataError(
            "scan resolution metadata must be a model or mapping."
        )
    return scan_resolution_metadata_from_dict(metadata)


def scan_resolution_metadata_to_dict(
    metadata: ScanResolutionMetadata,
) -> dict[str, object]:
    """Convert validated resolution metadata to a stable JSON mapping."""
    value = validate_scan_resolution_metadata(metadata)
    return {
        "schema_version": value.schema_version,
        "resolution_id": value.resolution_id,
        "failure_id": value.failure_id,
        "failure_metadata_path": value.failure_metadata_path,
        "resolution_status": value.resolution_status,
        "resolution_action": value.resolution_action,
        "resolved_at": value.resolved_at,
        "resolution_message": value.resolution_message,
        "module_details": dict(value.module_details),
        "module": value.module,
        "source_scan_id": value.source_scan_id,
        "source_sha256": value.source_sha256,
        "source_filename": value.source_filename,
        "retained_source_path": value.retained_source_path,
        "review_copy_path": value.review_copy_path,
        "resolution_evidence_path": value.resolution_evidence_path,
        "source_page_number": value.source_page_number,
        "class_id": value.class_id,
        "assignment_id": value.assignment_id,
        "student_id": value.student_id,
    }


def scan_resolution_metadata_from_dict(
    data: Mapping[str, object],
) -> ScanResolutionMetadata:
    """Build validated resolution metadata from an exact schema mapping."""
    if any(not isinstance(key, str) for key in data):
        raise ScanResolutionMetadataError(
            "scan resolution metadata keys must be strings."
        )
    keys = frozenset(data.keys())
    missing_keys = sorted(_METADATA_KEYS - keys)
    if missing_keys:
        raise ScanResolutionMetadataError(
            "scan resolution metadata is missing required key(s): "
            + ", ".join(missing_keys)
            + "."
        )
    extra_keys = sorted(keys - _METADATA_KEYS)
    if extra_keys:
        raise ScanResolutionMetadataError(
            "scan resolution metadata contains unknown key(s): "
            + ", ".join(extra_keys)
            + "."
        )
    module_details = data["module_details"]
    if not isinstance(module_details, dict):
        raise ScanResolutionMetadataError("module_details must be a dict.")
    return ScanResolutionMetadata(
        schema_version=data["schema_version"],  # type: ignore[arg-type]
        resolution_id=data["resolution_id"],  # type: ignore[arg-type]
        failure_id=data["failure_id"],  # type: ignore[arg-type]
        failure_metadata_path=data["failure_metadata_path"],  # type: ignore[arg-type]
        resolution_status=data["resolution_status"],  # type: ignore[arg-type]
        resolution_action=data["resolution_action"],  # type: ignore[arg-type]
        resolved_at=data["resolved_at"],  # type: ignore[arg-type]
        resolution_message=data["resolution_message"],  # type: ignore[arg-type]
        module_details=module_details,
        module=data["module"],  # type: ignore[arg-type]
        source_scan_id=data["source_scan_id"],  # type: ignore[arg-type]
        source_sha256=data["source_sha256"],  # type: ignore[arg-type]
        source_filename=data["source_filename"],  # type: ignore[arg-type]
        retained_source_path=data["retained_source_path"],  # type: ignore[arg-type]
        review_copy_path=data["review_copy_path"],  # type: ignore[arg-type]
        resolution_evidence_path=data["resolution_evidence_path"],  # type: ignore[arg-type]
        source_page_number=data["source_page_number"],  # type: ignore[arg-type]
        class_id=data["class_id"],  # type: ignore[arg-type]
        assignment_id=data["assignment_id"],  # type: ignore[arg-type]
        student_id=data["student_id"],  # type: ignore[arg-type]
    )


def scan_resolution_metadata_dir(root: str | Path) -> Path:
    """Return the shared scan resolution metadata directory."""
    return routing_review_dir(root) / "resolutions"


def scan_resolution_metadata_path(
    root: str | Path, resolution_id: str
) -> Path:
    """Return the canonical JSON path for one resolution record."""
    safe_id = _validate_identifier(resolution_id, "resolution_id")
    return scan_resolution_metadata_dir(root) / f"{safe_id}.json"


def write_scan_resolution_metadata(
    root: str | Path, metadata: ScanResolutionMetadata
) -> Path:
    """Validate and exclusively create one UTF-8 resolution JSON file."""
    validated = validate_scan_resolution_metadata(metadata)
    path = scan_resolution_metadata_path(root, validated.resolution_id)
    content = json.dumps(
        scan_resolution_metadata_to_dict(validated),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="") as metadata_file:
            metadata_file.write(content)
    except FileExistsError as error:
        raise ScanResolutionMetadataWriteError(
            f"Scan resolution metadata already exists: {path}"
        ) from error
    except (OSError, UnicodeError) as error:
        raise ScanResolutionMetadataWriteError(
            f"Could not write scan resolution metadata {path}: {error}"
        ) from error
    return path


def _validate_metadata_fields(metadata: ScanResolutionMetadata) -> None:
    if metadata.schema_version != "1":
        raise ScanResolutionMetadataError('schema_version must be "1".')
    _validate_identifier(metadata.resolution_id, "resolution_id")
    _validate_identifier(metadata.failure_id, "failure_id")
    if not is_scan_resolution_status(metadata.resolution_status):
        raise ScanResolutionMetadataError(
            "resolution_status must be a shared scan resolution status."
        )
    if not is_scan_resolution_action(metadata.resolution_action):
        raise ScanResolutionMetadataError(
            "resolution_action must be a shared scan resolution action."
        )
    _validate_iso_timestamp(metadata.resolved_at)
    _validate_non_empty_string(metadata.resolution_message, "resolution_message")

    if not isinstance(metadata.module_details, dict):
        raise ScanResolutionMetadataError("module_details must be a dict.")
    if any(not isinstance(key, str) for key in metadata.module_details):
        raise ScanResolutionMetadataError("module_details keys must be strings.")
    try:
        json.dumps(metadata.module_details, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ScanResolutionMetadataError(
            "module_details must be JSON-serializable."
        ) from error

    for field_name in (
        "module",
        "source_scan_id",
        "class_id",
        "assignment_id",
        "student_id",
    ):
        value = getattr(metadata, field_name)
        if value is not None:
            _validate_identifier(value, field_name)

    if metadata.source_sha256 is not None and (
        not isinstance(metadata.source_sha256, str)
        or not _SHA256_PATTERN.fullmatch(metadata.source_sha256)
    ):
        raise ScanResolutionMetadataError(
            "source_sha256 must be a full 64-character SHA-256 hexadecimal string."
        )
    if metadata.source_filename is not None:
        _validate_filename(metadata.source_filename, "source_filename")
    for field_name in (
        "failure_metadata_path",
        "retained_source_path",
        "review_copy_path",
        "resolution_evidence_path",
    ):
        value = getattr(metadata, field_name)
        if value is not None:
            _validate_workspace_relative_path(value, field_name)
    value = metadata.source_page_number
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 1
    ):
        raise ScanResolutionMetadataError(
            "source_page_number must be a positive integer."
        )


def _validate_identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(value, field_name)  # type: ignore[arg-type]
    except IdentifierValidationError as error:
        raise ScanResolutionMetadataError(str(error)) from error


def _validate_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ScanResolutionMetadataError(f"{field_name} must be a string.")
    if value == "":
        raise ScanResolutionMetadataError(f"{field_name} must not be empty.")
    if value != value.strip():
        raise ScanResolutionMetadataError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    return value


def _validate_iso_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise ScanResolutionMetadataError(
            "resolved_at must be an ISO timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ScanResolutionMetadataError(
            "resolved_at must be a valid ISO timestamp string."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScanResolutionMetadataError(
            "resolved_at must include a timezone offset."
        )
    return value


def _validate_filename(value: object, field_name: str) -> str:
    filename = _validate_non_empty_string(value, field_name)
    if (
        "\x00" in filename
        or "/" in filename
        or "\\" in filename
        or PureWindowsPath(filename).drive
        or filename in {".", ".."}
    ):
        raise ScanResolutionMetadataError(
            f"{field_name} must be a filename, not a path."
        )
    return filename


def _validate_workspace_relative_path(value: object, field_name: str) -> str:
    path_value = _validate_non_empty_string(value, field_name)
    windows_path = PureWindowsPath(path_value)
    posix_path = PurePosixPath(path_value)
    if (
        windows_path.is_absolute()
        or bool(windows_path.drive)
        or posix_path.is_absolute()
    ):
        raise ScanResolutionMetadataError(
            f"{field_name} must be relative to the workspace root."
        )
    normalized_parts = path_value.replace("\\", "/").split("/")
    if ".." in normalized_parts or "." in normalized_parts:
        raise ScanResolutionMetadataError(
            f"{field_name} must not contain traversal components."
        )
    if "\x00" in path_value:
        raise ScanResolutionMetadataError(
            f"{field_name} contains an unsafe path character."
        )
    return path_value
