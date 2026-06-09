"""Tests for shared identifier validation."""

from __future__ import annotations

import pytest

from pds_core.identifiers import (
    IdentifierValidationError,
    is_valid_identifier,
    validate_identifier,
)


@pytest.mark.parametrize(
    "identifier",
    [
        "english12_p4",
        "personal_narrative",
        "1001",
        "scoreform",
        "quillan",
        "lined-response-v1",
        "A",
        "abc-123_DEF",
    ],
)
def test_validate_identifier_accepts_valid_values(identifier: str) -> None:
    assert validate_identifier(identifier) == identifier


@pytest.mark.parametrize(
    "identifier",
    [
        "",
        " ",
        "English 12",
        " english12",
        "english12 ",
        "../english12",
        "classes/english12",
        r"C:\classes\english12",
        "english12;p4",
        "https://example.com",
        "personal|narrative",
        "aid=personal_narrative",
        "class.name",
        "class,name",
    ],
)
def test_validate_identifier_rejects_invalid_strings(identifier: str) -> None:
    with pytest.raises(IdentifierValidationError):
        validate_identifier(identifier)


@pytest.mark.parametrize(
    "value",
    [
        None,
        1001,
        1.5,
        True,
        ["english12_p4"],
        {"class_id": "english12_p4"},
    ],
)
def test_validate_identifier_rejects_non_strings(value: object) -> None:
    with pytest.raises(IdentifierValidationError, match="must be a string"):
        validate_identifier(value)  # type: ignore[arg-type]


def test_validate_identifier_error_mentions_field_name() -> None:
    with pytest.raises(IdentifierValidationError, match="class_id"):
        validate_identifier("English 12", "class_id")


@pytest.mark.parametrize(
    "identifier",
    [
        "english12_p4",
        "personal_narrative",
        "1001",
        "scoreform",
        "quillan",
        "lined-response-v1",
    ],
)
def test_is_valid_identifier_returns_true_for_valid_values(identifier: str) -> None:
    assert is_valid_identifier(identifier) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "English 12",
        "../english12",
        "classes/english12",
        r"C:\classes\english12",
        "personal|narrative",
        "aid=personal_narrative",
        None,
        1001,
    ],
)
def test_is_valid_identifier_returns_false_for_invalid_values(value: object) -> None:
    assert is_valid_identifier(value) is False