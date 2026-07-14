"""Generic immutable PDS2 routing-failure metadata."""

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
from pds_core.module_dispatch import (
    ModuleContractCompatibilityError,
    ModuleRegistrationValidationError,
    ModuleRouteHandlingError,
    RouteDispatchFailure,
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
from pds_core.scan_routes import routing_review_dir


ROUTING_FAILURE_SCHEMA_VERSION: Final[str] = "2"
ROUTING_FAILURE_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "source_missing",
        "source_unreadable",
        "source_type_unsupported",
        "source_retention_failed",
        "payload_missing",
        "payload_unreadable",
        "payload_invalid",
        "payload_schema_unsupported",
        "payload_too_large",
        "identifier_invalid",
        "module_unsupported",
        "module_profile_incompatible",
        "class_unknown",
        "work_unknown",
        "route_unknown",
        "route_inactive",
        "route_ambiguous",
        "route_mismatch",
        "route_registration_invalid",
        "target_unknown",
        "target_incompatible",
        "page_conflict",
        "processing_error",
        "evidence_write_failed",
    }
)

_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Fa-f]{64}$")
_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "failure_id",
        "scope",
        "stage",
        "created_at",
        "failure_category",
        "failure_message",
        "source_filename",
        "source_scan_id",
        "source_sha256",
        "retained_source_path",
        "review_copy_path",
        "source_page_number",
        "detected_payload",
        "route_locator",
        "target",
        "module_details",
    }
)
_EMPTY_DETAILS: Final[Mapping[str, JsonValue]] = MappingProxyType({})


class RoutingFailureMetadataError(ValueError):
    """Raised when routing-failure metadata is invalid."""


class RoutingFailureMetadataWriteError(RuntimeError):
    """Raised when routing-failure metadata cannot be created safely."""


class RoutingFailureMetadataReadError(RuntimeError):
    """Raised when persisted routing-failure metadata cannot be read."""


class RoutingFailureMetadataNotFoundError(RoutingFailureMetadataReadError):
    """Raised when the canonical routing-failure file is absent."""


class RoutingFailureMetadataIntegrityError(RoutingFailureMetadataReadError):
    """Raised when stored failure identity differs from requested identity."""


@dataclass(frozen=True, slots=True, init=False)
class RoutingFailureMetadata:
    """One immutable generic scan or page routing failure."""

    schema_version: str
    failure_id: str
    scope: str
    stage: str
    created_at: str
    failure_category: str
    failure_message: str
    source_filename: str
    source_scan_id: str | None
    source_sha256: str | None
    retained_source_path: str | None
    review_copy_path: str | None
    source_page_number: int | None
    detected_payload: str | None
    route_locator: RouteLocator | None
    target: ModuleRecordRef | None
    _module_details: FrozenJsonMapping = field(repr=False, compare=True)

    def __init__(
        self,
        schema_version: str,
        failure_id: str,
        scope: str,
        stage: str,
        created_at: str,
        failure_category: str,
        failure_message: str,
        source_filename: str,
        source_scan_id: str | None,
        source_sha256: str | None,
        retained_source_path: str | None,
        review_copy_path: str | None,
        source_page_number: int | None,
        detected_payload: str | None,
        route_locator: RouteLocator | None,
        target: ModuleRecordRef | None,
        module_details: Mapping[str, JsonValue] = _EMPTY_DETAILS,
    ) -> None:
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "failure_id", failure_id)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "failure_category", failure_category)
        object.__setattr__(self, "failure_message", failure_message)
        object.__setattr__(self, "source_filename", source_filename)
        object.__setattr__(self, "source_scan_id", source_scan_id)
        object.__setattr__(self, "source_sha256", source_sha256)
        object.__setattr__(self, "retained_source_path", retained_source_path)
        object.__setattr__(self, "review_copy_path", review_copy_path)
        object.__setattr__(self, "source_page_number", source_page_number)
        object.__setattr__(self, "detected_payload", detected_payload)
        object.__setattr__(self, "route_locator", route_locator)
        object.__setattr__(self, "target", target)
        _validate_metadata_fields(self)
        try:
            frozen_details = freeze_json_mapping(module_details, "module_details")
        except JsonValueIsolationError as error:
            raise RoutingFailureMetadataError(str(error)) from error
        object.__setattr__(self, "_module_details", frozen_details)

    @property
    def module_details(self) -> dict[str, JsonValue]:
        """Return an isolated JSON-native copy of module-owned diagnostics."""
        return thaw_json_mapping(self._module_details)


