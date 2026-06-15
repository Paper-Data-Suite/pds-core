"""Tests for read-only standards usage summary helpers."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardUsageCounts,
    StandardUsageEvent,
    StandardsUsageSummary,
    StandardsUsageReadError,
    StandardsValidationError,
    standards_usage_events_path,
    summarize_standard_usage_events,
    summarize_workspace_standard_usage_events,
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


def test_summarize_standard_usage_events_returns_empty_read_only_summary() -> None:
    summary = summarize_standard_usage_events(())

    assert summary.total_events == 0
    assert summary.by_standard_id == {}
    with pytest.raises(TypeError):
        cast(Any, summary.by_standard_id)["njsls-ela:RL.CR.11-12.1"] = object()


def test_summarize_standard_usage_events_counts_single_event() -> None:
    summary = summarize_standard_usage_events((make_usage_event(),))
    counts = summary.by_standard_id["njsls-ela:RL.CR.11-12.1"]

    assert summary.total_events == 1
    assert tuple(summary.by_standard_id) == ("njsls-ela:RL.CR.11-12.1",)
    assert counts.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert counts.total == 1
    assert counts.by_usage_type == {"assessed": 1}
    assert counts.by_module == {"pds-scoreform": 1}
    assert counts.by_assignment_id == {"villainy_final_exam": 1}


def test_summarize_standard_usage_events_aggregates_same_standard() -> None:
    events = (
        make_usage_event(event_id="evt_2026_000001"),
        make_usage_event(
            event_id="evt_2026_000002",
            usage_type="reviewed",
            module="pds-quillan",
            assignment_id="villainy_revision",
        ),
        make_usage_event(
            event_id="evt_2026_000003",
            usage_type="assessed",
            assignment_id="villainy_revision",
        ),
    )

    summary = summarize_standard_usage_events(events)
    counts = summary.by_standard_id["njsls-ela:RL.CR.11-12.1"]

    assert summary.total_events == 3
    assert counts.total == 3
    assert counts.by_usage_type == {"assessed": 2, "reviewed": 1}
    assert counts.by_module == {"pds-quillan": 1, "pds-scoreform": 2}
    assert counts.by_assignment_id == {
        "villainy_final_exam": 1,
        "villainy_revision": 2,
    }


def test_summarize_standard_usage_events_keeps_standards_independent() -> None:
    events = (
        make_usage_event(event_id="evt_2026_000001"),
        make_usage_event(
            event_id="evt_2026_000002",
            standard_id="njsls-ela:W.AW.11-12.1",
            usage_type="practiced",
            module="pds-quillan",
            assignment_id="argument_draft",
        ),
    )

    summary = summarize_standard_usage_events(events)

    assert summary.total_events == 2
    assert tuple(summary.by_standard_id) == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
    )
    assert summary.by_standard_id["njsls-ela:RL.CR.11-12.1"].total == 1
    writing_counts = summary.by_standard_id["njsls-ela:W.AW.11-12.1"]
    assert writing_counts.total == 1
    assert writing_counts.by_usage_type == {"practiced": 1}
    assert writing_counts.by_module == {"pds-quillan": 1}
    assert writing_counts.by_assignment_id == {"argument_draft": 1}


def test_summarize_standard_usage_events_counts_optional_assignment_id() -> None:
    events = (
        make_usage_event(event_id="evt_2026_000001", assignment_id=None),
        make_usage_event(
            event_id="evt_2026_000002",
            assignment_id="villainy_final_exam",
        ),
    )

    summary = summarize_standard_usage_events(events)
    counts = summary.by_standard_id["njsls-ela:RL.CR.11-12.1"]

    assert counts.by_assignment_id == {
        None: 1,
        "villainy_final_exam": 1,
    }
    assert tuple(counts.by_assignment_id) == (None, "villainy_final_exam")


def test_summarize_standard_usage_events_accepts_generator() -> None:
    events = (
        make_usage_event(event_id=f"evt_2026_{index:06d}")
        for index in range(3)
    )

    summary = summarize_standard_usage_events(events)

    assert summary.total_events == 3
    assert summary.by_standard_id["njsls-ela:RL.CR.11-12.1"].total == 3


def test_summarize_standard_usage_events_rejects_non_events() -> None:
    with pytest.raises(StandardsValidationError, match="StandardUsageEvent"):
        summarize_standard_usage_events([cast(Any, object())])


def test_usage_summary_dataclasses_and_mappings_are_read_only() -> None:
    summary = summarize_standard_usage_events((make_usage_event(),))
    counts = summary.by_standard_id["njsls-ela:RL.CR.11-12.1"]

    with pytest.raises(FrozenInstanceError):
        summary.total_events = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        counts.total = 2  # type: ignore[misc]
    with pytest.raises(TypeError):
        cast(Any, summary.by_standard_id)["extra"] = counts
    with pytest.raises(TypeError):
        cast(Any, counts.by_usage_type)["reviewed"] = 1
    with pytest.raises(TypeError):
        cast(Any, counts.by_module)["pds-quillan"] = 1
    with pytest.raises(TypeError):
        cast(Any, counts.by_assignment_id)[None] = 1


def test_direct_standard_usage_counts_makes_mutable_mappings_read_only() -> None:
    by_usage_type = {"reviewed": 1, "assessed": 2}
    by_module = {"pds-scoreform": 1, "pds-quillan": 2}
    by_assignment_id: dict[str | None, int] = {
        "villainy_final_exam": 1,
        None: 2,
    }

    counts = StandardUsageCounts(
        standard_id=" njsls-ela:RL.CR.11-12.1 ",
        total=3,
        by_usage_type=by_usage_type,
        by_module=by_module,
        by_assignment_id=by_assignment_id,
    )

    assert counts.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert tuple(counts.by_usage_type) == ("assessed", "reviewed")
    assert tuple(counts.by_module) == ("pds-quillan", "pds-scoreform")
    assert tuple(counts.by_assignment_id) == (None, "villainy_final_exam")
    with pytest.raises(TypeError):
        cast(Any, counts.by_usage_type)["taught"] = 1
    with pytest.raises(TypeError):
        cast(Any, counts.by_module)["pds-quillan"] = 3
    with pytest.raises(TypeError):
        cast(Any, counts.by_assignment_id)["new_assignment"] = 1


def test_direct_standard_usage_counts_detaches_input_mappings() -> None:
    by_usage_type = {"assessed": 1}
    by_module = {"pds-scoreform": 1}
    by_assignment_id: dict[str | None, int] = {"villainy_final_exam": 1}
    counts = StandardUsageCounts(
        standard_id="njsls-ela:RL.CR.11-12.1",
        total=1,
        by_usage_type=by_usage_type,
        by_module=by_module,
        by_assignment_id=by_assignment_id,
    )

    by_usage_type["reviewed"] = 99
    by_module["pds-quillan"] = 99
    by_assignment_id[None] = 99

    assert counts.by_usage_type == {"assessed": 1}
    assert counts.by_module == {"pds-scoreform": 1}
    assert counts.by_assignment_id == {"villainy_final_exam": 1}


def test_direct_standards_usage_summary_makes_mapping_read_only() -> None:
    counts = StandardUsageCounts(
        standard_id="njsls-ela:RL.CR.11-12.1",
        total=1,
        by_usage_type={"assessed": 1},
        by_module={"pds-scoreform": 1},
        by_assignment_id={"villainy_final_exam": 1},
    )
    by_standard_id = {"njsls-ela:RL.CR.11-12.1": counts}

    summary = StandardsUsageSummary(
        total_events=1,
        by_standard_id=by_standard_id,
    )

    assert summary.by_standard_id == {"njsls-ela:RL.CR.11-12.1": counts}
    with pytest.raises(TypeError):
        cast(Any, summary.by_standard_id)["njsls-ela:W.AW.11-12.1"] = counts


def test_direct_standards_usage_summary_detaches_input_mapping() -> None:
    counts = StandardUsageCounts(
        standard_id="njsls-ela:RL.CR.11-12.1",
        total=1,
        by_usage_type={"assessed": 1},
        by_module={"pds-scoreform": 1},
        by_assignment_id={"villainy_final_exam": 1},
    )
    extra_counts = StandardUsageCounts(
        standard_id="njsls-ela:W.AW.11-12.1",
        total=1,
        by_usage_type={"practiced": 1},
        by_module={"pds-quillan": 1},
        by_assignment_id={"argument_draft": 1},
    )
    by_standard_id = {"njsls-ela:RL.CR.11-12.1": counts}
    summary = StandardsUsageSummary(
        total_events=1,
        by_standard_id=by_standard_id,
    )

    by_standard_id["njsls-ela:W.AW.11-12.1"] = extra_counts

    assert summary.by_standard_id == {"njsls-ela:RL.CR.11-12.1": counts}


@pytest.mark.parametrize(
    "overrides",
    [
        {"total": -1},
        {"total": True},
        {"by_usage_type": {"assessed": 1.5}},
        {"by_usage_type": {"assessed": True}},
        {"by_usage_type": {"assessed": -1}},
        {"by_usage_type": {" ": 1}},
        {"by_module": {" ": 1}},
        {"by_assignment_id": {" ": 1}},
    ],
)
def test_direct_standard_usage_counts_rejects_invalid_data(
    overrides: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "standard_id": "njsls-ela:RL.CR.11-12.1",
        "total": 1,
        "by_usage_type": {"assessed": 1},
        "by_module": {"pds-scoreform": 1},
        "by_assignment_id": {"villainy_final_exam": 1},
    }
    values.update(overrides)

    with pytest.raises(StandardsValidationError):
        StandardUsageCounts(**cast(Any, values))


@pytest.mark.parametrize(
    "overrides",
    [
        {"total_events": -1},
        {"total_events": False},
        {"by_standard_id": {" ": cast(Any, object())}},
        {"by_standard_id": {"njsls-ela:RL.CR.11-12.1": cast(Any, object())}},
    ],
)
def test_direct_standards_usage_summary_rejects_invalid_data(
    overrides: dict[str, object],
) -> None:
    counts = StandardUsageCounts(
        standard_id="njsls-ela:RL.CR.11-12.1",
        total=1,
        by_usage_type={"assessed": 1},
        by_module={"pds-scoreform": 1},
        by_assignment_id={"villainy_final_exam": 1},
    )
    values: dict[str, object] = {
        "total_events": 1,
        "by_standard_id": {"njsls-ela:RL.CR.11-12.1": counts},
    }
    values.update(overrides)

    with pytest.raises(StandardsValidationError):
        StandardsUsageSummary(**cast(Any, values))


def test_summarize_standard_usage_events_returns_deterministic_order() -> None:
    events = (
        make_usage_event(
            event_id="evt_2026_000001",
            standard_id="njsls-ela:W.AW.11-12.1",
            usage_type="reviewed",
            module="pds-quillan",
        ),
        make_usage_event(
            event_id="evt_2026_000002",
            standard_id="njsls-ela:RL.CR.11-12.1",
            usage_type="assessed",
            module="pds-scoreform",
        ),
        make_usage_event(
            event_id="evt_2026_000003",
            standard_id="njsls-ela:RL.CR.11-12.1",
            usage_type="practiced",
            module="pds-quillan",
        ),
    )

    summary = summarize_standard_usage_events(events)
    reading_counts = summary.by_standard_id["njsls-ela:RL.CR.11-12.1"]

    assert tuple(summary.by_standard_id) == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
    )
    assert tuple(reading_counts.by_usage_type) == ("assessed", "practiced")
    assert tuple(reading_counts.by_module) == ("pds-quillan", "pds-scoreform")


def test_summarize_workspace_standard_usage_events_returns_empty_for_missing_ledger(
    tmp_path: Path,
) -> None:
    summary = summarize_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
    )

    assert summary.total_events == 0
    assert summary.by_standard_id == {}


def test_summarize_workspace_standard_usage_events_summarizes_canonical_ledger(
    tmp_path: Path,
) -> None:
    events = (
        make_usage_event(event_id="evt_2026_000001"),
        make_usage_event(event_id="evt_2026_000002", usage_type="reviewed"),
    )
    write_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
        events,
    )

    summary = summarize_workspace_standard_usage_events(
        tmp_path,
        "2026-2027",
        "english12_p3",
    )

    assert summary.total_events == 2
    assert summary.by_standard_id["njsls-ela:RL.CR.11-12.1"].by_usage_type == {
        "assessed": 1,
        "reviewed": 1,
    }


def test_summarize_workspace_standard_usage_events_preserves_read_errors(
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
        summarize_workspace_standard_usage_events(
            tmp_path,
            "2026-2027",
            "english12_p3",
        )

    assert raised.value.path == path
