"""Interactive standards management menu for teacher-facing CLI workflows."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace as dataclass_replace
from pathlib import Path
from collections.abc import Callable
from typing import TextIO

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
            "1": self.browse_standards,
            "2": self.search_standards,
            "3": self.view_standard,
            "4": self.browse_profiles,
            "5": self.view_profile,
            "6": self.create_profile,
            "7": self.edit_profile_standards,
            "8": self.import_standards_data,
            "9": self.export_standards_data,
            "10": self.validate_standards_library,
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
                    "6. Create profile",
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
            action()

    def browse_standards(self) -> None:
        filters = self._standard_filter_args()
        if filters is None:
            return
        handle_standards_list(filters, self.library, self.stdout, self.stderr)

    def search_standards(self) -> None:
        query = self._required_prompt("Enter search text: ")
        if query is None:
            return
        filters = self._standard_filter_args()
        if filters is None:
            return
        filters.query = query
        handle_standards_search(filters, self.library, self.stdout, self.stderr)

    def view_standard(self) -> None:
        standard_id = self._required_prompt(
            "Enter durable standard_id, not display code: "
        )
        if standard_id is None:
            return
        command_args = argparse.Namespace(standard_id=standard_id)
        handle_standards_show(command_args, self.library, self.stdout, self.stderr)

    def browse_profiles(self) -> None:
        filters = self._profile_filter_args()
        if filters is None:
            return
        handle_standards_profiles(filters, self.library, self.stdout, self.stderr)

    def view_profile(self) -> None:
        profile_id = self._required_prompt("Enter durable profile_id: ")
        if profile_id is None:
            return
        command_args = argparse.Namespace(profile_id=profile_id)
        handle_profile_show(command_args, self.library, self.stdout, self.stderr)

    def create_profile(self) -> None:
        profile_id = self._required_prompt("Enter durable profile_id: ")
        if profile_id is None:
            return
        metadata = self._profile_metadata()
        standards = self._standard_ids_prompt()
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

        self._print_profile_summary("Create profile", profile)
        if not self._confirm(f"Create profile {profile.profile_id}? Type YES to continue: "):
            self._cancelled()
            return
        if self._write_library(updated_library):
            self.library = updated_library
            print(f"Created standards profile {profile.profile_id}.", file=self.stdout)

    def edit_profile_standards(self) -> None:
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

    def add_standard_to_profile(self) -> None:
        profile = self._prompt_existing_profile()
        if profile is None:
            return
        definition = self._prompt_existing_standard()
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
            f"Added standard {definition.standard_id} to profile {profile.profile_id}.",
        )

    def remove_standard_from_profile(self) -> None:
        print(
            "This removes the standard from the profile only. It does not delete "
            "the standard.",
            file=self.stdout,
        )
        profile = self._prompt_existing_profile()
        if profile is None:
            return
        standard_id = self._required_prompt(
            "Enter durable standard_id to remove from profile membership: "
        )
        if standard_id is None:
            return
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
        profile = self._prompt_existing_profile()
        if profile is None:
            return
        standards = self._standard_ids_prompt()
        if standards is None:
            return
        try:
            updated_profile = dataclass_replace(profile, standards=standards)
            updated_library = replace_standards_profile(self.library, updated_profile)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return

        self._print_profile_summary("Replace profile standards", updated_profile)
        if not self._confirm(
            f"Replace standards for profile {profile.profile_id}? "
            "Type YES to continue: "
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
        )

    def import_full_library(self) -> None:
        source_path = self._required_prompt("Enter source JSON path: ")
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
        if not self._confirm(
            "Import full standards library? Type YES to continue: "
        ):
            self._cancelled()
            return

        target_path = standards_library_path(self.args.workspace_root)
        overwrite = False
        if target_path.exists():
            if not self._confirm(
                "Workspace standards library already exists. "
                "Overwrite it? Type YES to continue: "
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
        source_path = self._required_prompt("Enter source JSON path: ")
        if source_path is None:
            return
        mode = self._prompt(
            "Import mode (1 add new profile, 2 replace existing profile, 3 cancel): "
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
        prompt = (
            f"Add profile {profile.profile_id}? Type YES to continue: "
            if add
            else f"Replace profile {profile.profile_id}? Type YES to continue: "
        )
        if not self._confirm(prompt):
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
        )

    def export_full_library(self) -> None:
        target_path = self._required_prompt("Enter target JSON path: ")
        if target_path is None:
            return
        overwrite = self._confirm_overwrite(target_path)
        if overwrite is None:
            return
        self._print_library_summary(self.library)
        if not self._confirm("Export full standards library? Type YES to continue: "):
            self._cancelled()
            return
        command_args = self._command_args(path=target_path, overwrite=overwrite)
        handle_standards_export(command_args, self.library, self.stdout, self.stderr)

    def export_profile(self) -> None:
        profile = self._prompt_existing_profile()
        if profile is None:
            return
        target_path = self._required_prompt("Enter target JSON path: ")
        if target_path is None:
            return
        overwrite = self._confirm_overwrite(target_path)
        if overwrite is None:
            return
        self._print_profile_summary("Export profile", profile)
        if not self._confirm(
            f"Export profile {profile.profile_id}? Type YES to continue: "
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
        if not self._confirm(f"{prompt_text} Type YES to continue: "):
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
        active_choice = self._prompt(
            "Status filter (1 active only, 2 inactive only, 3 all, blank active): "
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

        category = self._optional_prompt(
            "Optional category path using '/' separators: "
        )
        try:
            parse_category_path(category)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return None

        return argparse.Namespace(
            source=self._optional_prompt("Optional source filter: "),
            subject=self._optional_prompt("Optional subject filter: "),
            course=self._optional_prompt("Optional course filter: "),
            domain=self._optional_prompt("Optional domain filter: "),
            available_module=self._optional_prompt(
                "Optional available module filter: "
            ),
            category=category,
            active=active,
        )

    def _profile_filter_args(self) -> argparse.Namespace | None:
        return argparse.Namespace(
            source=self._optional_prompt("Optional source filter: "),
            subject=self._optional_prompt("Optional subject filter: "),
            course=self._optional_prompt("Optional course filter: "),
        )

    def _profile_metadata(self) -> dict[str, str | None]:
        return {
            "title": self._optional_prompt("Optional title: "),
            "description": self._optional_prompt("Optional description: "),
            "subject": self._optional_prompt("Optional subject: "),
            "course": self._optional_prompt("Optional course: "),
            "source": self._optional_prompt("Optional source: "),
        }

    def _standard_ids_prompt(self) -> tuple[str, ...] | None:
        raw = self._prompt(
            "Enter durable standard_id values separated by commas (blank for none): "
        )
        if raw is None:
            self._cancelled()
            return None
        if not raw:
            return ()
        return tuple(part.strip() for part in raw.split(",") if part.strip())

    def _prompt_existing_profile(self) -> StandardsProfile | None:
        profile_id = self._required_prompt("Enter durable profile_id: ")
        if profile_id is None:
            return None
        profile = find_standards_profile(self.library, profile_id)
        if profile is None:
            print(f"Error: standards profile not found: {profile_id}", file=self.stderr)
            return None
        return profile

    def _prompt_existing_standard(self) -> StandardDefinition | None:
        standard_id = self._required_prompt(
            "Enter durable standard_id, not display code: "
        )
        if standard_id is None:
            return None
        definition = find_standard_definition(self.library, standard_id)
        if definition is None:
            print(f"Error: standard not found: {standard_id}", file=self.stderr)
            return None
        return definition

    def _confirm_overwrite(self, target_path: str) -> bool | None:
        path = Path(target_path)
        if not path.exists():
            return False
        if self._confirm(
            f"Target file already exists: {path}. Overwrite? Type YES to continue: "
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
    ) -> None:
        while True:
            self._print_menu(title, lines)
            choice = self._prompt("Choose an option: ")
            if choice is None or choice == back_choice:
                print("Back.", file=self.stdout)
                return
            action = actions.get(choice)
            if action is None:
                print("Invalid menu choice. Please try again.", file=self.stdout)
                continue
            action()

    def _print_menu(self, title: str, lines: tuple[str, ...]) -> None:
        print("", file=self.stdout)
        print(title, file=self.stdout)
        print("", file=self.stdout)
        for line in lines:
            print(line, file=self.stdout)

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

    def _prompt(self, prompt: str) -> str | None:
        print(prompt, end="", file=self.stdout)
        line = self.stdin.readline()
        if line == "":
            print("", file=self.stdout)
            return None
        return line.rstrip("\r\n").strip()

    def _required_prompt(self, prompt: str) -> str | None:
        value = self._prompt(prompt)
        if value is None or value == "":
            self._cancelled()
            return None
        return value

    def _optional_prompt(self, prompt: str) -> str | None:
        value = self._prompt(prompt)
        if value is None or value == "":
            return None
        return value

    def _confirm(self, prompt: str) -> bool:
        value = self._prompt(prompt)
        return value == "YES"

    def _cancelled(self) -> None:
        print("Cancelled.", file=self.stdout)