def is_routing_failure_category(value: object) -> bool:
    """Return whether a value is a shared routing-failure category."""
    return isinstance(value, str) and value in ROUTING_FAILURE_CATEGORIES


def validate_routing_failure_metadata(
    metadata: RoutingFailureMetadata | Mapping[str, object],
) -> RoutingFailureMetadata:
    """Validate and return exact version 2 routing-failure metadata."""
    if isinstance(metadata, RoutingFailureMetadata):
        _validate_metadata_fields(metadata)
        try:
            thaw_json_mapping(metadata._module_details)
        except JsonValueIsolationError as error:
            raise RoutingFailureMetadataError(str(error)) from error
        return metadata
    if not isinstance(metadata, Mapping):
        raise RoutingFailureMetadataError(
            "routing failure metadata must be a model or mapping."
        )
    return routing_failure_metadata_from_dict(metadata)


def routing_failure_metadata_to_dict(
    metadata: RoutingFailureMetadata,
) -> dict[str, object]:
    """Convert validated metadata to its exact 17-key JSON shape."""
    value = validate_routing_failure_metadata(metadata)
    return {
        "schema_version": value.schema_version,
        "failure_id": value.failure_id,
        "scope": value.scope,
        "stage": value.stage,
        "created_at": value.created_at,
        "failure_category": value.failure_category,
        "failure_message": value.failure_message,
        "source_filename": value.source_filename,
        "source_scan_id": value.source_scan_id,
        "source_sha256": value.source_sha256,
        "retained_source_path": value.retained_source_path,
        "review_copy_path": value.review_copy_path,
        "source_page_number": value.source_page_number,
        "detected_payload": value.detected_payload,
        "route_locator": (
            None
            if value.route_locator is None
            else route_locator_to_dict(value.route_locator)
        ),
        "target": (
            None if value.target is None else module_record_ref_to_dict(value.target)
        ),
        "module_details": value.module_details,
    }


