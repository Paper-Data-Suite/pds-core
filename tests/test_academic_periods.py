from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone

import pytest

from pds_core.academic_periods import (
    ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
    ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
    ACADEMIC_PERIOD_LIFECYCLES,
    ACADEMIC_PERIOD_TYPES,
    AcademicPeriod,
    AcademicPeriodCalendar,
    AcademicPeriodLifecycle,
    AcademicPeriodRef,
    AcademicPeriodType,
    AcademicPeriodValidationError,
    academic_period_calendar_from_dict,
    academic_period_calendar_to_dict,
    academic_period_from_dict,
    academic_period_ref_from_dict,
    academic_period_ref_to_dict,
    academic_period_to_dict,
    is_academic_period_lifecycle,
    is_academic_period_type,
    validate_academic_period_calendar_transition,
    validate_academic_period_hierarchy,
)

UTC = timezone.utc


def period(
    period_id: str,
    *,
    period_type: AcademicPeriodType = "marking_period",
    label: str | None = None,
    start_date: date = date(2026, 9, 1),
    end_date: date = date(2027, 6, 1),
    parent_period_id: str | None = None,
    sequence: int = 10,
    lifecycle: AcademicPeriodLifecycle = "active",
) -> AcademicPeriod:
    return AcademicPeriod(
        period_id=period_id,
        period_type=period_type,
        label=period_id if label is None else label,
        start_date=start_date,
        end_date=end_date,
        parent_period_id=parent_period_id,
        sequence=sequence,
        lifecycle=lifecycle,
    )


def calendar(
    *periods: AcademicPeriod,
    school_year: str = "2026-2027",
    revision: int = 1,
    created_at: datetime = datetime(2026, 7, 27, tzinfo=UTC),
    updated_at: datetime | None = None,
) -> AcademicPeriodCalendar:
    return AcademicPeriodCalendar(
        schema_version=ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
        record_type=ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
        school_year=school_year,
        calendar_revision=revision,
        created_at=created_at,
        updated_at=updated_at or created_at,
        periods=periods,
    )


def test_reference_is_validated_hashable_frozen_slotted_and_round_trips() -> None:
    value = AcademicPeriodRef("2026-2027", "mp1")
    assert value == AcademicPeriodRef("2026-2027", "mp1")
    assert len({value, AcademicPeriodRef("2027-2028", "mp1")}) == 2
    assert academic_period_ref_to_dict(value) == {
        "school_year": "2026-2027",
        "period_id": "mp1",
    }
    assert academic_period_ref_from_dict(academic_period_ref_to_dict(value)) == value
    with pytest.raises((FrozenInstanceError, AttributeError)):
        value.period_id = "other"  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        value.extra = True  # type: ignore[attr-defined]


@pytest.mark.parametrize("school_year", ["2026-2028", "bad", 2026])
def test_reference_rejects_invalid_school_year(school_year: object) -> None:
    with pytest.raises(AcademicPeriodValidationError, match="school_year"):
        AcademicPeriodRef(school_year, "mp1")  # type: ignore[arg-type]


@pytest.mark.parametrize("period_id", ["", " mp1", "mp/1", 1])
def test_reference_rejects_invalid_period_id(period_id: object) -> None:
    with pytest.raises(AcademicPeriodValidationError, match="period_id"):
        AcademicPeriodRef("2026-2027", period_id)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "data, message",
    [
        ({"school_year": "2026-2027"}, "missing"),
        (
            {"school_year": "2026-2027", "period_id": "mp1", "extra": 1},
            "unknown",
        ),
        ({"school_year": "2026-2027", 1: "mp1"}, "keys"),
        ([], "object"),
    ],
)
def test_reference_mapping_is_exact(data: object, message: str) -> None:
    with pytest.raises(AcademicPeriodValidationError, match=message):
        academic_period_ref_from_dict(data)


