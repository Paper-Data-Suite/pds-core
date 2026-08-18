from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
import json
from typing import Callable

import pytest

from pds_core.grouping_signals import (
    GROUPING_SIGNAL_CONTRACT_NAME,
    GROUPING_SIGNAL_RECORD_TYPE,
    GROUPING_SIGNAL_SCHEMA_VERSION,
    GROUPING_SIGNAL_SOURCE_KINDS,
    GroupingSignalDimension,
    GroupingSignalSet,
    GroupingSignalSource,
    GroupingSignalStudentBand,
    GroupingSignalValidationError,
    grouping_signal_set_from_dict,
    grouping_signal_set_from_json,
    grouping_signal_set_to_dict,
    grouping_signal_set_to_json,
    grouping_signal_set_to_json_bytes,
    is_grouping_signal_source_kind,
    validate_grouping_signal_set,
)

NOW = datetime(2026, 9, 1, 18, 30, tzinfo=UTC)
DIGEST = "a" * 64


def source(**changes: object) -> GroupingSignalSource:
    values: dict[str, object] = {
        "kind": "module_generated",
        "module_id": "meridian",
        "snapshot_id": "academic_snapshot_001",
        "snapshot_digest_algorithm": "sha256",
        "snapshot_digest": DIGEST,
    }
    values.update(changes)
    return GroupingSignalSource(**values)  # type: ignore[arg-type]


def teacher_source(**changes: object) -> GroupingSignalSource:
    values: dict[str, object] = {
        "kind": "teacher_authored",
        "module_id": None,
        "snapshot_id": None,
        "snapshot_digest_algorithm": None,
        "snapshot_digest": None,
    }
    values.update(changes)
    return GroupingSignalSource(**values)  # type: ignore[arg-type]


def signal(**changes: object) -> GroupingSignalSet:
    values: dict[str, object] = {
        "schema_version": "1",
        "record_type": "grouping_signal_set",
        "signal_set_id": "planning_signal_001",
        "class_id": "english10_p2",
        "created_at": NOW,
        "source": source(),
        "dimensions": (
            GroupingSignalDimension("reading_analysis", 4),
            GroupingSignalDimension("writing_claim_evidence", 3),
        ),
        "student_bands": (
            GroupingSignalStudentBand("student_001", "reading_analysis", 2),
            GroupingSignalStudentBand("student_002", "reading_analysis", 4),
            GroupingSignalStudentBand("student_001", "writing_claim_evidence", 3),
        ),
    }
    values.update(changes)
    return GroupingSignalSet(**values)  # type: ignore[arg-type]


def canonical_dict() -> dict[str, object]:
    return grouping_signal_set_to_dict(signal())


def test_public_contract_constants_are_exact() -> None:
    assert GROUPING_SIGNAL_CONTRACT_NAME == "grouping_signal_set_v1"
    assert GROUPING_SIGNAL_SCHEMA_VERSION == "1"
    assert GROUPING_SIGNAL_RECORD_TYPE == "grouping_signal_set"
    assert GROUPING_SIGNAL_SOURCE_KINDS == frozenset(
        {"teacher_authored", "module_generated"}
    )


@pytest.mark.parametrize("kind", sorted(GROUPING_SIGNAL_SOURCE_KINDS))
def test_source_kind_predicate_accepts_exact_values(kind: str) -> None:
    assert is_grouping_signal_source_kind(kind)


@pytest.mark.parametrize("kind", [None, "Teacher_Authored", "unknown", 1])
def test_source_kind_predicate_rejects_other_values(kind: object) -> None:
    assert not is_grouping_signal_source_kind(kind)


def test_models_are_frozen_slotted_and_hashable() -> None:
    value = signal()
    assert not hasattr(value, "__dict__")
    assert hash(value) == hash(signal())
    with pytest.raises(FrozenInstanceError):
        value.class_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.source.module_id = "changed"  # type: ignore[misc]


