"""Teacher-facing pds-core main menu entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from pds_core.cli_support import screen
from pds_core.cli_support.context import ArgumentParser
from pds_core.cli_support.menu import handle_standards_menu
from pds_core.cli_support.workspace_management import handle_workspace_menu
from pds_core.menu_navigation import (
    QuitPDS,
    ReturnToMainMenu,
    navigation_hint,
    parse_navigation_choice,
    print_navigation_options,
)
from pds_core.teacher_commands import (
    PromptKind,
    SharedTeacherCommand,
    parse_shared_teacher_command,
)
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    TeacherContextHint,
    TeacherMenuExit,
)
from pds_core.teacher_menus import (
    _classroom_menu_available,
    run_notes_tasks_menu,
)
from pds_core.classroom_entry import run_classroom_entry
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
        menu_args = argparse.Namespace(
            workspace=args.workspace,
            stdin=stdin,
        )
        return CoreMenu(menu_args, stdin, stdout, stderr).run()
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
    except QuitPDS:
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
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> None:
        self.args = args
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def run(self) -> int:
        while True:
            self._print_menu()
            choice = self._prompt("Choose an option: ")
            if choice is None or choice in ("", "4"):
                return 0
            try:
                parse_navigation_choice(choice, allow_back=False)
            except ReturnToMainMenu:
                continue
            if choice == "1":
                try:
                    code = self._run_standards_menu()
                except ReturnToMainMenu:
                    continue
                if code != 0:
                    return code
                continue
            if choice == "2":
                try:
                    code = handle_workspace_menu(
                        self.args,
                        StandardsLibrary(standards=(), profiles=()),
                        self.stdout,
                        self.stderr,
                    )
                except ReturnToMainMenu:
                    continue
                if code != 0:
                    return code
                continue
            if choice == "3":
                self._print_help()
                self._pause("Main Menu")
                continue
            if choice == "5" or (
                parse_shared_teacher_command(
                    choice,
                    prompt_kind=PromptKind.MENU_CHOICE,
                    interactive=True,
                    allow_notes=True,
                )
                is SharedTeacherCommand.NOTES
            ):
                result = self._run_notes_menu()
                if result is TeacherMenuExit.QUIT:
                    return 0
                continue
            if choice == "6":
                receipt = run_classroom_entry(
                    self.args.workspace, stdin=self.stdin, stdout=self.stdout,
                    stderr=self.stderr, interactive=True,
                )
                # Core holds no subordinate selection or cached workspace/library
                # at this boundary. Next entry resolves canonical state afresh.
                if receipt.exit is TeacherMenuExit.QUIT:
                    return 0
                if receipt.exit in (TeacherMenuExit.FAILED, TeacherMenuExit.UNAVAILABLE) or receipt.change_scopes:
                    print(receipt.message, file=self.stdout)
                    self._pause("Main Menu")
                continue
            print(navigation_hint(), file=self.stdout)

    def _run_standards_menu(self) -> int:
        try:
            workspace_root = resolve_workspace_root(self.args.workspace)
            if workspace_root.exists() and not workspace_root.is_dir():
                print(
                    f"Error: workspace root is not a directory: {workspace_root}",
                    file=self.stderr,
                )
                return 1
            library = load_workspace_standards_library(workspace_root)
        except (
            WorkspaceRootError,
            StandardsReadError,
            StandardsValidationError,
            StandardsWriteError,
        ) as error:
            print(f"Error: {error}", file=self.stderr)
            return 1

        standards_args = argparse.Namespace(
            workspace=self.args.workspace,
            workspace_root=workspace_root,
            stdin=self.stdin,
        )
        return handle_standards_menu(
            standards_args,
            library,
            self.stdout,
            self.stderr,
        )

    def _run_notes_menu(self) -> TeacherMenuExit:
        """Return only a navigation disposition; never impersonate a producer."""
        workspace_hint = (
            Path(self.args.workspace) if self.args.workspace is not None else None
        )
        result = run_notes_tasks_menu(
            SharedTeacherMenuRequest(
                caller_application="PDS Core",
                return_token="core-main-menu-notes",
                context=TeacherContextHint(workspace_root=workspace_hint),
            ),
            read_line=self.stdin.readline,
            output=self.stdout,
            interactive=True,
            error_output=self.stdout,
        )
        if result.exit in (TeacherMenuExit.FAILED, TeacherMenuExit.UNAVAILABLE):
            # Pause before redraw so a teacher can read the safe recovery note.
            print(result.message, file=self.stdout)
            self._pause("Main Menu")
        return result.exit

    def _print_help(self) -> None:
        screen.clear_screen(self.stdout)
        screen.print_app_header(self.stdout)
        print("Help", file=self.stdout)
        print("", file=self.stdout)
        print(
            "Use Standards Management to browse and maintain shared standards.",
            file=self.stdout,
        )
        print(
            "Use Workspace Settings to inspect, set, validate, or reset "
            "the shared workspace root.",
            file=self.stdout,
        )
        print(
            "Workspace reset clears only the saved preference; "
            "it does not delete files.",
            file=self.stdout,
        )
        print("", file=self.stdout)

    def _print_menu(self) -> None:
        screen.clear_screen(self.stdout)
        screen.print_app_header(self.stdout)
        print("Main Menu", file=self.stdout)
        print("", file=self.stdout)
        print("1. Standards Management", file=self.stdout)
        print("2. Workspace Settings", file=self.stdout)
        print("3. Help", file=self.stdout)
        print("4. Exit", file=self.stdout)
        print("5. Notes & Tasks  (:notes)", file=self.stdout)
        suffix = "" if _classroom_menu_available() else " (not yet available)"
        print(f"6. Workspace & Classroom Management{suffix}", file=self.stdout)
        print_navigation_options(back=False, main_menu=False, file=self.stdout)
        print("", file=self.stdout)

    def _prompt(self, prompt: str) -> str | None:
        print(prompt, end="", file=self.stdout, flush=True)
        line = self.stdin.readline()
        print("", file=self.stdout)
        if line == "":
            return None
        return line.rstrip("\r\n").strip()

    def _pause(self, context: str = "menu") -> None:
        print("", file=self.stdout)
        print(f"Press Enter to return to the {context}...", file=self.stdout)
        print(">", end="", file=self.stdout, flush=True)
        self.stdin.readline()
        print("", file=self.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
