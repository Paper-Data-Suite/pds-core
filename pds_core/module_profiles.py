"""Public module-profile contracts, registries, and installed discovery."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata
from typing import Final, Protocol, cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.routing_models import (
    ROUTE_REGISTRATION_STATUSES,
    RouteRegistration,
    RouteResolution,
)
from pds_core.scan_retention import RetainedSourceScan


CORE_ROUTING_CONTRACT_VERSION: Final[str] = "1"
MODULE_PROFILE_ENTRY_POINT_GROUP: Final[str] = "paper_data_suite.modules"


class ModuleRegistrationValidator(Protocol):
    """Validate module-owned structural registration requirements."""

    def __call__(self, registration: RouteRegistration, /) -> None: ...


class ModuleRouteHandler(Protocol):
    """Process one resolved retained-source page for its owning module."""

    def __call__(
        self,
        resolution: RouteResolution,
        retained_source: RetainedSourceScan,
        source_page_number: int,
        /,
    ) -> object: ...


class ModuleProfileError(ValueError):
    """Raised when a module profile is structurally invalid."""


class ModuleRegistryError(RuntimeError):
    """Raised when module registry construction or mutation fails."""


class UnsupportedModuleError(LookupError):
    """Raised when no registered profile owns a requested module ID."""


class ModuleDiscoveryError(RuntimeError):
    """Raised when installed module-profile discovery fails."""


@dataclass(frozen=True, slots=True)
class ModuleProfile:
    """One module's runtime compatibility and dispatch integration."""

    module_id: str
    display_name: str
    supported_core_routing_contract_versions: frozenset[str]
    supported_qr_schemas: frozenset[str]
    supported_route_registration_schema_versions: frozenset[str]
    dispatchable_route_statuses: frozenset[str]
    route_handler: ModuleRouteHandler
    registration_validator: ModuleRegistrationValidator | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "supported_core_routing_contract_versions",
            _freeze_identifiers(
                self.supported_core_routing_contract_versions,
                "supported_core_routing_contract_versions",
            ),
        )
        object.__setattr__(
            self,
            "supported_qr_schemas",
            _freeze_identifiers(
                self.supported_qr_schemas,
                "supported_qr_schemas",
            ),
        )
        object.__setattr__(
            self,
            "supported_route_registration_schema_versions",
            _freeze_identifiers(
                self.supported_route_registration_schema_versions,
                "supported_route_registration_schema_versions",
            ),
        )
        object.__setattr__(
            self,
            "dispatchable_route_statuses",
            _freeze_dispatch_statuses(self.dispatchable_route_statuses),
        )
        _validate_profile_fields(self)


def validate_module_profile(profile: ModuleProfile) -> ModuleProfile:
    """Revalidate and return an actual module profile."""
    if not isinstance(profile, ModuleProfile):
        raise ModuleProfileError("profile must be a ModuleProfile.")
    _validate_profile_fields(profile)
    return profile


class ModuleRegistry:
    """An application-owned, exact module-profile registry."""

    def __init__(self, profiles: Iterable[ModuleProfile] = ()) -> None:
        self._profiles: dict[str, ModuleProfile] = {}
        try:
            for profile in profiles:
                self.register(profile)
        except TypeError as error:
            raise ModuleRegistryError("profiles must be iterable.") from error

    def register(self, profile: ModuleProfile) -> None:
        """Register a profile without replacement or preference rules."""
        validated = validate_module_profile(profile)
        if validated.module_id in self._profiles:
            raise ModuleRegistryError(
                f"A module profile is already registered for "
                f"{validated.module_id!r}."
            )
        self._profiles[validated.module_id] = validated

    def get(self, module_id: str) -> ModuleProfile | None:
        """Return the exact registered profile, if present."""
        validated = _validate_module_id(module_id)
        return self._profiles.get(validated)

    def require(self, module_id: str) -> ModuleProfile:
        """Return the exact registered profile or reject the module."""
        validated = _validate_module_id(module_id)
        profile = self._profiles.get(validated)
        if profile is None:
            registered = ", ".join(self.module_ids()) or "(none)"
            raise UnsupportedModuleError(
                f"No module profile is registered for module_id {validated!r}; "
                f"registered module IDs: {registered}."
            )
        return profile

    def module_ids(self) -> tuple[str, ...]:
        """Return registered module IDs in deterministic order."""
        return tuple(sorted(self._profiles))

    def profiles(self) -> tuple[ModuleProfile, ...]:
        """Return registered profiles in deterministic module-ID order."""
        return tuple(self._profiles[module_id] for module_id in self.module_ids())


