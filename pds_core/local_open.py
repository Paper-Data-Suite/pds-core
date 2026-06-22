"""Open local filesystem paths with the system's default application."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


class LocalOpenError(Exception):
    """Raised when a local path cannot be opened safely."""


def _open_on_windows(path: Path) -> None:
    """Open *path* using the Windows shell."""
    os.startfile(path)


def open_local_path(path: str | Path) -> Path:
    """Open an existing local file or directory in the system default viewer."""
    if isinstance(path, str):
        if not path.strip():
            raise LocalOpenError("Local path must not be empty.")
        if path.strip().lower().startswith(("http://", "https://", "file://")):
            raise LocalOpenError("URLs cannot be opened as local paths.")

    resolved_path = Path(path).resolve(strict=False)

    if not resolved_path.exists():
        raise LocalOpenError(f"Local path does not exist: {resolved_path}")
    if not (resolved_path.is_file() or resolved_path.is_dir()):
        raise LocalOpenError(
            f"Local path is neither a file nor a directory: {resolved_path}"
        )

    try:
        if sys.platform == "win32":
            _open_on_windows(resolved_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(resolved_path)], check=True)
        else:
            subprocess.run(["xdg-open", str(resolved_path)], check=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise LocalOpenError(
            f"Could not open local path with the system viewer: {resolved_path}"
        ) from error

    return resolved_path
