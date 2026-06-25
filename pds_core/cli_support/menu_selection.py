"""Numbered selection helpers for menu workflows."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.formatting import readable_standard_block
from pds_core.cli_support.menu_prompts import MenuPromptMixin
from pds_core.standards import StandardDefinition, StandardsLibrary


class MenuSelectionMixin(MenuPromptMixin):
    """Mixin methods assume menu runner attributes for IO and library state."""

    args: argparse.Namespace
    library: StandardsLibrary
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def _select_standard_ids(
        self,
        title: str,
        *,
        available: tuple[StandardDefinition, ...],
        empty_message: str,
        include_filters: bool = True,
    ) -> tuple[str, ...] | None:
        del include_filters
        if not available:
            print(title, file=self.stdout)
            print("", file=self.stdout)
            print("No matching standards found.", file=self.stdout)
            print(empty_message, file=self.stdout)
            raw = self._prompt("> ")
            if raw is None:
                self._cancelled()
                return None
            return ()

        while True:
            print(title, file=self.stdout)
            print("", file=self.stdout)
            self._print_numbered_standards(available)
            print("Enter numbers separated by commas.", file=self.stdout)
            print("Example: 1,2,3", file=self.stdout)
            print(empty_message, file=self.stdout)
            raw = self._prompt("> ")
            if raw is None:
                self._cancelled()
                return None
            if raw == "":
                return ()
            try:
                indexes = self._parse_number_selection(raw, len(available))
            except ValueError as error:
                print(f"Invalid selection: {error}", file=self.stdout)
                continue
            return tuple(available[index - 1].standard_id for index in indexes)

    def _parse_number_selection(self, raw: str, maximum: int) -> tuple[int, ...]:
        selections: list[int] = []
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            if not value.isdecimal():
                raise ValueError(f"{value!r} is not a menu number.")
            number = int(value)
            if number < 1 or number > maximum:
                raise ValueError(f"{number} is outside 1-{maximum}.")
            if number not in selections:
                selections.append(number)
        if not selections:
            raise ValueError("enter at least one number or leave blank.")
        return tuple(selections)

    def _print_numbered_standards(
        self,
        definitions: tuple[StandardDefinition, ...],
    ) -> None:
        for index, definition in enumerate(definitions, start=1):
            for line in readable_standard_block(definition, index=index):
                print(line, file=self.stdout)
            print("", file=self.stdout)
