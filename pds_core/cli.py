"""Command-line entry point for PDS Core standards commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import NoReturn, TextIO, cast

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
    add_standard_definition,
    add_standards_profile,
    filter_standard_definitions,
    filter_standards_profiles,
    find_standard_definition,
    find_standards_profile,
    load_standards_library,
    load_workspace_standards_library,
    replace_standard_definition,
    replace_standards_profile,
    standards_library_path,
    standards_profile_from_dict,
    standards_profile_to_dict,
    upsert_standard_definition,
    write_standards_library,
    write_workspace_standards_library,
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
        args.workspace_root = workspace_root
        if getattr(args, "load_workspace_library", True):
            library = load_workspace_standards_library(workspace_root)
        else:
            library = StandardsLibrary(standards=(), profiles=())
        return handler(args, library, stdout, stderr)
    except (
        WorkspaceRootError,
        StandardsReadError,
        StandardsValidationError,
        StandardsWriteError,
    ) as error:
        print(f"Error: {error}", file=stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="pds-core",
        description=(
            "Paper Data Suite core utilities. Standards commands load the "
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
            "Browse, validate, import, export, and mutate the standards "
            "library. standard_id is the durable Paper Data Suite identifier; "
            "code is a teacher-facing display code and may not be unique. "
            "Retire/reactivate are non-destructive; destructive standard "
            "deletion is not supported."
        ),
        help="Browse, validate, import, export, and mutate the standards library.",
    )
    standards_subparsers = standards.add_subparsers(dest="standards_command")

    validate_parser = standards_subparsers.add_parser(
        "validate",
        help="Validate the active workspace standards library.",
        description=(
            "Validate the active workspace standards library. A missing "
            "standards/library.json is valid and is treated as an empty "
            "library without creating workspace artifacts. standard_id and "
            "profile_id values are durable references."
        ),
    )
    validate_parser.set_defaults(handler=_handle_standards_validate)

    validate_file_parser = standards_subparsers.add_parser(
        "validate-file",
        help="Validate an external standards library JSON file.",
        description=(
            "Validate an external canonical StandardsLibrary JSON file without "
            "importing it or reading the workspace library. standard_id and "
            "profile_id values are durable references."
        ),
    )
    validate_file_parser.add_argument("path", help="Standards library JSON file.")
    validate_file_parser.set_defaults(
        handler=_handle_standards_validate_file,
        load_workspace_library=False,
    )

    import_parser = standards_subparsers.add_parser(
        "import",
        help="Import a full standards library JSON file.",
        description=(
            "Import a canonical StandardsLibrary JSON file. Full-library import "
            "requires an explicit mode such as --replace; replacing an existing "
            "workspace library also requires --overwrite. Merge/upsert import "
            "is future work. standard_id and profile_id values are durable "
            "references."
        ),
    )
    import_parser.add_argument("path", help="Standards library JSON file to import.")
    import_parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the workspace library with the validated import file.",
    )
    import_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow --replace to overwrite an existing workspace library.",
    )
    import_parser.set_defaults(
        handler=_handle_standards_import,
        load_workspace_library=False,
    )

    export_parser = standards_subparsers.add_parser(
        "export",
        help="Export the active workspace standards library.",
        description=(
            "Export canonical StandardsLibrary JSON with durable standard_id "
            "and profile_id values preserved. code and title are display "
            "fields. Existing target files are refused unless --overwrite is "
            "supplied."
        ),
    )
    export_parser.add_argument("path", help="Target standards library JSON file.")
    export_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the target export file if it already exists.",
    )
    export_parser.set_defaults(handler=_handle_standards_export)

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

    add_parser = standards_subparsers.add_parser(
        "add",
        help="Add a new standard definition.",
        description=(
            "Add one standard definition to the canonical workspace "
            "standards/library.json. standard_id is the durable internal ID; "
            "code is a display field and may not be unique. Destructive "
            "standard deletion is not supported."
        ),
    )
    _add_standard_mutation_fields(add_parser, include_standard_id=True)
    add_parser.set_defaults(handler=_handle_standards_add)

    replace_parser = standards_subparsers.add_parser(
        "replace",
        help="Replace an existing standard definition.",
        description=(
            "Replace one existing standard definition in the canonical "
            "workspace standards/library.json. This is full-record "
            "replacement; omitted optional fields are cleared. standard_id is "
            "the durable internal ID; code is a display field and may not be "
            "unique. Destructive standard deletion is not supported."
        ),
    )
    replace_parser.add_argument(
        "standard_id",
        help="Durable standard_id to replace.",
    )
    _add_standard_mutation_fields(replace_parser, include_standard_id=False)
    replace_parser.set_defaults(handler=_handle_standards_replace)

    upsert_parser = standards_subparsers.add_parser(
        "upsert",
        help="Add or replace a standard definition.",
        description=(
            "Add or replace one standard definition in the canonical workspace "
            "standards/library.json. standard_id is the durable internal ID; "
            "code is a display field and may not be unique. Destructive "
            "standard deletion is not supported."
        ),
    )
    upsert_parser.add_argument(
        "standard_id",
        help="Durable standard_id to add or replace.",
    )
    _add_standard_mutation_fields(upsert_parser, include_standard_id=False)
    upsert_parser.set_defaults(handler=_handle_standards_upsert)

    retire_parser = standards_subparsers.add_parser(
        "retire",
        help="Mark an existing standard inactive without deleting it.",
        description=(
            "Retire one existing standard by setting active=false in the "
            "canonical workspace standards/library.json. Retire is "
            "non-destructive: the standard remains present and profile or "
            "historical references remain valid. Destructive standard deletion "
            "is not supported."
        ),
    )
    retire_parser.add_argument("standard_id", help="Durable standard_id to retire.")
    retire_parser.add_argument(
        "--force",
        action="store_true",
        help="Return success even if the standard is already inactive.",
    )
    retire_parser.set_defaults(handler=_handle_standards_retire)

    reactivate_parser = standards_subparsers.add_parser(
        "reactivate",
        help="Mark an existing retired standard active again.",
        description=(
            "Reactivate one existing standard by setting active=true in the "
            "canonical workspace standards/library.json. Reactivate is "
            "non-destructive and preserves profile or historical references. "
            "Destructive standard deletion is not supported."
        ),
    )
    reactivate_parser.add_argument(
        "standard_id",
        help="Durable standard_id to reactivate.",
    )
    reactivate_parser.add_argument(
        "--force",
        action="store_true",
        help="Return success even if the standard is already active.",
    )
    reactivate_parser.set_defaults(handler=_handle_standards_reactivate)

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

    profile_create_parser = profile_subparsers.add_parser(
        "create",
        help="Create a standards profile by durable profile_id.",
        description=(
            "Create a standards profile. profile_id is the durable profile "
            "identifier. title, source, subject, and course are display or "
            "filtering fields. Repeat --standard to store ordered durable "
            "standard_id membership references. Destructive profile deletion "
            "is not supported in v0.4.0."
        ),
    )
    profile_create_parser.add_argument(
        "--profile-id",
        required=True,
        help="Durable profile_id for the new profile.",
    )
    _add_profile_metadata_arguments(profile_create_parser)
    _add_profile_standard_arguments(profile_create_parser)
    profile_create_parser.set_defaults(handler=_handle_profile_create)

    profile_replace_parser = profile_subparsers.add_parser(
        "replace",
        help="Replace one standards profile by durable profile_id.",
        description=(
            "Replace a full standards profile record. The positional "
            "profile_id is the durable identifier; omitted title, source, "
            "subject, course, description, and --standard membership values "
            "are cleared. Standards membership stores ordered durable "
            "standard_id references. Destructive profile deletion is not "
            "supported in v0.4.0."
        ),
    )
    profile_replace_parser.add_argument(
        "profile_id",
        help="Durable profile_id to replace.",
    )
    _add_profile_metadata_arguments(profile_replace_parser)
    _add_profile_standard_arguments(profile_replace_parser)
    profile_replace_parser.set_defaults(handler=_handle_profile_replace)

    profile_add_standard_parser = profile_subparsers.add_parser(
        "add-standard",
        help="Add one standard_id reference to a profile.",
        description=(
            "Add one durable standard_id reference to a standards profile. "
            "This edits profile membership only and preserves profile "
            "metadata. Destructive profile deletion is not supported in "
            "v0.4.0."
        ),
    )
    profile_add_standard_parser.add_argument(
        "profile_id",
        help="Durable profile_id whose membership will be edited.",
    )
    profile_add_standard_parser.add_argument(
        "standard_id",
        help="Durable standard_id reference to append to the profile.",
    )
    profile_add_standard_parser.set_defaults(handler=_handle_profile_add_standard)

    profile_remove_standard_parser = profile_subparsers.add_parser(
        "remove-standard",
        help="Remove one standard_id reference from a profile.",
        description=(
            "Remove one durable standard_id reference from profile membership "
            "only. This does not delete the standard definition. Destructive "
            "profile deletion is not supported in v0.4.0."
        ),
    )
    profile_remove_standard_parser.add_argument(
        "profile_id",
        help="Durable profile_id whose membership will be edited.",
    )
    profile_remove_standard_parser.add_argument(
        "standard_id",
        help="Durable standard_id reference to remove from the profile.",
    )
    profile_remove_standard_parser.set_defaults(
        handler=_handle_profile_remove_standard
    )

    profile_validate_parser = profile_subparsers.add_parser(
        "validate",
        help="Validate one standards profile by durable profile_id.",
        description=(
            "Validate one standards profile against the active workspace "
            "library without writing files. profile_id is durable and profile "
            "membership stores durable standard_id references. Destructive "
            "profile deletion is not supported in v0.4.0."
        ),
    )
    profile_validate_parser.add_argument(
        "profile_id",
        help="Durable profile_id to validate.",
    )
    profile_validate_parser.set_defaults(handler=_handle_profile_validate)

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

    profile_import_parser = profile_subparsers.add_parser(
        "import",
        help="Import one standalone standards profile JSON file.",
        description=(
            "Import one canonical StandardsProfile JSON file. Use --add to add "
            "a new durable profile_id without replacing existing profiles. Use "
            "--replace --overwrite to explicitly replace an existing profile."
        ),
    )
    profile_import_parser.add_argument("path", help="Standards profile JSON file.")
    profile_import_parser.add_argument(
        "--add",
        action="store_true",
        help="Add the profile and fail if profile_id already exists.",
    )
    profile_import_parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing profile with the same durable profile_id.",
    )
    profile_import_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Required with --replace to overwrite an existing profile.",
    )
    profile_import_parser.set_defaults(handler=_handle_profile_import)

    profile_export_parser = profile_subparsers.add_parser(
        "export",
        help="Export one standalone standards profile JSON file.",
        description=(
            "Export one standards profile by durable profile_id. Existing target "
            "files are refused unless --overwrite is supplied. title is a "
            "display field."
        ),
    )
    profile_export_parser.add_argument(
        "profile_id",
        help="Durable profile_id to export.",
    )
    profile_export_parser.add_argument("path", help="Target standards profile JSON file.")
    profile_export_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the target export file if it already exists.",
    )
    profile_export_parser.set_defaults(handler=_handle_profile_export)

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


def _add_profile_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", help="Display title for the profile.")
    parser.add_argument("--description", help="Display description for the profile.")
    parser.add_argument("--subject", help="Display/filter subject for the profile.")
    parser.add_argument("--course", help="Display/filter course for the profile.")
    parser.add_argument("--source", help="Display/filter source for the profile.")


def _add_profile_standard_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--standard",
        action="append",
        dest="standards",
        help=(
            "Durable standard_id reference to include in ordered profile "
            "membership. Repeat for multiple standards."
        ),
    )


def _add_standard_mutation_fields(
    parser: argparse.ArgumentParser,
    *,
    include_standard_id: bool,
) -> None:
    if include_standard_id:
        parser.add_argument(
            "--standard-id",
            required=True,
            help="Durable internal standard_id for the new standard.",
        )
    parser.add_argument(
        "--code",
        required=True,
        help="Display code for teachers; it may not be unique.",
    )
    parser.add_argument("--source", required=True, help="Standards source.")
    parser.add_argument("--short-name", required=True, help="Short display name.")
    parser.add_argument("--description", required=True, help="Standard description.")
    parser.add_argument("--subject", help="Optional subject.")
    parser.add_argument("--course", help="Optional course.")
    parser.add_argument("--grade-band", help="Optional grade band.")
    parser.add_argument("--domain", help="Optional domain.")
    parser.add_argument(
        "--category-path",
        help=(
            "Optional category path using '/' separators, for example "
            "'English Language Arts/Reading Literature/Close Reading'."
        ),
    )
    parser.add_argument(
        "--tag",
        action="append",
        dest="tags",
        help="Optional tag. Repeat this flag for multiple tags.",
    )
    parser.add_argument(
        "--available-module",
        action="append",
        dest="available_modules",
        help="Optional available module. Repeat this flag for multiple modules.",
    )
    active_group = parser.add_mutually_exclusive_group()
    active_group.add_argument(
        "--active",
        action="store_const",
        const=True,
        dest="active",
        help="Write the standard as active (default).",
    )
    active_group.add_argument(
        "--inactive",
        action="store_const",
        const=False,
        dest="active",
        help="Write the standard as inactive.",
    )
    parser.set_defaults(active=True)


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


def _handle_standards_validate(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    path = standards_library_path(args.workspace_root)
    if path.exists():
        print("Standards library is valid.", file=stdout)
    else:
        print(
            "Standards library is valid. No workspace standards library exists; "
            "using empty library.",
            file=stdout,
        )
    return 0


def _handle_standards_validate_file(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        load_standards_library(args.path)
    except StandardsReadError as error:
        print(f"Error: {error}", file=stderr)
        return 1
    print(f"Standards library file is valid: {args.path}", file=stdout)
    return 0


def _handle_standards_export(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    target_path = Path(args.path)
    if target_path.exists() and not args.overwrite:
        print(f"Error: target file already exists: {target_path}", file=stderr)
        return 1

    try:
        write_standards_library(target_path, library, overwrite=args.overwrite)
    except StandardsWriteError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Exported standards library to {target_path}.", file=stdout)
    return 0


def _handle_standards_import(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not args.replace:
        print("Error: import requires an explicit mode such as --replace.", file=stderr)
        return 2

    try:
        imported_library = load_standards_library(args.path)
    except StandardsReadError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    target_path = standards_library_path(args.workspace_root)
    if target_path.exists() and not args.overwrite:
        print(
            f"Error: workspace standards library already exists: {target_path}",
            file=stderr,
        )
        return 1

    try:
        write_workspace_standards_library(
            args.workspace_root,
            imported_library,
            overwrite=args.overwrite,
        )
    except StandardsWriteError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Imported standards library from {args.path}.", file=stdout)
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


def _handle_standards_add(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        definition = _standard_definition_from_args(args.standard_id, args)
        updated_library = add_standard_definition(library, definition)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Added standard {definition.standard_id}.", file=stdout)
    return 0


def _handle_standards_replace(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        definition = _standard_definition_from_args(args.standard_id, args)
        updated_library = replace_standard_definition(library, definition)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Replaced standard {definition.standard_id}.", file=stdout)
    return 0


def _handle_standards_upsert(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    existed = find_standard_definition(library, args.standard_id) is not None
    try:
        definition = _standard_definition_from_args(args.standard_id, args)
        updated_library = upsert_standard_definition(library, definition)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    action = "Updated" if existed else "Added"
    print(f"{action} standard {definition.standard_id}.", file=stdout)
    return 0


def _handle_standards_retire(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return _set_standard_active(
        args,
        library,
        stdout,
        stderr,
        active=False,
        action="Retired",
        already_message="standard is already inactive",
    )


def _handle_standards_reactivate(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return _set_standard_active(
        args,
        library,
        stdout,
        stderr,
        active=True,
        action="Reactivated",
        already_message="standard is already active",
    )


def _standard_definition_from_args(
    standard_id: str,
    args: argparse.Namespace,
) -> StandardDefinition:
    return StandardDefinition(
        standard_id=standard_id,
        code=args.code,
        source=args.source,
        short_name=args.short_name,
        description=args.description,
        subject=args.subject,
        course=args.course,
        grade_band=args.grade_band,
        domain=args.domain,
        category_path=_parse_category_path(args.category_path),
        tags=tuple(args.tags or ()),
        active=args.active,
        available_modules=tuple(args.available_modules or ()),
    )


def _set_standard_active(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
    *,
    active: bool,
    action: str,
    already_message: str,
) -> int:
    existing = find_standard_definition(library, args.standard_id)
    if existing is None:
        print(f"Error: standard not found: {args.standard_id}", file=stderr)
        return 1
    if existing.active is active and not args.force:
        print(f"Error: {already_message}: {args.standard_id}", file=stderr)
        return 1

    try:
        updated_definition = dataclass_replace(existing, active=active)
        updated_library = replace_standard_definition(library, updated_definition)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"{action} standard {args.standard_id}.", file=stdout)
    return 0


def _write_workspace_mutated_library(
    args: argparse.Namespace,
    library: StandardsLibrary,
) -> None:
    write_workspace_standards_library(args.workspace_root, library, overwrite=True)


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


def _handle_profile_create(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        profile = _standards_profile_from_args(args.profile_id, args)
        updated_library = add_standards_profile(library, profile)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Created standards profile {profile.profile_id}.", file=stdout)
    return 0


def _handle_profile_replace(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        profile = _standards_profile_from_args(args.profile_id, args)
        updated_library = replace_standards_profile(library, profile)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Replaced standards profile {profile.profile_id}.", file=stdout)
    return 0


def _handle_profile_add_standard(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    profile = find_standards_profile(library, args.profile_id)
    if profile is None:
        print(f"Error: standards profile not found: {args.profile_id}", file=stderr)
        return 1

    definition = find_standard_definition(library, args.standard_id)
    if definition is None:
        print(f"Error: standard not found: {args.standard_id}", file=stderr)
        return 1

    if definition.standard_id in profile.standards:
        print(
            "Error: profile already contains standard "
            f"{definition.standard_id}: {profile.profile_id}",
            file=stderr,
        )
        return 1

    try:
        updated_profile = dataclass_replace(
            profile,
            standards=profile.standards + (definition.standard_id,),
        )
        updated_library = replace_standards_profile(library, updated_profile)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(
        f"Added standard {definition.standard_id} to profile {profile.profile_id}.",
        file=stdout,
    )
    return 0


def _handle_profile_remove_standard(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    profile = find_standards_profile(library, args.profile_id)
    if profile is None:
        print(f"Error: standards profile not found: {args.profile_id}", file=stderr)
        return 1

    try:
        standard_id = _normalize_standard_argument(library, args.standard_id)
    except StandardsValidationError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    if standard_id not in profile.standards:
        print(
            "Error: profile does not contain standard "
            f"{standard_id}: {profile.profile_id}",
            file=stderr,
        )
        return 1

    try:
        updated_profile = dataclass_replace(
            profile,
            standards=tuple(
                existing
                for existing in profile.standards
                if existing != standard_id
            ),
        )
        updated_library = replace_standards_profile(library, updated_profile)
        _write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(
        f"Removed standard {standard_id} from profile {profile.profile_id}.",
        file=stdout,
    )
    return 0


def _handle_profile_validate(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    profile = find_standards_profile(library, args.profile_id)
    if profile is None:
        print(f"Error: standards profile not found: {args.profile_id}", file=stderr)
        return 1

    print(f"Standards profile is valid: {profile.profile_id}", file=stdout)
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


def _handle_profile_export(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    profile = find_standards_profile(library, args.profile_id)
    if profile is None:
        print(f"Standards profile not found: {args.profile_id}", file=stderr)
        return 1

    target_path = Path(args.path)
    if target_path.exists() and not args.overwrite:
        print(f"Error: target file already exists: {target_path}", file=stderr)
        return 1

    try:
        _write_standards_profile(target_path, profile, overwrite=args.overwrite)
    except StandardsWriteError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(
        f"Exported standards profile {profile.profile_id} to {target_path}.",
        file=stdout,
    )
    return 0


def _handle_profile_import(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if args.add and args.replace:
        print("Error: profile import modes --add and --replace conflict.", file=stderr)
        return 2
    if not args.add and not args.replace:
        print(
            "Error: profile import requires an explicit mode such as --add.",
            file=stderr,
        )
        return 2
    if args.replace and not args.overwrite:
        print("Error: profile replace requires --overwrite.", file=stderr)
        return 1

    try:
        profile = _load_standards_profile(args.path)
        updated_library = (
            add_standards_profile(library, profile)
            if args.add
            else replace_standards_profile(library, profile)
        )
    except (StandardsReadError, StandardsValidationError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    try:
        write_workspace_standards_library(
            args.workspace_root,
            updated_library,
            overwrite=True,
        )
    except StandardsWriteError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    action = "Added" if args.add else "Replaced"
    print(
        f"{action} standards profile {profile.profile_id} from {args.path}.",
        file=stdout,
    )
    return 0


def _standards_profile_from_args(
    profile_id: str,
    args: argparse.Namespace,
) -> StandardsProfile:
    return StandardsProfile(
        profile_id=profile_id,
        standards=tuple(args.standards or ()),
        subject=args.subject,
        course=args.course,
        source=args.source,
        title=args.title,
        description=args.description,
    )


def _normalize_standard_argument(
    library: StandardsLibrary,
    standard_id: str,
) -> str:
    definition = find_standard_definition(library, standard_id)
    if definition is not None:
        return definition.standard_id

    StandardsProfile(profile_id="profile", standards=(standard_id,))
    return standard_id


def _load_standards_profile(path: str | Path) -> StandardsProfile:
    source_path = Path(path)
    try:
        with source_path.open(encoding="utf-8") as profile_file:
            data = json.load(profile_file)
    except json.JSONDecodeError as error:
        raise StandardsReadError(source_path, f"invalid JSON: {error}") from error
    except (OSError, UnicodeError) as error:
        raise StandardsReadError(source_path, str(error)) from error

    if not isinstance(data, dict):
        raise StandardsReadError(source_path, "top-level JSON value must be a mapping")

    try:
        return standards_profile_from_dict(data)
    except (StandardsValidationError, KeyError, TypeError) as error:
        raise StandardsReadError(
            source_path,
            f"invalid standards profile data: {error}",
        ) from error


def _write_standards_profile(
    path: str | Path,
    profile: StandardsProfile,
    *,
    overwrite: bool = False,
) -> None:
    target_path = Path(path)
    try:
        content = json.dumps(
            standards_profile_to_dict(profile),
            indent=2,
            sort_keys=True,
        ) + "\n"
    except (StandardsValidationError, TypeError, ValueError) as error:
        raise StandardsWriteError(
            target_path,
            f"invalid standards profile data: {error}",
        ) from error

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StandardsWriteError(target_path, str(error)) from error

    if target_path.exists() and not overwrite:
        raise StandardsWriteError(target_path, "target file already exists")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
        ) as profile_file:
            temp_path = Path(profile_file.name)
            profile_file.write(content)
            profile_file.flush()
            os.fsync(profile_file.fileno())

        os.replace(temp_path, target_path)
        temp_path = None
    except (OSError, UnicodeError) as error:
        cleanup_error: OSError | None = None
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as caught_cleanup_error:
                cleanup_error = caught_cleanup_error
        message = str(error)
        if cleanup_error is not None:
            message = f"{message}; temporary file cleanup failed: {cleanup_error}"
        raise StandardsWriteError(target_path, message) from error


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
