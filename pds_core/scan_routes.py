"""Shared scan inbox and archive route helpers for Paper Data Suite."""

from __future__ import annotations

from datetime import date

from pathlib import Path


class ScanRouteError(ValueError):
    """Raised when a scan route value is invalid."""


def scans_inbox_dir(root: str | Path) -> Path:
    """Return the shared raw scan inbox directory."""
    return Path(root) / "scans_inbox"


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