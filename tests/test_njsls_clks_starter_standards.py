"""Focused coverage for the 2020 NJSLS-CLKS starter standards pack."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace as dataclass_replace
from pathlib import Path

import pytest

from pds_core.standards import (
    StandardsLibrary,
    find_standard_definition,
    load_standards_library,
    standards_library_from_dict,
    standards_library_path,
    standards_library_to_dict,
)
from pds_core.standards_selection import (
    list_standards_for_profile_selection,
    list_standards_for_selection,
)
from pds_core.starter_standards import (
    StarterStandardsInstallError,
    install_starter_standards_library,
    list_starter_standards_packs,
    load_starter_standards_library,
    starter_standards_pack_metadata,
    validate_starter_standards_library,
)


PACK_ID = "njsls_clks_2020"
CSDT_PACK_ID = "njsls_csdt_2020"
ELA_PACK_ID = "njsls_ela_2023"
SOURCE = "2020 NJSLS-CLKS"
PFL_PROFILE_ID = "personal_financial_literacy_9_12_2020_njsls_clks"
CAREER_PROFILE_ID = "career_readiness_9_12_2020_njsls_clks"
LIFE_PROFILE_ID = "life_literacies_9_12_2020_njsls_clks"
COMBINED_PROFILE_ID = "clks_9_12_2020_njsls_clks"


def test_clks_starter_pack_is_discoverable_with_expected_metadata() -> None:
    packs = list_starter_standards_packs()

    assert [pack.pack_id for pack in packs] == [
        PACK_ID,
        CSDT_PACK_ID,
        ELA_PACK_ID,
    ]
    metadata = starter_standards_pack_metadata(PACK_ID)
    assert metadata.title == (
        "2020 NJSLS Career Readiness, Life Literacies and Key Skills "
        "Starter Standards"
    )
    assert metadata.source == SOURCE
    assert metadata.grade_bands == ("K-2", "3-5", "6-8", "9-12")
    assert metadata.courses == (
        "Personal Financial Literacy",
        "Career Awareness, Exploration, Preparation and Training",
        "Life Literacies and Key Skills",
    )
    assert metadata.standard_count == 301
    assert metadata.profile_count == 4
    assert metadata.profile_ids == (
        PFL_PROFILE_ID,
        CAREER_PROFILE_ID,
        LIFE_PROFILE_ID,
        COMBINED_PROFILE_ID,
    )
    assert metadata.framework_count == 1
    assert metadata.framework_ids == ("njsls_clks_2020",)


def test_clks_starter_pack_validates_complete_curated_source_structure() -> None:
    library = validate_starter_standards_library(PACK_ID)
    ids = [definition.standard_id for definition in library.standards]
    codes = [definition.code for definition in library.standards]

    assert len(ids) == len(set(ids)) == 301
    assert len(codes) == len(set(codes)) == 301
    assert all(standard_id.startswith("njsls-clks:") for standard_id in ids)
    assert all(code.startswith(("9.1.", "9.2.", "9.4.")) for code in codes)
    assert not any(code.startswith("9.3.") for code in codes)
    assert all(definition.source == SOURCE for definition in library.standards)
    assert all(definition.active for definition in library.standards)
    assert all(
        definition.available_modules == ("pds-quillan", "pds-scoreform")
        for definition in library.standards
    )

    assert Counter(definition.grade_band for definition in library.standards) == {
        "K-2": 37,
        "3-5": 55,
        "6-8": 102,
        "9-12": 107,
    }
    assert Counter(definition.subject for definition in library.standards) == {
        "Personal Financial Literacy": 125,
        "Career Awareness, Exploration, Preparation and Training": 56,
        "Life Literacies and Key Skills": 120,
    }


def test_clks_framework_provenance_matches_authoritative_2020_sources() -> None:
    framework = load_starter_standards_library(PACK_ID).frameworks[0]

    assert framework.framework_id == "njsls_clks_2020"
    assert framework.source == SOURCE
    assert framework.title == (
        "2020 New Jersey Student Learning Standards – Career Readiness, Life "
        "Literacies, and Key Skills"
    )
    assert framework.authority == "New Jersey State Board of Education"
    assert framework.publisher == "New Jersey Department of Education"
    assert framework.source_url == (
        "https://www.nj.gov/education/standards/clicks/Docs/2020NJSLS-CLKS.pdf"
    )
    assert framework.version == "2020"
    assert framework.adoption_date == "2020-06-03"
    assert framework.implementation_date == "2022-09"
    assert framework.supersedes == ()
    assert framework.license_name == "State of New Jersey Conditions of Use"
    assert framework.license_url == "https://nj.gov/nj/legal.shtml"
    assert framework.redistribution_notes is not None
    assert "copied, or distributed" in framework.redistribution_notes
    assert "third-party copyright" in framework.redistribution_notes


def test_clks_representative_official_codes_and_wording_are_preserved() -> None:
    library = load_starter_standards_library(PACK_ID)
    expected = {
        "9.1.2.CR.1": (
            "Recognize ways to volunteer in the classroom, school and community."
        ),
        "9.1.5.EG.2": "Describe how tax monies are spent",
        "9.1.8.CDM.1": (
            "Compare and contrast the use of credit cards and debit cards for "
            "specific purchases and the advantages and disadvantages of using each."
        ),
        "9.1.12.FI.1": "Identify ways to protect yourself from identify theft",
        "9.2.8.CAP.19": (
            "Relate academic achievement, as represented by high school diplomas, "
            "college degrees, and industry credentials, to employability and to "
            "potential level"
        ),
        "9.2.12.CAP.1": (
            "Analyze unemployment rates for workers with different levels of "
            "education and how the economic, social, and political conditions of a "
            "time period are affected by a recession."
        ),
        "9.4.12.DC.1": (
            "Explain the beneficial and harmful effects that intellectual property "
            "laws can have on the creation and sharing of content (e.g., "
            "6.1.12.CivicsPR.16.a)."
        ),
        "9.4.12.TL.1": (
            "Assess digital tools based on features such as accessibility options, "
            "capacities, and utility for accomplishing a specified task (e.g., "
            "W.11-12.6.)."
        ),
    }

    for code, description in expected.items():
        definition = find_standard_definition(library, f"njsls-clks:{code}")
        assert definition is not None
        assert definition.code == code
        assert definition.description == description


def test_clks_preserves_grade_two_career_code_under_the_9_2_source_section() -> None:
    library = load_starter_standards_library(PACK_ID)
    definition = find_standard_definition(library, "njsls-clks:9.1.2.CAP.1")

    assert definition is not None
    assert definition.code == "9.1.2.CAP.1"
    assert definition.subject == (
        "Career Awareness, Exploration, Preparation and Training"
    )
    assert definition.domain == "Career Awareness and Planning"
    assert definition.category_path[2] == (
        "9.2 Career Awareness, Exploration, Preparation and Training"
    )
    assert "standard_9_2" in definition.tags
    assert definition.description == (
        "Make a list of different types of jobs and describe the skills associated "
        "with each job."
    )


def test_clks_preserves_published_gca_colon_code() -> None:
    library = load_starter_standards_library(PACK_ID)
    definition = find_standard_definition(library, "njsls-clks:9.4.2.GCA:1")

    assert definition is not None
    assert definition.code == "9.4.2.GCA:1"
    assert definition.domain == "Global and Cultural Awareness"
    assert definition.subject == "Life Literacies and Key Skills"
    assert definition.category_path[-1] == definition.domain
    assert "disciplinary_concept:gca" in definition.tags


def test_clks_keeps_published_abbreviation_variation_without_spaces() -> None:
    library = load_starter_standards_library(PACK_ID)

    cases = {
        "9.1.5.EG.4": "Economic and Government Influences",
        "9.1.5.RMI.1": "Risk Management and Insurance",
        "9.1.8.RM.1": "Risk Management and Insurance",
        "9.1.12.CFR.1": "Civic Financial Responsibility",
    }
    for code, domain in cases.items():
        definition = find_standard_definition(library, f"njsls-clks:{code}")
        assert definition is not None
        assert definition.code == code
        assert " " not in definition.code
        assert definition.domain == domain


def test_clks_preserves_embedded_interdisciplinary_reference_text() -> None:
    library = load_starter_standards_library(PACK_ID)
    definition = find_standard_definition(library, "njsls-clks:9.4.12.IML.2")

    assert definition is not None
    assert definition.description == (
        "Evaluate digital sources for timeliness, accuracy, perspective, "
        "credibility of the source, and relevance of information, in media, data, "
        "or other resources (e.g., NJSLSA.W8, Social Studies Practice: Gathering "
        "and Evaluating Sources."
    )


def test_clks_high_school_profiles_are_complete_source_ordered_pools() -> None:
    library = load_starter_standards_library(PACK_ID)
    profiles = {profile.profile_id: profile for profile in library.profiles}

    pfl = profiles[PFL_PROFILE_ID]
    career = profiles[CAREER_PROFILE_ID]
    life = profiles[LIFE_PROFILE_ID]
    combined = profiles[COMBINED_PROFILE_ID]

    assert len(pfl.standards) == 55
    assert len(career.standards) == 23
    assert len(life.standards) == 29
    assert len(combined.standards) == len(set(combined.standards)) == 107

    assert pfl.standards == tuple(
        definition.standard_id
        for definition in library.standards
        if definition.subject == "Personal Financial Literacy"
        and definition.grade_band == "9-12"
    )
    assert career.standards == tuple(
        definition.standard_id
        for definition in library.standards
        if definition.subject
        == "Career Awareness, Exploration, Preparation and Training"
        and definition.grade_band == "9-12"
    )
    assert life.standards == tuple(
        definition.standard_id
        for definition in library.standards
        if definition.subject == "Life Literacies and Key Skills"
        and definition.grade_band == "9-12"
    )
    assert combined.standards == pfl.standards + career.standards + life.standards


def test_clks_library_round_trip_preserves_framework_standards_and_profiles() -> None:
    library = load_starter_standards_library(PACK_ID)

    restored = standards_library_from_dict(standards_library_to_dict(library))

    assert restored == library


def test_clks_selection_helpers_filter_and_resolve_shared_records() -> None:
    library = load_starter_standards_library(PACK_ID)

    media = list_standards_for_selection(
        library,
        source=SOURCE,
        subject="Life Literacies and Key Skills",
        domain="Information and Media Literacy",
        available_module="pds-scoreform",
    )
    assert len(media) == 35
    assert {item.source for item in media} == {SOURCE}
    assert {item.subject for item in media} == {"Life Literacies and Key Skills"}
    assert {item.domain for item in media} == {"Information and Media Literacy"}

    combined = list_standards_for_profile_selection(
        library,
        COMBINED_PROFILE_ID,
        available_module="pds-quillan",
    )
    assert len(combined) == 107
    assert combined[0].standard_id == "njsls-clks:9.1.12.CFR.1"
    assert combined[55].standard_id == "njsls-clks:9.2.12.CAP.1"
    assert combined[78].standard_id == "njsls-clks:9.4.12.CI.1"


def test_clks_install_is_idempotent_and_writes_only_shared_library(tmp_path: Path) -> None:
    first = install_starter_standards_library(
        tmp_path,
        PACK_ID,
        StandardsLibrary(standards=()),
    )
    before = standards_library_path(tmp_path).read_text(encoding="utf-8")
    second = install_starter_standards_library(
        tmp_path,
        PACK_ID,
        load_standards_library(standards_library_path(tmp_path)),
    )

    assert first.standards_added == 301
    assert first.profiles_added == 4
    assert first.frameworks_added == 1
    assert first.changed_count == 306
    assert second.standards_skipped == 301
    assert second.profiles_skipped == 4
    assert second.frameworks_skipped == 1
    assert second.changed_count == 0
    assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "classes").exists()
    assert not (tmp_path / "assignments").exists()
    assert not (tmp_path / "pds-quillan").exists()
    assert not (tmp_path / "pds-scoreform").exists()


@pytest.mark.parametrize(
    "pack_order",
    [
        (PACK_ID, CSDT_PACK_ID, ELA_PACK_ID),
        (CSDT_PACK_ID, ELA_PACK_ID, PACK_ID),
    ],
)
def test_clks_csdt_and_ela_packs_coexist_without_collisions(
    tmp_path: Path,
    pack_order: tuple[str, str, str],
) -> None:
    library = StandardsLibrary(standards=())
    for pack_id in pack_order:
        install_starter_standards_library(tmp_path, pack_id, library)
        library = load_standards_library(standards_library_path(tmp_path))

    assert len(library.standards) == 301 + 163 + 135
    assert len(library.profiles) == 4 + 2 + 2
    assert len(library.frameworks) == 3
    assert {framework.framework_id for framework in library.frameworks} == {
        "njsls_clks_2020",
        "njsls_csdt_2020",
        "njsls_ela_2023",
    }
    assert len({definition.standard_id for definition in library.standards}) == 599
    assert len({profile.profile_id for profile in library.profiles}) == 8

    assert find_standard_definition(library, "njsls-clks:9.4.12.IML.2") is not None
    assert find_standard_definition(library, "njsls-csdt:8.1.12.AP.1") is not None
    assert find_standard_definition(library, "njsls-ela:L.SS.9-10.1") is not None

    for pack_id in (PACK_ID, CSDT_PACK_ID, ELA_PACK_ID):
        before = standards_library_path(tmp_path).read_text(encoding="utf-8")
        result = install_starter_standards_library(tmp_path, pack_id, library)
        assert result.changed_count == 0
        assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before


def test_clks_standard_conflict_is_atomic_and_requires_explicit_overwrite(
    tmp_path: Path,
) -> None:
    starter = load_starter_standards_library(PACK_ID)
    conflict = dataclass_replace(
        starter.standards[0],
        description="Teacher-edited local wording.",
    )
    existing = StandardsLibrary(standards=(conflict,))

    with pytest.raises(StarterStandardsInstallError) as caught:
        install_starter_standards_library(tmp_path, PACK_ID, existing)

    assert caught.value.result.standard_conflicts == (starter.standards[0].standard_id,)
    assert not standards_library_path(tmp_path).exists()

    result = install_starter_standards_library(
        tmp_path,
        PACK_ID,
        existing,
        overwrite_conflicts=True,
    )
    assert result.standards_overwritten == 1
    installed = load_standards_library(standards_library_path(tmp_path))
    assert installed.standards[0] == starter.standards[0]


def test_clks_profile_and_framework_conflicts_are_atomic(tmp_path: Path) -> None:
    starter = load_starter_standards_library(PACK_ID)
    profile_conflict = dataclass_replace(
        starter.profiles[0],
        title="Teacher-edited profile title.",
    )
    framework_conflict = dataclass_replace(
        starter.frameworks[0],
        title="Teacher-edited framework title.",
    )
    existing = StandardsLibrary(
        standards=starter.standards,
        profiles=(profile_conflict,),
        frameworks=(framework_conflict,),
    )

    with pytest.raises(StarterStandardsInstallError) as caught:
        install_starter_standards_library(tmp_path, PACK_ID, existing)

    assert caught.value.result.profile_conflicts == (PFL_PROFILE_ID,)
    assert caught.value.result.framework_conflicts == ("njsls_clks_2020",)
    assert not standards_library_path(tmp_path).exists()

    result = install_starter_standards_library(
        tmp_path,
        PACK_ID,
        existing,
        overwrite_conflicts=True,
    )
    assert result.profiles_overwritten == 1
    assert result.frameworks_overwritten == 1
    assert not result.has_conflicts
