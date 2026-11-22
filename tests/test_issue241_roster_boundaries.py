"""Core #241 Slice B2: path, freshness and uncertain-write boundaries."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

import pds_core.roster_edits as edits
from pds_core._roster_write_lock import (
    RosterWriteLockError,
    acquire_roster_write_lock,
    roster_write_lock_path,
)
from pds_core.class_metadata import (
    create_class_metadata,
    write_class_metadata_for_class,
)
from pds_core.classes import write_class_roster
from pds_core.rosters import (
    Roster,
    RosterWriteError,
    _write_roster_unlocked,
    create_roster,
    load_roster,
)
from pds_core.routes import class_roster_path

CLASS_ID = "english12_p2"


def _student(student_id: str, period: str = "2") -> dict[str, str]:
    return {
        "student_id": student_id,
        "first_name": "Ari",
        "last_name": "Rivera",
        "period": period,
    }


def _seed(root: Path) -> Path:
    return write_class_roster(
        root, create_roster(CLASS_ID, [_student("0007"), _student("0011")])
    )


def _change(
    operation: edits.RosterEditOperation, **fields: str
) -> edits.StudentRosterChange:
    return edits.StudentRosterChange(operation, "0007", fields)


def _preview(
    root: Path, change: edits.StudentRosterChange
) -> edits.StudentRosterEditPreview:
    return edits.plan_student_roster_edit(root, CLASS_ID, change)


def _commit(
    root: Path,
    change: edits.StudentRosterChange,
    preview: edits.StudentRosterEditPreview,
    *,
    confirmed: bool = True,
) -> edits.StudentRosterEditCommitResult:
    return edits.commit_student_roster_edit(
        root,
        CLASS_ID,
        change,
        expected_current_state_token=preview.current_state_token,
        expected_candidate_state_token=preview.candidate_state_token,
        confirmed=confirmed,
    )


def _metadata(root: Path) -> None:
    write_class_metadata_for_class(
        root,
        create_class_metadata(
            CLASS_ID,
            "2026-2027",
            created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        ),
    )


def test_stale_absent_roster_appears_before_commit(tmp_path: Path) -> None:
    _metadata(tmp_path)
    change = _change("add", first_name="Ari", last_name="Rivera", period="2")
    preview = _preview(tmp_path, change)
    assert preview.current_state_token == "roster-state-v1:absent"

    path = write_class_roster(
        tmp_path, create_roster(CLASS_ID, [_student("0007")])
    )
    before = path.read_bytes()
    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "current_state_changed"
    assert path.read_bytes() == before
    assert not roster_write_lock_path(path).exists()


def test_stale_existing_roster_disappears_before_commit(tmp_path: Path) -> None:
    path = _seed(tmp_path)
    change = _change("update", period="3")
    preview = _preview(tmp_path, change)
    path.unlink()

    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "current_state_changed"
    assert not path.exists()
    assert not roster_write_lock_path(path).exists()


def test_stale_roster_during_lock_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _seed(tmp_path)
    change = _change("update", period="3")
    preview = _preview(tmp_path, change)
    replacement = create_roster(
        CLASS_ID, [_student("0007", "2"), _student("0011", "4")]
    )

    @contextmanager
    def competing_write(roster_path: str | Path) -> Iterator[None]:
        with acquire_roster_write_lock(roster_path):
            # Simulates an external writer that ignores the local lock.
            _write_roster_unlocked(path, replacement, overwrite=True)
            yield

    monkeypatch.setattr(edits, "acquire_roster_write_lock", competing_write)
    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "current_state_changed"
    roster = load_roster(path)
    assert roster.students[0].period == "2"
    assert roster.students[1].period == "4"


def test_noop_still_observes_occupied_roster_lock(tmp_path: Path) -> None:
    path = _seed(tmp_path)
    change = _change("update", period="2")
    preview = _preview(tmp_path, change)
    assert preview.no_change
    lock = roster_write_lock_path(path)
    lock.write_text("occupied", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "write_conflict"
    assert path.read_bytes() == before
    assert lock.read_text(encoding="utf-8") == "occupied"


def test_commit_requires_exact_confirmation_and_tokens(tmp_path: Path) -> None:
    path = _seed(tmp_path)
    change = _change("update", period="3")
    preview = _preview(tmp_path, change)
    before = path.read_bytes()
    with pytest.raises(edits.StudentRosterEditRequestError) as caught:
        _commit(tmp_path, change, preview, confirmed=False)
    assert caught.value.reason == "not_confirmed"

    with pytest.raises(edits.StudentRosterEditRequestError) as caught:
        edits.commit_student_roster_edit(
            tmp_path,
            CLASS_ID,
            change,
            expected_current_state_token="malformed",
            expected_candidate_state_token=preview.candidate_state_token,
            confirmed=True,
        )
    assert caught.value.reason == "invalid_token"
    assert path.read_bytes() == before


def test_replayed_preview_cannot_overwrite_committed_edit(tmp_path: Path) -> None:
    path = _seed(tmp_path)
    change = _change("update", period="3")
    preview = _preview(tmp_path, change)
    first = _commit(tmp_path, change, preview)
    assert first.outcome == "committed"
    after = path.read_bytes()
    with pytest.raises(edits.StudentRosterEditConflictError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "current_state_changed"
    assert path.read_bytes() == after


def test_writer_failure_after_replace_reports_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _seed(tmp_path)
    change = _change("update", period="3")
    preview = _preview(tmp_path, change)
    before = path.read_bytes()

    def replaced_then_error(
        roster_path: str | Path, roster: Roster, *, overwrite: bool = False
    ) -> None:
        _write_roster_unlocked(roster_path, roster, overwrite=overwrite)
        raise RosterWriteError(roster_path, "SECRET_AFTER_REPLACE")

    monkeypatch.setattr(edits, "_write_roster_unlocked", replaced_then_error)
    with pytest.raises(edits.StudentRosterEditWriteError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "write_outcome_uncertain"
    assert "SECRET" not in str(caught.value)
    assert path.read_bytes() != before
    assert load_roster(path).students[0].period == "3"
    assert not roster_write_lock_path(path).exists()


def test_writer_failure_without_replace_remains_definite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _seed(tmp_path)
    change = _change("update", period="3")
    preview = _preview(tmp_path, change)
    before = path.read_bytes()

    def failure(
        roster_path: str | Path, _roster: object, *, overwrite: bool = False
    ) -> None:
        raise RosterWriteError(roster_path, "SECRET_BEFORE_REPLACE")

    monkeypatch.setattr(edits, "_write_roster_unlocked", failure)
    with pytest.raises(edits.StudentRosterEditWriteError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "write_failed"
    assert "SECRET" not in str(caught.value)
    assert path.read_bytes() == before


def test_writer_lock_acquisition_failure_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _seed(tmp_path)
    before = path.read_bytes()
    change = _change("update", period="3")
    preview = _preview(tmp_path, change)

    @contextmanager
    def broken_lock(_path: str | Path) -> Iterator[None]:
        raise RosterWriteLockError("SECRET_LOCK_ERROR")
        yield

    monkeypatch.setattr(edits, "acquire_roster_write_lock", broken_lock)
    with pytest.raises(edits.StudentRosterEditWriteError) as caught:
        _commit(tmp_path, change, preview)
    assert caught.value.reason == "lock_failed"
    assert "SECRET" not in str(caught.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("target", ["classes", "class", "roster", "metadata"])
def test_redirected_canonical_paths_refused(tmp_path: Path, target: str) -> None:
    root = tmp_path / "primary"
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (root / "classes" / CLASS_ID).mkdir(parents=True)
    path = _seed(root)
    before = path.read_bytes()

    if target == "classes":
        outside = foreign / "classes"
        (root / "classes").rename(outside)
        link = root / "classes"
        dest = outside
    elif target == "class":
        outside = foreign / CLASS_ID
        (root / "classes" / CLASS_ID).rename(outside)
        link = root / "classes" / CLASS_ID
        dest = outside
    elif target == "roster":
        outside = foreign / "outside.csv"
        path.rename(outside)
        link = path
        dest = outside
    else:
        source = root / "classes" / CLASS_ID / "class.json"
        source.write_text("{}", encoding="utf-8")
        outside = foreign / "outside.json"
        source.rename(outside)
        link = source
        dest = outside

    try:
        link.symlink_to(dest, target_is_directory=target in {"classes", "class"})
    except (OSError, NotImplementedError) as error:
        pytest.skip(
            f"Filesystem does not support symlinks: {type(error).__name__}"
        )

    with pytest.raises(edits.StudentRosterEditWriteError) as caught:
        _preview(root, _change("update", period="3"))
    assert caught.value.reason == "unsafe_path"
    assert dest.exists()
    if target == "classes":
        assert (dest / CLASS_ID / "roster.csv").is_file()
    if target == "class":
        assert (dest / "roster.csv").is_file()
    if target == "roster":
        assert dest.read_bytes() == before
    assert link.is_symlink()


def test_bounded_class_metadata_error_on_first_add(tmp_path: Path) -> None:
    folder = tmp_path / "classes" / CLASS_ID
    folder.mkdir(parents=True)
    (folder / "class.json").write_text("SECRET_BROKEN_JSON", encoding="utf-8")
    with pytest.raises(edits.StudentRosterEditClassNotFoundError) as caught:
        _preview(
            tmp_path,
            _change("add", first_name="Ari", last_name="Rivera", period="2"),
        )
    assert caught.value.reason == "missing_class_metadata"
    assert "SECRET" not in str(caught.value)
    assert not (folder / "roster.csv").exists()
