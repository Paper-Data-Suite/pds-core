"""Shared active and legacy scan route helpers for Paper Data Suite."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Final


_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Fa-f]{64}$")
_UNSAFE_STEM_RUN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[^A-Za-z0-9_-]+"
)
_SAFE_RETAINED_FILENAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_.-]+$"
)
_SAFE_SCAN_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".jpeg", ".jpg", ".pdf", ".png", ".tif", ".tiff"}
)
_DIGEST_PREFIX_LENGTH: Final[int] = 12


class ScanRouteError(ValueError):
    """Raised when a scan route value is invalid."""


def scans_inbox_dir(root: str | Path) -> Path:
    """Return the shared raw scan inbox directory."""
    return Path(root) / "scans_inbox"


def scans_root_dir(root: str | Path) -> Path:
    """Return the shared active scan directory."""
    return Path(root) / "scans"


def scans_source_dir(root: str | Path) -> Path:
    """Return the active retained source scan directory."""
    return scans_root_dir(root) / "source"


def scans_source_date_dir(root: str | Path, source_date: date | str) -> Path:
    """Return a date-bucketed active retained source scan directory."""
    date_bucket = _normalize_source_date(source_date)
    return scans_source_dir(root) / date_bucket


def routing_review_dir(root: str | Path) -> Path:
    """Return the shared active scan routing review directory."""
    return scans_root_dir(root) / "review"


def build_retained_source_filename(
    *,
    intake_timestamp: datetime,
    original_filename: str,
    sha256_hex: str,
) -> str:
    """Build a collision-resistant filename for an active retained scan."""
    if not isinstance(intake_timestamp, datetime):
        raise ScanRouteError("intake_timestamp must be a datetime.")
    if (
        intake_timestamp.tzinfo is None
        or intake_timestamp.utcoffset() is None
    ):
        raise ScanRouteError("intake_timestamp must be timezone-aware.")

    original_path = _validate_filename_only(
        original_filename,
        "original_filename",
    )
    extension = original_path.suffix.lower()
    if extension not in _SAFE_SCAN_EXTENSIONS:
        allowed = ", ".join(sorted(_SAFE_SCAN_EXTENSIONS))
        raise ScanRouteError(
            f"original_filename must use a supported scan extension: {allowed}."
        )

    stem = _UNSAFE_STEM_RUN_PATTERN.sub("_", original_path.stem).strip("_")
    if stem == "":
        stem = "scan"

    if not isinstance(sha256_hex, str) or not _SHA256_PATTERN.fullmatch(
        sha256_hex
    ):
        raise ScanRouteError(
            "sha256_hex must be a full 64-character SHA-256 hexadecimal string."
        )

    utc_timestamp = intake_timestamp.astimezone(timezone.utc)
    timestamp_component = utc_timestamp.strftime("%Y%m%dT%H%M%S%fZ")
    digest_prefix = sha256_hex[:_DIGEST_PREFIX_LENGTH].lower()
    return f"{timestamp_component}__{stem}__{digest_prefix}{extension}"


def retained_source_scan_path(
    root: str | Path,
    *,
    intake_date: date | str,
    retained_filename: str,
) -> Path:
    """Return the active source path for an already-built retained filename."""
    filename = _validate_retained_filename(retained_filename)
    return scans_source_date_dir(root, intake_date) / filename


def scans_archive_dir(root: str | Path) -> Path:
    """Return the shared raw scan archive directory."""
    return Path(root) / "scans_archive"


def scans_archive_date_dir(root: str | Path, archive_date: date | str) -> Path:
    """Return a date-bucketed raw scan archive directory."""
    date_bucket = _normalize_archive_date(archive_date)
    return scans_archive_dir(root) / date_bucket


def _normalize_archive_date(archive_date: date | str) -> str:
    """Normalize a date or strict ISO date string to YYYY-MM-DD."""
    if isinstance(archive_date, date):
        return archive_date.isoformat()

    if not isinstance(archive_date, str):
        raise ScanRouteError("archive_date must be a date or ISO date string.")

    if archive_date != archive_date.strip():
        raise ScanRouteError("archive_date must not contain leading or trailing whitespace.")

    try:
        parsed_date = date.fromisoformat(archive_date)
    except ValueError as error:
        raise ScanRouteError(
            "archive_date must be a valid ISO date string in YYYY-MM-DD format."
        ) from error

    if archive_date != parsed_date.isoformat():
        raise ScanRouteError(
            "archive_date must be a strict ISO date string in YYYY-MM-DD format."
        )

    return archive_date


def _normalize_source_date(source_date: date | str) -> str:
    """Normalize a date or strict ISO date string to YYYY-MM-DD."""
    if isinstance(source_date, datetime):
        raise ScanRouteError("source_date must be a date or ISO date string.")

    if isinstance(source_date, date):
        return source_date.isoformat()

    if not isinstance(source_date, str):
        raise ScanRouteError("source_date must be a date or ISO date string.")

    if source_date != source_date.strip():
        raise ScanRouteError(
            "source_date must not contain leading or trailing whitespace."
        )

    try:
        parsed_date = date.fromisoformat(source_date)
    except ValueError as error:
        raise ScanRouteError(
            "source_date must be a valid ISO date string in YYYY-MM-DD format."
        ) from error

    if source_date != parsed_date.isoformat():
        raise ScanRouteError(
            "source_date must be a strict ISO date string in YYYY-MM-DD format."
        )

    return source_date


def _validate_filename_only(value: object, field_name: str) -> Path:
    if not isinstance(value, str):
        raise ScanRouteError(f"{field_name} must be a string.")
    if value == "":
        raise ScanRouteError(f"{field_name} must not be empty.")
    if value != value.strip():
        raise ScanRouteError(
            f"{field_name} must not contain leading or trailing whitespace."
        )
    if (
        "\x00" in value
        or "/" in value
        or "\\" in value
        or PureWindowsPath(value).drive
    ):
        raise ScanRouteError(f"{field_name} must be a filename, not a path.")
    if value in {".", ".."}:
        raise ScanRouteError(f"{field_name} must be a safe filename.")
    return Path(value)


def _validate_retained_filename(retained_filename: object) -> str:
    filename_path = _validate_filename_only(
        retained_filename,
        "retained_filename",
    )
    assert isinstance(retained_filename, str)
    if not _SAFE_RETAINED_FILENAME_PATTERN.fullmatch(retained_filename):
        raise ScanRouteError(
            "retained_filename contains unsafe filename characters."
        )
    if filename_path.suffix.lower() not in _SAFE_SCAN_EXTENSIONS:
        raise ScanRouteError(
            "retained_filename must use a supported scan extension."
        )
    return retained_filename
