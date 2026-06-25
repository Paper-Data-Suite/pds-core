"""Prompt and screen helpers for the interactive standards menu."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import TextIO

from pds_core.cli_support import screen
from pds_core.cli_support.standards_mutation import write_workspace_mutated_library
from pds_core.standards import (
    StandardsLibrary,
    StandardsValidationError,
    StandardsWriteError,
    validate_standards_library,
)


class MenuPromptMixin:
    """Mixin methods assume menu runner attributes for IO and library state."""

    args: argparse.Namespace
    library: StandardsLibrary
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def _run_submenu(
        self,
        title: str,
        lines: tuple[str, ...],
        back_choice: str,
        actions: dict[str, tuple[Callable[[], None], bool]],
        *,
        guidance: tuple[str, ...] = (),
        pause_context: str,
    ) -> None:
        while True:
            self._print_menu(title, lines, guidance=guidance)
            choice = self._prompt("Choose an option: ")
            if choice is None or choice == back_choice:
                print("Back.", file=self.stdout)
                return
            action = actions.get(choice)
            if action is None:
                print("Invalid menu choice. Please try again.", file=self.stdout)
                continue
            action_func, pause_after = action
            action_func()
            if pause_after:
                self._pause(pause_context)

    def _print_menu(
        self,
        title: str,
        lines: tuple[str, ...],
        *,
        guidance: tuple[str, ...] = (),
    ) -> None:
        self._clear_screen()
        print(title, file=self.stdout)
        print("", file=self.stdout)
        for line in guidance:
            print(line, file=self.stdout)
        if guidance:
            print("", file=self.stdout)
        for line in lines:
            print(line, file=self.stdout)
        print("", file=self.stdout)

    def _workflow_screen(self, title: str, lines: tuple[str, ...] = ()) -> None:
        self._clear_screen()
        print(title, file=self.stdout)
        print("", file=self.stdout)
        for line in lines:
            print(line, file=self.stdout)
        if lines:
            print("", file=self.stdout)

    def _guided_prompt(
        self,
        title: str | None,
        lines: tuple[str, ...],
        *,
        clear: bool = False,
    ) -> str | None:
        if clear:
            self._clear_screen()
        if title is not None:
            print(title, file=self.stdout)
            print("", file=self.stdout)
        for line in lines:
            print(line, file=self.stdout)
        print("", file=self.stdout)
        return self._prompt("> ")

    def _required_guided_prompt(
        self,
        title: str | None,
        lines: tuple[str, ...],
        *,
        clear: bool = False,
    ) -> str | None:
        value = self._guided_prompt(title, lines, clear=clear)
        if value is None or value == "":
            self._cancelled()
            return None
        return value

    def _optional_guided_prompt(
        self,
        title: str | None,
        lines: tuple[str, ...],
        *,
        clear: bool = False,
    ) -> str | None:
        value = self._guided_prompt(title, lines, clear=clear)
        if value is None or value == "":
            return None
        return value

    def _guided_confirm(
        self,
        lines: tuple[str, ...],
        *,
        title: str | None = None,
        clear: bool = False,
    ) -> bool:
        value = self._guided_prompt(title, lines, clear=clear)
        return value == "YES"

    def _write_library(self, library: StandardsLibrary) -> bool:
        try:
            validate_standards_library(library)
            write_workspace_mutated_library(self.args, library)
        except (StandardsValidationError, StandardsWriteError) as error:
            print(f"Error: {error}", file=self.stderr)
            return False
        return True

    def _clear_screen(self) -> None:
        screen.clear_screen(self.stdout)
        screen.print_app_header(self.stdout)

    def _prompt(self, prompt: str) -> str | None:
        print(prompt, end="", file=self.stdout, flush=True)
        line = self.stdin.readline()
        print("", file=self.stdout)
        if line == "":
            return None
        return line.rstrip("\r\n").strip()

    def _cancelled(self) -> None:
        print("Cancelled.", file=self.stdout)

    def _pause(self, context: str = "menu") -> None:
        print("", file=self.stdout)
        print(f"Press Enter to return to the {context}...", file=self.stdout)
        print(">", end="", file=self.stdout, flush=True)
        self.stdin.readline()
        print("", file=self.stdout)

    def _has_standards(self) -> bool:
        return bool(self.library.standards)

    def _has_profiles(self) -> bool:
        return bool(self.library.profiles)
