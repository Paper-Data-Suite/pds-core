"""Shared in-memory standards models and validation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
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


class StandardsUsageReadError(OSError):
    """Raised when a standards usage events JSONL file cannot be read."""

    path: Path

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        super().__init__(
            f"Could not read standards usage events JSONL {self.path}: {message}"
        )


class StandardsUsageWriteError(OSError):
    """Raised when a standards usage events JSONL file cannot be written."""

    path: Path

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        super().__init__(
            f"Could not write standards usage events JSONL {self.path}: "
            f"{message}"
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


def _validate_school_year(value: object) -> str:
    match = _SCHOOL_YEAR_PATTERN.fullmatch(
        _required_text(value, "school_year")
    )
    if match is None or int(match["end"]) != int(match["start"]) + 1:
        raise StandardsValidationError(
            "school_year must use consecutive years in YYYY-YYYY format."
        )
    return match.group(0)


def _validate_usage_class_id(value: object) -> str:
    if not isinstance(value, str):
        raise StandardsValidationError("class_id must be a string.")
    try:
        return validate_identifier(value, "class_id")
    except IdentifierValidationError as error:
        raise StandardsValidationError(str(error)) from error


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


@dataclass(frozen=True, slots=True)
class StandardUsageCounts:
    """Usage counts for one standard."""

    standard_id: str
    total: int
    by_usage_type: Mapping[str, int]
    by_module: Mapping[str, int]
    by_assignment_id: Mapping[str | None, int]

    def __post_init__(self) -> None:
        _normalize_standard_usage_counts(self)


@dataclass(frozen=True, slots=True)
class StandardsUsageSummary:
    """Read-only summary of standards usage events."""

    total_events: int
    by_standard_id: Mapping[str, StandardUsageCounts]

    def __post_init__(self) -> None:
        _normalize_standards_usage_summary(self)


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

    object.__setattr__(
        event,
        "school_year",
        _validate_school_year(event.school_year),
    )

    for field_name in ("class_id", "assignment_id"):
        value = getattr(event, field_name)
        if value is None and field_name == "assignment_id":
            continue
        if field_name == "class_id":
            object.__setattr__(
                event,
                field_name,
                _validate_usage_class_id(value),
            )
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


def add_standard_definition(
    library: StandardsLibrary,
    definition: StandardDefinition,
) -> StandardsLibrary:
    """Return a new library with definition added."""
    validated_library = validate_standards_library(library)
    validated_definition = validate_standard_definition(definition)

    if any(
        existing.standard_id == validated_definition.standard_id
        for existing in validated_library.standards
    ):
        raise StandardsValidationError(
            "add_standard_definition cannot add duplicate "
            f"standard_id {validated_definition.standard_id!r}."
        )

    return validate_standards_library(
        StandardsLibrary(
            standards=validated_library.standards + (validated_definition,),
            profiles=validated_library.profiles,
        )
    )


def replace_standard_definition(
    library: StandardsLibrary,
    definition: StandardDefinition,
) -> StandardsLibrary:
    """Return a new library with an existing definition replaced."""
    validated_library = validate_standards_library(library)
    validated_definition = validate_standard_definition(definition)

    replaced = False
    standards: list[StandardDefinition] = []
    for existing in validated_library.standards:
        if existing.standard_id == validated_definition.standard_id:
            standards.append(validated_definition)
            replaced = True
        else:
            standards.append(existing)

    if not replaced:
        raise StandardsValidationError(
            "replace_standard_definition cannot replace missing "
            f"standard_id {validated_definition.standard_id!r}."
        )

    return validate_standards_library(
        StandardsLibrary(
            standards=tuple(standards),
            profiles=validated_library.profiles,
        )
    )


def upsert_standard_definition(
    library: StandardsLibrary,
    definition: StandardDefinition,
) -> StandardsLibrary:
    """Return a new library with definition added or replaced."""
    validated_library = validate_standards_library(library)
    validated_definition = validate_standard_definition(definition)

    standards: list[StandardDefinition] = []
    replaced = False
    for existing in validated_library.standards:
        if existing.standard_id == validated_definition.standard_id:
            standards.append(validated_definition)
            replaced = True
        else:
            standards.append(existing)

    if not replaced:
        standards.append(validated_definition)

    return validate_standards_library(
        StandardsLibrary(
            standards=tuple(standards),
            profiles=validated_library.profiles,
        )
    )


def add_standards_profile(
    library: StandardsLibrary,
    profile: StandardsProfile,
) -> StandardsLibrary:
    """Return a new library with profile added."""
    validated_library = validate_standards_library(library)
    validated_profile = validate_standards_profile(profile)

    if any(
        existing.profile_id == validated_profile.profile_id
        for existing in validated_library.profiles
    ):
        raise StandardsValidationError(
            "add_standards_profile cannot add duplicate "
            f"profile_id {validated_profile.profile_id!r}."
        )

    return validate_standards_library(
        StandardsLibrary(
            standards=validated_library.standards,
            profiles=validated_library.profiles + (validated_profile,),
        )
    )


def replace_standards_profile(
    library: StandardsLibrary,
    profile: StandardsProfile,
) -> StandardsLibrary:
    """Return a new library with an existing profile replaced."""
    validated_library = validate_standards_library(library)
    validated_profile = validate_standards_profile(profile)

    replaced = False
    profiles: list[StandardsProfile] = []
    for existing in validated_library.profiles:
        if existing.profile_id == validated_profile.profile_id:
            profiles.append(validated_profile)
            replaced = True
        else:
            profiles.append(existing)

    if not replaced:
        raise StandardsValidationError(
            "replace_standards_profile cannot replace missing "
            f"profile_id {validated_profile.profile_id!r}."
        )

    return validate_standards_library(
        StandardsLibrary(
            standards=validated_library.standards,
            profiles=tuple(profiles),
        )
    )


def upsert_standards_profile(
    library: StandardsLibrary,
    profile: StandardsProfile,
) -> StandardsLibrary:
    """Return a new library with profile added or replaced."""
    validated_library = validate_standards_library(library)
    validated_profile = validate_standards_profile(profile)

    profiles: list[StandardsProfile] = []
    replaced = False
    for existing in validated_library.profiles:
        if existing.profile_id == validated_profile.profile_id:
            profiles.append(validated_profile)
            replaced = True
        else:
            profiles.append(existing)

    if not replaced:
        profiles.append(validated_profile)

    return validate_standards_library(
        StandardsLibrary(
            standards=validated_library.standards,
            profiles=tuple(profiles),
        )
    )


def _optional_filter_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _optional_category_path_prefix(
    value: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise StandardsValidationError(
            "category_path_prefix must be a tuple or list of strings."
        )
    if not isinstance(value, (tuple, list)):
        raise StandardsValidationError(
            "category_path_prefix must be a tuple or list of strings."
        )
    if not value:
        return ()
    return _text_tuple(value, "category_path_prefix")


def _optional_active_filter(value: bool | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise StandardsValidationError("active must be a boolean or None.")


def _require_standards_library(library: StandardsLibrary) -> StandardsLibrary:
    if not isinstance(library, StandardsLibrary):
        raise StandardsValidationError("library must be a StandardsLibrary.")
    return library


def find_standard_definition(
    library: StandardsLibrary,
    standard_id: str,
) -> StandardDefinition | None:
    """Return the standard definition with standard_id, or None."""
    validated_library = _require_standards_library(library)
    normalized_standard_id = _required_text(standard_id, "standard_id")

    for definition in validated_library.standards:
        if definition.standard_id == normalized_standard_id:
            return definition
    return None


def filter_standard_definitions(
    library: StandardsLibrary,
    *,
    subject: str | None = None,
    source: str | None = None,
    domain: str | None = None,
    active: bool | None = None,
    available_module: str | None = None,
    category_path_prefix: tuple[str, ...] | list[str] | None = None,
) -> tuple[StandardDefinition, ...]:
    """Return standards matching all supplied filters."""
    validated_library = _require_standards_library(library)
    normalized_subject = _optional_filter_text(subject, "subject")
    normalized_source = _optional_filter_text(source, "source")
    normalized_domain = _optional_filter_text(domain, "domain")
    normalized_active = _optional_active_filter(active)
    normalized_available_module = _optional_filter_text(
        available_module,
        "available_module",
    )
    normalized_category_path_prefix = _optional_category_path_prefix(
        category_path_prefix
    )

    matches: list[StandardDefinition] = []
    for definition in validated_library.standards:
        if (
            normalized_subject is not None
            and definition.subject != normalized_subject
        ):
            continue
        if (
            normalized_source is not None
            and definition.source != normalized_source
        ):
            continue
        if (
            normalized_domain is not None
            and definition.domain != normalized_domain
        ):
            continue
        if normalized_active is not None and definition.active is not normalized_active:
            continue
        if (
            normalized_available_module is not None
            and normalized_available_module not in definition.available_modules
        ):
            continue
        if normalized_category_path_prefix and not definition.category_path[
            : len(normalized_category_path_prefix)
        ] == normalized_category_path_prefix:
            continue
        matches.append(definition)
    return tuple(matches)


def list_standard_subjects(
    library: StandardsLibrary,
    *,
    active: bool | None = None,
    available_module: str | None = None,
) -> tuple[str, ...]:
    """Return sorted unique non-empty subjects from matching standards."""
    return tuple(
        sorted(
            {
                definition.subject
                for definition in filter_standard_definitions(
                    library,
                    active=active,
                    available_module=available_module,
                )
                if definition.subject is not None
            }
        )
    )


def list_standard_sources(
    library: StandardsLibrary,
    *,
    active: bool | None = None,
    available_module: str | None = None,
) -> tuple[str, ...]:
    """Return sorted unique sources from matching standards."""
    return tuple(
        sorted(
            {
                definition.source
                for definition in filter_standard_definitions(
                    library,
                    active=active,
                    available_module=available_module,
                )
                if definition.source
            }
        )
    )


def list_standard_domains(
    library: StandardsLibrary,
    *,
    subject: str | None = None,
    source: str | None = None,
    active: bool | None = None,
    available_module: str | None = None,
) -> tuple[str, ...]:
    """Return sorted unique non-empty domains from matching standards."""
    return tuple(
        sorted(
            {
                definition.domain
                for definition in filter_standard_definitions(
                    library,
                    subject=subject,
                    source=source,
                    active=active,
                    available_module=available_module,
                )
                if definition.domain is not None
            }
        )
    )


def list_standard_category_paths(
    library: StandardsLibrary,
    *,
    subject: str | None = None,
    source: str | None = None,
    domain: str | None = None,
    active: bool | None = None,
    available_module: str | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Return sorted unique non-empty category paths from matching standards."""
    return tuple(
        sorted(
            {
                definition.category_path
                for definition in filter_standard_definitions(
                    library,
                    subject=subject,
                    source=source,
                    domain=domain,
                    active=active,
                    available_module=available_module,
                )
                if definition.category_path
            }
        )
    )


