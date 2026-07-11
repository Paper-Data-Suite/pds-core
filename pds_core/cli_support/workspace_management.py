"""Teacher-facing workspace management commands and menu."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from pds_core.cli_support import screen
from pds_core.standards import StandardsLibrary
from pds_core.menu_navigation import (
    NavigationChoice,
    navigation_hint,
    parse_navigation_choice,
    print_navigation_options,
)
from pds_core.workspace import (
    WORKSPACE_ROOT_ENV_VAR,
    WorkspaceStatus,
    clear_saved_workspace_root,
    ensure_workspace_root,
    inspect_workspace_root,
    resolve_workspace_root,
    save_workspace_root,
)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _marker_path(root: Path) -> Path:
    return root / ".pds" / "workspace.json"


def _print_workspace_status(status: WorkspaceStatus, stdout: TextIO) -> None:
    marker_path = _marker_path(status.root)
    print("Resolved workspace root:", file=stdout)
    print(status.root, file=stdout)
    print("", file=stdout)
    print("Resolution source:", file=stdout)
    print(status.source, file=stdout)
    print("", file=stdout)
    print("Exists:", file=stdout)
    print(_yes_no(status.exists), file=stdout)
    print("", file=stdout)
    print("Is directory:", file=stdout)
    print(_yes_no(status.is_dir), file=stdout)
    print("", file=stdout)
    print("Writable:", file=stdout)
    print(_yes_no(status.is_writable), file=stdout)
    print("", file=stdout)
    print("Default workspace root:", file=stdout)
    print(status.default_root, file=stdout)
    print("", file=stdout)
    print("Saved config path:", file=stdout)
    print(status.config_path, file=stdout)
    print("", file=stdout)
    print("Workspace marker:", file=stdout)
    print("present" if marker_path.exists() else "missing", file=stdout)
    print("", file=stdout)
    print("Marker path:", file=stdout)
    print(marker_path, file=stdout)


def _print_workspace_paths(explicit_root: str | Path | None, stdout: TextIO) -> None:
    status = inspect_workspace_root(explicit_root)
    print("Workspace resolution precedence:", file=stdout)
    print("", file=stdout)
    print("1. Explicit path supplied to a command", file=stdout)
    print(f"2. {WORKSPACE_ROOT_ENV_VAR} environment variable", file=stdout)
    print("3. Saved user configuration", file=stdout)
    print("4. Default workspace root", file=stdout)
    print("", file=stdout)
    print("Saved config path:", file=stdout)
    print(status.config_path, file=stdout)
    print("", file=stdout)
    print("Default workspace root:", file=stdout)
    print(status.default_root, file=stdout)
    print("", file=stdout)
    print("Current resolved workspace root:", file=stdout)
    print(status.root, file=stdout)
    print("", file=stdout)
    print("Current resolution source:", file=stdout)
    print(status.source, file=stdout)
    print("", file=stdout)
    print(
        "The workspace root stores user data and generated working files.",
        file=stdout,
    )
    print(
        "It is separate from source checkouts, installed packages, "
        "and virtual environments.",
        file=stdout,
    )


def handle_workspace_show(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    """Show non-mutating workspace status."""
    _print_workspace_status(inspect_workspace_root(args.workspace), stdout)
    return 0


def handle_workspace_set(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    """Validate, create, and save a workspace root preference."""
    workspace_root = ensure_workspace_root(args.path)
    saved_root = save_workspace_root(workspace_root)
    print("Workspace root saved:", file=stdout)
    print(saved_root, file=stdout)
    print("", file=stdout)
    print(
        "This changes the saved workspace preference only. "
        "It does not move or delete existing files.",
        file=stdout,
    )
    print(
        f"If {WORKSPACE_ROOT_ENV_VAR} is set, it still takes precedence over "
        "the saved preference.",
        file=stdout,
    )
    return 0


def handle_workspace_validate(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    """Validate or create the current resolved workspace root."""
    workspace_root = ensure_workspace_root(resolve_workspace_root(args.workspace))
    print("Workspace validated successfully:", file=stdout)
    print(workspace_root, file=stdout)
    return 0


def handle_workspace_reset(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    """Clear only the saved workspace-root preference."""
    cleared = clear_saved_workspace_root()
    if cleared:
        print("Saved PDS workspace preference cleared.", file=stdout)
    else:
        print("No saved PDS workspace preference was set.", file=stdout)
    print("No workspace files were deleted.", file=stdout)
    print("", file=stdout)
    print("Current resolved PDS workspace root:", file=stdout)
    print(resolve_workspace_root(args.workspace), file=stdout)
    print("", file=stdout)
    print(
        f"If {WORKSPACE_ROOT_ENV_VAR} is set, it still takes precedence.",
        file=stdout,
    )
    return 0


def handle_workspace_paths(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    _stderr: TextIO,
) -> int:
    """Show workspace precedence and important paths."""
    _print_workspace_paths(args.workspace, stdout)
    return 0


def handle_workspace_menu(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Run the interactive workspace settings menu."""
    stdin = getattr(args, "stdin", sys.stdin)
    return WorkspaceSettingsMenu(args, library, stdin, stdout, stderr).run()


