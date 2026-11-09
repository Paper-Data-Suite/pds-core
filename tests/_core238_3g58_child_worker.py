"""Test-only hard-exit worker for Core #238 Slice 3G58.

This script is intentionally NOT installed under pds_core or exposed as a CLI.
It may touch only a newly prepared, synthetic directory directly beneath the
current process's system temporary directory. The real implementation accepts
no caller-selected writer paths; this test substitutes just its temporary root.
No production teacher data, association, or Notes records are touched.
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from pds_core import _teacher_private_recovery_scratch_dual_stage_attempt as drill


HARD_EXIT_CODE = 93
_PREFIX = "core238_3g58_crash_"
_MARKER = ".core238-3g58-synthetic-only"
_ALLOWED = frozenset(
    {
        drill.PrivateScratchDualStageFault.AFTER_PREPARED,
        drill.PrivateScratchDualStageFault.AFTER_REGISTRY_MARK,
        drill.PrivateScratchDualStageFault.AFTER_REGISTRY_REPLACE,
        drill.PrivateScratchDualStageFault.AFTER_REGISTRY_FLUSH,
        drill.PrivateScratchDualStageFault.AFTER_DESCRIPTOR_MARK,
        drill.PrivateScratchDualStageFault.AFTER_DESCRIPTOR_REPLACE,
        drill.PrivateScratchDualStageFault.AFTER_DESCRIPTOR_FLUSH,
        drill.PrivateScratchDualStageFault.AFTER_RELEASE,
    }
)


def _verified_scratch(root: Path, token: str) -> bool:
    """Reject anything except our empty, nonce-marked direct temp directory."""
    try:
        temporary = Path(tempfile.gettempdir()).resolve(strict=True)
        if (
            not root.is_absolute()
            or root.is_symlink()
            or root.resolve(strict=True).parent != temporary
            or not root.name.startswith(_PREFIX)
            or len(token) != 32
            or any(letter not in "0123456789abcdef" for letter in token)
        ):
            return False
        entries = tuple(root.iterdir())
        marker = root / _MARKER
        return (
            len(entries) == 1
            and entries[0] == marker
            and marker.is_file()
            and not marker.is_symlink()
            and marker.read_bytes() == (b"core238-3g58:" + token.encode("ascii"))
        )
    except (OSError, ValueError, UnicodeError):
        return False


def main() -> int:
    if sys.platform not in {"linux", "win32"} or len(sys.argv) != 4:
        return 2
    raw_root, token, name = sys.argv[1:]
    if name not in {item.value for item in _ALLOWED}:
        return 2
    root = Path(raw_root)
    if not _verified_scratch(root, token):
        return 2
    boundary = drill.PrivateScratchDualStageFault(name)

    @contextmanager
    def reserved_temporary_directory(*_args: object, **kwargs: object) -> Iterator[str]:
        if kwargs.get("prefix") != "core238_3g57_dual_stage_":
            raise RuntimeError("Unexpected scratch creation request")
        if not _verified_scratch(root, token):
            raise RuntimeError("Synthetic scratch reservation changed")
        yield str(root)

    def hard_exit(
        _selected: drill.PrivateScratchDualStageFault,
        point: drill.PrivateScratchDualStageFault,
    ) -> None:
        if point is boundary:
            os._exit(HARD_EXIT_CODE)

    # The test-only patch redirects the internally generated 3G57 temp root.
    # os._exit bypasses context-manager unwinding and closes the OS handles.
    with (
        patch.object(tempfile, "TemporaryDirectory", reserved_temporary_directory),
        patch.object(drill, "_inject", hard_exit),
    ):
        drill.rehearse_canonical_dual_stage_one_shot(boundary)
    # A returned result means the expected abrupt exit never happened.
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
