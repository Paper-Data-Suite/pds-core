"""Release-blocking multi-framework standards audit for Core v0.6.3."""

from __future__ import annotations

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
    list_profiles_for_selection,
    list_standards_for_profile_selection,
    list_standards_for_selection,
)
from pds_core.starter_standards import (
    StarterStandardsInstallError,
    install_starter_standards_library,
    load_starter_standards_library,
)

AP = "ap_csp_fall_2023"
CLKS = "njsls_clks_2020"
CSDT = "njsls_csdt_2020"
ELA = "njsls_ela_2023"
PACKS = (AP, CLKS, CSDT, ELA)
ENGLISH11 = "english11_2023_njsls_ela"
ENGLISH12 = "english12_2023_njsls_ela"


def _install(root: Path, order: tuple[str, ...]) -> StandardsLibrary:
    library = StandardsLibrary(standards=())
    for pack_id in order:
        install_starter_standards_library(root, pack_id, library)
        library = load_standards_library(standards_library_path(root))
    return library


def _semantic_signature(library: StandardsLibrary) -> tuple[dict[str, object], ...]:
    return (
        {item.standard_id: item for item in library.standards},
        {item.profile_id: item for item in library.profiles},
        {item.framework_id: item for item in library.frameworks},
    )


def test_english11_profile_reuses_existing_11_12_definitions_without_duplication() -> None:
    library = load_starter_standards_library(ELA)
    profiles = {item.profile_id: item for item in library.profiles}
    english11 = profiles[ENGLISH11]
    english12 = profiles[ENGLISH12]

    assert len(library.standards) == 135
    assert len(library.profiles) == 3
    assert len(english11.standards) == 67
    assert english11.standards == english12.standards
    assert english11.course == "English 11"
    assert english12.course == "English 12"
    assert all(standard_id.startswith("njsls-ela:") for standard_id in english11.standards)
    by_id = {item.standard_id: item for item in library.standards}
    assert {by_id[standard_id].grade_band for standard_id in english11.standards} == {"11-12"}


def test_english11_course_filter_uses_profile_membership_without_rewriting_legacy_definitions() -> None:
    library = load_starter_standards_library(ELA)
    profiles = {item.profile_id: item for item in library.profiles}
    representative = find_standard_definition(library, "njsls-ela:RL.CR.11-12.1")
    assert representative is not None
    # Preserve the released starter record so existing workspaces upgrade additively.
    assert representative.course == "English 12"

    english11 = list_standards_for_selection(
        library,
        source="2023 NJSLS-ELA",
        course="English 11",
        available_module="pds-quillan",
    )
    english12 = list_standards_for_selection(
        library,
        source="2023 NJSLS-ELA",
        course="English 12",
        available_module="pds-scoreform",
    )
    assert len(english11) == len(english12) == 67
    assert {item.standard_id for item in english11} == set(profiles[ENGLISH11].standards)
    assert {item.standard_id for item in english12} == set(profiles[ENGLISH12].standards)

    selected_profiles = list_profiles_for_selection(library, course="English 11")
    assert [item.profile_id for item in selected_profiles] == [ENGLISH11]


def test_pre_218_ela_workspace_upgrades_by_adding_only_english11_profile(tmp_path: Path) -> None:
    current = load_starter_standards_library(ELA)
    previous = StandardsLibrary(
        standards=current.standards,
        profiles=tuple(profile for profile in current.profiles if profile.profile_id != ENGLISH11),
        frameworks=current.frameworks,
    )

    result = install_starter_standards_library(tmp_path, ELA, previous)
    assert result.standards_added == 0
    assert result.standards_skipped == 135
    assert result.profiles_added == 1
    assert result.profiles_skipped == 2
    assert result.profiles_overwritten == 0
    assert result.frameworks_added == 0
    assert result.frameworks_skipped == 1
    assert result.changed_count == 1

    installed = load_standards_library(standards_library_path(tmp_path))
    assert len(installed.standards) == 135
    assert {profile.profile_id for profile in installed.profiles} == {
        "english10_2023_njsls_ela",
        ENGLISH11,
        ENGLISH12,
    }
    before = standards_library_path(tmp_path).read_text(encoding="utf-8")
    again = install_starter_standards_library(tmp_path, ELA, installed)
    assert again.changed_count == 0
    assert again.standards_skipped == 135
    assert again.profiles_skipped == 3
    assert again.frameworks_skipped == 1
    assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before


