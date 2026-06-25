"""Parser construction for the pds-core CLI."""

from __future__ import annotations

import argparse
from typing import Any

from pds_core.cli_support.context import ArgumentParser
from pds_core.cli_support.profiles import (
    add_profile_metadata_arguments,
    add_profile_standard_arguments,
    handle_profile_add_standard,
    handle_profile_create,
    handle_profile_export,
    handle_profile_import,
    handle_profile_remove_standard,
    handle_profile_replace,
    handle_profile_show,
    handle_profile_validate,
)
from pds_core.cli_support.standards_io import (
    handle_standards_export,
    handle_standards_import,
    handle_standards_validate,
    handle_standards_validate_file,
)
from pds_core.cli_support.standards_mutation import (
    add_standard_mutation_fields,
    handle_standards_add,
    handle_standards_reactivate,
    handle_standards_replace,
    handle_standards_retire,
    handle_standards_upsert,
)
from pds_core.cli_support.standards_read import (
    add_profile_filters,
    add_standard_filters,
    handle_standards_categories,
    handle_standards_domains,
    handle_standards_list,
    handle_standards_profiles,
    handle_standards_search,
    handle_standards_show,
    handle_standards_sources,
    handle_standards_subjects,
)


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
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

    _add_validate_parser(standards_subparsers)
    _add_validate_file_parser(standards_subparsers)
    _add_import_parser(standards_subparsers)
    _add_export_parser(standards_subparsers)
    _add_list_parser(standards_subparsers)
    _add_show_parser(standards_subparsers)
    _add_standard_mutation_parsers(standards_subparsers)
    _add_search_parser(standards_subparsers)
    _add_browse_value_parsers(standards_subparsers)
    _add_profiles_parser(standards_subparsers)
    _add_profile_parser(standards_subparsers)

    return parser


def _add_validate_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    validate_parser.set_defaults(handler=handle_standards_validate)


def _add_validate_file_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
        handler=handle_standards_validate_file,
        load_workspace_library=False,
    )


def _add_import_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
        handler=handle_standards_import,
        load_workspace_library=False,
    )


def _add_export_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    export_parser.set_defaults(handler=handle_standards_export)


def _add_list_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
    list_parser = standards_subparsers.add_parser(
        "list",
        help="List standards by durable standard_id.",
        description=(
            "List standards. standard_id is durable; code is display-facing and "
            "may not be unique."
        ),
    )
    add_standard_filters(list_parser)
    list_parser.set_defaults(handler=handle_standards_list)


def _add_show_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    show_parser.set_defaults(handler=handle_standards_show)


def _add_standard_mutation_parsers(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    add_standard_mutation_fields(add_parser, include_standard_id=True)
    add_parser.set_defaults(handler=handle_standards_add)

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
    add_standard_mutation_fields(replace_parser, include_standard_id=False)
    replace_parser.set_defaults(handler=handle_standards_replace)

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
    add_standard_mutation_fields(upsert_parser, include_standard_id=False)
    upsert_parser.set_defaults(handler=handle_standards_upsert)

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
    retire_parser.set_defaults(handler=handle_standards_retire)

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
    reactivate_parser.set_defaults(handler=handle_standards_reactivate)


def _add_search_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
    search_parser = standards_subparsers.add_parser(
        "search",
        help="Search standards by display text.",
        description=(
            "Search standards read-only. The query is matched against "
            "standard_id, code, names, descriptions, and metadata."
        ),
    )
    search_parser.add_argument("query", help="Case-insensitive text query.")
    add_standard_filters(search_parser)
    search_parser.set_defaults(handler=handle_standards_search)


def _add_browse_value_parsers(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
    for name, handler, empty_message in (
        ("subjects", handle_standards_subjects, "No subjects found."),
        ("sources", handle_standards_sources, "No sources found."),
        ("domains", handle_standards_domains, "No domains found."),
        ("categories", handle_standards_categories, "No categories found."),
    ):
        browse_parser = standards_subparsers.add_parser(
            name,
            help=f"List standard {name}.",
            description=f"List standard {name} from the read-only library.",
        )
        add_standard_filters(browse_parser)
        browse_parser.set_defaults(handler=handler, empty_message=empty_message)


def _add_profiles_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
    profiles_parser = standards_subparsers.add_parser(
        "profiles",
        help="List standards profiles by durable profile_id.",
        description=(
            "List standards profiles. profile_id is the durable profile "
            "identifier; titles and sources are display fields."
        ),
    )
    add_profile_filters(profiles_parser)
    profiles_parser.set_defaults(handler=handle_standards_profiles)


def _add_profile_parser(
    standards_subparsers: argparse._SubParsersAction[Any],
) -> None:
    profile_parser = standards_subparsers.add_parser(
        "profile",
        help="Inspect one standards profile.",
        description=(
            "Inspect standards profiles read-only. profile_id is the durable "
            "profile identifier."
        ),
    )
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")

    _add_profile_create_parser(profile_subparsers)
    _add_profile_replace_parser(profile_subparsers)
    _add_profile_membership_parsers(profile_subparsers)
    _add_profile_validate_parser(profile_subparsers)
    _add_profile_show_parser(profile_subparsers)
    _add_profile_import_parser(profile_subparsers)
    _add_profile_export_parser(profile_subparsers)


def _add_profile_create_parser(
    profile_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    add_profile_metadata_arguments(profile_create_parser)
    add_profile_standard_arguments(profile_create_parser)
    profile_create_parser.set_defaults(handler=handle_profile_create)


def _add_profile_replace_parser(
    profile_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    add_profile_metadata_arguments(profile_replace_parser)
    add_profile_standard_arguments(profile_replace_parser)
    profile_replace_parser.set_defaults(handler=handle_profile_replace)


def _add_profile_membership_parsers(
    profile_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    profile_add_standard_parser.set_defaults(handler=handle_profile_add_standard)

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
        handler=handle_profile_remove_standard
    )


def _add_profile_validate_parser(
    profile_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    profile_validate_parser.set_defaults(handler=handle_profile_validate)


def _add_profile_show_parser(
    profile_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    profile_show_parser.set_defaults(handler=handle_profile_show)


def _add_profile_import_parser(
    profile_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    profile_import_parser.set_defaults(handler=handle_profile_import)


def _add_profile_export_parser(
    profile_subparsers: argparse._SubParsersAction[Any],
) -> None:
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
    profile_export_parser.set_defaults(handler=handle_profile_export)
