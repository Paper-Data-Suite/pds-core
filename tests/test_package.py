"""Package smoke tests for pds-core."""

from __future__ import annotations

import pds_core


def test_package_imports() -> None:
    assert pds_core is not None