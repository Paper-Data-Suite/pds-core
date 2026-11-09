"""Test-only worker paused under a synthetic Core #238 transaction lock (3G59).

A parent process owns the nonce-marked, direct-child OS temporary directory.
No caller-provided teacher-private/workspace path is opened for mutation.
A separate test process must terminate this worker; the worker never self-exits
at the selected mutation point. No process or power-loss durability is claimed.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from pds_core import _teacher_private_recovery_scratch_dual_stage_attempt as drill

_PREFIX = "core238_3g59_parent_kill_"
_MARKER = ".core238-3g59-synthetic-only"
_READY = ".core238-3g59-held-boundary"
_ALLOWED = frozenset(
    {
        drill.PrivateScratchDualStageFault.AFTER_PREPARED,
        drill.PrivateScratchDualStageFault.AFTER_REGISTRY_REPLACE,
        drill.PrivateScratchDualStageFault.AFTER_DESCRIPTOR_REPLACE,
        drill.PrivateScratchDualStageFault.AFTER_DESCRIPTOR_FLUSH,
    }
)


def _valid_root(root: Path, token: str) -> bool:
    try:
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        if (
            not root.is_absolute()
            or root.is_symlink()
            or root.resolve(strict=True).parent != temp_root
            or not root.name.startswith(_PREFIX)
            or len(token) != 32
            or any(ch not in "0123456789abcdef" for ch in token)
        ):
            return False
        marker = root / _MARKER
        return (
            tuple(root.iterdir()) == (marker,)
            and marker.is_file()
            and not marker.is_symlink()
            and marker.read_bytes() == b"core238-3g59:" + token.encode("ascii")
        )
    except (OSError, UnicodeError, ValueError):
        return False


def main() -> int:
    if sys.platform not in {"win32", "linux"} or len(sys.argv) != 4:
        return 2
    root_raw, token, phase_raw = sys.argv[1:]
    if phase_raw not in {phase.value for phase in _ALLOWED}:
        return 2
    root = Path(root_raw)
    if not _valid_root(root, token):
        return 2
    selected = drill.PrivateScratchDualStageFault(phase_raw)

    @contextmanager
    def reserved_temp(*_args: object, **kwargs: object) -> Iterator[str]:
        if kwargs.get("prefix") != "core238_3g57_dual_stage_":
            raise RuntimeError("Unexpected synthetic temporary root request")
        if not _valid_root(root, token):
            raise RuntimeError("Synthetic scratch reservation changed")
        yield str(root)

    def pause_under_lock(
        _requested: drill.PrivateScratchDualStageFault,
        point: drill.PrivateScratchDualStageFault,
    ) -> None:
        if point is not selected:
            return
        # This callback is reached while the 3G57 operation lock, four parent
        # handles and both stage-file identity handles are retained.
        ready = root / _READY
        payload = (
            b"core238-3g59-held:"
            + token.encode("ascii")
            + b":"
            + point.value.encode("ascii")
        )
        with ready.open("xb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        # Parent must kill the worker externally; no context-manager unwind.
        threading.Event().wait(timeout=90)
        raise RuntimeError("Parent did not terminate the synthetic worker")

    with (
        patch.object(tempfile, "TemporaryDirectory", reserved_temp),
        patch.object(drill, "_inject", pause_under_lock),
    ):
        drill.rehearse_canonical_dual_stage_one_shot(selected)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
