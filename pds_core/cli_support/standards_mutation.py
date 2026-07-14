"""Standard definition mutation CLI command handlers."""

from __future__ import annotations

import argparse
from dataclasses import replace as dataclass_replace
from typing import TextIO

from pds_core.cli_support.standards_read import parse_category_path
from pds_core.cli_support.standards_io import load_standard_definitions_request
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
    add_standard_definition,
    add_standard_definitions,
    find_standard_definition,
    replace_standard_definition,
    upsert_standard_definition,
    write_workspace_standards_library,
)


def add_standard_mutation_fields(
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


def handle_standards_add(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        definition = standard_definition_from_args(args.standard_id, args)
        updated_library = add_standard_definition(library, definition)
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Added standard {definition.standard_id}.", file=stdout)
    return 0


def handle_standards_add_batch(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        definitions = load_standard_definitions_request(args.path)
        updated_library = add_standard_definitions(library, definitions)
        write_workspace_mutated_library(args, updated_library)
    except (StandardsReadError, StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Added {len(definitions)} standards from {args.path}.", file=stdout)
    return 0


def handle_standards_replace(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        definition = standard_definition_from_args(args.standard_id, args)
        updated_library = replace_standard_definition(library, definition)
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Replaced standard {definition.standard_id}.", file=stdout)
    return 0


def handle_standards_upsert(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    existed = find_standard_definition(library, args.standard_id) is not None
    try:
        definition = standard_definition_from_args(args.standard_id, args)
        updated_library = upsert_standard_definition(library, definition)
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    action = "Updated" if existed else "Added"
    print(f"{action} standard {definition.standard_id}.", file=stdout)
    return 0


def handle_standards_retire(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return set_standard_active(
        args,
        library,
        stdout,
        stderr,
        active=False,
        action="Retired",
        already_message="standard is already inactive",
    )


def handle_standards_reactivate(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return set_standard_active(
        args,
        library,
        stdout,
        stderr,
        active=True,
        action="Reactivated",
        already_message="standard is already active",
    )


def standard_definition_from_args(
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
        category_path=parse_category_path(args.category_path),
        tags=tuple(args.tags or ()),
        active=args.active,
        available_modules=tuple(args.available_modules or ()),
    )


def set_standard_active(
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
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"{action} standard {args.standard_id}.", file=stdout)
    return 0


def write_workspace_mutated_library(
    args: argparse.Namespace,
    library: StandardsLibrary,
) -> None:
    write_workspace_standards_library(args.workspace_root, library, overwrite=True)
