"""Issue #229 Slice 3: publication outcomes cannot depend on reader metadata.

All producer examples are Core-shaped contract fixtures, NOT imported producers.
In particular, Portia's reader/publication identifiers are hypothetical.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from pds_core.academic_work_registrations import AcademicWorkRegistration
from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerProfile,
    PublicationProducerProfileError,
    PublicationReaderSupport,
    SourceRecordContractSupport,
    build_publication_producer_registry,
    evaluate_publication_compatibility,
    lookup_publication_reader_support,
    validate_publication_producer_profile,
)
from pds_core.publication_records import (
    PublicationCapability,
    PublicationRecord,
    publication_record_to_dict,
)
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef


@dataclass(frozen=True)
class ProducerCase:
    module: str
    distribution: str
    manifest: str
    reader_contract: str
    academic_work: str | None
    capabilities: tuple[PublicationCapability, ...]
    source_contract: str | None = None


# These are representative contracts, not producer wheel conformance tests.
CASES = (
    ProducerCase(
        "scoreform", "scoreform", "scoreform_academic_result_manifest_v1",
        "scoreform_academic_result_reader_v1", "scoreform_academic_work_v1",
        ("points", "question_evidence", "multiple_attempts"),
    ),
    ProducerCase(
        "quillan", "quillan", "quillan_academic_result_manifest_v1",
        "quillan_academic_result_reader_v1", "quillan_academic_work_v1",
        ("standards_ratings",),
    ),
    ProducerCase(
        "concord", "pds-concord", "concord_academic_result_manifest_v1",
        "concord_academic_result_reader_v1", "concord_academic_work_v1",
        ("criterion_scores", "moderated_scores", "standards_ratings"),
        "concord_activity_v1",
    ),
    ProducerCase(
        "portia", "pds-portia", "portia_intervention_manifest_v1",
        "portia_intervention_reader_v1", None,
        ("intervention_status", "intervention_history"),
    ),
)
ACADEMIC_CASES = CASES[:3]
PORTIA = CASES[3]
PUBLISHED = datetime(2026, 9, 1, tzinfo=UTC)


def reader(
    case: ProducerCase, *, version: str | None = None
) -> PublicationReaderSupport:
    return PublicationReaderSupport(
        manifest_contract_version=case.manifest,
        distribution_name=case.distribution,
        reader_contract_version=version or case.reader_contract,
    )


def profile(
    case: ProducerCase, *, with_reader: bool, capabilities: frozenset[PublicationCapability] | None = None
) -> PublicationProducerProfile:
    is_academic = case.academic_work is not None
    source = (
        (SourceRecordContractSupport("activity", frozenset({case.source_contract})),)
        if case.source_contract is not None
        else ()
    )
    support = PublicationContractSupport(
        publication_kind=(
            "academic_result_set" if is_academic else "intervention_record_set"
        ),
        manifest_contract_versions=frozenset({case.manifest}),
        supported_capabilities=(
            frozenset(case.capabilities) if capabilities is None else capabilities
        ),
        source_record_contracts=source,
        allows_missing_source_record=case.source_contract is None,
        reader_support=(reader(case),) if with_reader else (),
    )
    return PublicationProducerProfile(
        module_id=case.module,
        display_name=f"Synthetic {case.module.title()}",
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=(
            frozenset({case.academic_work}) if case.academic_work else frozenset()
        ),
        publication_contracts=(support,),
    )


def publication(case: ProducerCase, *, with_source: bool = True) -> PublicationRecord:
    work = ModuleWorkRef(case.module, "class_a", "work_a")
    is_academic = case.academic_work is not None
    source = (
        ModuleRecordRef(case.module, "activity", "activity_1", case.source_contract)
        if with_source and case.source_contract else None
    )
    return PublicationRecord(
        schema_version="1",
        record_type="publication_record",
        publication_id="pub_" + "1" * 32,
        work=work,
        source_record=source,
        publication_kind=(
            "academic_result_set" if is_academic else "intervention_record_set"
        ),
        capabilities=case.capabilities,
        record_set_id="results",
        record_set_revision=1,
        manifest_contract_version=case.manifest,
        manifest_path=(
            f"classes/class_a/modules/{case.module}/work/work_a/manifest.json"
        ),
        manifest_digest_algorithm="sha256",
        manifest_digest="a" * 64,
        published_at=PUBLISHED,
        academic_work_registration_revision=1 if is_academic else None,
        supersedes_publication_id=None,
    )


def registration(
    case: ProducerCase, record: PublicationRecord
) -> AcademicWorkRegistration | None:
    if case.academic_work is None:
        return None
    return AcademicWorkRegistration(
        schema_version="1",
        record_type="academic_work_registration",
        work=record.work,
        registration_revision=1,
        producer_contract_version=case.academic_work,
        title="Synthetic Work",
        work_kind="assignment",
        academic_intent="summative",
        lifecycle="active",
        created_at=PUBLISHED,
        updated_at=PUBLISHED,
        source_records=(),
    )


def outcome(
    case: ProducerCase,
    record: PublicationRecord,
    academic_registration: AcademicWorkRegistration | None,
    *,
    with_reader: bool,
    capabilities: frozenset[PublicationCapability] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    result = evaluate_publication_compatibility(
        record,
        profile(case, with_reader=with_reader, capabilities=capabilities),
        academic_registration,
    )
    return result.compatible, result.codes


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.module)
def test_valid_publication_is_unaffected_by_reader_metadata(case: ProducerCase) -> None:
    record = publication(case)
    academic_registration = registration(case, record)
    expected = (True, ())
    assert outcome(case, record, academic_registration, with_reader=False) == expected
    assert outcome(case, record, academic_registration, with_reader=True) == expected
    # Reader support does not alter the canonical Publication Record format.
    assert "reader_support" not in publication_record_to_dict(record)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.module)
def test_wrong_manifest_is_rejected_equally_with_and_without_reader(
    case: ProducerCase,
) -> None:
    record = replace(publication(case), manifest_contract_version="other_manifest_v1")
    academic_registration = registration(case, record)
    expected = (False, ("contracts.manifest_version_incompatible",))
    assert outcome(case, record, academic_registration, with_reader=False) == expected
    assert outcome(case, record, academic_registration, with_reader=True) == expected


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.module)
def test_capability_mismatch_is_unaffected_by_reader_metadata(
    case: ProducerCase,
) -> None:
    record = publication(case)
    academic_registration = registration(case, record)
    expected = (False, ("contracts.capability_incompatible",))
    for flag in (False, True):
        assert outcome(
            case, record, academic_registration,
            with_reader=flag, capabilities=frozenset(),
        ) == expected


@pytest.mark.parametrize("case", ACADEMIC_CASES, ids=lambda c: c.module)
def test_missing_academic_registration_remains_incompatible(case: ProducerCase) -> None:
    record = publication(case)
    expected = (False, ("contracts.registration_version_incompatible",))
    assert outcome(case, record, None, with_reader=False) == expected
    assert outcome(case, record, None, with_reader=True) == expected


@pytest.mark.parametrize("case", ACADEMIC_CASES, ids=lambda c: c.module)
def test_wrong_academic_work_contract_remains_incompatible(case: ProducerCase) -> None:
    record = publication(case)
    original = registration(case, record)
    assert original is not None
    wrong = replace(original, producer_contract_version="other_academic_work_v1")
    expected = (False, ("contracts.registration_version_incompatible",))
    assert outcome(case, record, wrong, with_reader=False) == expected
    assert outcome(case, record, wrong, with_reader=True) == expected


@pytest.mark.parametrize("with_reader", [False, True])
def test_concord_source_record_requirements_remain_independent_of_reader(
    with_reader: bool,
) -> None:
    record = publication(CASES[2], with_source=False)
    reg = registration(CASES[2], record)
    assert outcome(CASES[2], record, reg, with_reader=with_reader) == (
        False, ("contracts.source_record_missing_incompatible",)
    )
    wrong_source = ModuleRecordRef("concord", "activity", "activity_1", "other_v1")
    wrong_record = replace(publication(CASES[2]), source_record=wrong_source)
    assert outcome(CASES[2], wrong_record, reg, with_reader=with_reader) == (
        False, ("contracts.source_record_version_incompatible",)
    )


@pytest.mark.parametrize("with_reader", [False, True])
def test_portia_intervention_never_requires_academic_registration(
    with_reader: bool,
) -> None:
    p = profile(PORTIA, with_reader=with_reader)
    assert p.supported_academic_work_contract_versions == frozenset()
    record = publication(PORTIA)
    assert record.academic_work_registration_revision is None
    assert evaluate_publication_compatibility(record, p).compatible
    assert lookup_publication_reader_support(
        p, "intervention_record_set", PORTIA.manifest
    ) == (reader(PORTIA) if with_reader else None)
    # Even with a valid declaration, academic registration is forbidden for Portia.
    fake_academic = AcademicWorkRegistration(
        schema_version="1",
        record_type="academic_work_registration",
        work=record.work,
        registration_revision=1,
        producer_contract_version="portia_other_v1",
        title="Synthetic Work",
        work_kind="assignment",
        academic_intent="summative",
        lifecycle="active",
        created_at=PUBLISHED,
        updated_at=PUBLISHED,
        source_records=(),
    )
    with pytest.raises(PublicationProducerProfileError):
        evaluate_publication_compatibility(record, p, fake_academic)


def test_metadata_cannot_claim_automatic_consumer_compatibility() -> None:
    case = CASES[0]
    legacy = profile(case, with_reader=False)
    new_contract = replace(
        legacy.publication_contracts[0],
        reader_support=(reader(case, version="scoreform_future_reader_v2"),),
    )
    declared = replace(legacy, publication_contracts=(new_contract,))
    record = publication(case)
    reg = registration(case, record)
    assert evaluate_publication_compatibility(record, declared, reg).compatible
    # Core reports the producer's declaration, not a consumer support verdict.
    assert lookup_publication_reader_support(
        declared, "academic_result_set", case.manifest
    ) == reader(case, version="scoreform_future_reader_v2")


def test_all_four_profiles_survive_registry_and_revalidation_without_siblings() -> None:
    profiles = tuple(profile(case, with_reader=True) for case in CASES)
    registry = build_publication_producer_registry(
        explicit_profiles=profiles, discover_installed=False
    )
    assert tuple(p.module_id for p in registry.profiles) == (
        "concord", "portia", "quillan", "scoreform"
    )
    for case in CASES:
        found = registry.get(case.module)
        assert found is not None
        assert validate_publication_producer_profile(found) == found
        result = lookup_publication_reader_support(
            found,
            "academic_result_set" if case.academic_work else "intervention_record_set",
            case.manifest,
        )
        assert result == reader(case)
        assert result.distribution_name == case.distribution


def test_partial_multi_manifest_support_preserves_publication_compatibility() -> None:
    case = CASES[0]
    old = profile(case, with_reader=False)
    original_support = old.publication_contracts[0]
    old_support = replace(
        original_support,
        manifest_contract_versions=frozenset({case.manifest, "future_manifest_v2"}),
    )
    new_support = replace(old_support, reader_support=(reader(case),))
    old_profile = replace(old, publication_contracts=(old_support,))
    new_profile = replace(old, publication_contracts=(new_support,))
    future_record = replace(
        publication(case), manifest_contract_version="future_manifest_v2"
    )
    reg = registration(case, future_record)
    assert evaluate_publication_compatibility(
        future_record, old_profile, reg
    ).compatible
    assert evaluate_publication_compatibility(
        future_record, new_profile, reg
    ).compatible
    assert lookup_publication_reader_support(
        new_profile, "academic_result_set", "future_manifest_v2"
    ) is None
