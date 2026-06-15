"""Tests for explicit-path standards usage event JSONL file helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardUsageEvent,
    StandardsUsageReadError,
    StandardsUsageWriteError,
    append_standard_usage_event,
    load_standard_usage_events,
    standard_usage_event_to_dict,
    write_standard_usage_events,
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


def test_load_standard_usage_events_reads_valid_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    events = (
        make_usage_event(),
        make_usage_event(
            event_id="evt_2026_000002",
            usage_type="reviewed",
            used_at=datetime(2026, 6, 15, 9, 30, tzinfo=timezone.utc),
        ),
    )
    path.write_text(
        "".join(
            json.dumps(standard_usage_event_to_dict(event)) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )

    loaded = load_standard_usage_events(path)

    assert loaded == events
    assert all(isinstance(event, StandardUsageEvent) for event in loaded)
    assert loaded[1].used_at.tzinfo is not None


def test_load_standard_usage_events_returns_empty_tuple_for_empty_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("", encoding="utf-8")

    assert load_standard_usage_events(path) == ()


def test_load_standard_usage_events_ignores_blank_lines(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    data = json.dumps(standard_usage_event_to_dict(make_usage_event()))
    path.write_text(f"\n  \n{data}\n\t\n", encoding="utf-8")

    assert load_standard_usage_events(path) == (make_usage_event(),)


def test_load_standard_usage_events_rejects_missing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.jsonl"

    with pytest.raises(StandardsUsageReadError) as raised:
        load_standard_usage_events(path)

    assert raised.value.path == path


def test_load_standard_usage_events_rejects_invalid_json_with_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("\n{not json}\n", encoding="utf-8")

    with pytest.raises(StandardsUsageReadError, match=r"line 2: invalid JSON"):
        load_standard_usage_events(path)


def test_load_standard_usage_events_rejects_non_object_line(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(
        StandardsUsageReadError,
        match=r"line 1: top-level JSON value must be a mapping",
    ):
        load_standard_usage_events(path)


def test_load_standard_usage_events_rejects_invalid_event_with_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    data = standard_usage_event_to_dict(make_usage_event())
    data["usage_type"] = "mastered"
    path.write_text(f"\n{json.dumps(data)}\n", encoding="utf-8")

    with pytest.raises(
        StandardsUsageReadError,
        match=r"line 2: invalid standards usage event data.*usage_type",
    ):
        load_standard_usage_events(path)


def test_append_standard_usage_event_creates_parent_and_appends_event(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "usage" / "events.jsonl"
    event = make_usage_event()

    append_standard_usage_event(path, event)

    assert load_standard_usage_events(path) == (event,)
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_append_standard_usage_event_preserves_existing_events(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = make_usage_event()
    second = make_usage_event(
        event_id="evt_2026_000002",
        usage_type="reviewed",
    )

    append_standard_usage_event(path, first)
    append_standard_usage_event(path, second)

    assert load_standard_usage_events(path) == (first, second)


def test_append_standard_usage_event_separates_unterminated_existing_line(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = make_usage_event()
    second = make_usage_event(event_id="evt_2026_000002")
    path.write_text(
        json.dumps(standard_usage_event_to_dict(first)),
        encoding="utf-8",
    )

    append_standard_usage_event(path, second)

    assert load_standard_usage_events(path) == (first, second)


def test_append_standard_usage_event_rejects_invalid_event(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"

    with pytest.raises(StandardsUsageWriteError, match="StandardUsageEvent"):
        append_standard_usage_event(path, cast(Any, object()))

    assert not path.exists()


def test_write_standard_usage_events_writes_jsonl_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    events = (
        make_usage_event(),
        make_usage_event(event_id="evt_2026_000002", usage_type="reviewed"),
    )

    write_standard_usage_events(path, events)

    assert load_standard_usage_events(path) == events
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == json.dumps(
        standard_usage_event_to_dict(events[0]),
        sort_keys=True,
        separators=(",", ":"),
    )


def test_write_standard_usage_events_refuses_overwrite_by_default(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("original", encoding="utf-8")

    with pytest.raises(StandardsUsageWriteError, match="already exists"):
        write_standard_usage_events(path, (make_usage_event(),))

    assert path.read_text(encoding="utf-8") == "original"


def test_write_standard_usage_events_overwrites_when_requested(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("old content", encoding="utf-8")
    event = make_usage_event(event_id="evt_2026_000002")

    write_standard_usage_events(path, (event,), overwrite=True)

    assert load_standard_usage_events(path) == (event,)


def test_write_standard_usage_events_preserves_target_on_validation_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    original = "original\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(StandardsUsageWriteError, match="StandardUsageEvent"):
        write_standard_usage_events(
            path,
            (make_usage_event(), cast(Any, object())),
            overwrite=True,
        )

    assert path.read_text(encoding="utf-8") == original


def test_write_standard_usage_events_writes_empty_file_for_empty_events(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"

    write_standard_usage_events(path, ())

    assert path.read_text(encoding="utf-8") == ""
    assert load_standard_usage_events(path) == ()


def test_write_standard_usage_events_creates_parent_directories(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "usage" / "events.jsonl"

    write_standard_usage_events(path, (make_usage_event(),))

    assert load_standard_usage_events(path) == (make_usage_event(),)


def test_write_standard_usage_events_cleans_up_after_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("original", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("pds_core.standards.os.replace", fail_replace)

    with pytest.raises(StandardsUsageWriteError, match="replace failed"):
        write_standard_usage_events(
            path,
            (make_usage_event(),),
            overwrite=True,
        )

    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".events.jsonl.*.tmp")) == []