@pytest.mark.parametrize("value", sorted(ACADEMIC_PERIOD_TYPES))
def test_all_period_types_are_accepted(value: str) -> None:
    assert is_academic_period_type(value)
    period("p", period_type=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", sorted(ACADEMIC_PERIOD_LIFECYCLES))
def test_all_lifecycles_are_accepted(value: str) -> None:
    assert is_academic_period_lifecycle(value)
    period("p", lifecycle=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["SEMESTER", " semester", "", "other", None, 1])
def test_period_type_predicate_and_constructor_reject_non_vocabulary(
    value: object,
) -> None:
    assert not is_academic_period_type(value)
    with pytest.raises(AcademicPeriodValidationError, match="period_type"):
        period("p", period_type=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["ACTIVE", "active ", "", "other", None, 1])
def test_lifecycle_predicate_and_constructor_reject_non_vocabulary(
    value: object,
) -> None:
    assert not is_academic_period_lifecycle(value)
    with pytest.raises(AcademicPeriodValidationError, match="lifecycle"):
        period("p", lifecycle=value)  # type: ignore[arg-type]


def test_period_supports_unicode_one_day_and_is_hashable_frozen_slotted() -> None:
    value = period(
        "custom_1",
        period_type="custom",
        label="Exámenes – 春",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 2),
        lifecycle="planned",
    )
    assert hash(value)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        value.label = "Changed"  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        value.extra = True  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "label", ["", "   ", " leading", "trailing ", "a\nb", "a\rb", "a\tb", "a\0b", "a\u2028b", "a\u2029b"]
)
def test_period_rejects_invalid_labels(label: str) -> None:
    with pytest.raises(AcademicPeriodValidationError, match="label"):
        period("p", label=label)


