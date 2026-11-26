"""Version and implemented capabilities for Core's teacher-experience contract.

A capability identifies an implemented Core facility; it does not attest to
Suite installation, producer adoption, user authorization, or a Core release.
Notes records, menu, and noninteractive CLI are implemented by Core #239–240.
Core #241 adds guarded individual roster edits and the direct roster CLI.
Core #242 adds the shared Workspace & Classroom Management menu.
Tokens make no claim of a release or an adopting consumer.
"""

from __future__ import annotations

from typing import Final

__all__ = (
    "TEACHER_EXPERIENCE_CONTRACT_VERSION",
    "get_teacher_experience_capabilities",
)

TEACHER_EXPERIENCE_CONTRACT_VERSION: Final[str] = "1"

_IMPLEMENTED_CAPABILITIES: Final[frozenset[str]] = frozenset(
    {
        "terminal.header.v1",
        "terminal.notes_command.v1",
        "notes.records.v1",
        "notes.menu.v1",
        "notes.cli.v1",
        "classroom.roster_edits.v1",
        "classroom.menu.v1",
    }
)


def get_teacher_experience_capabilities() -> frozenset[str]:
    """Report only teacher-experience capabilities implemented in this Core build.

    Tokens identify features present in this build, not published-version,
    producer/Suite adoption, workspace authorization, or classroom qualification.
    """
    return _IMPLEMENTED_CAPABILITIES
