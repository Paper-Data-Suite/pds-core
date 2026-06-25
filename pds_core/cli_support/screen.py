"""Small screen helpers shared by teacher-facing menu code."""

from __future__ import annotations

import os
from typing import TextIO

PDS_CORE_TITLE = "PDS Core"
ANSI_GREEN = "\033[32m"
ANSI_RESET = "\033[0m"


def supports_ansi(stdout: TextIO) -> bool:
    """Return whether menu output should include ANSI styling."""
    try:
        return bool(stdout.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def app_header(*, color: bool) -> str:
    """Return the persistent pds-core interactive header."""
    if color:
        return f"{ANSI_GREEN}{PDS_CORE_TITLE}{ANSI_RESET}"
    return PDS_CORE_TITLE


def print_app_header(stdout: TextIO) -> None:
    """Print the persistent app header for interactive menu screens."""
    print(app_header(color=supports_ansi(stdout)), file=stdout)
    print("", file=stdout)


def clear_screen(stdout: TextIO) -> None:
    """Clear an interactive terminal without affecting captured test output."""
    try:
        if not stdout.isatty():
            return
    except (AttributeError, OSError, ValueError):
        return

    try:
        os.system("cls" if os.name == "nt" else "clear")
    except OSError:
        return
