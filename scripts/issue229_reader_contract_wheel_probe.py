"""Strict, source-isolated installed Core #229 reader metadata probe.

This script is executed under an isolated Python interpreter in a fresh venv.
The Core source checkout is not placed on its import path.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_probe(*, expected_version: str, forbidden_root: Path) -> dict[str, object]:
    import pds_core
    from pds_core.academic_work_registrations import AcademicWorkRegistration
    from pds_core.publication_compatibility import (
        CORE_PUBLICATION_COMPATIBILITY_CONTRACT_VERSION,
        PublicationContractSupport,
        PublicationProducerProfile,
        PublicationReaderSupport,
        build_publication_producer_registry,
        evaluate_publication_compatibility,
        lookup_publication_reader_support,
        validate_publication_producer_profile,
    )
    from pds_core.publication_records import PublicationRecord
    from pds_core.routing_models import ModuleWorkRef

    require(importlib.metadata.version("pds-core") == expected_version, "Core distribution version mismatch.")
    require(pds_core.__version__ == expected_version, "Core package version mismatch.")
    require(CORE_PUBLICATION_COMPATIBILITY_CONTRACT_VERSION == "1", "Core publication compatibility contract changed.")
    origin_file = getattr(pds_core, "__file__", None)
    require(isinstance(origin_file, str), "Core package origin is unavailable.")
    assert isinstance(origin_file, str)
    origin = Path(origin_file).resolve()
    require(not origin.is_relative_to(forbidden_root.resolve()), "Core imported from source checkout.")

    work = ModuleWorkRef("scoreform", "class_a", "assessment_a")
    registration = AcademicWorkRegistration(
        schema_version="1",
        record_type="academic_work_registration",
        work=work,
        registration_revision=1,
        producer_contract_version="scoreform_academic_work_v1",
        title="Synthetic acceptance",
        work_kind="assignment",
        academic_intent="summative",
        lifecycle="active",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_records=(),
    )
    academic_publication = PublicationRecord(
        schema_version="1",
        record_type="publication_record",
        publication_id="pub_" + "a" * 32,
        work=work,
        source_record=None,
        publication_kind="academic_result_set",
        capabilities=("points",),
        record_set_id="results",
        record_set_revision=1,
        manifest_contract_version="scoreform_academic_result_manifest_v1",
        manifest_path="classes/class_a/modules/scoreform/work/assessment_a/manifest.json",
        manifest_digest_algorithm="sha256",
        manifest_digest="0" * 64,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        academic_work_registration_revision=1,
        supersedes_publication_id=None,
    )
    reader = PublicationReaderSupport(
        "scoreform_academic_result_manifest_v1",
        "scoreform",
        "scoreform_academic_result_reader_v1",
    )
    academic_support = PublicationContractSupport(
        publication_kind="academic_result_set",
        manifest_contract_versions=frozenset(
            {"scoreform_academic_result_manifest_v1", "scoreform_future_manifest_v2"}
        ),
        supported_capabilities=frozenset({"points"}),
        reader_support=(reader,),
    )
    academic_profile = PublicationProducerProfile(
        module_id="scoreform",
        display_name="Synthetic ScoreForm",
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=frozenset({"scoreform_academic_work_v1"}),
        publication_contracts=(academic_support,),
    )
    legacy_profile = replace(
        academic_profile,
        publication_contracts=(replace(academic_support, reader_support=()),),
    )
    require(validate_publication_producer_profile(academic_profile) == academic_profile, "Reader declaration lost in revalidation.")
    require(lookup_publication_reader_support(academic_profile, "academic_result_set", reader.manifest_contract_version) == reader, "Exact declared academic reader lookup failed.")
    require(lookup_publication_reader_support(academic_profile, "academic_result_set", "scoreform_future_manifest_v2") is None, "Partial manifest binding gained an implicit reader.")
    require(lookup_publication_reader_support(legacy_profile, "academic_result_set", reader.manifest_contract_version) is None, "Legacy profile inferred a reader.")
    qualified = evaluate_publication_compatibility(academic_publication, academic_profile, registration)
    previous = evaluate_publication_compatibility(academic_publication, legacy_profile, registration)
    require(qualified == previous and qualified.compatible, "Reader metadata changed academic publication compatibility.")

    intervention_work = ModuleWorkRef("portia", "class_a", "support_a")
    intervention = PublicationRecord(
        schema_version="1",
        record_type="publication_record",
        publication_id="pub_" + "b" * 32,
        work=intervention_work,
        source_record=None,
        publication_kind="intervention_record_set",
        capabilities=("intervention_status",),
        record_set_id="interventions",
        record_set_revision=1,
        manifest_contract_version="portia_intervention_manifest_v1",
        manifest_path="classes/class_a/modules/portia/work/support_a/manifest.json",
        manifest_digest_algorithm="sha256",
        manifest_digest="0" * 64,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        academic_work_registration_revision=None,
        supersedes_publication_id=None,
    )
    intervention_reader = PublicationReaderSupport(
        "portia_intervention_manifest_v1",
        "pds-portia",
        "portia_intervention_reader_v1",
    )
    intervention_support = PublicationContractSupport(
        publication_kind="intervention_record_set",
        manifest_contract_versions=frozenset({"portia_intervention_manifest_v1"}),
        supported_capabilities=frozenset({"intervention_status"}),
        reader_support=(intervention_reader,),
    )
    portia = PublicationProducerProfile(
        module_id="portia",
        display_name="Synthetic Portia",
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=frozenset(),
        publication_contracts=(intervention_support,),
    )
    legacy_portia = replace(portia, publication_contracts=(replace(intervention_support, reader_support=()),))
    require(lookup_publication_reader_support(portia, "intervention_record_set", "portia_intervention_manifest_v1") == intervention_reader, "Intervention reader lookup failed.")
    require(lookup_publication_reader_support(portia, "academic_result_set", "portia_intervention_manifest_v1") is None, "Publication kind boundary violated.")
    require(lookup_publication_reader_support(legacy_portia, "intervention_record_set", "portia_intervention_manifest_v1") is None, "Legacy intervention profile inferred a reader.")
    require(evaluate_publication_compatibility(intervention, portia).compatible, "Valid intervention publication rejected.")
    require(evaluate_publication_compatibility(intervention, legacy_portia) == evaluate_publication_compatibility(intervention, portia), "Reader metadata changed intervention publication compatibility.")

    registry = build_publication_producer_registry(
        explicit_profiles=(portia, academic_profile), discover_installed=False
    )
    require(registry.get("portia") == portia, "Intervention profile lost in registry.")
    require(registry.get("scoreform") == academic_profile, "Academic profile lost in registry.")

    return {
        "status": "pass",
        "core_distribution_version": expected_version,
        "import_source": "installed_wheel_outside_checkout",
        "publication_compatibility_contract_version": CORE_PUBLICATION_COMPATIBILITY_CONTRACT_VERSION,
        "checks": [
            "installed_public_api",
            "exact_manifest_reader_binding",
            "partial_manifest_support",
            "legacy_absent_reader_metadata",
            "academic_publication_invariance",
            "portia_intervention_no_academic_registration",
            "intervention_publication_invariance",
            "reader_lookup_publication_kind_boundary",
            "registry_revalidation",
        ],
        "producer_profiles": "synthetic_contract_fixtures_not_installed_producer_releases",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--forbidden-root", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(
        expected_version=args.expected_version,
        forbidden_root=args.forbidden_root,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
