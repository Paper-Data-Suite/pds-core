from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pds_core.academic_period_queries import (
    AcademicPeriodLookupError,
    find_academic_period,
    get_academic_period,
    list_academic_period_ancestors,
    list_academic_period_descendants,
    list_academic_periods,
    list_academic_periods_by_lifecycle,
    list_academic_periods_by_type,
    list_academic_periods_containing_date,
    list_child_academic_periods,
    list_root_academic_periods,
)
from pds_core.academic_periods import (
    ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
    ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
    AcademicPeriod,
    AcademicPeriodCalendar,
    AcademicPeriodValidationError,
)


def _period(
    period_id: str,
    *,
    parent: str | None = None,
    sequence: int = 1,
    start: date = date(2026, 9, 1),
    end: date = date(2027, 6, 1),
    period_type: str = "semester",
    lifecycle: str = "active",
) -> AcademicPeriod:
    return AcademicPeriod(
        period_id=period_id,
        period_type=period_type,  # type: ignore[arg-type]
        label=period_id,
        start_date=start,
        end_date=end,
        parent_period_id=parent,
        sequence=sequence,
        lifecycle=lifecycle,  # type: ignore[arg-type]
    )


def _calendar(*periods: AcademicPeriod) -> AcademicPeriodCalendar:
    timestamp = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return AcademicPeriodCalendar(
        schema_version=ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
        record_type=ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
        school_year="2026-2027",
        calendar_revision=1,
        created_at=timestamp,
        updated_at=timestamp,
        periods=periods,
    )


def test_hierarchy_queries_use_display_order() -> None:
    calendar = _calendar(
        _period("child_b", parent="root_b", sequence=2),
        _period("root_b", sequence=2),
        _period("grandchild", parent="child_a", sequence=1),
        _period("root_a", sequence=1, lifecycle="planned"),
        _period("child_a", parent="root_b", sequence=1),
    )

    assert [item.period_id for item in list_academic_periods(calendar)] == [
        "root_a",
        "root_b",
        "child_a",
        "grandchild",
        "child_b",
    ]
    assert [item.period_id for item in list_root_academic_periods(calendar)] == [
        "root_a",
        "root_b",
    ]
    assert [
        item.period_id for item in list_child_academic_periods(calendar, "root_b")
    ] == ["child_a", "child_b"]
    assert [
        item.period_id
        for item in list_academic_period_ancestors(calendar, "grandchild")
    ] == ["child_a", "root_b"]
    assert [
        item.period_id
        for item in list_academic_period_descendants(calendar, "root_b")
    ] == ["child_a", "grandchild", "child_b"]
    assert [
        item.period_id
        for item in list_academic_periods_by_lifecycle(calendar, "planned")
    ] == ["root_a"]
    assert len(list_academic_periods_by_type(calendar, "semester")) == 5


def test_lookup_is_exact_and_missing_required_values_raise() -> None:
    calendar = _calendar(_period("mp1"))
    assert find_academic_period(calendar, "mp1") == calendar.periods[0]
    assert find_academic_period(calendar, "different") is None
    with pytest.raises(AcademicPeriodLookupError):
        get_academic_period(calendar, "different")
    with pytest.raises(AcademicPeriodLookupError):
        list_child_academic_periods(calendar, "different")
    with pytest.raises(AcademicPeriodValidationError):
        find_academic_period(calendar, "bad/id")


def test_date_containment_is_inclusive_overlapping_and_rejects_datetime() -> None:
    calendar = _calendar(
        _period("semester"),
        _period(
            "window",
            sequence=2,
            period_type="progress_window",
            start=date(2026, 10, 1),
            end=date(2026, 10, 31),
        ),
    )
    assert [
        item.period_id
        for item in list_academic_periods_containing_date(
            calendar, date(2026, 10, 1)
        )
    ] == ["semester", "window"]
    assert list_academic_periods_containing_date(calendar, date(2026, 7, 1)) == ()
    with pytest.raises(AcademicPeriodValidationError):
        list_academic_periods_containing_date(
            calendar, datetime(2026, 10, 1, tzinfo=timezone.utc)
        )


def test_empty_calendar_and_invalid_filters() -> None:
    calendar = _calendar()
    assert list_academic_periods(calendar) == ()
    assert list_root_academic_periods(calendar) == ()
    with pytest.raises(AcademicPeriodValidationError):
        list_academic_periods_by_type(calendar, "year")  # type: ignore[arg-type]
    with pytest.raises(AcademicPeriodValidationError):
        list_academic_periods_by_lifecycle(calendar, "open")  # type: ignore[arg-type]


def test_iterative_preorder_supports_hierarchy_deeper_than_recursion_limit() -> None:
    periods = tuple(
        _period(
            f"period_{index:04d}",
            parent=None if index == 0 else f"period_{index - 1:04d}",
        )
        for index in range(1200)
    )
    calendar = _calendar(*periods)

    all_periods = list_academic_periods(calendar)
    descendants = list_academic_period_descendants(calendar, "period_0000")

    assert len(all_periods) == 1200
    assert len(descendants) == 1199
    assert [period.period_id for period in all_periods] == [
        f"period_{index:04d}" for index in range(1200)
    ]
    assert [period.period_id for period in descendants] == [
        f"period_{index:04d}" for index in range(1, 1200)
    ]
