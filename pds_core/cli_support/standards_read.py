"""Read-only standards CLI command handlers and filter helpers."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.cli_support.context import StandardFilters
from pds_core.cli_support.formatting import (
    compact_profile_row,
    compact_standard_row,
    display,
    format_tuple,
    print_values,
)
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsValidationError,
    filter_standard_definitions,
    filter_standards_profiles,
    find_standard_definition,
)


_CATEGORY_SEPARATOR = "/"


def add_standard_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", help="Filter standards by exact source.")
    parser.add_argument("--subject", help="Filter standards by exact subject.")
    parser.add_argument("--course", help="Filter standards by exact course.")
    parser.add_argument("--domain", help="Filter standards by exact domain.")
    parser.add_argument(
        "--category",
        help=(
            "Filter by category path prefix using '/' as the separator, "
            "for example 'English Language Arts/Reading Literature'."
        ),
    )
    parser.add_argument(
        "--available-module",
        help="Filter standards available to the named module.",
    )
    active_group = parser.add_mutually_exclusive_group()
    active_group.add_argument(
        "--active",
        action="store_const",
        const=True,
        dest="active",
        help="Only include active standards (default).",
    )
    active_group.add_argument(
        "--inactive",
        action="store_const",
        const=False,
        dest="active",
        help="Only include inactive standards.",
    )
    active_group.add_argument(
        "--all",
        action="store_const",
        const=None,
        dest="active",
        help="Include active and inactive standards.",
    )
    parser.set_defaults(active=True)


def add_profile_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", help="Filter profiles by exact source.")
    parser.add_argument("--subject", help="Filter profiles by exact subject.")
    parser.add_argument("--course", help="Filter profiles by exact course.")


def standard_filters(args: argparse.Namespace) -> StandardFilters:
    return StandardFilters(
        source=args.source,
        subject=args.subject,
        course=args.course,
        domain=args.domain,
        category_path_prefix=parse_category_path(args.category),
        available_module=args.available_module,
        active=args.active,
    )


def parse_category_path(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    parts = tuple(part.strip() for part in value.split(_CATEGORY_SEPARATOR))
    if not all(parts):
        raise StandardsValidationError(
            "category must contain non-empty path parts separated by '/'."
        )
    return parts


def matching_standards(
    library: StandardsLibrary,
    filters: StandardFilters,
) -> tuple[StandardDefinition, ...]:
    definitions = filter_standard_definitions(
        library,
        subject=filters.subject,
        source=filters.source,
        domain=filters.domain,
        active=filters.active,
        available_module=filters.available_module,
        category_path_prefix=filters.category_path_prefix,
    )
    if filters.course is not None:
        definitions = tuple(
            definition
            for definition in definitions
            if definition.course == filters.course
        )
    return tuple(sorted(definitions, key=lambda definition: definition.standard_id))


def handle_standards_list(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    definitions = matching_standards(library, standard_filters(args))
    if not definitions:
        print("No standards found.", file=stdout)
        return 0
    for definition in definitions:
        print(compact_standard_row(definition), file=stdout)
    return 0


def handle_standards_show(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    definition = find_standard_definition(library, args.standard_id)
    if definition is None:
        print(f"Standard not found: {args.standard_id}", file=stderr)
        return 1

    fields = (
        ("standard_id", definition.standard_id),
        ("code", definition.code),
        ("short_name", definition.short_name),
        ("description", definition.description),
        ("source", definition.source),
        ("subject", definition.subject),
        ("course", definition.course),
        ("grade_band", definition.grade_band),
        ("domain", definition.domain),
        ("category_path", format_tuple(definition.category_path, " / ")),
        ("tags", format_tuple(definition.tags, ", ")),
        ("active", str(definition.active).lower()),
        ("available_modules", format_tuple(definition.available_modules, ", ")),
    )
    for label, value in fields:
        print(f"{label}: {display(value)}", file=stdout)

    child_standards = child_standard_definitions(library, definition)
    if child_standards:
        print("subparts:", file=stdout)
        for child in child_standards:
            print(
                f"{child.code}. {child.short_name} - {child.description}",
                file=stdout,
            )
    return 0


def handle_standards_search(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    query = args.query.casefold()
    definitions = tuple(
        definition
        for definition in matching_standards(library, standard_filters(args))
        if query in _search_text(definition)
    )
    if not definitions:
        print("No standards found.", file=stdout)
        return 0
    for definition in definitions:
        print(compact_standard_row(definition), file=stdout)
    return 0


def handle_standards_subjects(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return print_values(
        sorted(
            {
                definition.subject
                for definition in matching_standards(library, standard_filters(args))
                if definition.subject is not None
            }
        ),
        args.empty_message,
        stdout,
    )


def handle_standards_sources(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return print_values(
        sorted(
            {
                definition.source
                for definition in matching_standards(library, standard_filters(args))
            }
        ),
        args.empty_message,
        stdout,
    )


def handle_standards_domains(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return print_values(
        sorted(
            {
                definition.domain
                for definition in matching_standards(library, standard_filters(args))
                if definition.domain is not None
            }
        ),
        args.empty_message,
        stdout,
    )


def handle_standards_categories(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return print_values(
        sorted(
            {
                " / ".join(definition.category_path)
                for definition in matching_standards(library, standard_filters(args))
                if definition.category_path
            }
        ),
        args.empty_message,
        stdout,
    )


def handle_standards_profiles(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    profiles = tuple(
        sorted(
            filter_standards_profiles(
                library,
                subject=args.subject,
                course=args.course,
                source=args.source,
            ),
            key=lambda profile: profile.profile_id,
        )
    )
    if not profiles:
        print("No standards profiles found.", file=stdout)
        return 0

    for profile in profiles:
        print(compact_profile_row(profile), file=stdout)
    return 0


def _search_text(definition: StandardDefinition) -> str:
    parts = (
        definition.standard_id,
        definition.code,
        definition.short_name,
        definition.description,
        definition.source,
        definition.subject,
        definition.course,
        definition.grade_band,
        definition.domain,
        " ".join(definition.category_path),
        " ".join(definition.tags),
    )
    return " ".join(part for part in parts if part is not None).casefold()


def child_standard_definitions(
    library: StandardsLibrary,
    parent: StandardDefinition,
) -> tuple[StandardDefinition, ...]:
    """Return standards represented as ID/code subparts of parent."""
    standard_prefix = f"{parent.standard_id}."
    code_prefix = f"{parent.code}."
    return tuple(
        sorted(
            (
                definition
                for definition in library.standards
                if definition.standard_id.startswith(standard_prefix)
                and definition.code.startswith(code_prefix)
                and definition.standard_id != parent.standard_id
            ),
            key=lambda definition: definition.standard_id,
        )
    )
