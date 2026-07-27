"""Canonical workspace persistence for Academic Period Calendars."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, NoReturn, cast

from pds_core.academic_period_queries import (
    AcademicPeriodLookupError,
    get_academic_period,
)
from pds_core.academic_periods import (
    AcademicPeriod,
    AcademicPeriodCalendar,
    AcademicPeriodRef,
    AcademicPeriodValidationError,
    academic_period_calendar_from_dict,
    academic_period_calendar_to_dict,
    validate_academic_period_calendar,
    validate_academic_period_calendar_transition,
    validate_academic_period_ref,
)
from pds_core.school_years import validate_school_year
from pds_core.workspace import _normalize_workspace_root

ACADEMIC_PERIOD_CURRENT_SCHEMA_VERSION: Final[str] = "1"
ACADEMIC_PERIOD_CURRENT_RECORD_TYPE: Final[str] = (
    "academic_period_calendar_current"
)

_POINTER_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "record_type", "school_year", "calendar_revision"}
)
_REVISION_NAME: Final[re.Pattern[str]] = re.compile(r"^[1-9]\d*\.json$")


class AcademicPeriodCalendarStorageError(RuntimeError):
    """Base error for persisted Academic Period Calendar operations."""


class AcademicPeriodCalendarReadError(AcademicPeriodCalendarStorageError):
    """Raised when calendar storage cannot be read or validated."""


class AcademicPeriodCalendarWriteError(AcademicPeriodCalendarStorageError):
    """Raised when a calendar revision or pointer cannot be written safely."""


class AcademicPeriodCalendarNotFoundError(AcademicPeriodCalendarReadError):
    """Raised when one explicitly requested revision does not exist."""


class AcademicPeriodCalendarConflictError(AcademicPeriodCalendarWriteError):
    """Raised for stale expected revisions or concurrent writes."""


class AcademicPeriodCalendarIntegrityError(AcademicPeriodCalendarStorageError):
    """Raised when canonical path identity and persisted identity disagree."""


class _DuplicateJsonKeyError(ValueError):
    """Raised internally for duplicate JSON object keys."""


class _InvalidJsonConstantError(ValueError):
    """Raised internally for non-standard JSON numbers."""


def academic_periods_dir(workspace_root: str | Path) -> Path:
    """Return the canonical root for Academic Period Calendar storage."""
    return _normalize_workspace_root(workspace_root) / "settings" / "academic_periods"


def academic_period_school_year_dir(
    workspace_root: str | Path,
    school_year: str,
) -> Path:
    """Return one school year's canonical calendar directory."""
    return academic_periods_dir(workspace_root) / validate_school_year(school_year)


def academic_period_revisions_dir(
    workspace_root: str | Path,
    school_year: str,
) -> Path:
    """Return one school year's immutable revision directory."""
    return academic_period_school_year_dir(workspace_root, school_year) / "revisions"


def academic_period_revision_path(
    workspace_root: str | Path,
    school_year: str,
    calendar_revision: int,
) -> Path:
    """Return the canonical path for one immutable calendar revision."""
    revision = _positive_revision(calendar_revision, "calendar_revision")
    return academic_period_revisions_dir(workspace_root, school_year) / f"{revision}.json"


def academic_period_current_path(
    workspace_root: str | Path,
    school_year: str,
) -> Path:
    """Return the canonical current-revision pointer path."""
    return academic_period_school_year_dir(workspace_root, school_year) / "current.json"


