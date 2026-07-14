"""Standards profile CLI parser helpers and command handlers."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import TextIO

from pds_core.cli_support.formatting import display, readable_standard_block
from pds_core.cli_support.standards_io import (
    load_standards_profile,
    write_standards_profile,
)
from pds_core.cli_support.standards_mutation import write_workspace_mutated_library
from pds_core.standards import (
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
    add_standards_to_profile,
    add_standards_profile,
    find_standard_definition,
    find_standards_profile,
    replace_standards_profile,
    remove_standards_from_profile,
    set_profile_standards,
    write_workspace_standards_library,
)


ProfileMembershipTransformation = Callable[
    [StandardsLibrary, str, tuple[str, ...]], StandardsLibrary
]


def add_profile_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", help="Display title for the profile.")
    parser.add_argument("--description", help="Display description for the profile.")
    parser.add_argument("--subject", help="Display/filter subject for the profile.")
    parser.add_argument("--course", help="Display/filter course for the profile.")
    parser.add_argument("--source", help="Display/filter source for the profile.")


def add_profile_standard_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--standard",
        action="append",
        dest="standards",
        help=(
            "Durable standard_id reference to include in ordered profile "
            "membership. Repeat for multiple standards."
        ),
    )


def handle_profile_create(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        profile = standards_profile_from_args(args.profile_id, args)
        updated_library = add_standards_profile(library, profile)
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Created standards profile {profile.profile_id}.", file=stdout)
    return 0


def handle_profile_replace(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        profile = standards_profile_from_args(args.profile_id, args)
        updated_library = replace_standards_profile(library, profile)
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(f"Replaced standards profile {profile.profile_id}.", file=stdout)
    return 0


def handle_profile_add_standard(
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
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(
        f"Added standard {definition.standard_id} to profile {profile.profile_id}.",
        file=stdout,
    )
    return 0


def handle_profile_remove_standard(
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
        standard_id = normalize_standard_argument(library, args.standard_id)
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
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(
        f"Removed standard {standard_id} from profile {profile.profile_id}.",
        file=stdout,
    )
    return 0


def handle_profile_add_standards(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return _handle_profile_membership_batch(
        args,
        library,
        stdout,
        stderr,
        transformation=add_standards_to_profile,
        message=f"Added {len(args.standard_ids)} standards to profile {{profile_id}}.",
    )


def handle_profile_remove_standards(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return _handle_profile_membership_batch(
        args,
        library,
        stdout,
        stderr,
        transformation=remove_standards_from_profile,
        message=f"Removed {len(args.standard_ids)} standards from profile {{profile_id}}.",
    )


def handle_profile_set_standards(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    standards = tuple(args.standards or ())
    return _handle_profile_membership_batch(
        args,
        library,
        stdout,
        stderr,
        transformation=set_profile_standards,
        standard_ids=standards,
        message=f"Set profile {{profile_id}} membership to {len(standards)} standards.",
    )


def _handle_profile_membership_batch(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
    *,
    transformation: ProfileMembershipTransformation,
    message: str,
    standard_ids: tuple[str, ...] | None = None,
) -> int:
    requested = standard_ids if standard_ids is not None else tuple(args.standard_ids)
    try:
        updated_library = transformation(library, args.profile_id, requested)
        write_workspace_mutated_library(args, updated_library)
    except (StandardsValidationError, StandardsWriteError) as error:
        print(f"Error: {error}", file=stderr)
        return 1
    profile = find_standards_profile(updated_library, args.profile_id)
    assert profile is not None
    print(message.format(profile_id=profile.profile_id), file=stdout)
    return 0


def handle_profile_validate(
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


def handle_profile_show(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    profile = find_standards_profile(library, args.profile_id)
    if profile is None:
        print(f"Standards profile not found: {args.profile_id}", file=stderr)
        return 1

    print("Profile", file=stdout)
    print("", file=stdout)
    print(f"Title: {display(profile.title)}", file=stdout)
    print(f"ID: {profile.profile_id}", file=stdout)
    print(f"Description: {display(profile.description)}", file=stdout)
    print(f"Subject: {display(profile.subject)}", file=stdout)
    print(f"Course: {display(profile.course)}", file=stdout)
    print(f"Source: {display(profile.source)}", file=stdout)

    print("", file=stdout)
    print("Standards:", file=stdout)
    had_unresolved = False
    for index, standard_id in enumerate(profile.standards, start=1):
        definition = find_standard_definition(library, standard_id)
        if definition is None:
            print(f"{index}. unresolved", file=stdout)
            print(f"   ID: {standard_id}", file=stdout)
            had_unresolved = True
        else:
            for line in readable_standard_block(definition, index=index):
                print(line, file=stdout)
        print("", file=stdout)
    return 1 if had_unresolved else 0


def handle_profile_export(
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
        write_standards_profile(target_path, profile, overwrite=args.overwrite)
    except StandardsWriteError as error:
        print(f"Error: {error}", file=stderr)
        return 1

    print(
        f"Exported standards profile {profile.profile_id} to {target_path}.",
        file=stdout,
    )
    return 0


def handle_profile_import(
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
        profile = load_standards_profile(args.path)
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


def standards_profile_from_args(
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


def normalize_standard_argument(
    library: StandardsLibrary,
    standard_id: str,
) -> str:
    definition = find_standard_definition(library, standard_id)
    if definition is not None:
        return definition.standard_id

    StandardsProfile(profile_id="profile", standards=(standard_id,))
    return standard_id
