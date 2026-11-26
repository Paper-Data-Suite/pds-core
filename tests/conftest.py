"""Explicit capability-disabled fixture for historical classroom gate tests."""

from __future__ import annotations

import pytest

from pds_core import teacher_experience


@pytest.fixture
def classroom_capability_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the unqualified build contract without disabling real services."""
    capabilities = teacher_experience.get_teacher_experience_capabilities()
    monkeypatch.setattr(
        teacher_experience, "_IMPLEMENTED_CAPABILITIES",
        capabilities - {"classroom.menu.v1"},
    )
