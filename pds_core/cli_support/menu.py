"""Interactive standards management menu entry point."""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

from pds_core.cli_support.menu_runner import StandardsMenu
from pds_core.standards import StandardsLibrary

__all__ = ["StandardsMenu", "handle_standards_menu"]


def handle_standards_menu(
    args: argparse.Namespace,
    library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Run the interactive standards management menu."""
    stdin = getattr(args, "stdin", sys.stdin)
    runner = StandardsMenu(args, library, stdin, stdout, stderr)
    return runner.run()
