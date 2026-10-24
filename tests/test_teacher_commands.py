"""Core #237 Slice 4: exact v1 prompt-scope and collision conformance."""

from __future__ import annotations

import contextlib
import inspect
import io
import os
import subprocess
import sys
from pathlib import Path
from typing import get_type_hints

import pytest

import pds_core.teacher_commands as teacher_commands
from pds_core.menu_navigation import (
    NavigationChoice,
    QuitPDS,
    ReturnToMainMenu,
    parse_navigation_choice,
)
from pds_core.teacher_commands import (
    PromptKind,
    SharedTeacherCommand,
    parse_shared_teacher_command,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities


def parse(
    value: str,
    *,
    prompt_kind: PromptKind = PromptKind.MENU_CHOICE,
    interactive: bool = True,
    allow_notes: bool = True,
) -> SharedTeacherCommand | None:
    return parse_shared_teacher_command(
        value,
        prompt_kind=prompt_kind,
        interactive=interactive,
        allow_notes=allow_notes,
    )


def test_public_exports_and_enum_values_are_exact() -> None:
    assert teacher_commands.__all__ == (
        "PromptKind",
        "SharedTeacherCommand",
        "parse_shared_teacher_command",
    )
    assert list(PromptKind) == [
        PromptKind.MENU_CHOICE,
        PromptKind.DATA_ENTRY,
        PromptKind.CONFIRMATION,
        PromptKind.PAUSE,
    ]
    assert [v.value for v in PromptKind] == [
        "menu_choice",
        "data_entry",
        "confirmation",
        "pause",
    ]
    assert list(SharedTeacherCommand) == [SharedTeacherCommand.NOTES]
    assert SharedTeacherCommand.NOTES.value == "notes"
    hints = get_type_hints(parse_shared_teacher_command)
    assert hints["value"] is str
    assert hints["prompt_kind"] is PromptKind
    assert hints["interactive"] is bool
    assert hints["allow_notes"] is bool
    assert hints["return"] == SharedTeacherCommand | None
    signature = inspect.signature(parse_shared_teacher_command)
    assert tuple(signature.parameters) == (
        "value",
        "prompt_kind",
        "interactive",
        "allow_notes",
    )
    assert signature.parameters["prompt_kind"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["interactive"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["allow_notes"].default is False


@pytest.mark.parametrize(
    "value", [":notes", " :notes ", "  :NoTeS  ", "\t:NOTES\t", "\u2003:NoTeS\u2003"]
)
def test_c01_c02_exact_shared_token_with_casefold_and_strip(value: str) -> None:
    assert parse(value) is SharedTeacherCommand.NOTES


@pytest.mark.parametrize("kind", list(PromptKind))
@pytest.mark.parametrize("interactive", [False, True])
@pytest.mark.parametrize("allow_notes", [False, True])
def test_prompt_kind_and_flags_have_orthogonal_authority(
    kind: PromptKind, interactive: bool, allow_notes: bool
) -> None:
    expected = (
        SharedTeacherCommand.NOTES
        if kind is PromptKind.MENU_CHOICE and interactive and allow_notes
        else None
    )
    assert (
        parse(
            ":notes", prompt_kind=kind, interactive=interactive, allow_notes=allow_notes
        )
        is expected
    )


@pytest.mark.parametrize(
    "local_or_near_miss",
    [
        "N",
        "n",
        "W",
        "w",
        "B",
        "b",
        "M",
        "m",
        "Q",
        "q",
        "H",
        "h",
        "A",
        "a",
        "1",
        "0",
        "25",
        "",
        " ",
        ":note",
        ":not",
        "::notes",
        ":notes anything",
        "anything :notes",
        "notes",
        ":debug",
        ":notes:",
        ":notes\n:notes",
        ":notes\x00",
        "：notes",
        ":nOtEs?",
    ],
)
def test_c07_c08_local_navigation_numeric_and_near_miss_untouched(
    local_or_near_miss: str,
) -> None:
    assert parse(local_or_near_miss) is None


@pytest.mark.parametrize(
    "kind", [PromptKind.DATA_ENTRY, PromptKind.CONFIRMATION, PromptKind.PAUSE]
)
@pytest.mark.parametrize("literal", [":notes", " :NoTeS ", "notes", "YES", "N", "W"])
def test_c05_c06_field_confirmation_and_pause_are_literal(
    kind: PromptKind, literal: str
) -> None:
    assert parse(literal, prompt_kind=kind) is None


@pytest.mark.parametrize("value", [None, b":notes", 1, True, [], {}, object()])
def test_c09_invalid_value_types_rejected_even_when_disabled(value: object) -> None:
    for enabled in (False, True):
        with pytest.raises(TypeError, match="value"):
            parse_shared_teacher_command(
                value,  # type: ignore[arg-type]
                prompt_kind=PromptKind.MENU_CHOICE,
                interactive=False,
                allow_notes=enabled,
            )


@pytest.mark.parametrize(
    "kind", [None, "menu_choice", "MENU_CHOICE", "data_entry", 1, object()]
)
def test_c09_prompt_kind_must_be_actual_enum_member(kind: object) -> None:
    with pytest.raises(TypeError, match="prompt_kind"):
        parse_shared_teacher_command(
            ":notes",
            prompt_kind=kind,  # type: ignore[arg-type]
            interactive=True,
            allow_notes=True,
        )


@pytest.mark.parametrize("bad_flag", [None, 0, 1, "true", [], object()])
@pytest.mark.parametrize("field", ["interactive", "allow_notes"])
def test_c09_flags_require_actual_boolean_types(field: str, bad_flag: object) -> None:
    flags: dict[str, object] = {"interactive": True, "allow_notes": True}
    flags[field] = bad_flag
    with pytest.raises(TypeError, match=field):
        parse_shared_teacher_command(
            ":notes",
            prompt_kind=PromptKind.MENU_CHOICE,
            **flags,  # type: ignore[arg-type]
        )


def test_invalid_later_argument_not_hidden_by_early_disabled_flag() -> None:
    with pytest.raises(TypeError, match="allow_notes"):
        parse_shared_teacher_command(
            ":notes",
            prompt_kind=PromptKind.DATA_ENTRY,
            interactive=False,
            allow_notes=1,  # type: ignore[arg-type]
        )


def test_allow_notes_default_is_off_and_required_flags_not_implicit() -> None:
    assert (
        parse_shared_teacher_command(
            ":notes", prompt_kind=PromptKind.MENU_CHOICE, interactive=True
        )
        is None
    )
    with pytest.raises(TypeError):
        parse_shared_teacher_command(":notes")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        parse_shared_teacher_command(":notes", PromptKind.MENU_CHOICE, True)  # type: ignore[call-arg]


def test_existing_navigation_parser_still_handles_b_m_q_a_without_notes() -> None:
    for selection in ("N", "n", "W", "w", "H", "h", "1"):
        assert parse(selection) is None
        assert parse_navigation_choice(selection) is None
    assert parse(":notes") is SharedTeacherCommand.NOTES
    assert parse_navigation_choice(":notes") is None
    assert parse("B") is None
    assert parse_navigation_choice("B") is NavigationChoice.BACK
    with pytest.raises(ReturnToMainMenu):
        parse_navigation_choice("M")
    with pytest.raises(QuitPDS):
        parse_navigation_choice("Q")
    assert parse("A") is None
    assert parse_navigation_choice("A") is None
    assert parse_navigation_choice("A", allow_all=True) is NavigationChoice.ALL


def test_c12_local_colon_command_collision_stays_caller_owned() -> None:
    # The owning menu deliberately disables the shared parser on this screen.
    assert parse(":notes", allow_notes=False) is None
    local_actions = {":notes": "existing-local-action", "N": "next-student"}
    assert local_actions[":notes"] == "existing-local-action"
    assert parse("N") is None
    assert local_actions["N"] == "next-student"


def test_c13_parser_capability_does_not_imply_a_working_notes_service() -> None:
    capabilities = get_teacher_experience_capabilities()
    assert capabilities == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert "notes.records.v1" not in capabilities
    assert "notes.menu.v1" not in capabilities
    assert "notes.cli.v1" not in capabilities
    # Receiving a typed request is not dispatch, persistence, or authorization.
    assert parse(":notes") is SharedTeacherCommand.NOTES


def test_parser_does_not_access_global_streams_input_or_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unexpected_input(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("Parser unexpectedly read global input")

    monkeypatch.setattr("builtins.input", unexpected_input)
    stdout = io.StringIO()
    stderr = io.StringIO()
    before = list(tmp_path.iterdir())
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        assert parse(":notes") is SharedTeacherCommand.NOTES
        assert parse(":notes", prompt_kind=PromptKind.DATA_ENTRY) is None
        with pytest.raises(TypeError):
            parse_shared_teacher_command(
                8,  # type: ignore[arg-type]
                prompt_kind=PromptKind.MENU_CHOICE,
                interactive=True,
                allow_notes=True,
            )
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""
    assert list(tmp_path.iterdir()) == before


def test_fresh_process_import_and_parse_are_silent_and_read_only(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(project_root), env.get("PYTHONPATH", "")))
    source = (
        "from pds_core.teacher_commands import PromptKind, SharedTeacherCommand, "
        "parse_shared_teacher_command; "
        "assert parse_shared_teacher_command(':notes', "
        "prompt_kind=PromptKind.MENU_CHOICE, interactive=True, allow_notes=True) "
        "is SharedTeacherCommand.NOTES"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", source],
        cwd=tmp_path,
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []
