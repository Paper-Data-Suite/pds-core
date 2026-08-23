"""Focused coverage for the AP Computer Science Principles Fall 2023 reference pack."""

from __future__ import annotations

import re
from dataclasses import replace as dataclass_replace
from pathlib import Path

import pytest

from pds_core.standards import (
    StandardsLibrary,
    StandardsProfile,
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

PACK_ID = "ap_csp_fall_2023"
CLKS_PACK_ID = "njsls_clks_2020"
CSDT_PACK_ID = "njsls_csdt_2020"
ELA_PACK_ID = "njsls_ela_2023"
SOURCE = "College Board AP CSP Fall 2023"
CONTENT_PROFILE_ID = "ap_csp_course_content_fall_2023"
THINKING_PROFILE_ID = "ap_csp_computational_thinking_fall_2023"
COMBINED_PROFILE_ID = "ap_csp_fall_2023"
EXPECTED_LO_CODES = (
    'CRD-1.A',
    'CRD-1.B',
    'CRD-1.C',
    'CRD-2.A',
    'CRD-2.B',
    'CRD-2.C',
    'CRD-2.D',
    'CRD-2.E',
    'CRD-2.F',
    'CRD-2.G',
    'CRD-2.H',
    'CRD-2.I',
    'CRD-2.J',
    'DAT-1.A',
    'DAT-1.B',
    'DAT-1.C',
    'DAT-1.D',
    'DAT-2.A',
    'DAT-2.B',
    'DAT-2.C',
    'DAT-2.D',
    'DAT-2.E',
    'AAP-1.A',
    'AAP-1.B',
    'AAP-1.C',
    'AAP-1.D',
    'AAP-2.A',
    'AAP-2.B',
    'AAP-2.C',
    'AAP-2.D',
    'AAP-2.E',
    'AAP-2.F',
    'AAP-2.G',
    'AAP-2.H',
    'AAP-2.I',
    'AAP-2.J',
    'AAP-2.K',
    'AAP-2.L',
    'AAP-2.M',
    'AAP-2.N',
    'AAP-3.A',
    'AAP-3.B',
    'AAP-3.C',
    'AAP-3.D',
    'AAP-3.E',
    'AAP-3.F',
    'AAP-4.A',
    'AAP-4.B',
    'CSN-1.A',
    'CSN-1.B',
    'CSN-1.C',
    'CSN-1.D',
    'CSN-1.E',
    'CSN-2.A',
    'CSN-2.B',
    'IOC-1.A',
    'IOC-1.B',
    'IOC-1.C',
    'IOC-1.D',
    'IOC-1.E',
    'IOC-1.F',
    'IOC-2.A',
    'IOC-2.B',
    'IOC-2.C',
)
EXPECTED_SKILL_CODES = (
    "1.A", "1.B", "1.C", "1.D",
    "2.A", "2.B",
    "3.A", "3.B", "3.C",
    "4.A", "4.B", "4.C",
    "5.A", "5.B", "5.C", "5.D", "5.E",
    "6.A", "6.B", "6.C",
)


def test_ap_csp_pack_is_discoverable_with_reference_metadata() -> None:
    packs = list_starter_standards_packs()
    assert [pack.pack_id for pack in packs] == [
        PACK_ID,
        CLKS_PACK_ID,
        CSDT_PACK_ID,
        ELA_PACK_ID,
    ]
    metadata = starter_standards_pack_metadata(PACK_ID)
    assert metadata.title == "AP Computer Science Principles Fall 2023 Framework References"
    assert metadata.source == SOURCE
    assert metadata.grade_bands == ()
    assert metadata.courses == ("AP Computer Science Principles",)
    assert metadata.standard_count == 95
    assert metadata.profile_count == 3
    assert metadata.profile_ids == (
        CONTENT_PROFILE_ID,
        THINKING_PROFILE_ID,
        COMBINED_PROFILE_ID,
    )
    assert metadata.framework_count == 1
    assert metadata.framework_ids == ("ap_csp_fall_2023",)


def test_ap_csp_pack_contains_exact_reference_roles_and_identifier_counts() -> None:
    library = validate_starter_standards_library(PACK_ID)
    assert len(library.standards) == 95
    assert len({item.standard_id for item in library.standards}) == 95
    assert all(item.standard_id.startswith("ap-csp-2023:") for item in library.standards)
    assert all(item.source == SOURCE for item in library.standards)
    assert all(item.subject == "Computer Science" for item in library.standards)
    assert all(item.course == "AP Computer Science Principles" for item in library.standards)
    assert all(item.grade_band is None for item in library.standards)
    assert all(
        item.available_modules == ("pds-quillan", "pds-scoreform")
        for item in library.standards
    )

    big_ideas = [item for item in library.standards if "big_idea" in item.tags]
    los = [
        item
        for item in library.standards
        if "learning_objective_reference" in item.tags
    ]
    practices = [
        item
        for item in library.standards
        if "computational_thinking_practice" in item.tags
    ]
    skills = [
        item
        for item in library.standards
        if "computational_thinking_skill" in item.tags
    ]
    assert [item.code for item in big_ideas] == ["CRD", "DAT", "AAP", "CSN", "IOC"]
    assert tuple(item.code for item in los) == EXPECTED_LO_CODES
    assert tuple(item.code for item in skills) == EXPECTED_SKILL_CODES
    assert len(practices) == 6


def test_ap_csp_framework_metadata_preserves_fall_version_without_invented_date() -> None:
    framework = load_starter_standards_library(PACK_ID).frameworks[0]
    assert framework.framework_id == "ap_csp_fall_2023"
    assert framework.source == SOURCE
    assert framework.title == "AP Computer Science Principles Course and Exam Description"
    assert framework.authority == "College Board"
    assert framework.publisher == "College Board"
    assert framework.version == "Fall 2023"
    assert framework.adoption_date is None
    assert framework.implementation_date is None
    assert framework.supersedes == ()
    assert framework.license_name == "College Board Educator Legal Terms"
    assert framework.license_url == "https://privacy.collegeboard.org/educator-legal-terms"
    assert framework.redistribution_notes is not None
    assert "protected framework prose" in framework.redistribution_notes


def test_ap_csp_big_ideas_and_practices_use_minimal_structural_titles() -> None:
    library = load_starter_standards_library(PACK_ID)
    expected = {
        "ap-csp-2023:big-idea:crd": ("CRD", "Big Idea 1: Creative Development"),
        "ap-csp-2023:big-idea:dat": ("DAT", "Big Idea 2: Data"),
        "ap-csp-2023:big-idea:aap": ("AAP", "Big Idea 3: Algorithms and Programming"),
        "ap-csp-2023:big-idea:csn": ("CSN", "Big Idea 4: Computer Systems and Networks"),
        "ap-csp-2023:big-idea:ioc": ("IOC", "Big Idea 5: Impact of Computing"),
        "ap-csp-2023:practice:1": (
            "Practice 1",
            "Practice 1: Computational Solution Design",
        ),
        "ap-csp-2023:practice:6": (
            "Practice 6",
            "Practice 6: Responsible Computing",
        ),
    }
    for standard_id, (code, short_name) in expected.items():
        item = find_standard_definition(library, standard_id)
        assert item is not None
        assert item.code == code
        assert item.short_name == short_name
        assert "Consult the official" in item.description
        assert "official_prose_not_redistributed" in item.tags


def test_ap_csp_learning_objectives_and_skills_use_fixed_reference_templates() -> None:
    library = load_starter_standards_library(PACK_ID)
    for item in library.standards:
        if "learning_objective_reference" in item.tags:
            assert item.short_name == f"Learning Objective {item.code}"
            assert item.description == (
                f"Reference to College Board AP CSP Learning Objective {item.code}. "
                "Consult the official Fall 2023 Course and Exam Description for "
                "authoritative wording."
            )
        if "computational_thinking_skill" in item.tags:
            assert item.short_name == f"Computational Thinking Skill {item.code}"
            assert item.description == (
                "Reference to College Board AP CSP Computational Thinking Skill "
                f"{item.code}. Consult the official Fall 2023 Course and Exam "
                "Description for authoritative wording."
            )


def test_ap_csp_pack_does_not_bundle_essential_knowledge_or_assessment_material() -> None:
    library = load_starter_standards_library(PACK_ID)
    assert not any(
        re.fullmatch(r"[A-Z]{3}-\d+\.[A-Z]\.\d+", item.code)
        for item in library.standards
    )
    text = "\n".join(item.description for item in library.standards).lower()
    for forbidden in (
        "essential knowledge",
        "scoring guideline",
        "ap classroom",
        "create performance task directions",
    ):
        assert forbidden not in text


def test_ap_csp_profiles_preserve_two_axis_structure_and_combined_pool() -> None:
    library = load_starter_standards_library(PACK_ID)
    profiles = {item.profile_id: item for item in library.profiles}
    content = profiles[CONTENT_PROFILE_ID]
    thinking = profiles[THINKING_PROFILE_ID]
    combined = profiles[COMBINED_PROFILE_ID]
    assert len(content.standards) == 69
    assert len(thinking.standards) == 26
    assert len(combined.standards) == 95
    assert combined.standards == content.standards + thinking.standards
    assert content.standards[0] == "ap-csp-2023:big-idea:crd"
    assert content.standards[1] == "ap-csp-2023:lo:CRD-1.A"
    assert thinking.standards[0] == "ap-csp-2023:practice:1"
    assert thinking.standards[1] == "ap-csp-2023:skill:1.A"


def test_ap_csp_library_round_trip_is_exact() -> None:
    library = load_starter_standards_library(PACK_ID)
    assert standards_library_from_dict(standards_library_to_dict(library)) == library


def test_ap_csp_selection_helpers_filter_reference_records() -> None:
    library = load_starter_standards_library(PACK_ID)
    content = list_standards_for_selection(
        library,
        source=SOURCE,
        subject="Computer Science",
        domain="Course Content",
        available_module="pds-scoreform",
    )
    thinking = list_standards_for_profile_selection(
        library,
        THINKING_PROFILE_ID,
        available_module="pds-quillan",
    )
    assert len(content) == 69
    assert len(thinking) == 26
    assert thinking[0].standard_id == "ap-csp-2023:practice:1"


def test_ap_csp_install_is_idempotent_and_writes_only_shared_library(
    tmp_path: Path,
) -> None:
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
    assert first.standards_added == 95
    assert first.profiles_added == 3
    assert first.frameworks_added == 1
    assert first.changed_count == 99
    assert second.standards_skipped == 95
    assert second.profiles_skipped == 3
    assert second.frameworks_skipped == 1
    assert second.changed_count == 0
    assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before
    assert not (tmp_path / "standards" / "usage").exists()


@pytest.mark.parametrize(
    "pack_order",
    [
        (PACK_ID, CLKS_PACK_ID, CSDT_PACK_ID, ELA_PACK_ID),
        (CLKS_PACK_ID, CSDT_PACK_ID, ELA_PACK_ID, PACK_ID),
    ],
)
def test_ap_csp_coexists_with_all_bundled_packs(
    tmp_path: Path,
    pack_order: tuple[str, ...],
) -> None:
    library = StandardsLibrary(standards=())
    for pack_id in pack_order:
        install_starter_standards_library(tmp_path, pack_id, library)
        library = load_standards_library(standards_library_path(tmp_path))
    assert len(library.standards) == 95 + 301 + 163 + 135
    assert len(library.profiles) == 3 + 4 + 2 + 2
    assert len(library.frameworks) == 4
    assert len({item.standard_id for item in library.standards}) == 694
    assert len({item.profile_id for item in library.profiles}) == 11
    assert {item.framework_id for item in library.frameworks} == {
        "ap_csp_fall_2023",
        "njsls_clks_2020",
        "njsls_csdt_2020",
        "njsls_ela_2023",
    }


def test_mixed_ap_njsls_local_profile_works_with_existing_selection_contract() -> None:
    ap = load_starter_standards_library(PACK_ID)
    csdt = load_starter_standards_library(CSDT_PACK_ID)
    combined = StandardsLibrary(
        standards=ap.standards + csdt.standards,
        profiles=ap.profiles + csdt.profiles,
        frameworks=ap.frameworks + csdt.frameworks,
    )
    mixed = StandardsProfile(
        profile_id="local_ap_csp_njsls_example",
        standards=(
            "ap-csp-2023:lo:AAP-2.A",
            "njsls-csdt:8.1.12.AP.1",
        ),
        subject="Computer Science",
        course="Local AP CSP alignment example",
        title="Local AP CSP / NJSLS example",
    )
    with_mixed = StandardsLibrary(
        standards=combined.standards,
        profiles=combined.profiles + (mixed,),
        frameworks=combined.frameworks,
    )
    assert [
        item.standard_id
        for item in list_standards_for_profile_selection(
            with_mixed,
            mixed.profile_id,
            available_module="pds-quillan",
        )
    ] == list(mixed.standards)
    assert [
        item.standard_id
        for item in list_standards_for_profile_selection(
            with_mixed,
            mixed.profile_id,
            available_module="pds-scoreform",
        )
    ] == list(mixed.standards)
    assert standards_library_from_dict(standards_library_to_dict(with_mixed)) == with_mixed


def test_ap_csp_conflicts_are_atomic_and_explicit_overwrite_is_required(
    tmp_path: Path,
) -> None:
    starter = load_starter_standards_library(PACK_ID)
    standard_conflict = dataclass_replace(
        starter.standards[0],
        description="Local edit.",
    )
    profile_conflict = dataclass_replace(
        starter.profiles[0],
        title="Local profile edit.",
    )
    framework_conflict = dataclass_replace(
        starter.frameworks[0],
        title="Local framework edit.",
    )
    existing = StandardsLibrary(
        standards=(standard_conflict,) + starter.standards[1:],
        profiles=(profile_conflict,) + starter.profiles[1:],
        frameworks=(framework_conflict,) + starter.frameworks[1:],
    )
    with pytest.raises(StarterStandardsInstallError) as caught:
        install_starter_standards_library(tmp_path, PACK_ID, existing)
    assert caught.value.result.standard_conflicts == (
        starter.standards[0].standard_id,
    )
    assert caught.value.result.profile_conflicts == (CONTENT_PROFILE_ID,)
    assert caught.value.result.framework_conflicts == ("ap_csp_fall_2023",)
    assert not standards_library_path(tmp_path).exists()

    result = install_starter_standards_library(
        tmp_path,
        PACK_ID,
        existing,
        overwrite_conflicts=True,
    )
    assert result.standards_overwritten == 1
    assert result.profiles_overwritten == 1
    assert result.frameworks_overwritten == 1
    assert not result.has_conflicts


def test_alignment_document_is_explicitly_pds_curated_and_non_equivalent() -> None:
    text = (
        Path(__file__).parents[1] / "docs" / "ap_csp_njsls_alignment.md"
    ).read_text(encoding="utf-8")
    assert "Paper Data Suite-curated" in text
    assert "not an official College Board or NJDOE crosswalk" in text
    assert "does not assert equivalence" in text
    assert "ap-csp-2023:big-idea:aap" in text
    assert "njsls-csdt:8.1.12.AP.1" in text
