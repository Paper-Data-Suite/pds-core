"""Core #242 Slice A: gated callable classroom menu and navigation receipts.

All fixtures are synthetic. No workspace operations or producer imports occur.
"""

from __future__ import annotations

import inspect
import io
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

import pds_core.teacher_menus as menus
from pds_core.cli_support import screen
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.teacher_menus import run_workspace_classroom_menu

pytestmark = pytest.mark.usefixtures("classroom_capability_disabled")


@pytest.fixture(autouse=True)
def _disable_navigation_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menus, "_CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY", False)


def _request(tmp_path: Path) -> SharedTeacherMenuRequest:
    return SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="q-review-opaque-handoff",
        context=TeacherContextHint(
            workspace_root=tmp_path / "not-created",
            class_id="english12_p2",
            display_label="Synthetic English 12 Assignment",
        ),
    )


def _preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, choices: list[str]
) -> tuple[SharedTeacherMenuResult, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY", True)
    out = io.StringIO()
    inputs = iter(choices)
    result = run_workspace_classroom_menu(
        _request(tmp_path),
        read_line=lambda: next(inputs),
        output=out,
        interactive=True,
    )
    assert result.return_token == "q-review-opaque-handoff"
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert "Revalidate workspace, class, roster and work" in result.message
    assert not (tmp_path / "not-created").exists()
    assert result.return_token not in out.getvalue()
    return result, out.getvalue()


def test_callable_signature_matches_accepted_teacher_contract() -> None:
    signature = inspect.signature(run_workspace_classroom_menu)
    assert tuple(signature.parameters) == (
        "request",
        "read_line",
        "output",
        "interactive",
        "error_output",
    )
    for name in ("read_line", "output", "interactive", "error_output"):
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert "run_workspace_classroom_menu" in menus.__all__


def test_public_entry_refuses_before_full_qualification(tmp_path: Path) -> None:
    def no_input() -> str:
        raise AssertionError("Unqualified Core may not prompt")

    out = io.StringIO()
    result = run_workspace_classroom_menu(
        _request(tmp_path),
        read_line=no_input,
        output=out,
        interactive=True,
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert "Revalidate workspace, class, roster and work" in result.message
    assert out.getvalue() == ""
    assert not (tmp_path / "not-created").exists()
    assert "classroom.roster_edits.v1" in get_teacher_experience_capabilities()
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()


def test_noninteractive_refuses_even_if_test_preview_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(menus, "_CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY", True)

    def no_input() -> str:
        raise AssertionError("Noninteractive Core cannot prompt")

    out = io.StringIO()
    result = run_workspace_classroom_menu(
        _request(tmp_path),
        read_line=no_input,
        output=out,
        interactive=False,
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "interactive session" in result.message
    assert out.getvalue() == ""
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize(
    ("choices", "expected"),
    [
        (["B\n"], TeacherMenuExit.BACK),
        (["m\n"], TeacherMenuExit.MAIN_MENU),
        (["Q\n"], TeacherMenuExit.QUIT),
        (["1\n", "B\n", "B\n"], TeacherMenuExit.BACK),
        (["1\n", "1\n", "B\n", "B\n", "B\n"], TeacherMenuExit.BACK),
        (["1\n", "2\n", "M\n"], TeacherMenuExit.MAIN_MENU),
        (["2\n", "B\n", "B\n"], TeacherMenuExit.BACK),
        (["2\n", "3\n", "B\n", "B\n", "B\n"], TeacherMenuExit.BACK),
        (["2\n", "2\n", "Q\n"], TeacherMenuExit.QUIT),
        (["3\n", "1\n", "B\n", "B\n", "B\n"], TeacherMenuExit.BACK),
    ],
)
def test_b_m_q_navigation_is_returned_to_the_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    choices: list[str],
    expected: TeacherMenuExit,
) -> None:
    result, transcript = _preview(tmp_path, monkeypatch, choices)
    assert result.exit is expected
    assert "PDS Core" in transcript
    assert "Navigation preview only" in transcript
    assert "\x1b[" not in transcript


@pytest.mark.parametrize("failure", [EOFError, StopIteration, KeyboardInterrupt])
def test_interrupted_input_is_cancelled_without_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[BaseException]
) -> None:
    monkeypatch.setattr(menus, "_CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY", True)

    def interruption() -> str:
        raise failure()

    result = run_workspace_classroom_menu(
        _request(tmp_path),
        read_line=interruption,
        output=io.StringIO(),
        interactive=True,
    )
    assert result.exit is TeacherMenuExit.CANCELLED
    assert result.durability is TeacherDurability.NO_CHANGE


def test_empty_input_is_cancelled_and_nonstring_input_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(menus, "_CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY", True)
    for raw, expected in (
        ("", TeacherMenuExit.CANCELLED),
        (12, TeacherMenuExit.FAILED),
    ):
        result = run_workspace_classroom_menu(
            _request(tmp_path),
            read_line=lambda: cast(str, raw),
            output=io.StringIO(),
            interactive=True,
        )
        assert result.exit is expected
        assert result.durability is TeacherDurability.NO_CHANGE
        assert not (tmp_path / "not-created").exists()


def test_invalid_options_dont_intercept_unrelated_shortcuts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, transcript = _preview(
        tmp_path,
        monkeypatch,
        ["N\n", "W\n", ":notes\n", "A\n", "H\n", "0\n", "999\n", "B\n"],
    )
    assert result.exit is TeacherMenuExit.BACK
    assert transcript.count("Choose a listed option") >= 7
    assert "No workspace data is accessed or saved" in transcript


def test_private_token_never_appears_and_no_fs_inspection_occurs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(menus, "_CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY", True)
    root = tmp_path / "not-created"
    out = io.StringIO()

    def forbidden_read(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Navigation preview must not access storage")

    monkeypatch.setattr(Path, "open", forbidden_read)
    monkeypatch.setattr(Path, "mkdir", forbidden_read)
    monkeypatch.setattr(Path, "iterdir", forbidden_read)

    inputs = iter(("2\n", "3\n", "B\n", "B\n", "B\n"))
    result = run_workspace_classroom_menu(
        _request(tmp_path),
        read_line=lambda: next(inputs),
        output=out,
        interactive=True,
    )
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "q-review-opaque-handoff" not in out.getvalue()
    assert "Synthetic English 12 Assignment" in out.getvalue()
    assert not root.exists()


def test_unqualified_input_validation_is_prior_to_callbacks(tmp_path: Path) -> None:
    out = io.StringIO()
    request = _request(tmp_path)
    with pytest.raises(TypeError):
        run_workspace_classroom_menu(
            cast(SharedTeacherMenuRequest, object()),
            read_line=lambda: "B",
            output=out,
            interactive=True,
        )
    with pytest.raises(TypeError):
        run_workspace_classroom_menu(
            request,
            read_line=cast(Callable[[], str], "B"),
            output=out,
            interactive=True,
        )
    with pytest.raises(TypeError):
        run_workspace_classroom_menu(
            request,
            read_line=lambda: "B",
            output=out,
            interactive=cast(bool, "yes"),
        )
    with pytest.raises(TypeError):
        run_workspace_classroom_menu(
            request,
            read_line=lambda: "B",
            output=out,
            interactive=True,
            error_output=cast(io.StringIO, object()),
        )
    assert out.getvalue() == ""


def test_screen_redraws_only_on_navigation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(screen, "clear_screen", lambda stream: stream.write("\f"))
    result, transcript = _preview(tmp_path, monkeypatch, ["1", "2", "B", "B", "B"])
    screens = [part for part in transcript.split("\f") if part.strip()]
    assert len(screens) == 5
    assert "Navigation Preview" in screens[0]
    assert "School-year management" in screens[2]
    assert result.exit is TeacherMenuExit.BACK
