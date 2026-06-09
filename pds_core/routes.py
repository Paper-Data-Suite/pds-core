"""Shared route resolution helpers for Paper Data Suite."""

from __future__ import annotations

from pathlib import Path

from pds_core.identifiers import validate_identifier


def classes_dir(root: str | Path) -> Path:
    """Return the shared classes directory."""
    return Path(root) / "classes"


def class_dir(root: str | Path, class_id: str) -> Path:
    """Return the directory for a class."""
    validate_identifier(class_id, "class_id")
    return classes_dir(root) / class_id


def class_roster_path(root: str | Path, class_id: str) -> Path:
    """Return the roster CSV path for a class."""
    return class_dir(root, class_id) / "roster.csv"


def class_assignments_dir(root: str | Path, class_id: str) -> Path:
    """Return the assignments directory for a class."""
    return class_dir(root, class_id) / "assignments"


def assignment_dir(root: str | Path, class_id: str, assignment_id: str) -> Path:
    """Return the directory for an assignment."""
    validate_identifier(assignment_id, "assignment_id")
    return class_assignments_dir(root, class_id) / assignment_id


def assignment_config_path(
    root: str | Path,
    class_id: str,
    assignment_id: str,
) -> Path:
    """Return the assignment configuration JSON path."""
    return assignment_dir(root, class_id, assignment_id) / "assignment.json"


def assignment_templates_dir(
    root: str | Path,
    class_id: str,
    assignment_id: str,
) -> Path:
    """Return the templates directory for an assignment."""
    return assignment_dir(root, class_id, assignment_id) / "templates"


def assignment_scans_dir(
    root: str | Path,
    class_id: str,
    assignment_id: str,
) -> Path:
    """Return the scans directory for an assignment."""
    return assignment_dir(root, class_id, assignment_id) / "scans"


def assignment_submissions_dir(
    root: str | Path,
    class_id: str,
    assignment_id: str,
) -> Path:
    """Return the submissions directory for an assignment."""
    return assignment_dir(root, class_id, assignment_id) / "submissions"


def student_submission_dir(
    root: str | Path,
    class_id: str,
    assignment_id: str,
    student_id: str,
) -> Path:
    """Return the routed submission directory for a student assignment."""
    validate_identifier(student_id, "student_id")
    return assignment_submissions_dir(root, class_id, assignment_id) / student_id


def assignment_results_dir(
    root: str | Path,
    class_id: str,
    assignment_id: str,
) -> Path:
    """Return the results directory for an assignment."""
    return assignment_dir(root, class_id, assignment_id) / "results"


def assignment_debug_dir(
    root: str | Path,
    class_id: str,
    assignment_id: str,
) -> Path:
    """Return the debug directory for an assignment."""
    return assignment_dir(root, class_id, assignment_id) / "debug"