"""Tests for bundled starter standards libraries."""

from __future__ import annotations

from dataclasses import replace as dataclass_replace
from pathlib import Path

import pytest

from pds_core.standards import (
    StandardsLibrary,
    StandardsValidationError,
    load_standards_library,
    standards_library_from_dict,
    standards_library_path,
    standards_library_to_dict,
    validate_profile_standard_selection,
)
from pds_core.standards_selection import (
    list_profiles_for_selection,
    list_standards_for_profile_selection,
)
from pds_core.starter_standards import (
    StarterStandardsInstallError,
    install_starter_standards_library,
    list_starter_standards_packs,
    load_starter_standards_library,
    starter_standards_pack_metadata,
    validate_starter_standards_library,
)


PACK_ID = "njsls_ela_2023"


def test_njsls_ela_2023_starter_pack_is_discoverable() -> None:
    packs = list_starter_standards_packs()

    assert [pack.pack_id for pack in packs] == [PACK_ID]
    metadata = packs[0]
    assert metadata.title == "2023 NJSLS ELA High School Starter Standards"
    assert metadata.source == "2023 NJSLS-ELA"
    assert metadata.grade_bands == ("9-10", "11-12")
    assert metadata.courses == ("English 10", "English 12")
    assert metadata.standard_count == 135
    assert metadata.profile_count == 2
    assert metadata.profile_ids == (
        "english10_2023_njsls_ela",
        "english12_2023_njsls_ela",
    )


def test_njsls_ela_2023_starter_pack_validates() -> None:
    library = validate_starter_standards_library(PACK_ID)
    standard_ids = [definition.standard_id for definition in library.standards]
    profile_ids = [profile.profile_id for profile in library.profiles]

    assert len(standard_ids) == len(set(standard_ids)) == 135
    assert len(profile_ids) == len(set(profile_ids)) == 2
    assert all(standard_id.startswith("njsls-ela:") for standard_id in standard_ids)
    assert all(definition.active for definition in library.standards)
    assert all(
        definition.available_modules == ("pds-quillan", "pds-scoreform")
        for definition in library.standards
    )

    for profile in library.profiles:
        assert all(standard_id in standard_ids for standard_id in profile.standards)

    english10 = next(
        profile
        for profile in library.profiles
        if profile.profile_id == "english10_2023_njsls_ela"
    )
    english12 = next(
        profile
        for profile in library.profiles
        if profile.profile_id == "english12_2023_njsls_ela"
    )
    by_id = {definition.standard_id: definition for definition in library.standards}
    assert {by_id[standard_id].grade_band for standard_id in english10.standards} == {
        "9-10"
    }
    assert {by_id[standard_id].grade_band for standard_id in english12.standards} == {
        "11-12"
    }
    assert len(english10.standards) == 68
    assert len(english12.standards) == 67
    assert english10.standards[:3] == (
        "njsls-ela:L.SS.9-10.1",
        "njsls-ela:L.SS.9-10.1.A",
        "njsls-ela:L.SS.9-10.1.B",
    )
    assert english12.standards[:3] == (
        "njsls-ela:L.SS.11-12.1",
        "njsls-ela:L.SS.11-12.1.A",
        "njsls-ela:L.SS.11-12.1.B",
    )


def test_starter_pack_round_trip_preserves_parent_and_subskill_records() -> None:
    library = load_starter_standards_library(PACK_ID)

    restored = standards_library_from_dict(standards_library_to_dict(library))

    assert restored == library
    restored_ids = {definition.standard_id for definition in restored.standards}
    assert "njsls-ela:W.AW.11-12.1" in restored_ids
    assert "njsls-ela:W.AW.11-12.1.A" in restored_ids


def test_starter_pack_represents_parents_and_subskills_as_standards() -> None:
    library = load_starter_standards_library(PACK_ID)
    by_id = {definition.standard_id: definition for definition in library.standards}

    assert "njsls-ela:W.AW.9-10.1" in by_id
    assert "njsls-ela:W.AW.9-10.1.A" in by_id
    parent = by_id["njsls-ela:W.AW.9-10.1"]
    subskill = by_id["njsls-ela:W.AW.9-10.1.A"]
    assert "A. Introduce precise claim(s)" not in parent.description
    assert subskill.code == "W.AW.9-10.1.A"
    assert subskill.short_name == "Argument Writing - A"
    assert subskill.category_path[-1] == parent.code
    assert "subskill" in subskill.tags
    assert f"parent_standard:{parent.standard_id}" in subskill.tags
    assert "subskill_letter:a" in subskill.tags
    assert "parent_standard" in parent.tags
    assert subskill.active
    assert subskill.available_modules == ("pds-quillan", "pds-scoreform")
    assert by_id["njsls-ela:RL.PP.9-10.5"].code == "RL.PP.9-10.5"
    assert by_id["njsls-ela:SL.PI.11-12.4"].code == "SL.PI.11-12.4"


