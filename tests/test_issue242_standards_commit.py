"""Synthetic Standards review and membership acceptance for Core #242."""

from __future__ import annotations

from pathlib import Path

import pytest

import pds_core.classroom_standards_commit as guarded
from pds_core.classroom_standards_commit import (
    ProfileMembershipChange,
    StandardsReviewConflict,
    StandardsReviewError,
    StandardsReviewWriteError,
    commit_profile_membership,
    inspect_standards_snapshot,
    plan_profile_membership,
)
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsWriteError,
    load_standards_library,
    standards_library_path,
    write_standards_library,
)

ONE = "synthetic:one"
TWO = "synthetic:two"
PROFILE = "english12"
ADD = ProfileMembershipChange("add", PROFILE, (TWO,))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    location = tmp_path / "synthetic-workspace"
    location.mkdir()
    return location


@pytest.fixture
def populated(root: Path) -> Path:
    library = StandardsLibrary(
        standards=(
            StandardDefinition(ONE, "ONE", "Synthetic", "One", "First standard"),
            StandardDefinition(TWO, "TWO", "Synthetic", "Two", "Second standard"),
        ),
        profiles=(
            StandardsProfile(PROFILE, (ONE,), title="English 12"),
            StandardsProfile("other", (TWO,), title="Other"),
        ),
    )
    write_standards_library(standards_library_path(root), library)
    return root


def _commit(
    root: Path,
    review: guarded.ProfileMembershipReview,
    *,
    change: ProfileMembershipChange = ADD,
    confirmed: bool = True,
) -> guarded.ProfileMembershipResult:
    return commit_profile_membership(
        root,
        change,
        expected_current_state_token=review.snapshot.state_token,
        expected_candidate_state_token=review.candidate_state_token,
        confirmed=confirmed,
    )


def test_missing_library_is_read_only(root: Path) -> None:
    snapshot = inspect_standards_snapshot(root)
    assert snapshot.present is False
    assert snapshot.library.standards == ()
    assert snapshot.library.profiles == ()
    assert not standards_library_path(root).parent.exists()
    assert not (root / ".school-year.write.lock").exists()


def test_review_exact_membership_and_commit(populated: Path) -> None:
    path = standards_library_path(populated)
    raw = path.read_bytes()
    review = plan_profile_membership(populated, ADD)
    assert review.before == (ONE,)
    assert review.after == (ONE, TWO)
    assert path.read_bytes() == raw
    assert not (populated / ".school-year.write.lock").exists()
    result = _commit(populated, review)
    assert result.outcome == "committed"
    saved = load_standards_library(path)
    assert saved == review.candidate
    assert saved.standards == review.snapshot.library.standards
    assert saved.profiles[0].title == "English 12"
    assert saved.profiles[1] == review.snapshot.library.profiles[1]
    assert result.state_token != review.snapshot.state_token
    assert not (populated / ".school-year.write.lock").exists()
    with pytest.raises(StandardsReviewConflict):
        _commit(populated, review)


@pytest.mark.parametrize(
    "change, after",
    [
        (ProfileMembershipChange("remove", PROFILE, (ONE,)), ()),
        (ProfileMembershipChange("set", PROFILE, (TWO,)), (TWO,)),
        (ProfileMembershipChange("set", PROFILE, ()), ()),
    ],
)
def test_remove_or_replace_preserves_definitions(
    populated: Path, change: ProfileMembershipChange, after: tuple[str, ...]
) -> None:
    review = plan_profile_membership(populated, change)
    result = _commit(populated, review, change=change)
    assert result.after == after
    assert inspect_standards_snapshot(populated).library.standards == review.snapshot.library.standards


def test_same_membership_is_noop(populated: Path) -> None:
    change = ProfileMembershipChange("set", PROFILE, (ONE,))
    review = plan_profile_membership(populated, change)
    raw = standards_library_path(populated).read_bytes()
    result = _commit(populated, review, change=change)
    assert result.outcome == "no_change"
    assert result.state_token == review.snapshot.state_token
    assert standards_library_path(populated).read_bytes() == raw


def test_unconfirmed_and_changed_candidate(populated: Path) -> None:
    review = plan_profile_membership(populated, ADD)
    raw = standards_library_path(populated).read_bytes()
    with pytest.raises(StandardsReviewError) as error:
        _commit(populated, review, confirmed=False)
    assert error.value.reason == "not_confirmed"
    with pytest.raises(StandardsReviewConflict) as error2:
        _commit(populated, review, change=ProfileMembershipChange("set", PROFILE, (TWO,)))
    assert error2.value.reason == "candidate_changed"
    assert standards_library_path(populated).read_bytes() == raw


def test_exact_raw_bytes_bind_review(populated: Path) -> None:
    review = plan_profile_membership(populated, ADD)
    path = standards_library_path(populated)
    raw = path.read_bytes() + b"\n"
    path.write_bytes(raw)
    with pytest.raises(StandardsReviewConflict) as error:
        _commit(populated, review)
    assert error.value.reason == "state_changed"
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "change",
    [
        ProfileMembershipChange("add", PROFILE, (ONE,)),
        ProfileMembershipChange("add", PROFILE, ("unknown",)),
        ProfileMembershipChange("add", PROFILE, (TWO, TWO)),
        ProfileMembershipChange("remove", PROFILE, (TWO,)),
        ProfileMembershipChange("add", "missing", (TWO,)),
        ProfileMembershipChange("add", "", (TWO,)),
    ],
)
def test_invalid_membership_refused(
    populated: Path, change: ProfileMembershipChange
) -> None:
    raw = standards_library_path(populated).read_bytes()
    with pytest.raises(StandardsReviewError):
        plan_profile_membership(populated, change)
    assert standards_library_path(populated).read_bytes() == raw


def test_live_lock_preserved(populated: Path) -> None:
    review = plan_profile_membership(populated, ADD)
    lock = populated / ".school-year.write.lock"
    lock.write_text("another owner", encoding="utf-8")
    with pytest.raises(StandardsReviewConflict):
        _commit(populated, review)
    assert lock.read_text(encoding="utf-8") == "another owner"


def test_corrupt_library_is_not_empty(populated: Path) -> None:
    path = standards_library_path(populated)
    path.write_bytes(b"{")
    with pytest.raises(StandardsReviewError):
        inspect_standards_snapshot(populated)
    assert path.read_bytes() == b"{"


def test_bounded_snapshot(populated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guarded, "_MAX_BYTES", 10)
    with pytest.raises(StandardsReviewError) as error:
        inspect_standards_snapshot(populated)
    assert error.value.reason == "oversized_library"


def test_postwrite_failure_is_uncertain(
    populated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review = plan_profile_membership(populated, ADD)
    actual = write_standards_library

    def write_then_fail(
        path: str | Path, library: StandardsLibrary, *, overwrite: bool = False
    ) -> None:
        actual(path, library, overwrite=overwrite)
        raise StandardsWriteError(path, "private injected failure")

    monkeypatch.setattr(guarded, "write_standards_library", write_then_fail)
    with pytest.raises(StandardsReviewWriteError) as error:
        _commit(populated, review)
    assert error.value.reason == "write_uncertain"
    assert "private" not in str(error.value)
    assert inspect_standards_snapshot(populated).library == review.candidate
    assert not (populated / ".school-year.write.lock").exists()
