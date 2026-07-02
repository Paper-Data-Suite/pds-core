"""Starter standards workflows for the interactive standards menu."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.starter_standards import (
    handle_starter_standards_install,
    handle_starter_standards_preview,
    handle_starter_standards_validate,
)
from pds_core.cli_support.menu_import_export_workflows import ImportExportWorkflowMixin
from pds_core.standards import StandardsLibrary, load_workspace_standards_library
from pds_core.starter_standards import (
    StarterStandardsPackMetadata,
    list_starter_standards_packs,
)


class StarterStandardsWorkflowMixin(ImportExportWorkflowMixin):
    """Starter standards workflows assume menu runner attributes."""

    args: argparse.Namespace
    library: StandardsLibrary
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def starter_standards_submenu(self) -> None:
        self._run_submenu(
            "Starter Standards",
            (
                "1. List starter standards packs",
                "2. Preview starter standards pack",
                "3. Validate starter standards pack",
                "4. Install starter standards pack",
                "5. Back",
            ),
            "5",
            {
                "1": (self.list_starter_standards, True),
                "2": (self.preview_starter_standards, True),
                "3": (self.validate_starter_standards, True),
                "4": (self.install_starter_standards, True),
            },
            guidance=(
                "Starter standards install shared definitions and reusable profiles.",
                "Install writes only standards/library.json after confirmation.",
            ),
            pause_context="Starter Standards menu",
        )

    def list_starter_standards(self) -> None:
        self._workflow_screen(
            "List Starter Standards",
            ("Showing bundled starter standards packs.", "This does not write files."),
        )
        self._print_starter_pack_list(list_starter_standards_packs(), detailed=True)

    def preview_starter_standards(self) -> None:
        pack = self._choose_starter_pack("Preview Starter Standards")
        if pack is None:
            return
        self._workflow_screen("Preview Starter Standards")
        command_args = argparse.Namespace(pack_id=pack.pack_id)
        handle_starter_standards_preview(
            command_args,
            self.library,
            self.stdout,
            self.stderr,
        )

    def validate_starter_standards(self) -> None:
        self._print_menu(
            "Validate Starter Standards",
            (
                "1. Validate all starter standards packs",
                "2. Choose a starter standards pack to validate",
                "3. Back",
            ),
        )
        choice = self._prompt("Choose an option: ")
        if choice is None or choice == "3":
            print("Back.", file=self.stdout)
            return
        if choice == "1":
            pack_id = None
        elif choice == "2":
            pack = self._choose_starter_pack("Choose Starter Standards Pack")
            if pack is None:
                return
            pack_id = pack.pack_id
        else:
            print("Invalid menu choice. Please try again.", file=self.stdout)
            return
        command_args = argparse.Namespace(pack_id=pack_id)
        handle_starter_standards_validate(
            command_args,
            self.library,
            self.stdout,
            self.stderr,
        )

    def install_starter_standards(self) -> None:
        pack = self._choose_starter_pack("Install Starter Standards")
        if pack is None:
            return
        if not self._guided_confirm(
            (
                "Selected starter standards pack:",
                pack.title,
                "",
                f"Pack ID: {pack.pack_id}",
                f"Source: {pack.source}",
                f"Grade bands: {', '.join(pack.grade_bands)}",
                f"Standards: {pack.standard_count}",
                f"Profiles: {pack.profile_count}",
                f"Profile IDs: {', '.join(pack.profile_ids)}",
                "",
                "Install this starter standards pack into standards/library.json?",
                "",
                "Existing matching records are skipped.",
                "Conflicting teacher-edited records are refused by default.",
                "No standards usage events will be recorded.",
                "Type YES to install.",
            ),
            title="Confirm Starter Standards Install",
            clear=True,
        ):
            self._cancelled()
            return

        command_args = argparse.Namespace(
            workspace_root=self.args.workspace_root,
            pack_id=pack.pack_id,
            overwrite=False,
        )
        code = handle_starter_standards_install(
            command_args,
            self.library,
            self.stdout,
            self.stderr,
        )
        if code == 0:
            self.library = load_workspace_standards_library(self.args.workspace_root)

    def _choose_starter_pack(self, title: str) -> StarterStandardsPackMetadata | None:
        packs = list_starter_standards_packs()
        if not packs:
            self._workflow_screen(title, ("No starter standards packs found.",))
            return None

        while True:
            self._workflow_screen(title, ("Available starter standards packs:",))
            self._print_starter_pack_list(packs, detailed=True)
            back_choice = str(len(packs) + 1)
            print(f"{back_choice}. Back", file=self.stdout)
            print("", file=self.stdout)
            choice = self._prompt("Choose a starter standards pack: ")
            if choice is None or choice == back_choice:
                print("Back.", file=self.stdout)
                return None
            if choice.isdecimal():
                index = int(choice) - 1
                if 0 <= index < len(packs):
                    return packs[index]
            print("Invalid menu choice. Please try again.", file=self.stdout)

    def _print_starter_pack_list(
        self,
        packs: tuple[StarterStandardsPackMetadata, ...],
        *,
        detailed: bool,
    ) -> None:
        if not packs:
            print("No starter standards packs found.", file=self.stdout)
            return
        for index, pack in enumerate(packs, start=1):
            print(f"{index}. {pack.title}", file=self.stdout)
            if detailed:
                print(f"   Pack ID: {pack.pack_id}", file=self.stdout)
                print(f"   Source: {pack.source}", file=self.stdout)
                print(f"   Grade bands: {', '.join(pack.grade_bands)}", file=self.stdout)
                print(f"   Standards: {pack.standard_count}", file=self.stdout)
                print(f"   Profiles: {pack.profile_count}", file=self.stdout)
            print("", file=self.stdout)
