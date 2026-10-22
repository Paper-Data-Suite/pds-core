"""Version and implemented capabilities for Core's teacher-experience contract.

A capability identifies an implemented Core facility; it does not attest to
Suite installation, producer adoption, user authorization, or a Core release.
This initial slice deliberately advertises no capabilities until the concrete
header and shared-command implementations qualify in later #237 slices.
"""

from __future__ import annotations

from typing import Final

__all__ = (
    "TEACHER_EXPERIENCE_CONTRACT_VERSION",
    "get_teacher_experience_capabilities",
)

TEACHER_EXPERIENCE_CONTRACT_VERSION: Final[str] = "1"

_IMPLEMENTED_CAPABILITIES: Final[frozenset[str]] = frozenset()


def get_teacher_experience_capabilities() -> frozenset[str]:
    """Report only teacher-experience capabilities implemented in this Core build.

    The immutable result is intentionally empty in #237 Slice 1. The upcoming
    header and command slices must add their tokens only after their actual
    API implementations and conformance tests pass. In particular, the version
    does not signal that any Notes or classroom administration service exists.
    """
    return _IMPLEMENTED_CAPABILITIES
