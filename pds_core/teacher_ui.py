"""Pure, validated teacher-facing headers under Core's v1 interface contract.

Rendering remains pure; output and ANSI probing are handled explicitly by
print_teacher_header, with conservative read-only capability checks. Importing
this module does not inspect terminals, access workspaces, or write output.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal, TextIO

from pds_core._teacher_terminal import supports_teacher_ansi

__all__ = (
    "TeacherScreenHeader",
    "render_teacher_header",
    "print_teacher_header",
)

_GREEN = "\x1b[32m"
_RESET = "\x1b[0m"


def _validate_field(value: str | None, *, name: str, required: bool) -> None:
    """Reject invalid or terminal-active input before rendering any field."""
    if value is None:
        if required:
            raise TypeError(f"{name} must be a nonblank string")
        return
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if required and not value.strip():
        raise ValueError(f"{name} must not be blank")
    # C* includes ASCII/C1 controls, ESC, bidi overrides and invalid surrogates;
    # Zl/Zp are Unicode line separators even when no ASCII newline is present.
    for character in value:
        kind = unicodedata.category(character)
        if kind.startswith("C") or kind in ("Zl", "Zp"):
            raise ValueError(f"{name} contains a control or line separator")


@dataclass(frozen=True, slots=True)
class TeacherScreenHeader:
    """Validated display-only application, task and optional context labels.

    Labels are caller-approved presentation text, never an installed-module
    identity, authorization claim or a reason to query student/work records.
    """

    application_name: str
    screen_title: str
    context_line: str | None = None

    def __post_init__(self) -> None:
        _validate_field(self.application_name, name="application_name", required=True)
        _validate_field(self.screen_title, name="screen_title", required=True)
        _validate_field(self.context_line, name="context_line", required=False)


def render_teacher_header(
    header: TeacherScreenHeader,
    *,
    ansi: bool = False,
) -> str:
    """Return exactly two or three LF-separated lines, without a final LF.

    Only the application-name line receives the exact green SGR wrapper when
    explicitly requested. No terminal-state, global-output or storage effects.
    """
    if not isinstance(header, TeacherScreenHeader):
        raise TypeError("header must be a TeacherScreenHeader")
    if type(ansi) is not bool:
        raise TypeError("ansi must be a bool")

    name = header.application_name
    if ansi:
        name = f"{_GREEN}{name}{_RESET}"
    lines = [name, header.screen_title]
    if header.context_line is not None and header.context_line.strip():
        lines.append(header.context_line)
    return "\n".join(lines)


def print_teacher_header(
    header: TeacherScreenHeader,
    *,
    output: TextIO,
    color: Literal["auto", "never"] = "auto",
) -> None:
    """Print one header plus one LF to the supplied stream, with safe fallback.

    Only auto mode consults stream/terminal capabilities. No screen clearing,
    prompt interception, global output or Windows console-mode mutation occurs.
    """
    if not isinstance(header, TeacherScreenHeader):
        raise TypeError("header must be a TeacherScreenHeader")
    if type(color) is not str:
        raise TypeError("color must be 'auto' or 'never'")
    if color not in ("auto", "never"):
        raise ValueError("color must be 'auto' or 'never'")
    if not callable(getattr(output, "write", None)):
        raise TypeError("output must be a writable TextIO stream")
    ansi = color == "auto" and supports_teacher_ansi(output)
    output.write(render_teacher_header(header, ansi=ansi) + "\n")
