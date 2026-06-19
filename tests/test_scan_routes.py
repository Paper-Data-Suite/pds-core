"""Tests for shared active and legacy scan route helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pds_core.scan_routes import (
    ScanRouteError,
    build_retained_source_filename,
    retained_source_scan_path,
    routing_review_dir,
    scans_archive_date_dir,
    scans_archive_dir,
    scans_inbox_dir,
    scans_root_dir,
    scans_source_date_dir,
    scans_source_dir,
)


def test_scans_inbox_dir_accepts_string_root() -> None:
    assert scans_inbox_dir("paper_data") == Path("paper_data") / "scans_inbox"


def test_scans_inbox_dir_accepts_path_root() -> None:
    assert scans_inbox_dir(Path("paper_data")) == Path("paper_data") / "scans_inbox"


def test_active_scan_directories_use_shared_layout() -> None:
    root = Path("paper_data")

    assert scans_root_dir(root) == root / "scans"
    assert scans_source_dir(root) == root / "scans" / "source"
    assert routing_review_dir(root) == root / "scans" / "review"


@pytest.mark.parametrize(
    ("source_date", "expected"),
    [
        (date(2026, 6, 19), "2026-06-19"),
        ("2026-06-19", "2026-06-19"),
    ],
)
def test_scans_source_date_dir_accepts_strict_dates(
    source_date: date | str,
    expected: str,
) -> None:
    assert scans_source_date_dir("paper_data", source_date) == (
        Path("paper_data") / "scans" / "source" / expected
    )


@pytest.mark.parametrize(
    "source_date",
    [
        "06-19-2026",
        "2026/06/19",
        "2026-6-19",
        "../2026-06-19",
        "2026-06-19/source",
        " 2026-06-19",
        "2026-06-19 ",
        "2026-02-30",
        "",
    ],
)
def test_scans_source_date_dir_rejects_invalid_date_strings(
    source_date: str,
) -> None:
    with pytest.raises(ScanRouteError):
        scans_source_date_dir("paper_data", source_date)


@pytest.mark.parametrize(
    "source_date",
    [None, 20260619, 1.5, True, datetime(2026, 6, 19)],
)
def test_scans_source_date_dir_rejects_invalid_date_types(
    source_date: object,
) -> None:
    with pytest.raises(ScanRouteError, match="source_date must be a date"):
        scans_source_date_dir(
            "paper_data",
            source_date,  # type: ignore[arg-type]
        )


def test_build_retained_source_filename_uses_utc_and_safe_components() -> None:
    timestamp = datetime(
        2026,
        6,
        19,
        14,
        45,
        12,
        123456,
        tzinfo=timezone(timedelta(hours=-4)),
    )

    filename = build_retained_source_filename(
        intake_timestamp=timestamp,
        original_filename="scanner export.PDF",
        sha256_hex="A1B2C3D4E5F6" + ("0" * 52),
    )

    assert filename == (
        "20260619T184512123456Z__scanner_export__a1b2c3d4e5f6.pdf"
    )


def test_build_retained_source_filename_falls_back_for_empty_safe_stem() -> None:
    filename = build_retained_source_filename(
        intake_timestamp=datetime(2026, 6, 19, tzinfo=timezone.utc),
        original_filename="@@@.pdf",
        sha256_hex="a" * 64,
    )

    assert filename == "20260619T000000000000Z__scan__aaaaaaaaaaaa.pdf"


@pytest.mark.parametrize(
    "original_filename",
    [
        "../scan.pdf",
        r"folder\scan.pdf",
        "C:scan.pdf",
        "/scan.pdf",
        "scan.exe",
        "scan",
        " scan.pdf",
    ],
)
def test_build_retained_source_filename_rejects_unsafe_names(
    original_filename: str,
) -> None:
    with pytest.raises(ScanRouteError):
        build_retained_source_filename(
            intake_timestamp=datetime(2026, 6, 19, tzinfo=timezone.utc),
            original_filename=original_filename,
            sha256_hex="a" * 64,
        )


def test_build_retained_source_filename_rejects_naive_timestamp() -> None:
    with pytest.raises(ScanRouteError, match="timezone-aware"):
        build_retained_source_filename(
            intake_timestamp=datetime(2026, 6, 19),
            original_filename="scan.pdf",
            sha256_hex="a" * 64,
        )


@pytest.mark.parametrize("sha256_hex", ["a" * 63, "g" * 64, "", 123])
def test_build_retained_source_filename_rejects_invalid_sha256(
    sha256_hex: object,
) -> None:
    with pytest.raises(ScanRouteError, match="64-character"):
        build_retained_source_filename(
            intake_timestamp=datetime(2026, 6, 19, tzinfo=timezone.utc),
            original_filename="scan.pdf",
            sha256_hex=sha256_hex,  # type: ignore[arg-type]
        )


def test_retained_source_scan_path_combines_validated_components() -> None:
    assert retained_source_scan_path(
        "paper_data",
        intake_date="2026-06-19",
        retained_filename="20260619T184512123456Z__scan__aaaaaaaaaaaa.pdf",
    ) == (
        Path("paper_data")
        / "scans"
        / "source"
        / "2026-06-19"
        / "20260619T184512123456Z__scan__aaaaaaaaaaaa.pdf"
    )


@pytest.mark.parametrize(
    "retained_filename",
    [
        "../scan.pdf",
        r"folder\scan.pdf",
        "C:scan.pdf",
        "/scan.pdf",
        "scan name.pdf",
        "scan.exe",
        "",
    ],
)
def test_retained_source_scan_path_rejects_unsafe_filename(
    retained_filename: str,
) -> None:
    with pytest.raises(ScanRouteError):
        retained_source_scan_path(
            "paper_data",
            intake_date="2026-06-19",
            retained_filename=retained_filename,
        )


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
    scans_root = scans_root_dir(tmp_path)
    source = scans_source_dir(tmp_path)
    source_date = scans_source_date_dir(tmp_path, "2026-06-19")
    review = routing_review_dir(tmp_path)
    retained = retained_source_scan_path(
        tmp_path,
        intake_date="2026-06-19",
        retained_filename="20260619T000000000000Z__scan__aaaaaaaaaaaa.pdf",
    )
    archive = scans_archive_dir(tmp_path)
    date_archive = scans_archive_date_dir(tmp_path, "2026-06-08")

    assert inbox == tmp_path / "scans_inbox"
    assert scans_root == tmp_path / "scans"
    assert source == tmp_path / "scans" / "source"
    assert source_date == source / "2026-06-19"
    assert review == tmp_path / "scans" / "review"
    assert retained.parent == source_date
    assert archive == tmp_path / "scans_archive"
    assert date_archive == tmp_path / "scans_archive" / "2026-06-08"

    assert not inbox.exists()
    assert not scans_root.exists()
    assert not source.exists()
    assert not source_date.exists()
    assert not review.exists()
    assert not retained.exists()
    assert not archive.exists()
    assert not date_archive.exists()
