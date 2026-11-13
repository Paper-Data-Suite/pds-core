"""Disposable second-generation recovery lock worker for Core #238 3G60.

Only accepts a nonce-marked Core 3G59 scratch directory under the OS temp root.
Read-only canonical inspection; the optional handshake marker is scratch-only.
No teacher workspace, Notes, production mutation, replay, or commit authority.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import (
    _teacher_private_recovery_canonical_native_parent_restart as parents,
)
from pds_core import _teacher_private_recovery_journaled_restart_drill as restart

_PREFIX = "core238_3g59_parent_kill_"
_RESERVATION = ".core238-3g59-synthetic-only"
_READY = ".core238-3g60-recovery-held"
_MODES = frozenset({"hold", "probe", "inspect"})


def _valid_root(root: Path, token: str) -> bool:
    try:
        system_temp = Path(tempfile.gettempdir()).resolve(strict=True)
        if (
            not root.is_absolute()
            or root.is_symlink()
            or root.resolve(strict=True).parent != system_temp
            or not root.name.startswith(_PREFIX)
            or len(token) != 32
            or any(ch not in "0123456789abcdef" for ch in token)
        ):
            return False
        marker = root / _RESERVATION
        private = root / "private"
        workspace = root / "workspace"
        journal = canonical._paths(private, workspace / ".pds")[4]
        if any(
            path.is_symlink()
            for path in (marker, private, workspace, workspace / ".pds", journal)
        ):
            return False
        return (
            marker.is_file()
            and marker.read_bytes() == b"core238-3g59:" + token.encode("ascii")
            and private.is_dir()
            and (private / ".native-lock").is_file()
            and journal.is_file()
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


def main() -> int:
    if sys.platform not in {"win32", "linux"} or len(sys.argv) != 4:
        return 2
    root_string, token, mode = sys.argv[1:]
    root = Path(root_string)
    if mode not in _MODES or not _valid_root(root, token):
        return 2
    private = root / "private"
    association = root / "workspace" / ".pds"
    checked = canonical._canonical_fork_intent()
    try:
        with restart._held_existing_restart_lock(private / ".native-lock"):
            with parents._hold_four_parents(
                parents._parent_roots(private, association)
            ) as retained:
                parents._require_held(retained)
                checkpoint = canonical._checkpoint(private, association, checked)
                parents._require_held(retained)
                if mode == "hold":
                    # A temporary handshake in the *disposable root*, not metadata.
                    ready = root / _READY
                    with ready.open("xb") as output:
                        output.write(
                            b"core238-3g60-recovery-held:"
                            + token.encode("ascii")
                            + b":"
                            + checkpoint.value.encode("ascii")
                        )
                        output.flush()
                        os.fsync(output.fileno())
                    # The parent must kill the process; no normal guard unwind.
                    threading.Event().wait(timeout=90)
                    return 6
                if mode == "probe":
                    # A probe getting this far is an unexpected admission.
                    return 5
                # Binary pipe output avoids CRLF translation on Windows.
                sys.stdout.buffer.write((checkpoint.value + "\n").encode("ascii"))
                sys.stdout.buffer.flush()
                return 0
    except restart._RestartGuardRefused:
        return 3
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
