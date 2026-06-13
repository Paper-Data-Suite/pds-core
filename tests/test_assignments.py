"""Tests for shared assignment folder helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.assignments import (
    AssignmentFolder,
    assignment_folder,
    ensure_assignment_folder,
    list_assignment_folders,
)
from pds_core.identifiers import IdentifierValidationError
from pds_core.routes import assignment_dir, class_assignments_dir, class_dir


def test_assignment_folder_returns_canonical_paths_without_creating_directories(
    tmp_path: Path,
) -> None:
    folder = assignment_folder(tmp_path, "english9_p2", "unit_1_quiz")

    assert isinstance(folder, AssignmentFolder)
    assert folder.class_id == "english9_p2"
    assert folder.assignment_id == "unit_1_quiz"
    assert folder.class_dir == class_dir(tmp_path, "english9_p2")
    assert folder.assignments_dir == class_assignments_dir(
        tmp_path,
        "english9_p2",
    )
    assert folder.assignment_dir == assignment_dir(
        tmp_path,
        "english9_p2",
        "unit_1_quiz",
    )
    assert not (tmp_path / "classes").exists()


def test_assignment_folder_rejects_invalid_class_id(tmp_path: Path) -> None:
    with pytest.raises(IdentifierValidationError, match="class_id"):
        assignment_folder(tmp_path, "english 9", "unit_1_quiz")


def test_assignment_folder_rejects_invalid_assignment_id(tmp_path: Path) -> None:
    with pytest.raises(IdentifierValidationError, match="assignment_id"):
        assignment_folder(tmp_path, "english9_p2", "unit 1 quiz")


def test_ensure_assignment_folder_creates_assignment_directory(
    tmp_path: Path,
) -> None:
    folder = ensure_assignment_folder(tmp_path, "english9_p2", "unit_1_quiz")

    assert folder.class_dir.is_dir()
    assert folder.assignments_dir.is_dir()
    assert folder.assignment_dir.is_dir()
    assert folder.assignment_dir == assignment_dir(
        tmp_path,
        "english9_p2",
        "unit_1_quiz",
    )
    assert list(folder.assignment_dir.iterdir()) == []


def test_list_assignment_folders_returns_assignment_folders_in_sorted_order(
    tmp_path: Path,
) -> None:
    ensure_assignment_folder(tmp_path, "english9_p2", "unit_3_test")
    ensure_assignment_folder(tmp_path, "english9_p2", "unit_1_quiz")
    ensure_assignment_folder(tmp_path, "english9_p2", "unit_2_essay")

    folders = list_assignment_folders(tmp_path, "english9_p2")

    assert [folder.assignment_id for folder in folders] == [
        "unit_1_quiz",
        "unit_2_essay",
        "unit_3_test",
    ]


def test_list_assignment_folders_skips_non_directories(tmp_path: Path) -> None:
    root = class_assignments_dir(tmp_path, "english9_p2")
    root.mkdir(parents=True)
    (root / "notes.txt").write_text("not an assignment", encoding="utf-8")
    ensure_assignment_folder(tmp_path, "english9_p2", "unit_1_quiz")

    folders = list_assignment_folders(tmp_path, "english9_p2")

    assert [folder.assignment_id for folder in folders] == ["unit_1_quiz"]


def test_list_assignment_folders_skips_invalid_assignment_folder_names(
    tmp_path: Path,
) -> None:
    root = class_assignments_dir(tmp_path, "english9_p2")
    root.mkdir(parents=True)
    (root / "invalid assignment").mkdir()
    ensure_assignment_folder(tmp_path, "english9_p2", "unit_1_quiz")

    folders = list_assignment_folders(tmp_path, "english9_p2")

    assert [folder.assignment_id for folder in folders] == ["unit_1_quiz"]


def test_list_assignment_folders_returns_empty_tuple_when_missing(
    tmp_path: Path,
) -> None:
    assert list_assignment_folders(tmp_path, "english9_p2") == ()


def test_list_assignment_folders_returns_empty_tuple_when_assignments_path_is_file(
    tmp_path: Path,
) -> None:
    root = class_assignments_dir(tmp_path, "english9_p2")
    root.parent.mkdir(parents=True)
    root.write_text("not a directory", encoding="utf-8")

    assert list_assignment_folders(tmp_path, "english9_p2") == ()


def test_list_assignment_folders_rejects_invalid_class_id(tmp_path: Path) -> None:
    with pytest.raises(IdentifierValidationError, match="class_id"):
        list_assignment_folders(tmp_path, "english 9")
