"""Interactive standards management menu for teacher-facing CLI workflows."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace as dataclass_replace
from pathlib import Path
from collections.abc import Callable
from typing import TextIO

from pds_core.cli_support import screen
from pds_core.cli_support.context import StandardFilters
from pds_core.cli_support.profiles import (
    handle_profile_export,
    handle_profile_import,
    handle_profile_show,
    standards_profile_from_args,
)
from pds_core.cli_support.standards_io import (
    handle_standards_export,
    handle_standards_import,
    handle_standards_validate,
    load_standards_profile,
)
from pds_core.cli_support.standards_mutation import write_workspace_mutated_library
from pds_core.cli_support.standards_read import (
    handle_standards_list,
    handle_standards_profiles,
    handle_standards_search,
    handle_standards_show,
    matching_standards,
    parse_category_path,
)
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
    add_standard_definition,
    add_standards_profile,
    find_standard_definition,
    find_standards_profile,
    replace_standards_profile,
    standards_library_path,
    validate_standards_library,
)

STANDARD_ID_GUIDANCE: tuple[str, ...] = (
    "Use the full durable standard_id, not only the display code.",
    "Correct example: njsls-ela:L.KL.11-12.2",
    "Not enough: L.KL.11-12.2",
)

STANDARD_ID_COPY_GUIDANCE = "Use Browse Standards or Search Standards first if you need to copy IDs."

DASH_TRANSLATION = str.maketrans(
    {
        "\u2013": "-",
        "\u2014": "-",
    }
)

_DESCRIPTION_PREVIEW_LENGTH = 120


def handle_standards_menu(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Run the interactive standards management menu."""
    stdin = getattr(args, "stdin", sys.stdin)
    runner = StandardsMenu(args, library, stdin, stdout, stderr)
    return runner.run()


