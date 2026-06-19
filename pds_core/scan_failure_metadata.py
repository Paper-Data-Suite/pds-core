"""Shared routing failure metadata helpers for active scans."""

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


ROUTING_FAILURE_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "assignment_unknown",
        "class_unknown",
        "evidence_write_failed",
        "identifier_invalid",
        "module_unsupported",
        "page_conflict",
        "payload_invalid",
        "payload_missing",
        "payload_schema_unsupported",
        "payload_unreadable",
        "processing_error",
        "route_ambiguous",
        "route_mismatch",
        "source_missing",
        "source_retention_failed",
        "source_type_unsupported",
        "source_unreadable",
        "student_unknown",
    }
)

_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Fa-f]{64}$")
_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "assignment_id",
        "class_id",
        "created_at",
        "detected_payload",
        "failure_category",
        "failure_id",
        "failure_message",
        "module",
        "module_details",
        "payload_page_number",
        "retained_source_path",
        "review_copy_path",
        "schema_version",
        "scope",
        "source_filename",
        "source_page_number",
        "source_scan_id",
        "source_sha256",
        "stage",
        "student_id",
    }
)


class RoutingFailureMetadataError(ValueError):
    """Raised when routing failure metadata is invalid."""


class RoutingFailureMetadataWriteError(RuntimeError):
    """Raised when routing failure metadata cannot be written safely."""


@dataclass(frozen=True, slots=True)
class RoutingFailureMetadata:
    """One shared active-scan routing failure record."""

    schema_version: str
    failure_id: str
    scope: str
    stage: str
    created_at: str
    failure_category: str
    failure_message: str
    source_filename: str
    module_details: dict[str, object]
    module: str | None = None
    source_scan_id: str | None = None
    source_sha256: str | None = None
    retained_source_path: str | None = None
    review_copy_path: str | None = None
    source_page_number: int | None = None
    detected_payload: str | None = None
    payload_page_number: int | None = None
    class_id: str | None = None
    assignment_id: str | None = None
    student_id: str | None = None

    def __post_init__(self) -> None:
        _validate_metadata_fields(self)


def is_routing_failure_category(value: object) -> bool:
    """Return whether a value is a shared routing failure category."""
    return isinstance(value, str) and value in ROUTING_FAILURE_CATEGORIES


def validate_routing_failure_metadata(
    metadata: RoutingFailureMetadata | Mapping[str, object],
) -> RoutingFailureMetadata:
    """Validate and return shared routing failure metadata."""
    if isinstance(metadata, RoutingFailureMetadata):
        _validate_metadata_fields(metadata)
        return metadata
    if not isinstance(metadata, Mapping):
        raise RoutingFailureMetadataError(
            "routing failure metadata must be a model or mapping."
        )
    return routing_failure_metadata_from_dict(metadata)


def routing_failure_metadata_to_dict(
    metadata: RoutingFailureMetadata,
) -> dict[str, object]:
    """Convert validated routing failure metadata to a stable JSON mapping."""
    validated = validate_routing_failure_metadata(metadata)
    return {
        "schema_version": validated.schema_version,
        "failure_id": validated.failure_id,
        "scope": validated.scope,
        "stage": validated.stage,
        "created_at": validated.created_at,
        "failure_category": validated.failure_category,
        "failure_message": validated.failure_message,
        "source_filename": validated.source_filename,
        "module_details": dict(validated.module_details),
        "module": validated.module,
        "source_scan_id": validated.source_scan_id,
        "source_sha256": validated.source_sha256,
        "retained_source_path": validated.retained_source_path,
        "review_copy_path": validated.review_copy_path,
        "source_page_number": validated.source_page_number,
        "detected_payload": validated.detected_payload,
        "payload_page_number": validated.payload_page_number,
        "class_id": validated.class_id,
        "assignment_id": validated.assignment_id,
        "student_id": validated.student_id,
    }


def routing_failure_metadata_from_dict(
    data: Mapping[str, object],
) -> RoutingFailureMetadata:
    """Build validated routing failure metadata from an exact schema mapping."""
    if any(not isinstance(key, str) for key in data):
        raise RoutingFailureMetadataError(
            "routing failure metadata keys must be strings."
        )

    keys = frozenset(data.keys())
    missing_keys = sorted(_METADATA_KEYS - keys)
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise RoutingFailureMetadataError(
            f"routing failure metadata is missing required key(s): {missing}."
        )
    extra_keys = sorted(keys - _METADATA_KEYS)
    if extra_keys:
        extra = ", ".join(extra_keys)
        raise RoutingFailureMetadataError(
            f"routing failure metadata contains unknown key(s): {extra}."
        )

    values = data
    module_details = values["module_details"]
    if not isinstance(module_details, dict):
        raise RoutingFailureMetadataError("module_details must be a dict.")

    return RoutingFailureMetadata(
        schema_version=values["schema_version"],  # type: ignore[arg-type]
        failure_id=values["failure_id"],  # type: ignore[arg-type]
        scope=values["scope"],  # type: ignore[arg-type]
        stage=values["stage"],  # type: ignore[arg-type]
        created_at=values["created_at"],  # type: ignore[arg-type]
        failure_category=values["failure_category"],  # type: ignore[arg-type]
        failure_message=values["failure_message"],  # type: ignore[arg-type]
        source_filename=values["source_filename"],  # type: ignore[arg-type]
        module_details=module_details,
        module=values["module"],  # type: ignore[arg-type]
        source_scan_id=values["source_scan_id"],  # type: ignore[arg-type]
        source_sha256=values["source_sha256"],  # type: ignore[arg-type]
        retained_source_path=values["retained_source_path"],  # type: ignore[arg-type]
        review_copy_path=values["review_copy_path"],  # type: ignore[arg-type]
        source_page_number=values["source_page_number"],  # type: ignore[arg-type]
        detected_payload=values["detected_payload"],  # type: ignore[arg-type]
        payload_page_number=values["payload_page_number"],  # type: ignore[arg-type]
        class_id=values["class_id"],  # type: ignore[arg-type]
        assignment_id=values["assignment_id"],  # type: ignore[arg-type]
        student_id=values["student_id"],  # type: ignore[arg-type]
    )


