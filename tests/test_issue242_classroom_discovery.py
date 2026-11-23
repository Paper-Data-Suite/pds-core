"""Core #242 Slice B1: canonical read-only discovery with synthetic data."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pds_core.class_metadata import (
    create_class_metadata,
    write_class_metadata_for_class,
)
from pds_core.classes import write_class_roster
from pds_core.classroom_discovery import (
    ClassroomDiscoveryError,
    inspect_classroom_overview,
    inspect_classroom_roster,
)
from pds_core.rosters import create_roster
from pds_core.routes import class_metadata_path, class_roster_path
from pds_core.school_years import open_school_year, school_year_state_path

CLASS = "english12_p2"


def _seed_roster(root: Path) -> Path:
    roster = create_roster(
        CLASS,
        [
            {
                "student_id": "0007",
                "first_name": "Ari",
                "last_name": "Rivera",
                "period": "2",
            },
            {
                "student_id": "0011",
                "first_name": "Ari",
                "last_name": "Rivera",
                "period": "2",
            },
            {
                "student_id": "0015",
                "first_name": "Casey",
                "last_name": "Park",
                "period": "2",
            },
        ],
    )
    return write_class_roster(root, roster)


def _seed_metadata(root: Path) -> Path:
    metadata = create_class_metadata(
        CLASS,
        "2026-2027",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    return write_class_metadata_for_class(root, metadata)


def test_missing_workspace_is_distinct_from_empty_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    result = inspect_classroom_overview(missing)
    assert result.workspace.root == missing.resolve()
    assert result.workspace.exists is False
    assert result.active_school_year is None
    assert result.classes == ()
    assert not missing.exists()

    empty = tmp_path / "empty"
    empty.mkdir()
    result = inspect_classroom_overview(empty)
    assert result.workspace.exists is True
    assert result.workspace.is_dir is True
    assert result.classes == ()
    assert list(empty.iterdir()) == []


def test_active_school_year_and_validated_metadata_read_only(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    roster_path = _seed_roster(root)
    metadata_path = _seed_metadata(root)
    open_school_year(
        root,
        "2026-2027",
        opened_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    originals = {
        path: path.read_bytes()
        for path in (
            roster_path,
            metadata_path,
            school_year_state_path(root),
        )
    }

    result = inspect_classroom_overview(root)
    assert result.active_school_year == "2026-2027"
    assert len(result.classes) == 1
    summary = result.classes[0]
    assert summary.class_id == CLASS
    assert summary.school_year == "2026-2027"
    assert summary.display_label == "english12 p2"
    assert summary.metadata_present is True
    assert summary.roster_present is True
    assert all(path.read_bytes() == old for path, old in originals.items())


def test_duplicate_student_names_have_exact_ids_and_stable_order(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    roster_path = _seed_roster(root)
    before = roster_path.read_bytes()

    selected = inspect_classroom_roster(root, CLASS)

    assert selected.roster_present is True
    assert len(selected.students) == 3
    assert [record.student_id for record in selected.students] == [
        "0007",
        "0011",
        "0015",
    ]
    assert selected.students[0].label == "Ari Rivera (ID: 0007)"
    assert selected.students[1].label == "Ari Rivera (ID: 0011)"
    assert selected.students[0].period == "2"
    assert roster_path.read_bytes() == before
    assert not (roster_path.parent / ".roster.write.lock").exists()


def test_missing_roster_is_not_a_corrupt_roster(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _seed_metadata(root)
    result = inspect_classroom_roster(root, CLASS)
    assert result.class_id == CLASS
    assert result.roster_present is False
    assert result.students == ()
    assert not class_roster_path(root, CLASS).exists()


def test_legacy_class_without_metadata_is_visible(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _seed_roster(root)
    result = inspect_classroom_overview(root)
    assert result.classes[0].metadata_present is False
    assert result.classes[0].school_year is None
    assert result.classes[0].roster_present is True
    assert not class_metadata_path(root, CLASS).exists()


@pytest.mark.parametrize(
    ("problem", "reason"),
    [
        ("year", "invalid_school_year"),
        ("metadata", "invalid_metadata"),
        ("roster", "invalid_roster"),
        ("classes-file", "invalid_classes"),
        ("workspace-file", "invalid_workspace"),
    ],
)
def test_corrupted_or_unusable_state_is_not_silent_empty(
    tmp_path: Path, problem: str, reason: str
) -> None:
    root = tmp_path / "workspace"
    if problem == "year":
        year_path = school_year_state_path(root)
        year_path.parent.mkdir(parents=True)
        year_path.write_text("{", encoding="utf-8")
    elif problem == "metadata":
        _seed_roster(root)
        class_metadata_path(root, CLASS).write_text("{", encoding="utf-8")
    elif problem == "roster":
        path = _seed_roster(root)
        path.write_text("not,a,valid,roster\n", encoding="utf-8")
    elif problem == "classes-file":
        root.mkdir()
        (root / "classes").write_text("not a directory", encoding="utf-8")
    else:
        root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ClassroomDiscoveryError) as raised:
        if problem == "roster":
            inspect_classroom_roster(root, CLASS)
        else:
            inspect_classroom_overview(root)
    assert raised.value.reason == reason
    assert str(root) not in str(raised.value)


def test_invalid_class_folder_is_not_silently_ignored(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "classes" / "not valid").mkdir(parents=True)
    with pytest.raises(ClassroomDiscoveryError) as raised:
        inspect_classroom_overview(root)
    assert raised.value.reason == "invalid_class"


def test_missing_or_invalid_class_selection_refuses_without_creation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    for selected, reason in (
        ("../other", "invalid_class"),
        ("missing", "missing_class"),
    ):
        with pytest.raises(ClassroomDiscoveryError) as raised:
            inspect_classroom_roster(root, selected)
        assert raised.value.reason == reason
        assert not root.exists()


def test_redirected_classes_collection_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    protected = root / "classes"
    original = Path.is_symlink

    def redirected(path: Path) -> bool:
        return path == protected or original(path)

    monkeypatch.setattr(Path, "is_symlink", redirected)
    with pytest.raises(ClassroomDiscoveryError) as raised:
        inspect_classroom_overview(root)
    assert raised.value.reason == "unsafe_path"
    assert not protected.exists()


def test_roster_size_limit_refuses_before_read(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    roster_path = _seed_roster(root)
    from pds_core import classroom_discovery

    previous = classroom_discovery.MAX_ROSTER_BYTES
    try:
        classroom_discovery.MAX_ROSTER_BYTES = 1
        with pytest.raises(ClassroomDiscoveryError) as raised:
            inspect_classroom_roster(root, CLASS)
        assert raised.value.reason == "roster_too_large"
    finally:
        classroom_discovery.MAX_ROSTER_BYTES = previous
    assert roster_path.exists()