def load_academic_period_calendar_revision(
    workspace_root: str | Path,
    school_year: str,
    calendar_revision: int,
) -> AcademicPeriodCalendar:
    """Strictly load and validate one exact calendar revision."""
    validated_school_year = validate_school_year(school_year)
    validated_revision = _positive_revision(
        calendar_revision, "calendar_revision"
    )
    path = academic_period_revision_path(
        workspace_root, validated_school_year, validated_revision
    )
    data = _load_json(path, missing_revision=True)
    if not isinstance(data, dict):
        error = AcademicPeriodValidationError(
            "persisted academic period calendar must be a JSON object."
        )
        raise AcademicPeriodCalendarReadError(
            f"Academic Period Calendar is invalid at {path}: {error}"
        ) from error
    try:
        calendar = academic_period_calendar_from_dict(data)
        validated = validate_academic_period_calendar(calendar)
    except AcademicPeriodValidationError as error:
        raise AcademicPeriodCalendarReadError(
            f"Academic Period Calendar is invalid at {path}: {error}"
        ) from error
    if validated.school_year != validated_school_year:
        raise AcademicPeriodCalendarIntegrityError(
            "Persisted calendar school_year does not match its canonical path "
            f"at {path}."
        )
    if validated.calendar_revision != validated_revision:
        raise AcademicPeriodCalendarIntegrityError(
            "Persisted calendar revision does not match its canonical path "
            f"at {path}."
        )
    return validated


def load_current_academic_period_calendar(
    workspace_root: str | Path,
    school_year: str,
) -> AcademicPeriodCalendar | None:
    """Load the explicitly selected current calendar, if configured."""
    validated_school_year = validate_school_year(school_year)
    pointer = _load_current_pointer(
        workspace_root, validated_school_year, missing_ok=True
    )
    if pointer is None:
        return None
    try:
        calendar = load_academic_period_calendar_revision(
            workspace_root, validated_school_year, pointer
        )
    except AcademicPeriodCalendarNotFoundError as error:
        raise AcademicPeriodCalendarIntegrityError(
            "Current Academic Period Calendar pointer references a missing revision "
            f"for {validated_school_year!r}."
        ) from error
    if calendar.calendar_revision != pointer:
        raise AcademicPeriodCalendarIntegrityError(
            "Current Academic Period Calendar pointer and revision disagree for "
            f"{validated_school_year!r}."
        )
    return calendar


def get_current_academic_period_calendar_revision(
    workspace_root: str | Path,
    school_year: str,
) -> int | None:
    """Return the validated current revision number, if configured."""
    validated_school_year = validate_school_year(school_year)
    return _load_current_pointer(
        workspace_root, validated_school_year, missing_ok=True
    )


