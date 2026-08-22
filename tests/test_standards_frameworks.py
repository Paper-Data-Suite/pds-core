"""Tests for standards-framework provenance and lifecycle metadata."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace as dataclass_replace
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsFrameworkMetadata,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    add_standard_definition,
    add_standard_definitions,
    add_standards_profile,
    filter_standards_frameworks,
    find_standards_framework,
    standards_framework_from_dict,
    standards_framework_to_dict,
    standards_library_from_dict,
    standards_library_to_dict,
    replace_standard_definition,
    replace_standards_profile,
    upsert_standard_definition,
    upsert_standards_profile,
    validate_standards_library,
)


def make_framework(**overrides: Any) -> StandardsFrameworkMetadata:
    values: dict[str, object] = {
        "framework_id": "example_2026",
        "source": "Example Framework 2026",
        "title": "Example Standards Framework",
        "authority": "Example Standards Board",
        "publisher": "Example Department of Education",
        "source_url": "https://example.invalid/standards/2026/",
        "version": "2026",
        "adoption_date": "2026-04-08",
        "implementation_date": "2027-09",
        "supersedes": ("example_2020",),
        "license_name": None,
        "license_url": None,
        "redistribution_notes": "Verify redistribution terms before republishing.",
    }
    values.update(overrides)
    return StandardsFrameworkMetadata(**cast(Any, values))


def make_standard(source: str = "Example Framework 2026") -> StandardDefinition:
    return StandardDefinition(
        standard_id=f"example:{source[-4:]}:A.1",
        code="A.1",
        source=source,
        short_name="Synthetic standard",
        description="Synthetic standard text.",
    )


def test_framework_normalizes_text_and_is_immutable() -> None:
    framework = make_framework(
        framework_id=" example_2026 ",
        authority=" Example Standards Board ",
        supersedes=(" example_2020 ",),
    )

    assert framework.framework_id == "example_2026"
    assert framework.authority == "Example Standards Board"
    assert framework.supersedes == ("example_2020",)
    with pytest.raises(FrozenInstanceError):
        setattr(framework, "title", "Replacement")


@pytest.mark.parametrize(
    "value",
    ["2026", "2026-09", "2026-09-01", "2024-02-29"],
)
def test_framework_accepts_source_date_precision(value: str) -> None:
    assert make_framework(adoption_date=value).adoption_date == value


@pytest.mark.parametrize(
    "value",
    ["2026-00", "2026-13", "2026-02-30", "26", "2026-9", "2026/09/01"],
)
def test_framework_rejects_invalid_lifecycle_dates(value: str) -> None:
    with pytest.raises(StandardsValidationError, match="YYYY"):
        make_framework(adoption_date=value)


def test_framework_rejects_duplicate_and_self_supersession() -> None:
    with pytest.raises(StandardsValidationError, match="duplicate framework IDs"):
        make_framework(supersedes=("example_2020", " example_2020 "))
    with pytest.raises(StandardsValidationError, match="supersede itself"):
        make_framework(supersedes=("example_2026",))


def test_framework_round_trips_through_dict() -> None:
    framework = make_framework()
    data = standards_framework_to_dict(framework)

    assert data["supersedes"] == ["example_2020"]
    assert data["implementation_date"] == "2027-09"
    assert standards_framework_from_dict(data) == framework


def test_framework_from_dict_rejects_unknown_keys() -> None:
    data = standards_framework_to_dict(make_framework())
    data["current"] = True
    with pytest.raises(StandardsValidationError, match=r"unknown key.*current"):
        standards_framework_from_dict(data)


def test_framework_from_dict_rejects_missing_required_and_non_mapping() -> None:
    data = standards_framework_to_dict(make_framework())
    del data["authority"]
    with pytest.raises(StandardsValidationError, match=r"required key.*authority"):
        standards_framework_from_dict(data)
    with pytest.raises(StandardsValidationError, match="mapping"):
        standards_framework_from_dict(cast(Any, []))


def test_library_rejects_duplicate_framework_ids_and_sources() -> None:
    first = make_framework()
    with pytest.raises(StandardsValidationError, match="duplicate framework IDs"):
        StandardsLibrary(standards=(), frameworks=(first, first))

    second = make_framework(framework_id="example_other_2026")
    with pytest.raises(StandardsValidationError, match="duplicate source values"):
        StandardsLibrary(standards=(), frameworks=(first, second))


def test_legacy_library_without_frameworks_remains_valid() -> None:
    library = standards_library_from_dict({"standards": [], "profiles": []})
    assert library.frameworks == ()
    assert standards_library_to_dict(library)["frameworks"] == []


def test_frameworks_can_exist_without_matching_standard_sources() -> None:
    library = StandardsLibrary(standards=(), frameworks=(make_framework(),))
    assert validate_standards_library(library) == library


def test_legacy_standard_source_needs_no_framework_metadata() -> None:
    standard = make_standard("Legacy Local Framework")
    library = StandardsLibrary(standards=(standard,))
    assert validate_standards_library(library) == library


def test_framework_lookup_and_filters_are_read_only() -> None:
    framework = make_framework()
    library = StandardsLibrary(standards=(), frameworks=(framework,))

    assert find_standards_framework(library, " example_2026 ") == framework
    assert find_standards_framework(library, "missing") is None
    assert filter_standards_frameworks(
        library, source="Example Framework 2026"
    ) == (framework,)
    assert filter_standards_frameworks(
        library, authority="Example Standards Board"
    ) == (framework,)
    assert filter_standards_frameworks(library, authority="Other") == ()


def test_old_and_successor_frameworks_can_coexist_without_changing_active() -> None:
    old_framework = make_framework(
        framework_id="example_2020",
        source="Example Framework 2020",
        version="2020",
        adoption_date="2020",
        implementation_date="2020-09",
        supersedes=(),
    )
    successor = make_framework()
    old_standard = make_standard("Example Framework 2020")
    new_standard = make_standard("Example Framework 2026")
    library = StandardsLibrary(
        standards=(old_standard, new_standard),
        frameworks=(old_framework, successor),
    )

    restored = standards_library_from_dict(standards_library_to_dict(library))
    assert restored == library
    assert restored.frameworks[1].supersedes == ("example_2020",)
    assert all(standard.active for standard in restored.standards)


def test_standard_and_profile_mutations_preserve_framework_metadata() -> None:
    framework = make_framework()
    library = StandardsLibrary(standards=(), frameworks=(framework,))
    standard = make_standard()

    with_standard = add_standard_definition(library, standard)
    assert with_standard.frameworks == (framework,)

    replacement = dataclass_replace(standard, short_name="Updated standard")
    replaced = replace_standard_definition(with_standard, replacement)
    assert replaced.frameworks == (framework,)
    upserted = upsert_standard_definition(replaced, standard)
    assert upserted.frameworks == (framework,)

    second = StandardDefinition(
        standard_id="example:2026:A.2",
        code="A.2",
        source=standard.source,
        short_name="Second synthetic standard",
        description="Second synthetic standard text.",
    )
    with_batch = add_standard_definitions(upserted, (second,))
    assert with_batch.frameworks == (framework,)

    profile = StandardsProfile(
        profile_id="example_profile",
        standards=(standard.standard_id,),
        source=standard.source,
    )
    with_profile = add_standards_profile(with_batch, profile)
    assert with_profile.frameworks == (framework,)

    profile_replacement = dataclass_replace(
        profile, description="Updated synthetic profile."
    )
    replaced_profile = replace_standards_profile(with_profile, profile_replacement)
    assert replaced_profile.frameworks == (framework,)
    upserted_profile = upsert_standards_profile(replaced_profile, profile)
    assert upserted_profile.frameworks == (framework,)
