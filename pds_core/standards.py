"""Shared in-memory standards models and validation."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from typing import TypeVar, cast


class StandardsValidationError(ValueError):
    """Raised when shared standards metadata is invalid."""


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
