"""Compatibility checks and page-by-page module route dispatch."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from pds_core.module_profiles import (
    CORE_ROUTING_CONTRACT_VERSION,
    ModuleProfile,
    ModuleRegistry,
    ModuleRegistryError,
    UnsupportedModuleError,
)
from pds_core.route_registrations import (
    RouteRegistrationPersistenceError,
    resolve_route_registration,
)
from pds_core.routing_models import (
    RouteLocator,
    RouteResolution,
    RoutingModelError,
    validate_route_locator,
)
from pds_core.scan_retention import RetainedSourceScan


class RouteDispatchRequestError(ValueError):
    """Raised when a dispatch request is invalid."""


class ModuleDispatchError(RuntimeError):
    """Base error for module compatibility and route dispatch."""


class ModuleContractCompatibilityError(ModuleDispatchError):
    """Raised when a module profile does not support a required contract."""


class RouteStatusNotDispatchableError(ModuleDispatchError):
    """Raised when the registration status is not dispatchable by the profile."""


class ModuleRegistrationValidationError(ModuleDispatchError):
    """Raised when module-specific registration validation fails."""


class ModuleRouteHandlingError(ModuleDispatchError):
    """Raised when the selected module handler fails."""


@dataclass(frozen=True, slots=True)
class RouteDispatchRequest:
    """A validated request to dispatch one retained-source page."""

    locator: RouteLocator
    retained_source: RetainedSourceScan
    source_page_number: int

    def __post_init__(self) -> None:
        _validate_dispatch_request(self)


@dataclass(frozen=True, slots=True)
class RouteDispatchSuccess:
    """A successful one-page module dispatch result."""

    request: RouteDispatchRequest
    profile: ModuleProfile
    resolution: RouteResolution
    module_result: object


@dataclass(frozen=True, slots=True)
class RouteDispatchFailure:
    """An expected one-page dispatch failure in a batch."""

    request: RouteDispatchRequest
    error: Exception


RouteDispatchOutcome: TypeAlias = RouteDispatchSuccess | RouteDispatchFailure


def dispatch_route(
    root: str | Path,
    registry: ModuleRegistry,
    request: RouteDispatchRequest,
) -> RouteDispatchSuccess:
    """Resolve and dispatch one retained-source page to its owning module."""
    validated_request = _validate_dispatch_request(request)
    if not isinstance(registry, ModuleRegistry):
        raise ModuleRegistryError("registry must be a ModuleRegistry.")

    profile = registry.require(validated_request.locator.module_id)
    _check_preload_compatibility(profile, validated_request)

    resolution = resolve_route_registration(root, validated_request.locator)
    _check_registration_compatibility(profile, validated_request, resolution)

    validator = profile.registration_validator
    if validator is not None:
        try:
            validator_result = validator(resolution.registration)
        except Exception as error:
            raise ModuleRegistrationValidationError(
                f"Registration validation failed for module "
                f"{profile.module_id!r} and route "
                f"{validated_request.locator.route_id!r}."
            ) from error
        if validator_result is not None:
            raise ModuleRegistrationValidationError(
                f"Registration validator for module {profile.module_id!r} "
                "must return None."
            )

    try:
        module_result = profile.route_handler(
            resolution,
            validated_request.retained_source,
            validated_request.source_page_number,
        )
    except Exception as error:
        raise ModuleRouteHandlingError(
            f"Route handler failed for module {profile.module_id!r} and route "
            f"{validated_request.locator.route_id!r}."
        ) from error

    return RouteDispatchSuccess(
        request=validated_request,
        profile=profile,
        resolution=resolution,
        module_result=module_result,
    )


def dispatch_routes(
    root: str | Path,
    registry: ModuleRegistry,
    requests: Iterable[RouteDispatchRequest],
) -> tuple[RouteDispatchOutcome, ...]:
    """Dispatch requests sequentially while isolating expected page failures."""
    outcomes: list[RouteDispatchOutcome] = []
    for request in requests:
        try:
            outcomes.append(dispatch_route(root, registry, request))
        except (
            RouteDispatchRequestError,
            UnsupportedModuleError,
            ModuleDispatchError,
            RouteRegistrationPersistenceError,
            RoutingModelError,
        ) as error:
            outcomes.append(RouteDispatchFailure(request=request, error=error))
    return tuple(outcomes)


def _validate_dispatch_request(value: object) -> RouteDispatchRequest:
    if not isinstance(value, RouteDispatchRequest):
        raise RouteDispatchRequestError(
            "request must be a RouteDispatchRequest."
        )
    if not isinstance(value.locator, RouteLocator):
        raise RouteDispatchRequestError("locator must be a RouteLocator.")
    try:
        validate_route_locator(value.locator)
    except (RoutingModelError, AttributeError, ValueError) as error:
        raise RouteDispatchRequestError("locator is not valid.") from error
    if not isinstance(value.retained_source, RetainedSourceScan):
        raise RouteDispatchRequestError(
            "retained_source must be a RetainedSourceScan."
        )
    if (
        not isinstance(value.source_page_number, int)
        or isinstance(value.source_page_number, bool)
        or value.source_page_number < 1
    ):
        raise RouteDispatchRequestError(
            "source_page_number must be an integer greater than or equal to one."
        )
    return value


def _check_preload_compatibility(
    profile: ModuleProfile,
    request: RouteDispatchRequest,
) -> None:
    if (
        CORE_ROUTING_CONTRACT_VERSION
        not in profile.supported_core_routing_contract_versions
    ):
        supported = ", ".join(
            sorted(profile.supported_core_routing_contract_versions)
        )
        raise ModuleContractCompatibilityError(
            f"Module {profile.module_id!r} does not support active Core routing "
            f"contract {CORE_ROUTING_CONTRACT_VERSION!r}; supported versions: "
            f"{supported}."
        )
    if request.locator.schema not in profile.supported_qr_schemas:
        supported = ", ".join(sorted(profile.supported_qr_schemas))
        raise ModuleContractCompatibilityError(
            f"Module {profile.module_id!r} does not support QR schema "
            f"{request.locator.schema!r}; supported schemas: {supported}."
        )


def _check_registration_compatibility(
    profile: ModuleProfile,
    request: RouteDispatchRequest,
    resolution: RouteResolution,
) -> None:
    registration = resolution.registration
    identities = (
        request.locator.module_id,
        registration.locator.module_id,
        registration.target.module_id,
    )
    if any(module_id != profile.module_id for module_id in identities):
        raise ModuleContractCompatibilityError(
            f"Module identity is inconsistent for profile "
            f"{profile.module_id!r} and route {request.locator.route_id!r}."
        )
    if (
        registration.schema_version
        not in profile.supported_route_registration_schema_versions
    ):
        supported = ", ".join(
            sorted(profile.supported_route_registration_schema_versions)
        )
        raise ModuleContractCompatibilityError(
            f"Module {profile.module_id!r} does not support route-registration "
            f"schema {registration.schema_version!r}; supported versions: "
            f"{supported}."
        )
    if registration.status not in profile.dispatchable_route_statuses:
        dispatchable = ", ".join(sorted(profile.dispatchable_route_statuses))
        raise RouteStatusNotDispatchableError(
            f"Module {profile.module_id!r} route "
            f"{registration.locator.route_id!r} has status "
            f"{registration.status!r}; dispatchable statuses: {dispatchable}."
        )
