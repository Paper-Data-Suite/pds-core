"""Pure, module-neutral queries for validated academic-period calendars."""

from __future__ import annotations

from datetime import date, datetime

from pds_core.academic_periods import (
    AcademicPeriod,
    AcademicPeriodCalendar,
    AcademicPeriodLifecycle,
    AcademicPeriodRef,
    AcademicPeriodType,
    AcademicPeriodValidationError,
    is_academic_period_lifecycle,
    is_academic_period_type,
    validate_academic_period_calendar,
    validate_academic_period_ref,
)


class AcademicPeriodLookupError(LookupError):
    """Raised when one requested period cannot be resolved."""


def list_academic_periods(
    calendar: AcademicPeriodCalendar,
) -> tuple[AcademicPeriod, ...]:
    """Return every period in deterministic hierarchy display order."""
    validated = _calendar(calendar)
    by_parent = _by_parent(validated)
    return _preorder_periods(by_parent, by_parent.get(None, ()))


def find_academic_period(
    calendar: AcademicPeriodCalendar,
    period_id: str,
) -> AcademicPeriod | None:
    """Return one exact period, or ``None`` when it is not present."""
    validated = _calendar(calendar)
    requested_id = _period_id(validated, period_id)
    return next(
        (period for period in validated.periods if period.period_id == requested_id),
        None,
    )


def get_academic_period(
    calendar: AcademicPeriodCalendar,
    period_id: str,
) -> AcademicPeriod:
    """Return one exact period or raise :class:`AcademicPeriodLookupError`."""
    period = find_academic_period(calendar, period_id)
    if period is None:
        raise AcademicPeriodLookupError(f"academic period {period_id!r} was not found.")
    return period


def list_root_academic_periods(
    calendar: AcademicPeriodCalendar,
) -> tuple[AcademicPeriod, ...]:
    """Return root periods in deterministic sibling order."""
    validated = _calendar(calendar)
    return _by_parent(validated).get(None, ())


def list_child_academic_periods(
    calendar: AcademicPeriodCalendar,
    parent_period_id: str,
) -> tuple[AcademicPeriod, ...]:
    """Return the requested period's direct children in sibling order."""
    validated = _calendar(calendar)
    parent = get_academic_period(validated, parent_period_id)
    return _by_parent(validated).get(parent.period_id, ())


def list_academic_period_ancestors(
    calendar: AcademicPeriodCalendar,
    period_id: str,
) -> tuple[AcademicPeriod, ...]:
    """Return ancestors from the immediate parent toward the root."""
    validated = _calendar(calendar)
    current = get_academic_period(validated, period_id)
    by_id = {period.period_id: period for period in validated.periods}
    result: list[AcademicPeriod] = []
    while current.parent_period_id is not None:
        current = by_id[current.parent_period_id]
        result.append(current)
    return tuple(result)


def list_academic_period_descendants(
    calendar: AcademicPeriodCalendar,
    period_id: str,
) -> tuple[AcademicPeriod, ...]:
    """Return descendants in deterministic depth-first preorder."""
    validated = _calendar(calendar)
    parent = get_academic_period(validated, period_id)
    by_parent = _by_parent(validated)
    return _preorder_periods(by_parent, by_parent.get(parent.period_id, ()))


def list_academic_periods_by_type(
    calendar: AcademicPeriodCalendar,
    period_type: AcademicPeriodType,
) -> tuple[AcademicPeriod, ...]:
    """Return periods of one exact shared type in hierarchy display order."""
    if not is_academic_period_type(period_type):
        raise AcademicPeriodValidationError("period_type is invalid.")
    return tuple(
        period
        for period in list_academic_periods(calendar)
        if period.period_type == period_type
    )


def list_academic_periods_by_lifecycle(
    calendar: AcademicPeriodCalendar,
    lifecycle: AcademicPeriodLifecycle,
) -> tuple[AcademicPeriod, ...]:
    """Return periods with one exact lifecycle in hierarchy display order."""
    if not is_academic_period_lifecycle(lifecycle):
        raise AcademicPeriodValidationError("lifecycle is invalid.")
    return tuple(
        period
        for period in list_academic_periods(calendar)
        if period.lifecycle == lifecycle
    )


def list_academic_periods_containing_date(
    calendar: AcademicPeriodCalendar,
    target_date: date,
) -> tuple[AcademicPeriod, ...]:
    """Return all periods containing *target_date*, inclusively."""
    if not isinstance(target_date, date) or isinstance(target_date, datetime):
        raise AcademicPeriodValidationError("target_date must be a date, not datetime.")
    return tuple(
        period
        for period in list_academic_periods(calendar)
        if period.start_date <= target_date <= period.end_date
    )


def _calendar(calendar: AcademicPeriodCalendar) -> AcademicPeriodCalendar:
    if not isinstance(calendar, AcademicPeriodCalendar):
        raise AcademicPeriodValidationError(
            "calendar must be an AcademicPeriodCalendar."
        )
    return validate_academic_period_calendar(calendar)


def _period_id(calendar: AcademicPeriodCalendar, period_id: str) -> str:
    reference = validate_academic_period_ref(
        AcademicPeriodRef(school_year=calendar.school_year, period_id=period_id)
    )
    return reference.period_id


def _by_parent(
    calendar: AcademicPeriodCalendar,
) -> dict[str | None, tuple[AcademicPeriod, ...]]:
    collected: dict[str | None, list[AcademicPeriod]] = {}
    for period in calendar.periods:
        collected.setdefault(period.parent_period_id, []).append(period)
    return {
        parent_id: tuple(
            sorted(periods, key=lambda period: (period.sequence, period.period_id))
        )
        for parent_id, periods in collected.items()
    }


def _preorder_periods(
    by_parent: dict[str | None, tuple[AcademicPeriod, ...]],
    initial: tuple[AcademicPeriod, ...],
) -> tuple[AcademicPeriod, ...]:
    result: list[AcademicPeriod] = []
    stack = list(reversed(initial))
    while stack:
        period = stack.pop()
        result.append(period)
        stack.extend(reversed(by_parent.get(period.period_id, ())))
    return tuple(result)
