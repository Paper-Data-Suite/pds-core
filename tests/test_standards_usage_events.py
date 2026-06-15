"""Tests for shared in-memory standards usage events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest

from pds_core.standards import (
    STANDARD_USAGE_TYPES,
    StandardUsageEvent,
    StandardsValidationError,
    validate_standard_usage_event,
)


def make_usage_event(**overrides: object) -> StandardUsageEvent:
    values: dict[str, object] = {
        "event_id": "evt_2026_000001",
        "standard_id": "njsls-ela:RL.CR.11-12.1",
        "school_year": "2026-2027",
        "class_id": "english12_p3",
        "module": "pds-scoreform",
        "usage_type": "assessed",
        "used_at": datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc),
        "assignment_id": "villainy_final_exam",
        "metadata": {"question_numbers": [1, 3, 5]},
    }
    values.update(overrides)
    return StandardUsageEvent(**cast(Any, values))


def test_standard_usage_event_accepts_valid_data() -> None:
    used_at = datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc)

    event = make_usage_event(used_at=used_at)

    assert event.event_id == "evt_2026_000001"
    assert event.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert event.school_year == "2026-2027"
    assert event.class_id == "english12_p3"
    assert event.module == "pds-scoreform"
    assert event.usage_type == "assessed"
    assert event.used_at is used_at
    assert event.assignment_id == "villainy_final_exam"
    assert event.metadata == {"question_numbers": [1, 3, 5]}


def test_standard_usage_event_preserves_punctuation_heavy_standard_id() -> None:
    event = make_usage_event(standard_id=" njsls-ela:RL.CR.11-12.1 ")

    assert event.standard_id == "njsls-ela:RL.CR.11-12.1"


def test_standard_usage_event_rejects_invalid_class_id() -> None:
    with pytest.raises(StandardsValidationError, match="class_id"):
        make_usage_event(class_id="english/12")


def test_standard_usage_event_rejects_invalid_assignment_id() -> None:
    with pytest.raises(StandardsValidationError, match="assignment_id"):
        make_usage_event(assignment_id="villainy final exam")


def test_standard_usage_event_allows_missing_assignment_id() -> None:
    event = make_usage_event(assignment_id=None)

    assert event.assignment_id is None


def test_standard_usage_event_rejects_unknown_usage_type() -> None:
    with pytest.raises(StandardsValidationError, match="usage_type"):
        make_usage_event(usage_type="mastered")


@pytest.mark.parametrize("usage_type", sorted(STANDARD_USAGE_TYPES))
def test_standard_usage_event_accepts_canonical_usage_types(
    usage_type: str,
) -> None:
    event = make_usage_event(usage_type=usage_type)

    assert event.usage_type == usage_type


def test_standard_usage_event_accepts_valid_school_year() -> None:
    event = make_usage_event(school_year="2027-2028")

    assert event.school_year == "2027-2028"


@pytest.mark.parametrize(
    "school_year",
    ["", " ", "2026", "2026-27", "2026/2027", "2026-2026", "2026-2028",
     "abcd-efgh"],
)
def test_standard_usage_event_rejects_invalid_school_year(
    school_year: str,
) -> None:
    with pytest.raises(StandardsValidationError, match="school_year"):
        make_usage_event(school_year=school_year)


def test_standard_usage_event_rejects_naive_used_at() -> None:
    with pytest.raises(StandardsValidationError, match="timezone-aware"):
        make_usage_event(used_at=datetime(2026, 6, 14, 10, 0))


def test_standard_usage_event_rejects_non_datetime_used_at() -> None:
    with pytest.raises(StandardsValidationError, match="datetime"):
        make_usage_event(used_at="2026-06-14T10:00:00Z")


def test_standard_usage_event_metadata_is_detached_from_input_mapping() -> None:
    metadata: dict[str, object] = {"source": "teacher"}

    event = make_usage_event(metadata=metadata)
    metadata["source"] = "changed"

    assert event.metadata == {"source": "teacher"}
    with pytest.raises(TypeError):
        event.metadata["source"] = "changed"  # type: ignore[index]


def test_standard_usage_event_rejects_non_mapping_metadata() -> None:
    with pytest.raises(StandardsValidationError, match="metadata"):
        make_usage_event(metadata=["not", "a", "mapping"])


def test_standard_usage_event_rejects_non_string_metadata_keys() -> None:
    with pytest.raises(StandardsValidationError, match="metadata keys"):
        make_usage_event(metadata={1: "question"})


@pytest.mark.parametrize(
    "field_name",
    ["event_id", "standard_id", "module"],
)
def test_standard_usage_event_rejects_blank_required_text(
    field_name: str,
) -> None:
    with pytest.raises(StandardsValidationError, match=field_name):
        make_usage_event(**{field_name: " "})


def test_validate_standard_usage_event_returns_validated_model() -> None:
    event = make_usage_event()

    assert validate_standard_usage_event(event) is event


def test_validate_standard_usage_event_rejects_wrong_type() -> None:
    with pytest.raises(StandardsValidationError, match="StandardUsageEvent"):
        validate_standard_usage_event(cast(Any, object()))