def discover_module_profiles() -> tuple[ModuleProfile, ...]:
    """Load validated module profiles from the declared entry-point group."""
    try:
        entry_points = metadata.entry_points(
            group=MODULE_PROFILE_ENTRY_POINT_GROUP
        )
        ordered_entry_points = sorted(
            entry_points,
            key=lambda entry_point: (
                entry_point.name,
                getattr(entry_point, "value", ""),
            ),
        )
    except Exception as error:
        raise ModuleDiscoveryError(
            "Could not enumerate installed module-profile entry points."
        ) from error

    discovered: dict[str, ModuleProfile] = {}
    for entry_point in ordered_entry_points:
        name = entry_point.name
        try:
            _validate_module_id(name)
            provider = entry_point.load()
            if not callable(provider):
                raise ModuleProfileError(
                    "the loaded entry-point object must be callable"
                )
            profile = provider()
            validated = validate_module_profile(profile)
            if name != validated.module_id:
                raise ModuleProfileError(
                    f"entry-point name {name!r} does not match profile "
                    f"module_id {validated.module_id!r}"
                )
            if validated.module_id in discovered:
                raise ModuleRegistryError(
                    f"Duplicate discovered module profile for "
                    f"{validated.module_id!r}."
                )
        except Exception as error:
            raise ModuleDiscoveryError(
                f"Module-profile discovery failed for entry point {name!r}."
            ) from error
        discovered[validated.module_id] = validated

    return tuple(discovered[module_id] for module_id in sorted(discovered))


def build_module_registry(
    *,
    explicit_profiles: Iterable[ModuleProfile] = (),
    discover_installed: bool = True,
) -> ModuleRegistry:
    """Build one independent registry from explicit and installed profiles."""
    registry = ModuleRegistry(explicit_profiles)
    if discover_installed:
        for profile in discover_module_profiles():
            registry.register(profile)
    return registry


def _validate_profile_fields(profile: ModuleProfile) -> None:
    _validate_module_id(profile.module_id)
    _validate_display_name(profile.display_name)
    _validate_frozen_identifiers(
        profile.supported_core_routing_contract_versions,
        "supported_core_routing_contract_versions",
    )
    _validate_frozen_identifiers(
        profile.supported_qr_schemas,
        "supported_qr_schemas",
    )
    _validate_frozen_identifiers(
        profile.supported_route_registration_schema_versions,
        "supported_route_registration_schema_versions",
    )
    _validate_frozen_dispatch_statuses(profile.dispatchable_route_statuses)
    if not callable(profile.route_handler):
        raise ModuleProfileError("route_handler must be callable.")
    if (
        profile.registration_validator is not None
        and not callable(profile.registration_validator)
    ):
        raise ModuleProfileError(
            "registration_validator must be callable or None."
        )


def _validate_module_id(value: object) -> str:
    identifier = _validate_safe_identifier(value, "module_id")
    if identifier != identifier.lower():
        raise ModuleProfileError("module_id must be lowercase.")
    return identifier


def _validate_safe_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ModuleProfileError(f"{field_name} must be a string.")
    try:
        return validate_identifier(value, field_name)
    except IdentifierValidationError as error:
        raise ModuleProfileError(str(error)) from error


def _validate_display_name(value: object) -> str:
    if not isinstance(value, str):
        raise ModuleProfileError("display_name must be a string.")
    if value == "":
        raise ModuleProfileError("display_name must not be empty.")
    if value != value.strip():
        raise ModuleProfileError(
            "display_name must not contain leading or trailing whitespace."
        )
    if any(
        unicodedata.category(character) in {"Cc", "Zl", "Zp"}
        for character in value
    ):
        raise ModuleProfileError(
            "display_name must be single-line and free of control characters."
        )
    return value


def _freeze_identifiers(value: object, field_name: str) -> frozenset[str]:
    if isinstance(value, (str, bytes)):
        raise ModuleProfileError(f"{field_name} must be a collection.")
    try:
        frozen = frozenset(value)  # type: ignore[call-overload]
    except TypeError as error:
        raise ModuleProfileError(f"{field_name} must be a collection.") from error
    _validate_frozen_identifiers(frozen, field_name)
    return cast(frozenset[str], frozen)


def _validate_frozen_identifiers(value: object, field_name: str) -> None:
    if not isinstance(value, frozenset):
        raise ModuleProfileError(f"{field_name} must be a frozenset.")
    if not value:
        raise ModuleProfileError(f"{field_name} must not be empty.")
    for item in value:
        _validate_safe_identifier(item, f"{field_name} member")


def _freeze_dispatch_statuses(value: object) -> frozenset[str]:
    frozen = _freeze_identifiers(value, "dispatchable_route_statuses")
    _validate_frozen_dispatch_statuses(frozen)
    return frozen


def _validate_frozen_dispatch_statuses(value: object) -> None:
    _validate_frozen_identifiers(value, "dispatchable_route_statuses")
    assert isinstance(value, frozenset)
    unsupported = value - ROUTE_REGISTRATION_STATUSES
    if unsupported:
        raise ModuleProfileError(
            "dispatchable_route_statuses contains unsupported status(es): "
            f"{', '.join(sorted(unsupported))}."
        )
