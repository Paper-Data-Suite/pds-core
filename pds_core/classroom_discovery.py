"""Read-only canonical classroom discovery for Core #242.

This module never writes state. Observations are not authorization or
freshness receipts; callers must reload them after shared-menu return.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pds_core.class_metadata import (
    ClassMetadataError,
    load_class_metadata_for_class,
)
from pds_core.classes import load_class_roster
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.rosters import RosterError, student_display_name
from pds_core.routes import (
    class_dir,
    class_metadata_path,
    class_roster_path,
    classes_dir,
)
from pds_core.school_years import (
    SchoolYearStateError,
    load_school_year_state,
    school_year_state_path,
)
from pds_core.workspace import (
    WorkspaceRootError,
    WorkspaceStatus,
    inspect_workspace_root,
)

MAX_DISCOVERED_CLASSES = 512
MAX_DISPLAY_STUDENTS = 5_000
MAX_ROSTER_BYTES = 8 * 1024 * 1024


class ClassroomDiscoveryError(Exception):
    """A bounded read refusal, without raw filesystem exceptions."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ClassroomClassSummary:
    class_id: str
    display_label: str
    school_year: str | None
    metadata_present: bool
    roster_present: bool


@dataclass(frozen=True, slots=True)
class ClassroomOverview:
    workspace: WorkspaceStatus
    active_school_year: str | None
    classes: tuple[ClassroomClassSummary, ...]


@dataclass(frozen=True, slots=True)
class ClassroomStudentChoice:
    student_id: str
    display_name: str
    period: str
    label: str


@dataclass(frozen=True, slots=True)
class ClassroomRosterView:
    class_id: str
    roster_present: bool
    students: tuple[ClassroomStudentChoice, ...]


def _safe_display(value: str) -> str:
    return "".join(
        char if not unicodedata.category(char).startswith("C") else "\ufffd"
        for char in value
    )


def _guard_path(path: Path) -> None:
    """Refuse symlink/junction redirection below a resolved workspace root."""
    try:
        junction = getattr(path, "is_junction", None)
        if (
            path.is_symlink()
            or (junction is not None and junction())
            or path.resolve(strict=False) != path
        ):
            raise ClassroomDiscoveryError(
                "unsafe_path",
                "A canonical classroom path is redirected; inspection refused.",
            )
    except (OSError, RuntimeError) as error:
        raise ClassroomDiscoveryError(
            "path_unavailable",
            "A canonical classroom path could not be inspected safely.",
        ) from error


def _workspace(explicit_root: str | Path | None) -> WorkspaceStatus:
    try:
        status = inspect_workspace_root(explicit_root)
    except WorkspaceRootError as error:
        raise ClassroomDiscoveryError(
            "workspace_unavailable",
            "Selected workspace configuration is unavailable.",
        ) from error
    if status.exists and not status.is_dir:
        raise ClassroomDiscoveryError(
            "invalid_workspace",
            "The selected workspace root is not a directory.",
        )
    return status


def _active_year(root: Path) -> str | None:
    _guard_path(root / "settings")
    _guard_path(school_year_state_path(root))
    try:
        state = load_school_year_state(root)
    except (SchoolYearStateError, OSError) as error:
        raise ClassroomDiscoveryError(
            "invalid_school_year",
            "The canonical school-year state is invalid.",
        ) from error
    if state is None or state.closed_at is not None:
        return None
    return state.active_school_year