def test_install_into_empty_workspace_writes_only_library(tmp_path: Path) -> None:
    result = install_starter_standards_library(
        tmp_path,
        PACK_ID,
        StandardsLibrary(standards=()),
    )

    assert result.standards_added == 135
    assert result.profiles_added == 2
    assert result.changed_count == 137
    assert standards_library_path(tmp_path).is_file()
    assert load_standards_library(standards_library_path(tmp_path)) == (
        load_starter_standards_library(PACK_ID)
    )
    workspace_entries = sorted(
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")
    )
    assert workspace_entries == [
        "standards",
        "standards/library.json",
    ]
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "classes").exists()
    assert not (tmp_path / "assignments").exists()
    assert not (tmp_path / "pds-quillan").exists()
    assert not (tmp_path / "pds-scoreform").exists()


def test_repeated_install_is_idempotent(tmp_path: Path) -> None:
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

    assert first.changed_count == 137
    assert second.standards_added == 0
    assert second.standards_skipped == 135
    assert second.profiles_added == 0
    assert second.profiles_skipped == 2
    assert second.changed_count == 0
    assert standards_library_path(tmp_path).read_text(encoding="utf-8") == before


def test_install_reports_conflicts_without_silent_overwrite(tmp_path: Path) -> None:
    starter = load_starter_standards_library(PACK_ID)
    conflicting_standard = dataclass_replace(
        starter.standards[0],
        description="Teacher-edited local wording.",
    )
    existing = StandardsLibrary(
        standards=(conflicting_standard,),
        profiles=(),
    )

    with pytest.raises(StarterStandardsInstallError) as caught:
        install_starter_standards_library(tmp_path, PACK_ID, existing)

    assert starter.standards[0].standard_id in caught.value.result.standard_conflicts
    assert not standards_library_path(tmp_path).exists()


def test_install_can_explicitly_overwrite_conflicting_pack_records(
    tmp_path: Path,
) -> None:
    starter = load_starter_standards_library(PACK_ID)
    conflicting_standard = dataclass_replace(
        starter.standards[0],
        description="Teacher-edited local wording.",
    )
    existing = StandardsLibrary(
        standards=(conflicting_standard,),
        profiles=(),
    )

    result = install_starter_standards_library(
        tmp_path,
        PACK_ID,
        existing,
        overwrite_conflicts=True,
    )

    assert result.standards_overwritten == 1
    assert result.standard_conflicts == ()
    installed = load_standards_library(standards_library_path(tmp_path))
    assert installed.standards[0] == starter.standards[0]


def test_invalid_starter_pack_does_not_write_partial_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_validation(_pack_id: str) -> StandardsLibrary:
        raise StandardsValidationError("invalid starter")

    monkeypatch.setattr(
        "pds_core.starter_standards.validate_starter_standards_library",
        fail_validation,
    )

    with pytest.raises(StandardsValidationError, match="invalid starter"):
        install_starter_standards_library(
            tmp_path,
            PACK_ID,
            StandardsLibrary(standards=()),
        )

    assert not (tmp_path / "standards").exists()


def test_installed_profiles_work_with_module_selection_helpers(tmp_path: Path) -> None:
    install_starter_standards_library(
        tmp_path,
        PACK_ID,
        StandardsLibrary(standards=()),
    )
    library = load_standards_library(standards_library_path(tmp_path))

    profiles = list_profiles_for_selection(library, source="2023 NJSLS-ELA")
    assert [profile.profile_id for profile in profiles] == [
        "english10_2023_njsls_ela",
        "english12_2023_njsls_ela",
    ]

    english10_items = list_standards_for_profile_selection(
        library,
        "english10_2023_njsls_ela",
        available_module="pds-quillan",
    )
    assert english10_items[0].standard_id == "njsls-ela:L.SS.9-10.1"
    assert english10_items[1].standard_id == "njsls-ela:L.SS.9-10.1.A"
    assert "njsls-ela:W.AW.9-10.1" in [
        item.standard_id for item in english10_items
    ]
    assert "njsls-ela:W.AW.9-10.1.A" in [
        item.standard_id for item in english10_items
    ]

    assert validate_profile_standard_selection(
        library,
        profile_id="english10_2023_njsls_ela",
        selected_standard_ids=("njsls-ela:RL.CR.9-10.1",),
    ) == ("njsls-ela:RL.CR.9-10.1",)
    with pytest.raises(StandardsValidationError, match="belong to profile"):
        validate_profile_standard_selection(
            library,
            profile_id="english10_2023_njsls_ela",
            selected_standard_ids=("njsls-ela:RL.CR.11-12.1",),
        )


def test_unknown_starter_pack_reports_available_ids() -> None:
    with pytest.raises(StandardsValidationError, match=PACK_ID):
        starter_standards_pack_metadata("missing_pack")
