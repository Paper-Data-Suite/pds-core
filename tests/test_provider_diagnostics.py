"""Tests for failure-isolating Core provider diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Callable, cast

import pytest

from pds_core.module_profiles import (
    MODULE_PROFILE_ENTRY_POINT_GROUP,
    ModuleDiscoveryError,
    ModuleProfile,
    discover_module_profiles,
)
from pds_core.provider_diagnostics import (
    ProviderDiagnosticRequestError,
    ProviderEnumerationError,
    ProviderKind,
    diagnose_core_providers,
    inspect_core_provider_entry_points,
)
from pds_core.publication_compatibility import (
    PUBLICATION_PRODUCER_ENTRY_POINT_GROUP,
    PublicationContractSupport,
    PublicationProducerDiscoveryError,
    PublicationProducerProfile,
    discover_publication_producer_profiles,
)


def _route_handler(*_args: object) -> object:
    return None


def _module_profile(
    module_id: str = "concord",
    *,
    core_versions: frozenset[str] = frozenset({"1"}),
) -> ModuleProfile:
    return ModuleProfile(
        module_id=module_id,
        display_name=module_id.title(),
        supported_core_routing_contract_versions=core_versions,
        supported_qr_schemas=frozenset({"PDS2"}),
        supported_route_registration_schema_versions=frozenset({"1"}),
        dispatchable_route_statuses=frozenset({"active"}),
        route_handler=_route_handler,
    )


def _publication_profile(
    module_id: str = "concord",
    *,
    schema_versions: frozenset[str] = frozenset({"1"}),
) -> PublicationProducerProfile:
    return PublicationProducerProfile(
        module_id=module_id,
        display_name=module_id.title(),
        supported_core_publication_schema_versions=schema_versions,
        supported_academic_work_contract_versions=frozenset(),
        publication_contracts=(
            PublicationContractSupport(
                publication_kind="intervention_record_set",
                manifest_contract_versions=frozenset({"intervention_v1"}),
                supported_capabilities=frozenset({"intervention_status"}),
            ),
        ),
    )


class FakeEntryPoint:
    def __init__(
        self,
        name: object,
        value: object,
        *,
        loaded: object = None,
        load_error: Exception | None = None,
        distribution_name: str | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self.dist = (
            None
            if distribution_name is None
            else SimpleNamespace(name=distribution_name)
        )
        self._loaded = loaded
        self._load_error = load_error
        self.load_count = 0

    def load(self) -> object:
        self.load_count += 1
        if self._load_error is not None:
            raise self._load_error
        return self._loaded


class _SelectableEntryPoints(tuple[FakeEntryPoint, ...]):
    _group_map: dict[str, tuple[FakeEntryPoint, ...]]

    def __new__(
        cls,
        points: tuple[FakeEntryPoint, ...],
        group_map: dict[str, tuple[FakeEntryPoint, ...]],
    ) -> "_SelectableEntryPoints":
        value = super().__new__(cls, points)
        value._group_map = group_map
        return value

    def select(self, *, group: str) -> "_SelectableEntryPoints":
        points = self._group_map.get(group, ())
        return _SelectableEntryPoints(points, self._group_map)


def _install_entry_points(
    monkeypatch: pytest.MonkeyPatch,
    *,
    routing: tuple[FakeEntryPoint, ...] = (),
    publication: tuple[FakeEntryPoint, ...] = (),
    fail_group: str | None = None,
) -> None:
    group_map = {
        MODULE_PROFILE_ENTRY_POINT_GROUP: routing,
        PUBLICATION_PRODUCER_ENTRY_POINT_GROUP: publication,
    }

    def entry_points(*, group: str | None = None) -> object:
        if group is not None:
            if group == fail_group:
                raise RuntimeError("metadata secret must not leak")
            return group_map[group]
        combined = routing + publication
        return _SelectableEntryPoints(combined, group_map)

    monkeypatch.setattr(
        "pds_core.provider_diagnostics.metadata.entry_points",
        entry_points,
    )


def test_metadata_inspection_is_deterministic_and_does_not_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zeta = FakeEntryPoint(
        "zeta",
        "zeta.integration:get_profile",
        loaded=lambda: _module_profile("zeta"),
        distribution_name="zeta-dist",
    )
    concord = FakeEntryPoint(
        "concord",
        "concord.integration:get_profile",
        loaded=lambda: _module_profile("concord"),
        distribution_name="concord-dist",
    )
    producer = FakeEntryPoint(
        "scoreform",
        "scoreform.publication:get_profile",
        loaded=lambda: _publication_profile("scoreform"),
        distribution_name="scoreform-dist",
    )
    _install_entry_points(
        monkeypatch,
        routing=(zeta, concord),
        publication=(producer,),
    )

    rows = inspect_core_provider_entry_points()

    assert [
        (row.provider_kind, row.entry_point_name)
        for row in rows
    ] == [
        ("routing_module", "concord"),
        ("routing_module", "zeta"),
        ("publication_producer", "scoreform"),
    ]
    assert rows[0].entry_point_target == "concord.integration:get_profile"
    assert rows[0].distribution_name == "concord-dist"
    assert zeta.load_count == 0
    assert concord.load_count == 0
    assert producer.load_count == 0


def test_metadata_inspection_sanitizes_control_characters_without_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = FakeEntryPoint(
        "bad\nname",
        "module\n:get_profile",
        loaded=lambda: _module_profile(),
        distribution_name="dist\nname",
    )
    _install_entry_points(monkeypatch, routing=(entry,))

    rows = inspect_core_provider_entry_points(provider_kind="routing_module")

    assert rows[0].entry_point_name == "bad\ufffdname"
    assert rows[0].entry_point_target == "module\ufffd:get_profile"
    assert rows[0].distribution_name == "dist\ufffdname"
    assert entry.load_count == 0


def test_metadata_inspection_bounds_untrusted_display_text_without_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = FakeEntryPoint(
        "a" * 400,
        "target" * 300,
        loaded=lambda: _module_profile(),
        distribution_name="distribution" * 40,
    )
    _install_entry_points(monkeypatch, routing=(entry,))

    row = inspect_core_provider_entry_points(provider_kind="routing_module")[0]

    distribution_name = row.distribution_name
    assert distribution_name is not None
    assert len(row.entry_point_name) == 256
    assert len(row.entry_point_target) == 1024
    assert len(distribution_name) == 256
    assert row.entry_point_name.endswith("\N{HORIZONTAL ELLIPSIS}")
    assert row.entry_point_target.endswith("\N{HORIZONTAL ELLIPSIS}")
    assert distribution_name.endswith("\N{HORIZONTAL ELLIPSIS}")
    assert entry.load_count == 0


def test_empty_provider_inventory_is_explicitly_representable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_entry_points(monkeypatch)

    assert inspect_core_provider_entry_points() == ()
    assert diagnose_core_providers() == ()


def test_provider_kind_filter_and_invalid_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing = FakeEntryPoint(
        "concord",
        "concord:get_profile",
        loaded=lambda: _module_profile(),
    )
    publication = FakeEntryPoint(
        "concord",
        "concord:get_publication_profile",
        loaded=lambda: _publication_profile(),
    )
    _install_entry_points(
        monkeypatch,
        routing=(routing,),
        publication=(publication,),
    )

    rows = inspect_core_provider_entry_points(provider_kind="publication_producer")
    assert [(row.provider_kind, row.entry_point_name) for row in rows] == [
        ("publication_producer", "concord")
    ]
    assert routing.load_count == 0

    unsupported = cast(ProviderKind, "unsupported")
    with pytest.raises(ProviderDiagnosticRequestError):
        inspect_core_provider_entry_points(provider_kind=unsupported)
    with pytest.raises(ProviderDiagnosticRequestError):
        diagnose_core_providers(provider_kind=unsupported)


def test_enumeration_failure_is_bounded_and_preserves_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_entry_points(
        monkeypatch,
        fail_group=MODULE_PROFILE_ENTRY_POINT_GROUP,
    )

    with pytest.raises(ProviderEnumerationError) as raised:
        diagnose_core_providers(provider_kind="routing_module")

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert "metadata secret" not in str(raised.value)


def test_valid_routing_and_publication_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing_profile = _module_profile()
    publication_profile = _publication_profile()
    _install_entry_points(
        monkeypatch,
        routing=(
            FakeEntryPoint(
                "concord",
                "concord:get_profile",
                loaded=lambda: routing_profile,
            ),
        ),
        publication=(
            FakeEntryPoint(
                "concord",
                "concord:get_publication_profile",
                loaded=lambda: publication_profile,
            ),
        ),
    )

    results = diagnose_core_providers()

    assert [result.code for result in results] == [
        "provider.valid",
        "provider.valid",
    ]
    assert [result.stage for result in results] == ["valid", "valid"]
    assert results[0].validated_profile is routing_profile
    assert results[1].validated_profile == publication_profile
    assert all(result.load_attempted for result in results)
    assert all(result.load_succeeded for result in results)
    assert all(result.provider_call_attempted for result in results)
    assert all(result.provider_call_succeeded for result in results)
    assert all(result.profile_validation == "passed" for result in results)
    assert all(result.core_compatibility == "passed" for result in results)


def test_invalid_entry_point_name_is_reported_without_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = FakeEntryPoint(
        "Concord",
        "concord:get_profile",
        loaded=lambda: _module_profile(),
    )
    _install_entry_points(monkeypatch, routing=(entry,))

    result = diagnose_core_providers(provider_kind="routing_module")[0]

    assert result.code == "provider.entry_point_name_invalid"
    assert result.stage == "identity_validation"
    assert not result.load_attempted
    assert entry.load_count == 0


def test_load_failure_is_isolated_and_error_text_is_not_exposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = FakeEntryPoint(
        "broken",
        "broken:get_profile",
        load_error=ImportError("student-name-and-path-secret"),
    )
    valid = FakeEntryPoint(
        "concord",
        "concord:get_profile",
        loaded=lambda: _module_profile(),
    )
    _install_entry_points(monkeypatch, routing=(valid, broken))

    results = diagnose_core_providers(provider_kind="routing_module")

    assert [result.metadata.entry_point_name for result in results] == [
        "broken",
        "concord",
    ]
    assert [result.code for result in results] == [
        "provider.load_failed",
        "provider.valid",
    ]
    assert "student-name-and-path-secret" not in results[0].message
    assert results[1].validated_profile == _module_profile()


def test_non_callable_and_provider_call_failure_are_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    non_callable = FakeEntryPoint(
        "alpha",
        "alpha:get_profile",
        loaded=object(),
    )

    def raise_secret() -> ModuleProfile:
        raise RuntimeError("raw traceback detail")

    raises = FakeEntryPoint(
        "beta",
        "beta:get_profile",
        loaded=raise_secret,
    )
    _install_entry_points(monkeypatch, routing=(raises, non_callable))

    results = diagnose_core_providers(provider_kind="routing_module")

    assert [result.code for result in results] == [
        "provider.not_callable",
        "provider.call_failed",
    ]
    assert not results[0].provider_call_attempted
    assert results[1].provider_call_attempted
    assert not results[1].provider_call_succeeded
    assert "raw traceback detail" not in results[1].message


def test_invalid_profile_and_identity_mismatch_are_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = FakeEntryPoint(
        "alpha",
        "alpha:get_profile",
        loaded=lambda: {},
    )
    mismatch = FakeEntryPoint(
        "beta",
        "beta:get_profile",
        loaded=lambda: _module_profile("concord"),
    )
    _install_entry_points(monkeypatch, routing=(mismatch, invalid))

    results = diagnose_core_providers(provider_kind="routing_module")

    assert [result.code for result in results] == [
        "provider.profile_invalid",
        "provider.identity_mismatch",
    ]
    assert results[0].provider_call_succeeded
    assert results[0].profile_validation == "failed"
    assert results[1].profile_validation == "passed"
    assert results[1].declared_identity == "concord"
    assert results[1].core_compatibility == "not_attempted"


@pytest.mark.parametrize(
    ("provider_kind", "profile_factory"),
    [
        (
            "routing_module",
            lambda: _module_profile("concord", core_versions=frozenset({"2"})),
        ),
        (
            "publication_producer",
            lambda: _publication_profile(
                "concord", schema_versions=frozenset({"2"})
            ),
        ),
    ],
)
def test_active_core_compatibility_failure_is_distinct(
    monkeypatch: pytest.MonkeyPatch,
    provider_kind: ProviderKind,
    profile_factory: Callable[[], object],
) -> None:
    entry = FakeEntryPoint(
        "concord",
        "concord:get_profile",
        loaded=profile_factory,
    )
    if provider_kind == "routing_module":
        _install_entry_points(monkeypatch, routing=(entry,))
    else:
        _install_entry_points(monkeypatch, publication=(entry,))

    result = diagnose_core_providers(provider_kind=provider_kind)[0]

    assert result.code == "provider.core_incompatible"
    assert result.stage == "compatibility"
    assert result.profile_validation == "passed"
    assert result.core_compatibility == "failed"
    assert result.declared_identity == "concord"
    assert result.validated_profile is None


def test_duplicate_identity_marks_each_candidate_without_erasing_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = FakeEntryPoint(
        "concord",
        "a:get_profile",
        loaded=lambda: _module_profile(),
        distribution_name="dist-a",
    )
    second = FakeEntryPoint(
        "concord",
        "b:get_profile",
        loaded=lambda: _module_profile(),
        distribution_name="dist-b",
    )
    _install_entry_points(monkeypatch, routing=(second, first))

    results = diagnose_core_providers(provider_kind="routing_module")

    assert [result.code for result in results] == [
        "provider.identity_conflict",
        "provider.identity_conflict",
    ]
    assert [result.stage for result in results] == [
        "registry_conflict",
        "registry_conflict",
    ]
    assert [result.metadata.entry_point_target for result in results] == [
        "a:get_profile",
        "b:get_profile",
    ]
    assert [result.metadata.distribution_name for result in results] == [
        "dist-a",
        "dist-b",
    ]
    assert all(result.registry_conflict for result in results)
    assert all(result.declared_identity == "concord" for result in results)
    assert all(result.profile_validation == "passed" for result in results)


def test_identity_mismatch_is_not_misreported_as_registry_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mismatched = FakeEntryPoint(
        "wrong",
        "wrong:get_profile",
        loaded=lambda: _module_profile("concord"),
    )
    valid = FakeEntryPoint(
        "concord",
        "concord:get_profile",
        loaded=lambda: _module_profile("concord"),
    )
    _install_entry_points(monkeypatch, routing=(mismatched, valid))

    results = diagnose_core_providers(provider_kind="routing_module")

    assert [result.code for result in results] == [
        "provider.valid",
        "provider.identity_mismatch",
    ]
    assert not results[0].registry_conflict
    assert not results[1].registry_conflict


def test_strict_runtime_discovery_still_fails_closed_for_broken_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routing_valid = FakeEntryPoint(
        "concord",
        "concord:get_profile",
        loaded=lambda: _module_profile(),
    )
    routing_broken = FakeEntryPoint(
        "quillan",
        "quillan:get_profile",
        load_error=ImportError("broken routing provider"),
    )
    publication_valid = FakeEntryPoint(
        "concord",
        "concord:get_publication_profile",
        loaded=lambda: _publication_profile(),
    )
    publication_broken = FakeEntryPoint(
        "quillan",
        "quillan:get_publication_profile",
        loaded=object(),
    )
    _install_entry_points(
        monkeypatch,
        routing=(routing_valid, routing_broken),
        publication=(publication_valid, publication_broken),
    )

    with pytest.raises(ModuleDiscoveryError):
        discover_module_profiles()
    with pytest.raises(PublicationProducerDiscoveryError):
        discover_publication_producer_profiles()

    routing_results = diagnose_core_providers(provider_kind="routing_module")
    publication_results = diagnose_core_providers(
        provider_kind="publication_producer"
    )
    assert [result.code for result in routing_results] == [
        "provider.valid",
        "provider.load_failed",
    ]
    assert [result.code for result in publication_results] == [
        "provider.valid",
        "provider.not_callable",
    ]


def test_metadata_fallback_for_distribution_without_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = FakeEntryPoint(
        "concord",
        "concord:get_profile",
        loaded=lambda: _module_profile(),
    )
    entry.dist = SimpleNamespace(metadata={"Name": "fallback-dist"})
    _install_entry_points(monkeypatch, routing=(entry,))

    row = inspect_core_provider_entry_points(
        provider_kind="routing_module"
    )[0]

    assert row.distribution_name == "fallback-dist"
