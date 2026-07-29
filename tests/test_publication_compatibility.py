from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
import importlib.metadata as importlib_metadata

import pytest

from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerProfile,
    PublicationProducerProfileError,
    SourceRecordContractSupport,
    build_publication_producer_registry,
    discover_publication_producer_profiles,
    evaluate_publication_compatibility,
)
import pds_core.publication_compatibility as compatibility
from pds_core.academic_work_registrations import AcademicWorkRegistration
from pds_core.publication_records import PublicationRecord
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef


def profile() -> PublicationProducerProfile:
    return PublicationProducerProfile(
        module_id="quillan",
        display_name="Quillan",
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=frozenset({"1"}),
        publication_contracts=(
            PublicationContractSupport(
                publication_kind="academic_result_set",
                manifest_contract_versions=frozenset({"1"}),
                supported_capabilities=frozenset({"standards_ratings"}),
                source_record_contracts=(
                    SourceRecordContractSupport(
                        "rating", frozenset({"1"}), allows_unversioned=False
                    ),
                ),
                allows_missing_source_record=False,
            ),
        ),
    )


def publication(*, version: str = "1") -> PublicationRecord:
    return PublicationRecord(
        schema_version="1",
        record_type="publication_record",
        publication_id="pub_11111111111111111111111111111111",
        work=ModuleWorkRef("quillan", "class_a", "essay"),
        source_record=ModuleRecordRef("quillan", "rating", "rating_1", version),
        publication_kind="academic_result_set",
        capabilities=("standards_ratings",),
        record_set_id="results",
        record_set_revision=1,
        manifest_contract_version="1",
        manifest_path="classes/class_a/modules/quillan/work/essay/manifest.json",
        manifest_digest_algorithm="sha256",
        manifest_digest="0" * 64,
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        academic_work_registration_revision=1,
        supersedes_publication_id=None,
    )


def registration(
    value: PublicationRecord,
    *,
    work: ModuleWorkRef | None = None,
    revision: int = 1,
    version: str = "1",
) -> AcademicWorkRegistration:
    return AcademicWorkRegistration(
        schema_version="1",
        record_type="academic_work_registration",
        work=value.work if work is None else work,
        registration_revision=revision,
        producer_contract_version=version,
        title="Essay",
        work_kind="assignment",
        academic_intent="summative",
        lifecycle="active",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, tzinfo=UTC),
        source_records=(),
    )


def test_profile_is_frozen_sorted_and_registry_lookup() -> None:
    value = profile()
    assert value.publication_contracts[0].publication_kind == "academic_result_set"
    assert build_publication_producer_registry(
        explicit_profiles=(value,), discover_installed=False
    ).get("quillan") == value
    with pytest.raises(AttributeError):
        value.module_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize("module_id", ["Quillan", "../quillan", ""])
def test_profile_rejects_invalid_module_id(module_id: str) -> None:
    with pytest.raises(PublicationProducerProfileError):
        PublicationProducerProfile(
            module_id,
            "Quillan",
            frozenset({"1"}),
            frozenset({"1"}),
            profile().publication_contracts,
        )


def test_evaluate_supported_and_version_incompatible() -> None:
    value = publication()
    assert evaluate_publication_compatibility(
        value, profile(), registration(value)
    ).compatible
    changed = publication(version="2")
    result = evaluate_publication_compatibility(
        changed, profile(), registration(changed)
    )
    assert not result.compatible
    assert result.codes == ("contracts.source_record_version_incompatible",)


def test_duplicate_support_rows_are_rejected() -> None:
    row = profile().publication_contracts[0]
    with pytest.raises(PublicationProducerProfileError):
        PublicationProducerProfile(
            "quillan", "Quillan", frozenset({"1"}), frozenset({"1"}), (row, row)
        )


