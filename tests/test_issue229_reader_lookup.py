"""Core #229 Slice 2: exact metadata lookup and profile propagation."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import builtins
import importlib.metadata as importlib_metadata
from typing import Any

import pytest

import pds_core.publication_compatibility as compatibility
from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerProfile,
    PublicationProducerProfileError,
    PublicationReaderSupport,
    build_publication_producer_registry,
    discover_publication_producer_profiles,
    lookup_publication_reader_support,
    validate_publication_producer_profile,
)


def declared_reader(
    manifest: str = "fixture_manifest_v1",
    contract: str = "fixture_reader_v1",
) -> PublicationReaderSupport:
    return PublicationReaderSupport(
        manifest_contract_version=manifest,
        distribution_name="pds-fixture",
        reader_contract_version=contract,
    )


def profile(*, with_reader: bool = True) -> PublicationProducerProfile:
    reader_rows = (declared_reader(),) if with_reader else ()
    return PublicationProducerProfile(
        module_id="fixture_producer",
        display_name="Fixture Producer",
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=frozenset({"academic_work_v1"}),
        publication_contracts=(
            PublicationContractSupport(
                publication_kind="academic_result_set",
                manifest_contract_versions=frozenset(
                    {"fixture_manifest_v1", "fixture_manifest_v2"}
                ),
                supported_capabilities=frozenset({"standards_ratings"}),
                reader_support=reader_rows,
            ),
        ),
    )


def intervention_profile(*, with_reader: bool) -> PublicationProducerProfile:
    return PublicationProducerProfile(
        module_id="portia_fixture",
        display_name="Synthetic Portia",
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=frozenset(),
        publication_contracts=(
            PublicationContractSupport(
                publication_kind="intervention_record_set",
                manifest_contract_versions=frozenset({"portia_intervention_v1"}),
                supported_capabilities=frozenset({"intervention_status"}),
                reader_support=(
                    PublicationReaderSupport(
                        "portia_intervention_v1",
                        "pds-portia",
                        "portia_intervention_reader_v1",
                    ),
                ) if with_reader else (),
            ),
        ),
    )


def test_exact_lookup_preserves_reader_identity() -> None:
    original = profile()
    assert lookup_publication_reader_support(
        original, "academic_result_set", "fixture_manifest_v1"
    ) == declared_reader()


def test_unadvertised_manifest_does_not_inherit_reader() -> None:
    assert lookup_publication_reader_support(
        profile(), "academic_result_set", "fixture_manifest_v2"
    ) is None
    assert lookup_publication_reader_support(
        profile(), "academic_result_set", "future_manifest_v1"
    ) is None


def test_absent_reader_metadata_has_no_implicit_fallback() -> None:
    assert profile(with_reader=False).publication_contracts[0].reader_support == ()
    assert lookup_publication_reader_support(
        profile(with_reader=False), "academic_result_set", "fixture_manifest_v1"
    ) is None


def test_publication_kind_is_an_exact_lookup_dimension() -> None:
    assert lookup_publication_reader_support(
        profile(), "intervention_record_set", "fixture_manifest_v1"
    ) is None


@pytest.mark.parametrize("with_reader", [False, True])
def test_portia_shaped_intervention_profile_is_supported(
    with_reader: bool,
) -> None:
    value = intervention_profile(with_reader=with_reader)
    assert value.supported_academic_work_contract_versions == frozenset()
    result = lookup_publication_reader_support(
        value, "intervention_record_set", "portia_intervention_v1"
    )
    assert (result is not None) is with_reader
    if result is not None:
        assert result.distribution_name == "pds-portia"
        assert result.reader_contract_version == "portia_intervention_reader_v1"


def test_profile_revalidation_preserves_reader_metadata() -> None:
    original = profile()
    renewed = validate_publication_producer_profile(original)
    assert renewed == original
    assert renewed is not original
    assert renewed.publication_contracts[0].reader_support == (declared_reader(),)
    assert lookup_publication_reader_support(
        renewed, "academic_result_set", "fixture_manifest_v1"
    ) == declared_reader()


def test_registry_revalidation_preserves_both_profile_shapes() -> None:
    academic = profile()
    intervention = intervention_profile(with_reader=True)
    registry = build_publication_producer_registry(
        explicit_profiles=(intervention, academic), discover_installed=False
    )
    assert [row.module_id for row in registry.profiles] == [
        "fixture_producer", "portia_fixture"
    ]
    for declared in (academic, intervention):
        assert registry.get(declared.module_id) == declared
    assert lookup_publication_reader_support(
        registry.get("portia_fixture"),  # type: ignore[arg-type]
        "intervention_record_set",
        "portia_intervention_v1",
    ) == intervention.publication_contracts[0].reader_support[0]


def test_validated_profiles_remain_backward_compatible() -> None:
    old = profile(with_reader=False)
    assert validate_publication_producer_profile(old) == old
    assert replace(old.publication_contracts[0]).reader_support == ()


@pytest.mark.parametrize(
    ("kind", "manifest"),
    [
        ("bad_kind", "fixture_manifest_v1"),
        ("academic_result_set", ""),
        ("academic_result_set", "../invalid"),
        ("academic_result_set", None),
    ],
)
def test_invalid_lookup_arguments_fail_closed(kind: object, manifest: object) -> None:
    with pytest.raises(PublicationProducerProfileError):
        lookup_publication_reader_support(
            profile(), kind, manifest  # type: ignore[arg-type]
        )


def test_invalid_profile_type_rejected_before_lookup() -> None:
    with pytest.raises(PublicationProducerProfileError):
        lookup_publication_reader_support(
            object(), "academic_result_set", "fixture_manifest_v1"  # type: ignore[arg-type]
        )


class _EntryPoints(tuple[object, ...]):
    def select(self, *, group: str) -> _EntryPoints:
        assert group == compatibility.PUBLICATION_PRODUCER_ENTRY_POINT_GROUP
        return self


def test_installed_discovery_preserves_metadata_and_never_imports_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producers = (
        SimpleNamespace(
            name="portia_fixture",
            load=lambda: lambda: intervention_profile(with_reader=True),
        ),
        SimpleNamespace(name="fixture_producer", load=lambda: profile),
    )
    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _EntryPoints(producers),
    )
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(
            (
                "scoreform.academic_result_reader",
                "quillan.academic_result_reader",
                "concord.academic_result_reader",
                "portia.academic_result_reader",
            )
        ):
            raise AssertionError("Metadata discovery imported a producer reader.")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    found = discover_publication_producer_profiles()
    assert [row.module_id for row in found] == [
        "fixture_producer", "portia_fixture"
    ]
    assert lookup_publication_reader_support(
        found[0], "academic_result_set", "fixture_manifest_v1"
    ) == declared_reader()
    assert lookup_publication_reader_support(
        found[1], "intervention_record_set", "portia_intervention_v1"
    ) == (
        intervention_profile(with_reader=True)
        .publication_contracts[0]
        .reader_support[0]
    )