def find_standards_profile(
    library: StandardsLibrary,
    profile_id: str,
) -> StandardsProfile | None:
    """Return the standards profile with profile_id, or None."""
    validated_library = _require_standards_library(library)
    normalized_profile_id = _required_text(profile_id, "profile_id")

    for profile in validated_library.profiles:
        if profile.profile_id == normalized_profile_id:
            return profile
    return None


def validate_profile_standard_selection(
    library: StandardsLibrary,
    *,
    profile_id: str,
    selected_standard_ids: Iterable[str],
) -> tuple[str, ...]:
    """Validate standard IDs selected from a shared standards profile."""
    validated_library = _require_standards_library(library)
    normalized_profile_id = _required_text(profile_id, "profile_id")
    normalized_selected_ids = _text_tuple(
        selected_standard_ids,
        "selected_standard_ids",
    )

    profile = find_standards_profile(validated_library, normalized_profile_id)
    if profile is None:
        raise StandardsValidationError(
            f"profile_id {normalized_profile_id!r} does not exist."
        )

    duplicates = [
        standard_id
        for standard_id, count in Counter(normalized_selected_ids).items()
        if count > 1
    ]
    if duplicates:
        duplicate_list = ", ".join(repr(standard_id) for standard_id in duplicates)
        raise StandardsValidationError(
            "selected_standard_ids must not contain duplicate standard IDs: "
            f"{duplicate_list}."
        )

    known_standard_ids = {
        definition.standard_id for definition in validated_library.standards
    }
    unknown_ids = [
        standard_id
        for standard_id in normalized_selected_ids
        if standard_id not in known_standard_ids
    ]
    if unknown_ids:
        unknown = ", ".join(repr(standard_id) for standard_id in unknown_ids)
        raise StandardsValidationError(
            "selected_standard_ids references unknown standard IDs: "
            f"{unknown}."
        )

    profile_standard_ids = set(profile.standards)
    outside_profile_ids = [
        standard_id
        for standard_id in normalized_selected_ids
        if standard_id not in profile_standard_ids
    ]
    if outside_profile_ids:
        outside_profile = ", ".join(
            repr(standard_id) for standard_id in outside_profile_ids
        )
        raise StandardsValidationError(
            "selected_standard_ids must belong to profile "
            f"{normalized_profile_id!r}: {outside_profile}."
        )

    return normalized_selected_ids


