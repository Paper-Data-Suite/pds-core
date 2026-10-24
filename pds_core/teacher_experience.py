"""Version and implemented capabilities for Core's teacher-experience contract.

A capability identifies an implemented Core facility; it does not attest to
Suite installation, producer adoption, user authorization, or a Core release.
Only the implemented header and pure opt-in shared-command parser are
advertised. Notes records, menus, CLI and administration remain absent.
"""

from __future__ import annotations

from typing import Final

__all__ = (
    "TEACHER_EXPERIENCE_CONTRACT_VERSION",
    "get_teacher_experience_capabilities",
)

TEACHER_EXPERIENCE_CONTRACT_VERSION: Final[str] = "1"

_IMPLEMENTED_CAPABILITIES: Final[frozenset[str]] = frozenset(
    {"terminal.header.v1", "terminal.notes_command.v1"}
)


def get_teacher_experience_capabilities() -> frozenset[str]:
    """Report only teacher-experience capabilities implemented in this Core build.

    Header printing and pure :notes recognition are separately usable Core
    primitives. Neither token promises a Notes record store, an interactive
    Notes menu, a Core CLI Notes route, or consumer-specific adoption.
    """
    return _IMPLEMENTED_CAPABILITIES
