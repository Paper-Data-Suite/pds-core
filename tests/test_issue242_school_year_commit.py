"""Core #242 C3B2: synthetic guarded school-year commit acceptance."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.classroom_school_year_commit as guarded
import pds_core.school_years as years
from pds_core.classroom_admin_preview import SchoolYearChange
from pds_core.classroom_school_year_commit import (
    SchoolYearCommitError,
    SchoolYearConflictError,
    SchoolYearWriteError,
    commit_guarded_school_year_change,
    plan_guarded_school_year_change,
)
from pds_core.classes import ensure_class_folder

YEAR = "2026-2027"
START = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
FINISH = datetime(2027, 6, 30, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "synthetic-workspace"
    folder.mkdir()
    return folder


def _plan(
    root: Path, change: SchoolYearChange, at: datetime
) -> guarded.GuardedSchoolYearReview:
    return plan_guarded_school_year_change(root, change, effective_at=at)


def _commit(
    root: Path,
    change: SchoolYearChange,
    at: datetime,
    *,
    confirmed: bool = True,
) -> guarded.SchoolYearCommitResult:
    review = _plan(root, change, at)
    return commit_guarded_school_year_change(
        root,
        change,
        effective_at=at,
        expected_current_state_token=review.current_state_token,
        expected_candidate_state_token=review.candidate_state_token,
        confirmed=confirmed,
    )


def test_review_first_year_is_read_only_and_timestamp_bound(root: Path) -> None:
    choice = SchoolYearChange("open", YEAR)
    one = _plan(root, choice, START)
    two = _plan(root, choice, FINISH)
    assert one.proposal.previous_record_status == "missing"
    assert one.proposal.proposed_active_year == YEAR
    assert one.proposal.no_change is False
    assert one.current_state_token == two.current_state_token
    assert one.candidate_state_token != two.candidate_state_token
    assert one.effective_at == START
    assert not years.school_year_state_path(root).exists()
    assert not (root / "settings").exists()
    assert not (root / ".school-year.write.lock").exists()


def test_confirmed_initial_open_uses_canonical_writer(root: Path) -> None:
    choice = SchoolYearChange("open", YEAR)
    previous = _plan(root, choice, START)
    result = _commit(root, choice, START)
    assert result.action == "open"
    assert result.outcome == "committed"
    assert result.previous_school_year is None
    assert result.active_school_year == YEAR
    assert result.previous_state_token == previous.current_state_token
    assert result.committed_state_token != result.previous_state_token
    state = years.load_school_year_state(root)
    assert state is not None
    assert state.active_school_year == YEAR
    assert state.opened_at == START
    assert state.closed_at is None
    assert not (root / ".school-year.write.lock").exists()


def test_open_same_active_year_is_true_noop(root: Path) -> None:
    years.open_school_year(root, YEAR, opened_at=START)
    path = years.school_year_state_path(root)
    before = path.read_bytes()
    result = _commit(root, SchoolYearChange("open", YEAR), FINISH)
    assert result.outcome == "no_change"
    assert result.active_school_year == YEAR
    assert result.previous_state_token == result.committed_state_token
    assert path.read_bytes() == before
    assert not (root / ".school-year.write.lock").exists()


def test_confirmed_close_preserves_existing_classroom_data(root: Path) -> None:
    years.open_school_year(root, YEAR, opened_at=START)
    folder = ensure_class_folder(root, "english12_p2")
    sentinel = folder.class_dir / "producer-work.txt"
    sentinel.write_text("preserved", encoding="utf-8")
    result = _commit(root, SchoolYearChange("close"), FINISH)
    assert result.outcome == "committed"
    assert result.previous_school_year == YEAR
    assert result.active_school_year is None
    state = years.load_school_year_state(root)
    assert state is not None
    assert state.closed_at == FINISH
    assert sentinel.read_text(encoding="utf-8") == "preserved"
    assert not (root / ".school-year.write.lock").exists()


def test_unconfirmed_review_makes_no_changes(root: Path) -> None:
    change = SchoolYearChange("open", YEAR)
    review = _plan(root, change, START)
    with pytest.raises(SchoolYearCommitError) as raised:
        commit_guarded_school_year_change(
            root,
            change,
            effective_at=START,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=False,
        )
    assert raised.value.reason == "not_confirmed"
    assert not years.school_year_state_path(root).exists()
    assert not (root / ".school-year.write.lock").exists()


def test_wrong_candidate_timestamp_refused(root: Path) -> None:
    change = SchoolYearChange("open", YEAR)
    review = _plan(root, change, START)
    with pytest.raises(SchoolYearConflictError) as raised:
        commit_guarded_school_year_change(
            root,
            change,
            effective_at=FINISH,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "candidate_changed"
    assert not years.school_year_state_path(root).exists()


def test_wrong_candidate_year_refused(root: Path) -> None:
    review = _plan(root, SchoolYearChange("open", YEAR), START)
    with pytest.raises(SchoolYearConflictError) as raised:
        commit_guarded_school_year_change(
            root,
            SchoolYearChange("open", "2027-2028"),
            effective_at=START,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "candidate_changed"


def test_stale_year_state_refused_before_writing(root: Path) -> None:
    change = SchoolYearChange("open", YEAR)
    review = _plan(root, change, START)
    years.open_school_year(root, "2027-2028", opened_at=START)
    previous = years.school_year_state_path(root).read_bytes()
    with pytest.raises(SchoolYearConflictError) as raised:
        commit_guarded_school_year_change(
            root,
            change,
            effective_at=START,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "current_state_changed"
    assert years.school_year_state_path(root).read_bytes() == previous


def test_stale_year_state_after_local_lock_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    change = SchoolYearChange("open", YEAR)
    review = _plan(root, change, START)
    actual = guarded._local_year_lock

    @contextmanager
    def external_write(location: Path) -> Iterator[None]:
        years.open_school_year(root, "2027-2028", opened_at=START)
        with actual(location):
            yield

    monkeypatch.setattr(guarded, "_local_year_lock", external_write)
    with pytest.raises(SchoolYearConflictError) as raised:
        commit_guarded_school_year_change(
            root,
            change,
            effective_at=START,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "current_state_changed"
    assert years.get_active_school_year(root) == "2027-2028"


def test_existing_writer_lock_is_never_overridden(root: Path) -> None:
    lock = root / ".school-year.write.lock"
    lock.write_text("owner", encoding="utf-8")
    with pytest.raises(SchoolYearConflictError) as raised:
        _commit(root, SchoolYearChange("open", YEAR), START)
    assert raised.value.reason == "write_conflict"
    assert lock.read_text(encoding="utf-8") == "owner"
    assert not years.school_year_state_path(root).exists()


def test_invalid_tokens_fail_before_creating_any_files(root: Path) -> None:
    change = SchoolYearChange("open", YEAR)
    preview = _plan(root, change, START)
    with pytest.raises(SchoolYearCommitError) as raised:
        commit_guarded_school_year_change(
            root,
            change,
            effective_at=START,
            expected_current_state_token="bad",
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "invalid_token"
    assert not years.school_year_state_path(root).exists()


def test_close_before_open_timestamp_rejected(root: Path) -> None:
    years.open_school_year(root, YEAR, opened_at=START)
    before = years.school_year_state_path(root).read_bytes()
    with pytest.raises(SchoolYearCommitError) as raised:
        _plan(
            root,
            SchoolYearChange("close"),
            datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
    assert raised.value.reason == "invalid_timestamp"
    assert years.school_year_state_path(root).read_bytes() == before


def test_naive_timestamp_is_rejected_before_any_write(root: Path) -> None:
    change = SchoolYearChange("open", YEAR)
    with pytest.raises(SchoolYearCommitError) as raised:
        _plan(root, change, datetime(2026, 9, 1))
    assert raised.value.reason == "invalid_timestamp"
    assert not years.school_year_state_path(root).exists()


def test_closed_year_rollover_preserves_old_record(root: Path) -> None:
    years.open_school_year(root, YEAR, opened_at=START)
    years.close_school_year(root, closed_at=FINISH)
    before = years.school_year_state_path(root).read_bytes()
    with pytest.raises(SchoolYearCommitError) as raised:
        _plan(root, SchoolYearChange("open", "2027-2028"), FINISH)
    assert raised.value.reason == "year_history_policy_required"
    assert years.school_year_state_path(root).read_bytes() == before


def test_first_year_refuses_preexisting_class_directory(root: Path) -> None:
    ensure_class_folder(root, "legacy_class")
    with pytest.raises(SchoolYearCommitError) as raised:
        _plan(root, SchoolYearChange("open", YEAR), START)
    assert raised.value.reason == "class_history_policy_required"
    assert not years.school_year_state_path(root).exists()


def test_after_canonical_write_failure_is_uncertain(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual = years.open_school_year

    def replace_then_fail(
        selected: str | Path,
        year: str,
        *,
        opened_at: datetime,
        overwrite: bool = False,
    ) -> years.SchoolYearState:
        actual(selected, year, opened_at=opened_at, overwrite=overwrite)
        raise years.SchoolYearStateError("injected after replacement")

    monkeypatch.setattr(guarded, "open_school_year", replace_then_fail)
    with pytest.raises(SchoolYearWriteError) as raised:
        _commit(root, SchoolYearChange("open", YEAR), START)
    assert raised.value.reason == "write_outcome_uncertain"
    assert years.get_active_school_year(root) == YEAR
    assert not (root / ".school-year.write.lock").exists()


def test_close_failure_after_replace_is_uncertain(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    years.open_school_year(root, YEAR, opened_at=START)
    actual = years.close_school_year

    def replace_then_fail(
        selected: str | Path, *, closed_at: datetime
    ) -> years.SchoolYearState:
        actual(selected, closed_at=closed_at)
        raise years.SchoolYearStateError("injected after closing")

    monkeypatch.setattr(guarded, "close_school_year", replace_then_fail)
    with pytest.raises(SchoolYearWriteError) as raised:
        _commit(root, SchoolYearChange("close"), FINISH)
    assert raised.value.reason == "write_outcome_uncertain"
    assert years.get_active_school_year(root) is None
    assert not (root / ".school-year.write.lock").exists()
