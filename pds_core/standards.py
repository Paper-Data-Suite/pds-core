"""Shared in-memory standards models and validation."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import TypeVar, cast


class StandardsValidationError(ValueError):
    """Raised when shared standards metadata is invalid."""


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
