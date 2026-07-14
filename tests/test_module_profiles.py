"""Tests for public module profiles, registries, and discovery."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Callable, cast

import pytest

from pds_core.module_profiles import (
    MODULE_PROFILE_ENTRY_POINT_GROUP,
    ModuleDiscoveryError,
    ModuleProfile,
    ModuleProfileError,
    ModuleRegistrationValidator,
    ModuleRegistry,
    ModuleRegistryError,
    UnsupportedModuleError,
    build_module_registry,
    discover_module_profiles,
    validate_module_profile,
)


def handler(*_args: object) -> object:
    return None


def validator(_registration: object) -> None:
    return None


def make_profile(
    module_id: str = "concord",
    *,
    route_handler: Callable[..., object] = handler,
    registration_validator: Callable[..., object] | None = None,
) -> ModuleProfile:
    return ModuleProfile(
        module_id=module_id,
        display_name=module_id.title(),
        supported_core_routing_contract_versions=frozenset({"1"}),
        supported_qr_schemas=frozenset({"PDS2"}),
        supported_route_registration_schema_versions=frozenset({"1"}),
        dispatchable_route_statuses=frozenset({"active"}),
        route_handler=route_handler,
        registration_validator=cast(
            ModuleRegistrationValidator | None, registration_validator
        ),
    )


class FakeEntryPoint:
    def __init__(
        self,
        name: str,
        value: str,
        loaded: object = None,
        load_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self._loaded = loaded
        self._load_error = load_error

    def load(self) -> object:
        if self._load_error is not None:
            raise self._load_error
        return self._loaded


def install_entry_points(
    monkeypatch: pytest.MonkeyPatch,
    entries: list[FakeEntryPoint],
) -> None:
    def entry_points(*, group: str) -> list[FakeEntryPoint]:
        assert group == MODULE_PROFILE_ENTRY_POINT_GROUP
        return entries

    monkeypatch.setattr(
        "pds_core.module_profiles.metadata.entry_points", entry_points
    )


def test_valid_profile_is_frozen_slotted_and_revalidates() -> None:
    profile = make_profile(registration_validator=validator)

    assert validate_module_profile(profile) is profile
    assert profile.module_id == "concord"
    assert profile.route_handler is handler
    assert profile.registration_validator is validator
    assert not hasattr(profile, "__dict__")
    with pytest.raises(FrozenInstanceError):
        profile.display_name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize("module_id", ["scoreform", "quillan", "concord"])
def test_initial_module_like_profiles_are_valid(module_id: str) -> None:
    assert make_profile(module_id).module_id == module_id


def test_profile_defensively_freezes_mutable_collections() -> None:
    core_versions = {"1"}
    qr_schemas = {"PDS2"}
    registration_versions = {"1"}
    statuses = {"active"}
    profile = ModuleProfile(
        "concord",
        "Concord",
        core_versions,  # type: ignore[arg-type]
        qr_schemas,  # type: ignore[arg-type]
        registration_versions,  # type: ignore[arg-type]
        statuses,  # type: ignore[arg-type]
        handler,
    )
    core_versions.add("2")
    qr_schemas.add("PDS3")
    registration_versions.add("2")
    statuses.add("retired")

    assert profile.supported_core_routing_contract_versions == frozenset({"1"})
    assert profile.supported_qr_schemas == frozenset({"PDS2"})
    assert profile.supported_route_registration_schema_versions == frozenset({"1"})
    assert profile.dispatchable_route_statuses == frozenset({"active"})


@pytest.mark.parametrize(
    "module_id", ["ScoreForm", "pds.scoreform", "scoreform/module", "../scoreform", ""]
)
def test_profile_rejects_invalid_module_id(module_id: str) -> None:
    with pytest.raises(ModuleProfileError, match="module_id"):
        make_profile(module_id)


@pytest.mark.parametrize(
    "display_name", ["", " Concord", "Concord ", "Con\ncord", "Con\x00cord", "Con\u2028cord", "Con\u2029cord"]
)
def test_profile_rejects_invalid_display_name(display_name: str) -> None:
    with pytest.raises(ModuleProfileError, match="display_name"):
        ModuleProfile(
            "concord",
            display_name,
            frozenset({"1"}),
            frozenset({"PDS2"}),
            frozenset({"1"}),
            frozenset({"active"}),
            handler,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "supported_core_routing_contract_versions",
        "supported_qr_schemas",
        "supported_route_registration_schema_versions",
        "dispatchable_route_statuses",
    ],
)
def test_profile_rejects_empty_compatibility_collection(field_name: str) -> None:
    values: dict[str, object] = {
        "module_id": "concord",
        "display_name": "Concord",
        "supported_core_routing_contract_versions": frozenset({"1"}),
        "supported_qr_schemas": frozenset({"PDS2"}),
        "supported_route_registration_schema_versions": frozenset({"1"}),
        "dispatchable_route_statuses": frozenset({"active"}),
        "route_handler": handler,
    }
    values[field_name] = frozenset()
    with pytest.raises(ModuleProfileError, match=field_name):
        ModuleProfile(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [frozenset({1}), frozenset({"bad.version"}), "PDS2"])
def test_profile_rejects_invalid_compatibility_values(value: object) -> None:
    with pytest.raises(ModuleProfileError):
        ModuleProfile(
            "concord",
            "Concord",
            value,  # type: ignore[arg-type]
            frozenset({"PDS2"}),
            frozenset({"1"}),
            frozenset({"active"}),
            handler,
        )


def test_profile_rejects_unsupported_status_and_non_callables() -> None:
    with pytest.raises(ModuleProfileError, match="unsupported"):
        ModuleProfile(
            "concord", "Concord", frozenset({"1"}), frozenset({"PDS2"}),
            frozenset({"1"}), frozenset({"unknown"}), handler,
        )
    with pytest.raises(ModuleProfileError, match="route_handler"):
        make_profile(route_handler=None)  # type: ignore[arg-type]
    with pytest.raises(ModuleProfileError, match="registration_validator"):
        make_profile(registration_validator=object())  # type: ignore[arg-type]
    with pytest.raises(ModuleProfileError, match="ModuleProfile"):
        validate_module_profile({})  # type: ignore[arg-type]


def test_registry_supports_exact_sorted_lookup_and_independent_instances() -> None:
    concord = make_profile("concord")
    scoreform = make_profile("scoreform")
    registry = ModuleRegistry((scoreform, concord))
    other = ModuleRegistry()

    assert registry.module_ids() == ("concord", "scoreform")
    assert registry.profiles() == (concord, scoreform)
    assert registry.get("concord") is concord
    assert registry.get("quillan") is None
    assert registry.require("scoreform") is scoreform
    assert other.module_ids() == ()
    with pytest.raises(UnsupportedModuleError, match="quillan"):
        registry.require("quillan")
    with pytest.raises(ModuleProfileError):
        registry.get("Concord")


def test_unsupported_module_diagnostic_identifies_empty_registry() -> None:
    registry = ModuleRegistry()

    with pytest.raises(UnsupportedModuleError) as raised:
        registry.require("concord")

    message = str(raised.value)
    assert "concord" in message
    assert "(none)" in message


def test_unsupported_module_diagnostic_lists_sorted_registered_ids() -> None:
    registry = ModuleRegistry(
        (make_profile("scoreform"), make_profile("concord"))
    )

    with pytest.raises(UnsupportedModuleError) as raised:
        registry.require("quillan")

    message = str(raised.value)
    assert "quillan" in message
    assert "concord, scoreform" in message


def test_registry_rejects_duplicates_and_preserves_original() -> None:
    original = make_profile()
    registry = ModuleRegistry((original,))
    with pytest.raises(ModuleRegistryError, match="already registered"):
        registry.register(original)
    with pytest.raises(ModuleRegistryError):
        registry.register(make_profile())
    assert registry.require("concord") is original
    assert not hasattr(registry, "replace")
    assert not hasattr(registry, "unregister")


def test_discovery_empty_and_valid_results_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concord = make_profile("concord")
    quillan = make_profile("quillan")
    install_entry_points(
        monkeypatch,
        [
            FakeEntryPoint("quillan", "z.provider", lambda: quillan),
            FakeEntryPoint("concord", "a.provider", lambda: concord),
        ],
    )
    assert discover_module_profiles() == (concord, quillan)
    install_entry_points(monkeypatch, [])
    assert discover_module_profiles() == ()


def test_discovery_wraps_entry_point_enumeration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_entry_points(*, group: str) -> object:
        assert group == MODULE_PROFILE_ENTRY_POINT_GROUP
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(
        "pds_core.module_profiles.metadata.entry_points", fail_entry_points
    )

    with pytest.raises(ModuleDiscoveryError) as raised:
        discover_module_profiles()

    assert isinstance(raised.value.__cause__, RuntimeError)


@pytest.mark.parametrize(
    "entry",
    [
        FakeEntryPoint("concord", "provider", object()),
        FakeEntryPoint("concord", "provider", lambda required: required),
        FakeEntryPoint("concord", "provider", lambda: {}),
        FakeEntryPoint("concord", "provider", lambda: make_profile("quillan")),
        FakeEntryPoint("concord", "provider", load_error=ImportError("broken")),
    ],
)
def test_discovery_wraps_broken_provider_contracts(
    monkeypatch: pytest.MonkeyPatch,
    entry: FakeEntryPoint,
) -> None:
    install_entry_points(monkeypatch, [entry])
    with pytest.raises(ModuleDiscoveryError) as raised:
        discover_module_profiles()
    assert raised.value.__cause__ is not None


def test_discovery_wraps_provider_exception_and_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> ModuleProfile:
        raise ValueError("provider failure")

    install_entry_points(monkeypatch, [FakeEntryPoint("concord", "x", fail)])
    with pytest.raises(ModuleDiscoveryError) as raised:
        discover_module_profiles()
    assert isinstance(raised.value.__cause__, ValueError)

    install_entry_points(
        monkeypatch,
        [
            FakeEntryPoint("concord", "a", lambda: make_profile()),
            FakeEntryPoint("concord", "b", lambda: make_profile()),
        ],
    )
    with pytest.raises(ModuleDiscoveryError) as duplicate:
        discover_module_profiles()
    assert isinstance(duplicate.value.__cause__, ModuleRegistryError)


def test_registry_builder_discovery_control_conflicts_and_no_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = make_profile("concord")
    install_entry_points(
        monkeypatch, [FakeEntryPoint("concord", "provider", lambda: installed)]
    )

    isolated = build_module_registry(discover_installed=False)
    discovered = build_module_registry()
    assert isolated.module_ids() == ()
    assert discovered.profiles() == (installed,)
    isolated.register(make_profile("quillan"))
    assert discovered.module_ids() == ("concord",)
    with pytest.raises(ModuleRegistryError):
        build_module_registry(
            explicit_profiles=(make_profile("concord"),),
            discover_installed=True,
        )
