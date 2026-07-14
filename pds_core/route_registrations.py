"""Persisted route-registration creation, loading, and resolution."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

from pds_core.routes import (
    class_dir,
    class_module_dir,
    module_work_dir,
    route_registration_path,
)
from pds_core.routing_models import (
    RouteLocator,
    RouteRegistration,
    RouteResolution,
    RoutingModelError,
    route_registration_from_dict,
    route_registration_to_dict,
    validate_route_locator,
    validate_route_registration,
)


class RouteRegistrationPersistenceError(RuntimeError):
    """Base error for persisted route-registration operations."""


class RouteRegistrationWriteError(RouteRegistrationPersistenceError):
    """Raised when a route registration cannot be created safely."""


class RouteRegistrationReadError(RouteRegistrationPersistenceError):
    """Raised when a persisted route registration cannot be read or validated."""


class RouteRegistrationNotFoundError(RouteRegistrationReadError):
    """Raised when the deterministic registration path does not exist."""


class RouteRegistrationIntegrityError(RouteRegistrationReadError):
    """Raised when persisted route identity does not match the requested locator."""


class _DuplicateJsonKeyError(ValueError):
    """Raised internally when persisted JSON repeats an object key."""


class _InvalidJsonConstantError(ValueError):
    """Raised internally when persisted JSON contains a non-standard number."""


def write_route_registration(
    root: str | Path,
    registration: RouteRegistration,
) -> Path:
    """Validate and exclusively persist one route registration."""
    if not isinstance(registration, RouteRegistration):
        raise RoutingModelError("registration must be a RouteRegistration.")
    validated = validate_route_registration(registration)
    path = route_registration_path(root, validated.locator)
    content = json.dumps(
        route_registration_to_dict(validated),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RouteRegistrationWriteError(
            f"Could not create route-registration directory {path.parent}: {error}"
        ) from error

    created = False
    try:
        with path.open("x", encoding="utf-8", newline="") as registration_file:
            created = True
            registration_file.write(content)
            registration_file.flush()
            os.fsync(registration_file.fileno())
    except FileExistsError as error:
        if not created:
            raise RouteRegistrationWriteError(
                f"Route registration already exists: {path}"
            ) from error
        _remove_incomplete_registration(path)
        raise RouteRegistrationWriteError(
            f"Could not write route registration {path}: {error}"
        ) from error
    except (OSError, UnicodeError) as error:
        if created:
            _remove_incomplete_registration(path)
        raise RouteRegistrationWriteError(
            f"Could not write route registration {path}: {error}"
        ) from error
    return path


def load_route_registration(
    root: str | Path,
    locator: RouteLocator,
) -> RouteRegistration:
    """Load and validate the registration at one locator's canonical path."""
    if not isinstance(locator, RouteLocator):
        raise RoutingModelError("locator must be a RouteLocator.")
    requested = validate_route_locator(locator)
    path = route_registration_path(root, requested)

    try:
        with path.open("r", encoding="utf-8") as registration_file:
            data = json.load(
                registration_file,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_invalid_json_constant,
            )
    except FileNotFoundError as error:
        raise RouteRegistrationNotFoundError(
            f"Route registration not found at canonical path: {path}"
        ) from error
    except (json.JSONDecodeError, UnicodeError, _DuplicateJsonKeyError,
            _InvalidJsonConstantError) as error:
        raise RouteRegistrationReadError(
            f"Route registration contains invalid JSON at {path}: {error}"
        ) from error
    except OSError as error:
        raise RouteRegistrationReadError(
            f"Could not read route registration {path}: {error}"
        ) from error

    if not isinstance(data, dict):
        model_error = RoutingModelError(
            "persisted route registration must be a JSON object."
        )
        raise RouteRegistrationReadError(
            f"Route registration is invalid at {path}: {model_error}"
        ) from model_error
    try:
        registration = route_registration_from_dict(data)
        validated = validate_route_registration(registration)
    except RoutingModelError as error:
        raise RouteRegistrationReadError(
            f"Route registration is invalid at {path}: {error}"
        ) from error

    if validated.locator != requested:
        raise RouteRegistrationIntegrityError(
            "Persisted route locator does not exactly match the requested locator "
            f"at {path}."
        )
    return validated


def resolve_route_registration(
    root: str | Path,
    locator: RouteLocator,
) -> RouteResolution:
    """Load an exact registration and calculate its shared canonical roots."""
    if not isinstance(locator, RouteLocator):
        raise RoutingModelError("locator must be a RouteLocator.")
    requested = validate_route_locator(locator)
    registration = load_route_registration(root, requested)
    return RouteResolution(
        locator=requested,
        registration=registration,
        class_root=class_dir(root, requested.class_id),
        module_root=class_module_dir(
            root,
            requested.class_id,
            requested.module_id,
        ),
        work_root=module_work_dir(root, requested.work),
    )


def _reject_duplicate_keys(
    pairs: Iterable[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_invalid_json_constant(value: str) -> NoReturn:
    raise _InvalidJsonConstantError(f"invalid JSON numeric constant: {value}")


def _remove_incomplete_registration(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