def inspect_classroom_overview(
    workspace_root: str | Path | None = None,
) -> ClassroomOverview:
    """Validate workspace/year/class metadata; defer roster loads to selection."""
    status = _workspace(workspace_root)
    if not status.exists:
        return ClassroomOverview(status, None, ())
    root = status.root
    year = _active_year(root)
    parent = classes_dir(root)
    _guard_path(parent)
    try:
        if not parent.exists():
            return ClassroomOverview(status, year, ())
        if not parent.is_dir():
            raise ClassroomDiscoveryError(
                "invalid_classes",
                "The canonical classes collection is not a directory.",
            )
        entries = sorted(parent.iterdir(), key=lambda entry: entry.name)
    except OSError as error:
        raise ClassroomDiscoveryError(
            "classes_unavailable",
            "The classes collection could not be listed.",
        ) from error

    classes: list[ClassroomClassSummary] = []
    for entry in entries:
        _guard_path(entry)
        try:
            if not entry.is_dir():
                continue
        except OSError as error:
            raise ClassroomDiscoveryError(
                "class_unavailable", "A class directory could not be inspected."
            ) from error
        try:
            class_id = validate_identifier(entry.name, "class_id")
        except IdentifierValidationError as error:
            raise ClassroomDiscoveryError(
                "invalid_class",
                "A class directory has an invalid identifier.",
            ) from error
        if len(classes) >= MAX_DISCOVERED_CLASSES:
            raise ClassroomDiscoveryError(
                "too_many_classes",
                "The class collection exceeds the supported display limit.",
            )
        metadata_path = class_metadata_path(root, class_id)
        roster_path = class_roster_path(root, class_id)
        _guard_path(metadata_path)
        _guard_path(roster_path)
        has_metadata = metadata_path.exists()
        has_roster = roster_path.exists()
        if has_metadata and not metadata_path.is_file():
            raise ClassroomDiscoveryError(
                "invalid_metadata", "Class metadata is not a regular file."
            )
        if has_roster and not roster_path.is_file():
            raise ClassroomDiscoveryError(
                "invalid_roster", "Canonical roster is not a regular file."
            )
        school_year: str | None = None
        if has_metadata:
            try:
                school_year = load_class_metadata_for_class(root, class_id).school_year
            except ClassMetadataError as error:
                raise ClassroomDiscoveryError(
                    "invalid_metadata", "Canonical class metadata is invalid."
                ) from error
        classes.append(
            ClassroomClassSummary(
                class_id=class_id,
                display_label=_safe_display(
                    class_id.replace("_", " ").replace("-", " ")
                ),
                school_year=school_year,
                metadata_present=has_metadata,
                roster_present=has_roster,
            )
        )
    return ClassroomOverview(status, year, tuple(classes))


def inspect_classroom_roster(
    workspace_root: str | Path | None,
    class_id: str,
) -> ClassroomRosterView:
    """Validate one roster; disambiguate names using unchanged student IDs."""
    try:
        selected = validate_identifier(class_id, "class_id")
    except IdentifierValidationError as error:
        raise ClassroomDiscoveryError(
            "invalid_class", "Selected class identifier is invalid."
        ) from error

    root = _workspace(workspace_root).root
    folder = class_dir(root, selected)
    path = class_roster_path(root, selected)
    for checked in (classes_dir(root), folder, path):
        _guard_path(checked)
    if not folder.is_dir():
        raise ClassroomDiscoveryError(
            "missing_class", "Selected canonical class no longer exists."
        )
    if not path.exists():
        return ClassroomRosterView(selected, False, ())
    if not path.is_file():
        raise ClassroomDiscoveryError(
            "invalid_roster", "Canonical roster is not a regular file."
        )
    try:
        if path.stat().st_size > MAX_ROSTER_BYTES:
            raise ClassroomDiscoveryError(
                "roster_too_large", "Roster exceeds the browsing size limit."
            )
        roster = load_class_roster(root, selected)
    except (OSError, RosterError) as error:
        raise ClassroomDiscoveryError(
            "invalid_roster", "Canonical roster could not be validated."
        ) from error
    if len(roster.students) > MAX_DISPLAY_STUDENTS:
        raise ClassroomDiscoveryError(
            "roster_too_large", "Roster exceeds the student display limit."
        )
    students = tuple(
        sorted(
            (
                ClassroomStudentChoice(
                    student_id=student.student_id,
                    display_name=_safe_display(student_display_name(student)),
                    period=_safe_display(student.period),
                    label=(
                        f"{_safe_display(student_display_name(student))} "
                        f"(ID: {student.student_id})"
                    ),
                )
                for student in roster.students
            ),
            key=lambda choice: (
                choice.display_name.casefold(),
                choice.student_id,
            ),
        )
    )
    return ClassroomRosterView(selected, True, students)
