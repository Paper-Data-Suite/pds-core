from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
import json

import pytest

from pds_core.academic_work_registrations import (
    ACADEMIC_WORK_INTENTS,
    ACADEMIC_WORK_REGISTRATION_LIFECYCLES,
    AcademicWorkRegistration,
    AcademicWorkRegistrationValidationError,
    academic_work_registration_from_dict,
    academic_work_registration_to_dict,
    is_academic_work_intent,
    is_academic_work_registration_lifecycle,
    validate_academic_work_registration_transition,
)
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef


NOW = datetime(2026, 7, 27, 13, tzinfo=timezone.utc)


def registration(**changes: object) -> AcademicWorkRegistration:
    values: dict[str, object] = {
        "schema_version": "1",
        "record_type": "academic_work_registration",
        "work": ModuleWorkRef("quillan", "english10_p2", "essay"),
        "registration_revision": 1,
        "producer_contract_version": "1",
        "title": "Literary Analysis — Résumé",
        "work_kind": "assignment",
        "academic_intent": "summative",
        "lifecycle": "active",
        "created_at": NOW,
        "updated_at": NOW,
        "source_records": [
            ModuleRecordRef("quillan", "assignment", "essay", "1")
        ],
    }
    values.update(changes)
    return AcademicWorkRegistration(**values)  # type: ignore[arg-type]


def test_registration_is_frozen_slotted_hashable_and_defensive() -> None:
    source = [ModuleRecordRef("quillan", "assignment", "essay", "1")]
    value = registration(source_records=source)
    source.clear()
    assert len(value.source_records) == 1
    assert not hasattr(value, "__dict__")
    assert hash(value) == hash(registration())
    with pytest.raises(FrozenInstanceError):
        value.title = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize("intent", sorted(ACADEMIC_WORK_INTENTS))
def test_all_intents(intent: str) -> None:
    assert is_academic_work_intent(intent)
    assert registration(academic_intent=intent).academic_intent == intent


@pytest.mark.parametrize("lifecycle", sorted(ACADEMIC_WORK_REGISTRATION_LIFECYCLES))
def test_all_lifecycles(lifecycle: str) -> None:
    assert is_academic_work_registration_lifecycle(lifecycle)
    assert registration(lifecycle=lifecycle).lifecycle == lifecycle


@pytest.mark.parametrize("value", [None, " Active", "ACTIVE", "unknown"])
def test_vocabulary_predicates_are_exact(value: object) -> None:
    assert not is_academic_work_intent(value)
    assert not is_academic_work_registration_lifecycle(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("registration_revision", 0),
        ("registration_revision", -1),
        ("registration_revision", True),
        ("work_kind", "Assignment"),
        ("work_kind", "bad/path"),
        ("producer_contract_version", " 1"),
        ("title", ""),
        ("title", " title"),
        ("title", "two\nlines"),
        ("created_at", datetime(2026, 1, 1)),
    ],
)
def test_invalid_fields(field: str, value: object) -> None:
    with pytest.raises(AcademicWorkRegistrationValidationError):
        registration(**{field: value})


def test_source_records_are_sorted_and_duplicates_or_mismatch_rejected() -> None:
    a = ModuleRecordRef("quillan", "assignment", "a", None)
    b = ModuleRecordRef("quillan", "assignment", "a", "1")
    assert registration(source_records=[b, a]).source_records == (a, b)
    with pytest.raises(AcademicWorkRegistrationValidationError, match="duplicate"):
        registration(source_records=[a, a])
    with pytest.raises(AcademicWorkRegistrationValidationError, match="module_id"):
        registration(source_records=[ModuleRecordRef("scoreform", "assignment", "a")])


def test_exact_mapping_round_trip_and_fresh_output() -> None:
    value = registration()
    data = academic_work_registration_to_dict(value)
    assert academic_work_registration_from_dict(data) == value
    assert json.loads(json.dumps(data, allow_nan=False))["title"] == value.title
    cast_work = data["work"]
    assert isinstance(cast_work, dict)
    cast_work["work_id"] = "changed"
    assert value.work.work_id == "essay"
    with pytest.raises(AcademicWorkRegistrationValidationError, match="unknown"):
        academic_work_registration_from_dict({**academic_work_registration_to_dict(value), "x": 1})
    incomplete = academic_work_registration_to_dict(value)
    incomplete.pop("title")
    with pytest.raises(AcademicWorkRegistrationValidationError, match="missing"):
        academic_work_registration_from_dict(incomplete)


def test_transition_rules_and_explicit_changes() -> None:
    old = registration()
    new = registration(
        registration_revision=3,
        title="New title",
        work_kind="project",
        academic_intent="formative",
        lifecycle="closed",
        producer_contract_version="2",
        source_records=(),
    )
    assert validate_academic_work_registration_transition(old, new) == new
    for bad in (
        registration(registration_revision=1),
        registration(registration_revision=2, created_at=NOW.replace(hour=12)),
        registration(registration_revision=2, work=ModuleWorkRef("quillan", "other", "essay")),
    ):
        with pytest.raises(AcademicWorkRegistrationValidationError):
            validate_academic_work_registration_transition(old, bad)


