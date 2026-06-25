"""Output formatting helpers for CLI command handlers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TextIO

from pds_core.standards import StandardDefinition, StandardsProfile


_EMPTY = "-"


def display(value: str | None) -> str:
    return value if value else _EMPTY


def format_tuple(values: tuple[str, ...], separator: str) -> str | None:
    if not values:
        return None
    return separator.join(values)


def print_values(values: Sequence[str], empty_message: str, stdout: TextIO) -> int:
    if not values:
        print(empty_message, file=stdout)
        return 0
    for value in values:
        print(value, file=stdout)
    return 0


def compact_standard_row(definition: StandardDefinition) -> str:
    status = "active" if definition.active else "inactive"
    return " | ".join(
        (
            definition.standard_id,
            definition.code,
            definition.short_name,
            definition.description,
            definition.source,
            display(definition.subject),
            display(definition.course),
            display(definition.domain),
            status,
        )
    )


def compact_profile_row(profile: StandardsProfile) -> str:
    return " | ".join(
        (
            profile.profile_id,
            display(profile.title),
            display(profile.subject),
            display(profile.course),
            display(profile.source),
            f"{len(profile.standards)} standards",
        )
    )


def description_preview(description: str, length: int = 120) -> str:
    if len(description) <= length:
        return description
    return f"{description[: length - 3].rstrip()}..."


def standard_heading(definition: StandardDefinition) -> str:
    return f"{definition.code} - {definition.short_name}"


def standard_metadata(definition: StandardDefinition) -> str:
    status = "Active" if definition.active else "Inactive"
    return " | ".join(
        value
        for value in (
            f"Source: {definition.source}",
            f"Subject: {definition.subject}" if definition.subject else None,
            f"Course: {definition.course}" if definition.course else None,
            f"Domain: {definition.domain}" if definition.domain else None,
            status,
        )
        if value is not None
    )


def readable_standard_block(
    definition: StandardDefinition,
    *,
    index: int | None = None,
    preview: bool = True,
    indent: str = "",
) -> tuple[str, ...]:
    prefix = f"{index}. " if index is not None else ""
    description = (
        description_preview(definition.description)
        if preview
        else definition.description
    )
    return (
        f"{indent}{prefix}{standard_heading(definition)}",
        f"{indent}   ID: {definition.standard_id}",
        f"{indent}   Description: {description}",
        f"{indent}   {standard_metadata(definition)}",
    )


def profile_metadata(profile: StandardsProfile) -> str:
    return " | ".join(
        value
        for value in (
            f"Subject: {profile.subject}" if profile.subject else None,
            f"Course: {profile.course}" if profile.course else None,
            f"Source: {profile.source}" if profile.source else None,
            f"{len(profile.standards)} standards",
        )
        if value is not None
    )


def readable_profile_block(
    profile: StandardsProfile,
    *,
    index: int | None = None,
) -> tuple[str, ...]:
    prefix = f"{index}. " if index is not None else ""
    title = profile.title or profile.profile_id
    lines = [
        f"{prefix}{title}",
        f"   ID: {profile.profile_id}",
    ]
    if profile.description:
        lines.append(f"   Description: {profile.description}")
    metadata = profile_metadata(profile)
    if metadata:
        lines.append(f"   {metadata}")
    return tuple(lines)
