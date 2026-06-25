"""Selectable filter helpers for the interactive standards menu."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.context import StandardFilters
from pds_core.cli_support.menu_prompts import MenuPromptMixin
from pds_core.cli_support.standards_read import matching_standards
from pds_core.standards import StandardDefinition, StandardsLibrary

_INVALID_SELECTION = object()
_SKIP_REMAINING_FILTERS = object()


class MenuFilterMixin(MenuPromptMixin):
    """Mixin methods assume menu runner attributes for IO and library state."""

    args: argparse.Namespace
    library: StandardsLibrary
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def _filtered_available_standards(self) -> tuple[StandardDefinition, ...]:
        subject = self._select_existing_value(
            "Filter Standards for Profile Selection",
            self._standard_values("subject", active=None),
            blank_label="any subject",
            workflow_title="Create Standard Profile",
            allow_skip_remaining=True,
        )
        if subject is _INVALID_SELECTION:
            return ()
        if subject is _SKIP_REMAINING_FILTERS:
            return matching_standards(
                self.library,
                StandardFilters(
                    source=None,
                    subject=None,
                    course=None,
                    domain=None,
                    category_path_prefix=(),
                    available_module=None,
                    active=None,
                ),
            )
        course = self._select_existing_value(
            "Course Filter",
            self._standard_values("course", active=None),
            blank_label="any course",
            workflow_title="Create Standard Profile",
            allow_skip_remaining=True,
        )
        if course is _INVALID_SELECTION:
            return ()
        if course is _SKIP_REMAINING_FILTERS:
            course = None
            domain = None
        else:
            domain = self._select_existing_value(
                "Domain Filter",
                self._standard_values("domain", active=None),
                blank_label="any domain",
                workflow_title="Create Standard Profile",
                allow_skip_remaining=True,
            )
            if domain is _INVALID_SELECTION:
                return ()
            if domain is _SKIP_REMAINING_FILTERS:
                domain = None
        filters = StandardFilters(
            source=None,
            subject=self._selected_or_none(subject),
            course=self._selected_or_none(course),
            domain=self._selected_or_none(domain),
            category_path_prefix=(),
            available_module=None,
            active=None,
        )
        return matching_standards(self.library, filters)

    def _standard_filter_args(self) -> argparse.Namespace | None:
        active_choice = self._guided_prompt(
            "Browse Standards",
            (
                "Status Filter",
                "",
                "1. Active only",
                "2. Inactive only",
                "3. All standards",
                "",
                "Leave blank for Active only.",
            ),
            clear=True,
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

        category = self._select_existing_value(
            "Category Filter",
            self._standard_category_values(active=active),
            blank_label="any category",
            workflow_title="Browse Standards",
            allow_skip_remaining=True,
        )
        if category is _INVALID_SELECTION:
            return None
        if category is _SKIP_REMAINING_FILTERS:
            return self._standard_filter_namespace(active=active)

        source = self._select_existing_value(
            "Source Filter",
            self._standard_values("source", active=active),
            blank_label="any source",
            workflow_title="Browse Standards",
            allow_skip_remaining=True,
        )
        if source is _INVALID_SELECTION:
            return None
        if source is _SKIP_REMAINING_FILTERS:
            return self._standard_filter_namespace(active=active, category=category)
        subject = self._select_existing_value(
            "Subject Filter",
            self._standard_values("subject", active=active),
            blank_label="any subject",
            workflow_title="Browse Standards",
            allow_skip_remaining=True,
        )
        if subject is _INVALID_SELECTION:
            return None
        if subject is _SKIP_REMAINING_FILTERS:
            return self._standard_filter_namespace(
                active=active,
                category=category,
                source=source,
            )
        course = self._select_existing_value(
            "Course Filter",
            self._standard_values("course", active=active),
            blank_label="any course",
            workflow_title="Browse Standards",
            allow_skip_remaining=True,
        )
        if course is _INVALID_SELECTION:
            return None
        if course is _SKIP_REMAINING_FILTERS:
            return self._standard_filter_namespace(
                active=active,
                category=category,
                source=source,
                subject=subject,
            )
        domain = self._select_existing_value(
            "Domain Filter",
            self._standard_values("domain", active=active),
            blank_label="any domain",
            workflow_title="Browse Standards",
            allow_skip_remaining=True,
        )
        if domain is _INVALID_SELECTION:
            return None
        if domain is _SKIP_REMAINING_FILTERS:
            return self._standard_filter_namespace(
                active=active,
                category=category,
                source=source,
                subject=subject,
                course=course,
            )
        available_module = self._select_existing_value(
            "Available Module Filter",
            self._standard_module_values(active=active),
            blank_label="any module",
            workflow_title="Browse Standards",
            allow_skip_remaining=True,
        )
        if available_module is _INVALID_SELECTION:
            return None
        if available_module is _SKIP_REMAINING_FILTERS:
            available_module = None

        return self._standard_filter_namespace(
            active=active,
            category=category,
            source=source,
            subject=subject,
            course=course,
            domain=domain,
            available_module=available_module,
        )

    def _profile_filter_args(self) -> argparse.Namespace | None:
        source = self._select_existing_value(
            "Profile Source Filter",
            self._profile_values("source"),
            blank_label="any source",
            workflow_title="Browse Profiles",
            allow_skip_remaining=True,
        )
        if source is _INVALID_SELECTION:
            return None
        if source is _SKIP_REMAINING_FILTERS:
            return argparse.Namespace(source=None, subject=None, course=None)
        subject = self._select_existing_value(
            "Profile Subject Filter",
            self._profile_values("subject"),
            blank_label="any subject",
            workflow_title="Browse Profiles",
            allow_skip_remaining=True,
        )
        if subject is _INVALID_SELECTION:
            return None
        if subject is _SKIP_REMAINING_FILTERS:
            return argparse.Namespace(
                source=self._selected_or_none(source),
                subject=None,
                course=None,
            )
        course = self._select_existing_value(
            "Profile Course Filter",
            self._profile_values("course"),
            blank_label="any course",
            workflow_title="Browse Profiles",
            allow_skip_remaining=True,
        )
        if course is _INVALID_SELECTION:
            return None
        if course is _SKIP_REMAINING_FILTERS:
            course = None
        return argparse.Namespace(
            source=self._selected_or_none(source),
            subject=self._selected_or_none(subject),
            course=self._selected_or_none(course),
        )

    def _select_existing_value(
        self,
        title: str,
        values: tuple[str, ...],
        *,
        blank_label: str,
        workflow_title: str | None = None,
        allow_skip_remaining: bool = False,
    ) -> str | object | None:
        if not values:
            return None
        if workflow_title is not None:
            self._workflow_screen(workflow_title, (title,))
        else:
            print(title, file=self.stdout)
            print("", file=self.stdout)
        if allow_skip_remaining:
            print("0. Skip remaining filters", file=self.stdout)
        for index, value in enumerate(values, start=1):
            print(f"{index}. {value}", file=self.stdout)
        print("", file=self.stdout)
        print(f"Leave blank for {blank_label}.", file=self.stdout)
        raw = self._prompt("> ")
        if raw is None or raw == "":
            return None
        if not raw.isdecimal():
            print(
                "Invalid selection. Enter a number from the list, or leave blank.",
                file=self.stdout,
            )
            return _INVALID_SELECTION
        index = int(raw)
        if allow_skip_remaining and index == 0:
            return _SKIP_REMAINING_FILTERS
        if index < 1 or index > len(values):
            print(
                "Invalid selection. Enter a number from the list, or leave blank.",
                file=self.stdout,
            )
            return _INVALID_SELECTION
        return values[index - 1]

    def _standard_filter_namespace(
        self,
        *,
        active: bool | None,
        category: str | object | None = None,
        source: str | object | None = None,
        subject: str | object | None = None,
        course: str | object | None = None,
        domain: str | object | None = None,
        available_module: str | object | None = None,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            source=self._selected_or_none(source),
            subject=self._selected_or_none(subject),
            course=self._selected_or_none(course),
            domain=self._selected_or_none(domain),
            available_module=self._selected_or_none(available_module),
            category=self._selected_or_none(category),
            active=active,
        )

    def _selected_or_none(self, value: str | object | None) -> str | None:
        return value if isinstance(value, str) else None

    def _standard_values(self, field_name: str, *, active: bool | None) -> tuple[str, ...]:
        values = {
            value
            for definition in self.library.standards
            if (active is None or definition.active is active)
            for value in (getattr(definition, field_name),)
            if isinstance(value, str) and value
        }
        return tuple(sorted(values))

    def _standard_category_values(self, *, active: bool | None) -> tuple[str, ...]:
        values = {
            "/".join(definition.category_path)
            for definition in self.library.standards
            if (active is None or definition.active is active) and definition.category_path
        }
        return tuple(sorted(values))

    def _standard_module_values(self, *, active: bool | None) -> tuple[str, ...]:
        values = {
            module
            for definition in self.library.standards
            if active is None or definition.active is active
            for module in definition.available_modules
        }
        return tuple(sorted(values))

    def _profile_values(self, field_name: str) -> tuple[str, ...]:
        values = {
            value
            for profile in self.library.profiles
            for value in (getattr(profile, field_name),)
            if isinstance(value, str) and value
        }
        return tuple(sorted(values))
