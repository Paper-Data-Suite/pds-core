"""Synthetic, nonauthoritative producer-contract fixtures for Core boundaries."""

from __future__ import annotations

import builtins
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
import hashlib
import importlib.metadata as importlib_metadata
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from pds_core import registry_services
from pds_core.academic_catalog import (
    AcademicCatalogBuildResult,
    PublicationCatalogQuery,
    query_academic_work_registration_catalog,
    query_publication_catalog,
    rebuild_academic_catalog,
)
from pds_core.academic_work_registrations import AcademicWorkRegistration
from pds_core.class_metadata import ClassMetadata, write_class_metadata_for_class
from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerProfile,
    PublicationProducerProfileError,
    SourceRecordContractSupport,
    build_publication_producer_registry,
    evaluate_publication_compatibility,
)
from pds_core.publication_records import (
    PublicationCapability,
    PublicationKind,
    PublicationRecord,
    PublicationRecordValidationError,
)
from pds_core.publication_storage import verify_publication_manifest
from pds_core.registry_audit import RegistryAuditOptions, audit_academic_registry
from pds_core.registry_services import (
    AcademicWorkRegistrationRequest,
    PublicationManifestRequest,
    get_canonical_publication_record,
    publish_manifest_revision,
    register_academic_work,
)
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef
from pds_core.routes import module_work_dir
from tests.cli.conftest import run_cli


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "producer_contracts"
CLASS_ID = "synthetic_class_2026"
FIXED_TIME = datetime(2026, 8, 1, 12, tzinfo=UTC)
SIBLING_MODULES = frozenset({"scoreform", "quillan", "concord", "portia"})


@dataclass(frozen=True, slots=True)
class ProducerCase:
    module_id: str
    fixture_name: str
    work: ModuleWorkRef
    publication_kind: PublicationKind
    capabilities: tuple[PublicationCapability, ...]
    academic_work_contract_version: str | None
    manifest_contract_version: str
    source_record: ModuleRecordRef | None
    record_set_id: str
    publication_id: str


CASES = (
    ProducerCase(
        "scoreform",
        "scoreform_points_attempts_v1.json",
        ModuleWorkRef("scoreform", CLASS_ID, "fractions_check"),
        "academic_result_set",
        ("multiple_attempts", "points", "question_evidence"),
        "fixture_scoreform_work_v1",
        "fixture_scoreform_result_set_v1",
        None,
        "points_attempts",
        "pub_11111111111111111111111111111111",
    ),
    ProducerCase(
        "quillan",
        "quillan_standards_ratings_v1.json",
        ModuleWorkRef("quillan", CLASS_ID, "position_paper"),
        "academic_result_set",
        ("standards_ratings",),
        "fixture_quillan_work_v1",
        "fixture_quillan_assignment_results_v1",
        ModuleRecordRef("quillan", "assignment", "position_paper", "2"),
        "assignment_ratings",
        "pub_22222222222222222222222222222222",
    ),
    ProducerCase(
        "concord",
        "concord_academic_results_v1.json",
        ModuleWorkRef("concord", CLASS_ID, "synthetic_activity_gamma"),
        "academic_result_set",
        ("criterion_scores", "moderated_scores", "standards_ratings"),
        "fixture_concord_activity_v1",
        "concord_academic_result_manifest_v1",
        ModuleRecordRef(
            "concord", "activity", "synthetic_activity_gamma", "fixture_contract_1"
        ),
        "approved_scores",
        "pub_33333333333333333333333333333333",
    ),
    ProducerCase(
        "portia",
        "portia_intervention_records_v1.json",
        ModuleWorkRef("portia", CLASS_ID, "synthetic_support_process_001"),
        "intervention_record_set",
        ("intervention_history", "intervention_outcomes", "intervention_status"),
        None,
        "fixture_portia_intervention_result_v1",
        None,
        "intervention_history",
        "pub_44444444444444444444444444444444",
    ),
)


def _profile(case: ProducerCase) -> PublicationProducerProfile:
    source_contracts: tuple[SourceRecordContractSupport, ...] = ()
    if case.source_record is not None:
        assert case.source_record.contract_version is not None
        source_contracts = (
            SourceRecordContractSupport(
                case.source_record.record_kind,
                frozenset({case.source_record.contract_version}),
            ),
        )
    return PublicationProducerProfile(
        module_id=case.module_id,
        display_name=case.module_id.title(),
        supported_core_publication_schema_versions=frozenset({"1"}),
        supported_academic_work_contract_versions=(
            frozenset()
            if case.academic_work_contract_version is None
            else frozenset({case.academic_work_contract_version})
        ),
        publication_contracts=(
            PublicationContractSupport(
                publication_kind=case.publication_kind,
                manifest_contract_versions=frozenset(
                    {case.manifest_contract_version}
                ),
                supported_capabilities=frozenset(case.capabilities),
                source_record_contracts=source_contracts,
                allows_missing_source_record=case.source_record is None,
            ),
        ),
    )