def routing_failure_metadata_from_dict(data: object) -> RoutingFailureMetadata:
    """Build metadata from an exact version 2 schema mapping."""
    mapping = _require_exact_mapping(data)
    route_data = mapping["route_locator"]
    target_data = mapping["target"]
    details = mapping["module_details"]
    if not isinstance(details, Mapping):
        raise RoutingFailureMetadataError("module_details must be a mapping.")
    try:
        route_locator = (
            None if route_data is None else route_locator_from_dict(route_data)
        )
        target = None if target_data is None else module_record_ref_from_dict(target_data)
        return RoutingFailureMetadata(
            schema_version=_require_string(mapping["schema_version"], "schema_version"),
            failure_id=_require_string(mapping["failure_id"], "failure_id"),
            scope=_require_string(mapping["scope"], "scope"),
            stage=_require_string(mapping["stage"], "stage"),
            created_at=_require_string(mapping["created_at"], "created_at"),
            failure_category=_require_string(
                mapping["failure_category"], "failure_category"
            ),
            failure_message=_require_string(
                mapping["failure_message"], "failure_message"
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
            detected_payload=_optional_string(
                mapping["detected_payload"], "detected_payload"
            ),
            route_locator=route_locator,
            target=target,
            module_details=cast(Mapping[str, JsonValue], details),
        )
    except RoutingModelError as error:
        raise RoutingFailureMetadataError(
            f"routing identity is invalid: {error}"
        ) from error


def routing_failure_category_for_dispatch_error(error: Exception) -> str:
    """Map one supported dispatch error to the generic failure vocabulary."""
    if not isinstance(error, Exception):
        raise RoutingFailureMetadataError("error must be an Exception.")
    if isinstance(error, UnsupportedModuleError):
        return "module_unsupported"
    if isinstance(error, ModuleContractCompatibilityError):
        return "module_profile_incompatible"
    if isinstance(error, RouteRegistrationNotFoundError):
        return "route_unknown"
    if isinstance(error, RouteRegistrationIntegrityError):
        return "route_mismatch"
    if isinstance(error, RouteRegistrationReadError):
        return "route_registration_invalid"
    if isinstance(error, RouteStatusNotDispatchableError):
        return "route_inactive"
    if isinstance(error, ModuleRegistrationValidationError):
        return "target_incompatible"
    if isinstance(error, ModuleRouteHandlingError):
        return "processing_error"
    if isinstance(error, RouteDispatchRequestError):
        return "processing_error"
    if isinstance(error, RoutingModelError):
        return "identifier_invalid"
    raise RoutingFailureMetadataError(
        f"unsupported dispatch error type: {type(error).__name__}."
    )


def routing_failure_stage_for_dispatch_error(error: Exception) -> str:
    """Map one supported dispatch error to its routing pipeline stage."""
    if isinstance(error, (UnsupportedModuleError, ModuleContractCompatibilityError)):
        return "module_resolution"
    if isinstance(
        error,
        (
            RouteRegistrationNotFoundError,
            RouteRegistrationIntegrityError,
            RouteRegistrationReadError,
            RouteStatusNotDispatchableError,
        ),
    ):
        return "route_resolution"
    if isinstance(error, ModuleRegistrationValidationError):
        return "module_validation"
    if isinstance(error, ModuleRouteHandlingError):
        return "module_handling"
    if isinstance(error, RouteDispatchRequestError):
        return "module_handling"
    if isinstance(error, RoutingModelError):
        return "route_resolution"
    routing_failure_category_for_dispatch_error(error)
    raise AssertionError("unreachable")


def routing_failure_metadata_from_dispatch_failure(
    failure: RouteDispatchFailure,
    *,
    failure_id: str,
    created_at: str,
    detected_payload: str | None = None,
    review_copy_path: str | None = None,
    target: ModuleRecordRef | None = None,
    module_details: Mapping[str, JsonValue] | None = None,
) -> RoutingFailureMetadata:
    """Build immutable failure metadata without accessing the filesystem."""
    if not isinstance(failure, RouteDispatchFailure):
        raise RoutingFailureMetadataError(
            "failure must be a RouteDispatchFailure."
        )
    request = failure.request
    retained = request.retained_source
    return RoutingFailureMetadata(
        schema_version=ROUTING_FAILURE_SCHEMA_VERSION,
        failure_id=failure_id,
        scope="page",
        stage=routing_failure_stage_for_dispatch_error(failure.error),
        created_at=created_at,
        failure_category=routing_failure_category_for_dispatch_error(failure.error),
        failure_message=str(failure.error),
        source_filename=retained.source_filename,
        source_scan_id=retained.source_scan_id,
        source_sha256=retained.source_sha256,
        retained_source_path=retained.retained_source_relative_path,
        review_copy_path=review_copy_path,
        source_page_number=request.source_page_number,
        detected_payload=detected_payload,
        route_locator=request.locator,
        target=target,
        module_details={} if module_details is None else module_details,
    )


def routing_failure_metadata_path(root: str | Path, failure_id: str) -> Path:
    """Return the canonical review path without touching the filesystem."""
    safe_failure_id = _validate_identifier(failure_id, "failure_id")
    return routing_review_dir(root) / f"{safe_failure_id}.json"


def write_routing_failure_metadata(
    root: str | Path, metadata: RoutingFailureMetadata
) -> Path:
    """Exclusively create one stable, flushed routing-failure record."""
    if not isinstance(metadata, RoutingFailureMetadata):
        raise RoutingFailureMetadataError(
            "metadata must be a RoutingFailureMetadata."
        )
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
    except OSError as error:
        raise RoutingFailureMetadataWriteError(
            f"Could not create routing-failure directory {path.parent}: {error}"
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
            raise RoutingFailureMetadataWriteError(
                f"Routing failure metadata already exists: {path}"
            ) from error
        _remove_incomplete_file(path)
        raise RoutingFailureMetadataWriteError(
            f"Could not write routing failure metadata {path}: {error}"
        ) from error
    except (OSError, UnicodeError) as error:
        if created:
            _remove_incomplete_file(path)
        raise RoutingFailureMetadataWriteError(
            f"Could not write routing failure metadata {path}: {error}"
        ) from error
    return path


def load_routing_failure_metadata(
    root: str | Path, failure_id: str
) -> RoutingFailureMetadata:
    """Load exact version 2 metadata from one canonical path."""
    requested_id = _validate_identifier(failure_id, "failure_id")
    path = routing_failure_metadata_path(root, requested_id)
    try:
        data = load_strict_json(path)
    except FileNotFoundError as error:
        raise RoutingFailureMetadataNotFoundError(
            f"Routing failure metadata not found at canonical path: {path}"
        ) from error
    except (
        json.JSONDecodeError,
        UnicodeError,
        DuplicateJsonKeyError,
        InvalidJsonConstantError,
    ) as error:
        raise RoutingFailureMetadataReadError(
            f"Routing failure metadata contains invalid JSON at {path}: {error}"
        ) from error
    except OSError as error:
        raise RoutingFailureMetadataReadError(
            f"Could not read routing failure metadata {path}: {error}"
        ) from error
    if not isinstance(data, dict):
        raise RoutingFailureMetadataReadError(
            f"Routing failure metadata must be a JSON object at {path}."
        )
    try:
        metadata = routing_failure_metadata_from_dict(data)
    except RoutingFailureMetadataError as error:
        raise RoutingFailureMetadataReadError(
            f"Routing failure metadata is invalid at {path}: {error}"
        ) from error
    if metadata.failure_id != requested_id:
        raise RoutingFailureMetadataIntegrityError(
            f"Stored failure_id does not match requested ID at {path}."
        )
    return metadata


def _validate_metadata_fields(metadata: RoutingFailureMetadata) -> None:
    if metadata.schema_version != ROUTING_FAILURE_SCHEMA_VERSION:
        raise RoutingFailureMetadataError(
            f'schema_version must be "{ROUTING_FAILURE_SCHEMA_VERSION}".'
        )
    _validate_identifier(metadata.failure_id, "failure_id")
    if not isinstance(metadata.scope, str) or metadata.scope not in {
        "scan",
        "page",
    }:
        raise RoutingFailureMetadataError('scope must be "scan" or "page".')
    _validate_identifier(metadata.stage, "stage")
    if metadata.stage != metadata.stage.lower():
        raise RoutingFailureMetadataError("stage must be lowercase.")
    _parse_timestamp(metadata.created_at, "created_at")
    if not is_routing_failure_category(metadata.failure_category):
        raise RoutingFailureMetadataError(
            "failure_category must be a shared routing failure category."
        )
    _validate_message(metadata.failure_message, "failure_message")
    _validate_filename(metadata.source_filename, "source_filename")

    present_provenance = (
        metadata.source_scan_id is not None,
        metadata.source_sha256 is not None,
        metadata.retained_source_path is not None,
    )
    if any(present_provenance) and not all(present_provenance):
        raise RoutingFailureMetadataError(
            "source_scan_id, source_sha256, and retained_source_path must be "
            "all null or all non-null."
        )
    if metadata.source_scan_id is not None:
        _validate_identifier(metadata.source_scan_id, "source_scan_id")
    if metadata.source_sha256 is not None and (
        not isinstance(metadata.source_sha256, str)
        or not _SHA256_PATTERN.fullmatch(metadata.source_sha256)
    ):
        raise RoutingFailureMetadataError(
            "source_sha256 must be exactly 64 hexadecimal characters."
        )
    if metadata.retained_source_path is not None:
        _validate_workspace_relative_path(
            metadata.retained_source_path, "retained_source_path"
        )
    if metadata.review_copy_path is not None:
        _validate_workspace_relative_path(
            metadata.review_copy_path, "review_copy_path"
        )

    if metadata.scope == "page":
        _validate_positive_int(metadata.source_page_number, "source_page_number")
    elif metadata.source_page_number is not None:
        raise RoutingFailureMetadataError(
            "scan-scoped failures require source_page_number to be null."
        )
    if metadata.detected_payload is not None and not isinstance(
        metadata.detected_payload, str
    ):
        raise RoutingFailureMetadataError(
            "detected_payload must be a string or null."
        )
    if metadata.route_locator is not None:
        if not isinstance(metadata.route_locator, RouteLocator):
            raise RoutingFailureMetadataError(
                "route_locator must be a RouteLocator or null."
            )
        try:
            validate_route_locator(metadata.route_locator)
        except RoutingModelError as error:
            raise RoutingFailureMetadataError(str(error)) from error
    if metadata.target is not None:
        if metadata.route_locator is None:
            raise RoutingFailureMetadataError(
                "target requires a non-null route_locator."
            )
        if not isinstance(metadata.target, ModuleRecordRef):
            raise RoutingFailureMetadataError(
                "target must be a ModuleRecordRef or null."
            )
        try:
            validate_module_record_ref(metadata.target)
        except RoutingModelError as error:
            raise RoutingFailureMetadataError(str(error)) from error
        if metadata.target.module_id != metadata.route_locator.module_id:
            raise RoutingFailureMetadataError(
                "target.module_id must match route_locator.module_id."
            )


def _require_exact_mapping(data: object) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise RoutingFailureMetadataError(
            "routing failure metadata must be a mapping."
        )
    raw_keys = list(data.keys())
    if any(not isinstance(key, str) for key in raw_keys):
        raise RoutingFailureMetadataError(
            "routing failure metadata keys must be strings."
        )
    keys = frozenset(cast(str, key) for key in raw_keys)
    missing = sorted(_METADATA_KEYS - keys)
    if missing:
        raise RoutingFailureMetadataError(
            "routing failure metadata is missing required key(s): "
            + ", ".join(missing)
            + "."
        )
    unknown = sorted(keys - _METADATA_KEYS)
    if unknown:
        raise RoutingFailureMetadataError(
            "routing failure metadata contains unknown key(s): "
            + ", ".join(unknown)
            + "."
        )
    return cast(Mapping[str, object], data)


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RoutingFailureMetadataError(f"{field_name} must be a string.")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name)


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise RoutingFailureMetadataError(
            f"{field_name} must be an integer or null."
        )
    return value


def _validate_identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(value, field_name)  # type: ignore[arg-type]
    except IdentifierValidationError as error:
        raise RoutingFailureMetadataError(str(error)) from error


def _parse_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise RoutingFailureMetadataError(
            f"{field_name} must be an ISO timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RoutingFailureMetadataError(
            f"{field_name} must be a valid ISO timestamp string."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RoutingFailureMetadataError(
            f"{field_name} must include a timezone offset."
        )
    return parsed


def _validate_message(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RoutingFailureMetadataError(f"{field_name} must be a string.")
    if not value:
        raise RoutingFailureMetadataError(f"{field_name} must not be empty.")
    if value != value.strip():
        raise RoutingFailureMetadataError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    if any(
        unicodedata.category(character) in {"Cc", "Zl", "Zp"}
        for character in value
    ):
        raise RoutingFailureMetadataError(
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
        raise RoutingFailureMetadataError(
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
        raise RoutingFailureMetadataError(
            f"{field_name} must be a safe workspace-relative path."
        )
    return path_value


def _validate_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RoutingFailureMetadataError(
            f"{field_name} must be a positive integer."
        )
    return value


def _remove_incomplete_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
