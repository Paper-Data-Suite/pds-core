"""Core #229 Slice 1: immutable, manifest-bound reader declarations."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerProfileError,
    PublicationReaderSupport,
)


def reader(
    manifest: str = "fixture_manifest_v1",
    *,
    distribution: str = "pds-fixture",
    contract: str = "fixture_reader_v1",
) -> PublicationReaderSupport:
    return PublicationReaderSupport(
        manifest_contract_version=manifest,
        distribution_name=distribution,
        reader_contract_version=contract,
    )


def support(
    reader_support: object = (),
    *,
    kind: str = "academic_result_set",
) -> PublicationContractSupport:
    return PublicationContractSupport(
        publication_kind=kind,  # type: ignore[arg-type]
        manifest_contract_versions=frozenset(
            {"fixture_manifest_v1", "fixture_manifest_v2"}
        ),
        supported_capabilities=frozenset({"standards_ratings"}),
        reader_support=reader_support,  # type: ignore[arg-type]
    )


def test_old_positional_publication_support_remains_valid() -> None:
    old = PublicationContractSupport(
        "academic_result_set",
        frozenset({"fixture_manifest_v1"}),
        frozenset({"standards_ratings"}),
    )
    assert old.reader_support == ()
    assert replace(old) == old
    assert support().reader_support == ()


def test_reader_declares_exact_manifest_distribution_and_contract() -> None:
    value = reader()
    assert value.manifest_contract_version == "fixture_manifest_v1"
    assert value.distribution_name == "pds-fixture"
    assert value.reader_contract_version == "fixture_reader_v1"
    with pytest.raises(FrozenInstanceError):
        value.reader_contract_version = "different_v1"  # type: ignore[misc]


def test_reader_collection_freezes_and_sorts_by_manifest() -> None:
    earlier = reader("fixture_manifest_v1")
    later = reader("fixture_manifest_v2", contract="fixture_reader_v2")
    mutable = [later, earlier]
    validated = support(mutable)
    assert validated.reader_support == (earlier, later)
    mutable.clear()
    assert validated.reader_support == (earlier, later)
    with pytest.raises(FrozenInstanceError):
        validated.reader_support = ()  # type: ignore[misc]
    assert support((earlier, later)) == validated


def test_partial_reader_advertisement_does_not_infer_other_manifest() -> None:
    validated = support((reader(),))
    assert len(validated.manifest_contract_versions) == 2
    assert validated.reader_support == (reader(),)
    assert not any(
        value.manifest_contract_version == "fixture_manifest_v2"
        for value in validated.reader_support
    )


def test_intervention_publication_uses_the_identical_reader_metadata_type() -> None:
    assert support((reader(),), kind="intervention_record_set").reader_support == (
        reader(),
    )
    assert support(kind="intervention_record_set").reader_support == ()


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("manifest_contract_version", ""),
        ("manifest_contract_version", "has spaces"),
        ("manifest_contract_version", "../escape"),
        ("manifest_contract_version", None),
        ("distribution_name", ""),
        ("distribution_name", "PDS-fixture"),
        ("distribution_name", "pds_fixture"),
        ("distribution_name", "pds.fixture"),
        ("distribution_name", "pds--fixture"),
        ("distribution_name", "pds fixture"),
        ("distribution_name", "pds-fixture/other"),
        ("distribution_name", "a" * 129),
        ("distribution_name", None),
        ("reader_contract_version", ""),
        ("reader_contract_version", "BAD_reader_v1"),
        ("reader_contract_version", "bad-reader-v1"),
        ("reader_contract_version", "bad reader v1"),
        ("reader_contract_version", "123"),
        ("reader_contract_version", "a" * 129),
        ("reader_contract_version", None),
    ],
)
def test_invalid_reader_identity_is_rejected(name: str, bad: object) -> None:
    with pytest.raises(PublicationProducerProfileError):
        replace(reader(), **{name: bad})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [None, "text", b"bytes", {"fixture_manifest_v1": reader()}, (object(),)],
)
def test_invalid_reader_collections_are_rejected(bad: object) -> None:
    with pytest.raises(PublicationProducerProfileError):
        support(bad)


def test_duplicate_manifest_binding_fails_even_if_reader_claim_differs() -> None:
    with pytest.raises(PublicationProducerProfileError, match="duplicate"):
        support((reader(), reader()))
    with pytest.raises(PublicationProducerProfileError, match="duplicate"):
        support((reader(), reader(contract="different_reader_v1")))


def test_unsupported_manifest_binding_is_rejected() -> None:
    with pytest.raises(PublicationProducerProfileError, match="unsupported manifest"):
        support((reader("unadvertised_manifest_v1"),))


def test_iterator_input_is_frozen_at_construction() -> None:
    values = iter([reader("fixture_manifest_v2"), reader()])
    assert support(values).reader_support == (reader(), reader("fixture_manifest_v2"))