PROFILES = tuple(_profile(case) for case in CASES)
PROFILE_BY_MODULE = {profile.module_id: profile for profile in PROFILES}


@dataclass(frozen=True, slots=True)
class PreparedProducerWorkspace:
    root: Path
    registrations: dict[str, AcademicWorkRegistration]
    publications: dict[str, PublicationRecord]
    catalog: AcademicCatalogBuildResult
    protected_bytes: dict[Path, bytes]


def _fixture_bytes(case: ProducerCase) -> bytes:
    return (FIXTURE_DIR / case.fixture_name).read_bytes()


def _manifest_relative_path(case: ProducerCase) -> Path:
    return (
        Path("classes")
        / case.work.class_id
        / "modules"
        / case.work.module_id
        / "work"
        / case.work.work_id
        / "exports"
        / "manifests"
        / case.record_set_id
        / "1.json"
    )


def _manifest_path(root: Path, case: ProducerCase) -> Path:
    return root / _manifest_relative_path(case)


def _registration_request(case: ProducerCase) -> AcademicWorkRegistrationRequest:
    assert case.academic_work_contract_version is not None
    sources = () if case.source_record is None else (case.source_record,)
    return AcademicWorkRegistrationRequest(
        work=case.work,
        producer_contract_version=case.academic_work_contract_version,
        title={
            "scoreform": "Synthetic Fractions Check",
            "quillan": "Synthetic Position Paper",
            "concord": "Synthetic Design Critique",
        }[case.module_id],
        work_kind={
            "scoreform": "assessment",
            "quillan": "assignment",
            "concord": "activity",
        }[case.module_id],
        academic_intent="summative",
        lifecycle="active",
        source_records=sources,
    )


def _prepare_workspace(root: Path) -> PreparedProducerWorkspace:
    root.mkdir(parents=True, exist_ok=True)
    write_class_metadata_for_class(
        root,
        ClassMetadata(CLASS_ID, "2026-2027", FIXED_TIME, FIXED_TIME, {}),
    )
    for case in CASES:
        path = _manifest_path(root, case)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_fixture_bytes(case))

    registrations: dict[str, AcademicWorkRegistration] = {}
    publications: dict[str, PublicationRecord] = {}
    identifiers = iter(case.publication_id for case in CASES)
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name.split(".", 1)[0] in SIBLING_MODULES:
            raise AssertionError(f"sibling implementation import attempted: {name}")
        return original_import(name, globals, locals, fromlist, level)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builtins, "__import__", guarded_import)
        patch.setattr(
            importlib_metadata,
            "entry_points",
            lambda: pytest.fail("installed producer discovery must stay disabled"),
        )
        patch.setattr(registry_services, "_service_time", lambda: FIXED_TIME)
        patch.setattr(registry_services, "_new_publication_id", identifiers.__next__)
        registry = build_publication_producer_registry(
            explicit_profiles=PROFILES,
            discover_installed=False,
        )
        assert tuple(profile.module_id for profile in registry.profiles) == (
            "concord",
            "portia",
            "quillan",
            "scoreform",
        )
        for case in CASES:
            if case.academic_work_contract_version is not None:
                registration = register_academic_work(
                    root, _registration_request(case)
                ).registration
                registrations[case.module_id] = registration
            manifest = _manifest_path(root, case)
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            result = publish_manifest_revision(
                root,
                PublicationManifestRequest(
                    work=case.work,
                    source_record=case.source_record,
                    publication_kind=case.publication_kind,
                    capabilities=case.capabilities,
                    record_set_id=case.record_set_id,
                    record_set_revision=1,
                    manifest_contract_version=case.manifest_contract_version,
                    manifest_path=manifest.relative_to(root).as_posix(),
                    academic_work_registration_revision=(
                        None
                        if case.academic_work_contract_version is None
                        else registrations[case.module_id].registration_revision
                    ),
                    expected_manifest_digest=digest,
                ),
            )
            assert result.disposition == "created"
            assert result.publication.publication_id == case.publication_id
            publications[case.module_id] = result.publication

    assert not any(
        name.split(".", 1)[0] in SIBLING_MODULES for name in sys.modules
    )
    protected_paths = [
        root / "classes" / CLASS_ID / "class.json",
        *(_manifest_path(root, case) for case in CASES),
        *(
            root / "registry" / "publications" / f"{case.publication_id}.json"
            for case in CASES
        ),
    ]
    for registration in registrations.values():
        registration_root = (
            root
            / "registry"
            / "work"
            / registration.work.class_id
            / registration.work.module_id
            / registration.work.work_id
        )
        protected_paths.extend(
            (
                registration_root
                / "revisions"
                / f"{registration.registration_revision}.json",
                registration_root / "current.json",
            )
        )
    protected_bytes = {path: path.read_bytes() for path in protected_paths}
    catalog = rebuild_academic_catalog(root)
    return PreparedProducerWorkspace(
        root, registrations, publications, catalog, protected_bytes
    )


