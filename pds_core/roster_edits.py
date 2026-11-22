"""Guarded, class-scoped single-student roster preview and commit.

Core #241: compose existing pure roster transforms, canonical freshness tokens,
and the shared per-roster writer. These services never edit module-owned work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping, TypeAlias

from pds_core._roster_write_lock import (
    RosterWriteLockConflictError,
    RosterWriteLockError,
    acquire_roster_write_lock,
)
from pds_core.class_metadata import (
    ClassMetadataError,
    load_class_metadata_for_class,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.roster_imports import (
    RosterImportRequestError,
    _load_current_state,
    _roster_state_token,
    _validate_state_token,
)
from pds_core.rosters import (
    ROSTER_REQUIRED_COLUMNS,
    Roster,
    RosterReadError,
    RosterValidationError,
    RosterWriteError,
    StudentRecord,
    _write_roster_unlocked,
    add_student_record,
    create_roster,
    remove_student_record,
    replace_student_record,
    student_lookup,
)
from pds_core.routes import class_dir, class_metadata_path, class_roster_path
from pds_core.workspace import WorkspaceRootError, resolve_workspace_root


RosterEditOperation: TypeAlias = Literal["add", "update", "remove"]
RosterEditOutcome: TypeAlias = Literal["committed", "no_change"]

_MUTABLE_FIELDS = frozenset({"first_name", "last_name", "period"})
_IDENTITY_FIELDS = frozenset({"class_id", "student_id"})


class StudentRosterEditError(Exception):
    """Base class for bounded teacher-facing roster-edit refusals."""

    reason: str

    def __init__(self, message: str, *, reason: str) -> None:
        self.reason = reason
        super().__init__(message)


class StudentRosterEditRequestError(StudentRosterEditError):
    """Invalid request, token or missing explicit authorization."""


class StudentRosterEditClassNotFoundError(StudentRosterEditError):
    """No usable canonical class or class metadata for first enrollment."""


class StudentRosterEditValidationError(StudentRosterEditError):
    """Invalid student mutation or invalid canonical roster."""


class StudentRosterEditConflictError(StudentRosterEditError):
    """A reviewed roster/candidate changed or another writer is active."""


class StudentRosterEditWriteError(StudentRosterEditError):
    """A canonical filesystem operation could not complete safely."""


@dataclass(frozen=True, slots=True)
class StudentRosterChange:
    """Exact action for one student, with a defensive immutable field snapshot."""

    operation: RosterEditOperation
    student_id: str
    fields: Mapping[str, str]

    def __post_init__(self) -> None:
        if type(self.operation) is not str or self.operation not in {
            "add",
            "update",
            "remove",
        }:
            raise StudentRosterEditRequestError(
                "Unsupported student roster operation.", reason="invalid_operation"
            )
        if type(self.student_id) is not str:
            raise StudentRosterEditRequestError(
                "Student identity must be a string.", reason="invalid_student_id"
            )
        try:
            validate_identifier(self.student_id, "student_id")
        except IdentifierValidationError as error:
            raise StudentRosterEditRequestError(
                "Student identity is invalid.", reason="invalid_student_id"
            ) from error

        if not isinstance(self.fields, Mapping):
            raise StudentRosterEditRequestError(
                "Change fields must be a mapping.", reason="invalid_fields"
            )
        values: dict[str, str] = {}
        for key, value in self.fields.items():
            if type(key) is not str or not key or key != key.strip():
                raise StudentRosterEditRequestError(
                    "Change field name is invalid.", reason="invalid_fields"
                )
            if key in _IDENTITY_FIELDS:
                raise StudentRosterEditRequestError(
                    "Class and student identities cannot be edited.",
                    reason="immutable_identity",
                )
            if type(value) is not str:
                raise StudentRosterEditRequestError(
                    "Change field values must be strings.", reason="invalid_fields"
                )
            values[key] = value

        if self.operation == "remove" and values:
            raise StudentRosterEditRequestError(
                "Remove must not specify changed fields.", reason="invalid_fields"
            )
        if self.operation == "update" and not values:
            raise StudentRosterEditRequestError(
                "Update must specify at least one field.", reason="invalid_fields"
            )
        if self.operation == "add" and not _MUTABLE_FIELDS.issubset(values):
            raise StudentRosterEditRequestError(
                "Add must include first name, last name and period.",
                reason="missing_required_field",
            )
        object.__setattr__(self, "fields", MappingProxyType(values))


@dataclass(frozen=True, slots=True)
class StudentRosterEditPreview:
    """Read-only reviewed candidate for one exact roster mutation."""

    class_id: str
    operation: RosterEditOperation
    student_id: str
    current_roster_present: bool
    current_record: StudentRecord | None
    proposed_record: StudentRecord | None
    changed_fields: tuple[str, ...]
    current_state_token: str
    candidate_state_token: str
    current_count: int
    proposed_count: int
    no_change: bool


@dataclass(frozen=True, slots=True)
class StudentRosterEditCommitResult:
    """Receipt of an unchanged or successfully persisted canonical roster."""

    class_id: str
    operation: RosterEditOperation
    student_id: str
    outcome: RosterEditOutcome
    previous_state_token: str
    committed_state_token: str
    roster_path: Path


def _validated_scope(workspace_root: str | Path, class_id: str) -> tuple[Path, Path]:
    try:
        selected_class = validate_identifier(class_id, "class_id")
    except (IdentifierValidationError, TypeError) as error:
        raise StudentRosterEditRequestError(
            "Requested class identity is invalid.", reason="invalid_class_id"
        ) from error
    try:
        root = resolve_workspace_root(workspace_root)
        folder = class_dir(root, selected_class)
        roster_path = class_roster_path(root, selected_class)
        metadata_path = class_metadata_path(root, selected_class)

        # Refuse junctions and symlinks below the canonical workspace root.
        # A symlink used to reach the workspace *root* is resolved by Core.
        for path in (root / "classes", folder, roster_path, metadata_path):
            junction = getattr(path, "is_junction", None)
            if path.is_symlink() or (junction is not None and junction()):
                raise StudentRosterEditWriteError(
                    "Canonical roster path is redirected.", reason="unsafe_path"
                )
        if not folder.is_dir():
            raise StudentRosterEditClassNotFoundError(
                "Requested canonical class does not exist.", reason="missing_class"
            )
    except WorkspaceRootError as error:
        raise StudentRosterEditRequestError(
            "Workspace root is invalid.", reason="invalid_workspace"
        ) from error
    except OSError as error:
        raise StudentRosterEditWriteError(
            "Canonical class path could not be inspected.", reason="path_failed"
        ) from error
    return root, roster_path


def _current_state(root: Path, class_id: str) -> tuple[Roster | None, str]:
    try:
        return _load_current_state(root, class_id)
    except RosterValidationError as error:
        raise StudentRosterEditValidationError(
            "Canonical roster failed validation.", reason="invalid_roster"
        ) from error
    except RosterReadError as error:
        raise StudentRosterEditWriteError(
            "Canonical roster could not be read.", reason="read_failed"
        ) from error


def _require_first_enrollment_class(root: Path, class_id: str) -> None:
    try:
        load_class_metadata_for_class(root, class_id)
    except ClassMetadataError as error:
        raise StudentRosterEditClassNotFoundError(
            "First enrollment requires valid existing class metadata.",
            reason="missing_class_metadata",
        ) from error


def _validated_candidate(
    current: Roster | None,
    class_id: str,
    change: StudentRosterChange,
) -> tuple[Roster, StudentRecord | None, StudentRecord | None, tuple[str, ...]]:
    current_record = (
        None if current is None else student_lookup(current).get(change.student_id)
    )
    fields = dict(change.fields)

    if change.operation == "add":
        if current_record is not None:
            raise StudentRosterEditValidationError(
                "Student already belongs to this class.", reason="duplicate_student"
            )
        if current is None:
            optional = tuple(sorted(set(fields) - _MUTABLE_FIELDS))
            columns = (*ROSTER_REQUIRED_COLUMNS, *optional)
            try:
                candidate = create_roster(
                    class_id,
                    [{"student_id": change.student_id, **fields}],
                    columns=columns,
                )
            except RosterValidationError as error:
                raise StudentRosterEditValidationError(
                    "Proposed student does not pass roster validation.",
                    reason="invalid_student",
                ) from error
            return (
                candidate,
                None,
                candidate.students[0],
                tuple(sorted(fields)),
            )

        _check_columns(fields, current.columns)
        extras = {
            key: fields.get(key, "")
            for key in current.columns
            if key not in ROSTER_REQUIRED_COLUMNS
        }
        student = StudentRecord(
            class_id=class_id,
            student_id=change.student_id,
            last_name=fields["last_name"],
            first_name=fields["first_name"],
            period=fields["period"],
            extra_fields=extras,
        )
        try:
            candidate = add_student_record(current, student)
        except RosterValidationError as error:
            raise StudentRosterEditValidationError(
                "Proposed student does not pass roster validation.",
                reason="invalid_student",
            ) from error
        return candidate, None, student, tuple(sorted(fields))

    if current is None or current_record is None:
        raise StudentRosterEditValidationError(
            "Requested student enrollment is missing.", reason="missing_student"
        )

    if change.operation == "update":
        _check_columns(fields, current.columns)
        extras = dict(current_record.extra_fields)
        for key, value in fields.items():
            if key not in _MUTABLE_FIELDS:
                extras[key] = value

        proposed = StudentRecord(
            class_id=class_id,
            student_id=change.student_id,
            last_name=fields.get("last_name", current_record.last_name),
            first_name=fields.get("first_name", current_record.first_name),
            period=fields.get("period", current_record.period),
            extra_fields=extras,
        )
        try:
            candidate = replace_student_record(current, proposed)
        except RosterValidationError as error:
            raise StudentRosterEditValidationError(
                "Proposed student does not pass roster validation.",
                reason="invalid_student",
            ) from error
        changed_fields = tuple(
            sorted(
                key
                for key, value in fields.items()
                if (
                    getattr(current_record, key)
                    if key in _MUTABLE_FIELDS
                    else current_record.extra_fields.get(key, "")
                )
                != value
            )
        )
        return candidate, current_record, proposed, changed_fields

    try:
        candidate = remove_student_record(current, change.student_id)
    except RosterValidationError as error:
        reason = (
            "empty_roster"
            if any(issue.code == "empty_roster" for issue in error.issues)
            else "invalid_student"
        )
        raise StudentRosterEditValidationError(
            "Cannot remove the selected student from this roster.", reason=reason
        ) from error
    return candidate, current_record, None, ()


def _check_columns(fields: Mapping[str, str], columns: tuple[str, ...]) -> None:
    if any(key not in columns for key in fields):
        raise StudentRosterEditValidationError(
            "Change field is not in the existing roster schema.",
            reason="unsupported_field",
        )


def _plan(
    root: Path, roster_path: Path, class_id: str, change: StudentRosterChange
) -> tuple[StudentRosterEditPreview, Roster]:
    current, current_token = _current_state(root, class_id)
    if current is None and change.operation == "add":
        _require_first_enrollment_class(root, class_id)

    candidate, before, after, changed_fields = _validated_candidate(
        current, class_id, change
    )
    candidate_token = _roster_state_token(candidate)
    return (
        StudentRosterEditPreview(
            class_id=class_id,
            operation=change.operation,
            student_id=change.student_id,
            current_roster_present=current is not None,
            current_record=before,
            proposed_record=after,
            changed_fields=changed_fields,
            current_state_token=current_token,
            candidate_state_token=candidate_token,
            current_count=0 if current is None else len(current.students),
            proposed_count=len(candidate.students),
            no_change=candidate_token == current_token,
        ),
        candidate,
    )


def plan_student_roster_edit(
    workspace_root: str | Path,
    class_id: str,
    change: StudentRosterChange,
) -> StudentRosterEditPreview:
    """Review a single-student roster proposal without writing anything."""
    if not isinstance(change, StudentRosterChange):
        raise StudentRosterEditRequestError(
            "Expected a validated student roster change.", reason="invalid_change"
        )
    root, path = _validated_scope(workspace_root, class_id)
    preview, _candidate = _plan(root, path, class_id, change)
    return preview


def _require_state_tokens(current: str, candidate: str) -> None:
    try:
        _validate_state_token(
            current, field_name="expected_current_state_token", allow_absent=True
        )
        _validate_state_token(
            candidate, field_name="expected_candidate_state_token", allow_absent=False
        )
    except RosterImportRequestError as error:
        raise StudentRosterEditRequestError(
            "Reviewed roster state token is invalid.", reason="invalid_token"
        ) from error


def _check_fresh(
    preview: StudentRosterEditPreview,
    expected_current: str,
    expected_candidate: str,
) -> None:
    if preview.current_state_token != expected_current:
        raise StudentRosterEditConflictError(
            "Canonical roster changed after preview.", reason="current_state_changed"
        )
    if preview.candidate_state_token != expected_candidate:
        raise StudentRosterEditConflictError(
            "Proposed student change differs from preview.",
            reason="candidate_changed",
        )


def commit_student_roster_edit(
    workspace_root: str | Path,
    class_id: str,
    change: StudentRosterChange,
    *,
    expected_current_state_token: str,
    expected_candidate_state_token: str,
    confirmed: bool,
) -> StudentRosterEditCommitResult:
    """Commit only the reviewed single-student change under the roster lock."""
    if confirmed is not True:
        raise StudentRosterEditRequestError(
            "An explicit confirmation is required.", reason="not_confirmed"
        )
    _require_state_tokens(expected_current_state_token, expected_candidate_state_token)
    if not isinstance(change, StudentRosterChange):
        raise StudentRosterEditRequestError(
            "Expected a validated student roster change.", reason="invalid_change"
        )

    root, path = _validated_scope(workspace_root, class_id)
    first_preview, _first_candidate = _plan(root, path, class_id, change)
    _check_fresh(
        first_preview, expected_current_state_token, expected_candidate_state_token
    )

    try:
        with acquire_roster_write_lock(path):
            # Re-read under the same lock used by all canonical roster writers.
            _validated_scope(root, class_id)
            preview, candidate = _plan(root, path, class_id, change)
            _check_fresh(
                preview, expected_current_state_token, expected_candidate_state_token
            )
            outcome: RosterEditOutcome = "no_change"
            if not preview.no_change:
                try:
                    _write_roster_unlocked(
                        path, candidate, overwrite=preview.current_roster_present
                    )
                except RosterWriteError as error:
                    raise StudentRosterEditWriteError(
                        "Canonical roster could not be persisted.",
                        reason="write_failed",
                    ) from error
                outcome = "committed"

            return StudentRosterEditCommitResult(
                class_id=class_id,
                operation=change.operation,
                student_id=change.student_id,
                outcome=outcome,
                previous_state_token=preview.current_state_token,
                committed_state_token=preview.candidate_state_token,
                roster_path=path,
            )
    except RosterWriteLockConflictError as error:
        raise StudentRosterEditConflictError(
            "Canonical roster already has an active writer.",
            reason="write_conflict",
        ) from error
    except RosterWriteLockError as error:
        raise StudentRosterEditWriteError(
            "Canonical roster write coordination failed.", reason="lock_failed"
        ) from error
