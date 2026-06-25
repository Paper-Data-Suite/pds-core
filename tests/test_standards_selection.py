"""Tests for module-facing standards selection helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

import pds_core.standards_selection as standards_selection
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsValidationError,
    standards_library_path,
)
from pds_core.standards_selection import (
    ProfileSelectionItem,
    StandardSelectionItem,
    format_profile_for_display,
    format_standard_for_display,
    list_profiles_for_selection,
    list_standards_for_profile_selection,
    list_standards_for_selection,
    load_standards_for_selection,
    resolve_profile_selection,
    resolve_profile_standard_selection,
    resolve_standard_selection,
)


def make_library() -> StandardsLibrary:
    standards = (
        StandardDefinition(
            standard_id="njsls-ela:W.AW.11-12.1",
            code="W.AW.11-12.1",
            source="NJSLS-ELA 2023",
            short_name="Argument Writing",
            description="Write arguments supported by evidence.",
            subject="English Language Arts",
            course="English 12",
            domain="Writing",
            active=True,
            available_modules=("pds-quillan",),
        ),
        StandardDefinition(
            standard_id="njsls-ela:RL.CR.11-12.1",
            code="RL.CR.11-12.1",
            source="NJSLS-ELA 2023",
            short_name="Close Reading Evidence",
            description="Cite strong and thorough textual evidence.",
            subject="English Language Arts",
            course="English 12",
            domain="Reading Literature",
            active=True,
            available_modules=("pds-scoreform", "pds-quillan"),
        ),
        StandardDefinition(
            standard_id="njsls-ela:RI.CR.11-12.1",
            code="RI.CR.11-12.1",
            source="NJSLS-ELA 2023",
            short_name="Informational Text Evidence",
            description="Cite textual evidence from informational text.",
            subject="English Language Arts",
            course="English 12",
            domain="Reading Informational Text",
            active=False,
            available_modules=("pds-scoreform",),
        ),
        StandardDefinition(
            standard_id="local-writing:evidence_explanation",
            code="evidence_explanation",
            source="Local Writing Rubric",
            short_name="Evidence Explanation",
            description="Explain how evidence supports a claim.",
            subject="English Language Arts",
            course="English 11",
            domain="Writing",
            active=True,
            available_modules=("pds-scoreform",),
        ),
    )
    profiles = (
        StandardsProfile(
            profile_id="english_12_njsls",
            standards=(
                "njsls-ela:RL.CR.11-12.1",
                "njsls-ela:W.AW.11-12.1",
                "njsls-ela:RI.CR.11-12.1",
            ),
            subject="English Language Arts",
            course="English 12",
            source="NJSLS-ELA 2023",
            title="English 12 NJSLS",
        ),
        StandardsProfile(
            profile_id="english_11_local",
            standards=("local-writing:evidence_explanation",),
            subject="English Language Arts",
            course="English 11",
            source="Local Writing Rubric",
            title="English 11 Local Writing",
        ),
    )
    return StandardsLibrary(standards=standards, profiles=profiles)


def item_ids(items: tuple[StandardSelectionItem, ...]) -> tuple[str, ...]:
    return tuple(item.standard_id for item in items)


def profile_ids(items: tuple[ProfileSelectionItem, ...]) -> tuple[str, ...]:
    return tuple(item.profile_id for item in items)


def unsafe_library_with_unknown_profile_reference() -> StandardsLibrary:
    library = object.__new__(StandardsLibrary)
    object.__setattr__(
        library,
        "standards",
        (
            StandardDefinition(
                standard_id="known:standard",
                code="known",
                source="Local",
                short_name="Known Standard",
                description="Known standard.",
            ),
        ),
    )
    object.__setattr__(
        library,
        "profiles",
        (
            StandardsProfile(
                profile_id="broken_profile",
                standards=("known:standard", "missing:standard"),
            ),
        ),
    )
    return library


def test_missing_workspace_standards_library_loads_empty_without_writes(
    tmp_path: Path,
) -> None:
    library = load_standards_for_selection(tmp_path)

    assert library == StandardsLibrary(standards=(), profiles=())
    assert not standards_library_path(tmp_path).exists()
    assert not (tmp_path / "standards").exists()


def test_invalid_existing_workspace_standards_library_raises_read_error(
    tmp_path: Path,
) -> None:
    path = standards_library_path(tmp_path)
    path.parent.mkdir()
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(StandardsReadError, match="invalid JSON"):
        load_standards_for_selection(tmp_path)


def test_profile_listing_returns_durable_ids_labels_and_filters() -> None:
    library = make_library()

    assert profile_ids(list_profiles_for_selection(library)) == (
        "english_11_local",
        "english_12_njsls",
    )

    njsls_profiles = list_profiles_for_selection(
        library,
        subject="English Language Arts",
        course="English 12",
        source="NJSLS-ELA 2023",
    )

    assert profile_ids(njsls_profiles) == ("english_12_njsls",)
    assert njsls_profiles[0].profile_id == "english_12_njsls"
    assert "English 12 NJSLS" in njsls_profiles[0].label
    assert "3 standards" in njsls_profiles[0].label


def test_empty_library_returns_empty_profile_list() -> None:
    assert list_profiles_for_selection(StandardsLibrary(standards=())) == ()


def test_resolve_profile_selection_uses_durable_profile_id_only() -> None:
    item = resolve_profile_selection(make_library(), " english_12_njsls ")

    assert item.profile_id == "english_12_njsls"
    assert item.title == "English 12 NJSLS"
    assert item.standard_count == 3

    with pytest.raises(StandardsValidationError, match="profile_id"):
        resolve_profile_selection(make_library(), "missing_profile")

    with pytest.raises(StandardsValidationError, match="profile_id"):
        resolve_profile_selection(make_library(), "English 12 NJSLS")


def test_standard_listing_returns_durable_ids_labels_and_default_active() -> None:
    items = list_standards_for_selection(make_library())

    assert item_ids(items) == (
        "local-writing:evidence_explanation",
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
    )
    assert items[1].standard_id == "njsls-ela:RL.CR.11-12.1"
    assert "RL.CR.11-12.1" in items[1].label
    assert "Close Reading Evidence" in items[1].label
    assert "njsls-ela:RI.CR.11-12.1" not in item_ids(items)


def test_standard_listing_active_modes_and_filters() -> None:
    library = make_library()

    assert item_ids(list_standards_for_selection(library, active=False)) == (
        "njsls-ela:RI.CR.11-12.1",
    )
    all_items = list_standards_for_selection(library, active=None)
    assert "njsls-ela:RI.CR.11-12.1" in item_ids(all_items)
    assert "[inactive]" in resolve_standard_selection(
        library,
        "njsls-ela:RI.CR.11-12.1",
    ).label

    filtered = list_standards_for_selection(
        library,
        subject="English Language Arts",
        course="English 12",
        source="NJSLS-ELA 2023",
        domain="Reading Literature",
        available_module="pds-scoreform",
    )

    assert item_ids(filtered) == ("njsls-ela:RL.CR.11-12.1",)


def test_empty_library_returns_empty_standard_list() -> None:
    assert list_standards_for_selection(StandardsLibrary(standards=())) == ()


def test_resolve_standard_selection_uses_durable_standard_id_only() -> None:
    item = resolve_standard_selection(
        make_library(),
        " njsls-ela:RL.CR.11-12.1 ",
    )

    assert item.standard_id == "njsls-ela:RL.CR.11-12.1"
    assert item.code == "RL.CR.11-12.1"

    with pytest.raises(StandardsValidationError, match="standard_id"):
        resolve_standard_selection(make_library(), "missing:standard")

    with pytest.raises(StandardsValidationError, match="standard_id"):
        resolve_standard_selection(make_library(), "RL.CR.11-12.1")


def test_profile_member_listing_preserves_order_and_filters() -> None:
    library = make_library()

    assert item_ids(
        list_standards_for_profile_selection(library, "english_12_njsls")
    ) == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
    )
    assert item_ids(
        list_standards_for_profile_selection(
            library,
            "english_12_njsls",
            active=None,
        )
    ) == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
        "njsls-ela:RI.CR.11-12.1",
    )
    assert item_ids(
        list_standards_for_profile_selection(
            library,
            "english_12_njsls",
            active=None,
            available_module="pds-scoreform",
        )
    ) == ("njsls-ela:RL.CR.11-12.1", "njsls-ela:RI.CR.11-12.1")


def test_profile_member_listing_reports_missing_profile_and_unknown_reference() -> None:
    with pytest.raises(StandardsValidationError, match="profile_id"):
        list_standards_for_profile_selection(make_library(), "missing_profile")

    with pytest.raises(StandardsValidationError, match="unknown standard_id"):
        list_standards_for_profile_selection(
            unsafe_library_with_unknown_profile_reference(),
            "broken_profile",
            active=None,
        )


def test_resolve_profile_standard_selection_validates_and_preserves_order() -> None:
    library = make_library()

    items = resolve_profile_standard_selection(
        library,
        profile_id="english_12_njsls",
        selected_standard_ids=(
            "njsls-ela:W.AW.11-12.1",
            "njsls-ela:RL.CR.11-12.1",
        ),
    )

    assert item_ids(items) == (
        "njsls-ela:W.AW.11-12.1",
        "njsls-ela:RL.CR.11-12.1",
    )
    assert resolve_profile_standard_selection(
        library,
        profile_id="english_12_njsls",
        selected_standard_ids=(),
    ) == ()

    with pytest.raises(StandardsValidationError, match="duplicate standard IDs"):
        resolve_profile_standard_selection(
            library,
            profile_id="english_12_njsls",
            selected_standard_ids=(
                "njsls-ela:RL.CR.11-12.1",
                " njsls-ela:RL.CR.11-12.1 ",
            ),
        )
    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        resolve_profile_standard_selection(
            library,
            profile_id="english_12_njsls",
            selected_standard_ids=("missing:standard",),
        )
    with pytest.raises(StandardsValidationError, match="belong to profile"):
        resolve_profile_standard_selection(
            library,
            profile_id="english_12_njsls",
            selected_standard_ids=("local-writing:evidence_explanation",),
        )


def test_display_formatters_distinguish_ids_from_display_fields() -> None:
    library = make_library()

    assert format_standard_for_display(library.standards[1]) == (
        "njsls-ela:RL.CR.11-12.1 | RL.CR.11-12.1 | "
        "Close Reading Evidence | NJSLS-ELA 2023"
    )
    assert format_profile_for_display(library.profiles[0]) == (
        "english_12_njsls | English 12 NJSLS | NJSLS-ELA 2023 | "
        "English Language Arts | English 12 | 3 standards"
    )


def test_quillan_like_profile_and_focus_standard_selection() -> None:
    library = make_library()

    profile = resolve_profile_selection(library, "english_12_njsls")
    focus_choices = list_standards_for_profile_selection(
        library,
        profile.profile_id,
        available_module="pds-quillan",
    )
    focus_standards = resolve_profile_standard_selection(
        library,
        profile_id=profile.profile_id,
        selected_standard_ids=(
            "njsls-ela:RL.CR.11-12.1",
            "njsls-ela:W.AW.11-12.1",
        ),
    )
    assignment_data = {
        "profile_id": profile.profile_id,
        "focus_standard_ids": [item.standard_id for item in focus_standards],
    }

    assert item_ids(focus_choices) == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
    )
    assert [item.label for item in focus_standards]
    assert assignment_data == {
        "profile_id": "english_12_njsls",
        "focus_standard_ids": [
            "njsls-ela:RL.CR.11-12.1",
            "njsls-ela:W.AW.11-12.1",
        ],
    }
    assert "RL.CR.11-12.1" not in assignment_data["focus_standard_ids"]


def test_scoreform_like_question_level_standard_tagging() -> None:
    library = make_library()

    available = list_standards_for_selection(
        library,
        course="English 12",
        available_module="pds-scoreform",
        active=None,
    )
    question_1_standard = resolve_standard_selection(
        library,
        "njsls-ela:RL.CR.11-12.1",
    )
    question_2_standard = resolve_standard_selection(
        library,
        "njsls-ela:RI.CR.11-12.1",
    )
    question_1_standard_ids = [question_1_standard.standard_id]
    question_2_standard_ids = [question_2_standard.standard_id]
    assignment_data = {
        "questions": [
            {"number": 1, "standard_ids": question_1_standard_ids},
            {"number": 2, "standard_ids": question_2_standard_ids},
        ]
    }

    assert item_ids(available) == (
        "njsls-ela:RI.CR.11-12.1",
        "njsls-ela:RL.CR.11-12.1",
    )
    assert question_1_standard.label.startswith("njsls-ela:RL.CR.11-12.1 |")
    assert assignment_data == {
        "questions": [
            {"number": 1, "standard_ids": ["njsls-ela:RL.CR.11-12.1"]},
            {"number": 2, "standard_ids": ["njsls-ela:RI.CR.11-12.1"]},
        ]
    }
    assert "RI.CR.11-12.1" not in question_2_standard_ids


def test_selection_apis_do_not_write_workspace_artifacts(tmp_path: Path) -> None:
    library = make_library()

    list_profiles_for_selection(library)
    list_standards_for_selection(library)
    resolve_profile_selection(library, "english_12_njsls")
    resolve_standard_selection(library, "njsls-ela:RL.CR.11-12.1")
    load_standards_for_selection(tmp_path)

    assert not (tmp_path / "standards").exists()
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "pds-scoreform").exists()
    assert not (tmp_path / "pds-quillan").exists()


def test_selection_module_does_not_import_scoreform_or_quillan() -> None:
    module_file = Path(standards_selection.__file__)

    source = module_file.read_text(encoding="utf-8")
    assert "scoreform" not in source.lower()
    assert "quillan" not in source.lower()
    assert "pds_scoreform" not in sys.modules
    assert "pds_quillan" not in sys.modules


def test_invalid_filter_values_raise_standards_validation_error() -> None:
    with pytest.raises(StandardsValidationError, match="course"):
        list_standards_for_selection(make_library(), course=cast(Any, " "))

    with pytest.raises(StandardsValidationError, match="active"):
        list_standards_for_profile_selection(
            make_library(),
            "english_12_njsls",
            active=cast(Any, "true"),
        )


def test_invalid_workspace_library_data_is_not_rewritten(tmp_path: Path) -> None:
    path = standards_library_path(tmp_path)
    path.parent.mkdir()
    original = json.dumps({"standards": [{"standard_id": "missing fields"}]})
    path.write_text(original, encoding="utf-8")

    with pytest.raises(StandardsReadError):
        load_standards_for_selection(tmp_path)

    assert path.read_text(encoding="utf-8") == original
