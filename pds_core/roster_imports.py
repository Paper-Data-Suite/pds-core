"""Guarded full-roster import planning and commit services."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pds_core._roster_write_lock import (
    RosterWriteLockConflictError,
    RosterWriteLockError,
    acquire_roster_write_lock,
)
from pds_core.classes import load_class_roster
from pds_core.identifiers import validate_identifier
from pds_core.rosters import (
    Roster,
    RosterError,
    RosterReadError,
    RosterWriteError,
    StudentRecord,
    _student_to_csv_row,
    _validate_roster_instance,
    _write_roster_unlocked,
    load_roster,
    student_lookup,
)
from pds_core.routes import class_roster_path

_STATE_TOKEN_PREFIX: Final[str] = "roster-state-v1"
_ABSENT_STATE_TOKEN: Final[str] = f"{_STATE_TOKEN_PREFIX}:absent"
_STATE_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^{re.escape(_STATE_TOKEN_PREFIX)}:(?:absent|sha256:[0-9a-f]{{64}})$"
)

RosterImportCandidate = Roster | str | Path


@dataclass(frozen=True, slots=True)
class RosterRecordChange:
    """One exact student-record replacement in a full-roster import."""

    student_id: str
    current: StudentRecord
    proposed: StudentRecord


@dataclass(frozen=True, slots=True)
class RosterImportPreview:
    """Immutable, non-mutating comparison of candidate and canonical state."""

    class_id: str
    candidate: Roster
    current_roster_present: bool
    current_state_token: str
    candidate_state_token: str
    additions: tuple[StudentRecord, ...]
    changes: tuple[RosterRecordChange, ...]
    removals: tuple[StudentRecord, ...]
    unchanged_student_ids: tuple[str, ...]

    @property
    def addition_count(self) -> int:
        return len(self.additions)

    @property
    def change_count(self) -> int:
        return len(self.changes)

    @property
    def removal_count(self) -> int:
        return len(self.removals)

    @property
    def unchanged_count(self) -> int:
        return len(self.unchanged_student_ids)


@dataclass(frozen=True, slots=True)
class RosterImportCommitResult:
    """Durable result of one successful guarded roster replacement."""

    class_id: str
    roster_path: Path
    roster: Roster
    previous_state_token: str
    committed_state_token: str


class RosterImportError(RosterError):
    """Base exception for guarded full-roster import operations."""


class RosterImportRequestError(RosterImportError):
    """Raised when a guarded-import request is structurally invalid."""


class RosterImportClassMismatchError(RosterImportRequestError):
    """Raised when the candidate belongs to a different class."""

    expected_class_id: str
    actual_class_id: str

    def __init__(self, expected_class_id: str, actual_class_id: str) -> None:
        self.expected_class_id = expected_class_id
        self.actual_class_id = actual_class_id
        super().__init__(
            "Candidate roster class_id "
            f"{actual_class_id!r} does not match target class_id "
            f"{expected_class_id!r}."
        )


class RosterImportConflictError(RosterImportError):
    """Raised when the reviewed canonical baseline is no longer current."""

    expected_state_token: str | None
    actual_state_token: str | None

    def __init__(
        self,
        message: str,
        *,
        expected_state_token: str | None = None,
        actual_state_token: str | None = None,
    ) -> None:
        self.expected_state_token = expected_state_token
        self.actual_state_token = actual_state_token
        super().__init__(message)


class RosterImportCandidateChangedError(RosterImportConflictError):
    """Raised when the candidate no longer matches the reviewed candidate."""


class RosterImportWriteError(RosterImportError):
    """Raised when guarded write coordination itself cannot be completed."""

    path: Path

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        super().__init__(
            f"Could not coordinate roster import at {self.path}: {message}"
        )


def plan_roster_import(
    workspace_root: str | Path,
    class_id: str,
    candidate: RosterImportCandidate,
) -> RosterImportPreview:
    """Validate and compare a complete candidate roster without writing state."""
    target_class_id = validate_identifier(class_id, "class_id")
    candidate_roster = _validated_candidate(candidate)
    _require_candidate_class(candidate_roster, target_class_id)

    current_roster, current_state_token = _load_current_state(
        workspace_root, target_class_id
    )
    candidate_state_token = _roster_state_token(candidate_roster)

    current_by_id: dict[str, StudentRecord] = (
        {} if current_roster is None else dict(student_lookup(current_roster))
    )
    candidate_by_id: dict[str, StudentRecord] = dict(student_lookup(candidate_roster))

    additions: list[StudentRecord] = []
    changes: list[RosterRecordChange] = []
    removals: list[StudentRecord] = []
    unchanged_student_ids: list[str] = []

    for student_id in sorted(set(current_by_id) | set(candidate_by_id)):
        current_student = current_by_id.get(student_id)
        candidate_student = candidate_by_id.get(student_id)
        if current_student is None:
            assert candidate_student is not None
            additions.append(candidate_student)
        elif candidate_student is None:
            removals.append(current_student)
        elif current_student == candidate_student:
            unchanged_student_ids.append(student_id)
        else:
            changes.append(
                RosterRecordChange(
                    student_id=student_id,
                    current=current_student,
                    proposed=candidate_student,
                )
            )

    return RosterImportPreview(
        class_id=target_class_id,
        candidate=candidate_roster,
        current_roster_present=current_roster is not None,
        current_state_token=current_state_token,
        candidate_state_token=candidate_state_token,
        additions=tuple(additions),
        changes=tuple(changes),
        removals=tuple(removals),
        unchanged_student_ids=tuple(unchanged_student_ids),
    )


def commit_roster_import(
    workspace_root: str | Path,
    class_id: str,
    candidate: RosterImportCandidate,
    *,
    expected_current_state_token: str,
    expected_candidate_state_token: str,
) -> RosterImportCommitResult:
    """Atomically replace a canonical roster only if the reviewed state is current."""
    target_class_id = validate_identifier(class_id, "class_id")
    _validate_state_token(
        expected_current_state_token,
        field_name="expected_current_state_token",
        allow_absent=True,
    )
    _validate_state_token(
        expected_candidate_state_token,
        field_name="expected_candidate_state_token",
        allow_absent=False,
    )

    candidate_roster = _validated_candidate(candidate)
    _require_candidate_class(candidate_roster, target_class_id)
    candidate_state_token = _roster_state_token(candidate_roster)
    if candidate_state_token != expected_candidate_state_token:
        raise RosterImportCandidateChangedError(
            "Candidate roster no longer matches the reviewed candidate state.",
            expected_state_token=expected_candidate_state_token,
            actual_state_token=candidate_state_token,
        )

    roster_path = class_roster_path(workspace_root, target_class_id)
    try:
        with acquire_roster_write_lock(roster_path, create_parent=True):
            current_roster, current_state_token = _load_current_state(
                workspace_root, target_class_id
            )
            if current_state_token != expected_current_state_token:
                raise RosterImportConflictError(
                    "Canonical roster changed after preview; create a new preview "
                    "before committing.",
                    expected_state_token=expected_current_state_token,
                    actual_state_token=current_state_token,
                )

            _write_roster_unlocked(
                roster_path,
                candidate_roster,
                overwrite=current_roster is not None,
            )
    except RosterWriteLockConflictError as error:
        raise RosterImportConflictError(
            "Another canonical roster write is already in progress; retry from a "
            "fresh preview."
        ) from error
    except RosterWriteLockError as error:
        raise RosterImportWriteError(roster_path, str(error)) from error
    except RosterWriteError:
        raise

    committed_roster = Roster(
        class_id=candidate_roster.class_id,
        students=candidate_roster.students,
        columns=candidate_roster.columns,
        source_path=roster_path,
    )
    return RosterImportCommitResult(
        class_id=target_class_id,
        roster_path=roster_path,
        roster=committed_roster,
        previous_state_token=expected_current_state_token,
        committed_state_token=candidate_state_token,
    )


def _validated_candidate(candidate: RosterImportCandidate) -> Roster:
    if isinstance(candidate, Roster):
        return _validate_roster_instance(candidate)
    if isinstance(candidate, (str, Path)):
        return load_roster(candidate)
    raise RosterImportRequestError(
        "candidate must be a validated Roster or a roster CSV path."
    )


def _require_candidate_class(candidate: Roster, class_id: str) -> None:
    if candidate.class_id != class_id:
        raise RosterImportClassMismatchError(class_id, candidate.class_id)


def _load_current_state(
    workspace_root: str | Path,
    class_id: str,
) -> tuple[Roster | None, str]:
    path = class_roster_path(workspace_root, class_id)
    try:
        path.lstat()
    except FileNotFoundError:
        return None, _ABSENT_STATE_TOKEN
    except OSError as error:
        raise RosterReadError(path, str(error)) from error

    roster = load_class_roster(workspace_root, class_id)
    return roster, _roster_state_token(roster)


def _roster_state_token(roster: Roster) -> str:
    canonical_bytes = _canonical_roster_bytes(roster)
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    return f"{_STATE_TOKEN_PREFIX}:sha256:{digest}"


def _canonical_roster_bytes(roster: Roster) -> bytes:
    validated = _validate_roster_instance(roster)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=validated.columns)
    writer.writeheader()
    for student in validated.students:
        writer.writerow(_student_to_csv_row(student, validated.columns))
    return output.getvalue().encode("utf-8")


def _validate_state_token(
    value: str,
    *,
    field_name: str,
    allow_absent: bool,
) -> None:
    if not isinstance(value, str) or _STATE_TOKEN_PATTERN.fullmatch(value) is None:
        raise RosterImportRequestError(
            f"{field_name} is not a valid guarded-roster state token."
        )
    if not allow_absent and value == _ABSENT_STATE_TOKEN:
        raise RosterImportRequestError(
            f"{field_name} must identify a concrete candidate roster state."
        )
