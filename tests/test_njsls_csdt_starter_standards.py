"""Focused coverage for the 2020 NJSLS-CS&DT starter standards pack."""

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


PACK_ID = "njsls_csdt_2020"
ELA_PACK_ID = "njsls_ela_2023"
SOURCE = "2020 NJSLS-CS&DT"
CS_PROFILE_ID = "computer_science_9_12_2020_njsls_csdt"
DT_PROFILE_ID = "design_thinking_9_12_2020_njsls_csdt"


def test_csdt_starter_pack_is_discoverable_with_expected_metadata() -> None:
    packs = list_starter_standards_packs()

    assert [pack.pack_id for pack in packs] == [PACK_ID, ELA_PACK_ID]
    metadata = starter_standards_pack_metadata(PACK_ID)
    assert metadata.title == (
        "2020 NJSLS Computer Science and Design Thinking Starter Standards"
    )
    assert metadata.source == SOURCE
    assert metadata.grade_bands == ("K-2", "3-5", "6-8", "9-12")
    assert metadata.courses == ("Computer Science", "Design Thinking")
    assert metadata.standard_count == 163
    assert metadata.profile_count == 2
    assert metadata.profile_ids == (CS_PROFILE_ID, DT_PROFILE_ID)
    assert metadata.framework_count == 1
    assert metadata.framework_ids == ("njsls_csdt_2020",)


def test_csdt_starter_pack_validates_complete_source_structure() -> None:
    library = validate_starter_standards_library(PACK_ID)
    ids = [definition.standard_id for definition in library.standards]
    codes = [definition.code for definition in library.standards]

    assert len(ids) == len(set(ids)) == 163
    assert len(codes) == len(set(codes)) == 163
    assert all(standard_id.startswith("njsls-csdt:") for standard_id in ids)
    assert all(code.startswith(("8.1.", "8.2.")) for code in codes)
    assert all(definition.source == SOURCE for definition in library.standards)
    assert all(definition.active for definition in library.standards)
    assert all(
        definition.available_modules == ("pds-quillan", "pds-scoreform")
        for definition in library.standards
    )

    assert Counter(definition.grade_band for definition in library.standards) == {
        "K-2": 34,
        "3-5": 38,
        "6-8": 47,
        "9-12": 44,
    }
    assert Counter(definition.subject for definition in library.standards) == {
        "Computer Science": 87,
        "Design Thinking": 76,
    }
    assert Counter(definition.domain for definition in library.standards) == {
        "Computing Systems": 14,
        "Networks and the Internet": 14,
        "Impacts of Computing": 8,
        "Data & Analysis": 21,
        "Algorithms & Programming": 30,
        "Engineering Design": 23,
        "Interaction of Technology and Humans": 17,
        "Nature of Technology": 12,
        "Effects of Technology on the Natural World": 17,
        "Ethics & Culture": 7,
    }