def test_programmatic_construction_defensively_normalizes_collections() -> None:
    dimensions = [
        GroupingSignalDimension("writing_claim_evidence", 3),
        GroupingSignalDimension("reading_analysis", 4),
    ]
    bands = [
        GroupingSignalStudentBand("student_001", "writing_claim_evidence", 3),
        GroupingSignalStudentBand("student_002", "reading_analysis", 4),
        GroupingSignalStudentBand("student_001", "reading_analysis", 2),
    ]
    value = signal(dimensions=dimensions, student_bands=bands)
    dimensions.clear()
    bands.clear()
    assert tuple(item.dimension_id for item in value.dimensions) == (
        "reading_analysis",
        "writing_claim_evidence",
    )
    assert tuple(
        (item.dimension_id, item.student_id) for item in value.student_bands
    ) == (
        ("reading_analysis", "student_001"),
        ("reading_analysis", "student_002"),
        ("writing_claim_evidence", "student_001"),
    )


def test_equivalent_runtime_order_and_timezone_produce_same_canonical_bytes() -> None:
    offset = timezone(timedelta(hours=-4))
    local_time = datetime(2026, 9, 1, 14, 30, tzinfo=offset)
    reversed_value = signal(
        created_at=local_time,
        dimensions=tuple(reversed(signal().dimensions)),
        student_bands=tuple(reversed(signal().student_bands)),
    )
    assert reversed_value == signal()
    assert grouping_signal_set_to_json_bytes(reversed_value) == (
        grouping_signal_set_to_json_bytes(signal())
    )


def test_teacher_authored_all_null_and_bound_provenance_are_valid() -> None:
    assert teacher_source().snapshot_id is None
    bound = teacher_source(
        snapshot_id="teacher_csv_001",
        snapshot_digest_algorithm="sha256",
        snapshot_digest="b" * 64,
    )
    assert bound.snapshot_id == "teacher_csv_001"


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "unknown"},
        {"module_id": "Meridian"},
        {"module_id": None},
        {"snapshot_id": None},
        {"snapshot_digest_algorithm": None},
        {"snapshot_digest": None},
        {"snapshot_digest_algorithm": "SHA256"},
        {"snapshot_digest": "A" * 64},
        {"snapshot_digest": "a" * 63},
        {"snapshot_digest": "g" * 64},
    ],
)
def test_invalid_module_generated_provenance_rejected(
    changes: dict[str, object],
) -> None:
    with pytest.raises(GroupingSignalValidationError):
        source(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"module_id": "meridian"},
        {"snapshot_id": "csv_1"},
        {"snapshot_digest_algorithm": "sha256"},
        {"snapshot_digest": DIGEST},
        {
            "snapshot_id": "csv_1",
            "snapshot_digest_algorithm": "sha256",
            "snapshot_digest": None,
        },
    ],
)
def test_invalid_teacher_authored_provenance_rejected(
    changes: dict[str, object],
) -> None:
    with pytest.raises(GroupingSignalValidationError):
        teacher_source(**changes)


@pytest.mark.parametrize(
    ("factory", "args"),
    [
        (GroupingSignalDimension, ("", 4)),
        (GroupingSignalDimension, (" bad", 4)),
        (GroupingSignalDimension, ("bad/path", 4)),
        (GroupingSignalDimension, ("good", 1)),
        (GroupingSignalDimension, ("good", True)),
        (GroupingSignalDimension, ("good", 2.0)),
        (GroupingSignalStudentBand, ("", "reading", 1)),
        (GroupingSignalStudentBand, ("student", "", 1)),
        (GroupingSignalStudentBand, ("student", "reading", 0)),
        (GroupingSignalStudentBand, ("student", "reading", True)),
        (GroupingSignalStudentBand, ("student", "reading", 1.0)),
    ],
)
def test_invalid_nested_model_fields_rejected(
    factory: Callable[..., object], args: tuple[object, ...]
) -> None:
    with pytest.raises(GroupingSignalValidationError):
        factory(*args)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "2"},
        {"record_type": "group_plan"},
        {"signal_set_id": ""},
        {"signal_set_id": " bad"},
        {"class_id": "bad/path"},
        {"created_at": datetime(2026, 9, 1, 18, 30)},
        {"created_at": "2026-09-01T18:30:00+00:00"},
        {"dimensions": ()},
        {"student_bands": ()},
    ],
)
def test_invalid_top_level_runtime_fields_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(GroupingSignalValidationError):
        signal(**changes)


def test_duplicate_dimensions_rejected_before_sorting() -> None:
    dims = (
        GroupingSignalDimension("reading", 3),
        GroupingSignalDimension("reading", 4),
    )
    bands = (GroupingSignalStudentBand("student", "reading", 1),)
    with pytest.raises(GroupingSignalValidationError, match="duplicate"):
        signal(dimensions=dims, student_bands=bands)