def test_period_rejects_reversed_dates_and_datetime_values() -> None:
    with pytest.raises(AcademicPeriodValidationError, match="start_date"):
        period("p", start_date=datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(AcademicPeriodValidationError, match="end_date"):
        period("p", end_date=datetime(2027, 6, 1, tzinfo=UTC))
    with pytest.raises(AcademicPeriodValidationError, match="later"):
        period("p", start_date=date(2027, 1, 2), end_date=date(2027, 1, 1))


@pytest.mark.parametrize("parent", ["", " bad", "other/year", 1])
def test_period_rejects_invalid_parent(parent: object) -> None:
    with pytest.raises(AcademicPeriodValidationError, match="parent_period_id"):
        period("p", parent_period_id=parent)  # type: ignore[arg-type]


@pytest.mark.parametrize("sequence", [0, -1, True, 1.5, "1"])
def test_period_rejects_invalid_sequence(sequence: object) -> None:
    with pytest.raises(AcademicPeriodValidationError, match="sequence"):
        period("p", sequence=sequence)  # type: ignore[arg-type]


def test_period_exact_mapping_and_round_trip() -> None:
    value = period(
        "mp1",
        label="Marking Period 1",
        start_date=date(2026, 9, 3),
        end_date=date(2026, 11, 6),
        parent_period_id="semester_1",
        lifecycle="closed",
    )
    expected = {
        "period_id": "mp1",
        "period_type": "marking_period",
        "label": "Marking Period 1",
        "start_date": "2026-09-03",
        "end_date": "2026-11-06",
        "parent_period_id": "semester_1",
        "sequence": 10,
        "lifecycle": "closed",
    }
    assert academic_period_to_dict(value) == expected
    assert academic_period_from_dict(expected) == value
    root_output = academic_period_to_dict(period("root"))
    assert "parent_period_id" in root_output
    assert root_output["parent_period_id"] is None


@pytest.mark.parametrize(
    "field, value",
    [
        ("start_date", "2026-02-30"),
        ("end_date", "09/01/2026"),
        ("sequence", True),
        ("parent_period_id", {}),
        ("label", 1),
    ],
)
def test_period_mapping_rejects_bad_primitive(field: str, value: object) -> None:
    data = academic_period_to_dict(period("p"))
    data[field] = value
    with pytest.raises(AcademicPeriodValidationError, match=field):
        academic_period_from_dict(data)


def test_period_mapping_rejects_missing_extra_and_non_mapping() -> None:
    data = academic_period_to_dict(period("p"))
    del data["label"]
    with pytest.raises(AcademicPeriodValidationError, match="missing"):
        academic_period_from_dict(data)
    data = academic_period_to_dict(period("p"))
    data["extension"] = True
    with pytest.raises(AcademicPeriodValidationError, match="unknown"):
        academic_period_from_dict(data)
    with pytest.raises(AcademicPeriodValidationError, match="object"):
        academic_period_from_dict([data])


def test_valid_hierarchies_and_explicit_non_rules() -> None:
    semester = period("semester", period_type="semester", sequence=10)
    mp = period(
        "mp",
        end_date=date(2027, 1, 1),
        parent_period_id="semester",
        sequence=10,
    )
    progress = period(
        "progress",
        period_type="progress_window",
        end_date=date(2026, 10, 1),
        parent_period_id="mp",
        sequence=10,
    )
    quarter = period("quarter", period_type="quarter", sequence=20)
    trimester = period("trimester", period_type="trimester", sequence=30)
    custom = period("custom", period_type="custom", sequence=40)
    assert validate_academic_period_hierarchy("2026-2027", []) == ()
    result = validate_academic_period_hierarchy(
        "2026-2027", [trimester, progress, quarter, mp, custom, semester]
    )
    assert [item.period_id for item in result] == sorted(
        ["trimester", "progress", "quarter", "mp", "custom", "semester"]
    )
    # Parallel roots overlap and even contain each other by date without hierarchy.
    assert all(item.lifecycle == "active" for item in result)


def test_equal_parent_child_ranges_and_sequences_under_different_parents() -> None:
    parent_a = period("a", sequence=10)
    parent_b = period("b", sequence=20)
    child_a = period("a_child", parent_period_id="a", sequence=10)
    child_b = period("b_child", parent_period_id="b", sequence=10)
    assert len(
        validate_academic_period_hierarchy(
            "2026-2027", [child_b, parent_b, child_a, parent_a]
        )
    ) == 4


@pytest.mark.parametrize("periods", [None, 1, object()])
def test_hierarchy_rejects_non_iterable_period_collection(
    periods: object,
) -> None:
    with pytest.raises(AcademicPeriodValidationError, match="iterable"):
        validate_academic_period_hierarchy(
            "2026-2027",
            periods,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "periods, message",
    [
        ([period("a"), period("a", sequence=20)], "duplicate period_id"),
        ([period("a", parent_period_id="missing")], "missing parent"),
        ([period("a", parent_period_id="a")], "own parent"),
        (
            [period("a", parent_period_id="b"), period("b", parent_period_id="a")],
            "cycle",
        ),
        (
            [
                period("a", parent_period_id="b"),
                period("b", parent_period_id="c"),
                period("c", parent_period_id="a"),
                period("root", sequence=20),
            ],
            "cycle",
        ),
        ([period("a"), period("b")], "duplicate sibling sequence"),
        (
            [
                period("a"),
                period("b", sequence=20),
                period("a1", parent_period_id="a"),
                period("a2", parent_period_id="a"),
            ],
            "duplicate sibling sequence",
        ),
    ],
)
def test_invalid_hierarchies(
    periods: list[AcademicPeriod], message: str
) -> None:
    with pytest.raises(AcademicPeriodValidationError, match=message):
        validate_academic_period_hierarchy("2026-2027", periods)


def test_hierarchy_rejects_parent_containment_failures() -> None:
    parent = period(
        "parent", start_date=date(2026, 9, 2), end_date=date(2027, 5, 31)
    )

    early_child = period(
        "early",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 5, 31),
        parent_period_id="parent",
        sequence=10,
    )
    late_child = period(
        "late",
        start_date=date(2026, 9, 2),
        end_date=date(2027, 6, 1),
        parent_period_id="parent",
        sequence=10,
    )

    for child in (early_child, late_child):
        with pytest.raises(AcademicPeriodValidationError, match="contained"):
            validate_academic_period_hierarchy("2026-2027", [parent, child])