def test_csdt_framework_provenance_matches_authoritative_2020_sources() -> None:
    framework = load_starter_standards_library(PACK_ID).frameworks[0]

    assert framework.framework_id == "njsls_csdt_2020"
    assert framework.source == SOURCE
    assert framework.title == (
        "2020 New Jersey Student Learning Standards – Computer Science and Design Thinking"
    )
    assert framework.authority == "New Jersey State Board of Education"
    assert framework.publisher == "New Jersey Department of Education"
    assert framework.source_url == (
        "https://www.nj.gov/education/standards/compsci/Docs/"
        "2020%20NJSLS-CSDT.pdf"
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


def test_csdt_representative_official_codes_and_wording_are_preserved() -> None:
    library = load_starter_standards_library(PACK_ID)
    expected = {
        "8.1.2.CS.1": (
            "Select and operate computing devices that perform a variety of tasks "
            "accurately and quickly based on user needs and preferences."
        ),
        "8.1.5.DA.4": (
            "Organize and present climate change data visually to highlight "
            "relationships or support a claim."
        ),
        "8.1.8.AP.7": (
            "Design programs, incorporating existing code, media, and libraries, "
            "and give attribution."
        ),
        "8.1.12.DA.3": "Translate between decimal numbers and binary numbers.",
        "8.2.2.ETW.4": (
            "Explain how the disposal of or reusing a product affects the local "
            "and global environment."
        ),
        "8.2.8.EC.2": (
            "Examine the effects of ethical and unethical practices in product "
            "design and development."
        ),
        "8.2.12.ED.5": (
            "Evaluate the effectiveness of a product or system based on factors "
            "that are related to its requirements, specifications, and constraints "
            "(e.g., safety, reliability, economic considerations, quality control, "
            "environmental concerns, manufacturability, maintenance and repair, "
            "ergonomics)."
        ),
    }

    for code, description in expected.items():
        definition = find_standard_definition(library, f"njsls-csdt:{code}")
        assert definition is not None
        assert definition.code == code
        assert definition.description == description


def test_csdt_etw4_preserves_published_code_despite_source_table_placement() -> None:
    library = load_starter_standards_library(PACK_ID)
    definition = find_standard_definition(library, "njsls-csdt:8.2.12.ETW.4")

    assert definition is not None
    assert definition.code == "8.2.12.ETW.4"
    assert definition.domain == "Effects of Technology on the Natural World"
    assert definition.subject == "Design Thinking"
    assert definition.category_path[-1] == definition.domain
    assert "disciplinary_concept:etw" in definition.tags
    assert definition.description == (
        "Research historical tensions between environmental and economic "
        "considerations as driven by human needs and wants in the development "
        "of a technological product and present the competing viewpoints."
    )


def test_csdt_high_school_profiles_are_complete_source_ordered_pools() -> None:
    library = load_starter_standards_library(PACK_ID)
    profiles = {profile.profile_id: profile for profile in library.profiles}

    cs_profile = profiles[CS_PROFILE_ID]
    dt_profile = profiles[DT_PROFILE_ID]
    assert len(cs_profile.standards) == 26
    assert len(dt_profile.standards) == 18
    assert cs_profile.standards == tuple(
        definition.standard_id
        for definition in library.standards
        if definition.code.startswith("8.1.12.")
    )
    assert dt_profile.standards == tuple(
        definition.standard_id
        for definition in library.standards
        if definition.code.startswith("8.2.12.")
    )
    assert all("ap_csp" not in profile.profile_id for profile in library.profiles)
    assert all("computer_science_principles" not in profile.profile_id for profile in library.profiles)


def test_csdt_library_round_trip_preserves_framework_standards_and_profiles() -> None:
    library = load_starter_standards_library(PACK_ID)

    restored = standards_library_from_dict(standards_library_to_dict(library))

    assert restored == library


def test_csdt_selection_helpers_filter_and_resolve_shared_records() -> None:
    library = load_starter_standards_library(PACK_ID)

    ap = list_standards_for_selection(
        library,
        source=SOURCE,
        subject="Computer Science",
        domain="Algorithms & Programming",
        available_module="pds-scoreform",
    )
    assert len(ap) == 30
    assert {item.source for item in ap} == {SOURCE}
    assert {item.subject for item in ap} == {"Computer Science"}
    assert {item.domain for item in ap} == {"Algorithms & Programming"}

    cs_high_school = list_standards_for_profile_selection(
        library,
        CS_PROFILE_ID,
        available_module="pds-quillan",
    )
    dt_high_school = list_standards_for_profile_selection(
        library,
        DT_PROFILE_ID,
        available_module="pds-scoreform",
    )
    assert len(cs_high_school) == 26
    assert len(dt_high_school) == 18
    assert cs_high_school[0].standard_id == "njsls-csdt:8.1.12.CS.1"
    assert dt_high_school[0].standard_id == "njsls-csdt:8.2.12.ED.1"


def test_csdt_install_is_idempotent_and_writes_only_shared_library(tmp_path: Path) -> None:
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

    assert first.standards_added == 163
    assert first.profiles_added == 2
    assert first.frameworks_added == 1
    assert first.changed_count == 166
    assert second.standards_skipped == 163
    assert second.profiles_skipped == 2
    assert second.frameworks_skipped == 1
    assert second.changed_count == 0
    assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "classes").exists()
    assert not (tmp_path / "assignments").exists()
    assert not (tmp_path / "pds-quillan").exists()
    assert not (tmp_path / "pds-scoreform").exists()


@pytest.mark.parametrize("first_pack, second_pack", [(PACK_ID, ELA_PACK_ID), (ELA_PACK_ID, PACK_ID)])
def test_csdt_and_ela_packs_coexist_in_either_install_order(
    tmp_path: Path,
    first_pack: str,
    second_pack: str,
) -> None:
    install_starter_standards_library(
        tmp_path,
        first_pack,
        StandardsLibrary(standards=()),
    )
    install_starter_standards_library(
        tmp_path,
        second_pack,
        load_standards_library(standards_library_path(tmp_path)),
    )
    combined = load_standards_library(standards_library_path(tmp_path))

    assert len(combined.standards) == 135 + 163
    assert len(combined.profiles) == 2 + 2
    assert len(combined.frameworks) == 2
    assert {framework.framework_id for framework in combined.frameworks} == {
        "njsls_ela_2023",
        "njsls_csdt_2020",
    }
    assert find_standard_definition(combined, "njsls-ela:L.SS.9-10.1") is not None
    assert find_standard_definition(combined, "njsls-csdt:8.1.12.AP.1") is not None

    before = standards_library_path(tmp_path).read_text(encoding="utf-8")
    result = install_starter_standards_library(tmp_path, second_pack, combined)
    assert result.changed_count == 0
    assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before


def test_csdt_standard_conflict_is_atomic_and_requires_explicit_overwrite(
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


def test_csdt_profile_and_framework_conflicts_are_atomic(tmp_path: Path) -> None:
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

    assert caught.value.result.profile_conflicts == (CS_PROFILE_ID,)
    assert caught.value.result.framework_conflicts == ("njsls_csdt_2020",)
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
