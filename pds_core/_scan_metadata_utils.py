"""Private strict-JSON and value-isolation helpers for scan metadata."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, TypeAlias

from pds_core.routing_models import JsonValue

FrozenJsonValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | tuple["FrozenJsonValue", ...]
    | Mapping[str, "FrozenJsonValue"]
)
FrozenJsonMapping: TypeAlias = Mapping[str, FrozenJsonValue]


class JsonValueIsolationError(ValueError):
    """Raised when a value is not an isolated JSON-native mapping."""


class DuplicateJsonKeyError(ValueError):
    """Raised when strict JSON loading encounters a duplicate object key."""


class InvalidJsonConstantError(ValueError):
    """Raised when strict JSON loading encounters a non-standard number."""


def freeze_json_mapping(value: object, field_name: str) -> FrozenJsonMapping:
    """Validate and deeply freeze a JSON-native mapping."""
    if not isinstance(value, Mapping):
        raise JsonValueIsolationError(f"{field_name} must be a mapping.")
    return _freeze_mapping(value, field_name, set())


def thaw_json_mapping(value: FrozenJsonMapping) -> dict[str, JsonValue]:
    """Return a fresh JSON-native copy of a frozen mapping."""
    return {
        key: _thaw_value(item, f"module_details.{key}")
        for key, item in value.items()
    }


def load_strict_json(path: Path) -> object:
    """Load UTF-8 JSON while rejecting duplicates and non-standard numbers."""
    with path.open("r", encoding="utf-8") as source:
        return json.load(
            source,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_invalid_constant,
        )


def _freeze_mapping(
    value: Mapping[object, object], path: str, active_ids: set[int]
) -> FrozenJsonMapping:
    container_id = id(value)
    if container_id in active_ids:
        raise JsonValueIsolationError(f"{path} must not contain circular references.")
    active_ids.add(container_id)
    try:
        frozen: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise JsonValueIsolationError(f"{path} keys must be strings.")
            frozen[key] = _freeze_value(item, f"{path}.{key}", active_ids)
        return MappingProxyType(frozen)
    finally:
        active_ids.remove(container_id)


def _freeze_value(
    value: object, path: str, active_ids: set[int]
) -> FrozenJsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JsonValueIsolationError(f"{path} must contain only finite numbers.")
        return value
    if isinstance(value, list):
        container_id = id(value)
        if container_id in active_ids:
            raise JsonValueIsolationError(
                f"{path} must not contain circular references."
            )
        active_ids.add(container_id)
        try:
            return tuple(
                _freeze_value(item, f"{path}[{index}]", active_ids)
                for index, item in enumerate(value)
            )
        finally:
            active_ids.remove(container_id)
    if isinstance(value, dict):
        return _freeze_mapping(value, path, active_ids)
    raise JsonValueIsolationError(
        f"{path} must contain only JSON-compatible values."
    )


def _thaw_value(value: FrozenJsonValue, path: str) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JsonValueIsolationError(f"{path} must contain only finite numbers.")
        return value
    if isinstance(value, tuple):
        return [
            _thaw_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise JsonValueIsolationError(f"{path} keys must be strings.")
            result[key] = _thaw_value(item, f"{path}.{key}")
        return result
    raise JsonValueIsolationError(f"{path} must contain only JSON-compatible values.")


def _reject_duplicate_keys(
    pairs: Iterable[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_invalid_constant(value: str) -> NoReturn:
    raise InvalidJsonConstantError(f"invalid JSON numeric constant: {value}")
