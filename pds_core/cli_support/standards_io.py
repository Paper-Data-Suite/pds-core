"""Standards library validation/import/export and profile JSON file helpers."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import TextIO

from pds_core.standards import (
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
    load_standards_library,
    standards_library_path,
    standards_profile_from_dict,
    standards_profile_to_dict,
    write_standards_library,
    write_workspace_standards_library,
)


def handle_standards_validate(
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


def handle_standards_validate_file(
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


def handle_standards_export(
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


def handle_standards_import(
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


def load_standards_profile(path: str | Path) -> StandardsProfile:
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


def write_standards_profile(
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
