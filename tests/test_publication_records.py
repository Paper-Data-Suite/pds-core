from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from typing import Any, cast

import pytest

from pds_core.publication_records import (
    PUBLICATION_CAPABILITIES,
    PUBLICATION_KINDS,
    PublicationRecord,
    PublicationRecordValidationError,
    PublicationWithdrawal,
    PublicationCapability,
    PublicationKind,
    is_publication_capability,
    is_publication_kind,
    publication_record_from_dict,
    publication_record_to_dict,
    publication_withdrawal_from_dict,
    publication_withdrawal_to_dict,
    validate_publication_manifest_path,
    validate_publication_record_series,
    validate_publication_supersession,
    validate_publication_withdrawal_relationship,
)
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef

NOW = datetime(2026, 7, 27, 14, tzinfo=timezone.utc)
PUB1 = "pub_11111111111111111111111111111111"
PUB2 = "pub_22222222222222222222222222222222"
PUB3 = "pub_33333333333333333333333333333333"


def publication(
    *, publication_id: str = PUB1, revision: int = 1,
    supersedes: str | None = None,
) -> PublicationRecord:
    work = ModuleWorkRef("quillan", "english10_p2", "essay")
    return PublicationRecord(
        schema_version="1",
        record_type="publication_record",
        publication_id=publication_id,
        work=work,
        source_record=ModuleRecordRef(
            "quillan", "assignment_results", "essay", "1"
        ),
        publication_kind="academic_result_set",
        capabilities=("standards_ratings", "points"),
        record_set_id="assignment_results",
        record_set_revision=revision,
        manifest_contract_version="1",
        manifest_path=(
            "classes/english10_p2/modules/quillan/work/essay/"
            f"exports/{revision}.json"
        ),
        manifest_digest_algorithm="sha256",
        manifest_digest="a" * 64,
        published_at=NOW + timedelta(minutes=revision),
        academic_work_registration_revision=1,
        supersedes_publication_id=supersedes,
    )


def test_closed_predicates_are_exact() -> None:
    assert all(is_publication_kind(value) for value in PUBLICATION_KINDS)
    assert all(is_publication_capability(value) for value in PUBLICATION_CAPABILITIES)
    assert not is_publication_kind(" Academic_result_set ")
    assert not is_publication_capability(1)


def test_publication_is_frozen_slotted_and_normalizes_capabilities() -> None:
    value = publication()
    assert value.capabilities == ("points", "standards_ratings")
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.record_set_id = "other"  # type: ignore[misc]
    assert hash(value) == hash(publication())


def forged_work(**changes: object) -> ModuleWorkRef:
    value = object.__new__(ModuleWorkRef)
    fields: dict[str, object] = {
        "module_id": "quillan", "class_id": "english10_p2", "work_id": "essay"
    }
    fields.update(changes)
    for key, item in fields.items():
        object.__setattr__(value, key, item)
    return value


def forged_source(**changes: object) -> ModuleRecordRef:
    value = object.__new__(ModuleRecordRef)
    fields: dict[str, object] = {
        "module_id": "quillan", "record_kind": "results",
        "record_id": "essay", "contract_version": "1",
    }
    fields.update(changes)
    for key, item in fields.items():
        object.__setattr__(value, key, item)
    return value


@pytest.mark.parametrize(
    "change",
    [
        {"work": {"module_id": "quillan"}},
        {"work": forged_work(module_id="Quillan")},
        {"source_record": {"module_id": "quillan"}},
        {"source_record": forged_source(record_kind="bad/kind")},
        {"source_record": ModuleRecordRef("scoreform", "results", "essay", "1")},
    ],
)
def test_nested_reference_validation(change: dict[str, object]) -> None:
    with pytest.raises(PublicationRecordValidationError):
        replace(publication(), **change)  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", sorted(PUBLICATION_KINDS))
def test_all_publication_kinds(kind: str) -> None:
    value = publication()
    if kind == "intervention_record_set":
        value = replace(
            value, publication_kind=cast(PublicationKind, kind), capabilities=(),
            academic_work_registration_revision=None,
        )
    assert value.publication_kind == kind