def filter_standards_profiles(
    library: StandardsLibrary,
    *,
    subject: str | None = None,
    course: str | None = None,
    source: str | None = None,
) -> tuple[StandardsProfile, ...]:
    """Return profiles matching all supplied filters."""
    validated_library = _require_standards_library(library)
    normalized_subject = _optional_filter_text(subject, "subject")
    normalized_course = _optional_filter_text(course, "course")
    normalized_source = _optional_filter_text(source, "source")

    matches: list[StandardsProfile] = []
    for profile in validated_library.profiles:
        if normalized_subject is not None and profile.subject != normalized_subject:
            continue
        if normalized_course is not None and profile.course != normalized_course:
            continue
        if normalized_source is not None and profile.source != normalized_source:
            continue
        matches.append(profile)
    return tuple(matches)


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


def _validate_nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StandardsValidationError(f"{field_name} must be an integer.")
    if value < 0:
        raise StandardsValidationError(f"{field_name} must not be negative.")
    return value


def _assignment_id_sort_key(value: str | None) -> tuple[bool, str]:
    return (value is not None, "" if value is None else value)


def _readonly_text_count_mapping(
    value: object,
    field_name: str,
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise StandardsValidationError(f"{field_name} must be a mapping.")

    entries: dict[str, int] = {}
    for key, count in value.items():
        normalized_key = _required_text(key, f"{field_name} key")
        entries[normalized_key] = _validate_nonnegative_int(
            count,
            f"{field_name}[{normalized_key!r}]",
        )
    return MappingProxyType({key: entries[key] for key in sorted(entries)})


def _readonly_assignment_count_mapping(
    value: object,
    field_name: str,
) -> Mapping[str | None, int]:
    if not isinstance(value, Mapping):
        raise StandardsValidationError(f"{field_name} must be a mapping.")

    entries: dict[str | None, int] = {}
    for key, count in value.items():
        if key is None:
            normalized_key = None
            key_name = "None"
        else:
            normalized_key = _required_text(key, f"{field_name} key")
            key_name = repr(normalized_key)
        entries[normalized_key] = _validate_nonnegative_int(
            count,
            f"{field_name}[{key_name}]",
        )
    return MappingProxyType(
        {
            key: entries[key]
            for key in sorted(entries, key=_assignment_id_sort_key)
        }
    )


def _normalize_standard_usage_counts(counts: StandardUsageCounts) -> None:
    object.__setattr__(
        counts,
        "standard_id",
        _required_text(counts.standard_id, "standard_id"),
    )
    object.__setattr__(
        counts,
        "total",
        _validate_nonnegative_int(counts.total, "total"),
    )
    object.__setattr__(
        counts,
        "by_usage_type",
        _readonly_text_count_mapping(counts.by_usage_type, "by_usage_type"),
    )
    object.__setattr__(
        counts,
        "by_module",
        _readonly_text_count_mapping(counts.by_module, "by_module"),
    )
    object.__setattr__(
        counts,
        "by_assignment_id",
        _readonly_assignment_count_mapping(
            counts.by_assignment_id,
            "by_assignment_id",
        ),
    )


def _readonly_standard_usage_counts_mapping(
    value: object,
) -> Mapping[str, StandardUsageCounts]:
    if not isinstance(value, Mapping):
        raise StandardsValidationError("by_standard_id must be a mapping.")

    entries: dict[str, StandardUsageCounts] = {}
    for key, counts in value.items():
        normalized_key = _required_text(key, "by_standard_id key")
        if not isinstance(counts, StandardUsageCounts):
            raise StandardsValidationError(
                "by_standard_id values must be StandardUsageCounts."
            )
        entries[normalized_key] = counts
    return MappingProxyType({key: entries[key] for key in sorted(entries)})


def _normalize_standards_usage_summary(
    summary: StandardsUsageSummary,
) -> None:
    object.__setattr__(
        summary,
        "total_events",
        _validate_nonnegative_int(summary.total_events, "total_events"),
    )
    object.__setattr__(
        summary,
        "by_standard_id",
        _readonly_standard_usage_counts_mapping(summary.by_standard_id),
    )


def summarize_standard_usage_events(
    events: Iterable[StandardUsageEvent],
) -> StandardsUsageSummary:
    """Summarize standards usage events without educational judgment."""
    total_events = 0
    totals_by_standard_id: Counter[str] = Counter()
    usage_type_counts: dict[str, Counter[str]] = {}
    module_counts: dict[str, Counter[str]] = {}
    assignment_id_counts: dict[str, Counter[str | None]] = {}

    for event in events:
        validated_event = validate_standard_usage_event(event)
        standard_id = validated_event.standard_id

        total_events += 1
        totals_by_standard_id[standard_id] += 1
        usage_type_counts.setdefault(standard_id, Counter())[
            validated_event.usage_type
        ] += 1
        module_counts.setdefault(standard_id, Counter())[
            validated_event.module
        ] += 1
        assignment_id_counts.setdefault(standard_id, Counter())[
            validated_event.assignment_id
        ] += 1

    return StandardsUsageSummary(
        total_events=total_events,
        by_standard_id=MappingProxyType(
            {
                standard_id: StandardUsageCounts(
                    standard_id=standard_id,
                    total=totals_by_standard_id[standard_id],
                    by_usage_type=usage_type_counts[standard_id],
                    by_module=module_counts[standard_id],
                    by_assignment_id=assignment_id_counts[standard_id],
                )
                for standard_id in sorted(totals_by_standard_id)
            }
        ),
    )


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


def standards_usage_dir(workspace_root: str | Path) -> Path:
    """Return the canonical standards usage directory for a workspace."""
    return standards_dir(workspace_root) / "usage"


def standards_usage_school_year_dir(
    workspace_root: str | Path,
    school_year: str,
) -> Path:
    """Return the canonical standards usage directory for a school year."""
    return standards_usage_dir(workspace_root) / _validate_school_year(
        school_year
    )


def standards_usage_class_dir(
    workspace_root: str | Path,
    school_year: str,
    class_id: str,
) -> Path:
    """Return the canonical standards usage directory for one class/year."""
    return standards_usage_school_year_dir(
        workspace_root,
        school_year,
    ) / _validate_usage_class_id(class_id)


def standards_usage_events_path(
    workspace_root: str | Path,
    school_year: str,
    class_id: str,
) -> Path:
    """Return the canonical standards usage events JSONL path."""
    return standards_usage_class_dir(
        workspace_root,
        school_year,
        class_id,
    ) / "events.jsonl"


def ensure_standards_dir(workspace_root: str | Path) -> Path:
    """Create and return the canonical standards directory."""
    directory = standards_dir(workspace_root)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ensure_standards_usage_class_dir(
    workspace_root: str | Path,
    school_year: str,
    class_id: str,
) -> Path:
    """Create and return the canonical standards usage class directory."""
    directory = standards_usage_class_dir(
        workspace_root,
        school_year,
        class_id,
    )
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


def load_standard_usage_events(
    path: str | Path,
) -> tuple[StandardUsageEvent, ...]:
    """Load standards usage events from a UTF-8 JSONL file."""
    source_path = Path(path)
    events: list[StandardUsageEvent] = []

    try:
        with source_path.open(encoding="utf-8") as usage_file:
            for line_number, line in enumerate(usage_file, start=1):
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as error:
                    raise StandardsUsageReadError(
                        source_path,
                        f"line {line_number}: invalid JSON: {error}",
                    ) from error

                if not isinstance(data, Mapping):
                    raise StandardsUsageReadError(
                        source_path,
                        f"line {line_number}: "
                        "top-level JSON value must be a mapping",
                    )

                try:
                    event = standard_usage_event_from_dict(
                        cast(Mapping[str, object], data)
                    )
                except (
                    StandardsValidationError,
                    KeyError,
                    TypeError,
                ) as error:
                    raise StandardsUsageReadError(
                        source_path,
                        f"line {line_number}: "
                        f"invalid standards usage event data: {error}",
                    ) from error
                events.append(event)
    except StandardsUsageReadError:
        raise
    except (OSError, UnicodeError) as error:
        raise StandardsUsageReadError(source_path, str(error)) from error

    return tuple(events)


def _serialize_standard_usage_event(event: StandardUsageEvent) -> str:
    return json.dumps(
        standard_usage_event_to_dict(event),
        sort_keys=True,
        separators=(",", ":"),
    )


def append_standard_usage_event(
    path: str | Path,
    event: StandardUsageEvent,
) -> None:
    """Append one standards usage event to a UTF-8 JSONL file."""
    target_path = Path(path)

    try:
        line = _serialize_standard_usage_event(event)
    except (StandardsValidationError, TypeError, ValueError) as error:
        raise StandardsUsageWriteError(
            target_path,
            f"invalid standards usage event data: {error}",
        ) from error

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        encoded_line = line.encode("utf-8")
        with target_path.open("ab+") as usage_file:
            usage_file.seek(0, os.SEEK_END)
            separator = b""
            if usage_file.tell() > 0:
                usage_file.seek(-1, os.SEEK_END)
                if usage_file.read(1) not in (b"\n", b"\r"):
                    separator = b"\n"
            usage_file.write(separator + encoded_line + b"\n")
    except (OSError, UnicodeError) as error:
        raise StandardsUsageWriteError(target_path, str(error)) from error


def write_standard_usage_events(
    path: str | Path,
    events: Iterable[StandardUsageEvent],
    *,
    overwrite: bool = False,
) -> None:
    """Atomically write standards usage events to a UTF-8 JSONL file."""
    target_path = Path(path)

    try:
        lines = [_serialize_standard_usage_event(event) for event in events]
        content = "".join(f"{line}\n" for line in lines)
    except (StandardsValidationError, TypeError, ValueError) as error:
        raise StandardsUsageWriteError(
            target_path,
            f"invalid standards usage event data: {error}",
        ) from error

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StandardsUsageWriteError(target_path, str(error)) from error

    if target_path.exists() and not overwrite:
        raise StandardsUsageWriteError(
            target_path,
            "target file already exists",
        )

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
        ) as usage_file:
            temp_path = Path(usage_file.name)
            usage_file.write(content)
            usage_file.flush()
            os.fsync(usage_file.fileno())

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
        raise StandardsUsageWriteError(target_path, message) from error


