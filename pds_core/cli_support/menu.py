"""Interactive standards management menu for teacher-facing CLI workflows."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace as dataclass_replace
from pathlib import Path
from collections.abc import Callable
from typing import TextIO

from pds_core.cli_support import screen
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
    parse_category_path,
)
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
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
            "4": (self.browse_profiles, True),
            "5": (self.view_profile, True),
            "6": (self.create_profile, True),
            "7": (self.edit_profile_standards, False),
            "8": (self.import_standards_data, False),
            "9": (self.export_standards_data, False),
            "10": (self.validate_standards_library, True),
        }
        while True:
            self._print_menu(
                "Standards Management",
                (
                    "1. Browse standards",
                    "2. Search standards",
                    "3. View standard",
                    "4. Browse profiles",
                    "5. View profile",
                    "6. Create Standard Profile",
                    "7. Edit profile standards",
                    "8. Import standards data",
                    "9. Export standards data",
                    "10. Validate standards library",
                    "11. Back",
                ),
            )
            choice = self._prompt("Choose an option: ")
            if choice is None or choice == "11":
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
        while True:
            standards = self._standard_ids_prompt()
            if standards is None:
                return
            if not self._print_standard_membership_errors(standards):
                continue

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
            break

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
        definition = self._prompt_existing_standard(
            None,
            (
                "Enter Durable Standard ID to Add.",
                "The standard must already exist in the standards library.",
                *STANDARD_ID_GUIDANCE,
                STANDARD_ID_COPY_GUIDANCE,
                "Leave blank to cancel.",
            ),
        )
        if definition is None:
            return
        if definition.standard_id in profile.standards:
            print(
                "Error: profile already contains standard "
                f"{definition.standard_id}: {profile.profile_id}",
                file=self.stderr,
            )
            return

        updated_profile = dataclass_replace(
            profile,
            standards=profile.standards + (definition.standard_id,),
        )
        self._replace_profile_membership(
            updated_profile,
            f"Add standard {definition.standard_id} to profile {profile.profile_id}?",
            f"Added standard {definition.standard_id} to profile "
            f"{profile.profile_id}.",
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
        standard_id = self._required_guided_prompt(
            None,
            (
                "Enter Durable Standard ID to Remove.",
                "The standard must already belong to this profile.",
                *STANDARD_ID_GUIDANCE,
                STANDARD_ID_COPY_GUIDANCE,
                "Leave blank to cancel.",
            ),
        )
        if standard_id is None:
            return
        standard_id = normalize_standard_id_entry(standard_id)
        if standard_id not in profile.standards:
            print(
                "Error: profile does not contain standard "
                f"{standard_id}: {profile.profile_id}",
                file=self.stderr,
            )
            return

        updated_profile = dataclass_replace(
            profile,
            standards=tuple(
                existing for existing in profile.standards if existing != standard_id
            ),
        )
        self._replace_profile_membership(
            updated_profile,
            f"Remove standard {standard_id} from profile {profile.profile_id}?",
            f"Removed standard {standard_id} from profile {profile.profile_id}.",
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
        standards = self._standard_ids_prompt(
            (
                "Enter New Standard IDs.",
                *STANDARD_ID_GUIDANCE,
                "Separate multiple IDs with commas.",
                STANDARD_ID_COPY_GUIDANCE,
                "Leave blank for no standards.",
            )
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
