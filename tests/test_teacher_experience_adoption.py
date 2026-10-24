"""Core #237 Slice 5: synthetic caller handoff, not a real Notes integration.

All labels and work are fictitious. The harness exercises only the published
Core header, pure command-parser and existing Core navigation contracts.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import pytest

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
from pds_core.teacher_experience import (
    TEACHER_EXPERIENCE_CONTRACT_VERSION,
    get_teacher_experience_capabilities,
)
from pds_core.teacher_ui import TeacherScreenHeader, print_teacher_header


class SyntheticReviewScreen:
    """Caller-owned controller with injected output and no Notes menu.

    ``parser_opt_in`` here is a test-only choice-boundary toggle. A real
    consumer must ALSO qualify Notes records/menu before offering the action.
    No Core or producer work is selected, suspended, restored or mutated.
    """

    def __init__(self) -> None:
        self.output = io.StringIO()
        self.local_events: list[str] = []
        self.local_actions = {
            "n": "next-student",
            "w": "next-student-needing-review",
            "h": "local-help",
            "1": "local-review-action",
        }

    def draw(self) -> None:
        print_teacher_header(
            TeacherScreenHeader(
                "Quillan", "Review Student Work", "Fictional English 12 Assignment"
            ),
            output=self.output,
            color="never",
        )

    def read_choice(
        self,
        value: str,
        *,
        kind: PromptKind = PromptKind.MENU_CHOICE,
        interactive: bool = True,
        parser_opt_in: bool = False,
    ) -> str:
        # Caller decides prompt eligibility; the parser never reads a field.
        command = parse_shared_teacher_command(
            value,
            prompt_kind=kind,
            interactive=interactive,
            allow_notes=parser_opt_in,
        )
        if command is SharedTeacherCommand.NOTES:
            self.local_events.append("notes-request-only")
            return "notes-request-only"
        if kind is not PromptKind.MENU_CHOICE:
            self.local_events.append("literal-data")
            return value
        # Existing local/navigation parsing remains the owning menu's work.
        nav = parse_navigation_choice(value, allow_all=True)
        if nav is NavigationChoice.BACK:
            return "back"
        if nav is NavigationChoice.ALL:
            return "all"
        response = self.local_actions.get(value.strip().casefold(), "invalid-choice")
        self.local_events.append(response)
        return response


def test_source_contract_and_two_implemented_capabilities_are_separate() -> None:
    assert TEACHER_EXPERIENCE_CONTRACT_VERSION == "1"
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for not_implemented in (
        "notes.records.v1",
        "notes.menu.v1",
        "notes.cli.v1",
        "classroom.roster_edits.v1",
        "classroom.menu.v1",
        "notes.portability.v1",
    ):
        assert not_implemented not in get_teacher_experience_capabilities()


def test_header_and_typed_intent_do_not_dispatch_or_mutate(tmp_path: Path) -> None:
    screen = SyntheticReviewScreen()
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        screen.draw()
        assert screen.read_choice(":NoTeS", parser_opt_in=True) == (
            "notes-request-only"
        )
    assert screen.output.getvalue() == (
        "Quillan\nReview Student Work\nFictional English 12 Assignment\n"
    )
    assert screen.local_events == ["notes-request-only"]
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""
    assert list(tmp_path.iterdir()) == []


def test_actual_unqualified_notes_menu_must_not_be_activated() -> None:
    capabilities = get_teacher_experience_capabilities()
    allow_real_menu = all(
        required in capabilities for required in ("notes.records.v1", "notes.menu.v1")
    )
    assert allow_real_menu is False
    # A synthetic menu choice cannot produce a callable Notes service.
    screen = SyntheticReviewScreen()
    assert screen.read_choice(":notes", parser_opt_in=allow_real_menu) == (
        "invalid-choice"
    )
    assert "notes-request-only" not in screen.local_events


@pytest.mark.parametrize("value", [":notes", "  :NoTeS  "])
def test_opt_in_is_explicit_and_choice_scoped(value: str) -> None:
    screen = SyntheticReviewScreen()
    assert screen.read_choice(value, parser_opt_in=False) == "invalid-choice"
    assert screen.read_choice(value, parser_opt_in=True) == "notes-request-only"


@pytest.mark.parametrize(
    ("local_choice", "expected"),
    [
        ("N", "next-student"),
        ("n", "next-student"),
        ("W", "next-student-needing-review"),
        ("w", "next-student-needing-review"),
        ("H", "local-help"),
        ("h", "local-help"),
        ("1", "local-review-action"),
        ("A", "all"),
        ("a", "all"),
        ("B", "back"),
        ("b", "back"),
    ],
)
def test_local_quillan_like_shortcuts_are_preserved_with_opt_in(
    local_choice: str, expected: str
) -> None:
    screen = SyntheticReviewScreen()
    assert screen.read_choice(local_choice, parser_opt_in=True) == expected
    assert "notes-request-only" not in screen.local_events


@pytest.mark.parametrize("choice", ["M", " m "])
def test_existing_main_menu_unwind_is_not_swallowed(choice: str) -> None:
    with pytest.raises(ReturnToMainMenu):
        SyntheticReviewScreen().read_choice(choice, parser_opt_in=True)


@pytest.mark.parametrize("choice", ["Q", " q "])
def test_existing_quit_unwind_is_not_swallowed(choice: str) -> None:
    with pytest.raises(QuitPDS):
        SyntheticReviewScreen().read_choice(choice, parser_opt_in=True)


@pytest.mark.parametrize(
    "kind", [PromptKind.DATA_ENTRY, PromptKind.CONFIRMATION, PromptKind.PAUSE]
)
@pytest.mark.parametrize(
    "literal", [":notes", " :NoTeS ", "N", "W", "YES", "C:/tmp/:notes"]
)
def test_data_confirmations_and_pauses_keep_literal_input(
    kind: PromptKind, literal: str
) -> None:
    screen = SyntheticReviewScreen()
    assert screen.read_choice(literal, kind=kind, parser_opt_in=True) == literal
    assert screen.local_events == ["literal-data"]


@pytest.mark.parametrize("value", [":notes", "  :NoTeS  "])
def test_noninteractive_choice_never_intercepts(value: str) -> None:
    screen = SyntheticReviewScreen()
    assert screen.read_choice(value, parser_opt_in=True, interactive=False) == (
        "invalid-choice"
    )
    assert "notes-request-only" not in screen.local_events


@pytest.mark.parametrize("value", [":notes extra", "::notes", ":note", "2", "", "  "])
def test_near_matches_and_numbers_remain_local(value: str) -> None:
    assert SyntheticReviewScreen().read_choice(value, parser_opt_in=True) == (
        "invalid-choice"
    )


def test_collision_exception_keeps_preexisting_local_colon_action() -> None:
    screen = SyntheticReviewScreen()
    screen.local_actions[":notes"] = "existing-local-notes-action"
    assert screen.read_choice(":notes", parser_opt_in=False) == (
        "existing-local-notes-action"
    )
    assert "notes-request-only" not in screen.local_events


def test_synthetic_caller_never_changes_published_navigation_parser() -> None:
    assert parse_navigation_choice(":notes") is None
    assert parse_navigation_choice("N") is None
    assert parse_navigation_choice("W") is None
    assert parse_navigation_choice("B") is NavigationChoice.BACK
    with pytest.raises(ReturnToMainMenu):
        parse_navigation_choice("M")
    with pytest.raises(QuitPDS):
        parse_navigation_choice("Q")
