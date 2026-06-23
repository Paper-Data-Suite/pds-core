"""Tests for shared standards profile focus-selection validation."""

from __future__ import annotations

import re
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    validate_profile_standard_selection,
)


def make_library() -> StandardsLibrary:
    standards = (
        StandardDefinition(
            standard_id="nj_ela_2023_rl_cr_11_12_1",
            code="RL.CR.11-12.1",
            source="NJSLS-ELA 2023",
            short_name="Close Reading Evidence",
            description="Cite strong and thorough textual evidence.",
        ),
        StandardDefinition(
            standard_id="nj_ela_2023_w_aw_11_12_1",
            code="W.AW.11-12.1",
            source="NJSLS-ELA 2023",
            short_name="Argument Writing",
            description="Write arguments supported by evidence.",
        ),
        StandardDefinition(
            standard_id="nj_ela_2023_l_vi_11_12_4",
            code="L.VI.11-12.4",
            source="NJSLS-ELA 2023",
            short_name="Vocabulary in Context",
            description="Determine or clarify meaning of unknown words.",
        ),
    )
    profiles = (
        StandardsProfile(
            profile_id="nj_ela_2023_11_12",
            standards=(
                "nj_ela_2023_rl_cr_11_12_1",
                "nj_ela_2023_w_aw_11_12_1",
            ),
        ),
        StandardsProfile(
            profile_id="nj_ela_2023_language_11_12",
            standards=("nj_ela_2023_l_vi_11_12_4",),
        ),
    )
    return StandardsLibrary(standards=standards, profiles=profiles)


def test_profile_standard_selection_accepts_known_profile_subset() -> None:
    assert validate_profile_standard_selection(
        make_library(),
        profile_id="nj_ela_2023_11_12",
        selected_standard_ids=(
            "nj_ela_2023_rl_cr_11_12_1",
            "nj_ela_2023_w_aw_11_12_1",
        ),
    ) == (
        "nj_ela_2023_rl_cr_11_12_1",
        "nj_ela_2023_w_aw_11_12_1",
    )


def test_profile_standard_selection_normalizes_selected_ids() -> None:
    assert validate_profile_standard_selection(
        make_library(),
        profile_id=" nj_ela_2023_11_12 ",
        selected_standard_ids=[" nj_ela_2023_rl_cr_11_12_1 "],
    ) == ("nj_ela_2023_rl_cr_11_12_1",)


def test_profile_standard_selection_accepts_empty_selection() -> None:
    assert (
        validate_profile_standard_selection(
            make_library(),
            profile_id="nj_ela_2023_11_12",
            selected_standard_ids=(),
        )
        == ()
    )


def test_profile_standard_selection_rejects_missing_profile() -> None:
    with pytest.raises(StandardsValidationError, match="profile_id"):
        validate_profile_standard_selection(
            make_library(),
            profile_id="missing_profile",
            selected_standard_ids=("nj_ela_2023_rl_cr_11_12_1",),
        )


def test_profile_standard_selection_rejects_unknown_selected_standard_id() -> None:
    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        validate_profile_standard_selection(
            make_library(),
            profile_id="nj_ela_2023_11_12",
            selected_standard_ids=("nj_ela_2023_missing",),
        )


def test_profile_standard_selection_rejects_standard_outside_profile() -> None:
    with pytest.raises(StandardsValidationError, match="belong to profile"):
        validate_profile_standard_selection(
            make_library(),
            profile_id="nj_ela_2023_11_12",
            selected_standard_ids=("nj_ela_2023_l_vi_11_12_4",),
        )


def test_profile_standard_selection_rejects_duplicate_selected_ids() -> None:
    with pytest.raises(StandardsValidationError, match="duplicate standard IDs"):
        validate_profile_standard_selection(
            make_library(),
            profile_id="nj_ela_2023_11_12",
            selected_standard_ids=(
                "nj_ela_2023_rl_cr_11_12_1",
                " nj_ela_2023_rl_cr_11_12_1 ",
            ),
        )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("profile_id", {"profile_id": " "}),
        (
            "selected_standard_ids[0]",
            {"selected_standard_ids": (" ",)},
        ),
        (
            "selected_standard_ids",
            {"selected_standard_ids": "nj_ela_2023_rl_cr_11_12_1"},
        ),
    ],
)
def test_profile_standard_selection_rejects_blank_or_invalid_ids(
    field_name: str,
    kwargs: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "profile_id": "nj_ela_2023_11_12",
        "selected_standard_ids": ("nj_ela_2023_rl_cr_11_12_1",),
        **kwargs,
    }

    with pytest.raises(StandardsValidationError, match=re.escape(field_name)):
        validate_profile_standard_selection(
            make_library(),
            profile_id=cast(str, values["profile_id"]),
            selected_standard_ids=cast(Any, values["selected_standard_ids"]),
        )
