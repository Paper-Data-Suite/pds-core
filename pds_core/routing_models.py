"""Shared identity and registration models for PDS2 page routing."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, TypeAlias, cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier

PDS2_SCHEMA: Final[Literal["PDS2"]] = "PDS2"
ROUTE_REGISTRATION_SCHEMA_VERSION: Final[str] = "1"
ROUTE_REGISTRATION_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "active",
        "inactive",
        "retired",
        "superseded",
        "cancelled",
        "invalidated",
    }
)

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
_FrozenJsonValue: TypeAlias = (
    JsonScalar
    | tuple["_FrozenJsonValue", ...]
    | Mapping[str, "_FrozenJsonValue"]
)
_FrozenJsonMapping: TypeAlias = Mapping[str, _FrozenJsonValue]
_EMPTY_MODULE_DETAILS: Final[Mapping[str, JsonValue]] = MappingProxyType({})

_MODULE_WORK_REF_KEYS: Final[frozenset[str]] = frozenset(
    {"module_id", "class_id", "work_id"}
)
_ROUTE_LOCATOR_KEYS: Final[frozenset[str]] = frozenset(
    {"schema", "module_id", "class_id", "work_id", "route_id"}
)
_MODULE_RECORD_REF_KEYS: Final[frozenset[str]] = frozenset(
    {"module_id", "record_kind", "record_id", "contract_version"}
)
_ROUTE_REGISTRATION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "locator",
        "target",
        "created_at",
        "status",
        "human_fallback",
        "module_details",
    }
)


class RoutingModelError(ValueError):
    """Raised when shared PDS2 routing model data is invalid."""


@dataclass(frozen=True, slots=True)
class ModuleWorkRef:
    """One module-owned top-level work context within one Core class."""

    module_id: str
    class_id: str
    work_id: str

    def __post_init__(self) -> None:
        _validate_lowercase_identifier(self.module_id, "module_id")
        _validate_identifier(self.class_id, "class_id")
        _validate_identifier(self.work_id, "work_id")


@dataclass(frozen=True, slots=True)
class RouteLocator:
    """The normalized identity carried by one PDS2 physical page route."""

    schema: Literal["PDS2"]
    work: ModuleWorkRef
    route_id: str

    def __post_init__(self) -> None:
        if self.schema != PDS2_SCHEMA:
            raise RoutingModelError(f'schema must be "{PDS2_SCHEMA}".')
        if not isinstance(self.work, ModuleWorkRef):
            raise RoutingModelError("work must be a ModuleWorkRef.")
        validate_module_work_ref(self.work)
        _validate_identifier(self.route_id, "route_id")

    @property
    def module_id(self) -> str:
        """Return the owning module identifier."""
        return self.work.module_id

    @property
    def class_id(self) -> str:
        """Return the Core class identifier."""
        return self.work.class_id

    @property
    def work_id(self) -> str:
        """Return the module-owned work identifier."""
        return self.work.work_id


@dataclass(frozen=True, slots=True)
class ModuleRecordRef:
    """A typed reference to a module-owned record."""

    module_id: str
    record_kind: str
    record_id: str
    contract_version: str | None = None

    def __post_init__(self) -> None:
        _validate_lowercase_identifier(self.module_id, "module_id")
        _validate_lowercase_identifier(self.record_kind, "record_kind")
        _validate_identifier(self.record_id, "record_id")
        if self.contract_version is not None:
            _validate_identifier(self.contract_version, "contract_version")


@dataclass(frozen=True, slots=True, init=False)
class RouteRegistration:
    """A persisted relationship from one locator to one module-owned target."""

    schema_version: str
    locator: RouteLocator
    target: ModuleRecordRef
    created_at: str
    status: str
    human_fallback: str
    _module_details: _FrozenJsonMapping = field(
        init=False, repr=False, compare=True
    )

    def __init__(
        self,
        schema_version: str,
        locator: RouteLocator,
        target: ModuleRecordRef,
        created_at: str,
        status: str,
        human_fallback: str,
        module_details: Mapping[str, JsonValue] = _EMPTY_MODULE_DETAILS,
    ) -> None:
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "locator", locator)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "human_fallback", human_fallback)
        _validate_route_registration_fields(self)
        object.__setattr__(
            self, "_module_details", _freeze_module_details(module_details)
        )

    @property
    def module_details(self) -> dict[str, JsonValue]:
        """Return an isolated JSON-native copy of module routing details."""
        return _thaw_module_details(self._module_details)


@dataclass(frozen=True, slots=True)
class RouteResolution:
    """A successful runtime resolution of a locator and registration."""

    locator: RouteLocator
    registration: RouteRegistration
    class_root: Path
    module_root: Path
    work_root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.locator, RouteLocator):
            raise RoutingModelError("locator must be a RouteLocator.")
        validate_route_locator(self.locator)
        if not isinstance(self.registration, RouteRegistration):
            raise RoutingModelError("registration must be a RouteRegistration.")
        validate_route_registration(self.registration)
        if self.locator != self.registration.locator:
            raise RoutingModelError(
                "locator must exactly match registration.locator."
            )
        for field_name in ("class_root", "module_root", "work_root"):
            if not isinstance(getattr(self, field_name), Path):
                raise RoutingModelError(f"{field_name} must be a Path.")


def is_route_registration_status(value: object) -> bool:
    """Return whether a value is a shared route-registration status."""
    return isinstance(value, str) and value in ROUTE_REGISTRATION_STATUSES


def validate_module_work_ref(
    value: ModuleWorkRef | Mapping[str, object],
) -> ModuleWorkRef:
    """Validate and return a module work reference."""
    if isinstance(value, ModuleWorkRef):
        _validate_lowercase_identifier(value.module_id, "module_id")
        _validate_identifier(value.class_id, "class_id")
        _validate_identifier(value.work_id, "work_id")
        return value
    return module_work_ref_from_dict(value)


def module_work_ref_to_dict(value: ModuleWorkRef) -> dict[str, object]:
    """Convert a validated module work reference to its exact JSON shape."""
    validated = validate_module_work_ref(value)
    return {
        "module_id": validated.module_id,
        "class_id": validated.class_id,
        "work_id": validated.work_id,
    }


def module_work_ref_from_dict(data: object) -> ModuleWorkRef:
    """Build a module work reference from an exact schema mapping."""
    mapping = _require_exact_mapping(
        data, _MODULE_WORK_REF_KEYS, "module work reference"
    )
    return ModuleWorkRef(
        module_id=_require_string(mapping["module_id"], "module_id"),
        class_id=_require_string(mapping["class_id"], "class_id"),
        work_id=_require_string(mapping["work_id"], "work_id"),
    )


def validate_route_locator(
    value: RouteLocator | Mapping[str, object],
) -> RouteLocator:
    """Validate and return a route locator."""
    if isinstance(value, RouteLocator):
        if value.schema != PDS2_SCHEMA:
            raise RoutingModelError(f'schema must be "{PDS2_SCHEMA}".')
        if not isinstance(value.work, ModuleWorkRef):
            raise RoutingModelError("work must be a ModuleWorkRef.")
        validate_module_work_ref(value.work)
        _validate_identifier(value.route_id, "route_id")
        return value
    return route_locator_from_dict(value)


def route_locator_to_dict(value: RouteLocator) -> dict[str, object]:
    """Convert a validated locator to the exact flat PDS2 field shape."""
    validated = validate_route_locator(value)
    return {
        "schema": validated.schema,
        "module_id": validated.module_id,
        "class_id": validated.class_id,
        "work_id": validated.work_id,
        "route_id": validated.route_id,
    }


def route_locator_from_dict(data: object) -> RouteLocator:
    """Build a route locator from an exact flat schema mapping."""
    mapping = _require_exact_mapping(data, _ROUTE_LOCATOR_KEYS, "route locator")
    schema = _require_string(mapping["schema"], "schema")
    if schema != PDS2_SCHEMA:
        raise RoutingModelError(f'schema must be "{PDS2_SCHEMA}".')
    work = ModuleWorkRef(
        module_id=_require_string(mapping["module_id"], "module_id"),
        class_id=_require_string(mapping["class_id"], "class_id"),
        work_id=_require_string(mapping["work_id"], "work_id"),
    )
    return RouteLocator(
        schema=PDS2_SCHEMA,
        work=work,
        route_id=_require_string(mapping["route_id"], "route_id"),
    )


def validate_module_record_ref(
    value: ModuleRecordRef | Mapping[str, object],
) -> ModuleRecordRef:
    """Validate and return a module-owned record reference."""
    if isinstance(value, ModuleRecordRef):
        _validate_lowercase_identifier(value.module_id, "module_id")
        _validate_lowercase_identifier(value.record_kind, "record_kind")
        _validate_identifier(value.record_id, "record_id")
        if value.contract_version is not None:
            _validate_identifier(value.contract_version, "contract_version")
        return value
    return module_record_ref_from_dict(value)


def module_record_ref_to_dict(value: ModuleRecordRef) -> dict[str, object]:
    """Convert a validated module record reference to its exact JSON shape."""
    validated = validate_module_record_ref(value)
    return {
        "module_id": validated.module_id,
        "record_kind": validated.record_kind,
        "record_id": validated.record_id,
        "contract_version": validated.contract_version,
    }


def module_record_ref_from_dict(data: object) -> ModuleRecordRef:
    """Build a module record reference from an exact schema mapping."""
    mapping = _require_exact_mapping(
        data, _MODULE_RECORD_REF_KEYS, "module record reference"
    )
    contract_version = mapping["contract_version"]
    if contract_version is not None:
        contract_version = _require_string(contract_version, "contract_version")
    return ModuleRecordRef(
        module_id=_require_string(mapping["module_id"], "module_id"),
        record_kind=_require_string(mapping["record_kind"], "record_kind"),
        record_id=_require_string(mapping["record_id"], "record_id"),
        contract_version=contract_version,
    )


def validate_route_registration(
    value: RouteRegistration | Mapping[str, object],
) -> RouteRegistration:
    """Validate and return a route registration."""
    if isinstance(value, RouteRegistration):
        _validate_route_registration_fields(value)
        _thaw_module_details(value._module_details)
        return value
    return route_registration_from_dict(value)


def route_registration_to_dict(value: RouteRegistration) -> dict[str, object]:
    """Convert a validated route registration to its exact JSON shape."""
    validated = validate_route_registration(value)
    return {
        "schema_version": validated.schema_version,
        "locator": route_locator_to_dict(validated.locator),
        "target": module_record_ref_to_dict(validated.target),
        "created_at": validated.created_at,
        "status": validated.status,
        "human_fallback": validated.human_fallback,
        "module_details": validated.module_details,
    }


def route_registration_from_dict(data: object) -> RouteRegistration:
    """Build a route registration from an exact nested schema mapping."""
    mapping = _require_exact_mapping(
        data, _ROUTE_REGISTRATION_KEYS, "route registration"
    )
    module_details = mapping["module_details"]
    if not isinstance(module_details, Mapping):
        raise RoutingModelError("module_details must be a mapping.")
    return RouteRegistration(
        schema_version=_require_string(
            mapping["schema_version"], "schema_version"
        ),
        locator=route_locator_from_dict(mapping["locator"]),
        target=module_record_ref_from_dict(mapping["target"]),
        created_at=_require_string(mapping["created_at"], "created_at"),
        status=_require_string(mapping["status"], "status"),
        human_fallback=_require_string(
            mapping["human_fallback"], "human_fallback"
        ),
        module_details=cast(Mapping[str, JsonValue], module_details),
    )


def _validate_route_registration_fields(value: RouteRegistration) -> None:
    if value.schema_version != ROUTE_REGISTRATION_SCHEMA_VERSION:
        raise RoutingModelError(
            f'schema_version must be "{ROUTE_REGISTRATION_SCHEMA_VERSION}".'
        )
    if not isinstance(value.locator, RouteLocator):
        raise RoutingModelError("locator must be a RouteLocator.")
    validate_route_locator(value.locator)
    if not isinstance(value.target, ModuleRecordRef):
        raise RoutingModelError("target must be a ModuleRecordRef.")
    validate_module_record_ref(value.target)
    if value.target.module_id != value.locator.module_id:
        raise RoutingModelError(
            "target.module_id must match locator.module_id."
        )
    _validate_iso_timestamp(value.created_at, "created_at")
    if not is_route_registration_status(value.status):
        raise RoutingModelError(
            "status must be a shared route-registration status."
        )
    _validate_human_fallback(value.human_fallback)


def _validate_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RoutingModelError(f"{field_name} must be a string.")
    try:
        return validate_identifier(value, field_name)
    except IdentifierValidationError as error:
        raise RoutingModelError(str(error)) from error


def _validate_lowercase_identifier(value: object, field_name: str) -> str:
    identifier = _validate_identifier(value, field_name)
    if identifier != identifier.lower():
        raise RoutingModelError(f"{field_name} must be lowercase.")
    return identifier


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RoutingModelError(f"{field_name} must be a string.")
    return value


def _require_exact_mapping(
    data: object, expected_keys: frozenset[str], model_name: str
) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise RoutingModelError(f"{model_name} must be a mapping.")
    raw_keys = list(data.keys())
    if any(not isinstance(key, str) for key in raw_keys):
        raise RoutingModelError(f"{model_name} keys must be strings.")
    keys = frozenset(cast(str, key) for key in raw_keys)
    missing = sorted(expected_keys - keys)
    if missing:
        raise RoutingModelError(
            f"{model_name} is missing required key(s): {', '.join(missing)}."
        )
    unknown = sorted(keys - expected_keys)
    if unknown:
        raise RoutingModelError(
            f"{model_name} contains unknown key(s): {', '.join(unknown)}."
        )
    return cast(Mapping[str, object], data)


def _validate_iso_timestamp(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RoutingModelError(
            f"{field_name} must be an ISO 8601 datetime string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RoutingModelError(
            f"{field_name} must be a valid ISO 8601 datetime string."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RoutingModelError(f"{field_name} must include a timezone offset.")
    return value


def _validate_human_fallback(value: object) -> str:
    if not isinstance(value, str):
        raise RoutingModelError("human_fallback must be a string.")
    if value == "":
        raise RoutingModelError("human_fallback must not be empty.")
    if value != value.strip():
        raise RoutingModelError(
            "human_fallback must not contain leading or trailing whitespace."
        )
    if any(
        unicodedata.category(character) in {"Cc", "Zl", "Zp"}
        for character in value
    ):
        raise RoutingModelError(
            "human_fallback must be single-line and free of control characters."
        )
    return value


def _freeze_module_details(value: object) -> _FrozenJsonMapping:
    if not isinstance(value, Mapping):
        raise RoutingModelError("module_details must be a mapping.")
    return _freeze_json_mapping(value, "module_details", set())


def _freeze_json_mapping(
    value: Mapping[object, object], path: str, active_ids: set[int]
) -> _FrozenJsonMapping:
    container_id = id(value)
    if container_id in active_ids:
        raise RoutingModelError(f"{path} must not contain circular references.")
    active_ids.add(container_id)
    try:
        frozen: dict[str, _FrozenJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RoutingModelError(f"{path} keys must be strings.")
            frozen[key] = _freeze_json_value(item, f"{path}.{key}", active_ids)
        return MappingProxyType(frozen)
    finally:
        active_ids.remove(container_id)


def _freeze_json_value(
    value: object, path: str, active_ids: set[int]
) -> _FrozenJsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RoutingModelError(f"{path} must contain only finite numbers.")
        return value
    if isinstance(value, list):
        container_id = id(value)
        if container_id in active_ids:
            raise RoutingModelError(
                f"{path} must not contain circular references."
            )
        active_ids.add(container_id)
        try:
            return tuple(
                _freeze_json_value(item, f"{path}[{index}]", active_ids)
                for index, item in enumerate(value)
            )
        finally:
            active_ids.remove(container_id)
    if isinstance(value, dict):
        return _freeze_json_mapping(value, path, active_ids)
    raise RoutingModelError(
        f"{path} must contain only JSON-compatible values."
    )


def _thaw_module_details(value: _FrozenJsonMapping) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise RoutingModelError("module_details keys must be strings.")
        result[key] = _thaw_json_value(item, f"module_details.{key}")
    return result


def _thaw_json_value(value: _FrozenJsonValue, path: str) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RoutingModelError(f"{path} must contain only finite numbers.")
        return value
    if isinstance(value, tuple):
        return [
            _thaw_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RoutingModelError(f"{path} keys must be strings.")
            result[key] = _thaw_json_value(item, f"{path}.{key}")
        return result
    raise RoutingModelError(f"{path} must contain only JSON-compatible values.")