def routing_failure_metadata_path(
    root: str | Path,
    failure_id: str,
) -> Path:
    """Return the canonical review JSON path for a routing failure."""
    safe_failure_id = _validate_identifier(failure_id, "failure_id")
    return routing_review_dir(root) / f"{safe_failure_id}.json"


def write_routing_failure_metadata(
    root: str | Path,
    metadata: RoutingFailureMetadata,
) -> Path:
    """Validate and exclusively create one UTF-8 routing failure JSON file."""
    validated = validate_routing_failure_metadata(metadata)
    path = routing_failure_metadata_path(root, validated.failure_id)
    content = json.dumps(
        routing_failure_metadata_to_dict(validated),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="") as metadata_file:
            metadata_file.write(content)
    except FileExistsError as error:
        raise RoutingFailureMetadataWriteError(
            f"Routing failure metadata already exists: {path}"
        ) from error
    except (OSError, UnicodeError) as error:
        raise RoutingFailureMetadataWriteError(
            f"Could not write routing failure metadata {path}: {error}"
        ) from error

    return path


def _validate_metadata_fields(metadata: RoutingFailureMetadata) -> None:
    if metadata.schema_version != "1":
        raise RoutingFailureMetadataError('schema_version must be "1".')

    _validate_identifier(metadata.failure_id, "failure_id")
    if metadata.scope not in {"scan", "page"}:
        raise RoutingFailureMetadataError('scope must be "scan" or "page".')
    _validate_identifier(metadata.stage, "stage")
    _validate_iso_timestamp(metadata.created_at)

    if not is_routing_failure_category(metadata.failure_category):
        raise RoutingFailureMetadataError(
            "failure_category must be a shared routing failure category."
        )
    _validate_non_empty_string(metadata.failure_message, "failure_message")
    _validate_filename(metadata.source_filename, "source_filename")

    if not isinstance(metadata.module_details, dict):
        raise RoutingFailureMetadataError("module_details must be a dict.")
    if any(not isinstance(key, str) for key in metadata.module_details):
        raise RoutingFailureMetadataError(
            "module_details keys must be strings."
        )
    try:
        json.dumps(metadata.module_details, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise RoutingFailureMetadataError(
            "module_details must be JSON-serializable."
        ) from error

    for field_name in ("module", "source_scan_id"):
        value = getattr(metadata, field_name)
        if value is not None:
            _validate_identifier(value, field_name)

    for field_name in ("class_id", "assignment_id", "student_id"):
        value = getattr(metadata, field_name)
        if value is not None:
            _validate_identifier(value, field_name)

    if metadata.source_sha256 is not None and (
        not isinstance(metadata.source_sha256, str)
        or not _SHA256_PATTERN.fullmatch(metadata.source_sha256)
    ):
        raise RoutingFailureMetadataError(
            "source_sha256 must be a full 64-character SHA-256 hexadecimal "
            "string."
        )

    for field_name in ("retained_source_path", "review_copy_path"):
        value = getattr(metadata, field_name)
        if value is not None:
            _validate_workspace_relative_path(value, field_name)

    for field_name in ("source_page_number", "payload_page_number"):
        value = getattr(metadata, field_name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 1
        ):
            raise RoutingFailureMetadataError(
                f"{field_name} must be a positive integer."
            )

    if metadata.detected_payload is not None and not isinstance(
        metadata.detected_payload, str
    ):
        raise RoutingFailureMetadataError(
            "detected_payload must be a string or null."
        )


def _validate_identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(value, field_name)  # type: ignore[arg-type]
    except IdentifierValidationError as error:
        raise RoutingFailureMetadataError(str(error)) from error


def _validate_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RoutingFailureMetadataError(f"{field_name} must be a string.")
    if value == "":
        raise RoutingFailureMetadataError(f"{field_name} must not be empty.")
    if value != value.strip():
        raise RoutingFailureMetadataError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    return value


def _validate_iso_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise RoutingFailureMetadataError(
            "created_at must be an ISO timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RoutingFailureMetadataError(
            "created_at must be a valid ISO timestamp string."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RoutingFailureMetadataError(
            "created_at must include a timezone offset."
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
        raise RoutingFailureMetadataError(
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
        raise RoutingFailureMetadataError(
            f"{field_name} must be relative to the workspace root."
        )
    normalized_parts = path_value.replace("\\", "/").split("/")
    if ".." in normalized_parts or "." in normalized_parts:
        raise RoutingFailureMetadataError(
            f"{field_name} must not contain traversal components."
        )
    if "\x00" in path_value:
        raise RoutingFailureMetadataError(
            f"{field_name} contains an unsafe path character."
        )
    return path_value
