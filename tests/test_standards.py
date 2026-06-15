"""Tests for shared in-memory standards models and validation."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    validate_standard_definition,
    validate_standards_library,
    validate_standards_profile,
)


def make_standard(
    standard_id: str = "njsls-ela:RL.CR.11-12.1",
    code: str = "RL.CR.11-12.1",
) -> StandardDefinition:
    return StandardDefinition(
        standard_id=standard_id,
        code=code,
        source="NJSLS-ELA",
        short_name="Close Reading Evidence",
        description="Cite strong and thorough textual evidence.",
    )


@pytest.mark.parametrize("code", ["RL.CR.11-12.1", "9.4.12.DC.1"])
def test_standard_definition_accepts_official_code_punctuation(code: str) -> None:
    definition = make_standard(code=code)

    assert definition.code == code


def test_standard_definition_preserves_standard_id_and_code() -> None:
    definition = make_standard()

    assert definition.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert definition.code == "RL.CR.11-12.1"
    assert definition.standard_id != definition.code


@pytest.mark.parametrize(
    "field_name",
    ["standard_id", "code", "source", "short_name", "description"],
)
def test_standard_definition_rejects_blank_required_fields(
    field_name: str,
) -> None:
    values = {
        "standard_id": "njsls-ela:RL.CR.11-12.1",
        "code": "RL.CR.11-12.1",
        "source": "NJSLS-ELA",
        "short_name": "Close Reading Evidence",
        "description": "Cite strong and thorough textual evidence.",
    }
    values[field_name] = "   "

    with pytest.raises(StandardsValidationError, match=field_name):
        StandardDefinition(**cast(Any, values))


def test_standard_definition_accepts_category_path_for_menu_grouping() -> None:
    path = [
        " English Language Arts ",
        "Reading Literature",
        "Close Reading",
    ]

    definition = StandardDefinition(
        standard_id="njsls-ela:RL.CR.11-12.1",
        code="RL.CR.11-12.1",
        source="NJSLS-ELA",
        short_name="Close Reading Evidence",
        description="Cite strong and thorough textual evidence.",
        category_path=path,  # type: ignore[arg-type]
    )
    path.append("Changed")

    assert definition.category_path == (
        "English Language Arts",
        "Reading Literature",
        "Close Reading",
    )


def test_standard_definition_rejects_blank_category_path_entries() -> None:
    with pytest.raises(StandardsValidationError, match=r"category_path\[1\]"):
        StandardDefinition(
            standard_id="njsls-ela:RL.CR.11-12.1",
            code="RL.CR.11-12.1",
            source="NJSLS-ELA",
            short_name="Close Reading Evidence",
            description="Cite strong and thorough textual evidence.",
            category_path=("English Language Arts", " "),
        )


def test_standard_definition_accepts_available_modules_metadata() -> None:
    modules = [" pds-scoreform ", "pds-quillan"]

    definition = StandardDefinition(
        standard_id="njsls-ela:RL.CR.11-12.1",
        code="RL.CR.11-12.1",
        source="NJSLS-ELA",
        short_name="Close Reading Evidence",
        description="Cite strong and thorough textual evidence.",
        available_modules=modules,  # type: ignore[arg-type]
    )
    modules.append("changed")

    assert definition.available_modules == ("pds-scoreform", "pds-quillan")


def test_standard_definition_trims_text_and_is_frozen() -> None:
    definition = StandardDefinition(
        standard_id=" local-writing:evidence_explanation ",
        code=" evidence_explanation ",
        source=" Local Writing Rubric ",
        short_name=" Evidence Explanation ",
        description=" Explain evidence clearly. ",
        subject=" English Language Arts ",
    )

    assert definition.standard_id == "local-writing:evidence_explanation"
    assert definition.code == "evidence_explanation"
    assert definition.subject == "English Language Arts"
    with pytest.raises(FrozenInstanceError):
        setattr(definition, "code", "changed")


def test_standards_profile_references_standard_ids() -> None:
    references = [
        " njsls-ela:RL.CR.11-12.1 ",
        "njsls-ela:W.AW.11-12.1",
    ]

    profile = StandardsProfile(
        profile_id=" english_12_njsls ",
        standards=references,  # type: ignore[arg-type]
        title=" English 12 ",
    )
    references.append("changed")

    assert profile.profile_id == "english_12_njsls"
    assert profile.standards == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
    )
    assert all(isinstance(standard_id, str) for standard_id in profile.standards)
    assert profile.title == "English 12"


def test_standards_profile_rejects_duplicate_standard_ids() -> None:
    with pytest.raises(StandardsValidationError, match="duplicate standard IDs"):
        StandardsProfile(
            profile_id="english_12_njsls",
            standards=(
                "njsls-ela:RL.CR.11-12.1",
                " njsls-ela:RL.CR.11-12.1 ",
            ),
        )


def test_standards_profile_rejects_empty_standard_references() -> None:
    with pytest.raises(StandardsValidationError, match="at least one"):
        StandardsProfile(
            profile_id="english_12_njsls",
            standards=(),
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("profile_id", " "),
        ("subject", " "),
        ("course", " "),
        ("source", " "),
        ("title", " "),
        ("description", " "),
    ],
)
def test_standards_profile_rejects_blank_text_fields(
    field_name: str,
    value: str,
) -> None:
    values: dict[str, object] = {
        "profile_id": "english_12_njsls",
        "standards": ("njsls-ela:RL.CR.11-12.1",),
        field_name: value,
    }

    with pytest.raises(StandardsValidationError, match=field_name):
        StandardsProfile(**cast(Any, values))


def test_standards_library_accepts_known_profile_references() -> None:
    definition = make_standard()
    profile = StandardsProfile(
        profile_id="english_12_njsls",
        standards=(definition.standard_id,),
    )

    library = StandardsLibrary(
        standards=[definition],  # type: ignore[arg-type]
        profiles=[profile],  # type: ignore[arg-type]
    )

    assert library.standards == (definition,)
    assert library.profiles == (profile,)


def test_standards_library_rejects_unknown_profile_references() -> None:
    profile = StandardsProfile(
        profile_id="english_12_njsls",
        standards=("njsls-ela:W.AW.11-12.1",),
    )

    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        StandardsLibrary(standards=(make_standard(),), profiles=(profile,))


def test_standards_library_rejects_duplicate_standard_ids() -> None:
    with pytest.raises(StandardsValidationError, match="duplicate standard IDs"):
        StandardsLibrary(standards=(make_standard(), make_standard()))


def test_standards_library_rejects_duplicate_profile_ids() -> None:
    definition = make_standard()
    profile = StandardsProfile(
        profile_id="english_12_njsls",
        standards=(definition.standard_id,),
    )

    with pytest.raises(StandardsValidationError, match="duplicate profile IDs"):
        StandardsLibrary(
            standards=(definition,),
            profiles=(profile, profile),
        )


def test_explicit_validation_helpers_return_validated_models() -> None:
    definition = make_standard()
    profile = StandardsProfile(
        profile_id="english_12_njsls",
        standards=(definition.standard_id,),
    )
    library = StandardsLibrary(
        standards=(definition,),
        profiles=(profile,),
    )

    assert validate_standard_definition(definition) is definition
    assert validate_standards_profile(profile) is profile
    assert validate_standards_library(library) is library