def test_four_pack_install_orders_have_identical_durable_content(tmp_path: Path) -> None:
    orders = (
        (AP, CLKS, CSDT, ELA),
        (ELA, CSDT, CLKS, AP),
        (CSDT, AP, ELA, CLKS),
    )
    libraries = tuple(_install(tmp_path / f"workspace-{index}", order) for index, order in enumerate(orders))
    first_signature = _semantic_signature(libraries[0])

    for library in libraries:
        assert len(library.standards) == 694
        assert len(library.profiles) == 12
        assert len(library.frameworks) == 4
        assert len({item.standard_id for item in library.standards}) == 694
        assert len({item.profile_id for item in library.profiles}) == 12
        assert len({item.framework_id for item in library.frameworks}) == 4
        assert len({item.source for item in library.frameworks}) == 4
        assert _semantic_signature(library) == first_signature
        assert standards_library_from_dict(standards_library_to_dict(library)) == library


def test_combined_framework_provenance_and_reference_types_remain_independent(tmp_path: Path) -> None:
    library = _install(tmp_path, PACKS)
    frameworks = {item.framework_id: item for item in library.frameworks}
    assert set(frameworks) == {
        "ap_csp_fall_2023",
        "njsls_clks_2020",
        "njsls_csdt_2020",
        "njsls_ela_2023",
    }
    assert frameworks["ap_csp_fall_2023"].authority == "College Board"
    assert frameworks["ap_csp_fall_2023"].implementation_date is None
    assert frameworks["njsls_clks_2020"].authority == "New Jersey State Board of Education"
    assert frameworks["njsls_csdt_2020"].implementation_date == "2022-09"
    assert frameworks["njsls_ela_2023"].implementation_date == "2024-09"

    ap_reference = find_standard_definition(library, "ap-csp-2023:lo:AAP-2.A")
    njsls_standard = find_standard_definition(library, "njsls-csdt:8.1.12.AP.1")
    assert ap_reference is not None and "framework_reference" in ap_reference.tags
    assert njsls_standard is not None and "performance_expectation" in njsls_standard.tags


def test_representative_profiles_resolve_for_quillan_and_scoreform(tmp_path: Path) -> None:
    library = _install(tmp_path, PACKS)
    profile_ids = (
        ENGLISH11,
        ENGLISH12,
        "computer_science_9_12_2020_njsls_csdt",
        "clks_9_12_2020_njsls_clks",
        "ap_csp_fall_2023",
    )
    for module in ("pds-quillan", "pds-scoreform"):
        for profile_id in profile_ids:
            items = list_standards_for_profile_selection(
                library,
                profile_id,
                available_module=module,
            )
            assert items, (module, profile_id)


def test_all_four_packs_are_independently_idempotent_after_combined_install(tmp_path: Path) -> None:
    library = _install(tmp_path, PACKS)
    for pack_id in PACKS:
        before = standards_library_path(tmp_path).read_text(encoding="utf-8")
        result = install_starter_standards_library(tmp_path, pack_id, library)
        assert result.changed_count == 0
        assert not result.has_conflicts
        assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before
        library = load_standards_library(standards_library_path(tmp_path))
    assert not (tmp_path / "standards" / "usage").exists()


def test_multiframework_conflict_is_atomic(tmp_path: Path) -> None:
    complete = _install(tmp_path / "source", PACKS)
    target = tmp_path / "target"
    conflict_id = "njsls-csdt:8.1.12.AP.1"
    existing = StandardsLibrary(
        standards=tuple(
            dataclass_replace(item, description="Local edit for audit.")
            if item.standard_id == conflict_id
            else item
            for item in complete.standards
        ),
        profiles=complete.profiles,
        frameworks=complete.frameworks,
    )

    with pytest.raises(StarterStandardsInstallError) as caught:
        install_starter_standards_library(target, CSDT, existing)
    assert caught.value.result.standard_conflicts == (conflict_id,)
    assert not standards_library_path(target).exists()
