"""Core #240-A: callable, isolated Notes navigation harness; no Notes writes."""

from __future__ import annotations

import inspect
import io
from pathlib import Path
from typing import cast

import pytest

import pds_core.teacher_menus as teacher_menus
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.teacher_menus import run_notes_tasks_menu


@pytest.fixture(autouse=True)
def _keep_scaffold_in_preview_or_unavailable_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve the Slice A test's unavailable case after Notes is enabled."""
    monkeypatch.setattr(teacher_menus, "_NOTES_MENU_QUALIFIED", False)


def _request(tmp_path: Path) -> SharedTeacherMenuRequest:
    return SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="q-review-screen-1",
        context=TeacherContextHint(
            workspace_root=tmp_path / "does-not-exist",
            display_label="Fictional English 12 Assignment",
        ),
    )


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    choices: list[str],
) -> tuple[TeacherMenuExit, str]:
    monkeypatch.setattr(teacher_menus, "_NAVIGATION_PREVIEW_TEST_ONLY", True)
    output = io.StringIO()
    lines = iter(choices)
    result = run_notes_tasks_menu(
        _request(tmp_path),
        read_line=lambda: next(lines),
        output=output,
        interactive=True,
    )
    assert result.return_token == "q-review-screen-1"
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not result.change_scopes
    assert not (tmp_path / "does-not-exist").exists()
    return result.exit, output.getvalue()


def test_public_api_shape_is_frozen() -> None:
    sig = inspect.signature(run_notes_tasks_menu)
    assert tuple(sig.parameters) == (
        "request",
        "read_line",
        "output",
        "interactive",
        "error_output",
    )
    for name in ("read_line", "output", "interactive", "error_output"):
        assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_public_entry_is_unavailable_until_real_notes_menu_qualifies(
    tmp_path: Path,
) -> None:
    def must_not_read() -> str:
        raise AssertionError("Slice A must not prompt")

    result = run_notes_tasks_menu(
        _request(tmp_path),
        read_line=must_not_read,
        output=io.StringIO(),
        interactive=True,
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not (tmp_path / "does-not-exist").exists()
    assert "notes.menu.v1" in get_teacher_experience_capabilities()
    assert "notes.records.v1" in get_teacher_experience_capabilities()


def test_noninteractive_refusal_consumes_no_input_even_in_test_preview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(teacher_menus, "_NAVIGATION_PREVIEW_TEST_ONLY", True)

    def no_input() -> str:
        raise AssertionError("A noninteractive call cannot consume input")

    output = io.StringIO()
    result = run_notes_tasks_menu(
        _request(tmp_path), read_line=no_input, output=output, interactive=False
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert output.getvalue() == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("choices", "expected"),
    [
        (["B\n"], TeacherMenuExit.BACK),
        (["M\n"], TeacherMenuExit.MAIN_MENU),
        (["Q\n"], TeacherMenuExit.QUIT),
        (["1\n", "B\n", "B\n"], TeacherMenuExit.BACK),
        (["1\n", "2\n", "B\n", "B\n", "B\n"], TeacherMenuExit.BACK),
        (["1\n", "3\n", "M\n"], TeacherMenuExit.MAIN_MENU),
        (["1\n", "1\n", "Q\n"], TeacherMenuExit.QUIT),
    ],
)
def test_navigation_returns_to_owning_caller(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    choices: list[str],
    expected: TeacherMenuExit,
) -> None:
    result, transcript = _invoke(monkeypatch, tmp_path, choices)
    assert result is expected
    assert "PDS Core\n" in transcript
    assert "Preview only. Nothing entered here can be saved." in transcript
    assert "q-review-screen-1" not in transcript


def test_eof_interrupt_and_invalid_result_do_not_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(teacher_menus, "_NAVIGATION_PREVIEW_TEST_ONLY", True)
    for fail in (EOFError, KeyboardInterrupt, StopIteration):

        def broken(failure: type[BaseException] = fail) -> str:
            raise failure()

        result = run_notes_tasks_menu(
            _request(tmp_path), read_line=broken, output=io.StringIO(), interactive=True
        )
        assert result.exit is TeacherMenuExit.CANCELLED
    result = run_notes_tasks_menu(
        _request(tmp_path),
        read_line=lambda: cast(str, 12),
        output=io.StringIO(),
        interactive=True,
    )
    assert result.exit is TeacherMenuExit.FAILED
    assert list(tmp_path.iterdir()) == []


def test_invalid_options_do_not_take_over_local_N_W_or_colon_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, transcript = _invoke(
        monkeypatch,
        tmp_path,
        ["N\n", "W\n", ":notes\n", "1\n", "2\n", "B\n", "B\n", "B\n"],
    )
    assert result is TeacherMenuExit.BACK
    assert transcript.count("Choose a listed option") >= 3
    assert "Task — Preview" in transcript
    assert "\x1b[" not in transcript  # redirected StringIO has no ANSI


def test_invalid_request_fails_before_io(tmp_path: Path) -> None:
    out = io.StringIO()
    with pytest.raises(TypeError):
        run_notes_tasks_menu(
            cast(SharedTeacherMenuRequest, object()),
            read_line=lambda: "B\n",
            output=out,
            interactive=True,
        )
    assert out.getvalue() == ""
