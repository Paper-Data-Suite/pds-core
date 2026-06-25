"""Command-line entry point for read-only PDS Core inspection commands."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import NoReturn, TextIO, cast

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsValidationError,
    filter_standard_definitions,
    filter_standards_profiles,
    find_standard_definition,
    find_standards_profile,
    load_workspace_standards_library,
)
from pds_core.workspace import WorkspaceRootError, resolve_workspace_root


_EMPTY = "-"
_CATEGORY_SEPARATOR = "/"
_Handler = Callable[[argparse.Namespace, StandardsLibrary, TextIO, TextIO], int]


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        raise SystemExit(f"{self.prog}: error: {message}")


@dataclass(frozen=True, slots=True)
class _StandardFilters:
    source: str | None = None
    subject: str | None = None
    course: str | None = None
    domain: str | None = None
    category_path_prefix: tuple[str, ...] = ()
    available_module: str | None = None
    active: bool | None = True


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pds-core command-line interface."""
    return _run(argv, stdout=sys.stdout, stderr=sys.stderr)


def _run(
    argv: Sequence[str] | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        code = error.code
        if isinstance(code, str):
            if code:
                print(code, file=stderr)
            return 2
        if code is None:
            return 0
        return code

    handler = cast(_Handler | None, getattr(args, "handler", None))
    if handler is None:
        parser.print_help(stdout)
        return 0

    try:
        workspace_root = resolve_workspace_root(args.workspace)
        if workspace_root.exists() and not workspace_root.is_dir():
            print(
                f"Error: workspace root is not a directory: {workspace_root}",
                file=stderr,
            )
            return 1
        library = load_workspace_standards_library(workspace_root)
        return handler(args, library, stdout, stderr)
    except (WorkspaceRootError, StandardsReadError, StandardsValidationError) as error:
        print(f"Error: {error}", file=stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="pds-core",
        description=(
            "Read-only Paper Data Suite core utilities. Commands load the "
            "active workspace standards library unless --workspace is supplied; "
            "a missing standards/library.json is treated as an empty library. "
            "For standards commands, standard_id and profile_id are durable "
            "internal IDs; code, title, and source are display fields."
        ),
    )
    parser.add_argument(
        "--workspace",
        metavar="PATH",
        help=(
            "Use this Paper Data Suite workspace root for this read-only "
            "command without saving configuration."
        ),
    )

    subparsers = parser.add_subparsers(dest="command")
    standards = subparsers.add_parser(
        "standards",
        description=(
            "Browse the read-only standards library. standard_id is the durable "
            "Paper Data Suite identifier; code is a teacher-facing display code "
            "and may not be unique."
        ),
        help="Browse and inspect the read-only standards library.",
    )
    standards_subparsers = standards.add_subparsers(dest="standards_command")

    list_parser = standards_subparsers.add_parser(
        "list",
        help="List standards by durable standard_id.",
        description=(
            "List standards. standard_id is durable; code is display-facing and "
            "may not be unique."
        ),
    )
    _add_standard_filters(list_parser)
    list_parser.set_defaults(handler=_handle_standards_list)

    show_parser = standards_subparsers.add_parser(
        "show",
        help="Show one standard by durable standard_id.",
        description=(
            "Show full read-only details for one standard. standard_id is the "
            "durable Paper Data Suite identifier; code is display-facing and "
            "may not be unique."
        ),
    )
    show_parser.add_argument("standard_id", help="Durable standard_id to show.")
    show_parser.set_defaults(handler=_handle_standards_show)

    search_parser = standards_subparsers.add_parser(
        "search",
        help="Search standards by display text.",
        description=(
            "Search standards read-only. The query is matched against "
            "standard_id, code, names, descriptions, and metadata."
        ),
    )
    search_parser.add_argument("query", help="Case-insensitive text query.")
    _add_standard_filters(search_parser)
    search_parser.set_defaults(handler=_handle_standards_search)

    for name, handler, empty_message in (
        ("subjects", _handle_standards_subjects, "No subjects found."),
        ("sources", _handle_standards_sources, "No sources found."),
        ("domains", _handle_standards_domains, "No domains found."),
        ("categories", _handle_standards_categories, "No categories found."),
    ):
        browse_parser = standards_subparsers.add_parser(
            name,
            help=f"List standard {name}.",
            description=f"List standard {name} from the read-only library.",
        )
        _add_standard_filters(browse_parser)
        browse_parser.set_defaults(handler=handler, empty_message=empty_message)

    profiles_parser = standards_subparsers.add_parser(
        "profiles",
        help="List standards profiles by durable profile_id.",
        description=(
            "List standards profiles. profile_id is the durable profile "
            "identifier; titles and sources are display fields."
        ),
    )
    _add_profile_filters(profiles_parser)
    profiles_parser.set_defaults(handler=_handle_standards_profiles)

    profile_parser = standards_subparsers.add_parser(
        "profile",
        help="Inspect one standards profile.",
        description=(
            "Inspect standards profiles read-only. profile_id is the durable "
            "profile identifier."
        ),
    )
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")
    profile_show_parser = profile_subparsers.add_parser(
        "show",
        help="Show one standards profile by durable profile_id.",
        description=(
            "Show full read-only details for one standards profile. profile_id "
            "is durable; title and source are display fields."
        ),
    )
    profile_show_parser.add_argument(
        "profile_id",
        help="Durable profile_id to show.",
    )
    profile_show_parser.set_defaults(handler=_handle_profile_show)

    return parser


def _add_standard_filters(parser: argparse.ArgumentParser) -> None:
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


def _add_profile_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", help="Filter profiles by exact source.")
    parser.add_argument("--subject", help="Filter profiles by exact subject.")
    parser.add_argument("--course", help="Filter profiles by exact course.")


def _standard_filters(args: argparse.Namespace) -> _StandardFilters:
    return _StandardFilters(
        source=args.source,
        subject=args.subject,
        course=args.course,
        domain=args.domain,
        category_path_prefix=_parse_category_path(args.category),
        available_module=args.available_module,
        active=args.active,
    )


def _parse_category_path(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    parts = tuple(part.strip() for part in value.split(_CATEGORY_SEPARATOR))
    if not all(parts):
        raise StandardsValidationError(
            "category must contain non-empty path parts separated by '/'."
        )
    return parts


def _matching_standards(
    library: StandardsLibrary,
    filters: _StandardFilters,
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


def _handle_standards_list(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    definitions = _matching_standards(library, _standard_filters(args))
    if not definitions:
        print("No standards found.", file=stdout)
        return 0
    for definition in definitions:
        print(_compact_standard_row(definition), file=stdout)
    return 0


def _handle_standards_show(
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
        ("category_path", _format_tuple(definition.category_path, " / ")),
        ("tags", _format_tuple(definition.tags, ", ")),
        ("active", str(definition.active).lower()),
        ("available_modules", _format_tuple(definition.available_modules, ", ")),
    )
    for label, value in fields:
        print(f"{label}: {_display(value)}", file=stdout)
    return 0


def _handle_standards_search(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    query = args.query.casefold()
    definitions = tuple(
        definition
        for definition in _matching_standards(library, _standard_filters(args))
        if query in _search_text(definition)
    )
    if not definitions:
        print("No standards found.", file=stdout)
        return 0
    for definition in definitions:
        print(_compact_standard_row(definition), file=stdout)
    return 0


def _handle_standards_subjects(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return _print_values(
        sorted(
            {
                definition.subject
                for definition in _matching_standards(library, _standard_filters(args))
                if definition.subject is not None
            }
        ),
        args.empty_message,
        stdout,
    )


def _handle_standards_sources(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return _print_values(
        sorted(
            {
                definition.source
                for definition in _matching_standards(library, _standard_filters(args))
            }
        ),
        args.empty_message,
        stdout,
    )


def _handle_standards_domains(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return _print_values(
        sorted(
            {
                definition.domain
                for definition in _matching_standards(library, _standard_filters(args))
                if definition.domain is not None
            }
        ),
        args.empty_message,
        stdout,
    )


def _handle_standards_categories(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    return _print_values(
        sorted(
            {
                " / ".join(definition.category_path)
                for definition in _matching_standards(library, _standard_filters(args))
                if definition.category_path
            }
        ),
        args.empty_message,
        stdout,
    )


def _handle_standards_profiles(
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
        print(_compact_profile_row(profile), file=stdout)
    return 0


def _handle_profile_show(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    profile = find_standards_profile(library, args.profile_id)
    if profile is None:
        print(f"Standards profile not found: {args.profile_id}", file=stderr)
        return 1

    fields = (
        ("profile_id", profile.profile_id),
        ("title", profile.title),
        ("description", profile.description),
        ("subject", profile.subject),
        ("course", profile.course),
        ("source", profile.source),
    )
    for label, value in fields:
        print(f"{label}: {_display(value)}", file=stdout)

    print("standards:", file=stdout)
    had_unresolved = False
    for standard_id in profile.standards:
        definition = find_standard_definition(library, standard_id)
        if definition is None:
            print(f"  {standard_id} | unresolved | unresolved", file=stdout)
            had_unresolved = True
        else:
            print(
                f"  {definition.standard_id} | {definition.code} | "
                f"{definition.short_name}",
                file=stdout,
            )
    return 1 if had_unresolved else 0


def _print_values(values: Sequence[str], empty_message: str, stdout: TextIO) -> int:
    if not values:
        print(empty_message, file=stdout)
        return 0
    for value in values:
        print(value, file=stdout)
    return 0


def _compact_standard_row(definition: StandardDefinition) -> str:
    status = "active" if definition.active else "inactive"
    return " | ".join(
        (
            definition.standard_id,
            definition.code,
            definition.short_name,
            definition.source,
            _display(definition.subject),
            _display(definition.course),
            _display(definition.domain),
            status,
        )
    )


def _compact_profile_row(profile: StandardsProfile) -> str:
    return " | ".join(
        (
            profile.profile_id,
            _display(profile.title),
            _display(profile.subject),
            _display(profile.course),
            _display(profile.source),
            f"{len(profile.standards)} standards",
        )
    )


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


def _display(value: str | None) -> str:
    return value if value else _EMPTY


def _format_tuple(values: tuple[str, ...], separator: str) -> str | None:
    if not values:
        return None
    return separator.join(values)


if __name__ == "__main__":
    raise SystemExit(main())
