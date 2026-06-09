"""Tests for shared route resolution helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.identifiers import IdentifierValidationError
from pds_core.routes import (
    assignment_config_path,
    assignment_debug_dir,
    assignment_dir,
    assignment_results_dir,
    assignment_scans_dir,
    assignment_submissions_dir,
    assignment_templates_dir,
    class_assignments_dir,
    class_dir,
    class_roster_path,
    classes_dir,
    student_submission_dir,
)


def test_classes_dir_accepts_string_root() -> None:
    assert classes_dir("paper_data") == Path("paper_data") / "classes"


def test_classes_dir_accepts_path_root() -> None:
    assert classes_dir(Path("paper_data")) == Path("paper_data") / "classes"


def test_class_dir() -> None:
    assert class_dir("paper_data", "english12_p4") == (
        Path("paper_data") / "classes" / "english12_p4"
    )


def test_class_roster_path() -> None:
    assert class_roster_path("paper_data", "english12_p4") == (
        Path("paper_data") / "classes" / "english12_p4" / "roster.csv"
    )


def test_class_assignments_dir() -> None:
    assert class_assignments_dir("paper_data", "english12_p4") == (
        Path("paper_data") / "classes" / "english12_p4" / "assignments"
    )


def test_assignment_dir() -> None:
    assert assignment_dir("paper_data", "english12_p4", "personal_narrative") == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
    )


def test_assignment_config_path() -> None:
    assert assignment_config_path(
        "paper_data",
        "english12_p4",
        "personal_narrative",
    ) == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "assignment.json"
    )


def test_assignment_templates_dir() -> None:
    assert assignment_templates_dir(
        "paper_data",
        "english12_p4",
        "personal_narrative",
    ) == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "templates"
    )


def test_assignment_scans_dir() -> None:
    assert assignment_scans_dir(
        "paper_data",
        "english12_p4",
        "personal_narrative",
    ) == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "scans"
    )


def test_assignment_submissions_dir() -> None:
    assert assignment_submissions_dir(
        "paper_data",
        "english12_p4",
        "personal_narrative",
    ) == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "submissions"
    )


def test_student_submission_dir() -> None:
    assert student_submission_dir(
        "paper_data",
        "english12_p4",
        "personal_narrative",
        "1001",
    ) == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "submissions"
        / "1001"
    )


def test_assignment_results_dir() -> None:
    assert assignment_results_dir(
        "paper_data",
        "english12_p4",
        "personal_narrative",
    ) == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "results"
    )


def test_assignment_debug_dir() -> None:
    assert assignment_debug_dir(
        "paper_data",
        "english12_p4",
        "personal_narrative",
    ) == (
        Path("paper_data")
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "debug"
    )


@pytest.mark.parametrize(
    "class_id",
    [
        "English 12",
        "../english12_p4",
        "classes/english12_p4",
        "english12;p4",
        "english12|p4",
        " english12_p4",
        "english12_p4 ",
    ],
)
def test_routes_reject_invalid_class_ids(class_id: str) -> None:
    with pytest.raises(IdentifierValidationError, match="class_id"):
        class_dir("paper_data", class_id)


@pytest.mark.parametrize(
    "assignment_id",
    [
        "personal narrative",
        "../personal_narrative",
        "assignments/personal_narrative",
        "aid=personal_narrative",
        "personal|narrative",
        " personal_narrative",
        "personal_narrative ",
    ],
)
def test_routes_reject_invalid_assignment_ids(assignment_id: str) -> None:
    with pytest.raises(IdentifierValidationError, match="assignment_id"):
        assignment_dir("paper_data", "english12_p4", assignment_id)


@pytest.mark.parametrize(
    "student_id",
    [
        "student 1001",
        "../1001",
        "students/1001",
        "sid=1001",
        "student|1001",
        " 1001",
        "1001 ",
    ],
)
def test_routes_reject_invalid_student_ids(student_id: str) -> None:
    with pytest.raises(IdentifierValidationError, match="student_id"):
        student_submission_dir(
            "paper_data",
            "english12_p4",
            "personal_narrative",
            student_id,
        )


def test_route_helpers_do_not_create_directories(tmp_path: Path) -> None:
    route = assignment_results_dir(tmp_path, "english12_p4", "personal_narrative")

    assert route == (
        tmp_path
        / "classes"
        / "english12_p4"
        / "assignments"
        / "personal_narrative"
        / "results"
    )
    assert not route.exists()
    assert not (tmp_path / "classes").exists()