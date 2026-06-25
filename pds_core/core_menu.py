"""Teacher-facing pds-core main menu entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from pds_core.cli_support import screen
from pds_core.cli_support.context import ArgumentParser
from pds_core.cli_support.menu import handle_standards_menu
from pds_core.standards import (
    StandardsLibrary,
    StandardsReadError,
    StandardsValidationError,
    StandardsWriteError,
    load_workspace_standards_library,
)
from pds_core.workspace import WorkspaceRootError, resolve_workspace_root


def main(argv: Sequence[str] | None = None) -> int:
    """Run the teacher-facing pds-core main menu."""
    return _run(argv, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)


def _run(
    argv: Sequence[str] | None,
    *,
    stdin: TextIO,
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

    try:
        workspace_root = resolve_workspace_root(args.workspace)
        if workspace_root.exists() and not workspace_root.is_dir():
            print(
                f"Error: workspace root is not a directory: {workspace_root}",
                file=stderr,
            )
            return 1
        library = load_workspace_standards_library(workspace_root)
        menu_args = argparse.Namespace(
            workspace_root=workspace_root,
            stdin=stdin,
        )
        return CoreMenu(menu_args, library, stdin, stdout, stderr).run()
    except (
        WorkspaceRootError,
        StandardsReadError,
        StandardsValidationError,
        StandardsWriteError,
    ) as error:
        print(f"Error: {error}", file=stderr)
        return 1
    except KeyboardInterrupt:
        print("", file=stdout)
        print("Cancelled.", file=stdout)
        return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the teacher-facing core shortcut."""
    parser = ArgumentParser(
        prog="core",
        description=(
            "Open the Paper Data Suite Core teacher-facing menu. "
            "Use pds-core for the full command namespace."
        ),
    )
    parser.add_argument(
        "--workspace",
        metavar="PATH",
        help=(
            "Use this Paper Data Suite workspace root for this menu without "
            "saving configuration."
        ),
    )
    return parser


class CoreMenu:
    """Small top-level menu that delegates to pds-core feature menus."""

    def __init__(
        self,
        args: argparse.Namespace,
        library: StandardsLibrary,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> None:
        self.args = args
        self.library = library
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def run(self) -> int:
        while True:
            self._print_menu()
            choice = self._prompt("Choose an option: ")
            if choice is None or choice in ("", "2"):
                print("Back.", file=self.stdout)
                return 0
            if choice == "1":
                code = handle_standards_menu(
                    self.args,
                    self.library,
                    self.stdout,
                    self.stderr,
                )
                if code != 0:
                    return code
                continue
            print("Invalid menu choice. Please try again.", file=self.stdout)

    def _print_menu(self) -> None:
        screen.clear_screen(self.stdout)
        print("Paper Data Suite Core", file=self.stdout)
        print("", file=self.stdout)
        print("1. Standards Management", file=self.stdout)
        print("2. Back / Exit", file=self.stdout)

    def _prompt(self, prompt: str) -> str | None:
        print(prompt, end="", file=self.stdout)
        line = self.stdin.readline()
        if line == "":
            print("", file=self.stdout)
            return None
        return line.rstrip("\r\n").strip()


if __name__ == "__main__":
    raise SystemExit(main())