@pytest.mark.parametrize("capability", sorted(PUBLICATION_CAPABILITIES))
def test_every_capability_and_kind_compatibility(capability: str) -> None:
    value = publication()
    if capability.startswith("intervention_"):
        value = replace(
            value, publication_kind="intervention_record_set",
            capabilities=(cast(PublicationCapability, capability),),
            academic_work_registration_revision=None,
        )
    else:
        value = replace(
            value, capabilities=(cast(PublicationCapability, capability),)
        )
    assert value.capabilities == (capability,)


def test_explicit_empty_capabilities() -> None:
    assert replace(publication(), capabilities=()).capabilities == ()


@pytest.mark.parametrize(
    "capabilities", ["points", b"points", {"points": True}, 1]
)
def test_capabilities_reject_non_collection_iterables(capabilities: object) -> None:
    with pytest.raises(PublicationRecordValidationError):
        replace(publication(), capabilities=capabilities)  # type: ignore[arg-type]


def test_capabilities_reject_duplicates_and_cross_family_values() -> None:
    with pytest.raises(PublicationRecordValidationError):
        replace(publication(), capabilities=("points", "points"))
    with pytest.raises(PublicationRecordValidationError):
        replace(publication(), capabilities=("intervention_status",))
    with pytest.raises(PublicationRecordValidationError):
        replace(
            publication(), publication_kind="intervention_record_set",
            capabilities=("points",), academic_work_registration_revision=None,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"record_set_id": "Results"}, {"record_set_id": "bad/id"},
        {"record_set_id": 1}, {"record_set_revision": 0},
        {"record_set_revision": -1}, {"record_set_revision": 1.0},
        {"record_set_revision": True}, {"manifest_contract_version": 1},
        {"manifest_contract_version": "bad/version"},
        {"manifest_digest_algorithm": "sha-256"},
        {"manifest_digest": "a" * 63}, {"manifest_digest": "A" * 64},
        {"manifest_digest": 1}, {"published_at": datetime(2026, 7, 27)},
        {"academic_work_registration_revision": None},
        {"academic_work_registration_revision": 0},
        {"academic_work_registration_revision": -1},
        {"academic_work_registration_revision": 1.0},
        {"academic_work_registration_revision": True},
        {"supersedes_publication_id": "pub_bad"},
    ],
)
def test_independent_field_contracts(change: dict[str, object]) -> None:
    with pytest.raises(PublicationRecordValidationError):
        replace(publication(), **change)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "change",
    [
        {"publication_id": "pub_A" + "0" * 31},
        {"record_set_revision": True},
        {"manifest_digest": "A" * 64},
        {"manifest_digest_algorithm": "SHA256"},
        {"published_at": datetime(2026, 1, 1)},
        {"supersedes_publication_id": PUB1},
    ],
)
def test_publication_rejects_invalid_core_fields(change: dict[str, object]) -> None:
    with pytest.raises(PublicationRecordValidationError):
        replace(publication(), **change)  # type: ignore[arg-type]


def test_kind_registration_and_capability_boundaries() -> None:
    with pytest.raises(PublicationRecordValidationError):
        replace(
            publication(),
            publication_kind="intervention_record_set",
            academic_work_registration_revision=None,
        )
    intervention = replace(
        publication(),
        publication_kind="intervention_record_set",
        capabilities=("intervention_status",),
        academic_work_registration_revision=None,
    )
    assert intervention.academic_work_registration_revision is None
    with pytest.raises(PublicationRecordValidationError):
        replace(intervention, academic_work_registration_revision=1)


@pytest.mark.parametrize(
    "path",
    [
        "",
        " classes/english10_p2/modules/quillan/work/essay/a.json",
        "classes/english10_p2/modules/quillan/work/essay/a.json ",
        "classes/english10_p2/modules/quillan/work/essay/a\x00.json",
        "/classes/english10_p2/modules/quillan/work/essay/a.json",
        "C:/classes/english10_p2/modules/quillan/work/essay/a.json",
        "//server/share/a.json",
        "classes\\english10_p2\\modules\\quillan\\work\\essay\\a.json",
        "classes/english10_p2/modules/quillan/work/essay/./a.json",
        "classes/english10_p2/modules/quillan/work/essay/../a.json",
        "classes/english10_p2/modules/quillan/work/essay//a.json",
        "classes/english10_p2/modules/quillan/work/essay",
        "registry/publications/a.json",
        "classes/other/modules/quillan/work/essay/a.json",
        "classes/english10_p2/modules/scoreform/work/essay/a.json",
        "classes/english10_p2/modules/quillan/work/other/a.json",
        "classes/english10_p2/modules/quillan/work/essay/a.txt",
    ],
)
def test_manifest_path_rejects_noncanonical_paths(path: str) -> None:
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_manifest_path(publication().work, path)


