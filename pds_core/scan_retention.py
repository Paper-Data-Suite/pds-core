"""Safe retained-source copying and provenance for active scans."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import BinaryIO, Final, Protocol

from pds_core.scan_routes import (
    ScanRouteError,
    build_retained_source_filename,
    retained_source_scan_path,
)


_COPY_BUFFER_SIZE: Final[int] = 1024 * 1024


class _Digest(Protocol):
    def update(self, data: bytes, /) -> None: ...


class SourceRetentionError(RuntimeError):
    """Raised when a source scan cannot be retained safely."""


@dataclass(frozen=True, slots=True)
class RetainedSourceScan:
    """Provenance for one retained source-scan intake event."""

    source_scan_id: str
    source_filename: str
    source_sha256: str
    retained_source_path: Path
    retained_source_relative_path: str
    intake_timestamp: datetime
    intake_date: date


def retain_source_scan(
    root: str | Path,
    source_file_path: str | Path,
    *,
    intake_timestamp: datetime | None = None,
    intake_date: date | str | None = None,
) -> RetainedSourceScan:
    """Copy one source scan safely into the active retained-source store."""
    workspace_root = _resolved_workspace_root(root)
    source_path = _readable_regular_file(source_file_path)
    timestamp = _normalize_intake_timestamp(intake_timestamp)

    try:
        source_sha256 = _sha256_file(source_path)
        retained_filename = build_retained_source_filename(
            intake_timestamp=timestamp,
            original_filename=source_path.name,
            sha256_hex=source_sha256,
        )
        route_date = intake_date if intake_date is not None else timestamp.date()
        retained_path = retained_source_scan_path(
            workspace_root,
            intake_date=route_date,
            retained_filename=retained_filename,
        )
    except (OSError, ScanRouteError, ValueError) as error:
        raise SourceRetentionError(f"Cannot prepare retained source: {error}") from error

    _require_contained(workspace_root, retained_path, "retained source path")
    try:
        retained_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SourceRetentionError(
            f"Cannot create retained source directory: {error}"
        ) from error
    _require_contained(
        workspace_root,
        retained_path.parent,
        "retained source directory",
    )

    try:
        copied_sha256 = _copy_exclusive_with_sha256(source_path, retained_path)
    except FileExistsError as error:
        raise SourceRetentionError(
            f"Retained source already exists: {retained_path}"
        ) from error
    except OSError as error:
        _remove_incomplete_copy(retained_path)
        raise SourceRetentionError(f"Cannot copy retained source: {error}") from error

    if copied_sha256 != source_sha256:
        _remove_incomplete_copy(retained_path)
        raise SourceRetentionError(
            "Source changed during retention; the incomplete retained copy was removed."
        )

    relative_path = _workspace_relative(workspace_root, retained_path)
    normalized_date = retained_path.parent.name
    return RetainedSourceScan(
        source_scan_id=f"scan_{retained_path.stem}",
        source_filename=source_path.name,
        source_sha256=source_sha256,
        retained_source_path=retained_path,
        retained_source_relative_path=relative_path,
        intake_timestamp=timestamp,
        intake_date=date.fromisoformat(normalized_date),
    )


def _resolved_workspace_root(root: str | Path) -> Path:
    try:
        resolved = Path(root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceRetentionError(f"Workspace root is invalid or missing: {error}") from error
    if not resolved.is_dir():
        raise SourceRetentionError(f"Workspace root is not a directory: {resolved}")
    return resolved


def _readable_regular_file(source_file_path: str | Path) -> Path:
    try:
        source = Path(source_file_path)
        if not source.exists():
            raise SourceRetentionError(f"Source file does not exist: {source}")
        if not source.is_file():
            raise SourceRetentionError(f"Source path is not a regular file: {source}")
        if not os.access(source, os.R_OK):
            raise SourceRetentionError(f"Source file is not readable: {source}")
        return source
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceRetentionError(f"Cannot validate source file: {error}") from error


def _normalize_intake_timestamp(value: datetime | None) -> datetime:
    timestamp = datetime.now(timezone.utc) if value is None else value
    if not isinstance(timestamp, datetime):
        raise SourceRetentionError("intake_timestamp must be a datetime.")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise SourceRetentionError("intake_timestamp must be timezone-aware.")
    return timestamp.astimezone(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(_COPY_BUFFER_SIZE), b""):
                digest.update(chunk)
    except OSError as error:
        raise SourceRetentionError(f"Cannot read source file: {error}") from error
    return digest.hexdigest()


def _copy_exclusive_with_sha256(source_path: Path, destination_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as source, destination_path.open("xb") as destination:
        _copy_and_hash(source, destination, digest)
    return digest.hexdigest()


def _copy_and_hash(
    source: BinaryIO,
    destination: BinaryIO,
    digest: _Digest,
) -> None:
    for chunk in iter(lambda: source.read(_COPY_BUFFER_SIZE), b""):
        destination.write(chunk)
        digest.update(chunk)


def _require_contained(root: Path, path: Path, description: str) -> None:
    try:
        path.resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise SourceRetentionError(
            f"Unsafe {description}; it must remain under the workspace root."
        ) from error


def _workspace_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        _remove_incomplete_copy(path)
        raise SourceRetentionError(
            "Retained source path is not safely relative to the workspace root."
        ) from error


def _remove_incomplete_copy(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
