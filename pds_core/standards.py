"""Shared in-memory standards models and validation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Final, TypeVar, cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier


STANDARD_USAGE_TYPES: Final[frozenset[str]] = frozenset(
    {"taught", "practiced", "assessed", "reviewed"}
)
_SCHOOL_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<start>\d{4})-(?P<end>\d{4})$"
)


class StandardsValidationError(ValueError):
    """Raised when shared standards metadata is invalid."""


class StandardsReadError(OSError):
    """Raised when a standards library JSON file cannot be read."""

    path: Path

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        super().__init__(
            f"Could not read standards library JSON {self.path}: {message}"
        )


class StandardsWriteError(OSError):
    """Raised when a standards library JSON file cannot be written."""

    path: Path

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        super().__init__(
            f"Could not write standards library JSON {self.path}: {message}"
        )


def _validated_mapping(
    value: object,
    model_name: str,
    required_keys: frozenset[str],
    allowed_keys: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise StandardsValidationError(f"{model_name} data must be a mapping.")

    non_string_keys = [key for key in value if not isinstance(key, str)]
    if non_string_keys:
        raise StandardsValidationError(
            f"{model_name} data keys must be strings."
        )

    data = cast(Mapping[str, object], value)
    unknown_keys = sorted(data.keys() - allowed_keys)
    if unknown_keys:
        unknown = ", ".join(unknown_keys)
        raise StandardsValidationError(
            f"{model_name} data contains unknown key(s): {unknown}."
        )

    missing_keys = sorted(required_keys - data.keys())
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise StandardsValidationError(
            f"{model_name} data is missing required key(s): {missing}."
        )

    return data


def _json_array(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise StandardsValidationError(f"{field_name} must be a list or tuple.")
    return tuple(value)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise StandardsValidationError(f"{field_name} must be a string.")

    normalized = value.strip()
    if not normalized:
        raise StandardsValidationError(f"{field_name} must not be blank.")
    return normalized


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise StandardsValidationError(
            f"{field_name} must be an iterable of strings."
        )

    try:
        entries: tuple[object, ...] = tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise StandardsValidationError(
            f"{field_name} must be an iterable of strings."
        ) from error

    normalized: list[str] = []
    for index, entry in enumerate(entries):
        normalized.append(_required_text(entry, f"{field_name}[{index}]"))
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class StandardDefinition:
    """One durable, module-neutral shared standard definition."""

    standard_id: str
    code: str
    source: str
    short_name: str
    description: str
    subject: str | None = None
    course: str | None = None
    grade_band: str | None = None
    domain: str | None = None
    category_path: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    active: bool = True
    available_modules: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _normalize_standard_definition(self)


@dataclass(frozen=True, slots=True)
class StandardsProfile:
    """A reusable grouping that references shared standard IDs."""

    profile_id: str
    standards: tuple[str, ...]
    subject: str | None = None
    course: str | None = None
    source: str | None = None
    title: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        _normalize_standards_profile(self)


@dataclass(frozen=True, slots=True)
class StandardsLibrary:
    """An immutable in-memory collection of definitions and profiles."""

    standards: tuple[StandardDefinition, ...]
    profiles: tuple[StandardsProfile, ...] = ()

    def __post_init__(self) -> None:
        _normalize_standards_library(self)


@dataclass(frozen=True, slots=True)
class StandardUsageEvent:
    """One module-neutral record of teacher-controlled standards usage."""

    event_id: str
    standard_id: str
    school_year: str
    class_id: str
    module: str
    usage_type: str
    used_at: datetime
    assignment_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _normalize_standard_usage_event(self)


def _normalize_standard_definition(definition: StandardDefinition) -> None:
    for field_name in (
        "standard_id",
        "code",
        "source",
        "short_name",
        "description",
    ):
        object.__setattr__(
            definition,
            field_name,
            _required_text(getattr(definition, field_name), field_name),
        )

    for field_name in ("subject", "course", "grade_band", "domain"):
        object.__setattr__(
            definition,
            field_name,
            _optional_text(getattr(definition, field_name), field_name),
        )

    for field_name in ("category_path", "tags", "available_modules"):
        object.__setattr__(
            definition,
            field_name,
            _text_tuple(getattr(definition, field_name), field_name),
        )

    if not isinstance(definition.active, bool):
        raise StandardsValidationError("active must be a boolean.")


def _normalize_standards_profile(profile: StandardsProfile) -> None:
    object.__setattr__(
        profile,
        "profile_id",
        _required_text(profile.profile_id, "profile_id"),
    )
    standards = _text_tuple(profile.standards, "standards")
    if not standards:
        raise StandardsValidationError(
            "standards must contain at least one standard ID."
        )
    if len(standards) != len(set(standards)):
        raise StandardsValidationError(
            "standards must not contain duplicate standard IDs."
        )
    object.__setattr__(profile, "standards", standards)

    for field_name in ("subject", "course", "source", "title", "description"):
        object.__setattr__(
            profile,
            field_name,
            _optional_text(getattr(profile, field_name), field_name),
        )


ModelT = TypeVar("ModelT")


def _model_tuple(
    value: object,
    field_name: str,
    model_type: type[ModelT],
) -> tuple[ModelT, ...]:
    if isinstance(value, (str, bytes)):
        raise StandardsValidationError(
            f"{field_name} must be an iterable of {model_type.__name__} objects."
        )

    try:
        entries: tuple[object, ...] = tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise StandardsValidationError(
            f"{field_name} must be an iterable of {model_type.__name__} objects."
        ) from error

    normalized: list[ModelT] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, model_type):
            raise StandardsValidationError(
                f"{field_name}[{index}] must be a {model_type.__name__}."
            )
        normalized.append(entry)
    return tuple(normalized)


def _normalize_standards_library(library: StandardsLibrary) -> None:
    standards = _model_tuple(
        library.standards,
        "standards",
        StandardDefinition,
    )
    profiles = _model_tuple(
        library.profiles,
        "profiles",
        StandardsProfile,
    )
    object.__setattr__(library, "standards", standards)
    object.__setattr__(library, "profiles", profiles)

    standard_ids = [definition.standard_id for definition in standards]
    if len(standard_ids) != len(set(standard_ids)):
        raise StandardsValidationError(
            "standards must not contain duplicate standard IDs."
        )

    profile_ids = [profile.profile_id for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise StandardsValidationError(
            "profiles must not contain duplicate profile IDs."
        )

    known_standard_ids = set(standard_ids)
    for profile in profiles:
        unknown_ids = [
            standard_id
            for standard_id in profile.standards
            if standard_id not in known_standard_ids
        ]
        if unknown_ids:
            unknown = ", ".join(repr(standard_id) for standard_id in unknown_ids)
            raise StandardsValidationError(
                f"profile {profile.profile_id!r} references unknown "
                f"standard IDs: {unknown}."
            )


def _normalize_standard_usage_event(event: StandardUsageEvent) -> None:
    for field_name in ("event_id", "standard_id", "module", "usage_type"):
        object.__setattr__(
            event,
            field_name,
            _required_text(getattr(event, field_name), field_name),
        )

    match = _SCHOOL_YEAR_PATTERN.fullmatch(
        _required_text(event.school_year, "school_year")
    )
    if match is None or int(match["end"]) != int(match["start"]) + 1:
        raise StandardsValidationError(
            "school_year must use consecutive years in YYYY-YYYY format."
        )
    object.__setattr__(event, "school_year", match.group(0))

    for field_name in ("class_id", "assignment_id"):
        value = getattr(event, field_name)
        if value is None and field_name == "assignment_id":
            continue
        try:
            normalized = validate_identifier(value, field_name)
        except IdentifierValidationError as error:
            raise StandardsValidationError(str(error)) from error
        object.__setattr__(event, field_name, normalized)

    if event.usage_type not in STANDARD_USAGE_TYPES:
        allowed = ", ".join(sorted(STANDARD_USAGE_TYPES))
        raise StandardsValidationError(
            f"usage_type must be one of: {allowed}."
        )

    if not isinstance(event.used_at, datetime):
        raise StandardsValidationError("used_at must be a datetime.")
    if event.used_at.tzinfo is None or event.used_at.utcoffset() is None:
        raise StandardsValidationError(
            "used_at must be timezone-aware."
        )

    if not isinstance(event.metadata, Mapping):
        raise StandardsValidationError("metadata must be a mapping.")
    if any(not isinstance(key, str) for key in event.metadata):
        raise StandardsValidationError("metadata keys must be strings.")
    object.__setattr__(
        event,
        "metadata",
        MappingProxyType(dict(event.metadata)),
    )


def validate_standard_definition(
    definition: StandardDefinition,
) -> StandardDefinition:
    """Validate and return a shared standard definition."""
    if not isinstance(definition, StandardDefinition):
        raise StandardsValidationError(
            "definition must be a StandardDefinition."
        )
    _normalize_standard_definition(definition)
    return definition


def validate_standards_profile(profile: StandardsProfile) -> StandardsProfile:
    """Validate and return a reusable standards profile."""
    if not isinstance(profile, StandardsProfile):
        raise StandardsValidationError("profile must be a StandardsProfile.")
    _normalize_standards_profile(profile)
    return profile


def validate_standards_library(library: StandardsLibrary) -> StandardsLibrary:
    """Validate and return an in-memory standards library."""
    if not isinstance(library, StandardsLibrary):
        raise StandardsValidationError("library must be a StandardsLibrary.")
    _normalize_standards_library(library)
    return library


def validate_standard_usage_event(
    event: StandardUsageEvent,
) -> StandardUsageEvent:
    """Validate and return a shared standards usage event."""
    if not isinstance(event, StandardUsageEvent):
        raise StandardsValidationError(
            "event must be a StandardUsageEvent."
        )
    _normalize_standard_usage_event(event)
    return event


_STANDARD_DEFINITION_REQUIRED_KEYS = frozenset(
    {"standard_id", "code", "source", "short_name", "description"}
)
_STANDARD_DEFINITION_KEYS = _STANDARD_DEFINITION_REQUIRED_KEYS | {
    "subject",
    "course",
    "grade_band",
    "domain",
    "category_path",
    "tags",
    "active",
    "available_modules",
}
_STANDARDS_PROFILE_REQUIRED_KEYS = frozenset({"profile_id", "standards"})
_STANDARDS_PROFILE_KEYS = _STANDARDS_PROFILE_REQUIRED_KEYS | {
    "subject",
    "course",
    "source",
    "title",
    "description",
}
_STANDARDS_LIBRARY_REQUIRED_KEYS = frozenset({"standards"})
_STANDARDS_LIBRARY_KEYS = _STANDARDS_LIBRARY_REQUIRED_KEYS | {"profiles"}
_STANDARD_USAGE_EVENT_REQUIRED_KEYS = frozenset(
    {
        "event_id",
        "standard_id",
        "school_year",
        "class_id",
        "module",
        "usage_type",
        "used_at",
    }
)
_STANDARD_USAGE_EVENT_KEYS = _STANDARD_USAGE_EVENT_REQUIRED_KEYS | {
    "assignment_id",
    "metadata",
}


def standard_definition_to_dict(
    definition: StandardDefinition,
) -> dict[str, object]:
    """Serialize a standard definition to a JSON-compatible dictionary."""
    validate_standard_definition(definition)
    return {
        "standard_id": definition.standard_id,
        "code": definition.code,
        "source": definition.source,
        "short_name": definition.short_name,
        "description": definition.description,
        "subject": definition.subject,
        "course": definition.course,
        "grade_band": definition.grade_band,
        "domain": definition.domain,
        "category_path": list(definition.category_path),
        "tags": list(definition.tags),
        "active": definition.active,
        "available_modules": list(definition.available_modules),
    }


def standard_definition_from_dict(
    data: Mapping[str, object],
) -> StandardDefinition:
    """Deserialize and validate a standard definition dictionary."""
    values = _validated_mapping(
        data,
        "standard definition",
        _STANDARD_DEFINITION_REQUIRED_KEYS,
        _STANDARD_DEFINITION_KEYS,
    )
    return StandardDefinition(
        standard_id=values["standard_id"],  # type: ignore[arg-type]
        code=values["code"],  # type: ignore[arg-type]
        source=values["source"],  # type: ignore[arg-type]
        short_name=values["short_name"],  # type: ignore[arg-type]
        description=values["description"],  # type: ignore[arg-type]
        subject=values.get("subject"),  # type: ignore[arg-type]
        course=values.get("course"),  # type: ignore[arg-type]
        grade_band=values.get("grade_band"),  # type: ignore[arg-type]
        domain=values.get("domain"),  # type: ignore[arg-type]
        category_path=_json_array(
            values.get("category_path", []),
            "category_path",
        ),  # type: ignore[arg-type]
        tags=_json_array(values.get("tags", []), "tags"),  # type: ignore[arg-type]
        active=values.get("active", True),  # type: ignore[arg-type]
        available_modules=_json_array(
            values.get("available_modules", []),
            "available_modules",
        ),  # type: ignore[arg-type]
    )


def standards_profile_to_dict(profile: StandardsProfile) -> dict[str, object]:
    """Serialize a standards profile to a JSON-compatible dictionary."""
    validate_standards_profile(profile)
    return {
        "profile_id": profile.profile_id,
        "standards": list(profile.standards),
        "subject": profile.subject,
        "course": profile.course,
        "source": profile.source,
        "title": profile.title,
        "description": profile.description,
    }


def standards_profile_from_dict(
    data: Mapping[str, object],
) -> StandardsProfile:
    """Deserialize and validate a standards profile dictionary."""
    values = _validated_mapping(
        data,
        "standards profile",
        _STANDARDS_PROFILE_REQUIRED_KEYS,
        _STANDARDS_PROFILE_KEYS,
    )
    return StandardsProfile(
        profile_id=values["profile_id"],  # type: ignore[arg-type]
        standards=_json_array(
            values["standards"],
            "standards",
        ),  # type: ignore[arg-type]
        subject=values.get("subject"),  # type: ignore[arg-type]
        course=values.get("course"),  # type: ignore[arg-type]
        source=values.get("source"),  # type: ignore[arg-type]
        title=values.get("title"),  # type: ignore[arg-type]
        description=values.get("description"),  # type: ignore[arg-type]
    )


def standards_library_to_dict(library: StandardsLibrary) -> dict[str, object]:
    """Serialize a standards library to a JSON-compatible dictionary."""
    validate_standards_library(library)
    return {
        "standards": [
            standard_definition_to_dict(definition)
            for definition in library.standards
        ],
        "profiles": [
            standards_profile_to_dict(profile) for profile in library.profiles
        ],
    }


def standards_library_from_dict(
    data: Mapping[str, object],
) -> StandardsLibrary:
    """Deserialize and validate a standards library dictionary."""
    values = _validated_mapping(
        data,
        "standards library",
        _STANDARDS_LIBRARY_REQUIRED_KEYS,
        _STANDARDS_LIBRARY_KEYS,
    )

    standards = []
    for index, entry in enumerate(
        _json_array(values["standards"], "standards")
    ):
        try:
            standards.append(
                standard_definition_from_dict(
                    cast(Mapping[str, object], entry)
                )
            )
        except StandardsValidationError as error:
            raise StandardsValidationError(
                f"standards[{index}]: {error}"
            ) from error

    profiles = []
    for index, entry in enumerate(
        _json_array(values.get("profiles", []), "profiles")
    ):
        try:
            profiles.append(
                standards_profile_from_dict(cast(Mapping[str, object], entry))
            )
        except StandardsValidationError as error:
            raise StandardsValidationError(
                f"profiles[{index}]: {error}"
            ) from error

    return StandardsLibrary(
        standards=tuple(standards),
        profiles=tuple(profiles),
    )


def standard_usage_event_to_dict(
    event: StandardUsageEvent,
) -> dict[str, object]:
    """Serialize a standards usage event to a JSON-compatible dictionary."""
    validate_standard_usage_event(event)
    return {
        "event_id": event.event_id,
        "standard_id": event.standard_id,
        "school_year": event.school_year,
        "class_id": event.class_id,
        "module": event.module,
        "usage_type": event.usage_type,
        "used_at": event.used_at.isoformat(),
        "assignment_id": event.assignment_id,
        "metadata": dict(event.metadata),
    }


def standard_usage_event_from_dict(
    data: Mapping[str, object],
) -> StandardUsageEvent:
    """Deserialize and validate a standards usage event dictionary."""
    values = _validated_mapping(
        data,
        "standard usage event",
        _STANDARD_USAGE_EVENT_REQUIRED_KEYS,
        _STANDARD_USAGE_EVENT_KEYS,
    )

    used_at_value = values["used_at"]
    if not isinstance(used_at_value, str):
        raise StandardsValidationError("used_at must be an ISO datetime string.")
    try:
        used_at = datetime.fromisoformat(used_at_value)
    except ValueError as error:
        raise StandardsValidationError(
            "used_at must be a valid ISO datetime string."
        ) from error

    return StandardUsageEvent(
        event_id=values["event_id"],  # type: ignore[arg-type]
        standard_id=values["standard_id"],  # type: ignore[arg-type]
        school_year=values["school_year"],  # type: ignore[arg-type]
        class_id=values["class_id"],  # type: ignore[arg-type]
        module=values["module"],  # type: ignore[arg-type]
        usage_type=values["usage_type"],  # type: ignore[arg-type]
        used_at=used_at,
        assignment_id=values.get("assignment_id"),  # type: ignore[arg-type]
        metadata=values.get("metadata", {}),  # type: ignore[arg-type]
    )


def standards_dir(workspace_root: str | Path) -> Path:
    """Return the canonical standards directory for a workspace."""
    return Path(workspace_root) / "standards"


def standards_library_path(workspace_root: str | Path) -> Path:
    """Return the canonical shared standards library JSON path."""
    return standards_dir(workspace_root) / "library.json"


def ensure_standards_dir(workspace_root: str | Path) -> Path:
    """Create and return the canonical standards directory."""
    directory = standards_dir(workspace_root)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_standards_library(path: str | Path) -> StandardsLibrary:
    """Load, deserialize, and validate a UTF-8 standards library JSON file."""
    source_path = Path(path)

    try:
        with source_path.open(encoding="utf-8") as standards_file:
            data = json.load(standards_file)
    except json.JSONDecodeError as error:
        raise StandardsReadError(
            source_path,
            f"invalid JSON: {error}",
        ) from error
    except (OSError, UnicodeError) as error:
        raise StandardsReadError(source_path, str(error)) from error

    if not isinstance(data, Mapping):
        raise StandardsReadError(
            source_path,
            "top-level JSON value must be a mapping",
        )

    try:
        return standards_library_from_dict(cast(Mapping[str, object], data))
    except (StandardsValidationError, KeyError, TypeError) as error:
        raise StandardsReadError(
            source_path,
            f"invalid standards library data: {error}",
        ) from error


def write_standards_library(
    path: str | Path,
    library: StandardsLibrary,
    *,
    overwrite: bool = False,
) -> None:
    """Atomically write a standards library to a UTF-8 JSON file."""
    target_path = Path(path)

    try:
        data = standards_library_to_dict(library)
        content = json.dumps(data, indent=2, sort_keys=True) + "\n"
    except (StandardsValidationError, TypeError, ValueError) as error:
        raise StandardsWriteError(
            target_path,
            f"invalid standards library data: {error}",
        ) from error

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StandardsWriteError(target_path, str(error)) from error

    if target_path.exists() and not overwrite:
        raise StandardsWriteError(target_path, "target file already exists")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
        ) as standards_file:
            temp_path = Path(standards_file.name)
            standards_file.write(content)
            standards_file.flush()
            os.fsync(standards_file.fileno())

        os.replace(temp_path, target_path)
        temp_path = None
    except (OSError, UnicodeError) as error:
        cleanup_error: OSError | None = None
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as caught_cleanup_error:
                cleanup_error = caught_cleanup_error

        message = str(error)
        if cleanup_error is not None:
            message = f"{message}; temporary file cleanup failed: {cleanup_error}"
        raise StandardsWriteError(target_path, message) from error


def load_workspace_standards_library(
    workspace_root: str | Path,
) -> StandardsLibrary:
    """Load the canonical shared standards library for a workspace."""
    return load_standards_library(standards_library_path(workspace_root))


def write_workspace_standards_library(
    workspace_root: str | Path,
    library: StandardsLibrary,
    *,
    overwrite: bool = False,
) -> None:
    """Write the canonical shared standards library for a workspace."""
    write_standards_library(
        standards_library_path(workspace_root),
        library,
        overwrite=overwrite,
    )
