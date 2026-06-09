"""Tests for shared scan inbox and archive route helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pds_core.scan_routes import (
    ScanRouteError,
    scans_archive_date_dir,
    scans_archive_dir,
    scans_inbox_dir,
)


def test_scans_inbox_dir_accepts_string_root() -> None:
    assert scans_inbox_dir("paper_data") == Path("paper_data") / "scans_inbox"


def test_scans_inbox_dir_accepts_path_root() -> None:
    assert scans_inbox_dir(Path("paper_data")) == Path("paper_data") / "scans_inbox"


def test_scans_archive_dir_accepts_string_root() -> None:
    assert scans_archive_dir("paper_data") == Path("paper_data") / "scans_archive"


def test_scans_archive_dir_accepts_path_root() -> None:
    assert scans_archive_dir(Path("paper_data")) == Path("paper_data") / "scans_archive"


def test_scans_archive_date_dir_accepts_date() -> None:
    assert scans_archive_date_dir("paper_data", date(2026, 6, 8)) == (
        Path("paper_data") / "scans_archive" / "2026-06-08"
    )


def test_scans_archive_date_dir_accepts_strict_iso_date_string() -> None:
    assert scans_archive_date_dir("paper_data", "2026-06-08") == (
        Path("paper_data") / "scans_archive" / "2026-06-08"
    )


def test_scans_archive_date_dir_accepts_path_root() -> None:
    assert scans_archive_date_dir(Path("paper_data"), "2026-06-08") == (
        Path("paper_data") / "scans_archive" / "2026-06-08"
    )


@pytest.mark.parametrize(
    "archive_date",
    [
        "06-08-2026",
        "2026/06/08",
        "June 8, 2026",
        "2026-6-8",
        "../2026-06-08",
        "2026-06-08/archive",
        " 2026-06-08",
        "2026-06-08 ",
        "2026-02-30",
        "",
    ],
)
def test_scans_archive_date_dir_rejects_invalid_date_strings(
    archive_date: str,
) -> None:
    with pytest.raises(ScanRouteError):
        scans_archive_date_dir("paper_data", archive_date)


@pytest.mark.parametrize("archive_date", [None, 20260608, 1.5, True])
def test_scans_archive_date_dir_rejects_invalid_date_types(
    archive_date: object,
) -> None:
    with pytest.raises(ScanRouteError, match="archive_date must be a date"):
        scans_archive_date_dir(
            "paper_data",
            archive_date,  # type: ignore[arg-type]
        )


def test_scan_route_helpers_do_not_create_directories(tmp_path: Path) -> None:
    inbox = scans_inbox_dir(tmp_path)
    archive = scans_archive_dir(tmp_path)
    date_archive = scans_archive_date_dir(tmp_path, "2026-06-08")

    assert inbox == tmp_path / "scans_inbox"
    assert archive == tmp_path / "scans_archive"
    assert date_archive == tmp_path / "scans_archive" / "2026-06-08"

    assert not inbox.exists()
    assert not archive.exists()
    assert not date_archive.exists()