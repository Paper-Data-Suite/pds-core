"""Synthetic C3B5 service acceptance; no real classroom data."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.classroom_class_commit as guarded
from pds_core.class_metadata import load_class_metadata_for_class
from pds_core.classroom_admin_preview import ClassCreationChange
from pds_core.classroom_class_commit import (
    ClassCreationConflictError,
    ClassCreationError,
    ClassCreationWriteError,
    commit_guarded_class_creation,
    inspect_class_creation_recovery,
    plan_guarded_class_creation,
)
from pds_core.routes import class_dir, class_metadata_path, class_roster_path
from pds_core.school_years import close_school_year, open_school_year

YEAR = "2026-2027"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)
AT = datetime(2026, 9, 2, tzinfo=timezone.utc)
CHANGE = ClassCreationChange("english10_p2", YEAR)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "synthetic-workspace"
    folder.mkdir()
    open_school_year(folder, YEAR, opened_at=START)
    return folder


def _plan(root: Path) -> guarded.GuardedClassCreationReview:
    return plan_guarded_class_creation(root, CHANGE, created_at=AT)


def _commit(
    root: Path,
    review: guarded.GuardedClassCreationReview,
    *,
    confirmed: bool = True,
    created_at: datetime = AT,
    change: ClassCreationChange = CHANGE,
) -> guarded.ClassCreationResult:
    return commit_guarded_class_creation(
        root,
        change,
        created_at=created_at,
        expected_current_state_token=review.current_state_token,
        expected_candidate_state_token=review.candidate_state_token,
        confirmed=confirmed,
    )


def test_review_read_only_and_timestamp_bound(root: Path) -> None:
    one = _plan(root)
    two = plan_guarded_class_creation(
        root, CHANGE, created_at=datetime(2026, 9, 3, tzinfo=timezone.utc)
    )
    assert one.current_state_token == two.current_state_token
    assert one.candidate_state_token != two.candidate_state_token
    assert not (root / "classes").exists()
    assert not (root / ".school-year.write.lock").exists()
    assert not tuple(root.glob(".core242-class-*"))


def test_commit_canonical_empty_class(root: Path) -> None:
    review = _plan(root)
    result = _commit(root, review)
    assert result.outcome == "committed"
    assert result.metadata_path == class_metadata_path(root, CHANGE.class_id)
    assert load_class_metadata_for_class(root, CHANGE.class_id) == review.metadata
    assert not class_roster_path(root, CHANGE.class_id).exists()
    assert not (root / ".school-year.write.lock").exists()
    assert not tuple(root.glob(".core242-class-*"))
    assert inspect_class_creation_recovery(root, CHANGE, created_at=AT) == "matches_review"
    before = result.metadata_path.read_bytes()
    with pytest.raises(ClassCreationConflictError):
        _commit(root, review)
    assert result.metadata_path.read_bytes() == before


def test_unconfirmed_and_changed_candidate(root: Path) -> None:
    review = _plan(root)
    with pytest.raises(ClassCreationError, match="confirmation"):
        _commit(root, review, confirmed=False)
    with pytest.raises(ClassCreationConflictError) as raised:
        _commit(root, review, created_at=datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert raised.value.reason == "candidate_changed"
    with pytest.raises(ClassCreationConflictError) as raised:
        _commit(root, review, change=ClassCreationChange("other", YEAR))
    assert raised.value.reason == "candidate_changed"
    assert not (root / "classes").exists()


def test_closed_year_after_review(root: Path) -> None:
    review = _plan(root)
    close_school_year(root, closed_at=AT)
    with pytest.raises(ClassCreationConflictError):
        _commit(root, review)
    assert not (root / "classes").exists()


def test_existing_folder_and_case_collision_preserved(root: Path) -> None:
    review = _plan(root)
    target = class_dir(root, CHANGE.class_id.upper())
    target.mkdir(parents=True)
    sentinel = target / "existing.txt"
    sentinel.write_text("existing", encoding="utf-8")
    with pytest.raises(ClassCreationConflictError):
        _commit(root, review)
    assert sentinel.read_text(encoding="utf-8") == "existing"


def test_shared_year_lock(root: Path) -> None:
    review = _plan(root)
    lock = root / ".school-year.write.lock"
    lock.write_text("owner", encoding="utf-8")
    with pytest.raises(ClassCreationConflictError) as raised:
        _commit(root, review)
    assert raised.value.reason == "write_conflict"
    assert lock.read_text(encoding="utf-8") == "owner"
    assert not (root / "classes").exists()


@pytest.mark.parametrize(
    "at", [datetime(2026, 9, 2), datetime(2025, 9, 2, tzinfo=timezone.utc)]
)
def test_invalid_timestamp(root: Path, at: datetime) -> None:
    with pytest.raises(ClassCreationError) as raised:
        plan_guarded_class_creation(root, CHANGE, created_at=at)
    assert raised.value.reason == "invalid_timestamp"


def test_reserved_class_id(root: Path) -> None:
    with pytest.raises(ClassCreationError) as raised:
        plan_guarded_class_creation(
            root, ClassCreationChange("CON", YEAR), created_at=AT
        )
    assert raised.value.reason == "invalid_class"


def test_stage_failure_leaves_no_class(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review = _plan(root)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("injected stage failure")

    monkeypatch.setattr(guarded, "write_class_metadata", fail)
    with pytest.raises(ClassCreationWriteError) as raised:
        _commit(root, review)
    assert raised.value.outcome == "no_change"
    assert inspect_class_creation_recovery(root, CHANGE, created_at=AT) == "absent"
    assert not tuple(root.glob(".core242-class-*"))


def test_publication_failure_preserves_partial(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review = _plan(root)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("injected link failure")

    monkeypatch.setattr(os, "link", fail)
    with pytest.raises(ClassCreationWriteError) as raised:
        _commit(root, review)
    assert raised.value.outcome == "partial"
    target = class_dir(root, CHANGE.class_id)
    assert target.is_dir()
    assert inspect_class_creation_recovery(root, CHANGE, created_at=AT) == "empty_directory"
    with pytest.raises(ClassCreationConflictError):
        _commit(root, review)
    assert target.is_dir()
    assert not (root / ".school-year.write.lock").exists()


def test_postpublication_failure_is_indeterminate(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review = _plan(root)
    actual = os.link

    def link_then_fail(source: Path, destination: Path) -> None:
        actual(source, destination)
        raise OSError("injected after publication")

    monkeypatch.setattr(os, "link", link_then_fail)
    with pytest.raises(ClassCreationWriteError) as raised:
        _commit(root, review)
    assert raised.value.outcome == "indeterminate"
    assert inspect_class_creation_recovery(root, CHANGE, created_at=AT) == "matches_review"
    assert not (root / ".school-year.write.lock").exists()


def test_concurrent_metadata_not_overwritten(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review = _plan(root)
    actual = os.link

    def conflict(source: Path, destination: Path) -> None:
        destination.write_text("external", encoding="utf-8")
        actual(source, destination)

    monkeypatch.setattr(os, "link", conflict)
    with pytest.raises(ClassCreationWriteError) as raised:
        _commit(root, review)
    assert raised.value.outcome == "indeterminate"
    assert class_metadata_path(root, CHANGE.class_id).read_text(encoding="utf-8") == "external"
    assert inspect_class_creation_recovery(root, CHANGE, created_at=AT) == "conflict"


def test_recovery_never_adopts_unowned_directory(root: Path) -> None:
    target = class_dir(root, CHANGE.class_id)
    target.mkdir(parents=True)
    assert inspect_class_creation_recovery(root, CHANGE, created_at=AT) == "empty_directory"
    with pytest.raises(ClassCreationConflictError):
        _plan(root)
    (target / "producer-work.txt").write_text("preserve", encoding="utf-8")
    assert inspect_class_creation_recovery(root, CHANGE, created_at=AT) == "conflict"
    assert (target / "producer-work.txt").read_text(encoding="utf-8") == "preserve"
