"""Shared assignment folder helpers for Paper Data Suite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.routes import assignment_dir, class_assignments_dir, class_dir


@dataclass(frozen=True, slots=True)
class AssignmentFolder:
    """Canonical paths for one assignment folder."""

    class_id: str
    assignment_id: str
    class_dir: Path
    assignments_dir: Path
    assignment_dir: Path


def assignment_folder(
    workspace_root: str | Path,
    class_id: str,
    assignment_id: str,
) -> AssignmentFolder:
    """Return canonical paths for an assignment without filesystem access."""
    validate_identifier(class_id, "class_id")
    validate_identifier(assignment_id, "assignment_id")
    return AssignmentFolder(
        class_id=class_id,
        assignment_id=assignment_id,
        class_dir=class_dir(workspace_root, class_id),
        assignments_dir=class_assignments_dir(workspace_root, class_id),
        assignment_dir=assignment_dir(workspace_root, class_id, assignment_id),
    )


def ensure_assignment_folder(
    workspace_root: str | Path,
    class_id: str,
    assignment_id: str,
) -> AssignmentFolder:
    """Create the canonical assignment directory and return its paths."""
    folder = assignment_folder(workspace_root, class_id, assignment_id)
    folder.assignment_dir.mkdir(parents=True, exist_ok=True)
    return folder


def list_assignment_folders(
    workspace_root: str | Path,
    class_id: str,
) -> tuple[AssignmentFolder, ...]:
    """Discover valid assignment folders for a class."""
    validate_identifier(class_id, "class_id")
    root = class_assignments_dir(workspace_root, class_id)
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    except (FileNotFoundError, NotADirectoryError):
        return ()

    folders: list[AssignmentFolder] = []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
            validate_identifier(entry.name, "assignment_id")
        except (IdentifierValidationError, OSError):
            continue

        folders.append(assignment_folder(workspace_root, class_id, entry.name))

    return tuple(folders)