class WorkspaceSettingsMenu:
    """Interactive workspace management menu."""

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
        actions = {
            "1": self.show_status,
            "2": self.set_workspace_root,
            "3": self.validate_workspace,
            "4": self.reset_saved_preference,
            "5": self.show_paths,
        }
        while True:
            self._print_menu()
            choice = self._prompt("Choose an option: ")
            if choice is None or choice == "6":
                print("Back.", file=self.stdout)
                return 0
            if parse_navigation_choice(choice) is NavigationChoice.BACK:
                print("Back.", file=self.stdout)
                return 0
            action = actions.get(choice)
            if action is None:
                print(navigation_hint(), file=self.stdout)
                continue
            action()
            self._pause("Workspace Settings menu")

    def show_status(self) -> None:
        self._workflow_screen("Show Workspace Status")
        _print_workspace_status(
            inspect_workspace_root(self.args.workspace),
            self.stdout,
        )

    def set_workspace_root(self) -> None:
        self._workflow_screen(
            "Set Workspace Root",
            (
                "Enter the folder where Paper Data Suite should store class, "
                "assignment, scan, standards, and module data.",
                "",
                "This changes the saved workspace preference only. "
                "It does not move or delete existing files.",
                f"If {WORKSPACE_ROOT_ENV_VAR} is set, it still takes "
                "precedence over the saved preference.",
            ),
        )
        value = self._prompt("> ")
        if value is None or value == "":
            print("Cancelled.", file=self.stdout)
            return
        args = argparse.Namespace(path=value)
        handle_workspace_set(args, self.library, self.stdout, self.stderr)

    def validate_workspace(self) -> None:
        self._workflow_screen(
            "Validate/Create Current Workspace",
            ("This uses the current resolved workspace root.",),
        )
        handle_workspace_validate(self.args, self.library, self.stdout, self.stderr)

    def reset_saved_preference(self) -> None:
        self._workflow_screen(
            "Reset Saved Workspace Preference",
            ("This clears only the saved preference. No workspace files are deleted.",),
        )
        handle_workspace_reset(self.args, self.library, self.stdout, self.stderr)

    def show_paths(self) -> None:
        self._workflow_screen("Workspace Paths and Precedence")
        _print_workspace_paths(self.args.workspace, self.stdout)

    def _print_menu(self) -> None:
        self._clear_screen()
        print("Workspace Settings", file=self.stdout)
        print("", file=self.stdout)
        print("1. Show workspace status", file=self.stdout)
        print("2. Set workspace root", file=self.stdout)
        print("3. Validate/create current workspace", file=self.stdout)
        print("4. Reset saved workspace preference", file=self.stdout)
        print("5. Show workspace paths and precedence", file=self.stdout)
        print_navigation_options(file=self.stdout)
        print("", file=self.stdout)

    def _workflow_screen(self, title: str, lines: tuple[str, ...] = ()) -> None:
        self._clear_screen()
        print(title, file=self.stdout)
        print("", file=self.stdout)
        for line in lines:
            print(line, file=self.stdout)
        if lines:
            print("", file=self.stdout)

    def _clear_screen(self) -> None:
        screen.clear_screen(self.stdout)
        screen.print_app_header(self.stdout)

    def _prompt(self, prompt: str) -> str | None:
        print(prompt, end="", file=self.stdout, flush=True)
        line = self.stdin.readline()
        print("", file=self.stdout)
        if line == "":
            return None
        return line.rstrip("\r\n").strip()

    def _pause(self, context: str) -> None:
        print("", file=self.stdout)
        print(f"Press Enter to return to the {context}...", file=self.stdout)
        print(">", end="", file=self.stdout, flush=True)
        self.stdin.readline()
        print("", file=self.stdout)
