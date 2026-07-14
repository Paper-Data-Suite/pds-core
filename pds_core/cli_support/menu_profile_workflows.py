"""Profile workflows for the interactive standards menu."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.formatting import standard_metadata
from pds_core.cli_support.menu_selection import MenuSelectionMixin
from pds_core.cli_support.menu_standard_workflows import StandardsWorkflowMixin
from pds_core.cli_support.profiles import handle_profile_show, standards_profile_from_args
from pds_core.cli_support.standards_read import handle_standards_profiles
from pds_core.standards import (
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    add_standards_to_profile,
    add_standards_profile,
    find_standard_definition,
    find_standards_profile,
    remove_standards_from_profile,
    set_profile_standards,
)


class ProfileWorkflowMixin(StandardsWorkflowMixin, MenuSelectionMixin):
    """Profile workflows assume menu runner attributes and shared mixin helpers."""

    args: argparse.Namespace
    library: StandardsLibrary
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def browse_profiles(self) -> None:
        if not self._has_profiles():
            self._clear_screen()
            print("No standards profiles found.", file=self.stdout)
            return
        self._workflow_screen("Browse Profiles")
        filters = self._profile_filter_args()
        if filters is None:
            return
        self._workflow_screen("Browse Profiles Results")
        handle_standards_profiles(filters, self.library, self.stdout, self.stderr)

    def view_profile(self) -> None:
        if not self._has_profiles():
            self._clear_screen()
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
            self._clear_screen()
            print("No standards profiles found.", file=self.stdout)
            self._pause("Profiles menu")
            return
        if not self._has_standards():
            self._clear_screen()
            print("No standards exist yet.", file=self.stdout)
            print(
                "Create standards before editing profile membership.",
                file=self.stdout,
            )
            self._pause("Profiles menu")
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
            self._pause("Edit Profile Standards menu")

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

        try:
            updated_library = add_standards_to_profile(
                self.library, profile.profile_id, standards
            )
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return
        self._replace_profile_membership(
            updated_library,
            profile.profile_id,
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

        try:
            updated_library = remove_standards_from_profile(
                self.library, profile.profile_id, standards
            )
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return
        self._replace_profile_membership(
            updated_library,
            profile.profile_id,
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
            updated_library = set_profile_standards(
                self.library, profile.profile_id, standards
            )
        except StandardsValidationError as error:
            print(f"Error: {error}", file=self.stderr)
            return
        updated_profile = find_standards_profile(updated_library, profile.profile_id)
        assert updated_profile is not None

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

    def _replace_profile_membership(
        self,
        updated_library: StandardsLibrary,
        profile_id: str,
        prompt_text: str,
        success_message: str,
    ) -> None:
        updated_profile = find_standards_profile(updated_library, profile_id)
        assert updated_profile is not None
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
                print(f"   ID: {definition.standard_id}", file=self.stdout)
                print(f"   {standard_metadata(definition)}", file=self.stdout)