def test_duplicate_student_dimension_pair_rejected_even_when_band_matches() -> None:
    dims = (GroupingSignalDimension("reading", 3),)
    entry = GroupingSignalStudentBand("student", "reading", 1)
    with pytest.raises(GroupingSignalValidationError, match="duplicate"):
        signal(dimensions=dims, student_bands=(entry, entry))


def test_same_student_in_different_dimensions_is_valid() -> None:
    value = signal()
    assert sum(item.student_id == "student_001" for item in value.student_bands) == 2


def test_undeclared_dimension_rejected() -> None:
    with pytest.raises(GroupingSignalValidationError, match="undeclared"):
        signal(
            student_bands=(
                *signal().student_bands,
                GroupingSignalStudentBand("student_003", "science", 1),
            )
        )


def test_band_above_declared_count_rejected() -> None:
    with pytest.raises(GroupingSignalValidationError, match="between 1 and 4"):
        signal(
            student_bands=(
                GroupingSignalStudentBand("student_001", "reading_analysis", 5),
                GroupingSignalStudentBand(
                    "student_001", "writing_claim_evidence", 1
                ),
            )
        )


def test_every_declared_dimension_requires_one_entry_but_partial_coverage_is_valid(
) -> None:
    partial = signal()
    assert len(partial.student_bands) == 3
    with pytest.raises(GroupingSignalValidationError, match="at least one"):
        signal(
            student_bands=(
                GroupingSignalStudentBand("student_001", "reading_analysis", 2),
            )
        )


def test_structurally_valid_unknown_student_is_not_roster_checked() -> None:
    value = signal(
        student_bands=(
            GroupingSignalStudentBand("synthetic_unknown", "reading_analysis", 2),
            GroupingSignalStudentBand(
                "synthetic_unknown", "writing_claim_evidence", 1
            ),
        )
    )
    assert value.student_bands[0].student_id == "synthetic_unknown"


def test_validate_returns_fresh_fully_revalidated_value() -> None:
    value = signal()
    validated = validate_grouping_signal_set(value)
    assert validated == value
    assert validated is not value
    assert validated.source is not value.source


def test_exact_dict_shape_and_field_order() -> None:
    data = canonical_dict()
    assert list(data) == [
        "schema_version",
        "record_type",
        "signal_set_id",
        "class_id",
        "created_at",
        "source",
        "dimensions",
        "student_bands",
    ]
    source_data = data["source"]
    assert isinstance(source_data, dict)
    assert list(source_data) == [
        "kind",
        "module_id",
        "snapshot_id",
        "snapshot_digest_algorithm",
        "snapshot_digest",
    ]
    dimensions = data["dimensions"]
    assert isinstance(dimensions, list)
    assert list(dimensions[0]) == ["dimension_id", "band_count"]
    bands = data["student_bands"]
    assert isinstance(bands, list)
    assert list(bands[0]) == ["student_id", "dimension_id", "band"]


def test_dict_round_trip_is_exact() -> None:
    value = signal()
    data = grouping_signal_set_to_dict(value)
    assert grouping_signal_set_from_dict(data) == value
    assert grouping_signal_set_to_dict(grouping_signal_set_from_dict(data)) == data


@pytest.mark.parametrize("missing", sorted({
    "schema_version",
    "record_type",
    "signal_set_id",
    "class_id",
    "created_at",
    "source",
    "dimensions",
    "student_bands",
}))
def test_from_dict_rejects_every_missing_top_level_field(missing: str) -> None:
    data = canonical_dict()
    data.pop(missing)
    with pytest.raises(GroupingSignalValidationError, match="missing"):
        grouping_signal_set_from_dict(data)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: {**data, "metadata": {}},
        lambda data: {**data, "score": 80},
        lambda data: {**data, "percentage": 80.0},
        lambda data: {**data, "grade": "B"},
        lambda data: {**data, "proficiency": 3},
        lambda data: {**data, "group_id": "g1"},
        lambda data: {**data, "group_membership": {}},
        lambda data: {**data, "group_plan_id": "p1"},
        lambda data: {**data, "strategy": "mixed"},
        lambda data: {**data, "student_name": "Synthetic Student"},
        lambda data: {**data, "notes": "private"},
    ],
)
def test_prohibited_top_level_fields_are_rejected_as_unknown(
    mutator: Callable[[dict[str, object]], dict[str, object]],
) -> None:
    with pytest.raises(GroupingSignalValidationError, match="unknown"):
        grouping_signal_set_from_dict(mutator(canonical_dict()))


