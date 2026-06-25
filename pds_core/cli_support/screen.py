"""Small screen helpers shared by teacher-facing menu code."""

from __future__ import annotations

import os
from typing import TextIO


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
