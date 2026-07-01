"""Starter standards workflows for the interactive standards menu."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.starter_standards import (
    handle_starter_standards_install,
    handle_starter_standards_list,
    handle_starter_standards_preview,
    handle_starter_standards_validate,
)
from pds_core.cli_support.menu_import_export_workflows import ImportExportWorkflowMixin
from pds_core.standards import StandardsLibrary, load_workspace_standards_library


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
        handle_starter_standards_list(
            self.args,
            self.library,
            self.stdout,
            self.stderr,
        )

    def preview_starter_standards(self) -> None:
        pack_id = self._starter_pack_prompt("Preview Starter Standards")
        if pack_id is None:
            return
        command_args = argparse.Namespace(pack_id=pack_id)
        handle_starter_standards_preview(
            command_args,
            self.library,
            self.stdout,
            self.stderr,
        )

    def validate_starter_standards(self) -> None:
        pack_id = self._optional_guided_prompt(
            "Validate Starter Standards",
            (
                "Enter a starter standards pack ID.",
                "Leave blank to validate all packs.",
                "Example: njsls_ela_2023",
            ),
            clear=True,
        )
        command_args = argparse.Namespace(pack_id=pack_id)
        handle_starter_standards_validate(
            command_args,
            self.library,
            self.stdout,
            self.stderr,
        )

    def install_starter_standards(self) -> None:
        pack_id = self._starter_pack_prompt("Install Starter Standards")
        if pack_id is None:
            return
        if not self._guided_confirm(
            (
                "Install this starter standards pack into standards/library.json?",
                "Existing matching records are skipped.",
                "Conflicting teacher-edited records are refused by default.",
                "Type YES to install.",
            ),
            title="Confirm Starter Standards Install",
            clear=True,
        ):
            self._cancelled()
            return

        command_args = argparse.Namespace(
            workspace_root=self.args.workspace_root,
            pack_id=pack_id,
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

    def _starter_pack_prompt(self, title: str) -> str | None:
        return self._required_guided_prompt(
            title,
            (
                "Enter Starter Standards Pack ID.",
                "Example: njsls_ela_2023",
            ),
            clear=True,
        )
