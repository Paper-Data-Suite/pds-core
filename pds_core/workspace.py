"""Workspace root configuration and validation for Paper Data Suite."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_ROOT_ENV_VAR = "PDS_WORKSPACE_ROOT"
_WORKSPACE_MARKER = {"created_by": "pds-core", "workspace_version": 1}


class WorkspaceRootError(Exception):
    """Raised when workspace configuration or validation fails."""


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    """User-level Paper Data Suite workspace configuration."""

    workspace_root: Path | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceStatus:
    """Resolved workspace root and its non-mutating filesystem status."""

    root: Path
    source: str
    exists: bool
    is_dir: bool
    is_writable: bool
    config_path: Path
    default_root: Path


def _normalize_path(path: str | Path, *, description: str) -> Path:
    raw_path = os.fspath(path)
    if not raw_path.strip():
        raise WorkspaceRootError(f"{description} cannot be empty")

    expanded_path = os.path.expandvars(os.path.expanduser(raw_path))
    try:
        return Path(expanded_path).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceRootError(
            f"Could not resolve {description.lower()}: {raw_path!r}"
        ) from exc


def _normalize_workspace_root(path: str | Path) -> Path:
    root = _normalize_path(path, description="Workspace root")
    if root == Path(root.anchor):
        raise WorkspaceRootError(
            f"Workspace root cannot be a filesystem root: {root}"
        )
    return root


def _write_text_atomically(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def get_default_workspace_root() -> Path:
    """Return the default per-user Paper Data Suite workspace root."""
    return _normalize_workspace_root(Path.home() / "Paper Data Suite")


def get_workspace_config_path() -> Path:
    """Return the platform-specific user configuration file path."""
    home = Path.home()

    if sys.platform == "win32":
        config_dir = Path(
            os.environ.get("APPDATA", home / "AppData" / "Roaming")
        ) / "Paper Data Suite"
    elif sys.platform == "darwin":
        config_dir = home / "Library" / "Application Support" / "Paper Data Suite"
    else:
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        config_dir = (
            Path(xdg_config_home) if xdg_config_home else home / ".config"
        ) / "paper-data-suite"

    return _normalize_path(config_dir / "config.json", description="Config path")


def load_workspace_config() -> WorkspaceConfig:
    """Load the saved user workspace configuration."""
    config_path = get_workspace_config_path()
    if not config_path.exists():
        return WorkspaceConfig()

    try:
        with config_path.open(encoding="utf-8") as config_file:
            data: object = json.load(config_file)
    except json.JSONDecodeError as exc:
        raise WorkspaceRootError(
            f"Workspace config contains invalid JSON: {config_path}"
        ) from exc
    except OSError as exc:
        raise WorkspaceRootError(
            f"Could not read workspace config: {config_path}"
        ) from exc

    if not isinstance(data, dict):
        raise WorkspaceRootError(
            f"Workspace config must contain a JSON object: {config_path}"
        )

    workspace_root: object = data.get("workspace_root")
    if workspace_root is None:
        return WorkspaceConfig()
    if not isinstance(workspace_root, str):
        raise WorkspaceRootError(
            "Workspace config 'workspace_root' must be a string or null"
        )

    return WorkspaceConfig(
        workspace_root=_normalize_workspace_root(workspace_root)
    )


def save_workspace_root(path: str | Path) -> Path:
    """Save a workspace root in the user configuration and return it."""
    workspace_root = _normalize_workspace_root(path)
    config_path = get_workspace_config_path()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomically(
            config_path,
            json.dumps(
                {"workspace_root": str(workspace_root)},
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    except OSError as exc:
        raise WorkspaceRootError(
            f"Could not save workspace config: {config_path}"
        ) from exc

    return workspace_root


def clear_saved_workspace_root() -> bool:
    """Clear the saved workspace-root configuration."""
    config_path = get_workspace_config_path()

    try:
        config_path.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise WorkspaceRootError(
            f"Could not clear workspace config: {config_path}"
        ) from exc

    return True


def _resolve_workspace_root_with_source(
    explicit_root: str | Path | None = None,
) -> tuple[Path, str]:
    if explicit_root is not None:
        return _normalize_workspace_root(explicit_root), "explicit"

    environment_root = os.environ.get(WORKSPACE_ROOT_ENV_VAR)
    if environment_root is not None:
        return _normalize_workspace_root(environment_root), "environment"

    saved_root = load_workspace_config().workspace_root
    if saved_root is not None:
        return saved_root, "saved_config"

    return get_default_workspace_root(), "default"


def _is_workspace_root_writable(root: Path, *, exists: bool, is_dir: bool) -> bool:
    try:
        if exists:
            return is_dir and os.access(root, os.W_OK)

        candidate = root.parent
        while not candidate.exists():
            parent = candidate.parent
            if parent == candidate:
                return False
            candidate = parent
        return candidate.is_dir() and os.access(candidate, os.W_OK)
    except OSError:
        return False


def resolve_workspace_root(
    explicit_root: str | Path | None = None,
) -> Path:
    """Resolve the workspace root without creating it or changing config."""
    root, _source = _resolve_workspace_root_with_source(explicit_root)
    return root


def inspect_workspace_root(
    explicit_root: str | Path | None = None,
) -> WorkspaceStatus:
    """Inspect the resolved workspace root without changing the filesystem."""
    root, source = _resolve_workspace_root_with_source(explicit_root)
    config_path = get_workspace_config_path()
    default_root = get_default_workspace_root()

    try:
        exists = root.exists()
        is_dir = root.is_dir() if exists else False
    except OSError:
        exists = False
        is_dir = False

    return WorkspaceStatus(
        root=root,
        source=source,
        exists=exists,
        is_dir=is_dir,
        is_writable=_is_workspace_root_writable(
            root,
            exists=exists,
            is_dir=is_dir,
        ),
        config_path=config_path,
        default_root=default_root,
    )


def ensure_workspace_root(
    path: str | Path,
    create: bool = True,
) -> Path:
    """Validate a workspace root, creating it and its metadata when requested."""
    workspace_root = _normalize_workspace_root(path)

    if workspace_root.exists() and not workspace_root.is_dir():
        raise WorkspaceRootError(
            f"Workspace root exists but is not a directory: {workspace_root}"
        )
    if not workspace_root.exists():
        if not create:
            raise WorkspaceRootError(
                f"Workspace root does not exist: {workspace_root}"
            )
        try:
            workspace_root.mkdir(parents=True)
        except OSError as exc:
            raise WorkspaceRootError(
                f"Could not create workspace root: {workspace_root}"
            ) from exc

    write_test_descriptor: int | None = None
    write_test_path: Path | None = None
    try:
        write_test_descriptor, raw_write_test_path = tempfile.mkstemp(
            dir=workspace_root,
            prefix=".pds_write_test.",
            suffix=".tmp",
        )
        write_test_path = Path(raw_write_test_path)
        os.close(write_test_descriptor)
        write_test_descriptor = None
        write_test_path.unlink()
    except OSError as exc:
        raise WorkspaceRootError(
            f"Workspace root is not writable: {workspace_root}"
        ) from exc
    finally:
        if write_test_descriptor is not None:
            try:
                os.close(write_test_descriptor)
            except OSError:
                pass
        if write_test_path is not None:
            try:
                write_test_path.unlink(missing_ok=True)
            except OSError:
                pass

    if create:
        metadata_dir = workspace_root / ".pds"
        marker_path = metadata_dir / "workspace.json"
        try:
            metadata_dir.mkdir(exist_ok=True)
            _write_text_atomically(
                marker_path,
                json.dumps(_WORKSPACE_MARKER, indent=2, sort_keys=True) + "\n",
            )
        except OSError as exc:
            raise WorkspaceRootError(
                f"Could not create workspace metadata: {metadata_dir}"
            ) from exc

    return workspace_root
