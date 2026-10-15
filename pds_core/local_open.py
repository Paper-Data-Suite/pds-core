"""Open existing local files and folders with their default operating-system app.

On Windows, deeply nested paths can be readable by Python but inaccessible to
an external PDF/HTML viewer. A short, per-user junction is used for that shell
handoff without modifying or copying authoritative source files.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid


class LocalOpenError(Exception):
    """A local open request cannot be submitted safely."""


# Conservative path budget for legacy shell/file-URL consumers. This is a
# handoff threshold, NOT a universal Windows filesystem limit.
_WINDOWS_VIEWER_SAFE_PATH_UNITS = 240
_WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS = 30 * 24 * 60 * 60
_ALIAS_PATTERN = re.compile(r"v_[0-9a-f]{32}\Z")
_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _windows_path_units(path: Path) -> int:
    """Measure Windows WCHARs, not Unicode code points."""
    return len(str(path).encode("utf-16-le")) // 2


def _is_reparse_point(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE
    )


def _viewer_alias_root() -> Path:
    """Prepare an inherited-user-ACL directory outside canonical PDS storage."""
    raw = os.environ.get("LOCALAPPDATA")
    if not raw:
        raise LocalOpenError("Windows user-local application data is unavailable.")
    local = Path(raw).resolve(strict=True)
    if not local.is_dir():
        raise LocalOpenError("Windows user-local application data is invalid.")
    app_dir = local / "PaperDataSuite"
    alias_dir = app_dir / "viewer-aliases-v1"
    for directory in (app_dir, alias_dir):
        directory.mkdir(mode=0o700, exist_ok=True)
        if _is_reparse_point(directory) or not directory.is_dir():
            raise LocalOpenError("Viewer alias directory is not a real directory.")
    return alias_dir


def _remove_viewer_junction(link: Path) -> None:
    """Remove only the link, NEVER recursively visit its target directory."""
    if not _is_reparse_point(link):
        raise LocalOpenError("Viewer alias is no longer a link.")
    if sys.platform == "win32":
        # Windows uses RemoveDirectoryW to remove directory junctions.
        link.rmdir()
    else:
        link.unlink()


def _prune_stale_aliases(root: Path) -> None:
    """Best-effort eventual cleanup; never remove recent/in-use aliases."""
    cutoff = time.time() - _WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS
    try:
        for entry in root.iterdir():
            if not _ALIAS_PATTERN.fullmatch(entry.name):
                continue
            try:
                if entry.lstat().st_mtime >= cutoff:
                    continue
                if not _is_reparse_point(entry):
                    continue
                _remove_viewer_junction(entry)
            except (OSError, LocalOpenError):
                # Cleanup is auxiliary; a viewer or security policy may still
                # require an alias. Never block opening an unrelated file.
                continue
    except OSError:
        # Do not turn optional cleanup into loss of access.
        return


def _create_windows_junction(link: Path, target_dir: Path) -> None:
    """Create one Windows junction without shell interpolation of source names.

    Windows PowerShell's built-in Junction item type does not require an admin
    session (qualified on a real Windows pilot). Inputs go through process
    environment variables, not PowerShell command strings.
    """
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "New-Item -ItemType Junction "
        "-Path $env:PDS_CORE_VIEWER_LINK "
        "-Target $env:PDS_CORE_VIEWER_TARGET "
        "-ErrorAction Stop | Out-Null"
    )
    env = os.environ.copy()
    env["PDS_CORE_VIEWER_LINK"] = str(link)
    env["PDS_CORE_VIEWER_TARGET"] = str(target_dir)
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=20,
    )


def _prepare_windows_viewer_alias(canonical: Path) -> Path:
    """Return a short lexical alias to the *same* file or folder.

    The alias must not be passed through Path.resolve() before shell launch.
    A successful caller retains the junction until later stale cleanup: the
    receiving viewer may be asynchronous and open the file after this returns.
    """
    root = _viewer_alias_root()
    _prune_stale_aliases(root)
    target_dir = canonical.parent if canonical.is_file() else canonical
    link = root / ("v_" + uuid.uuid4().hex)
    alias = link / canonical.name if canonical.is_file() else link

    if _windows_path_units(alias) > _WINDOWS_VIEWER_SAFE_PATH_UNITS:
        raise LocalOpenError(
            "A short Windows viewer path cannot be constructed for this target."
        )
    if os.path.lexists(link):
        # lexists detects dangling reparse points that Path.exists() may miss.
        raise LocalOpenError("Windows viewer alias name unexpectedly exists.")

    try:
        _create_windows_junction(link, target_dir)
        # Verify link target and final file identity before the handoff. This
        # must be checked without losing the lexical alias for the viewer.
        if not _is_reparse_point(link):
            raise LocalOpenError("Windows viewer alias was not a junction.")
        if not alias.exists() or not os.path.samefile(alias, canonical):
            raise LocalOpenError("Windows viewer alias did not match the source.")
    except Exception as error:
        # If junction creation succeeded partially, remove only the alias.
        try:
            if _is_reparse_point(link):
                _remove_viewer_junction(link)
        except (OSError, LocalOpenError):
            pass
        if isinstance(error, LocalOpenError):
            raise
        if isinstance(error, (OSError, RuntimeError, subprocess.SubprocessError)):
            raise LocalOpenError(
                "Could not prepare the Windows viewer-safe path."
            ) from error
        raise
    return alias


def _open_on_windows(path: Path) -> None:
    """Request a Windows shell handoff without claiming the viewer rendered."""
    if sys.platform != "win32":
        raise OSError("Windows shell opener is unavailable on this platform.")
    handoff = path
    if _windows_path_units(path) > _WINDOWS_VIEWER_SAFE_PATH_UNITS:
        handoff = _prepare_windows_viewer_alias(path)
    # IMPORTANT: do not resolve handoff. That expands the junction back into the
    # original long source path and reintroduces the external viewer failure.
    try:
        os.startfile(handoff)
    except (OSError, RuntimeError):
        # The shell rejected the request synchronously, so no asynchronous
        # viewer needs this newly created alias. Remove only the junction.
        # A launched viewer's alias is deliberately retained instead.
        if handoff != path:
            link = handoff.parent if path.is_file() else handoff
            try:
                _remove_viewer_junction(link)
            except (OSError, LocalOpenError):
                pass
        raise


def open_local_path(path: str | Path) -> Path:
    """Submit a launch request for an existing local file or directory.

    Returns the canonical source path, not a temporary alias. Successful return
    means the operating system accepted the launch request; it cannot establish
    that an asynchronous external application displayed the file.
    """
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
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise LocalOpenError(
            "Could not request local path opening with the system viewer: "
            f"{resolved_path}"
        ) from error
    return resolved_path
