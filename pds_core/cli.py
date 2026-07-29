"""Command-line entry point for PDS Core standards commands."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO, cast

from pds_core.cli_support.context import Handler
from pds_core.cli_support.academic_registry import emit_academic_command_error
from pds_core.cli_support.parser import build_parser
from pds_core.standards import (
    StandardsLibrary,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
    load_workspace_standards_library,
)
from pds_core.workspace import WorkspaceRootError, resolve_workspace_root


def _academic_command_name(args: object) -> str:
    academic = getattr(args, "academic_command", None)
    if academic == "registry":
        command = getattr(args, "registry_command", None)
        entity = getattr(args, "entity", None)
        suffix = f" {entity}" if command in {"list", "show"} and entity else ""
        return f"academic registry {command or 'command'}{suffix}"
    if academic == "periods":
        return f"academic periods {getattr(args, 'periods_command', None) or 'command'}"
    return "academic command"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pds-core command-line interface."""
    return _run(argv, stdout=sys.stdout, stderr=sys.stderr)


def _run(
    argv: Sequence[str] | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    parser = build_parser()
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

    handler = cast(Handler | None, getattr(args, "handler", None))
    if handler is None:
        parser.print_help(stdout)
        return 0

    try:
        workspace_root = resolve_workspace_root(args.workspace)
        if workspace_root.exists() and not workspace_root.is_dir():
            raise WorkspaceRootError(
                f"workspace root is not a directory: {workspace_root}"
            )
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
        if getattr(args, "command", None) == "academic":
            if not hasattr(args, "workspace_root"):
                raw_workspace = getattr(args, "workspace", None)
                args.workspace_root = (
                    Path(raw_workspace).resolve(strict=False)
                    if isinstance(raw_workspace, str) and raw_workspace
                    else Path.cwd().resolve()
                )
            return emit_academic_command_error(
                args,
                _academic_command_name(args),
                error,
                stdout,
                stderr,
            )
        print(f"Error: {error}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