def test_exact_mapping_round_trip_and_fresh_output() -> None:
    value = publication()
    data = publication_record_to_dict(value)
    assert publication_record_from_dict(data) == value
    assert data["source_record"] == {
        "module_id": "quillan",
        "record_kind": "assignment_results",
        "record_id": "essay",
        "contract_version": "1",
    }
    assert data["capabilities"] == ["points", "standards_ratings"]
    assert data["published_at"] == value.published_at.isoformat()
    assert set(data) == {
        "schema_version", "record_type", "publication_id", "work",
        "source_record", "publication_kind", "capabilities", "record_set_id",
        "record_set_revision", "manifest_contract_version", "manifest_path",
        "manifest_digest_algorithm", "manifest_digest", "published_at",
        "academic_work_registration_revision", "supersedes_publication_id",
    }
    assert json.dumps(data, allow_nan=False)
    cast_capabilities = data["capabilities"]
    assert isinstance(cast_capabilities, list)
    cast_capabilities.append("criterion_scores")
    assert value.capabilities == ("points", "standards_ratings")
    for key in tuple(data):
        incomplete = publication_record_to_dict(value)
        del incomplete[key]
        with pytest.raises(PublicationRecordValidationError):
            publication_record_from_dict(incomplete)


def test_optional_values_are_explicit_null_and_outputs_are_fresh() -> None:
    value = replace(publication(), source_record=None)
    data = publication_record_to_dict(value)
    assert data["source_record"] is None
    assert data["supersedes_publication_id"] is None
    work = data["work"]
    assert isinstance(work, dict)
    work["work_id"] = "changed"
    assert value.work.work_id == "essay"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update({"extension": True}),
        lambda data: data.update({1: "bad"}),
        lambda data: data.update({"work": {"module_id": "quillan"}}),
        lambda data: data.update({"source_record": {"module_id": "quillan"}}),
        lambda data: data.update({"capabilities": ("points",)}),
        lambda data: data.update({"record_set_revision": True}),
        lambda data: data.update({"academic_work_registration_revision": True}),
        lambda data: data.update({"published_at": "not-a-time"}),
        lambda data: data.update({"source_record": 1}),
        lambda data: data.update({"supersedes_publication_id": 1}),
    ],
)
def test_mapping_rejects_invalid_shapes(mutation: object) -> None:
    data = cast(dict[object, object], publication_record_to_dict(publication()))
    cast(Any, mutation)(data)
    with pytest.raises(PublicationRecordValidationError):
        publication_record_from_dict(data)


@pytest.mark.parametrize("data", [None, [], "record", 1])
def test_mapping_requires_object(data: object) -> None:
    with pytest.raises(PublicationRecordValidationError):
        publication_record_from_dict(data)


def test_supersession_and_complete_series() -> None:
    first = publication()
    second = publication(publication_id=PUB2, revision=3, supersedes=PUB1)
    third = publication(publication_id=PUB3, revision=8, supersedes=PUB2)
    assert validate_publication_supersession(first, second) == second
    assert validate_publication_record_series((third, first, second)) == (
        first,
        second,
        third,
    )
    assert validate_publication_record_series(()) == ()
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series(
            (first, second, replace(third, supersedes_publication_id=PUB1))
        )
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series(1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "change",
    [
        {"work": ModuleWorkRef("scoreform", "english10_p2", "essay")},
        {"work": ModuleWorkRef("quillan", "other", "essay")},
        {"work": ModuleWorkRef("quillan", "english10_p2", "other")},
        {"publication_kind": "intervention_record_set",
         "capabilities": (), "academic_work_registration_revision": None},
        {"record_set_id": "other"}, {"record_set_revision": 1},
        {"record_set_revision": 0}, {"supersedes_publication_id": PUB3},
        {"published_at": NOW},
    ],
)
def test_supersession_rejections(change: dict[str, object]) -> None:
    first = publication()
    candidate = publication(publication_id=PUB2, revision=3, supersedes=PUB1)
    if change.get("record_set_revision") == 0:
        change["record_set_revision"] = first.record_set_revision
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_supersession(
            first, replace(candidate, **change)  # type: ignore[arg-type]
        )


