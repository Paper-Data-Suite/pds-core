"""Synthetic C3B7 class creation controller acceptance."""

from __future__ import annotations

import io
import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

import pds_core.teacher_menus as menus
from pds_core.class_metadata import load_class_metadata_for_class
from pds_core.routes import class_dir, class_roster_path
from pds_core.school_years import close_school_year, open_school_year
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.teacher_menus import run_workspace_classroom_menu

pytestmark = pytest.mark.usefixtures("classroom_capability_disabled")

YEAR = "2026-2027"
CLASS = "english10_p2"
START = "2026-09-01T08:00:00-04:00"
AT = "2026-09-02T08:00:00-04:00"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "synthetic-workspace"
    folder.mkdir()
    open_school_year(folder, YEAR, opened_at=datetime.fromisoformat(START))
    return folder


def _run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    *,
    enabled: bool = True,
    interactive: bool = True,
    before_confirm: Callable[[], None] | None = None,
) -> tuple[SharedTeacherMenuResult, str, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_CLASS_PREVIEW_TEST_ONLY", enabled)
    request = SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="opaque-class-return",
        context=TeacherContextHint(workspace_root=root, display_label="Synthetic"),
    )
    iterator = iter(answers)
    out, err = io.StringIO(), io.StringIO()

    def read() -> str:
        answer = next(iterator)
        if answer == "C" and before_confirm is not None:
            before_confirm()
        return answer

    result = run_workspace_classroom_menu(
        request, read_line=read, output=out, error_output=err, interactive=interactive
    )
    assert result.return_token == "opaque-class-return"
    assert "opaque-class-return" not in out.getvalue() + err.getvalue()
    assert "Revalidate workspace" in result.message
    return result, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("enabled, interactive", [(False, True), (True, False)])
def test_public_boundary(
    root: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool, interactive: bool
) -> None:
    result, out, err = _run(
        root, monkeypatch, [], enabled=enabled, interactive=interactive
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert out == err == ""
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()
    assert not (root / "classes").exists()


def test_confirmed_class_creation(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, out, err = _run(root, monkeypatch, ["6", CLASS, AT, "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.CLASS})
    assert f"Class ID: {CLASS}" in out
    assert f"School year: {YEAR}" in out
    assert f"Created at: {AT}" in out
    assert "PREVIEW ONLY" in out and "no roster is created" in out
    assert re.search(r"\b[0-9a-f]{64}\b", out) is None
    metadata = load_class_metadata_for_class(root, CLASS)
    assert metadata.created_at.isoformat() == AT
    assert not class_roster_path(root, CLASS).exists()
    assert err == ""


@pytest.mark.parametrize(
    "answers, expected",
    [
        (["6", "B", "B"], TeacherMenuExit.BACK),
        (["6", CLASS, "B", "B"], TeacherMenuExit.BACK),
        (["6", CLASS, AT, "B", "B"], TeacherMenuExit.BACK),
        (["6", CLASS, AT, "no", "B"], TeacherMenuExit.BACK),
        (["6", CLASS, AT, ":notes", "B"], TeacherMenuExit.BACK),
        (["6", CLASS, AT, "M"], TeacherMenuExit.MAIN_MENU),
        (["6", "Q"], TeacherMenuExit.QUIT),
        (["6", CLASS], TeacherMenuExit.CANCELLED),
        (["6", CLASS, AT], TeacherMenuExit.CANCELLED),
    ],
)
def test_navigation_never_creates(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    expected: TeacherMenuExit,
) -> None:
    result, _, _ = _run(root, monkeypatch, answers)
    assert result.exit is expected
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not (root / "classes").exists()


def test_stale_year_refused(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def close() -> None:
        close_school_year(root, closed_at=datetime.fromisoformat(AT))

    result, _, err = _run(
        root, monkeypatch, ["6", CLASS, AT, "C"], before_confirm=close
    )
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "refused" in err
    assert not (root / "classes").exists()


def test_partial_write_receipt(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("private injected failure")

    monkeypatch.setattr(os, "link", fail)
    result, _, err = _run(root, monkeypatch, ["6", CLASS, AT, "C"])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.PARTIAL
    assert result.change_scopes == frozenset({TeacherChangeScope.CLASS})
    assert "empty_directory" in err
    assert "private injected failure" not in err
    assert class_dir(root, CLASS).is_dir()


def test_indeterminate_receipt(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actual = os.link

    def publish_then_fail(source: Path, destination: Path) -> None:
        actual(source, destination)
        raise OSError("injected after publication")

    monkeypatch.setattr(os, "link", publish_then_fail)
    result, _, err = _run(root, monkeypatch, ["6", CLASS, AT, "C"])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.INDETERMINATE
    assert result.change_scopes == frozenset({TeacherChangeScope.CLASS})
    assert "matches_review" in err
    assert "before retry" in err
