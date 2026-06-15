"""Tests for standards JSON-compatible dictionary helpers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    standard_definition_from_dict,
    standard_definition_to_dict,
    standards_library_from_dict,
    standards_library_to_dict,
    standards_profile_from_dict,
    standards_profile_to_dict,
)


def make_standard() -> StandardDefinition:
    return StandardDefinition(
        standard_id="njsls-ela:RL.CR.11-12.1",
        code="RL.CR.11-12.1",
        source="NJSLS-ELA",
        short_name="Close Reading Evidence",
        description="Cite strong and thorough textual evidence.",
        subject="English Language Arts",
        course="English 12",
        grade_band="11-12",
        domain="Reading Literature",
        category_path=(
            "English Language Arts",
            "Reading Literature",
            "Close Reading",
        ),
        tags=("close_reading", "textual_evidence"),
        active=True,
        available_modules=("pds-scoreform", "pds-quillan"),
    )


def make_profile() -> StandardsProfile:
    return StandardsProfile(
        profile_id="english_12_njsls",
        standards=("njsls-ela:RL.CR.11-12.1",),
        subject="English Language Arts",
        course="English 12",
        source="NJSLS-ELA",
        title="English 12 NJSLS",
        description="Synthetic English 12 standards profile.",
    )


def test_standard_definition_to_dict_serializes_all_fields() -> None:
    data = standard_definition_to_dict(make_standard())

    assert data == {
        "standard_id": "njsls-ela:RL.CR.11-12.1",
        "code": "RL.CR.11-12.1",
        "source": "NJSLS-ELA",
        "short_name": "Close Reading Evidence",
        "description": "Cite strong and thorough textual evidence.",
        "subject": "English Language Arts",
        "course": "English 12",
        "grade_band": "11-12",
        "domain": "Reading Literature",
        "category_path": [
            "English Language Arts",
            "Reading Literature",
            "Close Reading",
        ],
        "tags": ["close_reading", "textual_evidence"],
        "active": True,
        "available_modules": ["pds-scoreform", "pds-quillan"],
    }
    assert data["standard_id"] != data["code"]


def test_standard_definition_to_dict_includes_empty_optional_fields() -> None:
    definition = StandardDefinition(
        standard_id="local-writing:evidence_explanation",
        code="evidence_explanation",
        source="Local Writing Rubric",
        short_name="Evidence Explanation",
        description="Explain evidence clearly.",
    )

    data = standard_definition_to_dict(definition)

    assert data["subject"] is None
    assert data["course"] is None
    assert data["grade_band"] is None
    assert data["domain"] is None
    assert data["category_path"] == []
    assert data["tags"] == []
    assert data["available_modules"] == []


def test_standard_definition_from_dict_builds_valid_model() -> None:
    data = standard_definition_to_dict(make_standard())
    data["standard_id"] = " njsls-ela:RL.CR.11-12.1 "
    data["category_path"] = [
        " English Language Arts ",
        "Reading Literature",
        "Close Reading",
    ]

    definition = standard_definition_from_dict(data)

    assert definition.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert definition.code == "RL.CR.11-12.1"
    assert definition.category_path == (
        "English Language Arts",
        "Reading Literature",
        "Close Reading",
    )
    assert definition.tags == ("close_reading", "textual_evidence")
    assert definition.available_modules == ("pds-scoreform", "pds-quillan")


def test_standard_definition_round_trips_through_dict() -> None:
    definition = make_standard()

    assert (
        standard_definition_from_dict(
            standard_definition_to_dict(definition)
        )
        == definition
    )


def test_standard_definition_from_dict_rejects_missing_required_keys() -> None:
    data = standard_definition_to_dict(make_standard())
    del data["code"]

    with pytest.raises(StandardsValidationError, match=r"required key.*code"):
        standard_definition_from_dict(data)


def test_standard_definition_from_dict_rejects_unknown_keys() -> None:
    data = standard_definition_to_dict(make_standard())
    data["schema_version"] = 1

    with pytest.raises(StandardsValidationError, match=r"unknown key.*schema_version"):
        standard_definition_from_dict(data)


def test_standard_definition_from_dict_rejects_invalid_array_fields() -> None:
    data = standard_definition_to_dict(make_standard())
    data["category_path"] = "English Language Arts"

    with pytest.raises(StandardsValidationError, match="category_path"):
        standard_definition_from_dict(data)


def test_standards_profile_round_trips_through_dict() -> None:
    profile = make_profile()

    data = standards_profile_to_dict(profile)

    assert data["standards"] == ["njsls-ela:RL.CR.11-12.1"]
    assert standards_profile_from_dict(data) == profile


def test_standards_profile_from_dict_rejects_string_standards() -> None:
    data = standards_profile_to_dict(make_profile())
    data["standards"] = "njsls-ela:RL.CR.11-12.1"

    with pytest.raises(StandardsValidationError, match="standards"):
        standards_profile_from_dict(data)


def test_standards_profile_from_dict_rejects_duplicate_references() -> None:
    data = standards_profile_to_dict(make_profile())
    data["standards"] = [
        "njsls-ela:RL.CR.11-12.1",
        " njsls-ela:RL.CR.11-12.1 ",
    ]

    with pytest.raises(StandardsValidationError, match="duplicate standard IDs"):
        standards_profile_from_dict(data)


def test_standards_library_round_trips_through_dict() -> None:
    library = StandardsLibrary(
        standards=(make_standard(),),
        profiles=(make_profile(),),
    )

    data = standards_library_to_dict(library)

    assert isinstance(data["standards"], list)
    assert isinstance(data["profiles"], list)
    assert standards_library_from_dict(data) == library


def test_standards_library_from_dict_allows_missing_profiles() -> None:
    library = standards_library_from_dict(
        {"standards": [standard_definition_to_dict(make_standard())]}
    )

    assert library.standards == (make_standard(),)
    assert library.profiles == ()


def test_standards_library_from_dict_rejects_unknown_profile_references() -> None:
    profile_data = standards_profile_to_dict(make_profile())
    profile_data["standards"] = ["njsls-ela:W.AW.11-12.1"]

    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        standards_library_from_dict(
            {
                "standards": [standard_definition_to_dict(make_standard())],
                "profiles": [profile_data],
            }
        )


def test_standards_library_from_dict_rejects_duplicate_standard_ids() -> None:
    standard_data = standard_definition_to_dict(make_standard())

    with pytest.raises(StandardsValidationError, match="duplicate standard IDs"):
        standards_library_from_dict(
            {"standards": [standard_data, standard_data]}
        )


def test_standards_library_from_dict_rejects_duplicate_profile_ids() -> None:
    profile_data = standards_profile_to_dict(make_profile())

    with pytest.raises(StandardsValidationError, match="duplicate profile IDs"):
        standards_library_from_dict(
            {
                "standards": [standard_definition_to_dict(make_standard())],
                "profiles": [profile_data, profile_data],
            }
        )


def test_standards_library_from_dict_rejects_invalid_nested_records() -> None:
    with pytest.raises(
        StandardsValidationError,
        match=r"standards\[0\].*mapping",
    ):
        standards_library_from_dict({"standards": ["not a mapping"]})


@pytest.mark.parametrize(
    "deserializer",
    [
        standard_definition_from_dict,
        standards_profile_from_dict,
        standards_library_from_dict,
    ],
)
def test_standards_deserializers_reject_non_mapping_input(
    deserializer: Any,
) -> None:
    with pytest.raises(StandardsValidationError, match="mapping"):
        deserializer(cast(Any, []))
