"""Shared deterministic path helpers for Paper Data Suite."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.routing_models import (
    ModuleWorkRef,
    RouteLocator,
    RoutingModelError,
    validate_module_work_ref,
    validate_route_locator,
)


class ModuleWorkPathError(ValueError):
    """Raised when a module-owned descendant path is unsafe."""


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


def class_metadata_path(root: str | Path, class_id: str) -> Path:
    """Return the class metadata JSON path for a class."""
    return class_dir(root, class_id) / "class.json"


def class_modules_dir(root: str | Path, class_id: str) -> Path:
    """Return the module collection directory for a class."""
    return class_dir(root, class_id) / "modules"


def class_module_dir(
    root: str | Path,
    class_id: str,
    module_id: str,
) -> Path:
    """Return one module's directory within a class."""
    modules_root = class_modules_dir(root, class_id)
    validated_module_id = validate_identifier(module_id, "module_id")
    if validated_module_id != validated_module_id.lower():
        raise IdentifierValidationError("module_id must be lowercase.")
    return modules_root / validated_module_id


def module_work_collection_dir(
    root: str | Path,
    class_id: str,
    module_id: str,
) -> Path:
    """Return one module's work collection directory within a class."""
    return class_module_dir(root, class_id, module_id) / "work"


def module_work_dir(root: str | Path, work: ModuleWorkRef) -> Path:
    """Return the canonical root for a complete module-qualified work identity."""
    if not isinstance(work, ModuleWorkRef):
        raise RoutingModelError("work must be a ModuleWorkRef.")
    validated = validate_module_work_ref(work)
    return (
        module_work_collection_dir(
            root,
            validated.class_id,
            validated.module_id,
        )
        / validated.work_id
    )


def module_routes_dir(root: str | Path, work: ModuleWorkRef) -> Path:
    """Return the canonical route-registration directory for module work."""
    return module_work_dir(root, work) / "routes"


def route_registration_path(root: str | Path, locator: RouteLocator) -> Path:
    """Return the deterministic JSON path for a route registration."""
    if not isinstance(locator, RouteLocator):
        raise RoutingModelError("locator must be a RouteLocator.")
    validated = validate_route_locator(locator)
    return module_routes_dir(root, validated.work) / f"{validated.route_id}.json"


def safe_module_work_descendant(
    root: str | Path,
    work: ModuleWorkRef,
    relative_path: str | Path,
) -> Path:
    """Return a lexically contained module-owned path beneath a work root."""
    if not isinstance(work, ModuleWorkRef):
        raise RoutingModelError("work must be a ModuleWorkRef.")
    validated_work = validate_module_work_ref(work)
    if not isinstance(relative_path, (str, Path)):
        raise ModuleWorkPathError("relative_path must be a string or Path.")

    path_text = str(relative_path)
    if path_text == "":
        raise ModuleWorkPathError("relative_path must not be empty.")
    if path_text != path_text.strip():
        raise ModuleWorkPathError(
            "relative_path must not contain leading or trailing whitespace."
        )
    if "\x00" in path_text:
        raise ModuleWorkPathError("relative_path must not contain NUL characters.")

    windows_path = PureWindowsPath(path_text)
    posix_path = PurePosixPath(path_text)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
    ):
        raise ModuleWorkPathError("relative_path must be a relative descendant path.")

    components = path_text.replace("\\", "/").split("/")
    if any(component == "" for component in components):
        raise ModuleWorkPathError(
            "relative_path must not contain empty path components."
        )
    if any(component in {".", ".."} for component in components):
        raise ModuleWorkPathError(
            "relative_path must not contain traversal components."
        )

    work_root = module_work_dir(root, validated_work)
    descendant = work_root.joinpath(*components)
    try:
        relative_descendant = descendant.relative_to(work_root)
    except ValueError as error:
        raise ModuleWorkPathError(
            "relative_path must remain beneath the module work root."
        ) from error
    if not relative_descendant.parts:
        raise ModuleWorkPathError("relative_path must identify a descendant.")
    return descendant