def test_unknown_nested_fields_are_rejected() -> None:
    data = canonical_dict()
    assert isinstance(data["source"], dict)
    data["source"]["grade"] = 1
    with pytest.raises(GroupingSignalValidationError, match="unknown"):
        grouping_signal_set_from_dict(data)

    data = canonical_dict()
    assert isinstance(data["dimensions"], list)
    data["dimensions"][0]["proficiency"] = "high"
    with pytest.raises(GroupingSignalValidationError, match="unknown"):
        grouping_signal_set_from_dict(data)

    data = canonical_dict()
    assert isinstance(data["student_bands"], list)
    data["student_bands"][0]["group_id"] = "g1"
    with pytest.raises(GroupingSignalValidationError, match="unknown"):
        grouping_signal_set_from_dict(data)


def test_allowed_identifier_text_is_not_keyword_censored() -> None:
    value = signal(
        source=source(snapshot_id="grade_snapshot_without_raw_values")
    )
    assert value.source.snapshot_id == "grade_snapshot_without_raw_values"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: 1,
        lambda data: {**data, 1: "x"},
        lambda data: {**data, "schema_version": 1},
        lambda data: {**data, "record_type": None},
        lambda data: {**data, "dimensions": ()},
        lambda data: {**data, "student_bands": ()},
        lambda data: {**data, "created_at": "not-a-time"},
        lambda data: {**data, "created_at": "2026-09-01T18:30:00"},
        lambda data: {**data, "created_at": "2026-09-01T14:30:00-04:00"},
        lambda data: {**data, "created_at": "2026-09-01T18:30:00Z"},
    ],
)
def test_from_dict_rejects_malformed_or_noncanonical_shapes(
    mutator: Callable[[dict[str, object]], object],
) -> None:
    with pytest.raises(GroupingSignalValidationError):
        grouping_signal_set_from_dict(mutator(canonical_dict()))


def test_from_dict_rejects_noncanonical_list_order() -> None:
    data = canonical_dict()
    assert isinstance(data["dimensions"], list)
    data["dimensions"].reverse()
    with pytest.raises(GroupingSignalValidationError, match="canonical"):
        grouping_signal_set_from_dict(data)

    data = canonical_dict()
    assert isinstance(data["student_bands"], list)
    data["student_bands"].reverse()
    with pytest.raises(GroupingSignalValidationError, match="canonical"):
        grouping_signal_set_from_dict(data)


def test_canonical_json_has_one_literal_golden_representation() -> None:
    one = GroupingSignalSet(
        schema_version="1",
        record_type="grouping_signal_set",
        signal_set_id="teacher_plan_001",
        class_id="english10_p2",
        created_at=datetime(2026, 9, 1, 18, tzinfo=UTC),
        source=teacher_source(),
        dimensions=(GroupingSignalDimension("discussion_support", 3),),
        student_bands=(
            GroupingSignalStudentBand("student_001", "discussion_support", 1),
        ),
    )
    expected = """{
  \"schema_version\": \"1\",
  \"record_type\": \"grouping_signal_set\",
  \"signal_set_id\": \"teacher_plan_001\",
  \"class_id\": \"english10_p2\",
  \"created_at\": \"2026-09-01T18:00:00+00:00\",
  \"source\": {
    \"kind\": \"teacher_authored\",
    \"module_id\": null,
    \"snapshot_id\": null,
    \"snapshot_digest_algorithm\": null,
    \"snapshot_digest\": null
  },
  \"dimensions\": [
    {
      \"dimension_id\": \"discussion_support\",
      \"band_count\": 3
    }
  ],
  \"student_bands\": [
    {
      \"student_id\": \"student_001\",
      \"dimension_id\": \"discussion_support\",
      \"band\": 1
    }
  ]
}
"""
    assert grouping_signal_set_to_json(one) == expected
    assert grouping_signal_set_to_json_bytes(one) == expected.encode("utf-8")
    assert grouping_signal_set_from_json(expected) == one


def test_json_round_trip_is_byte_stable() -> None:
    canonical = grouping_signal_set_to_json_bytes(signal())
    loaded = grouping_signal_set_from_json(canonical)
    assert grouping_signal_set_to_json_bytes(loaded) == canonical


