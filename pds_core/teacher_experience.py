"""Version and implemented capabilities for Core's teacher-experience contract.

A capability identifies an implemented Core facility; it does not attest to
Suite installation, producer adoption, user authorization, or a Core release.
This slice advertises only the implemented, tested header renderer/printer.
The shared-command parser and all Notes/administration services remain absent.
"""

from __future__ import annotations

from typing import Final

__all__ = (
    "TEACHER_EXPERIENCE_CONTRACT_VERSION",
    "get_teacher_experience_capabilities",
)

TEACHER_EXPERIENCE_CONTRACT_VERSION: Final[str] = "1"

_IMPLEMENTED_CAPABILITIES: Final[frozenset[str]] = frozenset({"terminal.header.v1"})


def get_teacher_experience_capabilities() -> frozenset[str]:
    """Report only teacher-experience capabilities implemented in this Core build.

    This Slice 3 implementation includes safe streamed teacher headers. The
    :notes parser is not yet installed, and neither a Notes service nor a
    classroom administration menu is implied by the contract version.
    """
    return _IMPLEMENTED_CAPABILITIES
