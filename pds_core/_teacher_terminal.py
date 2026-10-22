"""Conservative, read-only terminal color detection for teacher headers.

No import-time terminal inspection, handle mutation or global stream changes.
All failed probes choose plain text, including Windows consoles without VT.
"""

from __future__ import annotations

import os
from typing import TextIO


def _is_windows() -> bool:
    return os.name == "nt"


def _windows_vt_enabled(output: TextIO) -> bool:
    """Read the supplied Windows console mode; never enable VT processing."""
    try:
        import ctypes
        import importlib

        msvcrt = importlib.import_module("msvcrt")
        get_osfhandle = getattr(msvcrt, "get_osfhandle")
        handle = get_osfhandle(output.fileno())
        if handle == -1:
            return False
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            return False
        get_mode = win_dll("kernel32", use_last_error=True).GetConsoleMode
        get_mode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        get_mode.restype = ctypes.c_int
        mode = ctypes.c_uint32(0)
        if not get_mode(ctypes.c_void_p(handle), ctypes.byref(mode)):
            return False
        return bool(mode.value & 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        # Non-console streams, invalid/closed handles, unavailable Win32 APIs,
        # and capability-probe failures must not leak terminal escapes.
        return False


def supports_teacher_ansi(output: TextIO) -> bool:
    """Only allow styling when the actual output demonstrably supports it."""
    if os.environ.get("NO_COLOR"):
        return False
    term = os.environ.get("TERM", "").strip()
    if term.casefold() == "dumb":
        return False
    try:
        if not output.isatty():
            return False
    except Exception:
        return False
    if _is_windows():
        return _windows_vt_enabled(output)
    # A POSIX TTY with no TERM designation is not evidence of ANSI support.
    return bool(term)
