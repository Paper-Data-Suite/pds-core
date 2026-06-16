"""Tests for read-only standards library browsing helpers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    filter_standard_definitions,
    filter_standards_profiles,
    find_standard_definition,
    find_standards_profile,
    list_standard_category_paths,
    list_standard_domains,
    list_standard_sources,
    list_standard_subjects,
    standards_library_from_dict,
    standards_library_to_dict,
)


def make_library() -> StandardsLibrary:
    standards = (
        StandardDefinition(
            standard_id="njsls-ela:RL.CR.11-12.1",
            code="RL.CR.11-12.1",
            source="NJSLS-ELA",
            short_name="Close Reading Evidence",
            description="Cite strong and thorough textual evidence.",
            subject="English Language Arts",
            course="English 12",
            domain="Reading Literature",
            category_path=(
                "English Language Arts",
                "Reading Literature",
                "Close Reading",
            ),
            tags=("close_reading", "textual_evidence"),
            active=True,
            available_modules=("pds-scoreform", "pds-quillan"),
        ),
        StandardDefinition(
            standard_id="njsls-ela:RI.CR.11-12.1",
            code="RI.CR.11-12.1",
            source="NJSLS-ELA",
            short_name="Informational Text Evidence",
            description="Cite textual evidence from informational text.",
            subject="English Language Arts",
            course="English 12",
            domain="Reading Informational Text",
            category_path=(
                "English Language Arts",
                "Reading Informational Text",
                "Close Reading",
            ),
            active=False,
            available_modules=("pds-quillan",),
        ),
        StandardDefinition(
            standard_id="local-writing:evidence_explanation",
            code="evidence_explanation",
            source="Local Writing Rubric",
            short_name="Evidence Explanation",
            description="Explain how evidence supports a claim.",
            subject="English Language Arts",
            course="English 12",
            domain="Writing",
            category_path=("English Language Arts", "Writing"),
            active=True,
            available_modules=("pds-scoreform",),
        ),
        StandardDefinition(
            standard_id="local-misc:unfiled",
            code="unfiled",
            source="Local Misc",
            short_name="Unfiled Skill",
            description="A local skill without subject or domain metadata.",
            active=True,
        ),
    )
    profiles = (
        StandardsProfile(
            profile_id="english_12_njsls",
            standards=(
                "njsls-ela:RL.CR.11-12.1",
                "njsls-ela:RI.CR.11-12.1",
            ),
            subject="English Language Arts",
            course="English 12",
            source="NJSLS-ELA",
            title="English 12 NJSLS",
        ),
        StandardsProfile(
            profile_id="english_12_local",
            standards=("local-writing:evidence_explanation",),
            subject="English Language Arts",
            course="English 12",
            source="Local Writing Rubric",
            title="English 12 Local Writing",
        ),
        StandardsProfile(
            profile_id="misc_local",
            standards=("local-misc:unfiled",),
            source="Local Misc",
            title="Miscellaneous",
        ),
    )
    return StandardsLibrary(standards=standards, profiles=profiles)


def standard_ids(definitions: tuple[StandardDefinition, ...]) -> tuple[str, ...]:
    return tuple(definition.standard_id for definition in definitions)


def profile_ids(profiles: tuple[StandardsProfile, ...]) -> tuple[str, ...]:
    return tuple(profile.profile_id for profile in profiles)


def test_find_standard_definition_finds_existing_standard() -> None:
    library = make_library()

    assert (
        find_standard_definition(library, "njsls-ela:RL.CR.11-12.1")
        == library.standards[0]
    )


def test_find_standard_definition_trims_standard_id() -> None:
    library = make_library()

    assert (
        find_standard_definition(library, " njsls-ela:RL.CR.11-12.1 ")
        == library.standards[0]
    )


def test_find_standard_definition_returns_none_for_missing_standard() -> None:
    assert find_standard_definition(make_library(), "missing") is None


def test_find_standard_definition_rejects_blank_standard_id() -> None:
    with pytest.raises(StandardsValidationError, match="standard_id"):
        find_standard_definition(make_library(), " ")


def test_find_standards_profile_finds_existing_profile() -> None:
    library = make_library()

    assert find_standards_profile(library, "english_12_njsls") == library.profiles[0]


def test_find_standards_profile_trims_profile_id() -> None:
    library = make_library()

    assert find_standards_profile(library, " english_12_njsls ") == library.profiles[0]


def test_find_standards_profile_returns_none_for_missing_profile() -> None:
    assert find_standards_profile(make_library(), "missing") is None


def test_find_standards_profile_rejects_blank_profile_id() -> None:
    with pytest.raises(StandardsValidationError, match="profile_id"):
        find_standards_profile(make_library(), " ")


def test_filter_standard_definitions_without_filters_preserves_order() -> None:
    library = make_library()

    assert filter_standard_definitions(library) == library.standards


def test_filter_standard_definitions_by_subject() -> None:
    assert standard_ids(
        filter_standard_definitions(
            make_library(),
            subject="English Language Arts",
        )
    ) == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:RI.CR.11-12.1",
        "local-writing:evidence_explanation",
    )


def test_filter_standard_definitions_by_source() -> None:
    assert standard_ids(
        filter_standard_definitions(make_library(), source="NJSLS-ELA")
    ) == ("njsls-ela:RL.CR.11-12.1", "njsls-ela:RI.CR.11-12.1")


def test_filter_standard_definitions_by_domain() -> None:
    assert standard_ids(
        filter_standard_definitions(make_library(), domain="Writing")
    ) == ("local-writing:evidence_explanation",)


def test_filter_standard_definitions_by_active_true() -> None:
    assert standard_ids(filter_standard_definitions(make_library(), active=True)) == (
        "njsls-ela:RL.CR.11-12.1",
        "local-writing:evidence_explanation",
        "local-misc:unfiled",
    )


def test_filter_standard_definitions_by_active_false() -> None:
    assert standard_ids(filter_standard_definitions(make_library(), active=False)) == (
        "njsls-ela:RI.CR.11-12.1",
    )


def test_filter_standard_definitions_by_available_module() -> None:
    assert standard_ids(
        filter_standard_definitions(
            make_library(),
            available_module="pds-scoreform",
        )
    ) == (
        "njsls-ela:RL.CR.11-12.1",
        "local-writing:evidence_explanation",
    )


def test_filter_standard_definitions_by_category_path_prefix() -> None:
    assert standard_ids(
        filter_standard_definitions(
            make_library(),
            category_path_prefix=("English Language Arts", "Reading Literature"),
        )
    ) == ("njsls-ela:RL.CR.11-12.1",)


def test_filter_standard_definitions_trims_category_path_prefix() -> None:
    assert standard_ids(
        filter_standard_definitions(
            make_library(),
            category_path_prefix=[" English Language Arts ", "Writing"],
        )
    ) == ("local-writing:evidence_explanation",)


def test_filter_standard_definitions_treats_empty_prefix_as_no_filter() -> None:
    library = make_library()

    assert filter_standard_definitions(library, category_path_prefix=()) == (
        library.standards
    )
    assert filter_standard_definitions(library, category_path_prefix=[]) == (
        library.standards
    )


def test_filter_standard_definitions_combines_filters_with_and_semantics() -> None:
    assert standard_ids(
        filter_standard_definitions(
            make_library(),
            subject="English Language Arts",
            source="NJSLS-ELA",
            active=True,
            available_module="pds-quillan",
            category_path_prefix=("English Language Arts",),
        )
    ) == ("njsls-ela:RL.CR.11-12.1",)


def test_filter_standard_definitions_returns_empty_tuple_when_no_match() -> None:
    assert filter_standard_definitions(make_library(), domain="Geometry") == ()


def test_filter_standard_definitions_rejects_invalid_active_value() -> None:
    with pytest.raises(StandardsValidationError, match="active"):
        filter_standard_definitions(make_library(), active=cast(Any, "true"))


@pytest.mark.parametrize(
    ("filter_name", "value"),
    [
        ("subject", " "),
        ("source", " "),
        ("domain", " "),
        ("available_module", " "),
        ("subject", 12),
    ],
)
def test_filter_standard_definitions_rejects_invalid_text_filter_values(
    filter_name: str,
    value: object,
) -> None:
    with pytest.raises(StandardsValidationError, match=filter_name):
        filter_standard_definitions(
            make_library(),
            **cast(Any, {filter_name: value}),
        )


@pytest.mark.parametrize("prefix", ["English Language Arts", b"English"])
def test_filter_standard_definitions_rejects_string_category_path_prefix(
    prefix: object,
) -> None:
    with pytest.raises(StandardsValidationError, match="category_path_prefix"):
        filter_standard_definitions(
            make_library(),
            category_path_prefix=cast(Any, prefix),
        )


def test_filter_standard_definitions_rejects_blank_category_path_prefix_entry() -> None:
    with pytest.raises(StandardsValidationError, match=r"category_path_prefix\[1\]"):
        filter_standard_definitions(
            make_library(),
            category_path_prefix=("English Language Arts", " "),
        )


def test_filter_standard_definitions_does_not_mutate_library() -> None:
    library = make_library()
    before = standards_library_to_dict(library)

    filter_standard_definitions(
        library,
        subject="English Language Arts",
        active=True,
        available_module="pds-scoreform",
    )

    assert standards_library_to_dict(library) == before


def test_list_standard_subjects_returns_sorted_unique_subjects() -> None:
    assert list_standard_subjects(make_library()) == ("English Language Arts",)


def test_list_standard_subjects_omits_missing_subjects() -> None:
    library = StandardsLibrary(
        standards=(
            StandardDefinition(
                standard_id="local:missing_subject",
                code="missing_subject",
                source="Local",
                short_name="Missing Subject",
                description="No subject metadata.",
            ),
        )
    )

    assert list_standard_subjects(library) == ()


def test_list_standard_sources_returns_sorted_unique_sources() -> None:
    assert list_standard_sources(make_library()) == (
        "Local Misc",
        "Local Writing Rubric",
        "NJSLS-ELA",
    )


def test_list_standard_domains_returns_sorted_unique_domains() -> None:
    assert list_standard_domains(make_library()) == (
        "Reading Informational Text",
        "Reading Literature",
        "Writing",
    )


def test_list_standard_category_paths_returns_sorted_unique_paths() -> None:
    assert list_standard_category_paths(make_library()) == (
        ("English Language Arts", "Reading Informational Text", "Close Reading"),
        ("English Language Arts", "Reading Literature", "Close Reading"),
        ("English Language Arts", "Writing"),
    )


def test_list_helpers_respect_active_filters() -> None:
    assert list_standard_sources(make_library(), active=False) == ("NJSLS-ELA",)
    assert list_standard_domains(make_library(), active=True) == (
        "Reading Literature",
        "Writing",
    )


def test_list_helpers_respect_available_module_filters() -> None:
    assert list_standard_subjects(
        make_library(),
        available_module="pds-scoreform",
    ) == ("English Language Arts",)
    assert list_standard_category_paths(
        make_library(),
        available_module="pds-quillan",
    ) == (
        ("English Language Arts", "Reading Informational Text", "Close Reading"),
        ("English Language Arts", "Reading Literature", "Close Reading"),
    )


def test_list_helpers_return_empty_tuple_for_empty_library() -> None:
    library = StandardsLibrary(standards=(), profiles=())

    assert list_standard_subjects(library) == ()
    assert list_standard_sources(library) == ()
    assert list_standard_domains(library) == ()
    assert list_standard_category_paths(library) == ()


def test_filter_standards_profiles_without_filters_preserves_order() -> None:
    library = make_library()

    assert filter_standards_profiles(library) == library.profiles


def test_filter_standards_profiles_by_subject() -> None:
    assert profile_ids(
        filter_standards_profiles(
            make_library(),
            subject="English Language Arts",
        )
    ) == ("english_12_njsls", "english_12_local")


def test_filter_standards_profiles_by_course() -> None:
    assert profile_ids(
        filter_standards_profiles(make_library(), course="English 12")
    ) == ("english_12_njsls", "english_12_local")


def test_filter_standards_profiles_by_source() -> None:
    assert profile_ids(
        filter_standards_profiles(make_library(), source="Local Writing Rubric")
    ) == ("english_12_local",)


def test_filter_standards_profiles_combines_filters_with_and_semantics() -> None:
    assert profile_ids(
        filter_standards_profiles(
            make_library(),
            subject="English Language Arts",
            course="English 12",
            source="NJSLS-ELA",
        )
    ) == ("english_12_njsls",)


def test_filter_standards_profiles_returns_empty_tuple_when_no_match() -> None:
    assert filter_standards_profiles(make_library(), course="Geometry") == ()


@pytest.mark.parametrize(
    ("filter_name", "value"),
    [
        ("subject", " "),
        ("course", " "),
        ("source", " "),
        ("source", 12),
    ],
)
def test_filter_standards_profiles_rejects_invalid_text_filter_values(
    filter_name: str,
    value: object,
) -> None:
    with pytest.raises(StandardsValidationError, match=filter_name):
        filter_standards_profiles(
            make_library(),
            **cast(Any, {filter_name: value}),
        )


def test_filter_standards_profiles_does_not_mutate_library() -> None:
    library = make_library()
    before = standards_library_to_dict(library)

    filter_standards_profiles(
        library,
        subject="English Language Arts",
        course="English 12",
    )

    assert standards_library_to_dict(library) == before


def test_existing_standards_library_shape_round_trips_unchanged() -> None:
    library = make_library()

    round_tripped = standards_library_from_dict(standards_library_to_dict(library))

    assert round_tripped == library
    assert round_tripped.profiles == library.profiles
    assert round_tripped.standards[0].domain == "Reading Literature"
    assert round_tripped.standards[0].tags == (
        "close_reading",
        "textual_evidence",
    )
