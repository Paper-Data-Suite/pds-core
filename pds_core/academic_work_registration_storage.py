"""Strict canonical persistence for Academic Work Registrations."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, NoReturn, cast

from pds_core.academic_work_registrations import (
    AcademicWorkRegistration,
    AcademicWorkRegistrationValidationError,
    academic_work_registration_from_dict,
    academic_work_registration_to_dict,
    validate_academic_work_registration,
    validate_academic_work_registration_transition,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.registry_paths import (
    academic_work_registration_current_path,
    academic_work_registration_dir,
    academic_work_registration_revision_path,
    academic_work_registration_revisions_dir,
    academic_work_registrations_dir,
)
from pds_core.routes import module_work_dir
from pds_core.routing_models import (
    ModuleWorkRef,
    RoutingModelError,
    module_work_ref_from_dict,
    module_work_ref_to_dict,
    validate_module_work_ref,
)
from pds_core.workspace import _normalize_workspace_root

ACADEMIC_WORK_REGISTRATION_CURRENT_SCHEMA_VERSION: Final[str] = "1"
ACADEMIC_WORK_REGISTRATION_CURRENT_RECORD_TYPE: Final[str] = (
    "academic_work_registration_current"
)

_POINTER_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "record_type", "work", "registration_revision"}
)
_REVISION_NAME: Final[re.Pattern[str]] = re.compile(r"^[1-9]\d*\.json$")


class AcademicWorkRegistrationStorageError(RuntimeError):
    """Base error for persisted registration operations."""


class AcademicWorkRegistrationReadError(AcademicWorkRegistrationStorageError):
    """Raised when registration storage cannot be read or validated."""


class AcademicWorkRegistrationWriteError(AcademicWorkRegistrationStorageError):
    """Raised when registration storage cannot be written safely."""


class AcademicWorkRegistrationNotFoundError(AcademicWorkRegistrationReadError):
    """Raised when one explicitly requested registration revision is absent."""


class AcademicWorkRegistrationConflictError(AcademicWorkRegistrationWriteError):
    """Raised for stale revisions, collisions, or concurrent writes."""


class AcademicWorkRegistrationIntegrityError(AcademicWorkRegistrationStorageError):
    """Raised when canonical path identity and persisted identity disagree."""


class _DuplicateJsonKeyError(ValueError):
    pass


class _InvalidJsonConstantError(ValueError):
    pass


def load_academic_work_registration_revision(
    workspace_root: str | Path,
    work: ModuleWorkRef,
    registration_revision: int,
) -> AcademicWorkRegistration:
    """Strictly load one exact registration revision."""
    validated_work = _work(work)
    revision = _positive_revision(registration_revision, "registration_revision")
    path = academic_work_registration_revision_path(workspace_root, validated_work, revision)
    data = _load_json(path, missing_revision=True)
    if not isinstance(data, dict):
        raise AcademicWorkRegistrationReadError(
            f"Academic Work Registration must be a JSON object at {path}."
        )
    try:
        registration = validate_academic_work_registration(
            academic_work_registration_from_dict(data)
        )
    except AcademicWorkRegistrationValidationError as error:
        raise AcademicWorkRegistrationReadError(
            f"Academic Work Registration is invalid at {path}: {error}"
        ) from error
    if registration.work != validated_work:
        raise AcademicWorkRegistrationIntegrityError(
            f"Persisted registration work does not match its canonical path at {path}."
        )
    if registration.registration_revision != revision:
        raise AcademicWorkRegistrationIntegrityError(
            f"Persisted registration revision does not match its canonical path at {path}."
        )
    return registration


def load_current_academic_work_registration(
    workspace_root: str | Path, work: ModuleWorkRef,
) -> AcademicWorkRegistration | None:
    """Load only the explicitly selected current registration."""
    validated_work = _work(work)
    revision = _load_current_pointer(workspace_root, validated_work, missing_ok=True)
    if revision is None:
        return None
    try:
        registration = load_academic_work_registration_revision(
            workspace_root, validated_work, revision
        )
    except AcademicWorkRegistrationNotFoundError as error:
        raise AcademicWorkRegistrationIntegrityError(
            f"Current registration pointer references a missing revision for {validated_work}."
        ) from error
    if registration.work != validated_work or registration.registration_revision != revision:
        raise AcademicWorkRegistrationIntegrityError(
            f"Current registration pointer and revision disagree for {validated_work}."
        )
    return registration


def get_current_academic_work_registration_revision(
    workspace_root: str | Path, work: ModuleWorkRef,
) -> int | None:
    """Return the validated current revision number, if configured."""
    validated_work = _work(work)
    return _load_current_pointer(workspace_root, validated_work, missing_ok=True)


def list_academic_work_registration_revisions(
    workspace_root: str | Path, work: ModuleWorkRef,
) -> tuple[int, ...]:
    """Return all canonical valid revisions in numeric order."""
    validated_work = _work(work)
    directory = academic_work_registration_revisions_dir(workspace_root, validated_work)
    try:
        entries = tuple(directory.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise AcademicWorkRegistrationReadError(
            f"Could not enumerate registration revisions {directory}: {error}"
        ) from error
    revisions: list[int] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            is_file = entry.is_file()
        except OSError as error:
            raise AcademicWorkRegistrationReadError(
                f"Could not inspect registration revision entry {entry}: {error}"
            ) from error
        if not is_file or _REVISION_NAME.fullmatch(entry.name) is None:
            raise AcademicWorkRegistrationReadError(
                f"Unexpected entry in registration revisions: {entry}"
            )
        revision = int(entry.name[:-5])
        load_academic_work_registration_revision(workspace_root, validated_work, revision)
        revisions.append(revision)
    return tuple(sorted(revisions))


def list_academic_work_registration_refs(
    workspace_root: str | Path,
) -> tuple[ModuleWorkRef, ...]:
    """Boundedly list work references having valid current registrations."""
    root = academic_work_registrations_dir(workspace_root)
    levels: list[tuple[Path, str, str]] = []
    for class_entry in _visible_directories(root, "registration class"):
        class_id = _path_identifier(class_entry, "class_id", lowercase=False)
        for module_entry in _visible_directories(class_entry, "registration module"):
            module_id = _path_identifier(module_entry, "module_id", lowercase=True)
            levels.append((module_entry, class_id, module_id))
    configured: list[ModuleWorkRef] = []
    for module_entry, class_id, module_id in levels:
        for work_entry in _visible_directories(module_entry, "registration work"):
            work_id = _path_identifier(work_entry, "work_id", lowercase=False)
            try:
                work = ModuleWorkRef(module_id=module_id, class_id=class_id, work_id=work_id)
            except RoutingModelError as error:
                raise AcademicWorkRegistrationReadError(
                    f"Invalid registration work directory {work_entry}: {error}"
                ) from error
            _validate_registration_directory_entries(work_entry)
            # Keep enumeration bounded while still validating every visible
            # entry in the canonical revisions directory.
            list_academic_work_registration_revisions(workspace_root, work)
            if load_current_academic_work_registration(workspace_root, work) is not None:
                configured.append(work)
    return tuple(sorted(configured, key=lambda value: (
        value.class_id, value.module_id, value.work_id
    )))


def write_academic_work_registration(
    workspace_root: str | Path,
    registration: AcademicWorkRegistration,
    *,
    expected_current_revision: int | None,
) -> Path:
    """Exclusively create a registration revision and atomically select it."""
    if not isinstance(registration, AcademicWorkRegistration):
        raise AcademicWorkRegistrationValidationError(
            "registration must be an AcademicWorkRegistration."
        )
    candidate = validate_academic_work_registration(registration)
    expected = (
        None if expected_current_revision is None else
        _positive_revision(expected_current_revision, "expected_current_revision")
    )
    if expected is None and candidate.registration_revision != 1:
        raise AcademicWorkRegistrationConflictError(
            "An initial Academic Work Registration must use revision 1."
        )
    content = json.dumps(
        academic_work_registration_to_dict(candidate),
        indent=2, sort_keys=True, allow_nan=False,
    ) + "\n"
    producer_root = module_work_dir(_normalize_workspace_root(workspace_root), candidate.work)
    if expected is None:
        _require_existing_producer_work_root(producer_root)

    registration_dir = academic_work_registration_dir(workspace_root, candidate.work)
    revisions_dir = academic_work_registration_revisions_dir(workspace_root, candidate.work)
    path = academic_work_registration_revision_path(
        workspace_root, candidate.work, candidate.registration_revision
    )
    lock_path = registration_dir / ".write.lock"
    try:
        revisions_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise AcademicWorkRegistrationWriteError(
            f"Could not create registration directory {revisions_dir}: {error}"
        ) from error

    lock_created = False
    try:
        try:
            with lock_path.open("x", encoding="utf-8", newline=""):
                lock_created = True
        except FileExistsError as error:
            raise AcademicWorkRegistrationConflictError(
                f"Academic Work Registration write lock already exists: {lock_path}"
            ) from error
        except OSError as error:
            raise AcademicWorkRegistrationWriteError(
                f"Could not acquire registration write lock {lock_path}: {error}"
            ) from error

        _validate_write_state(workspace_root, candidate, expected, path)
        _write_revision_exclusively(path, content)
        try:
            persisted = load_academic_work_registration_revision(
                workspace_root, candidate.work, candidate.registration_revision
            )
        except AcademicWorkRegistrationStorageError as error:
            _remove_file(path)
            raise AcademicWorkRegistrationWriteError(
                f"Could not verify new registration revision {path}: {error}"
            ) from error
        if persisted != candidate:
            _remove_file(path)
            raise AcademicWorkRegistrationWriteError(
                f"Persisted Academic Work Registration differs at {path}."
            )

        _publish_current_pointer(workspace_root, candidate)
        try:
            selected = load_current_academic_work_registration(workspace_root, candidate.work)
        except AcademicWorkRegistrationStorageError as error:
            raise AcademicWorkRegistrationIntegrityError(
                f"Registration pointer was published but could not be verified for {candidate.work}: {error}"
            ) from error
        if selected != candidate:
            raise AcademicWorkRegistrationIntegrityError(
                f"Published registration pointer did not select candidate {candidate.work}."
            )
        return path
    finally:
        if lock_created:
            _remove_file(lock_path)


def _require_existing_producer_work_root(path: Path) -> None:
    """Require an existing producer-owned directory for initial registration."""
    try:
        is_directory = path.is_dir()
    except OSError as error:
        raise AcademicWorkRegistrationWriteError(
            f"Could not inspect producer work root {path}: {error}"
        ) from error
    if not is_directory:
        raise AcademicWorkRegistrationWriteError(
            f"Producer work root must already exist as a directory: {path}"
        )


def _validate_write_state(
    workspace_root: str | Path,
    candidate: AcademicWorkRegistration,
    expected: int | None,
    target_path: Path,
) -> None:
    current_revision = get_current_academic_work_registration_revision(
        workspace_root, candidate.work
    )
    revisions = list_academic_work_registration_revisions(workspace_root, candidate.work)
    if expected is None:
        if current_revision is not None:
            raise AcademicWorkRegistrationConflictError(
                f"A current registration already exists for {candidate.work}."
            )
        if revisions:
            raise AcademicWorkRegistrationIntegrityError(
                f"Orphan registration revisions block initial creation for {candidate.work}."
            )
        return
    if current_revision is None:
        raise AcademicWorkRegistrationConflictError(
            "No current Academic Work Registration exists for the expected revision."
        )
    if current_revision != expected:
        raise AcademicWorkRegistrationConflictError(
            f"Expected current revision {expected}, found {current_revision}."
        )
    current = load_academic_work_registration_revision(
        workspace_root, candidate.work, current_revision
    )
    validate_academic_work_registration_transition(current, candidate)
    if target_path.exists():
        raise AcademicWorkRegistrationConflictError(
            f"Academic Work Registration revision already exists: {target_path}"
        )
    newer = tuple(revision for revision in revisions if revision > current_revision)
    if newer:
        raise AcademicWorkRegistrationIntegrityError(
            "Orphan registration revision(s) newer than current block the write: "
            + ", ".join(str(value) for value in newer) + "."
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
        raise AcademicWorkRegistrationConflictError(
            f"Academic Work Registration revision already exists: {path}"
        ) from error
    except (OSError, UnicodeError) as error:
        if created:
            _remove_file(path)
        raise AcademicWorkRegistrationWriteError(
            f"Could not write Academic Work Registration revision {path}: {error}"
        ) from error


def _publish_current_pointer(
    workspace_root: str | Path, registration: AcademicWorkRegistration,
) -> None:
    path = academic_work_registration_current_path(workspace_root, registration.work)
    content = json.dumps(
        {
            "schema_version": ACADEMIC_WORK_REGISTRATION_CURRENT_SCHEMA_VERSION,
            "record_type": ACADEMIC_WORK_REGISTRATION_CURRENT_RECORD_TYPE,
            "work": module_work_ref_to_dict(registration.work),
            "registration_revision": registration.registration_revision,
        },
        indent=2, sort_keys=True, allow_nan=False,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
        ) as output:
            temporary_path = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory_if_supported(path.parent)
    except (OSError, UnicodeError) as error:
        raise AcademicWorkRegistrationWriteError(
            f"Could not publish Academic Work Registration pointer {path}: {error}"
        ) from error
    finally:
        if temporary_path is not None:
            _remove_file(temporary_path)


def _load_current_pointer(
    workspace_root: str | Path, work: ModuleWorkRef, *, missing_ok: bool,
) -> int | None:
    path = academic_work_registration_current_path(workspace_root, work)
    try:
        data = _load_json(path, missing_revision=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    if not isinstance(data, dict):
        raise AcademicWorkRegistrationReadError(
            f"Academic Work Registration pointer must be a JSON object at {path}."
        )
    try:
        mapping = cast(Mapping[object, object], data)
        keys = frozenset(key for key in mapping if isinstance(key, str))
        if len(keys) != len(mapping) or keys != _POINTER_KEYS:
            missing = sorted(_POINTER_KEYS - keys)
            unknown = sorted(keys - _POINTER_KEYS)
            details = []
            if missing:
                details.append("missing key(s): " + ", ".join(missing))
            if unknown:
                details.append("unknown key(s): " + ", ".join(unknown))
            raise ValueError("current pointer has " + "; ".join(details) + ".")
        if mapping["schema_version"] != ACADEMIC_WORK_REGISTRATION_CURRENT_SCHEMA_VERSION:
            raise ValueError('current pointer schema_version must be "1".')
        if mapping["record_type"] != ACADEMIC_WORK_REGISTRATION_CURRENT_RECORD_TYPE:
            raise ValueError(
                'current pointer record_type must be "academic_work_registration_current".'
            )
        embedded_work = module_work_ref_from_dict(mapping["work"])
        revision = _positive_revision(mapping["registration_revision"], "registration_revision")
    except (RoutingModelError, AcademicWorkRegistrationValidationError, ValueError) as error:
        raise AcademicWorkRegistrationReadError(
            f"Academic Work Registration pointer is invalid at {path}: {error}"
        ) from error
    if embedded_work != work:
        raise AcademicWorkRegistrationIntegrityError(
            f"Registration pointer work does not match its canonical path at {path}."
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
            raise AcademicWorkRegistrationNotFoundError(
                f"Academic Work Registration revision not found: {path}"
            ) from error
        raise
    except (json.JSONDecodeError, UnicodeError, _DuplicateJsonKeyError, _InvalidJsonConstantError) as error:
        raise AcademicWorkRegistrationReadError(
            f"Academic Work Registration contains invalid JSON at {path}: {error}"
        ) from error
    except OSError as error:
        raise AcademicWorkRegistrationReadError(
            f"Could not read Academic Work Registration storage {path}: {error}"
        ) from error


def _visible_directories(root: Path, description: str) -> tuple[Path, ...]:
    try:
        entries = tuple(root.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise AcademicWorkRegistrationReadError(f"Could not enumerate {root}: {error}") from error
    result: list[Path] = []
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.name.startswith("."):
            continue
        try:
            is_directory = entry.is_dir()
        except OSError as error:
            raise AcademicWorkRegistrationReadError(f"Could not inspect {entry}: {error}") from error
        if not is_directory:
            raise AcademicWorkRegistrationReadError(
                f"Unexpected visible {description} entry: {entry}"
            )
        result.append(entry)
    return tuple(result)


def _path_identifier(path: Path, field_name: str, *, lowercase: bool) -> str:
    try:
        value = validate_identifier(path.name, field_name)
    except IdentifierValidationError as error:
        raise AcademicWorkRegistrationReadError(
            f"Invalid {field_name} registry directory {path}: {error}"
        ) from error
    if lowercase and value != value.lower():
        raise AcademicWorkRegistrationReadError(f"{field_name} must be lowercase at {path}.")
    return value


def _validate_registration_directory_entries(directory: Path) -> None:
    """Reject visible entries outside the bounded registration layout."""
    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise AcademicWorkRegistrationReadError(
            f"Could not enumerate registration directory {directory}: {error}"
        ) from error
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.name == "current.json":
            try:
                valid = entry.is_file()
            except OSError as error:
                raise AcademicWorkRegistrationReadError(
                    f"Could not inspect registration entry {entry}: {error}"
                ) from error
        elif entry.name == "revisions":
            try:
                valid = entry.is_dir()
            except OSError as error:
                raise AcademicWorkRegistrationReadError(
                    f"Could not inspect registration entry {entry}: {error}"
                ) from error
        else:
            valid = False
        if not valid:
            raise AcademicWorkRegistrationReadError(
                f"Unexpected visible registration entry: {entry}"
            )


def _work(value: object) -> ModuleWorkRef:
    if not isinstance(value, ModuleWorkRef):
        raise AcademicWorkRegistrationValidationError("work must be a ModuleWorkRef.")
    try:
        return validate_module_work_ref(value)
    except RoutingModelError as error:
        raise AcademicWorkRegistrationValidationError(f"work is invalid: {error}") from error


def _positive_revision(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AcademicWorkRegistrationValidationError(
            f"{field_name} must be a positive integer."
        )
    return value


def _reject_duplicate_keys(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
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
