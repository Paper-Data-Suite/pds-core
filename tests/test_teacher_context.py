"""Core #240-A: public request/result contract validation (no workspace I/O)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
    TeacherWorkReference,
)


def test_public_request_keeps_exact_token_and_optional_nonstudent_hints(
    tmp_path: Path,
) -> None:
    hint = TeacherContextHint(
        workspace_root=tmp_path,
        class_id="English12_P2",
        work=TeacherWorkReference("quillan", "assignment", "Narrative_01"),
        display_label="English 12 — Writing",
    )
    request = SharedTeacherMenuRequest("Quillan", "opaque-local-1", hint)
    assert request.context == hint
    assert request.return_token == "opaque-local-1"
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(FrozenInstanceError):
        request.return_token = "other"  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["", " \t ", "x\nY", "x\x1b[32m", "x\u202e", "x" * 129])
def test_invalid_return_token_rejected_before_any_menu(bad: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        SharedTeacherMenuRequest("Core", bad)


@pytest.mark.parametrize("bad", ["", "A\nB", "\x1bCore", "A\u2028B"])
def test_invalid_display_labels_rejected(bad: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        TeacherContextHint(display_label=bad)


def test_invalid_shapes_fail_closed_without_coercion() -> None:
    with pytest.raises(TypeError):
        TeacherContextHint(workspace_root=cast(Path, "C:/fake"))
    with pytest.raises(TypeError):
        TeacherContextHint(work=cast(TeacherWorkReference, object()))
    with pytest.raises(TypeError):
        SharedTeacherMenuRequest("Core", "token", cast(TeacherContextHint, {}))
    with pytest.raises(ValueError):
        TeacherWorkReference("Quillan", "assignment", "a")
    with pytest.raises(ValueError):
        TeacherContextHint(class_id="../student")
    with pytest.raises(ValueError):
        TeacherWorkReference("quillan", "assignment", "A B")


def test_result_keeps_navigation_and_durability_independent() -> None:
    result = SharedTeacherMenuResult(
        "opaque-local-1",
        TeacherMenuExit.BACK,
        TeacherDurability.COMMITTED,
        frozenset({TeacherChangeScope.NOTES}),
        "Saved. Returning to caller.",
    )
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.NOTES})
    assert result.return_token == "opaque-local-1"


@pytest.mark.parametrize(
    "exit_kind", [TeacherMenuExit.BACK, TeacherMenuExit.QUIT, TeacherMenuExit.CANCELLED]
)
def test_confirmed_work_is_compatible_with_later_navigation(
    exit_kind: TeacherMenuExit,
) -> None:
    record = SharedTeacherMenuResult(
        "token",
        exit_kind,
        TeacherDurability.PARTIAL,
        frozenset({TeacherChangeScope.NOTES}),
        "Some changes were saved. Review the remainder.",
    )
    assert record.change_scopes == frozenset({TeacherChangeScope.NOTES})


def test_result_invariants_prevent_misleading_durability() -> None:
    with pytest.raises(ValueError):
        SharedTeacherMenuResult(
            "t",
            TeacherMenuExit.BACK,
            TeacherDurability.NO_CHANGE,
            frozenset({TeacherChangeScope.NOTES}),
            "No change",
        )
    with pytest.raises(ValueError):
        SharedTeacherMenuResult(
            "t", TeacherMenuExit.BACK, TeacherDurability.COMMITTED, frozenset(), "Saved"
        )
    with pytest.raises(ValueError):
        SharedTeacherMenuResult(
            "t",
            TeacherMenuExit.UNAVAILABLE,
            TeacherDurability.COMMITTED,
            frozenset({TeacherChangeScope.NOTES}),
            "Unavailable",
        )
    with pytest.raises(TypeError):
        SharedTeacherMenuResult(
            "t",
            TeacherMenuExit.BACK,
            TeacherDurability.NO_CHANGE,
            cast(frozenset[TeacherChangeScope], {"notes"}),
            "Invalid",
        )
    with pytest.raises(ValueError):
        SharedTeacherMenuResult(
            "t",
            TeacherMenuExit.BACK,
            TeacherDurability.NO_CHANGE,
            frozenset(),
            "Trace\nback",
        )