def test_unrelated_date_containment_does_not_infer_hierarchy() -> None:
    outer = period(
        "outer",
        period_type="semester",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 6, 1),
        sequence=10,
    )
    inner = period(
        "inner",
        period_type="custom",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 11, 1),
        sequence=20,
    )

    result = validate_academic_period_hierarchy(
        "2026-2027",
        [inner, outer],
    )

    assert all(item.parent_period_id is None for item in result)


@pytest.mark.parametrize(
    "boundary", [date(2025, 12, 31), date(2028, 1, 1)]
)
def test_hierarchy_rejects_dates_outside_named_years(boundary: date) -> None:
    with pytest.raises(AcademicPeriodValidationError, match="outside school_year"):
        validate_academic_period_hierarchy(
            "2026-2027", [period("p", start_date=boundary, end_date=boundary)]
        )
    with pytest.raises(AcademicPeriodValidationError, match="school_year"):
        validate_academic_period_hierarchy("2026-2028", [])


def test_calendar_is_immutable_defensive_ordered_json_safe_and_round_trips() -> None:
    caller_periods = [period("z", sequence=20), period("a", sequence=10)]
    value = AcademicPeriodCalendar(
        "1",
        "academic_period_calendar",
        "2026-2027",
        1,
        datetime(2026, 7, 27, 8, tzinfo=timezone(timedelta(hours=-4))),
        datetime(2026, 7, 28, 8, tzinfo=timezone(timedelta(hours=-4))),
        caller_periods,  # type: ignore[arg-type]
    )
    caller_periods.clear()
    assert [item.period_id for item in value.periods] == ["a", "z"]
    output = academic_period_calendar_to_dict(value)
    json.dumps(output, allow_nan=False)
    output_periods = output["periods"]
    assert isinstance(output_periods, list)
    output_periods.clear()
    assert len(value.periods) == 2
    assert academic_period_calendar_from_dict(
        academic_period_calendar_to_dict(value)
    ) == value
    with pytest.raises((FrozenInstanceError, AttributeError)):
        value.periods = ()  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        value.extra = True  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"schema_version": "2"}, "schema_version"),
        ({"record_type": "other"}, "record_type"),
        ({"calendar_revision": 0}, "calendar_revision"),
        ({"calendar_revision": True}, "calendar_revision"),
        ({"created_at": datetime(2026, 1, 1)}, "timezone-aware"),
        ({"updated_at": datetime(2026, 1, 1)}, "timezone-aware"),
    ],
)
def test_calendar_rejects_invalid_fields(
    changes: dict[str, object], message: str
) -> None:
    args: dict[str, object] = {
        "schema_version": "1",
        "record_type": "academic_period_calendar",
        "school_year": "2026-2027",
        "calendar_revision": 1,
        "created_at": datetime(2026, 7, 27, tzinfo=UTC),
        "updated_at": datetime(2026, 7, 27, tzinfo=UTC),
        "periods": (),
    }
    args.update(changes)
    with pytest.raises(AcademicPeriodValidationError, match=message):
        AcademicPeriodCalendar(**args)  # type: ignore[arg-type]


