"""CLI handlers for bundled starter standards libraries."""

from __future__ import annotations

import argparse
from typing import TextIO

from pds_core.standards import StandardsLibrary, StandardsValidationError
from pds_core.starter_standards import (
    StarterStandardsInstallError,
    StarterStandardsPackMetadata,
    install_starter_standards_library,
    list_starter_standards_packs,
    starter_standards_pack_metadata,
    validate_starter_standards_library,
)


def handle_starter_standards_list(
    _args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    """List bundled starter standards packs."""
    packs = list_starter_standards_packs()
    if not packs:
        print("No starter standards packs found.", file=stdout)
        return 0
    for pack in packs:
        print(_metadata_row(pack), file=stdout)
    return 0


def handle_starter_standards_preview(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Preview one bundled starter standards pack."""
    try:
        metadata = starter_standards_pack_metadata(args.pack_id)
    except StandardsValidationError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(metadata.title, file=stdout)
    print("", file=stdout)
    print(f"Pack ID: {metadata.pack_id}", file=stdout)
    print(f"Source: {metadata.source}", file=stdout)
    print(f"Grade bands: {', '.join(metadata.grade_bands)}", file=stdout)
    print(f"Courses: {', '.join(metadata.courses)}", file=stdout)
    print(f"Standards: {metadata.standard_count}", file=stdout)
    print(f"Profiles: {metadata.profile_count}", file=stdout)
    print(f"Profile IDs: {', '.join(metadata.profile_ids)}", file=stdout)
    print(f"Description: {metadata.description}", file=stdout)
    return 0


def handle_starter_standards_validate(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Validate one or all bundled starter standards packs."""
    pack_ids = (
        (args.pack_id,)
        if args.pack_id is not None
        else tuple(pack.pack_id for pack in list_starter_standards_packs())
    )
    for pack_id in pack_ids:
        try:
            library = validate_starter_standards_library(pack_id)
        except StandardsValidationError as error:
            print(f"Error: {error}", file=stderr)
            return 1
        print(
            f"Starter standards pack is valid: {pack_id} "
            f"({len(library.standards)} standards, "
            f"{len(library.profiles)} profiles).",
            file=stdout,
        )
    return 0


def handle_starter_standards_install(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Install one bundled starter standards pack into the workspace."""
    try:
        result = install_starter_standards_library(
            args.workspace_root,
            args.pack_id,
            library,
            overwrite_conflicts=args.overwrite,
        )
    except StarterStandardsInstallError as error:
        print(f"Error: {error}", file=stderr)
        return 1
    except StandardsValidationError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Installed starter standards pack: {result.pack_id}", file=stdout)
    print(f"Workspace library: {result.target_path}", file=stdout)
    print(
        "Standards: "
        f"{result.standards_added} added, "
        f"{result.standards_skipped} skipped, "
        f"{result.standards_overwritten} overwritten.",
        file=stdout,
    )
    print(
        "Profiles: "
        f"{result.profiles_added} added, "
        f"{result.profiles_skipped} skipped, "
        f"{result.profiles_overwritten} overwritten.",
        file=stdout,
    )
    if result.changed_count == 0:
        print("No workspace changes were needed.", file=stdout)
    print("No standards usage events were recorded.", file=stdout)
    return 0


def _metadata_row(metadata: StarterStandardsPackMetadata) -> str:
    return " | ".join(
        (
            metadata.pack_id,
            metadata.title,
            metadata.source,
            f"grade bands: {', '.join(metadata.grade_bands)}",
            f"{metadata.standard_count} standards",
            f"{metadata.profile_count} profiles",
        )
    )