def test_every_claimed_compatibility_code() -> None:
    value = publication()
    support = profile().publication_contracts[0]
    other_profile = replace(profile(), module_id="other")
    assert "contracts.profile_module_mismatch" in evaluate_publication_compatibility(
        value, other_profile, registration(value)
    ).codes
    unsupported_schema = replace(
        profile(), supported_core_publication_schema_versions=frozenset({"2"})
    )
    assert "contracts.publication_schema_incompatible" in evaluate_publication_compatibility(
        value, unsupported_schema, registration(value)
    ).codes
    unsupported_registration = replace(
        profile(), supported_academic_work_contract_versions=frozenset({"2"})
    )
    assert "contracts.registration_version_incompatible" in evaluate_publication_compatibility(
        value, unsupported_registration, registration(value)
    ).codes
    intervention = replace(
        value,
        publication_kind="intervention_record_set",
        capabilities=("intervention_status",),
        source_record=None,
        academic_work_registration_revision=None,
    )
    assert "contracts.publication_kind_incompatible" in evaluate_publication_compatibility(
        intervention, profile()
    ).codes
    assert "contracts.manifest_version_incompatible" in evaluate_publication_compatibility(
        replace(value, manifest_contract_version="2"),
        profile(),
        registration(value),
    ).codes
    no_capabilities = replace(
        profile(),
        publication_contracts=(replace(support, supported_capabilities=frozenset()),),
    )
    assert "contracts.capability_incompatible" in evaluate_publication_compatibility(
        value, no_capabilities, registration(value)
    ).codes
    assert "contracts.source_record_missing_incompatible" in evaluate_publication_compatibility(
        replace(value, source_record=None), profile(), registration(value)
    ).codes
    wrong_kind = replace(
        value,
        source_record=ModuleRecordRef("quillan", "other", "rating_1", "1"),
    )
    assert "contracts.source_record_kind_incompatible" in evaluate_publication_compatibility(
        wrong_kind, profile(), registration(wrong_kind)
    ).codes
    assert "contracts.source_record_version_incompatible" in evaluate_publication_compatibility(
        publication(version="2"), profile(), registration(value)
    ).codes


def test_registration_relationship_is_exact_and_intervention_needs_none() -> None:
    value = publication()
    with pytest.raises(PublicationProducerProfileError):
        evaluate_publication_compatibility(
            value,
            profile(),
            registration(value, work=ModuleWorkRef("quillan", "class_b", "essay")),
        )
    with pytest.raises(PublicationProducerProfileError):
        evaluate_publication_compatibility(
            value, profile(), registration(value, revision=2)
        )
    assert evaluate_publication_compatibility(value, profile()).codes == (
        "contracts.registration_version_incompatible",
    )
    intervention = replace(
        value,
        publication_kind="intervention_record_set",
        capabilities=("intervention_status",),
        source_record=None,
        academic_work_registration_revision=None,
    )
    assert "contracts.publication_kind_incompatible" in evaluate_publication_compatibility(
        intervention, profile()
    ).codes


class _EntryPoints(tuple[object, ...]):
    def select(self, *, group: str) -> "_EntryPoints":
        return self


def _point(name: str, loaded: object) -> SimpleNamespace:
    return SimpleNamespace(name=name, load=lambda: loaded)


def test_discovery_identity_order_duplicates_and_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = replace(profile(), module_id="zeta", display_name="Zeta")
    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _EntryPoints((_point("zeta", lambda: second), _point("quillan", profile))),
    )
    assert [item.module_id for item in discover_publication_producer_profiles()] == [
        "quillan",
        "zeta",
    ]
    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _EntryPoints((_point("wrong", profile),)),
    )
    with pytest.raises(compatibility.PublicationProducerDiscoveryError):
        discover_publication_producer_profiles()
    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _EntryPoints((_point("quillan", object()),)),
    )
    with pytest.raises(compatibility.PublicationProducerDiscoveryError):
        discover_publication_producer_profiles()

    def broken() -> PublicationProducerProfile:
        raise RuntimeError("provider failed")

    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: _EntryPoints((_point("quillan", broken),)),
    )
    with pytest.raises(compatibility.PublicationProducerDiscoveryError):
        discover_publication_producer_profiles()


def test_defensive_result_registry_and_display_name_validation() -> None:
    with pytest.raises(PublicationProducerProfileError):
        compatibility.PublicationCompatibilityResult(False, [["bad"]])  # type: ignore[arg-type]
    with pytest.raises(PublicationProducerProfileError):
        compatibility.PublicationCompatibilityResult(True, "contracts.bad")  # type: ignore[arg-type]
    with pytest.raises(compatibility.PublicationProducerRegistryError):
        compatibility.PublicationProducerRegistry("bad")  # type: ignore[arg-type]
    with pytest.raises(PublicationProducerProfileError):
        replace(profile(), display_name="bad\nname")
    with pytest.raises(PublicationProducerProfileError):
        replace(profile(), display_name="bad\u2028name")
    with pytest.raises(PublicationProducerProfileError):
        replace(profile(), publication_contracts={"academic_result_set": True})  # type: ignore[arg-type]
