"""Append-only version 2 resolution metadata for routing failures."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Final, cast

from pds_core._scan_metadata_utils import (
    DuplicateJsonKeyError,
    FrozenJsonMapping,
    InvalidJsonConstantError,
    JsonValueIsolationError,
    freeze_json_mapping,
    load_strict_json,
    thaw_json_mapping,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.routing_models import (
    JsonValue,
    ModuleRecordRef,
    RouteLocator,
    RoutingModelError,
    module_record_ref_from_dict,
    module_record_ref_to_dict,
    route_locator_from_dict,
    route_locator_to_dict,
    validate_module_record_ref,
    validate_route_locator,
)
from pds_core.scan_failure_metadata import (
    ROUTING_FAILURE_SCHEMA_VERSION,
    RoutingFailureMetadata,
    RoutingFailureMetadataReadError,
    load_routing_failure_metadata,
    validate_routing_failure_metadata,
)
from pds_core.scan_routes import routing_review_dir


SCAN_RESOLUTION_SCHEMA_VERSION: Final[str] = "2"
SCAN_RESOLUTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"resolved", "deferred"}
)
SCAN_RESOLUTION_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "route_selected",
        "route_corrected",
        "evidence_filed",
        "rescan_needed",
        "cannot_route",
        "dismissed_duplicate",
        "deferred",
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
        "source_filename",
        "source_scan_id",
        "source_sha256",
        "retained_source_path",
        "review_copy_path",
        "source_page_number",
        "route_locator",
        "target",
        "resolution_evidence_path",
        "module_details",
    }
)
_PROVENANCE_FIELDS: Final[tuple[str, ...]] = (
    "source_filename",
    "source_scan_id",
    "source_sha256",
    "retained_source_path",
    "review_copy_path",
    "source_page_number",
)
_NO_FINAL_ROUTE_ACTIONS: Final[frozenset[str]] = frozenset(
    {"rescan_needed", "cannot_route", "dismissed_duplicate"}
)
_ROUTED_ACTIONS: Final[frozenset[str]] = frozenset(
    {"route_selected", "route_corrected"}
)
_EMPTY_DETAILS: Final[Mapping[str, JsonValue]] = MappingProxyType({})


class ScanResolutionMetadataError(ValueError):
    """Raised when resolution metadata is invalid."""


class ScanResolutionMetadataWriteError(RuntimeError):
    """Raised when a resolution cannot be appended safely."""


class ScanResolutionMetadataReadError(RuntimeError):
    """Raised when persisted resolution metadata cannot be read."""


class ScanResolutionMetadataNotFoundError(ScanResolutionMetadataReadError):
    """Raised when the canonical resolution file is absent."""


class ScanResolutionMetadataIntegrityError(ScanResolutionMetadataReadError):
    """Raised when stored resolution identity differs from requested identity."""


@dataclass(frozen=True, slots=True, init=False)
class ScanResolutionMetadata:
    """One immutable resolution event linked to a routing failure."""

    schema_version: str
    resolution_id: str
    failure_id: str
    failure_metadata_path: str
    resolution_status: str
    resolution_action: str
    resolved_at: str
    resolution_message: str
    source_filename: str
    source_scan_id: str | None
    source_sha256: str | None
    retained_source_path: str | None
    review_copy_path: str | None
    source_page_number: int | None
    route_locator: RouteLocator | None
    target: ModuleRecordRef | None
    resolution_evidence_path: str | None
    _module_details: FrozenJsonMapping = field(repr=False, compare=True)

    def __init__(
        self,
        schema_version: str,
        resolution_id: str,
        failure_id: str,
        failure_metadata_path: str,
        resolution_status: str,
        resolution_action: str,
        resolved_at: str,
        resolution_message: str,
        source_filename: str,
        source_scan_id: str | None,
        source_sha256: str | None,
        retained_source_path: str | None,
        review_copy_path: str | None,
        source_page_number: int | None,
        route_locator: RouteLocator | None,
        target: ModuleRecordRef | None,
        resolution_evidence_path: str | None,
        module_details: Mapping[str, JsonValue] = _EMPTY_DETAILS,
    ) -> None:
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "resolution_id", resolution_id)
        object.__setattr__(self, "failure_id", failure_id)
        object.__setattr__(self, "failure_metadata_path", failure_metadata_path)
        object.__setattr__(self, "resolution_status", resolution_status)
        object.__setattr__(self, "resolution_action", resolution_action)
        object.__setattr__(self, "resolved_at", resolved_at)
        object.__setattr__(self, "resolution_message", resolution_message)
        object.__setattr__(self, "source_filename", source_filename)
        object.__setattr__(self, "source_scan_id", source_scan_id)
        object.__setattr__(self, "source_sha256", source_sha256)
        object.__setattr__(self, "retained_source_path", retained_source_path)
        object.__setattr__(self, "review_copy_path", review_copy_path)
        object.__setattr__(self, "source_page_number", source_page_number)
        object.__setattr__(self, "route_locator", route_locator)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "resolution_evidence_path", resolution_evidence_path)
        _validate_metadata_fields(self)
        try:
            frozen_details = freeze_json_mapping(module_details, "module_details")
        except JsonValueIsolationError as error:
            raise ScanResolutionMetadataError(str(error)) from error
        object.__setattr__(self, "_module_details", frozen_details)

    @property
    def module_details(self) -> dict[str, JsonValue]:
        """Return an isolated JSON-native copy of module-owned details."""
        return thaw_json_mapping(self._module_details)


def is_scan_resolution_status(value: object) -> bool:
    """Return whether a value is a shared resolution status."""
    return isinstance(value, str) and value in SCAN_RESOLUTION_STATUSES


def is_scan_resolution_action(value: object) -> bool:
    """Return whether a value is a shared resolution action."""
    return isinstance(value, str) and value in SCAN_RESOLUTION_ACTIONS


def validate_scan_resolution_metadata(
    metadata: ScanResolutionMetadata | Mapping[str, object],
) -> ScanResolutionMetadata:
    """Validate and return exact version 2 resolution metadata."""
    if isinstance(metadata, ScanResolutionMetadata):
        _validate_metadata_fields(metadata)
        try:
            thaw_json_mapping(metadata._module_details)
        except JsonValueIsolationError as error:
            raise ScanResolutionMetadataError(str(error)) from error
        return metadata
    if not isinstance(metadata, Mapping):
        raise ScanResolutionMetadataError(
            "scan resolution metadata must be a model or mapping."
        )
    return scan_resolution_metadata_from_dict(metadata)


def scan_resolution_metadata_to_dict(
    metadata: ScanResolutionMetadata,
) -> dict[str, object]:
    """Convert validated metadata to its exact 18-key JSON shape."""
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
        "source_filename": value.source_filename,
        "source_scan_id": value.source_scan_id,
        "source_sha256": value.source_sha256,
        "retained_source_path": value.retained_source_path,
        "review_copy_path": value.review_copy_path,
        "source_page_number": value.source_page_number,
        "route_locator": (
            None
            if value.route_locator is None
            else route_locator_to_dict(value.route_locator)
        ),
        "target": (
            None if value.target is None else module_record_ref_to_dict(value.target)
        ),
        "resolution_evidence_path": value.resolution_evidence_path,
        "module_details": value.module_details,
    }


def scan_resolution_metadata_from_dict(data: object) -> ScanResolutionMetadata:
    """Build metadata from an exact version 2 schema mapping."""
    mapping = _require_exact_mapping(data)
    route_data = mapping["route_locator"]
    target_data = mapping["target"]
    details = mapping["module_details"]
    if not isinstance(details, Mapping):
        raise ScanResolutionMetadataError("module_details must be a mapping.")
    try:
        route_locator = (
            None if route_data is None else route_locator_from_dict(route_data)
        )
        target = None if target_data is None else module_record_ref_from_dict(target_data)
        return ScanResolutionMetadata(
            schema_version=_require_string(mapping["schema_version"], "schema_version"),
            resolution_id=_require_string(mapping["resolution_id"], "resolution_id"),
            failure_id=_require_string(mapping["failure_id"], "failure_id"),
            failure_metadata_path=_require_string(
                mapping["failure_metadata_path"], "failure_metadata_path"
            ),
            resolution_status=_require_string(
                mapping["resolution_status"], "resolution_status"
            ),
            resolution_action=_require_string(
                mapping["resolution_action"], "resolution_action"
            ),
            resolved_at=_require_string(mapping["resolved_at"], "resolved_at"),
            resolution_message=_require_string(
                mapping["resolution_message"], "resolution_message"
            ),
            source_filename=_require_string(
                mapping["source_filename"], "source_filename"
            ),
            source_scan_id=_optional_string(
                mapping["source_scan_id"], "source_scan_id"
            ),
            source_sha256=_optional_string(
                mapping["source_sha256"], "source_sha256"
            ),
            retained_source_path=_optional_string(
                mapping["retained_source_path"], "retained_source_path"
            ),
            review_copy_path=_optional_string(
                mapping["review_copy_path"], "review_copy_path"
            ),
            source_page_number=_optional_int(
                mapping["source_page_number"], "source_page_number"
            ),
            route_locator=route_locator,
            target=target,
            resolution_evidence_path=_optional_string(
                mapping["resolution_evidence_path"], "resolution_evidence_path"
            ),
            module_details=cast(Mapping[str, JsonValue], details),
        )
    except RoutingModelError as error:
        raise ScanResolutionMetadataError(
            f"routing identity is invalid: {error}"
        ) from error


def create_scan_resolution_metadata(
    failure: RoutingFailureMetadata,
    *,
    resolution_id: str,
    resolution_status: str,
    resolution_action: str,
    resolved_at: str,
    resolution_message: str,
    route_locator: RouteLocator | None = None,
    target: ModuleRecordRef | None = None,
    resolution_evidence_path: str | None = None,
    module_details: Mapping[str, JsonValue] | None = None,
) -> ScanResolutionMetadata:
    """Build a resolution event while leaving its failure unchanged."""
    if not isinstance(failure, RoutingFailureMetadata):
        raise ScanResolutionMetadataError(
            "failure must be a RoutingFailureMetadata."
        )
    try:
        validated_failure = validate_routing_failure_metadata(failure)
    except ValueError as error:
        raise ScanResolutionMetadataError(f"failure is invalid: {error}") from error
    if validated_failure.schema_version != ROUTING_FAILURE_SCHEMA_VERSION:
        raise ScanResolutionMetadataError("failure must use schema version 2.")
    metadata = ScanResolutionMetadata(
        schema_version=SCAN_RESOLUTION_SCHEMA_VERSION,
        resolution_id=resolution_id,
        failure_id=validated_failure.failure_id,
        failure_metadata_path=_canonical_failure_path(validated_failure.failure_id),
        resolution_status=resolution_status,
        resolution_action=resolution_action,
        resolved_at=resolved_at,
        resolution_message=resolution_message,
        source_filename=validated_failure.source_filename,
        source_scan_id=validated_failure.source_scan_id,
        source_sha256=validated_failure.source_sha256,
        retained_source_path=validated_failure.retained_source_path,
        review_copy_path=validated_failure.review_copy_path,
        source_page_number=validated_failure.source_page_number,
        route_locator=route_locator,
        target=target,
        resolution_evidence_path=resolution_evidence_path,
        module_details={} if module_details is None else module_details,
    )
    if _parse_timestamp(metadata.resolved_at, "resolved_at") < _parse_timestamp(
        validated_failure.created_at, "created_at"
    ):
        raise ScanResolutionMetadataError(
            "resolved_at must not predate the linked failure."
        )
    return metadata


def scan_resolution_metadata_dir(root: str | Path) -> Path:
    """Return the append-only resolution directory without creating it."""
    return routing_review_dir(root) / "resolutions"


def scan_resolution_metadata_path(root: str | Path, resolution_id: str) -> Path:
    """Return one canonical resolution path without creating it."""
    safe_id = _validate_identifier(resolution_id, "resolution_id")
    return scan_resolution_metadata_dir(root) / f"{safe_id}.json"


def write_scan_resolution_metadata(
    root: str | Path, metadata: ScanResolutionMetadata
) -> Path:
    """Verify linkage, then exclusively append one resolution record."""
    if not isinstance(metadata, ScanResolutionMetadata):
        raise ScanResolutionMetadataError(
            "metadata must be a ScanResolutionMetadata."
        )
    validated = validate_scan_resolution_metadata(metadata)
    try:
        failure = load_routing_failure_metadata(root, validated.failure_id)
    except RoutingFailureMetadataReadError as error:
        raise ScanResolutionMetadataReadError(
            f"Could not load linked routing failure: {error}"
        ) from error
    _verify_failure_link(validated, failure)

    path = scan_resolution_metadata_path(root, validated.resolution_id)
    content = json.dumps(
        scan_resolution_metadata_to_dict(validated),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ScanResolutionMetadataWriteError(
            f"Could not create resolution directory {path.parent}: {error}"
        ) from error

    created = False
    try:
        with path.open("x", encoding="utf-8", newline="") as output:
            created = True
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        if not created:
            raise ScanResolutionMetadataWriteError(
                f"Scan resolution metadata already exists: {path}"
            ) from error
        _remove_incomplete_file(path)
        raise ScanResolutionMetadataWriteError(
            f"Could not write scan resolution metadata {path}: {error}"
        ) from error
    except (OSError, UnicodeError) as error:
        if created:
            _remove_incomplete_file(path)
        raise ScanResolutionMetadataWriteError(
            f"Could not write scan resolution metadata {path}: {error}"
        ) from error
    return path


def load_scan_resolution_metadata(
    root: str | Path, resolution_id: str
) -> ScanResolutionMetadata:
    """Load exact version 2 resolution metadata from one canonical path."""
    requested_id = _validate_identifier(resolution_id, "resolution_id")
    path = scan_resolution_metadata_path(root, requested_id)
    try:
        data = load_strict_json(path)
    except FileNotFoundError as error:
        raise ScanResolutionMetadataNotFoundError(
            f"Scan resolution metadata not found at canonical path: {path}"
        ) from error
    except (
        json.JSONDecodeError,
        UnicodeError,
        DuplicateJsonKeyError,
        InvalidJsonConstantError,
    ) as error:
        raise ScanResolutionMetadataReadError(
            f"Scan resolution metadata contains invalid JSON at {path}: {error}"
        ) from error
    except OSError as error:
        raise ScanResolutionMetadataReadError(
            f"Could not read scan resolution metadata {path}: {error}"
        ) from error
    if not isinstance(data, dict):
        raise ScanResolutionMetadataReadError(
            f"Scan resolution metadata must be a JSON object at {path}."
        )
    try:
        metadata = scan_resolution_metadata_from_dict(data)
    except ScanResolutionMetadataError as error:
        raise ScanResolutionMetadataReadError(
            f"Scan resolution metadata is invalid at {path}: {error}"
        ) from error
    if metadata.resolution_id != requested_id:
        raise ScanResolutionMetadataIntegrityError(
            f"Stored resolution_id does not match requested ID at {path}."
        )
    return metadata


def _validate_metadata_fields(metadata: ScanResolutionMetadata) -> None:
    if metadata.schema_version != SCAN_RESOLUTION_SCHEMA_VERSION:
        raise ScanResolutionMetadataError(
            f'schema_version must be "{SCAN_RESOLUTION_SCHEMA_VERSION}".'
        )
    _validate_identifier(metadata.resolution_id, "resolution_id")
    _validate_identifier(metadata.failure_id, "failure_id")
    expected_failure_path = _canonical_failure_path(metadata.failure_id)
    if metadata.failure_metadata_path != expected_failure_path:
        raise ScanResolutionMetadataError(
            f"failure_metadata_path must equal {expected_failure_path!r}."
        )
    _validate_workspace_relative_path(
        metadata.failure_metadata_path, "failure_metadata_path"
    )
    if not is_scan_resolution_status(metadata.resolution_status):
        raise ScanResolutionMetadataError(
            "resolution_status must be a shared scan resolution status."
        )
    if not is_scan_resolution_action(metadata.resolution_action):
        raise ScanResolutionMetadataError(
            "resolution_action must be a shared scan resolution action."
        )
    _parse_timestamp(metadata.resolved_at, "resolved_at")
    _validate_message(metadata.resolution_message, "resolution_message")
    _validate_filename(metadata.source_filename, "source_filename")

    present_provenance = (
        metadata.source_scan_id is not None,
        metadata.source_sha256 is not None,
        metadata.retained_source_path is not None,
    )
    if any(present_provenance) and not all(present_provenance):
        raise ScanResolutionMetadataError(
            "source_scan_id, source_sha256, and retained_source_path must be "
            "all null or all non-null."
        )
    if metadata.source_scan_id is not None:
        _validate_identifier(metadata.source_scan_id, "source_scan_id")
    if metadata.source_sha256 is not None and (
        not isinstance(metadata.source_sha256, str)
        or not _SHA256_PATTERN.fullmatch(metadata.source_sha256)
    ):
        raise ScanResolutionMetadataError(
            "source_sha256 must be exactly 64 hexadecimal characters."
        )
    for field_name in (
        "retained_source_path",
        "review_copy_path",
        "resolution_evidence_path",
    ):
        value = getattr(metadata, field_name)
        if value is not None:
            _validate_workspace_relative_path(value, field_name)
    if metadata.source_page_number is not None:
        _validate_positive_int(metadata.source_page_number, "source_page_number")

    if metadata.route_locator is not None:
        if not isinstance(metadata.route_locator, RouteLocator):
            raise ScanResolutionMetadataError(
                "route_locator must be a RouteLocator or null."
            )
        try:
            validate_route_locator(metadata.route_locator)
        except RoutingModelError as error:
            raise ScanResolutionMetadataError(str(error)) from error
    if metadata.target is not None:
        if metadata.route_locator is None:
            raise ScanResolutionMetadataError(
                "target requires a non-null route_locator."
            )
        if not isinstance(metadata.target, ModuleRecordRef):
            raise ScanResolutionMetadataError(
                "target must be a ModuleRecordRef or null."
            )
        try:
            validate_module_record_ref(metadata.target)
        except RoutingModelError as error:
            raise ScanResolutionMetadataError(str(error)) from error
        if metadata.target.module_id != metadata.route_locator.module_id:
            raise ScanResolutionMetadataError(
                "target.module_id must match route_locator.module_id."
            )

    if metadata.resolution_status == "deferred":
        if metadata.resolution_action != "deferred":
            raise ScanResolutionMetadataError(
                "deferred status requires deferred action."
            )
    elif metadata.resolution_action == "deferred":
        raise ScanResolutionMetadataError(
            "deferred action requires deferred status."
        )
    if metadata.resolution_action == "deferred" and any(
        value is not None
        for value in (
            metadata.route_locator,
            metadata.target,
            metadata.resolution_evidence_path,
        )
    ):
        raise ScanResolutionMetadataError(
            "deferred resolutions cannot include a route, target, or evidence path."
        )
    if metadata.resolution_action in _ROUTED_ACTIONS and (
        metadata.route_locator is None or metadata.target is None
    ):
        raise ScanResolutionMetadataError(
            "route_selected and route_corrected require a locator and target."
        )
    if (
        metadata.resolution_action == "evidence_filed"
        and metadata.resolution_evidence_path is None
    ):
        raise ScanResolutionMetadataError(
            "evidence_filed requires resolution_evidence_path."
        )
    if metadata.resolution_action in _NO_FINAL_ROUTE_ACTIONS and any(
        value is not None
        for value in (
            metadata.route_locator,
            metadata.target,
            metadata.resolution_evidence_path,
        )
    ):
        raise ScanResolutionMetadataError(
            "no-final-route actions cannot include a route, target, or evidence path."
        )


def _verify_failure_link(
    resolution: ScanResolutionMetadata, failure: RoutingFailureMetadata
) -> None:
    if failure.schema_version != ROUTING_FAILURE_SCHEMA_VERSION:
        raise ScanResolutionMetadataIntegrityError(
            "Linked failure must use schema version 2."
        )
    if resolution.failure_id != failure.failure_id:
        raise ScanResolutionMetadataIntegrityError(
            "Linked failure ID does not match the resolution."
        )
    expected_path = _canonical_failure_path(failure.failure_id)
    if resolution.failure_metadata_path != expected_path:
        raise ScanResolutionMetadataIntegrityError(
            "Resolution failure_metadata_path is not canonical."
        )
    for field_name in _PROVENANCE_FIELDS:
        if getattr(resolution, field_name) != getattr(failure, field_name):
            raise ScanResolutionMetadataIntegrityError(
                f"Resolution {field_name} does not match the linked failure."
            )
    if _parse_timestamp(resolution.resolved_at, "resolved_at") < _parse_timestamp(
        failure.created_at, "created_at"
    ):
        raise ScanResolutionMetadataIntegrityError(
            "Resolution timestamp predates the linked failure."
        )


def _canonical_failure_path(failure_id: str) -> str:
    safe_id = _validate_identifier(failure_id, "failure_id")
    return f"scans/review/{safe_id}.json"


def _require_exact_mapping(data: object) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise ScanResolutionMetadataError(
            "scan resolution metadata must be a mapping."
        )
    raw_keys = list(data.keys())
    if any(not isinstance(key, str) for key in raw_keys):
        raise ScanResolutionMetadataError(
            "scan resolution metadata keys must be strings."
        )
    keys = frozenset(cast(str, key) for key in raw_keys)
    missing = sorted(_METADATA_KEYS - keys)
    if missing:
        raise ScanResolutionMetadataError(
            "scan resolution metadata is missing required key(s): "
            + ", ".join(missing)
            + "."
        )
    unknown = sorted(keys - _METADATA_KEYS)
    if unknown:
        raise ScanResolutionMetadataError(
            "scan resolution metadata contains unknown key(s): "
            + ", ".join(unknown)
            + "."
        )
    return cast(Mapping[str, object], data)


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ScanResolutionMetadataError(f"{field_name} must be a string.")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name)


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ScanResolutionMetadataError(
            f"{field_name} must be an integer or null."
        )
    return value


def _validate_identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(value, field_name)  # type: ignore[arg-type]
    except IdentifierValidationError as error:
        raise ScanResolutionMetadataError(str(error)) from error


def _parse_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ScanResolutionMetadataError(
            f"{field_name} must be an ISO timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ScanResolutionMetadataError(
            f"{field_name} must be a valid ISO timestamp string."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScanResolutionMetadataError(
            f"{field_name} must include a timezone offset."
        )
    return parsed


def _validate_message(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ScanResolutionMetadataError(f"{field_name} must be a string.")
    if not value:
        raise ScanResolutionMetadataError(f"{field_name} must not be empty.")
    if value != value.strip():
        raise ScanResolutionMetadataError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    if any(
        unicodedata.category(character) in {"Cc", "Zl", "Zp"}
        for character in value
    ):
        raise ScanResolutionMetadataError(
            f"{field_name} must be single-line and free of control characters."
        )
    return value


def _validate_filename(value: object, field_name: str) -> str:
    filename = _validate_message(value, field_name)
    if (
        "\x00" in filename
        or "/" in filename
        or "\\" in filename
        or bool(PureWindowsPath(filename).drive)
        or filename in {".", ".."}
    ):
        raise ScanResolutionMetadataError(
            f"{field_name} must be a filename, not a path."
        )
    return filename


def _validate_workspace_relative_path(value: object, field_name: str) -> str:
    path_value = _validate_message(value, field_name)
    windows_path = PureWindowsPath(path_value)
    posix_path = PurePosixPath(path_value)
    parts = path_value.replace("\\", "/").split("/")
    if (
        windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
        or posix_path.is_absolute()
        or "" in parts
        or "." in parts
        or ".." in parts
        or "\x00" in path_value
    ):
        raise ScanResolutionMetadataError(
            f"{field_name} must be a safe workspace-relative path."
        )
    return path_value


def _validate_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ScanResolutionMetadataError(
            f"{field_name} must be a positive integer."
        )
    return value


def _remove_incomplete_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
