"""Stateful runner and top-level routing for the standards menu."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.menu_import_export_workflows import ImportExportWorkflowMixin
from pds_core.cli_support.standards_io import handle_standards_validate
from pds_core.standards import StandardsLibrary


class StandardsMenu(ImportExportWorkflowMixin):
    """Small stateful runner for the interactive standards menu."""

    def __init__(
        self,
        args: argparse.Namespace,
        library: StandardsLibrary,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> None:
        self.args = args
        self.library = library
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def run(self) -> int:
        actions = {
            "1": self.standards_submenu,
            "2": self.profiles_submenu,
            "3": self.import_export_submenu,
            "4": self.validate_standards_library,
        }
        while True:
            self._print_menu(
                "Standards Library",
                (
                    "1. Standards",
                    "2. Profiles",
                    "3. Import / Export",
                    "4. Validate library",
                    "5. Back",
                ),
            )
            choice = self._prompt("Choose an option: ")
            if choice is None or choice == "5":
                print("Back.", file=self.stdout)
                return 0
            action = actions.get(choice)
            if action is None:
                print("Invalid menu choice. Please try again.", file=self.stdout)
                continue
            action()
            if choice == "4":
                self._pause("Standards Library menu")

    def standards_submenu(self) -> None:
        self._run_submenu(
            "Standards",
            (
                "1. Browse standards",
                "2. Search standards",
                "3. View standard",
                "4. Add standard",
                "5. Back",
            ),
            "5",
            {
                "1": (self.browse_standards, True),
                "2": (self.search_standards, True),
                "3": (self.view_standard, True),
                "4": (self.add_standard, True),
            },
            pause_context="Standards menu",
        )

    def profiles_submenu(self) -> None:
        self._run_submenu(
            "Profiles",
            (
                "1. Browse profiles",
                "2. View profile",
                "3. Create Standard Profile",
                "4. Edit profile standards",
                "5. Import profile",
                "6. Export profile",
                "7. Back",
            ),
            "7",
            {
                "1": (self.browse_profiles, True),
                "2": (self.view_profile, True),
                "3": (self.create_profile, True),
                "4": (self.edit_profile_standards, False),
                "5": (self.import_profile, True),
                "6": (self.export_profile, True),
            },
            pause_context="Profiles menu",
        )

    def import_export_submenu(self) -> None:
        self._run_submenu(
            "Import / Export",
            (
                "1. Import full standards library",
                "2. Export full standards library",
                "3. Import profile",
                "4. Export profile",
                "5. Back",
            ),
            "5",
            {
                "1": (self.import_full_library, True),
                "2": (self.export_full_library, True),
                "3": (self.import_profile, True),
                "4": (self.export_profile, True),
            },
            guidance=(
                "Import and export read or write JSON files only after confirmation.",
            ),
            pause_context="Import / Export menu",
        )

    def validate_standards_library(self) -> None:
        self._workflow_screen(
            "Validate Standards Library",
            ("Checking the active workspace standards library.", "This does not write files."),
        )
        handle_standards_validate(self.args, self.library, self.stdout, self.stderr)
