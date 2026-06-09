"""Shared identifier validation for Paper Data Suite."""

from __future__ import annotations

import re
from typing import Final

IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")


class IdentifierValidationError(ValueError):
    """Raised when an identifier is missing or unsafe."""


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    """Validate a path-safe and QR-safe identifier.

    Valid identifiers may contain only letters, numbers, underscores, and hyphens.
    """
    if not isinstance(value, str):
        raise IdentifierValidationError(f"{field_name} must be a string.")

    if value == "":
        raise IdentifierValidationError(f"{field_name} must not be empty.")

    if value != value.strip():
        raise IdentifierValidationError(
            f"{field_name} must not contain leading or trailing whitespace."
        )

    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise IdentifierValidationError(
            f"{field_name} must contain only letters, numbers, underscores, "
            "and hyphens."
        )

    return value


def is_valid_identifier(value: object) -> bool:
    """Return whether a value is a valid path-safe and QR-safe identifier."""
    if not isinstance(value, str):
        return False

    try:
        validate_identifier(value)
    except IdentifierValidationError:
        return False

    return True