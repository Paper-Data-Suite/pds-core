"""Tests for standards usage workspace path and file helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardUsageEvent,
    StandardsUsageReadError,
    StandardsUsageWriteError,
    StandardsValidationError,
    append_workspace_standard_usage_event,
    ensure_standards_usage_class_dir,
    load_workspace_standard_usage_events,
    standards_usage_class_dir,
    standards_usage_dir,
    standards_usage_events_path,
    standards_usage_school_year_dir,
    write_workspace_standard_usage_events,
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


def test_standards_usage_paths_are_canonical(tmp_path: Path) -> None:
    assert standards_usage_dir(tmp_path) == tmp_path / "standards" / "usage"
    assert standards_usage_school_year_dir(
        tmp_path, "2026-2027"
    ) == tmp_path / "standards" / "usage" / "2026-2027"
    assert standards_usage_class_dir(
        tmp_path, "2026-2027", "english12_p3"
    ) == tmp_path / "standards" / "usage" / "2026-2027" / "english12_p3"
    assert standards_usage_events_path(
        tmp_path, "2026-2027", "english12_p3"
    ) == (
        tmp_path
        / "standards"
        / "usage"
        / "2026-2027"
        / "english12_p3"
        / "events.jsonl"
    )


def test_standards_usage_path_helpers_have_no_side_effects(
    tmp_path: Path,
) -> None:
    standards_usage_dir(tmp_path)
    standards_usage_school_year_dir(tmp_path, "2026-2027")
    standards_usage_class_dir(tmp_path, "2026-2027", "english12_p3")
    standards_usage_events_path(tmp_path, "2026-2027", "english12_p3")

    assert not (tmp_path / "standards").exists()


def test_ensure_standards_usage_class_dir_creates_only_directory(
    tmp_path: Path,
) -> None:
    directory = ensure_standards_usage_class_dir(
        tmp_path,
        "2026-2027",
        "english12_p3",
    )

    assert directory.is_dir()
    assert not (directory / "events.jsonl").exists()


@pytest.mark.parametrize(
    "school_year",
    [
        "",
        " ",
        "2026",
        "2026-27",
        "2026/2027",
        "2026-2026",
        "2026-2028",
        "abcd-efgh",
    ],
)
def test_usage_path_helpers_reject_invalid_school_year(
    tmp_path: Path,
    school_year: str,
) -> None:
    with pytest.raises(StandardsValidationError, match="school_year"):
        standards_usage_school_year_dir(tmp_path, school_year)


@pytest.mark.parametrize("class_id", ["english/12", "english 12", "../secret"])
def test_usage_path_helpers_reject_invalid_class_id(
    tmp_path: Path,
    class_id: str,
) -> None:
    with pytest.raises(StandardsValidationError, match="class_id"):
        standards_usage_class_dir(tmp_path, "2026-2027", class_id)


def test_load_workspace_usage_events_returns_empty_for_missing_ledger(
    tmp_path: Path,
) -> None:
    assert load_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
    ) == ()


def test_load_workspace_usage_events_reads_canonical_ledger(
    tmp_path: Path,
) -> None:
    events = (
        make_usage_event(),
        make_usage_event(event_id="evt_2026_000002", usage_type="reviewed"),
    )
    write_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
        events,
    )

    assert load_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
    ) == events


def test_load_workspace_usage_events_preserves_structured_read_errors(
    tmp_path: Path,
) -> None:
    path = standards_usage_events_path(
        tmp_path,
        "2026-2027",
        "english12_p3",
    )
    path.parent.mkdir(parents=True)
    path.write_text("{not json}\n", encoding="utf-8")

    with pytest.raises(StandardsUsageReadError) as raised:
        load_workspace_standard_usage_events(
            tmp_path,
            "2026-2027",
            "english12_p3",
        )

    assert raised.value.path == path


def test_append_workspace_usage_event_uses_canonical_ledger(
    tmp_path: Path,
) -> None:
    first = make_usage_event()
    second = make_usage_event(
        event_id="evt_2026_000002",
        usage_type="reviewed",
    )

    append_workspace_standard_usage_event(tmp_path, first)
    append_workspace_standard_usage_event(tmp_path, second)

    path = standards_usage_events_path(
        tmp_path,
        "2026-2027",
        "english12_p3",
    )
    assert path.is_file()
    assert load_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
    ) == (first, second)


def test_append_workspace_usage_event_rejects_invalid_object(
    tmp_path: Path,
) -> None:
    with pytest.raises(StandardsUsageWriteError, match="StandardUsageEvent"):
        append_workspace_standard_usage_event(tmp_path, cast(Any, object()))

    assert not (tmp_path / "standards").exists()


def test_write_workspace_usage_events_preserves_overwrite_behavior(
    tmp_path: Path,
) -> None:
    original = make_usage_event()
    replacement = make_usage_event(event_id="evt_2026_000002")
    write_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
        (original,),
    )

    with pytest.raises(StandardsUsageWriteError, match="already exists"):
        write_workspace_standard_usage_events(
            tmp_path,
            "2026-2027",
            "english12_p3",
            (replacement,),
        )

    write_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
        (replacement,),
        overwrite=True,
    )

    assert load_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
    ) == (replacement,)


def test_write_workspace_usage_events_materializes_generator_once(
    tmp_path: Path,
) -> None:
    events = (
        make_usage_event(event_id=f"evt_2026_{index:06d}")
        for index in range(2)
    )

    write_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
        events,
    )

    assert len(
        load_workspace_standard_usage_events(
            tmp_path,
            "2026-2027",
            "english12_p3",
        )
    ) == 2


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"school_year": "2027-2028"}, "school_year"),
        ({"class_id": "english12_p4"}, "class_id"),
    ],
)
def test_write_workspace_usage_events_rejects_mismatched_events(
    tmp_path: Path,
    override: dict[str, object],
    match: str,
) -> None:
    path = standards_usage_events_path(
        tmp_path,
        "2026-2027",
        "english12_p3",
    )
    path.parent.mkdir(parents=True)
    path.write_text("original\n", encoding="utf-8")

    with pytest.raises(StandardsUsageWriteError, match=match):
        write_workspace_standard_usage_events(
            tmp_path,
            "2026-2027",
            "english12_p3",
            (make_usage_event(**override),),
            overwrite=True,
        )

    assert path.read_text(encoding="utf-8") == "original\n"
