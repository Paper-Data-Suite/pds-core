"""Shared class folder helpers for Paper Data Suite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pds_core.class_metadata import (
    ClassMetadata,
    ClassMetadataError,
    load_class_metadata_for_class,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.rosters import (
    Roster,
    RosterError,
    RosterIssue,
    RosterValidationError,
    load_roster,
    write_roster,
)
from pds_core.routes import (
    class_assignments_dir,
    class_dir,
    class_metadata_path,
    class_roster_path,
    classes_dir,
)


@dataclass(frozen=True, slots=True)
class ClassFolder:
    """Canonical paths and optional roster data for one class folder."""

    class_id: str
    class_dir: Path
    roster_path: Path
    metadata_path: Path
    roster: Roster | None = None
    metadata: ClassMetadata | None = None


def class_folder(workspace_root: str | Path, class_id: str) -> ClassFolder:
    """Return canonical paths for a class without accessing the filesystem."""
    validate_identifier(class_id, "class_id")
    return ClassFolder(
        class_id=class_id,
        class_dir=class_dir(workspace_root, class_id),
        roster_path=class_roster_path(workspace_root, class_id),
        metadata_path=class_metadata_path(workspace_root, class_id),
    )


def ensure_class_folder(workspace_root: str | Path, class_id: str) -> ClassFolder:
    """Create the canonical class-level directories and return their paths."""
    folder = class_folder(workspace_root, class_id)
    class_assignments_dir(workspace_root, class_id).mkdir(
        parents=True,
        exist_ok=True,
    )
    return folder


def _validate_roster_class_id(roster: Roster, class_id: str) -> None:
    if roster.class_id != class_id:
        raise RosterValidationError(
            (
                RosterIssue(
                    code="class_id_mismatch",
                    message="Roster class_id does not match class folder.",
                    column="class_id",
                    value=roster.class_id,
                ),
            )
        )


def load_class_roster(workspace_root: str | Path, class_id: str) -> Roster:
    """Load and validate the canonical roster for a class folder."""
    folder = class_folder(workspace_root, class_id)
    roster = load_roster(folder.roster_path)
    _validate_roster_class_id(roster, class_id)
    return roster


def write_class_roster(
    workspace_root: str | Path,
    roster: Roster,
    *,
    overwrite: bool = False,
) -> Path:
    """Write a roster to its canonical class folder."""
    validate_identifier(roster.class_id, "class_id")
    folder = ensure_class_folder(workspace_root, roster.class_id)
    write_roster(folder.roster_path, roster, overwrite=overwrite)
    return folder.roster_path


def list_class_folders(
    workspace_root: str | Path,
    *,
    require_roster: bool = False,
    load_rosters: bool = False,
    require_metadata: bool = False,
    load_metadata: bool = False,
) -> tuple[ClassFolder, ...]:
    """Discover valid class folders under a workspace root."""
    root = classes_dir(workspace_root)
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    except (FileNotFoundError, NotADirectoryError):
        return ()

    folders: list[ClassFolder] = []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
            validate_identifier(entry.name, "class_id")
        except (IdentifierValidationError, OSError):
            continue

        folder = class_folder(workspace_root, entry.name)
        if (require_roster or load_rosters) and not folder.roster_path.is_file():
            continue
        if (require_metadata or load_metadata) and not folder.metadata_path.is_file():
            continue

        roster: Roster | None = None
        if load_rosters:
            try:
                roster = load_class_roster(workspace_root, entry.name)
            except RosterError:
                continue

        metadata: ClassMetadata | None = None
        if load_metadata:
            try:
                metadata = load_class_metadata_for_class(workspace_root, entry.name)
            except ClassMetadataError:
                continue

        if load_rosters or load_metadata:
            folder = ClassFolder(
                class_id=folder.class_id,
                class_dir=folder.class_dir,
                roster_path=folder.roster_path,
                metadata_path=folder.metadata_path,
                roster=roster,
                metadata=metadata,
            )

        folders.append(folder)

    return tuple(folders)
