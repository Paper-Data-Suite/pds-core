"""Tests for safe active source-scan retention."""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import pds_core.scan_retention as scan_retention
from pds_core.scan_retention import (
    RetainedSourceScan,
    SourceRetentionError,
    retain_source_scan,
)


TIMESTAMP = datetime(2026, 6, 19, 18, 45, 12, 123456, tzinfo=timezone.utc)


def test_retain_source_scan_copies_and_returns_provenance(tmp_path: Path) -> None:
    source = tmp_path / "Scanner Export.PDF"
    contents = b"readable scan bytes"
    source.write_bytes(contents)

    retained = retain_source_scan(tmp_path, source, intake_timestamp=TIMESTAMP)

    expected_digest = hashlib.sha256(contents).hexdigest()
    assert isinstance(retained, RetainedSourceScan)
    assert retained.source_filename == source.name
    assert retained.source_sha256 == expected_digest
    assert retained.intake_timestamp == TIMESTAMP
    assert retained.intake_date == date(2026, 6, 19)
    assert retained.retained_source_path.parent == (
        tmp_path / "scans" / "source" / "2026-06-19"
    )
    assert retained.retained_source_path.suffix == ".pdf"
    assert retained.retained_source_path.read_bytes() == contents
    assert retained.retained_source_relative_path == (
        f"scans/source/2026-06-19/{retained.retained_source_path.name}"
    )
    assert retained.source_scan_id == f"scan_{retained.retained_source_path.stem}"
    assert source.exists()
    assert source.read_bytes() == contents


def test_non_utc_timestamp_uses_utc_timestamp_and_date_bucket(tmp_path: Path) -> None:
    source = tmp_path / "scan.png"
    source.write_bytes(b"png")
    local_timestamp = datetime(
        2026, 6, 19, 20, 30, tzinfo=timezone(timedelta(hours=-4))
    )

    retained = retain_source_scan(
        tmp_path, source, intake_timestamp=local_timestamp
    )

    assert retained.intake_timestamp == datetime(
        2026, 6, 20, 0, 30, tzinfo=timezone.utc
    )
    assert retained.intake_date == date(2026, 6, 20)
    assert retained.retained_source_path.parent.name == "2026-06-20"


@pytest.mark.parametrize("intake_date", [date(2026, 6, 18), "2026-06-18"])
def test_explicit_intake_date_is_used(
    tmp_path: Path, intake_date: date | str
) -> None:
    source = tmp_path / "scan.jpg"
    source.write_bytes(b"jpg")

    retained = retain_source_scan(
        tmp_path,
        source,
        intake_timestamp=TIMESTAMP,
        intake_date=intake_date,
    )

    assert retained.intake_date == date(2026, 6, 18)
    assert retained.retained_source_path.parent.name == "2026-06-18"


@pytest.mark.parametrize("intake_date", ["2026-6-19", "../2026-06-19", ""])
def test_invalid_explicit_intake_date_is_rejected(
    tmp_path: Path, intake_date: str
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(SourceRetentionError, match="source_date"):
        retain_source_scan(
            tmp_path,
            source,
            intake_timestamp=TIMESTAMP,
            intake_date=intake_date,
        )


def test_naive_timestamp_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(SourceRetentionError, match="timezone-aware"):
        retain_source_scan(
            tmp_path, source, intake_timestamp=datetime(2026, 6, 19)
        )


def test_missing_workspace_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SourceRetentionError, match="Workspace root"):
        retain_source_scan(tmp_path / "missing", tmp_path / "scan.pdf")


def test_file_workspace_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "not-a-directory"
    root.write_text("file", encoding="utf-8")
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(SourceRetentionError, match="not a directory"):
        retain_source_scan(root, source)


def test_missing_source_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SourceRetentionError, match="does not exist"):
        retain_source_scan(tmp_path, tmp_path / "missing.pdf")


def test_directory_source_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SourceRetentionError, match="not a regular file"):
        retain_source_scan(tmp_path, tmp_path)


def test_unreadable_source_is_rejected_with_controlled_access_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"pdf")
    monkeypatch.setattr(os, "access", lambda *_args: False)

    with pytest.raises(SourceRetentionError, match="not readable"):
        retain_source_scan(tmp_path, source)


@pytest.mark.parametrize("extension", [".txt", ".bmp", ".exe", ""])
def test_unsupported_or_missing_extension_is_rejected(
    tmp_path: Path, extension: str
) -> None:
    source = tmp_path / f"scan{extension}"
    source.write_bytes(b"not supported")

    with pytest.raises(SourceRetentionError, match="supported scan extension"):
        retain_source_scan(tmp_path, source, intake_timestamp=TIMESTAMP)


def test_destination_collision_does_not_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"original")
    first = retain_source_scan(tmp_path, source, intake_timestamp=TIMESTAMP)
    retained_contents = first.retained_source_path.read_bytes()

    with pytest.raises(SourceRetentionError, match="already exists"):
        retain_source_scan(tmp_path, source, intake_timestamp=TIMESTAMP)

    assert first.retained_source_path.read_bytes() == retained_contents
    assert source.read_bytes() == b"original"


def test_source_change_is_detected_and_copy_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"before")
    original_copy = scan_retention._copy_exclusive_with_sha256

    def mutate_then_copy(source_path: Path, destination_path: Path) -> str:
        source_path.write_bytes(b"after")
        return original_copy(source_path, destination_path)

    monkeypatch.setattr(
        scan_retention, "_copy_exclusive_with_sha256", mutate_then_copy
    )

    with pytest.raises(SourceRetentionError, match="changed during retention"):
        retain_source_scan(tmp_path, source, intake_timestamp=TIMESTAMP)

    retained_dir = tmp_path / "scans" / "source" / "2026-06-19"
    assert list(retained_dir.iterdir()) == []


def test_symlink_escape_is_rejected_when_supported(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"pdf")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    scans = tmp_path / "scans"
    scans.mkdir()
    try:
        (scans / "source").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable on this platform")

    with pytest.raises(SourceRetentionError, match="workspace root"):
        retain_source_scan(tmp_path, source, intake_timestamp=TIMESTAMP)

    assert list(outside.iterdir()) == []
