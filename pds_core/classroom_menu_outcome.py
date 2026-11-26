"""Best-effort notices after a classroom operation has a known outcome."""

from __future__ import annotations

from typing import TextIO


def _outcome_notice(message: str, *, file: TextIO) -> None:
    """A lost terminal notice must not erase an already determined receipt.

    Use only for outcome diagnostics, never for prompts or reviewed previews.
    The returned receipt remains authoritative when the output stream closes
    or the teacher interrupts display after the operation.
    """
    try:
        print(message, file=file, flush=True)
    except (OSError, ValueError, KeyboardInterrupt):
        pass
