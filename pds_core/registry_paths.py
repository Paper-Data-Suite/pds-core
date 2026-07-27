"""Pure canonical path helpers for the neutral Core registry."""

from __future__ import annotations

from pathlib import Path

from pds_core.academic_work_registrations import AcademicWorkRegistrationValidationError
from pds_core.routing_models import ModuleWorkRef, RoutingModelError, validate_module_work_ref
from pds_core.workspace import _normalize_workspace_root


def registry_dir(workspace_root: str | Path) -> Path:
    """Return the neutral Core registry root."""
    return _normalize_workspace_root(workspace_root) / "registry"


def academic_work_registrations_dir(workspace_root: str | Path) -> Path:
    """Return the registry collection containing work identities."""
    return registry_dir(workspace_root) / "work"


def academic_work_registration_dir(
    workspace_root: str | Path, work: ModuleWorkRef,
) -> Path:
    """Return one work identity's registration directory."""
    validated = _work(work)
    return (
        academic_work_registrations_dir(workspace_root)
        / validated.class_id / validated.module_id / validated.work_id
    )


def academic_work_registration_revisions_dir(
    workspace_root: str | Path, work: ModuleWorkRef,
) -> Path:
    """Return one registration's immutable revision directory."""
    return academic_work_registration_dir(workspace_root, work) / "revisions"


def academic_work_registration_revision_path(
    workspace_root: str | Path, work: ModuleWorkRef, registration_revision: int,
) -> Path:
    """Return the canonical path for one immutable registration revision."""
    revision = _positive_revision(registration_revision)
    return academic_work_registration_revisions_dir(workspace_root, work) / f"{revision}.json"


def academic_work_registration_current_path(
    workspace_root: str | Path, work: ModuleWorkRef,
) -> Path:
    """Return the canonical current-registration pointer path."""
    return academic_work_registration_dir(workspace_root, work) / "current.json"


def _work(value: object) -> ModuleWorkRef:
    if not isinstance(value, ModuleWorkRef):
        raise AcademicWorkRegistrationValidationError("work must be a ModuleWorkRef.")
    try:
        return validate_module_work_ref(value)
    except RoutingModelError as error:
        raise AcademicWorkRegistrationValidationError(f"work is invalid: {error}") from error


def _positive_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AcademicWorkRegistrationValidationError(
            "registration_revision must be a positive integer."
        )
    return value
