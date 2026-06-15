"""Tests for standards usage event dictionary helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardUsageEvent,
    StandardsValidationError,
    standard_usage_event_from_dict,
    standard_usage_event_to_dict,
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


def make_usage_event_data(**overrides: object) -> dict[str, object]:
    data = standard_usage_event_to_dict(make_usage_event())
    data.update(overrides)
    return data


def test_standard_usage_event_to_dict_serializes_all_fields() -> None:
    data = standard_usage_event_to_dict(make_usage_event())

    assert data == {
        "event_id": "evt_2026_000001",
        "standard_id": "njsls-ela:RL.CR.11-12.1",
        "school_year": "2026-2027",
        "class_id": "english12_p3",
        "module": "pds-scoreform",
        "usage_type": "assessed",
        "used_at": "2026-06-14T10:00:00+00:00",
        "assignment_id": "villainy_final_exam",
        "metadata": {"question_numbers": [1, 3, 5]},
    }
    assert isinstance(data["metadata"], dict)


def test_standard_usage_event_to_dict_includes_none_assignment_id() -> None:
    data = standard_usage_event_to_dict(make_usage_event(assignment_id=None))

    assert data["assignment_id"] is None


def test_standard_usage_event_to_dict_detaches_metadata_mapping() -> None:
    event = make_usage_event()

    data = standard_usage_event_to_dict(event)
    cast(dict[str, object], data["metadata"])["source"] = "changed"

    assert "source" not in event.metadata


def test_standard_usage_event_from_dict_builds_valid_model() -> None:
    data = make_usage_event_data(
        event_id=" evt_2026_000001 ",
        standard_id=" njsls-ela:RL.CR.11-12.1 ",
    )

    event = standard_usage_event_from_dict(data)

    assert event.event_id == "evt_2026_000001"
    assert event.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert event.class_id == "english12_p3"
    assert event.used_at == datetime(
        2026, 6, 14, 10, 0, tzinfo=timezone.utc
    )
    assert event.used_at.tzinfo is not None
    assert event.metadata == {"question_numbers": [1, 3, 5]}


def test_standard_usage_event_round_trips_through_dict() -> None:
    event = make_usage_event()

    result = standard_usage_event_from_dict(
        standard_usage_event_to_dict(event)
    )

    assert result == event


def test_standard_usage_event_from_dict_rejects_missing_required_keys() -> None:
    data = make_usage_event_data()
    del data["used_at"]

    with pytest.raises(StandardsValidationError, match=r"required key.*used_at"):
        standard_usage_event_from_dict(data)


def test_standard_usage_event_from_dict_rejects_unknown_keys() -> None:
    data = make_usage_event_data(schema_version=1)

    with pytest.raises(
        StandardsValidationError,
        match=r"unknown key.*schema_version",
    ):
        standard_usage_event_from_dict(data)


def test_standard_usage_event_from_dict_rejects_non_string_keys() -> None:
    data = cast(dict[Any, object], make_usage_event_data())
    data[1] = "unknown"

    with pytest.raises(StandardsValidationError, match="keys must be strings"):
        standard_usage_event_from_dict(cast(Any, data))


def test_standard_usage_event_from_dict_rejects_invalid_used_at_string() -> None:
    data = make_usage_event_data(used_at="not-a-date")

    with pytest.raises(StandardsValidationError, match="valid ISO datetime"):
        standard_usage_event_from_dict(data)


def test_standard_usage_event_from_dict_rejects_naive_used_at_string() -> None:
    data = make_usage_event_data(used_at="2026-06-14T10:00:00")

    with pytest.raises(StandardsValidationError, match="timezone-aware"):
        standard_usage_event_from_dict(data)


def test_standard_usage_event_from_dict_rejects_non_string_used_at() -> None:
    data = make_usage_event_data(used_at=123)

    with pytest.raises(StandardsValidationError, match="ISO datetime string"):
        standard_usage_event_from_dict(data)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("usage_type", "mastered"),
        ("school_year", "2026-2028"),
        ("class_id", "english/12"),
        ("assignment_id", "villainy final exam"),
    ],
)
def test_standard_usage_event_from_dict_reuses_model_validation(
    field_name: str,
    value: object,
) -> None:
    data = make_usage_event_data(**{field_name: value})

    with pytest.raises(StandardsValidationError, match=field_name):
        standard_usage_event_from_dict(data)


def test_standard_usage_event_from_dict_allows_missing_assignment_id() -> None:
    data = make_usage_event_data()
    del data["assignment_id"]

    event = standard_usage_event_from_dict(data)

    assert event.assignment_id is None


def test_standard_usage_event_from_dict_defaults_missing_metadata() -> None:
    data = make_usage_event_data()
    del data["metadata"]

    event = standard_usage_event_from_dict(data)

    assert event.metadata == {}


def test_standard_usage_event_from_dict_rejects_invalid_metadata() -> None:
    data = make_usage_event_data(metadata=["not", "a", "mapping"])

    with pytest.raises(StandardsValidationError, match="metadata"):
        standard_usage_event_from_dict(data)


def test_standard_usage_event_from_dict_rejects_non_string_metadata_keys() -> None:
    data = make_usage_event_data(metadata={1: "question"})

    with pytest.raises(StandardsValidationError, match="metadata keys"):
        standard_usage_event_from_dict(data)


def test_standard_usage_event_from_dict_rejects_non_mapping_input() -> None:
    with pytest.raises(StandardsValidationError, match="mapping"):
        standard_usage_event_from_dict(cast(Any, []))