def test_boundary_fields_are_absent() -> None:
    names = {item.name for item in fields(AcademicWorkRegistration)}
    assert not names & {
        "academic_period", "grade_category", "weight", "points", "attempts",
        "results", "publication_id", "manifest_path", "manifest_digest",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("producer_contract_version", 1),
        ("work_kind", 1),
        ("title", 1),
        ("title", "a\tb"),
        ("title", "a\0b"),
        ("title", "a\rb"),
        ("title", "a\u2028b"),
        ("title", "a\u2029b"),
        ("updated_at", datetime(2026, 7, 27, 13)),
        ("updated_at", NOW - timedelta(seconds=1)),
        ("work", {"module_id": "quillan", "class_id": "class", "work_id": "essay"}),
        ("source_records", 1),
        ("source_records", "record"),
        ("source_records", b"record"),
        ("source_records", [object()]),
    ],
)
def test_additional_field_validation(field: str, value: object) -> None:
    with pytest.raises(AcademicWorkRegistrationValidationError):
        registration(**{field: value})


def test_invalid_existing_module_record_ref_is_revalidated() -> None:
    invalid = object.__new__(ModuleRecordRef)
    object.__setattr__(invalid, "module_id", "Quillan")
    object.__setattr__(invalid, "record_kind", "assignment")
    object.__setattr__(invalid, "record_id", "essay")
    object.__setattr__(invalid, "contract_version", None)
    with pytest.raises(AcademicWorkRegistrationValidationError, match="source_records"):
        registration(source_records=[invalid])


def test_empty_source_records_are_explicit() -> None:
    value = registration(source_records=[])
    assert value.source_records == ()
    assert academic_work_registration_to_dict(value)["source_records"] == []


def test_documented_dictionary_shape_is_exact_and_not_flattened() -> None:
    value = registration()
    assert academic_work_registration_to_dict(value) == {
        "schema_version": "1",
        "record_type": "academic_work_registration",
        "work": {
            "module_id": "quillan",
            "class_id": "english10_p2",
            "work_id": "essay",
        },
        "registration_revision": 1,
        "producer_contract_version": "1",
        "title": "Literary Analysis — Résumé",
        "work_kind": "assignment",
        "academic_intent": "summative",
        "lifecycle": "active",
        "created_at": "2026-07-27T13:00:00+00:00",
        "updated_at": "2026-07-27T13:00:00+00:00",
        "source_records": [{
            "module_id": "quillan",
            "record_kind": "assignment",
            "record_id": "essay",
            "contract_version": "1",
        }],
    }


@pytest.mark.parametrize("missing", sorted({
    "schema_version", "record_type", "work", "registration_revision",
    "producer_contract_version", "title", "work_kind", "academic_intent",
    "lifecycle", "created_at", "updated_at", "source_records",
}))
def test_mapping_rejects_every_missing_field(missing: str) -> None:
    data = academic_work_registration_to_dict(registration())
    data.pop(missing)
    with pytest.raises(AcademicWorkRegistrationValidationError, match="missing"):
        academic_work_registration_from_dict(data)


@pytest.mark.parametrize("unknown", ["extension", "grade_category", "publication_id"])
def test_mapping_rejects_unknown_fields(unknown: str) -> None:
    data = academic_work_registration_to_dict(registration())
    data[unknown] = "value"
    with pytest.raises(AcademicWorkRegistrationValidationError, match="unknown"):
        academic_work_registration_from_dict(data)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: 1,
        lambda data: {**data, 1: "non-string"},
        lambda data: {**data, "source_records": ()},
        lambda data: {**data, "work": {"module_id": "quillan"}},
        lambda data: {**data, "source_records": [{"module_id": "quillan"}]},
        lambda data: {**data, "registration_revision": True},
        lambda data: {**data, "created_at": "not-a-time"},
        lambda data: {**data, "updated_at": "not-a-time"},
    ],
)
def test_mapping_rejects_malformed_shapes(mutator: object) -> None:
    data = academic_work_registration_to_dict(registration())
    malformed = mutator(data)  # type: ignore[operator]
    with pytest.raises(AcademicWorkRegistrationValidationError):
        academic_work_registration_from_dict(malformed)


@pytest.mark.parametrize(
    "candidate",
    [
        registration(
            registration_revision=2,
            work=ModuleWorkRef("scoreform", "english10_p2", "essay"),
            source_records=(),
        ),
        registration(registration_revision=2, work=ModuleWorkRef("quillan", "different", "essay")),
        registration(registration_revision=2, work=ModuleWorkRef("quillan", "english10_p2", "different")),
        registration(registration_revision=1),
        registration(registration_revision=2, created_at=NOW - timedelta(hours=1)),
        registration(
            registration_revision=2,
            updated_at=NOW + timedelta(minutes=30),
        ),
    ],
)
def test_transition_rejections_are_independent(candidate: AcademicWorkRegistration) -> None:
    if candidate.updated_at > NOW:
        old = registration(updated_at=NOW + timedelta(hours=1))
    else:
        old = registration()
    with pytest.raises(AcademicWorkRegistrationValidationError):
        validate_academic_work_registration_transition(old, candidate)


def test_transition_rejects_decreasing_revision() -> None:
    with pytest.raises(AcademicWorkRegistrationValidationError, match="greater"):
        validate_academic_work_registration_transition(
            registration(registration_revision=2), registration(registration_revision=1)
        )


def test_transition_accepts_all_explicit_metadata_changes_together() -> None:
    source = ModuleRecordRef("quillan", "project", "new_source", None)
    candidate = registration(
        registration_revision=10,
        producer_contract_version="2",
        title="Explicitly Revised",
        work_kind="project",
        academic_intent="reporting_only",
        lifecycle="cancelled",
        updated_at=NOW + timedelta(hours=1),
        source_records=(source,),
    )
    assert validate_academic_work_registration_transition(registration(), candidate) == candidate
