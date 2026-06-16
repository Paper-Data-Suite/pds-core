"""Tests for in-memory standards library mutation helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    add_standard_definition,
    add_standards_profile,
    filter_standard_definitions,
    replace_standard_definition,
    replace_standards_profile,
    standards_library_from_dict,
    standards_library_to_dict,
    upsert_standard_definition,
    upsert_standards_profile,
)


DefinitionMutationHelper = Callable[
    [StandardsLibrary, StandardDefinition],
    StandardsLibrary,
]
ProfileMutationHelper = Callable[
    [StandardsLibrary, StandardsProfile],
    StandardsLibrary,
]


def make_standard(
    standard_id: str,
    code: str,
    short_name: str | None = None,
    *,
    active: bool = True,
) -> StandardDefinition:
    return StandardDefinition(
        standard_id=standard_id,
        code=code,
        source="NJSLS-ELA",
        short_name=short_name or code,
        description=f"{code} description.",
        subject="English Language Arts",
        course="English 12",
        domain="Reading Literature",
        category_path=("English Language Arts", "Reading Literature"),
        tags=("close_reading",),
        active=active,
        available_modules=("pds-scoreform",),
    )


def make_profile(
    profile_id: str,
    standards: tuple[str, ...],
    title: str | None = None,
) -> StandardsProfile:
    return StandardsProfile(
        profile_id=profile_id,
        standards=standards,
        subject="English Language Arts",
        course="English 12",
        source="NJSLS-ELA",
        title=title or profile_id,
    )


def make_library() -> StandardsLibrary:
    first = make_standard(
        "njsls-ela:RL.CR.11-12.1",
        "RL.CR.11-12.1",
        "Close Reading Evidence",
    )
    second = make_standard(
        "njsls-ela:W.AW.11-12.1",
        "W.AW.11-12.1",
        "Argument Writing",
    )
    profile = make_profile(
        "english_12_njsls",
        (first.standard_id, second.standard_id),
        "English 12 NJSLS",
    )
    return StandardsLibrary(standards=(first, second), profiles=(profile,))


def standard_ids(library: StandardsLibrary) -> tuple[str, ...]:
    return tuple(definition.standard_id for definition in library.standards)


def profile_ids(library: StandardsLibrary) -> tuple[str, ...]:
    return tuple(profile.profile_id for profile in library.profiles)


def test_add_standard_definition_appends_new_definition() -> None:
    library = make_library()
    definition = make_standard("local-writing:evidence", "evidence")

    updated = add_standard_definition(library, definition)

    assert standard_ids(updated) == (
        "njsls-ela:RL.CR.11-12.1",
        "njsls-ela:W.AW.11-12.1",
        "local-writing:evidence",
    )
    assert updated.standards[-1] == definition


def test_add_standard_definition_preserves_standards_and_profiles() -> None:
    library = make_library()
    definition = make_standard("local-writing:evidence", "evidence")

    updated = add_standard_definition(library, definition)

    assert updated.standards[:2] == library.standards
    assert updated.profiles == library.profiles


def test_add_standard_definition_rejects_duplicate_standard_id() -> None:
    library = make_library()
    duplicate = make_standard("njsls-ela:RL.CR.11-12.1", "changed")

    with pytest.raises(StandardsValidationError, match="duplicate.*standard_id"):
        add_standard_definition(library, duplicate)


def test_replace_standard_definition_updates_existing_definition() -> None:
    library = make_library()
    replacement = make_standard(
        "njsls-ela:RL.CR.11-12.1",
        "RL.CR.11-12.1",
        "Updated Close Reading Evidence",
    )

    updated = replace_standard_definition(library, replacement)

    assert updated.standards[0] == replacement
    assert updated.standards[0].short_name == "Updated Close Reading Evidence"


def test_replace_standard_definition_preserves_order_and_profiles() -> None:
    library = make_library()
    replacement = make_standard("njsls-ela:W.AW.11-12.1", "W.AW.11-12.1")

    updated = replace_standard_definition(library, replacement)

    assert standard_ids(updated) == standard_ids(library)
    assert updated.standards[1] == replacement
    assert updated.profiles == library.profiles


def test_replace_standard_definition_rejects_missing_standard_id() -> None:
    library = make_library()
    missing = make_standard("local-writing:evidence", "evidence")

    with pytest.raises(StandardsValidationError, match="missing.*standard_id"):
        replace_standard_definition(library, missing)


def test_upsert_standard_definition_replaces_existing_in_place() -> None:
    library = make_library()
    replacement = make_standard("njsls-ela:W.AW.11-12.1", "W.AW.11-12.1")

    updated = upsert_standard_definition(library, replacement)

    assert standard_ids(updated) == standard_ids(library)
    assert updated.standards[1] == replacement


def test_upsert_standard_definition_appends_new_definition() -> None:
    library = make_library()
    definition = make_standard("local-writing:evidence", "evidence")

    updated = upsert_standard_definition(library, definition)

    assert standard_ids(updated)[-1] == "local-writing:evidence"
    assert updated.standards[-1] == definition


@pytest.mark.parametrize(
    "helper",
    [
        add_standard_definition,
        replace_standard_definition,
        upsert_standard_definition,
    ],
)
def test_standard_definition_helpers_reject_non_library_values(
    helper: DefinitionMutationHelper,
) -> None:
    with pytest.raises(StandardsValidationError, match="library"):
        helper(cast(Any, "not a library"), make_standard("local:a", "a"))


@pytest.mark.parametrize(
    "helper",
    [
        add_standard_definition,
        replace_standard_definition,
        upsert_standard_definition,
    ],
)
def test_standard_definition_helpers_reject_non_definition_values(
    helper: DefinitionMutationHelper,
) -> None:
    with pytest.raises(StandardsValidationError, match="definition"):
        helper(make_library(), cast(Any, "not a definition"))


def test_standard_definition_helpers_do_not_mutate_original_library() -> None:
    library = make_library()
    before = standards_library_to_dict(library)

    upsert_standard_definition(
        library,
        make_standard("njsls-ela:W.AW.11-12.1", "W.AW.11-12.1"),
    )
    add_standard_definition(
        library,
        make_standard("local-writing:evidence", "evidence"),
    )

    assert standards_library_to_dict(library) == before


def test_add_standards_profile_appends_new_profile() -> None:
    library = make_library()
    profile = make_profile(
        "english_12_close_reading",
        (library.standards[0].standard_id,),
    )

    updated = add_standards_profile(library, profile)

    assert profile_ids(updated) == ("english_12_njsls", "english_12_close_reading")
    assert updated.profiles[-1] == profile


def test_add_standards_profile_preserves_standards_and_profiles() -> None:
    library = make_library()
    profile = make_profile(
        "english_12_close_reading",
        (library.standards[0].standard_id,),
    )

    updated = add_standards_profile(library, profile)

    assert updated.standards == library.standards
    assert updated.profiles[:-1] == library.profiles


def test_add_standards_profile_rejects_duplicate_profile_id() -> None:
    library = make_library()
    duplicate = make_profile("english_12_njsls", (library.standards[0].standard_id,))

    with pytest.raises(StandardsValidationError, match="duplicate.*profile_id"):
        add_standards_profile(library, duplicate)


def test_add_standards_profile_rejects_unknown_standard_references() -> None:
    library = make_library()
    profile = make_profile("unknown_profile", ("unknown:standard",))

    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        add_standards_profile(library, profile)


def test_replace_standards_profile_updates_existing_profile() -> None:
    library = make_library()
    replacement = make_profile(
        "english_12_njsls",
        (library.standards[0].standard_id,),
        "Close Reading Only",
    )

    updated = replace_standards_profile(library, replacement)

    assert updated.profiles[0] == replacement
    assert updated.profiles[0].standards == (library.standards[0].standard_id,)


def test_replace_standards_profile_preserves_original_profile_order() -> None:
    library = add_standards_profile(
        make_library(),
        make_profile("english_12_argument", ("njsls-ela:W.AW.11-12.1",)),
    )
    replacement = make_profile(
        "english_12_njsls",
        ("njsls-ela:RL.CR.11-12.1",),
        "Replacement",
    )

    updated = replace_standards_profile(library, replacement)

    assert profile_ids(updated) == ("english_12_njsls", "english_12_argument")
    assert updated.profiles[0] == replacement
    assert updated.standards == library.standards


def test_replace_standards_profile_rejects_missing_profile_id() -> None:
    library = make_library()
    missing = make_profile("missing_profile", (library.standards[0].standard_id,))

    with pytest.raises(StandardsValidationError, match="missing.*profile_id"):
        replace_standards_profile(library, missing)


def test_replace_standards_profile_rejects_unknown_standard_references() -> None:
    library = make_library()
    profile = make_profile("english_12_njsls", ("unknown:standard",))

    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        replace_standards_profile(library, profile)


def test_upsert_standards_profile_replaces_existing_in_place() -> None:
    library = make_library()
    replacement = make_profile(
        "english_12_njsls",
        (library.standards[0].standard_id,),
        "Close Reading Only",
    )

    updated = upsert_standards_profile(library, replacement)

    assert profile_ids(updated) == profile_ids(library)
    assert updated.profiles[0] == replacement


def test_upsert_standards_profile_appends_new_profile() -> None:
    library = make_library()
    profile = make_profile(
        "english_12_close_reading",
        (library.standards[0].standard_id,),
    )

    updated = upsert_standards_profile(library, profile)

    assert profile_ids(updated)[-1] == "english_12_close_reading"
    assert updated.profiles[-1] == profile


def test_upsert_standards_profile_rejects_unknown_standard_references() -> None:
    library = make_library()
    profile = make_profile("unknown_profile", ("unknown:standard",))

    with pytest.raises(StandardsValidationError, match="unknown standard IDs"):
        upsert_standards_profile(library, profile)


@pytest.mark.parametrize(
    "helper",
    [
        add_standards_profile,
        replace_standards_profile,
        upsert_standards_profile,
    ],
)
def test_standards_profile_helpers_reject_non_library_values(
    helper: ProfileMutationHelper,
) -> None:
    profile = make_profile("profile", ("njsls-ela:RL.CR.11-12.1",))

    with pytest.raises(StandardsValidationError, match="library"):
        helper(cast(Any, "not a library"), profile)


@pytest.mark.parametrize(
    "helper",
    [
        add_standards_profile,
        replace_standards_profile,
        upsert_standards_profile,
    ],
)
def test_standards_profile_helpers_reject_non_profile_values(
    helper: ProfileMutationHelper,
) -> None:
    with pytest.raises(StandardsValidationError, match="profile"):
        helper(make_library(), cast(Any, "not a profile"))


def test_standards_profile_helpers_do_not_mutate_original_library() -> None:
    library = make_library()
    before = standards_library_to_dict(library)

    upsert_standards_profile(
        library,
        make_profile("english_12_njsls", (library.standards[0].standard_id,)),
    )
    add_standards_profile(
        library,
        make_profile("english_12_close_reading", (library.standards[0].standard_id,)),
    )

    assert standards_library_to_dict(library) == before


def test_mutated_library_preserves_round_trip_shape_and_browsing() -> None:
    library = make_library()
    added = make_standard("local-writing:evidence", "evidence")
    updated = add_standard_definition(library, added)
    round_tripped = standards_library_from_dict(standards_library_to_dict(updated))

    assert round_tripped == updated
    assert round_tripped.profiles == updated.profiles
    assert round_tripped.standards[-1].domain == "Reading Literature"
    assert round_tripped.standards[-1].tags == ("close_reading",)
    assert filter_standard_definitions(
        round_tripped,
        available_module="pds-scoreform",
    ) == round_tripped.standards


def test_replace_standard_definition_can_retire_standard() -> None:
    library = make_library()
    retired = make_standard(
        "njsls-ela:RL.CR.11-12.1",
        "RL.CR.11-12.1",
        active=False,
    )

    updated = replace_standard_definition(library, retired)

    assert updated.standards[0].active is False
    assert library.standards[0].active is True
