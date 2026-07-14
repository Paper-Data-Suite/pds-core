"""Tests for atomic standards and profile-membership transformations."""

from __future__ import annotations

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    add_standard_definitions,
    add_standards_to_profile,
    remove_standards_from_profile,
    set_profile_standards,
)


def definition(standard_id: str) -> StandardDefinition:
    return StandardDefinition(
        standard_id=standard_id,
        code=standard_id,
        source="Synthetic",
        short_name=standard_id,
        description=f"Description for {standard_id}.",
    )


def library() -> StandardsLibrary:
    standards = tuple(definition(item) for item in ("one", "two", "three", "four"))
    return StandardsLibrary(
        standards=standards,
        profiles=(
            StandardsProfile(
                profile_id="main",
                standards=("one", "two"),
                title="Title",
                description="Description",
                subject="Subject",
                course="Course",
                source="Source",
            ),
            StandardsProfile(profile_id="other", standards=("four",)),
        ),
    )


def test_add_standard_definitions_preserves_and_appends_ordered_flat_records() -> None:
    original = library()
    parent = definition("local:parent")
    subpart_a = definition("local:parent.A")
    subpart_b = definition("local:parent.B")

    updated = add_standard_definitions(original, (parent, subpart_a, subpart_b))

    assert updated.standards == original.standards + (parent, subpart_a, subpart_b)
    assert updated.profiles == original.profiles


@pytest.mark.parametrize("items", [(), []])
def test_add_standard_definitions_rejects_empty_batch(items: object) -> None:
    with pytest.raises(StandardsValidationError, match="must not be empty"):
        add_standard_definitions(library(), items)  # type: ignore[arg-type]


def test_add_standard_definitions_rejects_normalized_duplicates_and_conflicts() -> None:
    with pytest.raises(StandardsValidationError, match="duplicate"):
        add_standard_definitions(library(), (definition(" new "), definition("new")))
    with pytest.raises(StandardsValidationError, match="existing"):
        add_standard_definitions(library(), (definition(" one "), definition("new")))


@pytest.mark.parametrize("bad_index", [0, 1])
def test_add_standard_definitions_rejects_any_invalid_item(bad_index: int) -> None:
    items: list[object] = [definition("new-a"), definition("new-b")]
    items[bad_index] = "invalid"
    with pytest.raises(StandardsValidationError, match="definition"):
        add_standard_definitions(library(), items)  # type: ignore[arg-type]


def test_profile_batch_mutations_preserve_metadata_order_and_unrelated_records() -> None:
    original = library()
    added = add_standards_to_profile(original, " main ", (" four ", "three"))
    assert added.profiles[0].standards == ("one", "two", "four", "three")
    assert added.profiles[0].title == "Title"
    assert added.profiles[0].description == "Description"
    assert added.profiles[0].subject == "Subject"
    assert added.profiles[0].course == "Course"
    assert added.profiles[0].source == "Source"
    assert added.profiles[1] == original.profiles[1]
    assert added.standards == original.standards

    removed = remove_standards_from_profile(added, "main", ("four", "one"))
    assert removed.profiles[0].standards == ("two", "three")

    replaced = set_profile_standards(removed, "main", ("four", "one"))
    assert replaced.profiles[0].standards == ("four", "one")
    assert replaced.profiles[0].title == "Title"
    assert replaced.profiles[1] == original.profiles[1]

    cleared = set_profile_standards(replaced, "main", ())
    assert cleared.profiles[0].standards == ()
    assert cleared.profiles[0].title == "Title"


@pytest.mark.parametrize(
    ("operation", "profile_id", "ids", "message"),
    [
        (add_standards_to_profile, "missing", ("three",), "profile not found"),
        (add_standards_to_profile, "main", ("missing",), "standard not found"),
        (add_standards_to_profile, "main", (" three ", "three"), "duplicate"),
        (add_standards_to_profile, "main", ("one",), "already contains"),
        (remove_standards_from_profile, "main", ("three",), "does not contain"),
    ],
)
def test_profile_batch_mutations_reject_complete_invalid_requests(
    operation: object, profile_id: str, ids: tuple[str, ...], message: str
) -> None:
    from collections.abc import Callable
    from typing import cast

    transform = cast(
        Callable[[StandardsLibrary, str, tuple[str, ...]], StandardsLibrary], operation
    )
    with pytest.raises(StandardsValidationError, match=message):
        transform(library(), profile_id, ids)


@pytest.mark.parametrize("operation", [add_standards_to_profile, remove_standards_from_profile])
def test_add_and_remove_require_non_empty_requests(operation: object) -> None:
    from collections.abc import Callable
    from typing import cast

    transform = cast(
        Callable[[StandardsLibrary, str, tuple[str, ...]], StandardsLibrary], operation
    )
    with pytest.raises(StandardsValidationError, match="must not be empty"):
        transform(library(), "main", ())
