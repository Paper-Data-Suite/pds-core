"""Standards definition workflows for the interactive standards menu."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.formatting import description_preview
from pds_core.cli_support.menu_filters import MenuFilterMixin
from pds_core.cli_support.standards_read import (
    handle_standards_list,
    handle_standards_search,
    handle_standards_show,
)
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsValidationError,
    add_standard_definitions,
    find_standard_definition,
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


class StandardsWorkflowMixin(MenuFilterMixin):
    """Standards workflows assume menu runner attributes and prompt helpers."""

    args: argparse.Namespace
    library: StandardsLibrary
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def browse_standards(self) -> None:
        if not self._has_standards():
            self._clear_screen()
            print("No standards found.", file=self.stdout)
            return
        self._workflow_screen("Browse Standards")
        filters = self._standard_filter_args()
        if filters is None:
            return
        self._workflow_screen("Browse Standards Results")
        handle_standards_list(filters, self.library, self.stdout, self.stderr)

    def search_standards(self) -> None:
        if not self._has_standards():
            self._clear_screen()
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
        self._workflow_screen(f'Search Standards Results for "{query}"')
        filters = argparse.Namespace(
            query=query,
            source=None,
            subject=None,
            course=None,
            domain=None,
            available_module=None,
            category=None,
            active=None,
        )
        handle_standards_search(filters, self.library, self.stdout, self.stderr)

    def view_standard(self) -> None:
        if not self._has_standards():
            self._clear_screen()
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
            "Add Standard",
            (
                "Enter Display Code.",
                "Example: L.VI.11-12.4",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if code is None:
            return
        short_name = self._optional_guided_prompt(
            "Add Standard",
            (
                "Enter Short Name.",
                "Example: Figurative Language and Word Relationships",
                "Leave blank to use the display code.",
            ),
            clear=True,
        )
        description = self._required_guided_prompt(
            "Add Standard",
            (
                "Enter Standard Description.",
                "Paste or type the full standard statement.",
                "Example: Demonstrate understanding of figurative language, "
                "word relationships, and nuances in word meanings.",
                "Leave blank to cancel.",
            ),
            clear=True,
        )
        if description is None:
            return
        source = self._optional_guided_prompt(
            "Add Standard",
            (
                "Enter Source.",
                "Example: NJSLS-ELA 2023",
                "Leave blank to use Unspecified.",
            ),
            clear=True,
        )
        subject = self._optional_guided_prompt(
            "Add Standard",
            (
                "Enter Subject.",
                "Example: English Language Arts",
                "Leave blank for no subject.",
            ),
            clear=True,
        )
        course = self._optional_guided_prompt(
            "Add Standard",
            ("Enter Course.", "Example: English 12", "Leave blank for no course."),
            clear=True,
        )
        domain = self._optional_guided_prompt(
            "Add Standard",
            (
                "Enter Domain or Category.",
                "Example: Language",
                "Leave blank for no domain/category.",
            ),
            clear=True,
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
            updated_library = add_standard_definitions(
                self.library, (definition, *subparts)
            )
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

    def _collect_standard_subparts(
        self,
        parent: StandardDefinition,
    ) -> tuple[StandardDefinition, ...] | None:
        if not self._guided_confirm(
            (
                "Add lettered subparts for this standard?",
                "Type YES to add subparts.",
                "Anything else skips.",
            ),
            title="Add Standard",
            clear=True,
        ):
            return ()

        subparts: list[StandardDefinition] = []
        while True:
            letter = self._optional_guided_prompt(
                "Add Standard Subparts",
                (
                    f"Parent: {parent.code}",
                    "",
                    "Enter Subpart Letter.",
                    "Example: A",
                    "Leave blank to stop adding subparts.",
                ),
                clear=True,
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
                "Add Standard Subparts",
                (
                    f"Parent: {parent.code}",
                    "",
                    "Enter Subpart Short Name.",
                    "Example: Figures of Speech",
                    f"Leave blank to use Subpart {letter}.",
                ),
                clear=True,
            )
            description = self._optional_guided_prompt(
                "Add Standard Subparts",
                (
                    f"Parent: {parent.code}",
                    "",
                    "Enter Subpart Description.",
                    "Example: Interpret figures of speech in context and "
                    "analyze their role in the text.",
                    "Leave blank to cancel this subpart.",
                ),
                clear=True,
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
        self._clear_screen()
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
        return description_preview(description, _DESCRIPTION_PREVIEW_LENGTH)


def normalize_standard_id_entry(value: str) -> str:
    """Normalize common user-entered punctuation in standard IDs."""
    return value.strip().translate(DASH_TRANSLATION)
