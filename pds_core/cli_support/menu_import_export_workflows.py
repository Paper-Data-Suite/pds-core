"""Import/export workflows for the interactive standards menu."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TextIO

from pds_core.cli_support.menu_profile_workflows import ProfileWorkflowMixin
from pds_core.cli_support.profiles import handle_profile_export, handle_profile_import
from pds_core.cli_support.standards_io import (
    handle_standards_export,
    handle_standards_import,
    load_standards_profile,
)
from pds_core.standards import (
    StandardsLibrary,
    StandardsReadError,
    StandardsValidationError,
    add_standards_profile,
    replace_standards_profile,
    standards_library_path,
)


class ImportExportWorkflowMixin(ProfileWorkflowMixin):
    """Import/export workflows assume menu runner attributes and prompt helpers."""

    args: argparse.Namespace
    library: StandardsLibrary
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def import_standards_data(self) -> None:
        actions = {
            "1": (self.import_full_library, True),
            "2": (self.import_profile, True),
        }
        self._run_submenu(
            "Import Standards Data",
            (
                "1. Import full standards library",
                "2. Import standards profile",
                "3. Back",
            ),
            "3",
            actions,
            guidance=(
                "Import reads standards data from JSON files.",
                "Files are validated before writing.",
                "Replacement requires confirmation.",
            ),
            pause_context="Import / Export menu",
        )

    def import_full_library(self) -> None:
        source_path = self._required_guided_prompt(
            "Import Full Standards Library",
            (
                "Enter Source JSON Path.",
                "This should be a full standards library JSON file.",
                r"Example: C:\Users\...\standards-library.json",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if source_path is None:
            return
        try:
            imported_library = self._load_library_file(source_path)
        except StandardsReadError as error:
            print(f"Error: {error}", file=self.stderr)
            return

        print(
            "This will replace the active workspace standards library.",
            file=self.stdout,
        )
        self._print_library_summary(imported_library)
        if not self._guided_confirm(
            (
                "This will replace the active workspace standards library after validation.",
                "Type YES to continue.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return

        target_path = standards_library_path(self.args.workspace_root)
        overwrite = False
        if target_path.exists():
            if not self._guided_confirm(
                (
                    "Workspace standards library already exists.",
                    "Type YES to overwrite.",
                    "Anything else cancels.",
                )
            ):
                self._cancelled()
                return
            overwrite = True

        command_args = self._command_args(
            path=source_path,
            replace=True,
            overwrite=overwrite,
        )
        code = handle_standards_import(
            command_args,
            self.library,
            self.stdout,
            self.stderr,
        )
        if code == 0:
            self.library = imported_library

    def import_profile(self) -> None:
        source_path = self._required_guided_prompt(
            "Import Standards Profile",
            (
                "Enter Source JSON Path.",
                "This should be one standalone standards profile JSON file.",
                r"Example: C:\Users\...\english-12-profile.json",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if source_path is None:
            return
        mode = self._guided_prompt(
            None,
            (
                "Choose Import Mode.",
                "1 = add only, 2 = replace existing profile.",
                "Leave blank to cancel.",
            ),
        )
        if mode in (None, "", "3"):
            self._cancelled()
            return
        add = mode == "1"
        replace = mode == "2"
        if not add and not replace:
            print("Invalid import mode.", file=self.stdout)
            return

        try:
            profile = load_standards_profile(source_path)
            updated_library = (
                add_standards_profile(self.library, profile)
                if add
                else replace_standards_profile(self.library, profile)
            )
        except (StandardsReadError, StandardsValidationError) as error:
            print(f"Error: {error}", file=self.stderr)
            return

        self._print_profile_summary("Import profile", profile)
        action = "Add" if add else "Replace"
        if not self._guided_confirm(
            (
                f"{action} profile {profile.profile_id}?",
                "Type YES to continue.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return

        command_args = self._command_args(
            path=source_path,
            add=add,
            replace=replace,
            overwrite=replace,
        )
        code = handle_profile_import(
            command_args,
            self.library,
            self.stdout,
            self.stderr,
        )
        if code == 0:
            self.library = updated_library

    def export_standards_data(self) -> None:
        actions = {
            "1": (self.export_full_library, True),
            "2": (self.export_profile, True),
        }
        self._run_submenu(
            "Export Standards Data",
            (
                "1. Export full standards library",
                "2. Export standards profile",
                "3. Back",
            ),
            "3",
            actions,
            guidance=(
                "Export writes standards data to JSON files.",
                "Existing files are not overwritten unless you confirm.",
            ),
            pause_context="Import / Export menu",
        )

    def export_full_library(self) -> None:
        target_path = self._required_guided_prompt(
            "Export Full Standards Library",
            (
                "Enter Target JSON Path.",
                r"Example: C:\Users\...\standards-library-export.json",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if target_path is None:
            return
        overwrite = self._confirm_overwrite(target_path)
        if overwrite is None:
            return
        self._print_library_summary(self.library)
        if not self._guided_confirm(
            (
                "Export full standards library?",
                "Type YES to continue.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return
        command_args = self._command_args(path=target_path, overwrite=overwrite)
        handle_standards_export(command_args, self.library, self.stdout, self.stderr)

    def export_profile(self) -> None:
        if not self._has_profiles():
            self._clear_screen()
            print("No standards profiles found.", file=self.stdout)
            return
        profile = self._prompt_existing_profile(
            "Export Standards Profile",
            (
                "Enter Durable Profile ID.",
                "Example: english_12_language_standards",
                "Use Browse Profiles first if you do not know the ID.",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if profile is None:
            return
        target_path = self._required_guided_prompt(
            None,
            (
                "Enter Target JSON Path.",
                r"Example: C:\Users\...\english-12-language-standards.json",
                "Leave blank to cancel.",
            ),
        )
        if target_path is None:
            return
        overwrite = self._confirm_overwrite(target_path)
        if overwrite is None:
            return
        self._print_profile_summary("Export profile", profile)
        if not self._guided_confirm(
            (
                f"Export profile {profile.profile_id}?",
                "Type YES to continue.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return
        command_args = self._command_args(
            profile_id=profile.profile_id,
            path=target_path,
            overwrite=overwrite,
        )
        handle_profile_export(command_args, self.library, self.stdout, self.stderr)

    def _confirm_overwrite(self, target_path: str) -> bool | None:
        path = Path(target_path)
        if not path.exists():
            return False
        if self._guided_confirm(
            (
                "Target file already exists.",
                "Type YES to overwrite.",
                "Anything else cancels.",
            )
        ):
            return True
        self._cancelled()
        return None

    def _load_library_file(self, path: str) -> StandardsLibrary:
        from pds_core.standards import load_standards_library

        return load_standards_library(path)

    def _command_args(self, **values: object) -> argparse.Namespace:
        data = {
            "workspace_root": self.args.workspace_root,
        }
        data.update(values)
        return argparse.Namespace(**data)

    def _print_library_summary(self, library: StandardsLibrary) -> None:
        print(
            f"Summary: {len(library.standards)} standards, "
            f"{len(library.profiles)} profiles.",
            file=self.stdout,
        )