def test_series_rejects_structural_failures() -> None:
    first = publication()
    second = publication(publication_id=PUB2, revision=3, supersedes=PUB1)
    third = publication(publication_id=PUB3, revision=5, supersedes=PUB2)
    assert validate_publication_record_series((first,)) == (first,)
    for invalid in ("records", b"records", 1):
        with pytest.raises(PublicationRecordValidationError):
            validate_publication_record_series(invalid)  # type: ignore[arg-type]
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series((first, object()))  # type: ignore[arg-type]
    mixed_values = [
        replace(
            second, work=ModuleWorkRef("quillan", "other", "essay"),
            manifest_path="classes/other/modules/quillan/work/essay/exports/3.json",
        ),
        replace(
            second, publication_kind="intervention_record_set", capabilities=(),
            academic_work_registration_revision=None,
        ),
        replace(second, record_set_id="other"),
    ]
    for mixed in mixed_values:
        with pytest.raises(PublicationRecordValidationError):
            validate_publication_record_series((first, mixed))
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series((first, first))
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series(
            (first, second, replace(third, record_set_revision=3))
        )
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series((first, replace(second, supersedes_publication_id=PUB3)))
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series((first, replace(second, supersedes_publication_id=None)))
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series(
            (first, second, replace(third, supersedes_publication_id=PUB1))
        )
    cycle_a = replace(first, supersedes_publication_id=PUB2)
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_record_series((cycle_a, second))


def test_withdrawal_shape_and_relationship() -> None:
    value = publication()
    withdrawal = PublicationWithdrawal(
        schema_version="1",
        record_type="publication_withdrawal",
        publication_id=PUB1,
        withdrawn_at=value.published_at,
        reason="Producer correction required.",
    )
    assert publication_withdrawal_from_dict(
        publication_withdrawal_to_dict(withdrawal)
    ) == withdrawal
    assert hash(withdrawal) == hash(replace(withdrawal))
    assert not hasattr(withdrawal, "__dict__")
    with pytest.raises(FrozenInstanceError):
        withdrawal.reason = "changed"  # type: ignore[misc]
    assert json.dumps(publication_withdrawal_to_dict(withdrawal), allow_nan=False)
    assert validate_publication_withdrawal_relationship(value, withdrawal) == withdrawal
    with pytest.raises(PublicationRecordValidationError):
        validate_publication_withdrawal_relationship(
            value,
            replace(withdrawal, withdrawn_at=value.published_at - timedelta(seconds=1)),
        )
    with pytest.raises(PublicationRecordValidationError):
        replace(withdrawal, reason="two\nlines")


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2"}, {"record_type": "withdrawal"},
        {"publication_id": "bad"}, {"withdrawn_at": datetime(2026, 7, 27)},
        {"reason": 1}, {"reason": ""}, {"reason": "   "},
        {"reason": " leading"}, {"reason": "trailing "}, {"reason": "a\tb"},
        {"reason": "a\nb"}, {"reason": "a\rb"}, {"reason": "a\x00b"},
        {"reason": "a\u2028b"}, {"reason": "a\u2029b"},
    ],
)
def test_withdrawal_field_validation(change: dict[str, object]) -> None:
    value = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, NOW, "Correction required."
    )
    with pytest.raises(PublicationRecordValidationError):
        replace(value, **change)  # type: ignore[arg-type]


def test_withdrawal_exact_conversion_rejections() -> None:
    value = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, NOW, "Correction required."
    )
    data = publication_withdrawal_to_dict(value)
    assert set(data) == {
        "schema_version", "record_type", "publication_id", "withdrawn_at", "reason"
    }
    assert data["withdrawn_at"] == NOW.isoformat()
    for key in tuple(data):
        missing = dict(data)
        del missing[key]
        with pytest.raises(PublicationRecordValidationError):
            publication_withdrawal_from_dict(missing)
    non_string_key = cast(dict[object, object], dict(data))
    non_string_key[1] = "bad"
    unknown = dict(data)
    unknown["extra"] = 1
    bad_values: tuple[object, ...] = (unknown, non_string_key, [], None)
    for bad in bad_values:
        with pytest.raises(PublicationRecordValidationError):
            publication_withdrawal_from_dict(bad)