def test_calendar_rejects_timestamp_order_and_mapping_shape() -> None:
    with pytest.raises(AcademicPeriodValidationError, match="updated_at"):
        calendar(
            created_at=datetime(2026, 7, 28, tzinfo=UTC),
            updated_at=datetime(2026, 7, 27, tzinfo=UTC),
        )
    data = academic_period_calendar_to_dict(calendar())
    data["periods"] = {}
    with pytest.raises(AcademicPeriodValidationError, match="periods"):
        academic_period_calendar_from_dict(data)
    data = academic_period_calendar_to_dict(calendar())
    data["extra"] = 1
    with pytest.raises(AcademicPeriodValidationError, match="unknown"):
        academic_period_calendar_from_dict(data)


def test_calendar_parses_numeric_offsets_and_z_but_rejects_naive_timestamps() -> None:
    data = academic_period_calendar_to_dict(calendar())
    data["created_at"] = "2026-07-27T08:00:00-04:00"
    data["updated_at"] = "2026-07-27T12:00:00Z"
    parsed = academic_period_calendar_from_dict(data)
    assert parsed.created_at.utcoffset() == timedelta(hours=-4)
    assert parsed.updated_at.utcoffset() == timedelta(0)
    data["updated_at"] = "2026-07-27T12:00:00"
    with pytest.raises(AcademicPeriodValidationError, match="timezone-aware"):
        academic_period_calendar_from_dict(data)


def test_transition_rejects_calendar_identity_and_order_changes() -> None:
    created = datetime(2026, 7, 27, tzinfo=UTC)
    previous = calendar(
        period("p"),
        revision=2,
        created_at=created,
        updated_at=created + timedelta(days=2),
    )
    candidates = [
        (
            calendar(
                period(
                    "p",
                    start_date=date(2027, 9, 1),
                    end_date=date(2028, 6, 1),
                ),
                school_year="2027-2028",
                revision=3,
                created_at=created,
                updated_at=created + timedelta(days=3),
            ),
            "school_year",
        ),
        (replace(previous, calendar_revision=2), "greater"),
        (replace(previous, calendar_revision=1), "greater"),
        (
            replace(
                previous,
                calendar_revision=3,
                created_at=created + timedelta(days=1),
            ),
            "created_at",
        ),
        (
            replace(
                previous,
                calendar_revision=3,
                updated_at=created + timedelta(days=1),
            ),
            "updated_at",
        ),
    ]
    for candidate, message in candidates:
        with pytest.raises(AcademicPeriodValidationError, match=message):
            validate_academic_period_calendar_transition(previous, candidate)


def test_transition_rejects_removal_and_existing_type_change() -> None:
    previous = calendar(period("p"))
    removed = calendar(revision=2, updated_at=previous.updated_at + timedelta(days=1))
    with pytest.raises(AcademicPeriodValidationError, match="removes"):
        validate_academic_period_calendar_transition(previous, removed)
    changed = calendar(
        period("p", period_type="quarter"),
        revision=2,
        updated_at=previous.updated_at + timedelta(days=1),
    )
    with pytest.raises(AcademicPeriodValidationError, match="period_type"):
        validate_academic_period_calendar_transition(previous, changed)


def test_transition_allows_editable_fields_addition_and_correction_pattern() -> None:
    anchor = period("anchor", period_type="custom", sequence=10)
    old = period(
        "old",
        period_type="semester",
        parent_period_id="anchor",
        lifecycle="active",
    )
    previous = calendar(anchor, old)
    corrected_old = period(
        "old",
        period_type="semester",
        label="Old (cancelled)",
        start_date=date(2026, 9, 2),
        end_date=date(2027, 5, 31),
        parent_period_id=None,
        sequence=20,
        lifecycle="cancelled",
    )
    replacement = period(
        "replacement",
        period_type="quarter",
        label="Corrected period",
        start_date=date(2026, 9, 2),
        end_date=date(2027, 5, 31),
        sequence=30,
        lifecycle="planned",
    )
    candidate = calendar(
        anchor,
        corrected_old,
        replacement,
        revision=3,
        updated_at=previous.updated_at + timedelta(days=2),
    )
    assert validate_academic_period_calendar_transition(previous, candidate) == candidate