@pytest.fixture(scope="module")
def producer_workspace(
    tmp_path_factory: pytest.TempPathFactory,
) -> PreparedProducerWorkspace:
    return _prepare_workspace(tmp_path_factory.mktemp("producer_contracts"))


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _load_fixture(case: ProducerCase) -> dict[str, Any]:
    text = _fixture_bytes(case).decode("utf-8")

    def reject_constant(value: str) -> None:
        raise ValueError(f"nonstandard numeric value: {value}")

    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=reject_constant,
    )
    assert isinstance(value, dict)
    return value


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        mapping_keys = set(value)
        for item in value.values():
            mapping_keys.update(_all_keys(item))
        return mapping_keys
    if isinstance(value, list):
        list_keys: set[str] = set()
        for item in value:
            list_keys.update(_all_keys(item))
        return list_keys
    return set()


def test_fixture_files_are_deterministic_strict_synthetic_json() -> None:
    for case in CASES:
        raw = _fixture_bytes(case)
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
        assert not raw.startswith(b"\xef\xbb\xbf")
        value = _load_fixture(case)
        expected = (
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        assert raw == expected
        lowered = raw.decode("utf-8").casefold()
        assert "c:\\" not in lowered and "/users/" not in lowered
        assert "@" not in lowered and "password" not in lowered
        assert "student_name" not in lowered and "teacher_name" not in lowered


def test_scoreform_fixture_preserves_unselected_native_attempt_evidence() -> None:
    body = _load_fixture(CASES[0])
    assert body["contract_version"] == CASES[0].manifest_contract_version
    assert body["producer_module_id"] == "scoreform"
    assert body["generated_at"] == "2026-08-01T12:00:00Z"
    assert body["work"] == {
        "class_id": CLASS_ID,
        "module_id": "scoreform",
        "work_id": CASES[0].work.work_id,
    }
    assert body["record_set"] == {"record_set_id": "points_attempts", "revision": 1}
    assessment = body["assessment"]
    assert assessment["assessment_id"] == CASES[0].work.work_id
    assert assessment["question_count"] == 2
    question_ids = [question["question_id"] for question in assessment["questions"]]
    assert question_ids == ["q1", "q2"]
    assert sum(question["points"] for question in assessment["questions"]) == 12
    attempts = body["attempts"]
    assert isinstance(attempts, list) and len(attempts) == 2
    assert [attempt["attempt_number"] for attempt in attempts] == [2, 3]
    assert all(attempt["attempt_number"] != body["record_set"]["revision"] for attempt in attempts)
    assert len({attempt["attempt_id"] for attempt in attempts}) == 2
    assert len({attempt["issuance_id"] for attempt in attempts}) == 2
    assert len({attempt["subject_id"] for attempt in attempts}) == 1
    assert [attempt["points_earned"] for attempt in attempts] == [7, 10]
    assert all(attempt["total_points"] == 12 for attempt in attempts)
    assert all(
        [response["question_id"] for response in attempt["responses"]] == question_ids
        for attempt in attempts
    )
    assert all(
        response["response"] and isinstance(response["correct"], bool)
        for attempt in attempts
        for response in attempt["responses"]
    )
    assert all(
        "evidence" in response
        for attempt in attempts
        for response in attempt["responses"]
    )
    keys = _all_keys(body)
    assert keys.isdisjoint(
        {
            "course_grade",
            "grade",
            "grade_attempt",
            "letter_grade",
            "mastery",
            "official_attempt",
            "percentage",
            "proficiency",
            "selected_attempt",
        }
    )


def test_quillan_fixture_preserves_local_scale_and_nonnumeric_missing_states() -> None:
    body = _load_fixture(CASES[1])
    case = CASES[1]
    assert body["producer_module_id"] == "quillan"
    assert body["generated_at"] == "2026-08-01T12:00:00Z"
    assert body["work"] == {
        "class_id": CLASS_ID,
        "module_id": "quillan",
        "work_id": "position_paper",
    }
    assert body["assignment"]["assignment_id"] == case.work.work_id
    assert body["assignment"]["standards_profile_id"] == "synthetic_writing_profile"
    assert body["assignment"]["focus_standards"] == [
        "synthetic_standard_argument",
        "synthetic_standard_evidence",
    ]
    assert case.source_record == ModuleRecordRef(
        "quillan", "assignment", "position_paper", "2"
    )
    scale = body["assignment_local_rating_scale"]
    assert scale["scale_id"] == "synthetic_assignment_scale"
    assert scale["scale_revision"] == 3
    reviews = body["reviews"]
    assert len(reviews) == 3
    rated = next(review for review in reviews if review["subject_id"].endswith("rated"))
    missing = next(review for review in reviews if review["subject_id"].endswith("missing"))
    returned = next(review for review in reviews if review["subject_id"].endswith("returned"))
    assert all("rating_level_id" in rating for rating in rated["overall_focus_standard_ratings"])
    missing_rows = missing["overall_focus_standard_ratings"]
    assert sum(row.get("state") == "missing" for row in missing_rows) == 1
    assert not missing["returned_without_full_review"]
    returned_rows = returned["overall_focus_standard_ratings"]
    assert returned["returned_without_full_review"]
    assert returned["review_state"] == "returned_without_full_review"
    assert {rating["state"] for rating in returned_rows} == {"not_reviewed"}
    assert all("rating_level_id" not in rating for rating in returned_rows)
    assert all(
        rating["scale_id"] == scale["scale_id"]
        for review in reviews
        for rating in review["overall_focus_standard_ratings"]
    )
    assert _all_keys(body).isdisjoint({"percentage", "grade"})


def test_concord_fixture_preserves_score_kinds_dispositions_and_moderation() -> None:
    body = _load_fixture(CASES[2])
    case = CASES[2]
    assert body["manifest_contract_version"] == "concord_academic_result_manifest_v1"
    assert body["producer_module_id"] == "concord"
    assert body["generated_at"] == "2026-08-01T12:00:00Z"
    assert body["record_set_id"] == case.record_set_id
    assert body["record_set_revision"] == 1
    assert body["work"] == {
        "class_id": CLASS_ID,
        "module_id": "concord",
        "work_id": "synthetic_activity_gamma",
    }
    assert body["source_activity"] == {
        "contract_version": "fixture_contract_1",
        "module_id": "concord",
        "record_id": "synthetic_activity_gamma",
        "record_kind": "activity",
    }
    activity = body["activity"]
    assert activity["activity_id"] == case.work.work_id
    assert activity["class_id"] == CLASS_ID
    assert activity["title"] == "Synthetic Design Critique"
    assert activity["scoring_orientation"] == "mixed"
    assert activity["standards_profile_id"] == "synthetic_concord_profile"
    assert activity["focus_standard_ids"] == ["synthetic_standard_reasoning"]
    criteria = {row["criterion_kind"]: row for row in body["criteria"]}
    assert criteria["standard_backed"]["standard_id"] == "synthetic_standard_reasoning"
    assert "standard_id" not in criteria["local"]
    scale = body["scoring_scales"][0]
    assert (scale["scale_lineage_id"], scale["revision"], scale["scale_type"]) == (
        "synthetic_concord_scale",
        4,
        "ordinal",
    )
    levels = scale["levels"]
    assert [level["order"] for level in levels] == [1, 2, 3, 4]
    scale_values = {level["machine_value"] for level in levels}
    assert all(level["display_label"] and level["description"] for level in levels)
    scores = body["score_records"]
    standard = next(row for row in scores if row["score_kind"] == "standard_backed" and row["current_status"] == "current")
    local = next(
        row
        for row in scores
        if row["score_kind"] == "local" and row["disposition"] == "scored"
    )
    non_score = next(row for row in scores if row["disposition"] != "scored")
    assert standard["standard_id"] == "synthetic_standard_reasoning"
    assert standard["standard_id"] == criteria["standard_backed"]["standard_id"]
    assert standard["standard_id"] in activity["focus_standard_ids"]
    assert "standard_id" not in local
    assert all(
        row["scoring_scale_id"] == scale["scoring_scale_id"]
        and row["scoring_scale_revision"] == scale["revision"]
        for row in scores
    )
    assert all(row["value"] in scale_values for row in scores if row["disposition"] == "scored")
    assert "value" not in non_score
    assert non_score["disposition"] == "insufficient_evidence"
    assert non_score["disposition"] not in scale_values
    assert non_score["target_reference"] == {"target_id": "synthetic_group_target", "target_kind": "group"}
    assert {row["target_kind"] for row in body["targets"]} == {"individual", "group"}
    assert len({row["target_id"] for row in body["targets"]}) == 2
    assert {row["current_status"] for row in scores} == {"current", "superseded"}
    old = next(row for row in scores if row["current_status"] == "superseded")
    assert old["superseded_by_score_record_id"] == standard["score_record_id"]
    assert standard["supersedes_score_record_id"] == old["score_record_id"]
    evidence_link = body["score_evidence_links"][0]
    assert evidence_link["link_id"]
    assert evidence_link["score_record_id"] in {
        row["score_record_id"] for row in scores
    }
    assert set(evidence_link["evidence_reference"]) == {
        "contract_version",
        "module_id",
        "record_id",
        "record_kind",
    }
    assert evidence_link["relation"] == "supports"
    assert evidence_link["position"] == 1
    assert evidence_link["status"] == "active"
    moderation = body["moderation"][0]
    assert moderation["moderation_id"]
    assert moderation["moderation_revision"] == 2
    assert moderation["completion_state"] == "complete"
    assert moderation["approval_state"] == "approved"
    assert moderation["responsible_role"] == "teacher"
    assert moderation["qualification_state"] == "permitted_for_publication"
    assert set(moderation["score_record_ids"]) == {
        row["score_record_id"] for row in scores
    }
    assert all(row["moderation_complete"] for row in scores)
    provenance = body["publication_projection_provenance"]
    assert provenance == {
        "current_and_superseded_history_policy": "include_both",
        "fixture_generator": "pds_core_synthetic_fixture",
        "included_score_scope": "teacher_approved_activity_scores",
        "projected_at": "2026-08-01T12:00:00Z",
        "source_activity_contract_version": "fixture_contract_1",
        "synthetic_fixture": True,
    }
    assert "grade" not in _all_keys(body)


def test_portia_fixture_preserves_nonacademic_intervention_and_typed_reference() -> None:
    body = _load_fixture(CASES[3])
    assert body["producer_module_id"] == "portia"
    assert body["generated_at"] == "2026-08-01T12:00:00Z"
    assert body["work"] == {
        "class_id": CLASS_ID,
        "module_id": "portia",
        "work_id": "synthetic_support_process_001",
    }
    assert body["record_set"] == {"record_set_id": "intervention_history", "revision": 1}
    assert len(body["implementation_history"]) == 2
    assert body["implementation_status"] == "active"
    assert body["follow_up"]["state"] == "scheduled"
    assert body["outcome"]["state"] == "continue_and_review"
    reference = body["related_records"][0]
    assert set(reference) == {"record_ref", "work_ref"}
    assert set(reference["work_ref"]) == {"module_id", "class_id", "work_id"}
    assert set(reference["record_ref"]) == {
        "module_id",
        "record_kind",
        "record_id",
        "contract_version",
    }
    assert (
        reference["work_ref"]["module_id"]
        == reference["record_ref"]["module_id"]
    )
    assert reference == {
        "record_ref": {
            "contract_version": "fixture_related_record_v1",
            "module_id": "fixture_source",
            "record_id": "synthetic_record_001",
            "record_kind": "observation",
        },
        "work_ref": {
            "class_id": CLASS_ID,
            "module_id": "fixture_source",
            "work_id": "synthetic_context_work",
        },
    }
    assert "contents" not in reference
    assert _all_keys(body).isdisjoint(
        {
            "academic_work_registration_revision",
            "grade",
            "points",
            "score",
            "standards_rating",
        }
    )


def test_profiles_match_exact_contract_matrix_and_remain_metadata_only() -> None:
    registry = build_publication_producer_registry(
        explicit_profiles=PROFILES, discover_installed=False
    )
    assert len(registry.profiles) == 4
    for case in CASES:
        profile = registry.get(case.module_id)
        assert profile is not None
        expected_versions = (
            frozenset()
            if case.academic_work_contract_version is None
            else frozenset({case.academic_work_contract_version})
        )
        assert profile.supported_academic_work_contract_versions == expected_versions
        support = profile.publication_contracts[0]
        assert support.publication_kind == case.publication_kind
        assert support.manifest_contract_versions == frozenset(
            {case.manifest_contract_version}
        )
        assert support.supported_capabilities == frozenset(case.capabilities)
    assert {field.name for field in fields(PublicationProducerProfile)} == {
        "module_id",
        "display_name",
        "supported_core_publication_schema_versions",
        "supported_academic_work_contract_versions",
        "publication_contracts",
    }


def test_shared_capability_labels_do_not_equate_producer_contracts(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    quillan = producer_workspace.publications["quillan"]
    concord = producer_workspace.publications["concord"]
    assert "standards_ratings" in quillan.capabilities
    assert "standards_ratings" in concord.capabilities
    assert quillan.manifest_contract_version != concord.manifest_contract_version
    assert _fixture_bytes(CASES[1]) != _fixture_bytes(CASES[2])
    swapped = replace(
        quillan, manifest_contract_version=concord.manifest_contract_version
    )
    result = evaluate_publication_compatibility(
        swapped,
        PROFILE_BY_MODULE["quillan"],
        producer_workspace.registrations["quillan"],
    )
    assert "contracts.manifest_version_incompatible" in result.codes


def test_end_to_end_pipeline_publishes_exact_manifests_and_retrieves_envelopes(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    prepared = producer_workspace
    assert set(prepared.registrations) == {"scoreform", "quillan", "concord"}
    assert len(prepared.publications) == 4 and "portia" not in prepared.registrations
    for case in CASES:
        publication = prepared.publications[case.module_id]
        registration = prepared.registrations.get(case.module_id)
        assert verify_publication_manifest(prepared.root, publication) == _manifest_path(
            prepared.root, case
        )
        assert publication.manifest_digest == hashlib.sha256(
            _fixture_bytes(case)
        ).hexdigest()
        assert publication.work == case.work
        assert publication.source_record == case.source_record
        assert publication.publication_kind == case.publication_kind
        assert publication.capabilities == tuple(sorted(case.capabilities))
        assert publication.record_set_id == case.record_set_id
        assert publication.record_set_revision == 1
        expected_relative = _manifest_relative_path(case)
        assert publication.manifest_path == expected_relative.as_posix()
        assert Path(publication.manifest_path).parts[-4:-2] == (
            "exports",
            "manifests",
        )
        assert Path(publication.manifest_path).parent.name == case.record_set_id
        assert Path(publication.manifest_path).name == "1.json"
        assert "latest" not in Path(publication.manifest_path).parts
        assert Path(publication.manifest_path).name != case.fixture_name
        assert _manifest_path(prepared.root, case).is_relative_to(
            module_work_dir(prepared.root, case.work)
        )
        assert _manifest_path(prepared.root, case).read_bytes() == _fixture_bytes(case)
        assert publication.manifest_contract_version == case.manifest_contract_version
        assert publication.academic_work_registration_revision == (
            None if registration is None else registration.registration_revision
        )
        assert publication.supersedes_publication_id is None
        compatibility = evaluate_publication_compatibility(
            publication, PROFILE_BY_MODULE[case.module_id], registration
        )
        assert compatibility.compatible and compatibility.codes == ()
        assert (
            get_canonical_publication_record(prepared.root, publication.publication_id)
            == publication
        )


def test_fixture_and_core_identities_are_exactly_coherent(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    prepared = producer_workspace
    for case in CASES:
        body = _load_fixture(case)
        fixture_work = body["work"]
        assert fixture_work == {
            "class_id": case.work.class_id,
            "module_id": case.work.module_id,
            "work_id": case.work.work_id,
        }
        publication = prepared.publications[case.module_id]
        assert publication.work == case.work
        if case.module_id in {"scoreform", "quillan", "portia"}:
            assert body["record_set"] == {
                "record_set_id": publication.record_set_id,
                "revision": publication.record_set_revision,
            }
        else:
            assert body["record_set_id"] == publication.record_set_id
            assert body["record_set_revision"] == publication.record_set_revision
    quillan_case = CASES[1]
    quillan_registration = prepared.registrations["quillan"]
    quillan_publication = prepared.publications["quillan"]
    assert quillan_registration.source_records == (quillan_case.source_record,)
    assert quillan_publication.source_record == quillan_case.source_record
    assert quillan_case.source_record is not None
    assert quillan_case.source_record.record_id == quillan_case.work.work_id
    concord_case = CASES[2]
    concord_body = _load_fixture(concord_case)
    concord_registration = prepared.registrations["concord"]
    assert concord_registration.work == concord_case.work
    assert concord_registration.source_records == (concord_case.source_record,)
    assert prepared.publications["concord"].source_record == concord_case.source_record
    assert concord_body["source_activity"]["record_id"] == concord_case.work.work_id
    assert concord_body["activity"]["activity_id"] == concord_case.work.work_id
    assert "portia" not in prepared.registrations
    assert prepared.publications["portia"].academic_work_registration_revision is None
    assert prepared.publications["portia"].source_record is None


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.module_id)
def test_profiles_reject_unsupported_manifest_contracts(
    producer_workspace: PreparedProducerWorkspace, case: ProducerCase
) -> None:
    publication = producer_workspace.publications[case.module_id]
    registration = producer_workspace.registrations.get(case.module_id)
    result = evaluate_publication_compatibility(
        replace(publication, manifest_contract_version="unsupported_fixture_v9"),
        PROFILE_BY_MODULE[case.module_id],
        registration,
    )
    assert "contracts.manifest_version_incompatible" in result.codes


@pytest.mark.parametrize(
    ("module_id", "unsupported_capability"),
    (
        ("scoreform", "standards_ratings"),
        ("scoreform", "criterion_scores"),
        ("quillan", "points"),
        ("quillan", "multiple_attempts"),
        ("concord", "points"),
    ),
)
def test_academic_profiles_require_capability_subsets(
    producer_workspace: PreparedProducerWorkspace,
    module_id: str,
    unsupported_capability: PublicationCapability,
) -> None:
    publication = producer_workspace.publications[module_id]
    registration = producer_workspace.registrations[module_id]
    result = evaluate_publication_compatibility(
        replace(
            publication,
            capabilities=tuple(sorted((*publication.capabilities, unsupported_capability))),
        ),
        PROFILE_BY_MODULE[module_id],
        registration,
    )
    assert "contracts.capability_incompatible" in result.codes


@pytest.mark.parametrize("module_id", ("scoreform", "quillan", "concord"))
def test_academic_profiles_reject_intervention_publications(
    producer_workspace: PreparedProducerWorkspace, module_id: str
) -> None:
    publication = producer_workspace.publications[module_id]
    incompatible = replace(
        publication,
        academic_work_registration_revision=None,
        capabilities=("intervention_status",),
        publication_kind="intervention_record_set",
        source_record=None,
    )
    result = evaluate_publication_compatibility(
        incompatible, PROFILE_BY_MODULE[module_id]
    )
    assert "contracts.publication_kind_incompatible" in result.codes


def test_source_record_policies_are_enforced(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    publications = producer_workspace.publications
    registrations = producer_workspace.registrations
    scoreform = publications["scoreform"]
    forbidden_source = replace(
        scoreform,
        source_record=ModuleRecordRef(
            "scoreform", "assignment", "synthetic_assignment", "1"
        ),
    )
    assert "contracts.source_record_kind_incompatible" in evaluate_publication_compatibility(
        forbidden_source, PROFILE_BY_MODULE["scoreform"], registrations["scoreform"]
    ).codes
    for module_id, wrong_kind, wrong_version in (
        ("quillan", "rating", "1"),
        ("concord", "result", "wrong_contract"),
    ):
        publication = publications[module_id]
        profile = PROFILE_BY_MODULE[module_id]
        registration = registrations[module_id]
        assert "contracts.source_record_missing_incompatible" in evaluate_publication_compatibility(
            replace(publication, source_record=None), profile, registration
        ).codes
        wrong = replace(
            publication,
            source_record=ModuleRecordRef(
                module_id, wrong_kind, "synthetic_wrong_source", wrong_version
            ),
        )
        assert "contracts.source_record_kind_incompatible" in evaluate_publication_compatibility(
            wrong, profile, registration
        ).codes
        assert publication.source_record is not None
        wrong_contract = replace(
            publication,
            source_record=replace(
                publication.source_record, contract_version="unsupported_contract"
            ),
        )
        assert "contracts.source_record_version_incompatible" in evaluate_publication_compatibility(
            wrong_contract, profile, registration
        ).codes
        with pytest.raises(
            PublicationRecordValidationError,
            match="source_record.module_id must match work.module_id",
        ):
            replace(
                publication,
                source_record=replace(
                    publication.source_record, module_id="other_module"
                ),
            )


def test_quillan_source_contract_negative_matrix(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    publication = producer_workspace.publications["quillan"]
    registration = producer_workspace.registrations["quillan"]
    profile = PROFILE_BY_MODULE["quillan"]
    assert "contracts.source_record_missing_incompatible" in evaluate_publication_compatibility(
        replace(publication, source_record=None), profile, registration
    ).codes
    wrong_kind = replace(
        publication,
        source_record=ModuleRecordRef("quillan", "rating", "position_paper", "2"),
    )
    assert "contracts.source_record_kind_incompatible" in evaluate_publication_compatibility(
        wrong_kind, profile, registration
    ).codes
    for version in ("1", "unsupported_assignment_v9"):
        wrong_version = replace(
            publication,
            source_record=ModuleRecordRef(
                "quillan", "assignment", "position_paper", version
            ),
        )
        assert "contracts.source_record_version_incompatible" in evaluate_publication_compatibility(
            wrong_version, profile, registration
        ).codes
    other_work = replace(publication.work, module_id="other_module")
    other_source = ModuleRecordRef(
        "other_module", "assignment", "position_paper", "2"
    )
    other_publication = replace(
        publication,
        manifest_path=publication.manifest_path.replace(
            "/modules/quillan/", "/modules/other_module/"
        ),
        source_record=other_source,
        work=other_work,
    )
    other_registration = replace(
        registration,
        work=other_work,
        source_records=(other_source,),
    )
    result = evaluate_publication_compatibility(
        other_publication, profile, other_registration
    )
    assert "contracts.profile_module_mismatch" in result.codes
    assert "contracts.source_record_kind_incompatible" in result.codes


@pytest.mark.parametrize(
    "capability", ("points", "standards_ratings", "criterion_scores")
)
def test_portia_rejects_academic_publications_and_capabilities(
    producer_workspace: PreparedProducerWorkspace,
    capability: PublicationCapability,
) -> None:
    portia = producer_workspace.publications["portia"]
    fabricated_registration = replace(
        producer_workspace.registrations["scoreform"], work=portia.work
    )
    academic = replace(
        portia,
        academic_work_registration_revision=fabricated_registration.registration_revision,
        capabilities=(capability,),
        publication_kind="academic_result_set",
    )
    result = evaluate_publication_compatibility(
        academic, PROFILE_BY_MODULE["portia"], fabricated_registration
    )
    assert "contracts.publication_kind_incompatible" in result.codes
    assert "contracts.registration_version_incompatible" in result.codes


def test_profile_module_registration_and_portia_boundaries_are_enforced(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    publications = producer_workspace.publications
    registrations = producer_workspace.registrations
    scoreform = publications["scoreform"]
    mismatch = evaluate_publication_compatibility(
        scoreform, PROFILE_BY_MODULE["quillan"], registrations["scoreform"]
    )
    assert "contracts.profile_module_mismatch" in mismatch.codes
    for module_id in ("scoreform", "quillan", "concord"):
        publication = publications[module_id]
        registration = replace(
            registrations[module_id], producer_contract_version="unsupported_work_v9"
        )
        result = evaluate_publication_compatibility(
            publication, PROFILE_BY_MODULE[module_id], registration
        )
        assert "contracts.registration_version_incompatible" in result.codes
    portia = publications["portia"]
    assert evaluate_publication_compatibility(
        portia, PROFILE_BY_MODULE["portia"]
    ).compatible
    assert PROFILE_BY_MODULE[
        "portia"
    ].supported_academic_work_contract_versions == frozenset()
    academic_against_portia = evaluate_publication_compatibility(
        scoreform, PROFILE_BY_MODULE["portia"], registrations["scoreform"]
    )
    assert "contracts.publication_kind_incompatible" in academic_against_portia.codes
    assert set(portia.capabilities).isdisjoint(
        {"points", "standards_ratings", "criterion_scores"}
    )
    fabricated_registration = replace(registrations["scoreform"], work=portia.work)
    with pytest.raises(PublicationProducerProfileError):
        evaluate_publication_compatibility(
            portia, PROFILE_BY_MODULE["portia"], fabricated_registration
        )


def test_catalog_rebuild_and_queries_preserve_only_shared_discovery_metadata(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    prepared = producer_workspace
    assert prepared.catalog.metadata.registration_revision_count == 3
    assert prepared.catalog.metadata.publication_count == 4
    registrations = query_academic_work_registration_catalog(prepared.root)
    assert {row.module_id for row in registrations} == {
        "scoreform",
        "quillan",
        "concord",
    }
    rows = query_publication_catalog(prepared.root)
    assert [row.publication_id for row in rows] == [case.publication_id for case in CASES]
    assert {row.module_id for row in rows} == {case.module_id for case in CASES}
    assert {
        row.module_id
        for row in query_publication_catalog(
            prepared.root,
            PublicationCatalogQuery(publication_kind="academic_result_set"),
        )
    } == {"scoreform", "quillan", "concord"}
    assert [
        row.module_id
        for row in query_publication_catalog(
            prepared.root,
            PublicationCatalogQuery(publication_kind="intervention_record_set"),
        )
    ] == ["portia"]
    for case in CASES:
        assert [
            row.module_id
            for row in query_publication_catalog(
                prepared.root, PublicationCatalogQuery(module_id=case.module_id)
            )
        ] == [case.module_id]
        for capability in case.capabilities:
            expected_modules = {
                other.module_id for other in CASES if capability in other.capabilities
            }
            actual_modules = {
                row.module_id
                for row in query_publication_catalog(
                    prepared.root,
                    PublicationCatalogQuery(required_capabilities=(capability,)),
                )
            }
            assert actual_modules == expected_modules
    assert [
        row.module_id
        for row in query_publication_catalog(
            prepared.root, PublicationCatalogQuery(source_contract_version="2")
        )
    ] == ["quillan"]
    catalog_bytes = prepared.catalog.catalog_path.read_bytes()
    for prohibited in (
        b"synthetic_attempt_001",
        b"returned_without_full_review",
        b"teacher_approved",
        b"continue_and_review",
    ):
        assert prohibited not in catalog_bytes


def test_complete_audit_uses_explicit_profiles_and_is_healthy(
    producer_workspace: PreparedProducerWorkspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        importlib_metadata,
        "entry_points",
        lambda: pytest.fail("audit must not discover installed producer profiles"),
    )
    report = audit_academic_registry(
        producer_workspace.root,
        options=RegistryAuditOptions(
            require_catalog=True,
            require_producer_profiles=True,
            discover_installed_producer_profiles=False,
        ),
        producer_profiles=PROFILES,
    )
    assert report.ok and report.canonical_valid
    assert report.manifests_valid is True
    assert report.contracts_compatible is True
    assert report.catalog_ready is True
    assert report.counts.registration_works == 3
    assert report.counts.publication_records == 4
    assert report.counts.verified_manifests == 4
    assert not report.findings


def test_cli_json_lists_four_envelopes_without_manifest_body_data(
    producer_workspace: PreparedProducerWorkspace,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, output, error = run_cli(
        producer_workspace.root,
        "academic",
        "registry",
        "list",
        "publications",
        "--format",
        "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    rows = payload["data"]["rows"]
    assert code == 0 and error == "" and len(rows) == 4
    assert {row["module_id"] for row in rows} == {case.module_id for case in CASES}
    assert {row["publication_kind"] for row in rows} == {
        "academic_result_set",
        "intervention_record_set",
    }
    assert {tuple(row["capabilities"]) for row in rows} == {
        tuple(sorted(case.capabilities)) for case in CASES
    }
    for prohibited in (
        "synthetic_attempt_001",
        "points_earned",
        "returned_without_full_review",
        "teacher_approved",
        "continue_and_review",
    ):
        assert prohibited not in output


def test_read_workflow_does_not_mutate_fixtures_manifests_or_canonical_records(
    producer_workspace: PreparedProducerWorkspace,
) -> None:
    prepared = producer_workspace
    source_before = {case.fixture_name: _fixture_bytes(case) for case in CASES}
    for case in CASES:
        publication = prepared.publications[case.module_id]
        registration = prepared.registrations.get(case.module_id)
        verify_publication_manifest(prepared.root, publication)
        evaluate_publication_compatibility(
            publication, PROFILE_BY_MODULE[case.module_id], registration
        )
        get_canonical_publication_record(prepared.root, publication.publication_id)
    query_publication_catalog(prepared.root)
    audit_academic_registry(
        prepared.root,
        options=RegistryAuditOptions(
            require_catalog=True,
            require_producer_profiles=True,
            discover_installed_producer_profiles=False,
        ),
        producer_profiles=PROFILES,
    )
    assert source_before == {
        case.fixture_name: _fixture_bytes(case) for case in CASES
    }
    assert prepared.protected_bytes == {
        path: path.read_bytes() for path in prepared.protected_bytes
    }
