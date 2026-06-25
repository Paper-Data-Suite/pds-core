"""Module-facing standards selection and display helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    filter_standard_definitions,
    filter_standards_profiles,
    find_standard_definition,
    find_standards_profile,
    load_workspace_standards_library,
    validate_profile_standard_selection,
)


@dataclass(frozen=True, slots=True)
class StandardSelectionItem:
    """Display-ready standard metadata with a durable storage ID."""

    standard_id: str
    label: str
    code: str
    short_name: str
    source: str
    subject: str | None = None
    course: str | None = None
    domain: str | None = None
    active: bool = True
    available_modules: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileSelectionItem:
    """Display-ready profile metadata with a durable storage ID."""

    profile_id: str
    label: str
    title: str | None = None
    source: str | None = None
    subject: str | None = None
    course: str | None = None
    standard_count: int = 0


def load_standards_for_selection(workspace_root: str | Path) -> StandardsLibrary:
    """Load the active workspace standards library for read-only selection."""
    return load_workspace_standards_library(workspace_root)


def format_standard_for_display(definition: StandardDefinition) -> str:
    """Return a teacher-readable label for one standard definition."""
    label = " | ".join(
        (
            definition.standard_id,
            definition.code,
            definition.short_name,
            definition.source,
        )
    )
    if not definition.active:
        label = f"{label} [inactive]"
    return label


def format_profile_for_display(profile: StandardsProfile) -> str:
    """Return a teacher-readable label for one standards profile."""
    parts = [profile.profile_id]
    if profile.title is not None:
        parts.append(profile.title)
    if profile.source is not None:
        parts.append(profile.source)
    if profile.subject is not None:
        parts.append(profile.subject)
    if profile.course is not None:
        parts.append(profile.course)
    parts.append(_format_count(profile.standards))
    return " | ".join(parts)


def list_profiles_for_selection(
    library: StandardsLibrary,
    *,
    subject: str | None = None,
    course: str | None = None,
    source: str | None = None,
) -> tuple[ProfileSelectionItem, ...]:
    """Return display-ready profiles sorted by durable profile ID."""
    profiles = sorted(
        filter_standards_profiles(
            library,
            subject=subject,
            course=course,
            source=source,
        ),
        key=lambda profile: profile.profile_id,
    )
    return tuple(_profile_selection_item(profile) for profile in profiles)


def list_standards_for_selection(
    library: StandardsLibrary,
    *,
    subject: str | None = None,
    course: str | None = None,
    source: str | None = None,
    domain: str | None = None,
    available_module: str | None = None,
    active: bool | None = True,
) -> tuple[StandardSelectionItem, ...]:
    """Return display-ready standards sorted by durable standard ID."""
    normalized_course = _optional_filter_text(course, "course")
    definitions = filter_standard_definitions(
        library,
        subject=subject,
        source=source,
        domain=domain,
        active=active,
        available_module=available_module,
    )
    if normalized_course is not None:
        definitions = tuple(
            definition
            for definition in definitions
            if definition.course == normalized_course
        )
    return tuple(
        _standard_selection_item(definition)
        for definition in sorted(
            definitions,
            key=lambda definition: definition.standard_id,
        )
    )


def list_standards_for_profile_selection(
    library: StandardsLibrary,
    profile_id: str,
    *,
    active: bool | None = True,
    available_module: str | None = None,
) -> tuple[StandardSelectionItem, ...]:
    """Return profile-member standards in profile order."""
    if active is not None and not isinstance(active, bool):
        raise StandardsValidationError("active must be a boolean or None.")
    normalized_available_module = _optional_filter_text(
        available_module,
        "available_module",
    )
    profile = _require_profile(library, profile_id)

    items: list[StandardSelectionItem] = []
    for standard_id in profile.standards:
        definition = find_standard_definition(library, standard_id)
        if definition is None:
            raise StandardsValidationError(
                f"profile_id {profile.profile_id!r} references unknown "
                f"standard_id {standard_id!r}."
            )
        if active is not None and definition.active is not active:
            continue
        if (
            normalized_available_module is not None
            and normalized_available_module not in definition.available_modules
        ):
            continue
        items.append(_standard_selection_item(definition))
    return tuple(items)


def resolve_profile_selection(
    library: StandardsLibrary,
    profile_id: str,
) -> ProfileSelectionItem:
    """Resolve one durable profile ID to display-ready metadata."""
    return _profile_selection_item(_require_profile(library, profile_id))


def resolve_standard_selection(
    library: StandardsLibrary,
    standard_id: str,
) -> StandardSelectionItem:
    """Resolve one durable standard ID to display-ready metadata."""
    return _standard_selection_item(_require_standard(library, standard_id))


def resolve_profile_standard_selection(
    library: StandardsLibrary,
    *,
    profile_id: str,
    selected_standard_ids: Iterable[str],
) -> tuple[StandardSelectionItem, ...]:
    """Validate selected profile standards and return display-ready items."""
    validated_standard_ids = validate_profile_standard_selection(
        library,
        profile_id=profile_id,
        selected_standard_ids=selected_standard_ids,
    )
    return tuple(
        _standard_selection_item(_require_standard(library, standard_id))
        for standard_id in validated_standard_ids
    )


def _profile_selection_item(profile: StandardsProfile) -> ProfileSelectionItem:
    return ProfileSelectionItem(
        profile_id=profile.profile_id,
        label=format_profile_for_display(profile),
        title=profile.title,
        source=profile.source,
        subject=profile.subject,
        course=profile.course,
        standard_count=len(profile.standards),
    )


def _standard_selection_item(
    definition: StandardDefinition,
) -> StandardSelectionItem:
    return StandardSelectionItem(
        standard_id=definition.standard_id,
        label=format_standard_for_display(definition),
        code=definition.code,
        short_name=definition.short_name,
        source=definition.source,
        subject=definition.subject,
        course=definition.course,
        domain=definition.domain,
        active=definition.active,
        available_modules=definition.available_modules,
    )


def _require_profile(
    library: StandardsLibrary,
    profile_id: str,
) -> StandardsProfile:
    profile = find_standards_profile(library, profile_id)
    if profile is None:
        normalized_profile_id = _required_text(profile_id, "profile_id")
        raise StandardsValidationError(
            f"profile_id {normalized_profile_id!r} does not exist."
        )
    return profile


def _require_standard(
    library: StandardsLibrary,
    standard_id: str,
) -> StandardDefinition:
    definition = find_standard_definition(library, standard_id)
    if definition is None:
        normalized_standard_id = _required_text(standard_id, "standard_id")
        raise StandardsValidationError(
            f"standard_id {normalized_standard_id!r} does not exist."
        )
    return definition


def _optional_filter_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise StandardsValidationError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise StandardsValidationError(f"{field_name} must not be blank.")
    return normalized


def _format_count(values: tuple[str, ...]) -> str:
    count = len(values)
    noun = "standard" if count == 1 else "standards"
    return f"{count} {noun}"


__all__ = [
    "ProfileSelectionItem",
    "StandardSelectionItem",
    "format_profile_for_display",
    "format_standard_for_display",
    "list_profiles_for_selection",
    "list_standards_for_profile_selection",
    "list_standards_for_selection",
    "load_standards_for_selection",
    "resolve_profile_selection",
    "resolve_profile_standard_selection",
    "resolve_standard_selection",
]
