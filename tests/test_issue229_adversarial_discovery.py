"""Issue #229 Slice 4: reader declarations are bounded, exact and inert.

Synthetic Core metadata only. No producer reader is imported or invoked.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.metadata as importlib_metadata
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import pds_core.publication_compatibility as compatibility
from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerDiscoveryError,
    PublicationProducerProfile,
    PublicationProducerProfileError,
    PublicationReaderSupport,
    build_publication_producer_registry,
    discover_publication_producer_profiles,
    lookup_publication_reader_support,
)
from pds_core.publication_records import PublicationCapability


MANIFEST_1 = "fixture_manifest_v1"
MANIFEST_2 = "fixture_manifest_v2"


def reader(
    manifest: str = MANIFEST_1,
    *,
    distribution: str = "pds-fixture",
    contract: str = "fixture_reader_v1",
) -> PublicationReaderSupport:
    return PublicationReaderSupport(manifest, distribution, contract)


def publication_support(
    declarations: object = (),
    *,
    kind: str = "academic_result_set",
) -> PublicationContractSupport:
    capabilities: frozenset[PublicationCapability] = (
        frozenset({"standards_ratings"})
        if kind == "academic_result_set"
        else frozenset({"intervention_status"})
    )
    return PublicationContractSupport(
        publication_kind=kind,  # type: ignore[arg-type]
        manifest_contract_versions=frozenset({MANIFEST_1, MANIFEST_2}),
        supported_capabilities=capabilities,
        reader_support=declarations,  # type: ignore[arg-type]
    )


def producer(
    declarations: object = (),
    *,
    module: str = "fixture",
    kind: str = "academic_result_set",
) -> PublicationProducerProfile:
    return PublicationProducerProfile(
        module_id=module,
        display_name="Synthetic Producer",
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=(
            frozenset({"academic_v1"})
            if kind == "academic_result_set"
            else frozenset()
        ),
        publication_contracts=(publication_support(declarations, kind=kind),),
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        19,
        "reader",
        b"reader",
        {MANIFEST_1: reader()},
        (reader(), object()),
        (reader(), {"manifest_contract_version": MANIFEST_2}),
        [None],
    ],
)
def test_bad_declaration_collection_fails_with_core_error(value: object) -> None:
    with pytest.raises(PublicationProducerProfileError):
        publication_support(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_contract_version", "../fixture_manifest_v1"),
        ("manifest_contract_version", "fixture.manifest.v1"),
        ("manifest_contract_version", "fixture\u200bmanifest_v1"),
        ("manifest_contract_version", "fixture_manifest_v1\n"),
        ("distribution_name", "PDS-Fixture"),
        ("distribution_name", "pds_fixture"),
        ("distribution_name", "pds.fixture"),
        ("distribution_name", "-pds-fixture"),
        ("distribution_name", "pds-fixture-"),
        ("distribution_name", "pds--fixture"),
        ("distribution_name", "pds-fixture/reader"),
        ("distribution_name", "pds-fixture\x00reader"),
        ("reader_contract_version", "fixture-reader-v1"),
        ("reader_contract_version", "Fixture_reader_v1"),
        ("reader_contract_version", "fixture.reader.v1"),
        ("reader_contract_version", "fixture_reader_v1\n"),
        ("reader_contract_version", "fixture_reader_v1/../../x"),
    ],
)
def test_declaration_rejects_noncanonical_or_unsafe_identity(
    field: str, value: str
) -> None:
    with pytest.raises(PublicationProducerProfileError):
        replace(reader(), **{field: value})


@pytest.mark.parametrize("same_contract", [True, False])
def test_duplicate_manifest_binding_is_ambiguous_even_when_identical(
    same_contract: bool,
) -> None:
    second = reader() if same_contract else reader(contract="other_reader_v1")
    with pytest.raises(PublicationProducerProfileError, match="duplicate"):
        publication_support((reader(), second))


def test_unsupported_manifest_binding_rejected_before_registry() -> None:
    with pytest.raises(PublicationProducerProfileError, match="unsupported manifest"):
        publication_support((reader("other_manifest_v1"),))


def test_partial_manifest_binding_does_not_infer_reader_support() -> None:
    p = producer((reader(MANIFEST_2),))
    assert lookup_publication_reader_support(p, "academic_result_set", MANIFEST_1) is None
    assert lookup_publication_reader_support(p, "academic_result_set", MANIFEST_2) == reader(
        MANIFEST_2
    )
    assert lookup_publication_reader_support(p, "academic_result_set", "future_v1") is None


def test_multiple_manifest_versions_require_explicit_independent_bindings() -> None:
    a = reader(MANIFEST_1)
    b = reader(MANIFEST_2, contract="fixture_reader_v2")
    p = producer(iter([b, a]))
    assert p.publication_contracts[0].reader_support == (a, b)
    assert lookup_publication_reader_support(p, "academic_result_set", MANIFEST_1) == a
    assert lookup_publication_reader_support(p, "academic_result_set", MANIFEST_2) == b


def test_academic_and_intervention_bindings_remain_kind_scoped() -> None:
    academic = publication_support((reader(),))
    intervention_reader = reader(contract="fixture_intervention_reader_v1")
    intervention = publication_support(
        (intervention_reader,), kind="intervention_record_set"
    )
    mixed = replace(producer(), publication_contracts=(intervention, academic))
    assert lookup_publication_reader_support(
        mixed, "academic_result_set", MANIFEST_1
    ) == reader()
    assert lookup_publication_reader_support(
        mixed, "intervention_record_set", MANIFEST_1
    ) == intervention_reader
    assert lookup_publication_reader_support(
        mixed, "intervention_record_set", MANIFEST_2
    ) is None


class EntryPoints(tuple[object, ...]):
    def select(self, *, group: str) -> EntryPoints:
        assert group == compatibility.PUBLICATION_PRODUCER_ENTRY_POINT_GROUP
        return self


def test_discovery_and_lookup_do_not_import_readers_or_access_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Core loads the producer *profile provider*, not its reader implementation."""
    calls: list[str] = []
    p = producer((reader(),), module="fixture")

    def load_profile_provider() -> object:
        calls.append("load_profile_provider")

        def profile_provider() -> PublicationProducerProfile:
            calls.append("profile_provider")
            return p

        return profile_provider

    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: EntryPoints((SimpleNamespace(name="fixture", load=load_profile_provider),)),
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Reader inspection accessed an external resource")

    original_import = builtins.__import__
    original_import_module = importlib.import_module

    def guard_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(("scoreform.academic_result_reader", "quillan.academic_result_reader", "concord.academic_result_reader", "portia.publication_reader")):
            raise AssertionError("A producer reader was imported")
        return original_import(name, *args, **kwargs)

    def guard_import_module(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.endswith("reader"):
            raise AssertionError("A producer reader was dynamically imported")
        return original_import_module(name, *args, **kwargs)

    with monkeypatch.context() as scope:
        scope.setattr(builtins, "open", forbidden)
        scope.setattr(Path, "open", forbidden)
        scope.setattr(Path, "read_text", forbidden)
        scope.setattr(Path, "read_bytes", forbidden)
        scope.setattr(importlib_metadata, "version", forbidden)
        scope.setattr(builtins, "__import__", guard_import)
        scope.setattr(importlib, "import_module", guard_import_module)
        discovered = discover_publication_producer_profiles()
        found = lookup_publication_reader_support(
            discovered[0], "academic_result_set", MANIFEST_1
        )
    assert calls == ["load_profile_provider", "profile_provider"]
    assert discovered == (p,)
    assert found == reader()


def test_invalid_nested_metadata_from_entrypoint_fails_discovery_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_provider() -> PublicationProducerProfile:
        return producer((reader(), reader(contract="other_reader_v1")))

    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: EntryPoints((SimpleNamespace(name="fixture", load=lambda: invalid_provider),)),
    )
    with pytest.raises(PublicationProducerDiscoveryError):
        discover_publication_producer_profiles()


def test_explicit_registry_without_discovery_never_loads_installed_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden() -> object:
        raise AssertionError("discover_installed=False used entry_points")

    monkeypatch.setattr(importlib_metadata, "entry_points", forbidden)
    value = producer((reader(),))
    registry = build_publication_producer_registry(
        explicit_profiles=(value,), discover_installed=False
    )
    assert registry.get("fixture") == value


def test_intervention_metadata_never_implies_reader_execution() -> None:
    p = producer(
        (reader(contract="portia_intervention_reader_v1"),),
        module="portia_fixture",
        kind="intervention_record_set",
    )
    assert p.supported_academic_work_contract_versions == frozenset()
    assert lookup_publication_reader_support(
        p, "intervention_record_set", MANIFEST_1
    ) == reader(contract="portia_intervention_reader_v1")
