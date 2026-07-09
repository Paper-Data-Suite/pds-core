"""Tests for shared class folder helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pds_core.class_metadata import (
    create_class_metadata,
    write_class_metadata_for_class,
)
from pds_core.classes import (
    ClassFolder,
    class_folder,
    ensure_class_folder,
    list_class_folders,
    load_class_roster,
    write_class_roster,
)
from pds_core.identifiers import IdentifierValidationError
from pds_core.rosters import (
    Roster,
    RosterValidationError,
    RosterWriteError,
    create_roster,
    load_roster,
    write_roster,
)
from pds_core.routes import class_assignments_dir, class_metadata_path, class_roster_path

OPENED_AT = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)


def make_roster(class_id: str = "english9_p2") -> Roster:
    return create_roster(
        class_id,
        [
            {
                "student_id": "1001",
                "last_name": "Doe",
                "first_name": "Jane",
                "period": "2",
            }
        ],
    )


def test_class_folder_returns_expected_paths(tmp_path: Path) -> None:
    folder = class_folder(tmp_path, "english9_p2")

    assert isinstance(folder, ClassFolder)
    assert folder.class_id == "english9_p2"
    assert folder.class_dir == tmp_path / "classes" / "english9_p2"
    assert folder.roster_path == folder.class_dir / "roster.csv"
    assert folder.metadata_path == folder.class_dir / "class.json"
    assert folder.roster is None
    assert folder.metadata is None
    assert not (tmp_path / "classes").exists()


def test_class_folder_rejects_invalid_class_id(tmp_path: Path) -> None:
    with pytest.raises(IdentifierValidationError, match="class_id"):
        class_folder(tmp_path, "english 9")


def test_ensure_class_folder_creates_class_directories(tmp_path: Path) -> None:
    first = ensure_class_folder(tmp_path, "english9_p2")
    second = ensure_class_folder(tmp_path, "english9_p2")

    assert first == second
    assert first.class_dir.is_dir()
    assert class_assignments_dir(tmp_path, "english9_p2").is_dir()
    assert not first.roster_path.exists()
    assert not first.metadata_path.exists()


def test_load_class_roster_loads_roster_from_canonical_path(
    tmp_path: Path,
) -> None:
    roster = make_roster()
    path = write_class_roster(tmp_path, roster)

    loaded = load_class_roster(tmp_path, "english9_p2")

    assert loaded.class_id == "english9_p2"
    assert loaded.source_path == path


def test_load_class_roster_rejects_mismatched_class_id(tmp_path: Path) -> None:
    folder = ensure_class_folder(tmp_path, "english9_p2")
    write_roster(folder.roster_path, make_roster("english9_p3"))

    with pytest.raises(RosterValidationError) as raised:
        load_class_roster(tmp_path, "english9_p2")

    assert [issue.code for issue in raised.value.issues] == ["class_id_mismatch"]
    issue = raised.value.issues[0]
    assert issue.column == "class_id"
    assert issue.value == "english9_p3"


def test_write_class_roster_writes_to_canonical_path(tmp_path: Path) -> None:
    roster = make_roster()

    path = write_class_roster(tmp_path, roster)

    assert path == class_roster_path(tmp_path, roster.class_id)
    assert load_roster(path).students == roster.students
    assert class_assignments_dir(tmp_path, roster.class_id).is_dir()


def test_write_class_roster_honors_overwrite(tmp_path: Path) -> None:
    roster = make_roster()
    path = write_class_roster(tmp_path, roster)

    with pytest.raises(RosterWriteError):
        write_class_roster(tmp_path, roster)

    assert write_class_roster(tmp_path, roster, overwrite=True) == path


def test_list_class_folders_returns_sorted_class_folders(tmp_path: Path) -> None:
    ensure_class_folder(tmp_path, "english9_p3")
    ensure_class_folder(tmp_path, "english9_p1")
    classes_path = tmp_path / "classes"
    (classes_path / "notes.txt").write_text("not a class", encoding="utf-8")
    (classes_path / "invalid class").mkdir()

    folders = list_class_folders(tmp_path)

    assert [folder.class_id for folder in folders] == [
        "english9_p1",
        "english9_p3",
    ]


def test_list_class_folders_returns_empty_tuple_when_classes_dir_missing(
    tmp_path: Path,
) -> None:
    assert list_class_folders(tmp_path) == ()


def test_list_class_folders_require_roster_filters_missing_rosters(
    tmp_path: Path,
) -> None:
    ensure_class_folder(tmp_path, "english9_p1")
    write_class_roster(tmp_path, make_roster("english9_p2"))

    folders = list_class_folders(tmp_path, require_roster=True)

    assert [folder.class_id for folder in folders] == ["english9_p2"]
    assert folders[0].roster is None
    assert folders[0].metadata is None


def test_list_class_folders_loads_rosters_when_requested(
    tmp_path: Path,
) -> None:
    path = write_class_roster(tmp_path, make_roster())

    folders = list_class_folders(tmp_path, load_rosters=True)

    assert len(folders) == 1
    assert folders[0].roster is not None
    assert folders[0].roster.source_path == path
    assert folders[0].metadata is None


def test_list_class_folders_require_metadata_filters_missing_metadata(
    tmp_path: Path,
) -> None:
    ensure_class_folder(tmp_path, "english9_p1")
    metadata = create_class_metadata(
        "english9_p2",
        "2026-2027",
        created_at=OPENED_AT,
    )
    write_class_metadata_for_class(tmp_path, metadata)

    folders = list_class_folders(tmp_path, require_metadata=True)

    assert [folder.class_id for folder in folders] == ["english9_p2"]
    assert folders[0].metadata_path == class_metadata_path(tmp_path, "english9_p2")
    assert folders[0].metadata is None


def test_list_class_folders_loads_metadata_when_requested(tmp_path: Path) -> None:
    metadata = create_class_metadata(
        "english9_p2",
        "2026-2027",
        created_at=OPENED_AT,
    )
    path = write_class_metadata_for_class(tmp_path, metadata)

    folders = list_class_folders(tmp_path, load_metadata=True)

    assert len(folders) == 1
    assert folders[0].metadata is not None
    assert folders[0].metadata.class_id == "english9_p2"
    assert folders[0].metadata_path == path
    assert folders[0].roster is None


def test_list_class_folders_skips_invalid_metadata_when_loading(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    valid = create_class_metadata(
        "english9_p1",
        "2026-2027",
        created_at=OPENED_AT,
    )
    write_class_metadata_for_class(tmp_path, valid)
    invalid_path = ensure_class_folder(tmp_path, "english9_p2").metadata_path
    invalid_path.write_text("{not json}", encoding="utf-8")

    folders = list_class_folders(tmp_path, load_metadata=True)

    assert [folder.class_id for folder in folders] == ["english9_p1"]
    assert capsys.readouterr() == ("", "")


def test_list_class_folders_roster_loading_does_not_require_metadata(
    tmp_path: Path,
) -> None:
    write_class_roster(tmp_path, make_roster())

    folders = list_class_folders(tmp_path, require_roster=True, load_rosters=True)

    assert [folder.class_id for folder in folders] == ["english9_p2"]
    assert folders[0].roster is not None
    assert folders[0].metadata is None


def test_list_class_folders_skips_invalid_rosters_when_loading(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_class_roster(tmp_path, make_roster("english9_p1"))
    invalid_path = ensure_class_folder(tmp_path, "english9_p2").roster_path
    invalid_path.write_text("not,a,valid,roster\n", encoding="utf-8")

    folders = list_class_folders(tmp_path, load_rosters=True)

    assert [folder.class_id for folder in folders] == ["english9_p1"]
    assert capsys.readouterr() == ("", "")


def test_list_class_folders_skips_mismatched_rosters_when_loading(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder = ensure_class_folder(tmp_path, "english9_p2")
    write_roster(folder.roster_path, make_roster("english9_p3"))

    assert list_class_folders(tmp_path, load_rosters=True) == ()
    assert capsys.readouterr() == ("", "")