@pytest.mark.parametrize(
    "transform",
    [
        lambda text: text.replace("  ", "    ", 1),
        lambda text: text.rstrip("\n"),
        lambda text: text + "\n",
        lambda text: " " + text,
        lambda text: text.replace("\n", "\r\n"),
        lambda text: json.dumps(json.loads(text), separators=(",", ":")) + "\n",
        lambda text: text.replace(
            '"schema_version": "1",\n  "record_type": "grouping_signal_set"',
            '"record_type": "grouping_signal_set",\n  "schema_version": "1"',
        ),
        lambda text: text.replace("+00:00", "Z", 1),
        lambda text: text.replace(
            "2026-09-01T18:30:00+00:00", "2026-09-01T14:30:00-04:00", 1
        ),
    ],
)
def test_strict_json_loader_rejects_byte_noncanonical_text(
    transform: Callable[[str], str],
) -> None:
    canonical = grouping_signal_set_to_json(signal())
    changed = transform(canonical)
    assert changed != canonical
    with pytest.raises(GroupingSignalValidationError):
        grouping_signal_set_from_json(changed)


def test_strict_json_loader_rejects_bom_and_invalid_utf8() -> None:
    canonical = grouping_signal_set_to_json_bytes(signal())
    with pytest.raises(GroupingSignalValidationError):
        grouping_signal_set_from_json(b"\xef\xbb\xbf" + canonical)
    with pytest.raises(GroupingSignalValidationError, match="UTF-8"):
        grouping_signal_set_from_json(b"\xff")


@pytest.mark.parametrize(
    "fragment",
    [
        '"schema_version": "1",\n  "schema_version": "1",',
        '"kind": "module_generated",\n    "kind": "module_generated",',
        (
            '"dimension_id": "reading_analysis",\n      '
            '"dimension_id": "reading_analysis",'
        ),
        '"student_id": "student_001",\n      "student_id": "student_001",',
    ],
)
def test_strict_json_loader_rejects_duplicate_keys(fragment: str) -> None:
    canonical = grouping_signal_set_to_json(signal())
    if fragment.startswith('"schema_version"'):
        changed = canonical.replace('"schema_version": "1",', fragment, 1)
    elif fragment.startswith('"kind"'):
        changed = canonical.replace('"kind": "module_generated",', fragment, 1)
    elif fragment.startswith('"dimension_id"'):
        changed = canonical.replace(
            '"dimension_id": "reading_analysis",', fragment, 1
        )
    else:
        changed = canonical.replace('"student_id": "student_001",', fragment, 1)
    with pytest.raises(GroupingSignalValidationError, match="duplicate"):
        grouping_signal_set_from_json(changed)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_strict_json_loader_rejects_invalid_numeric_constants(constant: str) -> None:
    canonical = grouping_signal_set_to_json(signal())
    changed = canonical.replace('"band": 2', f'"band": {constant}', 1)
    with pytest.raises(GroupingSignalValidationError, match="numeric constant"):
        grouping_signal_set_from_json(changed)


def test_json_loader_rejects_wrong_input_type_and_nonobject_root() -> None:
    with pytest.raises(GroupingSignalValidationError, match="string or UTF-8 bytes"):
        grouping_signal_set_from_json(1)  # type: ignore[arg-type]
    with pytest.raises(GroupingSignalValidationError, match="object"):
        grouping_signal_set_from_json("[]\n")


def test_boundary_fields_are_absent() -> None:
    names = {item.name for item in fields(GroupingSignalSet)}
    assert names == {
        "schema_version",
        "record_type",
        "signal_set_id",
        "class_id",
        "created_at",
        "source",
        "dimensions",
        "student_bands",
    }
    assert not names & {
        "score",
        "percentage",
        "grade",
        "proficiency",
        "group_id",
        "group_membership",
        "group_plan_id",
        "strategy",
        "metadata",
        "updated_at",
    }


def test_validation_errors_do_not_dump_complete_record() -> None:
    data = canonical_dict()
    data["metadata"] = {"private": "value"}
    with pytest.raises(GroupingSignalValidationError) as exc_info:
        grouping_signal_set_from_dict(data)
    message = str(exc_info.value)
    assert "student_001" not in message
    assert DIGEST not in message
    assert "metadata" in message