class StandardsMenu:
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
            "1": (self.browse_standards, True),
            "2": (self.search_standards, True),
            "3": (self.view_standard, True),
            "4": (self.add_standard, True),
            "5": (self.browse_profiles, True),
            "6": (self.view_profile, True),
            "7": (self.create_profile, True),
            "8": (self.edit_profile_standards, False),
            "9": (self.import_standards_data, False),
            "10": (self.export_standards_data, False),
            "11": (self.validate_standards_library, True),
        }
        while True:
            self._print_menu(
                "Standards Management",
                (
                    "1. Browse standards",
                    "2. Search standards",
                    "3. View standard",
                    "4. Add standard",
                    "5. Browse profiles",
                    "6. View profile",
                    "7. Create Standard Profile",
                    "8. Edit profile standards",
                    "9. Import standards data",
                    "10. Export standards data",
                    "11. Validate standards library",
                    "12. Back",
                ),
            )
            choice = self._prompt("Choose an option: ")
            if choice is None or choice == "12":
                print("Back.", file=self.stdout)
                return 0
            action = actions.get(choice)
            if action is None:
                print("Invalid menu choice. Please try again.", file=self.stdout)
                continue
            action_func, pause_after = action
            action_func()
            if pause_after:
                self._pause()

    def browse_standards(self) -> None:
        if not self._has_standards():
            screen.clear_screen(self.stdout)
            print("No standards found.", file=self.stdout)
            return
        self._workflow_screen("Browse Standards")
        filters = self._standard_filter_args()
        if filters is None:
            return
        handle_standards_list(filters, self.library, self.stdout, self.stderr)

    def search_standards(self) -> None:
        if not self._has_standards():
            screen.clear_screen(self.stdout)
            print("No standards found.", file=self.stdout)
            return
        query = self._required_guided_prompt(
            "Search Standards",
            (
                "Enter search text.",
                "Search checks IDs, display codes, names, descriptions, and metadata.",
                "Example: language or RL.CR.11-12.1",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if query is None:
            return
        filters = self._standard_filter_args()
        if filters is None:
            return
        filters.query = query
        handle_standards_search(filters, self.library, self.stdout, self.stderr)

    def view_standard(self) -> None:
        if not self._has_standards():
            screen.clear_screen(self.stdout)
            print("No standards found.", file=self.stdout)
            return
        standard_id = self._required_guided_prompt(
            "View Standard",
            (
                "Enter Durable Standard ID.",
                *STANDARD_ID_GUIDANCE,
                STANDARD_ID_COPY_GUIDANCE,
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if standard_id is None:
            return
        standard_id = normalize_standard_id_entry(standard_id)
        command_args = argparse.Namespace(standard_id=standard_id)
        handle_standards_show(command_args, self.library, self.stdout, self.stderr)

    def add_standard(self) -> None:
        standard_id = self._required_guided_prompt(
            "Add Standard",
            (
                "Enter Durable Standard ID.",
                "Use lowercase source prefix plus display code.",
                "Example: njsls-ela:L.VI.11-12.4",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if standard_id is None:
            return
        standard_id = normalize_standard_id_entry(standard_id)
        if not self._valid_teacher_standard_id(standard_id):
            print(
                "Error: standard_id must include a source prefix and display code, "
                "for example njsls-ela:L.VI.11-12.4.",
                file=self.stderr,
            )
            return
        if find_standard_definition(self.library, standard_id) is not None:
            print(f"Error: duplicate standard_id: {standard_id}", file=self.stderr)
            return

        code = self._required_guided_prompt(
            None,
            (
                "Enter Display Code.",
                "Example: L.VI.11-12.4",
                "Leave blank to cancel.",
            ),
        )
        if code is None:
            return
        short_name = self._optional_guided_prompt(
            None,
            (
                "Enter Short Name.",
                "Example: Figurative Language and Word Relationships",
                "Leave blank to use the display code.",
            ),
        )
        description = self._required_guided_prompt(
            None,
            (
                "Enter Standard Description.",
                "Paste or type the full standard statement.",
                "Example: Demonstrate understanding of figurative language, "
                "word relationships, and nuances in word meanings.",
                "Leave blank to cancel.",
            ),
        )
        if description is None:
            return
        source = self._optional_guided_prompt(
            None,
            (
                "Enter Source.",
                "Example: NJSLS-ELA 2023",
                "Leave blank to use Unspecified.",
            ),
        )
        subject = self._optional_guided_prompt(
            None,
            (
                "Enter Subject.",
                "Example: English Language Arts",
                "Leave blank for no subject.",
            ),
        )
        course = self._optional_guided_prompt(
            None,
            ("Enter Course.", "Example: English 12", "Leave blank for no course."),
        )
        domain = self._optional_guided_prompt(
            None,
            (
                "Enter Domain or Category.",
                "Example: Language",
                "Leave blank for no domain/category.",
            ),
        )
        try:
            definition = StandardDefinition(
                standard_id=standard_id,
                code=code,
                source=source or "Unspecified",
                short_name=short_name or code,
                description=description,
                subject=subject,
                course=course,
                domain=domain,
                category_path=(domain,) if domain else (),
                active=True,
            )
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return

        subparts = self._collect_standard_subparts(definition)
        if subparts is None:
            return

        try:
            updated_library = add_standard_definition(self.library, definition)
            for subpart in subparts:
                updated_library = add_standard_definition(updated_library, subpart)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return

        self._print_standard_review(definition, subparts)
        if not self._guided_confirm(
            (
                "Type YES to create this standard.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return
        if self._write_library(updated_library):
            self.library = updated_library
            print(f"Created standard {definition.standard_id}.", file=self.stdout)
            for subpart in subparts:
                print(f"Created standard {subpart.standard_id}.", file=self.stdout)

    def browse_profiles(self) -> None:
        if not self._has_profiles():
            screen.clear_screen(self.stdout)
            print("No standards profiles found.", file=self.stdout)
            return
        self._workflow_screen("Browse Profiles")
        filters = self._profile_filter_args()
        if filters is None:
            return
        handle_standards_profiles(filters, self.library, self.stdout, self.stderr)

    def view_profile(self) -> None:
        if not self._has_profiles():
            screen.clear_screen(self.stdout)
            print("No standards profiles found.", file=self.stdout)
            return
        profile_id = self._required_guided_prompt(
            "View Profile",
            (
                "Enter Durable Profile ID.",
                "Example: english_12_njsls",
                "Use Browse Profiles first if you do not know the ID.",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if profile_id is None:
            return
        command_args = argparse.Namespace(profile_id=profile_id)
        handle_profile_show(command_args, self.library, self.stdout, self.stderr)

    def create_profile(self) -> None:
        if not self._has_standards() and not self._empty_standards_profile_choice():
            return
        profile_id = self._required_guided_prompt(
            "Create Standard Profile",
            (
                "Enter Durable Profile ID.",
                "This is the permanent ID for this standards collection.",
                "Use lowercase letters, numbers, and underscores.",
                "Example: english_12_language_standards",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if profile_id is None:
            return
        metadata = self._profile_metadata()
        standards = (
            ()
            if not self._has_standards()
            else self._select_standard_ids(
                "Select Standards for This Profile",
                available=self._filtered_available_standards(),
                empty_message="Leave blank for an empty profile.",
            )
        )
        if standards is None:
            return

        command_args = argparse.Namespace(
            profile_id=profile_id,
            standards=list(standards),
            **metadata,
        )
        try:
            profile = standards_profile_from_args(profile_id, command_args)
            updated_library = add_standards_profile(self.library, profile)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return

        self._print_standard_profile_review(profile)
        if not self._guided_confirm(
            (
                "Type YES to create this standard profile.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return
        if self._write_library(updated_library):
            self.library = updated_library
            print(f"Created standards profile {profile.profile_id}.", file=self.stdout)

    def edit_profile_standards(self) -> None:
        if not self._has_profiles():
            screen.clear_screen(self.stdout)
            print("No standards profiles found.", file=self.stdout)
            self._pause()
            return
        if not self._has_standards():
            screen.clear_screen(self.stdout)
            print("No standards exist yet.", file=self.stdout)
            print(
                "Create standards before editing profile membership.",
                file=self.stdout,
            )
            self._pause()
            return
        actions = {
            "1": self.add_standard_to_profile,
            "2": self.remove_standard_from_profile,
            "3": self.replace_profile_standards,
        }
        while True:
            self._print_menu(
                "Edit Profile Standards",
                (
                    "1. Add standard to profile",
                    "2. Remove standard from profile",
                    "3. Replace profile standards",
                    "4. Back",
                ),
                guidance=(
                    "This changes which existing standards belong to an "
                    "existing standards profile.",
                    "It does not create, edit, or delete standard definitions.",
                    "It does not delete profiles.",
                ),
            )
            choice = self._prompt("Choose an option: ")
            if choice is None or choice == "4":
                print("Back.", file=self.stdout)
                return
            action = actions.get(choice)
            if action is None:
                print("Invalid menu choice. Please try again.", file=self.stdout)
                continue
            action()
            self._pause()

    def add_standard_to_profile(self) -> None:
        profile = self._prompt_existing_profile(
            "Add Standard to Profile",
            (
                "Enter Durable Profile ID.",
                "This profile will receive the standard.",
                "Example: english_12_language_standards",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if profile is None:
            return
        available = tuple(
            definition
            for definition in self.library.standards
            if definition.standard_id not in profile.standards
        )
        standards = self._select_standard_ids(
            "Available Standards Not In This Profile",
            available=available,
            empty_message="Leave blank to cancel.",
            include_filters=False,
        )
        if standards is None or not standards:
            return

        updated_profile = dataclass_replace(
            profile,
            standards=profile.standards + standards,
        )
        self._replace_profile_membership(
            updated_profile,
            f"Add selected standards to profile {profile.profile_id}?",
            f"Added {len(standards)} standard(s) to profile {profile.profile_id}.",
        )

    def remove_standard_from_profile(self) -> None:
        profile = self._prompt_existing_profile(
            "Remove Standard from Profile",
            (
                "Enter Durable Profile ID.",
                "This only changes profile membership. It does not delete the standard.",
                "Example: english_12_language_standards",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if profile is None:
            return
        current = tuple(
            definition
            for standard_id in profile.standards
            for definition in (find_standard_definition(self.library, standard_id),)
            if definition is not None
        )
        standards = self._select_standard_ids(
            "Current Standards",
            available=current,
            empty_message="Leave blank to cancel.",
            include_filters=False,
        )
        if standards is None or not standards:
            return

        updated_profile = dataclass_replace(
            profile,
            standards=tuple(
                existing for existing in profile.standards if existing not in standards
            ),
        )
        self._replace_profile_membership(
            updated_profile,
            f"Remove selected standards from profile {profile.profile_id}?",
            f"Removed {len(standards)} standard(s) from profile {profile.profile_id}.",
        )

    def replace_profile_standards(self) -> None:
        profile = self._prompt_existing_profile(
            "Replace Profile Standards",
            (
                "Enter Durable Profile ID.",
                "This will replace only the profile's standards list.",
                "Profile metadata will be preserved.",
                "Example: english_12_language_standards",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if profile is None:
            return
        standards = self._select_standard_ids(
            "Select Replacement Standards",
            available=self._filtered_available_standards(),
            empty_message="Leave blank for no standards.",
        )
        if standards is None:
            return
        try:
            updated_profile = dataclass_replace(profile, standards=standards)
            updated_library = replace_standards_profile(self.library, updated_profile)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return

        self._print_profile_summary("Replace profile standards", updated_profile)
        if not self._guided_confirm(
            (
                f"Replace standards for profile {profile.profile_id}?",
                "Type YES to continue.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return
        if self._write_library(updated_library):
            self.library = updated_library
            print(
                f"Replaced standards for profile {profile.profile_id}.",
                file=self.stdout,
            )

    def import_standards_data(self) -> None:
        actions = {
            "1": self.import_full_library,
            "2": self.import_profile,
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
            "1": self.export_full_library,
            "2": self.export_profile,
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
            screen.clear_screen(self.stdout)
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

    def validate_standards_library(self) -> None:
        self._workflow_screen(
            "Validate Standards Library",
            ("Checking the active workspace standards library.", "This does not write files."),
        )
        handle_standards_validate(self.args, self.library, self.stdout, self.stderr)

    def _replace_profile_membership(
        self,
        updated_profile: StandardsProfile,
        prompt_text: str,
        success_message: str,
    ) -> None:
        try:
            updated_library = replace_standards_profile(self.library, updated_profile)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return
        self._print_profile_summary("Profile membership change", updated_profile)
        if not self._guided_confirm(
            (
                prompt_text,
                "Type YES to continue.",
                "Anything else cancels.",
            )
        ):
            self._cancelled()
            return
        if self._write_library(updated_library):
            self.library = updated_library
            print(success_message, file=self.stdout)

    def _write_library(self, library: StandardsLibrary) -> bool:
        try:
            validate_standards_library(library)
            write_workspace_mutated_library(self.args, library)
        except (StandardsValidationError, StandardsWriteError) as error:
            print(f"Error: {error}", file=self.stderr)
            return False
        return True

    def _empty_standards_profile_choice(self) -> bool:
        self._print_menu(
            "Create Standard Profile",
            (
                "No standards exist yet.",
                "",
                "Profiles are collections of existing standards.",
                "1. Add Standard",
                "2. Create empty profile",
                "3. Back",
            ),
        )
        choice = self._prompt("> ")
        if choice == "1":
            self.add_standard()
            return False
        if choice == "2":
            return True
        print("Back.", file=self.stdout)
        return False

    def _filtered_available_standards(self) -> tuple[StandardDefinition, ...]:
        filters = StandardFilters(
            source=None,
            subject=self._optional_guided_prompt(
                "Filter Standards for Profile Selection",
                (
                    "Enter subject filter.",
                    "Example: English Language Arts",
                    "Leave blank for any subject.",
                ),
            ),
            course=self._optional_guided_prompt(
                None,
                (
                    "Enter course filter.",
                    "Example: English 12",
                    "Leave blank for any course.",
                ),
            ),
            domain=self._optional_guided_prompt(
                None,
                (
                    "Enter domain/category filter.",
                    "Example: Language",
                    "Leave blank for any domain/category.",
                ),
            ),
            category_path_prefix=(),
            available_module=None,
            active=None,
        )
        return matching_standards(self.library, filters)

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
            print(
                f"{index}. {definition.code} - {definition.short_name}",
                file=self.stdout,
            )
            print(
                f"   {self._description_preview(definition.description)}",
                file=self.stdout,
            )
            metadata = " | ".join(
                value
                for value in (
                    definition.source,
                    definition.subject,
                    definition.course,
                    definition.domain,
                )
                if value
            )
            if metadata:
                print(f"   {metadata}", file=self.stdout)
            print("", file=self.stdout)

    def _collect_standard_subparts(
        self,
        parent: StandardDefinition,
    ) -> tuple[StandardDefinition, ...] | None:
        if not self._guided_confirm(
            (
                "Add lettered subparts for this standard?",
                "Type YES to add subparts.",
                "Anything else skips.",
            )
        ):
            return ()

        subparts: list[StandardDefinition] = []
        while True:
            letter = self._optional_guided_prompt(
                None,
                (
                    "Enter Subpart Letter.",
                    "Example: A",
                    "Leave blank to stop adding subparts.",
                ),
            )
            if letter is None:
                return tuple(subparts)
            letter = letter.strip().upper()
            if not letter.isalpha() or len(letter) != 1:
                print("Error: subpart letter must be one letter.", file=self.stderr)
                continue
            subpart_id = f"{parent.standard_id}.{letter}"
            if find_standard_definition(self.library, subpart_id) is not None or any(
                subpart.standard_id == subpart_id for subpart in subparts
            ):
                print(
                    f"Error: duplicate subpart standard_id: {subpart_id}",
                    file=self.stderr,
                )
                continue
            short_name = self._optional_guided_prompt(
                None,
                (
                    "Enter Subpart Short Name.",
                    "Example: Figures of Speech",
                    f"Leave blank to use Subpart {letter}.",
                ),
            )
            description = self._optional_guided_prompt(
                None,
                (
                    "Enter Subpart Description.",
                    "Example: Interpret figures of speech in context and "
                    "analyze their role in the text.",
                    "Leave blank to cancel this subpart.",
                ),
            )
            if description is None:
                print("Subpart cancelled.", file=self.stdout)
                continue
            try:
                subparts.append(
                    StandardDefinition(
                        standard_id=subpart_id,
                        code=f"{parent.code}.{letter}",
                        source=parent.source,
                        short_name=short_name or f"Subpart {letter}",
                        description=description,
                        subject=parent.subject,
                        course=parent.course,
                        grade_band=parent.grade_band,
                        domain=parent.domain,
                        category_path=parent.category_path,
                        tags=parent.tags,
                        active=parent.active,
                        available_modules=parent.available_modules,
                    )
                )
            except StandardsValidationError as error:
                print(f"Error: {error}", file=self.stderr)
        return tuple(subparts)

    def _print_standard_review(
        self,
        definition: StandardDefinition,
        subparts: tuple[StandardDefinition, ...],
    ) -> None:
        print("Review Standard", file=self.stdout)
        print("", file=self.stdout)
        print(f"Standard ID: {definition.standard_id}", file=self.stdout)
        print(f"Display Code: {definition.code}", file=self.stdout)
        print(f"Short Name: {definition.short_name}", file=self.stdout)
        print(f"Description: {definition.description}", file=self.stdout)
        print(f"Source: {definition.source}", file=self.stdout)
        print(f"Subject: {definition.subject or '-'}", file=self.stdout)
        print(f"Course: {definition.course or '-'}", file=self.stdout)
        print(f"Domain/Category: {definition.domain or '-'}", file=self.stdout)
        print(f"Active: {'yes' if definition.active else 'no'}", file=self.stdout)
        if subparts:
            print("", file=self.stdout)
            print("Subparts:", file=self.stdout)
            for subpart in subparts:
                print(
                    f"{subpart.code} - {subpart.short_name}: "
                    f"{subpart.description}",
                    file=self.stdout,
                )

    def _valid_teacher_standard_id(self, standard_id: str) -> bool:
        prefix, separator, code = standard_id.partition(":")
        return bool(separator and prefix.strip() and code.strip())

    def _description_preview(self, description: str) -> str:
        if len(description) <= _DESCRIPTION_PREVIEW_LENGTH:
            return description
        return f"{description[: _DESCRIPTION_PREVIEW_LENGTH - 3].rstrip()}..."

    def _standard_filter_args(self) -> argparse.Namespace | None:
        active_choice = self._guided_prompt(
            None,
            (
                "Status Filter.",
                "1 = active only, 2 = inactive only, 3 = all.",
                "Leave blank for active only.",
            ),
        )
        if active_choice is None:
            self._cancelled()
            return None
        active: bool | None
        if active_choice in ("", "1"):
            active = True
        elif active_choice == "2":
            active = False
        elif active_choice == "3":
            active = None
        else:
            print("Invalid status filter.", file=self.stdout)
            return None

        category = self._optional_guided_prompt(
            None,
            (
                "Category Filter.",
                "Enter a category path using / separators.",
                "Example: Reading/Literature",
                "Leave blank for any category.",
            ),
        )
        try:
            parse_category_path(category)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return None

        return argparse.Namespace(
            source=self._optional_guided_prompt(
                None,
                (
                    "Source Filter.",
                    "Example: NJSLS-ELA 2023",
                    "Leave blank for any source.",
                ),
            ),
            subject=self._optional_guided_prompt(
                None,
                (
                    "Subject Filter.",
                    "Example: English Language Arts",
                    "Leave blank for any subject.",
                ),
            ),
            course=self._optional_guided_prompt(
                None,
                ("Course Filter.", "Example: English 12", "Leave blank for any course."),
            ),
            domain=self._optional_guided_prompt(
                None,
                ("Domain Filter.", "Example: Reading", "Leave blank for any domain."),
            ),
            available_module=self._optional_guided_prompt(
                None,
                (
                    "Available Module Filter.",
                    "Example: core",
                    "Leave blank for any module.",
                ),
            ),
            category=category,
            active=active,
        )

    def _profile_filter_args(self) -> argparse.Namespace | None:
        return argparse.Namespace(
            source=self._optional_guided_prompt(
                None,
                (
                    "Profile Source Filter.",
                    "Example: NJSLS-ELA 2023",
                    "Leave blank for any source.",
                ),
            ),
            subject=self._optional_guided_prompt(
                None,
                (
                    "Profile Subject Filter.",
                    "Example: English Language Arts",
                    "Leave blank for any subject.",
                ),
            ),
            course=self._optional_guided_prompt(
                None,
                (
                    "Profile Course Filter.",
                    "Example: English 12",
                    "Leave blank for any course.",
                ),
            ),
        )

    def _profile_metadata(self) -> dict[str, str | None]:
        return {
            "title": self._optional_guided_prompt(
                None,
                (
                    "Enter Profile Title.",
                    "This is the teacher-facing name.",
                    "Example: English 12 Language Standards",
                    "Leave blank to use the profile ID as the title.",
                ),
            ),
            "description": self._optional_guided_prompt(
                None,
                (
                    "Enter Profile Description.",
                    "Briefly describe when this profile should be used.",
                    "Example: Language standards for English 12 writing and grammar assignments.",
                    "Leave blank for no description.",
                ),
            ),
            "subject": self._optional_guided_prompt(
                None,
                (
                    "Enter Subject.",
                    "Example: English Language Arts",
                    "Leave blank for no subject.",
                ),
            ),
            "course": self._optional_guided_prompt(
                None,
                ("Enter Course.", "Example: English 12", "Leave blank for no course."),
            ),
            "source": self._optional_guided_prompt(
                None,
                ("Enter Source.", "Example: NJSLS-ELA 2023", "Leave blank for no source."),
            ),
        }

    def _standard_ids_prompt(
        self,
        lines: tuple[str, ...] = (
            "Enter Standard IDs for this profile.",
            *STANDARD_ID_GUIDANCE,
            "Separate multiple IDs with commas.",
            STANDARD_ID_COPY_GUIDANCE,
            "Leave blank to create an empty profile.",
        ),
    ) -> tuple[str, ...] | None:
        raw = self._guided_prompt(
            None,
            lines,
        )
        if raw is None:
            self._cancelled()
            return None
        if not raw:
            return ()
        return tuple(
            normalize_standard_id_entry(part)
            for part in raw.split(",")
            if part.strip()
        )

    def _print_standard_membership_errors(self, standards: tuple[str, ...]) -> bool:
        duplicates = tuple(
            standard_id
            for index, standard_id in enumerate(standards)
            if standard_id in standards[:index]
        )
        unknown = tuple(
            standard_id
            for standard_id in standards
            if find_standard_definition(self.library, standard_id) is None
        )
        if not duplicates and not unknown:
            return True

        if unknown:
            print("Some standards were not found:", file=self.stdout)
            print("", file=self.stdout)
            for standard_id in unknown:
                print(standard_id, file=self.stdout)
            print("", file=self.stdout)
        if duplicates:
            print("Some standard IDs were entered more than once:", file=self.stdout)
            print("", file=self.stdout)
            for standard_id in duplicates:
                print(standard_id, file=self.stdout)
            print("", file=self.stdout)

        print(STANDARD_ID_GUIDANCE[0], file=self.stdout)
        print(STANDARD_ID_GUIDANCE[1], file=self.stdout)
        print("", file=self.stdout)
        print(
            "Enter Standard IDs again, or leave blank to create an empty profile.",
            file=self.stdout,
        )
        return False

    def _prompt_existing_profile(
        self,
        title: str | None = None,
        lines: tuple[str, ...] = (
            "Enter Durable Profile ID.",
            "Example: english_12_language_standards",
            "Leave blank to cancel.",
        ),
        *,
        clear: bool = False,
    ) -> StandardsProfile | None:
        profile_id = self._required_guided_prompt(title, lines, clear=clear)
        if profile_id is None:
            return None
        profile = find_standards_profile(self.library, profile_id)
        if profile is None:
            print(
                f"Error: standards profile not found: {profile_id}",
                file=self.stderr,
            )
            return None
        return profile

    def _prompt_existing_standard(
        self,
        title: str | None = None,
        lines: tuple[str, ...] = (
            "Enter Durable Standard ID.",
            "Use the permanent standard_id, not just the display code.",
            "Example: njsls-ela:RL.CR.11-12.1",
            "Leave blank to cancel.",
        ),
        *,
        clear: bool = False,
    ) -> StandardDefinition | None:
        standard_id = self._required_guided_prompt(title, lines, clear=clear)
        if standard_id is None:
            return None
        standard_id = normalize_standard_id_entry(standard_id)
        definition = find_standard_definition(self.library, standard_id)
        if definition is None:
            print(f"Error: standard not found: {standard_id}", file=self.stderr)
            return None
        return definition

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

    def _run_submenu(
        self,
        title: str,
        lines: tuple[str, ...],
        back_choice: str,
        actions: dict[str, Callable[[], None]],
        *,
        guidance: tuple[str, ...] = (),
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
            action()
            self._pause()

    def _print_menu(
        self,
        title: str,
        lines: tuple[str, ...],
        *,
        guidance: tuple[str, ...] = (),
    ) -> None:
        screen.clear_screen(self.stdout)
        print(title, file=self.stdout)
        print("", file=self.stdout)
        for line in guidance:
            print(line, file=self.stdout)
        if guidance:
            print("", file=self.stdout)
        for line in lines:
            print(line, file=self.stdout)

    def _workflow_screen(self, title: str, lines: tuple[str, ...] = ()) -> None:
        screen.clear_screen(self.stdout)
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
            screen.clear_screen(self.stdout)
        if title is not None:
            print(title, file=self.stdout)
            print("", file=self.stdout)
        for line in lines:
            print(line, file=self.stdout)
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

    def _guided_confirm(self, lines: tuple[str, ...]) -> bool:
        value = self._guided_prompt(None, lines)
        return value == "YES"

    def _print_library_summary(self, library: StandardsLibrary) -> None:
        print(
            f"Summary: {len(library.standards)} standards, "
            f"{len(library.profiles)} profiles.",
            file=self.stdout,
        )

    def _print_profile_summary(self, action: str, profile: StandardsProfile) -> None:
        print(action, file=self.stdout)
        print(f"profile_id: {profile.profile_id}", file=self.stdout)
        print(f"title: {profile.title or '-'}", file=self.stdout)
        print(f"description: {profile.description or '-'}", file=self.stdout)
        print(f"subject: {profile.subject or '-'}", file=self.stdout)
        print(f"course: {profile.course or '-'}", file=self.stdout)
        print(f"source: {profile.source or '-'}", file=self.stdout)
        print(f"standards: {len(profile.standards)}", file=self.stdout)
        for standard_id in profile.standards:
            definition = find_standard_definition(self.library, standard_id)
            if definition is None:
                print(f"  {standard_id} | unresolved | unresolved", file=self.stdout)
            else:
                print(
                    f"  {definition.standard_id} | {definition.code} | "
                    f"{definition.short_name}",
                    file=self.stdout,
                )

    def _print_standard_profile_review(self, profile: StandardsProfile) -> None:
        print("Review Standard Profile", file=self.stdout)
        print("", file=self.stdout)
        print(f"Profile ID: {profile.profile_id}", file=self.stdout)
        print(f"Title: {profile.title or '-'}", file=self.stdout)
        print(f"Description: {profile.description or '-'}", file=self.stdout)
        print(f"Subject: {profile.subject or '-'}", file=self.stdout)
        print(f"Course: {profile.course or '-'}", file=self.stdout)
        print(f"Source: {profile.source or '-'}", file=self.stdout)
        print(f"Standards: {len(profile.standards)}", file=self.stdout)
        if profile.standards:
            print("", file=self.stdout)
            print("Selected Standards:", file=self.stdout)
            for index, standard_id in enumerate(profile.standards, start=1):
                definition = find_standard_definition(self.library, standard_id)
                if definition is None:
                    print(f"{index}. {standard_id} - unresolved", file=self.stdout)
                    continue
                print(
                    f"{index}. {definition.code} - {definition.short_name}",
                    file=self.stdout,
                )
                print(
                    f"   {self._description_preview(definition.description)}",
                    file=self.stdout,
                )

    def _prompt(self, prompt: str) -> str | None:
        print(prompt, end="", file=self.stdout, flush=True)
        line = self.stdin.readline()
        if line == "":
            print("", file=self.stdout)
            return None
        return line.rstrip("\r\n").strip()

    def _cancelled(self) -> None:
        print("Cancelled.", file=self.stdout)

    def _pause(self) -> None:
        print("", file=self.stdout)
        print("Press Enter to continue...", end="", file=self.stdout)
        line = self.stdin.readline()
        if line == "":
            print("", file=self.stdout)
            return

    def _has_standards(self) -> bool:
        return bool(self.library.standards)

    def _has_profiles(self) -> bool:
        return bool(self.library.profiles)


def normalize_standard_id_entry(value: str) -> str:
    """Normalize common user-entered punctuation in standard IDs."""
    return value.strip().translate(DASH_TRANSLATION)
