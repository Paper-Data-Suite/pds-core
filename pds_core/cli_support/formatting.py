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
