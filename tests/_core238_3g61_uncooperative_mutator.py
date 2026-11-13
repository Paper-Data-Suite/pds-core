"""3G61 disposable uncooperative writer; deliberately does not take a recovery lock.

Only one nonce-marked native Core test root, directly under the OS temp root,
can be touched. Never accepts arbitrary paths, bytes, names or production data.
The worker is not imported by production modules and has no Notes privileges.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical

_PREFIX = "core238_3g59_parent_kill_"
_MARKER = ".core238-3g59-synthetic-only"
_MODES = frozenset({"journal", "registry", "descriptor", "namespace"})
_CORRUPTION = b"core238-3g61-conflicting-synthetic-image\n"
_EXTRA = ".core238-3g61-unexpected-registry-stage"


def _valid_root(root: Path, token: str) -> bool:
    try:
        temp = Path(tempfile.gettempdir()).resolve(strict=True)
        if (
            not root.is_absolute()
            or root.is_symlink()
            or root.resolve(strict=True).parent != temp
            or not root.name.startswith(_PREFIX)
            or len(token) != 32
            or any(character not in "0123456789abcdef" for character in token)
        ):
            return False
        marker = root / _MARKER
        private = root / "private"
        workspace = root / "workspace"
        association = workspace / ".pds"
        journal = canonical._paths(private, association)[4]
        roots = (root, private, workspace, association, private / "transactions")
        if any(path.is_symlink() or not path.is_dir() for path in roots):
            return False
        if marker.is_symlink() or journal.is_symlink():
            return False
        return (
            marker.is_file()
            and marker.read_bytes() == b"core238-3g59:" + token.encode("ascii")
            and journal.is_file()
            and (private / ".native-lock").is_file()
        )
    except (OSError, ValueError, TypeError, UnicodeError):
        return False


def _corrupt_image(path: Path) -> bool:
    """Alter only an existing regular scratch image, preserving its inode."""
    descriptor: int | None = None
    try:
        if path.is_symlink() or not path.is_file():
            return False
        flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        at_path = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (at_path.st_dev, at_path.st_ino)
            or not (0 < opened.st_size <= 65536)
        ):
            return False
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, _CORRUPTION)
        os.ftruncate(descriptor, len(_CORRUPTION))
        os.fsync(descriptor)
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main() -> int:
    if sys.platform not in {"win32", "linux"} or len(sys.argv) != 4:
        return 2
    root_raw, token, mode = sys.argv[1:]
    root = Path(root_raw)
    if mode not in _MODES or not _valid_root(root, token):
        return 2
    private = root / "private"
    association = root / "workspace" / ".pds"
    registry, _, descriptor, _, journal = canonical._paths(private, association)
    if mode == "namespace":
        destination = private / _EXTRA
        if destination.is_symlink() or destination.exists():
            return 4
        try:
            with destination.open("xb") as stream:
                stream.write(_CORRUPTION)
                stream.flush()
                os.fsync(stream.fileno())
            return 0
        except (OSError, ValueError, TypeError):
            return 4
    target = {"journal": journal, "registry": registry, "descriptor": descriptor}[mode]
    return 0 if _corrupt_image(target) else 4


if __name__ == "__main__":
    raise SystemExit(main())