def list_academic_period_calendar_school_years(
    workspace_root: str | Path,
) -> tuple[str, ...]:
    """Return school years with valid configured current calendars.

    Hidden implementation artifacts are ignored; visible entries must be
    canonical school-year directories.
    """
    root = academic_periods_dir(workspace_root)
    try:
        entries = tuple(root.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise AcademicPeriodCalendarReadError(
            f"Could not enumerate Academic Period Calendar storage {root}: {error}"
        ) from error

    configured: list[str] = []
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.name.startswith("."):
            continue
        try:
            school_year = validate_school_year(entry.name)
        except ValueError as error:
            raise AcademicPeriodCalendarReadError(
                f"Unexpected entry in Academic Period Calendar storage: {entry}"
            ) from error
        try:
            is_directory = entry.is_dir()
        except OSError as error:
            raise AcademicPeriodCalendarReadError(
                f"Could not inspect Academic Period Calendar entry {entry}: {error}"
            ) from error
        if not is_directory:
            raise AcademicPeriodCalendarReadError(
                f"Academic Period Calendar school-year entry is not a directory: {entry}"
            )
        if load_current_academic_period_calendar(workspace_root, school_year) is not None:
            configured.append(school_year)
    return tuple(configured)


def list_academic_period_calendar_revisions(
    workspace_root: str | Path,
    school_year: str,
) -> tuple[int, ...]:
    """Return all valid canonical revisions in ascending numeric order.

    Hidden interrupted-write artifacts are ignored; visible entries must be
    canonical positive-integer JSON revision files.
    """
    validated_school_year = validate_school_year(school_year)
    directory = academic_period_revisions_dir(workspace_root, validated_school_year)
    try:
        entries = tuple(directory.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise AcademicPeriodCalendarReadError(
            f"Could not enumerate Academic Period Calendar revisions {directory}: {error}"
        ) from error

    revisions: list[int] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            is_file = entry.is_file()
        except OSError as error:
            raise AcademicPeriodCalendarReadError(
                "Could not inspect Academic Period Calendar revision entry "
                f"{entry}: {error}"
            ) from error
        if not is_file or _REVISION_NAME.fullmatch(entry.name) is None:
            raise AcademicPeriodCalendarReadError(
                f"Unexpected entry in Academic Period Calendar revisions: {entry}"
            )
        revision = int(entry.name[:-5])
        load_academic_period_calendar_revision(
            workspace_root, validated_school_year, revision
        )
        revisions.append(revision)
    return tuple(sorted(revisions))


def write_academic_period_calendar(
    workspace_root: str | Path,
    calendar: AcademicPeriodCalendar,
    *,
    expected_current_revision: int | None,
) -> Path:
    """Exclusively create a revision and atomically publish its pointer."""
    if not isinstance(calendar, AcademicPeriodCalendar):
        raise AcademicPeriodValidationError(
            "calendar must be an AcademicPeriodCalendar."
        )
    candidate = validate_academic_period_calendar(calendar)
    expected = (
        None
        if expected_current_revision is None
        else _positive_revision(
            expected_current_revision, "expected_current_revision"
        )
    )
    if expected is None and candidate.calendar_revision != 1:
        raise AcademicPeriodCalendarConflictError(
            "An initial Academic Period Calendar must use revision 1."
        )
    content = json.dumps(
        academic_period_calendar_to_dict(candidate),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    school_year_dir = academic_period_school_year_dir(
        workspace_root, candidate.school_year
    )
    revisions_dir = academic_period_revisions_dir(
        workspace_root, candidate.school_year
    )
    path = academic_period_revision_path(
        workspace_root, candidate.school_year, candidate.calendar_revision
    )
    lock_path = school_year_dir / ".write.lock"

    try:
        revisions_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise AcademicPeriodCalendarWriteError(
            f"Could not create Academic Period Calendar directory {revisions_dir}: {error}"
        ) from error

    lock_created = False
    try:
        try:
            with lock_path.open("x", encoding="utf-8", newline=""):
                lock_created = True
        except FileExistsError as error:
            raise AcademicPeriodCalendarConflictError(
                f"Academic Period Calendar write lock already exists: {lock_path}"
            ) from error
        except OSError as error:
            raise AcademicPeriodCalendarWriteError(
                f"Could not acquire Academic Period Calendar write lock {lock_path}: {error}"
            ) from error

        _validate_write_state(
            workspace_root,
            candidate,
            expected,
            path,
        )
        _write_revision_exclusively(path, content)
        try:
            persisted = load_academic_period_calendar_revision(
                workspace_root,
                candidate.school_year,
                candidate.calendar_revision,
            )
        except AcademicPeriodCalendarStorageError as error:
            _remove_file(path)
            raise AcademicPeriodCalendarWriteError(
                f"Could not verify new Academic Period Calendar revision {path}: {error}"
            ) from error
        if persisted != candidate:
            _remove_file(path)
            raise AcademicPeriodCalendarWriteError(
                f"Persisted Academic Period Calendar revision differs at {path}."
            )

        _publish_current_pointer(workspace_root, candidate)
        try:
            selected = load_current_academic_period_calendar(
                workspace_root, candidate.school_year
            )
        except AcademicPeriodCalendarStorageError as error:
            raise AcademicPeriodCalendarIntegrityError(
                "Academic Period Calendar pointer was published but its selected "
                "revision could not be verified "
                f"for {candidate.school_year!r}: {error}"
            ) from error
        if selected != candidate:
            raise AcademicPeriodCalendarIntegrityError(
                "Published Academic Period Calendar pointer did not resolve to the "
                f"candidate revision for {candidate.school_year!r}."
            )
        return path
    finally:
        if lock_created:
            _remove_file(lock_path)


def resolve_academic_period_ref(
    workspace_root: str | Path,
    reference: AcademicPeriodRef,
    *,
    calendar_revision: int | None = None,
) -> AcademicPeriod:
    """Resolve one school-year-qualified reference against exact workspace state."""
    if not isinstance(reference, AcademicPeriodRef):
        raise AcademicPeriodValidationError(
            "reference must be an AcademicPeriodRef."
        )
    requested = validate_academic_period_ref(reference)
    if calendar_revision is None:
        calendar = load_current_academic_period_calendar(
            workspace_root, requested.school_year
        )
        if calendar is None:
            raise AcademicPeriodLookupError(
                "No current Academic Period Calendar is configured for "
                f"{requested.school_year!r}."
            )
    else:
        revision = _positive_revision(calendar_revision, "calendar_revision")
        calendar = load_academic_period_calendar_revision(
            workspace_root, requested.school_year, revision
        )
    if calendar.school_year != requested.school_year:
        raise AcademicPeriodCalendarIntegrityError(
            "Resolved Academic Period Calendar school_year does not match the reference."
        )
    return get_academic_period(calendar, requested.period_id)


def _validate_write_state(
    workspace_root: str | Path,
    candidate: AcademicPeriodCalendar,
    expected: int | None,
    target_path: Path,
) -> None:
    current_revision = get_current_academic_period_calendar_revision(
        workspace_root, candidate.school_year
    )
    revisions = list_academic_period_calendar_revisions(
        workspace_root, candidate.school_year
    )
    if expected is None:
        if current_revision is not None:
            raise AcademicPeriodCalendarConflictError(
                "A current Academic Period Calendar already exists for "
                f"{candidate.school_year!r}."
            )
        if revisions:
            raise AcademicPeriodCalendarIntegrityError(
                "Orphan Academic Period Calendar revisions block initial creation for "
                f"{candidate.school_year!r}."
            )
        return

    if current_revision is None:
        raise AcademicPeriodCalendarConflictError(
            "No current Academic Period Calendar exists for the expected revision."
        )
    if current_revision != expected:
        raise AcademicPeriodCalendarConflictError(
            f"Expected current revision {expected}, found {current_revision}."
        )
    current = load_academic_period_calendar_revision(
        workspace_root, candidate.school_year, current_revision
    )
    validate_academic_period_calendar_transition(current, candidate)
    if target_path.exists():
        raise AcademicPeriodCalendarConflictError(
            f"Academic Period Calendar revision already exists: {target_path}"
        )
    newer = tuple(revision for revision in revisions if revision > current_revision)
    if newer:
        raise AcademicPeriodCalendarIntegrityError(
            "Orphan Academic Period Calendar revision(s) newer than current block "
            f"the write: {', '.join(str(value) for value in newer)}."
        )


def _write_revision_exclusively(path: Path, content: str) -> None:
    created = False
    try:
        with path.open("x", encoding="utf-8", newline="") as output:
            created = True
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory_if_supported(path.parent)
    except FileExistsError as error:
        if created:
            _remove_file(path)
        raise AcademicPeriodCalendarConflictError(
            f"Academic Period Calendar revision already exists: {path}"
        ) from error
    except (OSError, UnicodeError) as error:
        if created:
            _remove_file(path)
        raise AcademicPeriodCalendarWriteError(
            f"Could not write Academic Period Calendar revision {path}: {error}"
        ) from error


def _publish_current_pointer(
    workspace_root: str | Path,
    calendar: AcademicPeriodCalendar,
) -> None:
    path = academic_period_current_path(workspace_root, calendar.school_year)
    content = json.dumps(
        {
            "schema_version": ACADEMIC_PERIOD_CURRENT_SCHEMA_VERSION,
            "record_type": ACADEMIC_PERIOD_CURRENT_RECORD_TYPE,
            "school_year": calendar.school_year,
            "calendar_revision": calendar.calendar_revision,
        },
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as output:
            temporary_path = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory_if_supported(path.parent)
    except (OSError, UnicodeError) as error:
        raise AcademicPeriodCalendarWriteError(
            f"Could not publish Academic Period Calendar pointer {path}: {error}"
        ) from error
    finally:
        if temporary_path is not None:
            _remove_file(temporary_path)


def _load_current_pointer(
    workspace_root: str | Path,
    school_year: str,
    *,
    missing_ok: bool,
) -> int | None:
    path = academic_period_current_path(workspace_root, school_year)
    try:
        data = _load_json(path, missing_revision=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    if not isinstance(data, dict):
        error = ValueError("current pointer must be a JSON object.")
        raise AcademicPeriodCalendarReadError(
            f"Academic Period Calendar pointer is invalid at {path}: {error}"
        ) from error
    try:
        mapping = cast(Mapping[object, object], data)
        if any(not isinstance(key, str) for key in mapping):
            raise ValueError("current pointer keys must be strings.")
        keys = frozenset(cast(str, key) for key in mapping)
        if keys != _POINTER_KEYS:
            missing = sorted(_POINTER_KEYS - keys)
            unknown = sorted(keys - _POINTER_KEYS)
            details: list[str] = []
            if missing:
                details.append("missing key(s): " + ", ".join(missing))
            if unknown:
                details.append("unknown key(s): " + ", ".join(unknown))
            raise ValueError("current pointer has " + "; ".join(details) + ".")
        if mapping["schema_version"] != ACADEMIC_PERIOD_CURRENT_SCHEMA_VERSION:
            raise ValueError('current pointer schema_version must be "1".')
        if mapping["record_type"] != ACADEMIC_PERIOD_CURRENT_RECORD_TYPE:
            raise ValueError(
                'current pointer record_type must be "academic_period_calendar_current".'
            )
        embedded_school_year = validate_school_year(mapping["school_year"])
        revision = _positive_revision(
            mapping["calendar_revision"], "calendar_revision"
        )
    except (AcademicPeriodValidationError, ValueError) as error:
        raise AcademicPeriodCalendarReadError(
            f"Academic Period Calendar pointer is invalid at {path}: {error}"
        ) from error
    if embedded_school_year != school_year:
        raise AcademicPeriodCalendarIntegrityError(
            "Academic Period Calendar pointer school_year does not match its "
            f"canonical path at {path}."
        )
    return revision


def _load_json(path: Path, *, missing_revision: bool) -> object:
    try:
        with path.open("r", encoding="utf-8") as source:
            return json.load(
                source,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_invalid_constant,
            )
    except FileNotFoundError as error:
        if missing_revision:
            raise AcademicPeriodCalendarNotFoundError(
                f"Academic Period Calendar revision not found: {path}"
            ) from error
        raise
    except (
        json.JSONDecodeError,
        UnicodeError,
        _DuplicateJsonKeyError,
        _InvalidJsonConstantError,
    ) as error:
        raise AcademicPeriodCalendarReadError(
            f"Academic Period Calendar contains invalid JSON at {path}: {error}"
        ) from error
    except OSError as error:
        raise AcademicPeriodCalendarReadError(
            f"Could not read Academic Period Calendar storage {path}: {error}"
        ) from error


def _positive_revision(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AcademicPeriodValidationError(
            f"{field_name} must be a positive integer."
        )
    return value


def _reject_duplicate_keys(
    pairs: Iterable[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_invalid_constant(value: str) -> NoReturn:
    raise _InvalidJsonConstantError(f"invalid JSON numeric constant: {value}")


def _fsync_directory_if_supported(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