def load_workspace_standards_library(
    workspace_root: str | Path,
) -> StandardsLibrary:
    """Load the canonical shared standards library for a workspace."""
    path = standards_library_path(workspace_root)
    if not path.exists():
        return StandardsLibrary(standards=(), profiles=())
    return load_standards_library(path)


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


def load_workspace_standard_usage_events(
    workspace_root: str | Path,
    school_year: str,
    class_id: str,
) -> tuple[StandardUsageEvent, ...]:
    """Load canonical standards usage events for one class/year."""
    path = standards_usage_events_path(
        workspace_root,
        school_year,
        class_id,
    )
    if not path.exists():
        return ()
    return load_standard_usage_events(path)


def summarize_workspace_standard_usage_events(
    workspace_root: str | Path,
    school_year: str,
    class_id: str,
) -> StandardsUsageSummary:
    """Load and summarize canonical workspace usage events for one class/year."""
    return summarize_standard_usage_events(
        load_workspace_standard_usage_events(
            workspace_root,
            school_year,
            class_id,
        )
    )


def append_workspace_standard_usage_event(
    workspace_root: str | Path,
    event: StandardUsageEvent,
) -> None:
    """Append one event to its canonical workspace usage ledger."""
    fallback_path = standards_usage_dir(workspace_root) / "events.jsonl"
    try:
        validated_event = validate_standard_usage_event(event)
    except StandardsValidationError as error:
        raise StandardsUsageWriteError(
            fallback_path,
            f"invalid standards usage event data: {error}",
        ) from error

    append_standard_usage_event(
        standards_usage_events_path(
            workspace_root,
            validated_event.school_year,
            validated_event.class_id,
        ),
        validated_event,
    )


def write_workspace_standard_usage_events(
    workspace_root: str | Path,
    school_year: str,
    class_id: str,
    events: Iterable[StandardUsageEvent],
    *,
    overwrite: bool = False,
) -> None:
    """Write canonical workspace standards usage events for one class/year."""
    validated_school_year = _validate_school_year(school_year)
    validated_class_id = _validate_usage_class_id(class_id)
    target_path = standards_usage_events_path(
        workspace_root,
        validated_school_year,
        validated_class_id,
    )

    try:
        materialized_events = tuple(events)
        for index, event in enumerate(materialized_events):
            validate_standard_usage_event(event)
            if event.school_year != validated_school_year:
                raise StandardsValidationError(
                    f"events[{index}].school_year must match "
                    f"target school_year {validated_school_year!r}."
                )
            if event.class_id != validated_class_id:
                raise StandardsValidationError(
                    f"events[{index}].class_id must match "
                    f"target class_id {validated_class_id!r}."
                )
    except (StandardsValidationError, TypeError) as error:
        raise StandardsUsageWriteError(
            target_path,
            f"invalid standards usage event data: {error}",
        ) from error

    write_standard_usage_events(
        target_path,
        materialized_events,
        overwrite=overwrite,
    )
