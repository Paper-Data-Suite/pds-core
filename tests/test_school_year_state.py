"""Tests for shared active school-year workspace state."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from pds_core.school_years import (
    SchoolYearState,
    SchoolYearStateError,
    close_school_year,
    get_active_school_year,
    load_school_year_state,
    open_school_year,
    school_year_state_path,
    validate_school_year,
)


OPENED_AT = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)
CLOSED_AT = datetime(2027, 6, 25, 15, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("school_year", ["2026-2027", "1999-2000"])
def test_validate_school_year_accepts_consecutive_years(school_year: str) -> None:
    assert validate_school_year(school_year) == school_year


@pytest.mark.parametrize(
    "school_year",
    ["2026", "2026-26", "2026-2028", "2027-2026", "abcd-efgh"],
)
def test_validate_school_year_rejects_invalid_years(school_year: str) -> None:
    with pytest.raises(ValueError, match="school_year"):
        validate_school_year(school_year)


def write_state_json(tmp_path: Path, data: object) -> Path:
    path = school_year_state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_school_year_state_path_is_canonical_and_has_no_side_effects(
    tmp_path: Path,
) -> None:
    path = school_year_state_path(tmp_path)

    assert path == tmp_path.resolve() / "settings" / "school_year.json"
    assert path.is_relative_to(tmp_path.resolve())
    assert not path.exists()
    assert not (tmp_path / "settings").exists()


def test_missing_school_year_state_returns_none(tmp_path: Path) -> None:
    assert load_school_year_state(tmp_path) is None
    assert get_active_school_year(tmp_path) is None


def test_open_school_year_writes_state_file(tmp_path: Path) -> None:
    state = open_school_year(
        tmp_path,
        "2026-2027",
        opened_at=OPENED_AT,
    )

    assert isinstance(state, SchoolYearState)
    assert state.active_school_year == "2026-2027"
    assert state.opened_at == OPENED_AT
    assert state.closed_at is None
    assert get_active_school_year(tmp_path) == "2026-2027"

    path = school_year_state_path(tmp_path)
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "active_school_year": "2026-2027",
        "opened_at": OPENED_AT.isoformat(),
        "closed_at": None,
    }


def test_load_school_year_state_round_trips_timezone_aware_datetimes(
    tmp_path: Path,
) -> None:
    opened = datetime(
        2026,
        8,
        28,
        9,
        0,
        tzinfo=timezone(timedelta(hours=-4)),
    )
    opened_state = open_school_year(
        tmp_path,
        "2026-2027",
        opened_at=opened,
    )

    loaded_state = load_school_year_state(tmp_path)

    assert loaded_state == opened_state
    assert loaded_state is not None
    assert loaded_state.opened_at.tzinfo is not None
    assert loaded_state.opened_at.utcoffset() == timedelta(hours=-4)


def test_close_school_year_writes_closed_state(tmp_path: Path) -> None:
    open_school_year(tmp_path, "2026-2027", opened_at=OPENED_AT)

    closed_state = close_school_year(tmp_path, closed_at=CLOSED_AT)

    assert closed_state.active_school_year == "2026-2027"
    assert closed_state.opened_at == OPENED_AT
    assert closed_state.closed_at == CLOSED_AT
    assert load_school_year_state(tmp_path) == closed_state
    assert get_active_school_year(tmp_path) is None


def test_opening_new_year_after_closing_previous_year_succeeds(
    tmp_path: Path,
) -> None:
    open_school_year(tmp_path, "2026-2027", opened_at=OPENED_AT)
    close_school_year(tmp_path, closed_at=CLOSED_AT)

    reopened_state = open_school_year(
        tmp_path,
        "2027-2028",
        opened_at=CLOSED_AT + timedelta(days=1),
    )

    assert reopened_state.active_school_year == "2027-2028"
    assert reopened_state.closed_at is None
    assert get_active_school_year(tmp_path) == "2027-2028"


def test_opening_same_school_year_while_open_returns_existing_state(
    tmp_path: Path,
) -> None:
    opened_state = open_school_year(
        tmp_path,
        "2026-2027",
        opened_at=OPENED_AT,
    )

    same_state = open_school_year(
        tmp_path,
        "2026-2027",
        opened_at=OPENED_AT + timedelta(days=1),
    )

    assert same_state == opened_state


def test_opening_different_year_while_open_fails_unless_overwrite(
    tmp_path: Path,
) -> None:
    open_school_year(tmp_path, "2026-2027", opened_at=OPENED_AT)

    with pytest.raises(SchoolYearStateError, match="already open"):
        open_school_year(
            tmp_path,
            "2027-2028",
            opened_at=OPENED_AT + timedelta(days=1),
        )

    replacement_state = open_school_year(
        tmp_path,
        "2027-2028",
        opened_at=OPENED_AT + timedelta(days=1),
        overwrite=True,
    )

    assert replacement_state.active_school_year == "2027-2028"
    assert get_active_school_year(tmp_path) == "2027-2028"


@pytest.mark.parametrize(
    "school_year",
    [
        "2025",
        "2025/2026",
        "25-26",
        "2025 - 2026",
        "2026-2025",
        "2025-2027",
    ],
)
def test_open_school_year_rejects_invalid_school_years(
    tmp_path: Path,
    school_year: str,
) -> None:
    with pytest.raises(SchoolYearStateError, match="school_year"):
        open_school_year(tmp_path, school_year, opened_at=OPENED_AT)

    assert not (tmp_path / "settings").exists()


def test_open_school_year_rejects_naive_opened_at(tmp_path: Path) -> None:
    with pytest.raises(SchoolYearStateError, match="timezone-aware"):
        open_school_year(
            tmp_path,
            "2026-2027",
            opened_at=datetime(2026, 8, 28, 9, 0),
        )


def test_close_school_year_rejects_naive_closed_at(tmp_path: Path) -> None:
    open_school_year(tmp_path, "2026-2027", opened_at=OPENED_AT)

    with pytest.raises(SchoolYearStateError, match="timezone-aware"):
        close_school_year(
            tmp_path,
            closed_at=datetime(2027, 6, 25, 15, 0),
        )


def test_close_school_year_rejects_closed_at_before_opened_at(
    tmp_path: Path,
) -> None:
    open_school_year(tmp_path, "2026-2027", opened_at=OPENED_AT)

    with pytest.raises(SchoolYearStateError, match="earlier"):
        close_school_year(
            tmp_path,
            closed_at=OPENED_AT - timedelta(seconds=1),
        )


def test_close_school_year_requires_existing_open_state(tmp_path: Path) -> None:
    with pytest.raises(SchoolYearStateError, match="No school year"):
        close_school_year(tmp_path, closed_at=CLOSED_AT)


def test_close_school_year_rejects_already_closed_state(tmp_path: Path) -> None:
    open_school_year(tmp_path, "2026-2027", opened_at=OPENED_AT)
    close_school_year(tmp_path, closed_at=CLOSED_AT)

    with pytest.raises(SchoolYearStateError, match="already closed"):
        close_school_year(tmp_path, closed_at=CLOSED_AT)


@pytest.mark.parametrize(
    "raw_content",
    [
        "{not json}",
        "[]",
        '"state"',
    ],
)
def test_load_school_year_state_rejects_malformed_json_files(
    tmp_path: Path,
    raw_content: str,
) -> None:
    path = school_year_state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(raw_content, encoding="utf-8")

    with pytest.raises(SchoolYearStateError):
        load_school_year_state(tmp_path)

    assert path.read_text(encoding="utf-8") == raw_content


@pytest.mark.parametrize(
    "data",
    [
        {"opened_at": OPENED_AT.isoformat(), "closed_at": None},
        {"active_school_year": "2026-2027", "closed_at": None},
        {
            "active_school_year": "2026-2027",
            "opened_at": OPENED_AT.isoformat(),
        },
        {
            "active_school_year": "2026-2027",
            "opened_at": "not-a-datetime",
            "closed_at": None,
        },
        {
            "active_school_year": "2026-2027",
            "opened_at": datetime(2026, 8, 28, 9, 0).isoformat(),
            "closed_at": None,
        },
        {
            "active_school_year": "2026-2027",
            "opened_at": OPENED_AT.isoformat(),
            "closed_at": "not-a-datetime",
        },
        {
            "active_school_year": "2026-2027",
            "opened_at": OPENED_AT.isoformat(),
            "closed_at": (OPENED_AT - timedelta(seconds=1)).isoformat(),
        },
        {
            "active_school_year": 2026,
            "opened_at": OPENED_AT.isoformat(),
            "closed_at": None,
        },
        {
            "active_school_year": "2026-2027",
            "opened_at": 123,
            "closed_at": None,
        },
        {
            "active_school_year": "2026-2027",
            "opened_at": OPENED_AT.isoformat(),
            "closed_at": 123,
        },
        {
            "active_school_year": "2026-2027",
            "opened_at": OPENED_AT.isoformat(),
            "closed_at": None,
            "extra": True,
        },
    ],
)
def test_load_school_year_state_rejects_invalid_state_data(
    tmp_path: Path,
    data: dict[str, object],
) -> None:
    write_state_json(tmp_path, data)

    with pytest.raises(SchoolYearStateError):
        load_school_year_state(tmp_path)


def test_school_year_state_rejects_non_datetime_values() -> None:
    with pytest.raises(SchoolYearStateError, match="opened_at"):
        SchoolYearState(
            active_school_year="2026-2027",
            opened_at=cast(Any, "2026-08-28T09:00:00+00:00"),
        )


def test_open_and_close_create_no_module_or_ledger_side_effects(
    tmp_path: Path,
) -> None:
    open_school_year(tmp_path, "2026-2027", opened_at=OPENED_AT)
    close_school_year(tmp_path, closed_at=CLOSED_AT)

    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings"]
    assert school_year_state_path(tmp_path).is_file()
    for directory_name in (
        "standards",
        "classes",
        "assignments",
        "rosters",
        "reports",
        "pds-scoreform",
        "pds-quillan",
    ):
        assert not (tmp_path / directory_name).exists()
