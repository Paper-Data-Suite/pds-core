"""Issue #226 bounded retained-source naming regression tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pds_core.identifiers import is_valid_identifier
from pds_core.scan_retention import retain_source_scan
from pds_core.scan_routes import (
    RETAINED_SOURCE_FILENAME_MAX_LENGTH,
    RETAINED_SOURCE_ORIGINAL_STEM_MAX_LENGTH,
    SOURCE_SCAN_ID_MAX_LENGTH,
    build_retained_source_filename,
    retained_source_scan_path,
)


TIMESTAMP = datetime(2026, 9, 30, 3, 18, 38, 64717, tzinfo=timezone.utc)
DIGEST = "63e3b37316eb" + ("0" * 52)


def test_bounded_retained_source_contract_has_explicit_fixed_limits() -> None:
    assert RETAINED_SOURCE_ORIGINAL_STEM_MAX_LENGTH == 64
    assert RETAINED_SOURCE_FILENAME_MAX_LENGTH == 107
    assert SOURCE_SCAN_ID_MAX_LENGTH == 107


def test_ordinary_filename_keeps_legacy_serialization() -> None:
    filename = build_retained_source_filename(
        intake_timestamp=TIMESTAMP,
        original_filename="scanner export.PDF",
        sha256_hex=DIGEST,
    )

    assert filename == (
        "20260930T031838064717Z__scanner_export__63e3b37316eb.pdf"
    )


def test_extremely_long_filename_is_compacted_and_bounded() -> None:
    original_filename = ("descriptive_school_scanner_export_" * 20) + ".pdf"

    filename = build_retained_source_filename(
        intake_timestamp=TIMESTAMP,
        original_filename=original_filename,
        sha256_hex=DIGEST,
    )

    components = filename.removesuffix(".pdf").split("__")
    assert len(original_filename) > 400
    assert len(filename) <= RETAINED_SOURCE_FILENAME_MAX_LENGTH
    assert components[0] == "20260930T031838064717Z"
    assert components[1].startswith("scan_")
    assert len(components[1]) == 21
    assert components[2] == "63e3b37316eb"
    assert original_filename[:-4] not in filename


def test_compacted_long_names_do_not_collapse_on_shared_prefix() -> None:
    shared = "x" * 200
    first = build_retained_source_filename(
        intake_timestamp=TIMESTAMP,
        original_filename=f"{shared}_first.pdf",
        sha256_hex=DIGEST,
    )
    second = build_retained_source_filename(
        intake_timestamp=TIMESTAMP,
        original_filename=f"{shared}_second.pdf",
        sha256_hex=DIGEST,
    )

    assert first != second
    assert len(first) <= RETAINED_SOURCE_FILENAME_MAX_LENGTH
    assert len(second) <= RETAINED_SOURCE_FILENAME_MAX_LENGTH


def test_retention_preserves_original_filename_but_bounds_core_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / (("physical_scan_" * 7) + ".pdf")
    source.write_bytes(b"issue 226 retained source bytes")

    retained = retain_source_scan(
        tmp_path,
        source,
        intake_timestamp=TIMESTAMP,
    )

    assert retained.source_filename == source.name
    assert len(source.stem) > RETAINED_SOURCE_ORIGINAL_STEM_MAX_LENGTH
    assert len(retained.retained_source_path.name) <= RETAINED_SOURCE_FILENAME_MAX_LENGTH
    assert len(retained.source_scan_id) <= SOURCE_SCAN_ID_MAX_LENGTH
    assert is_valid_identifier(retained.source_scan_id)
    assert retained.retained_source_path.read_bytes() == source.read_bytes()


def test_reader_still_accepts_long_legacy_retained_filename() -> None:
    legacy_filename = (
        "20260930T031838064717Z__"
        + ("legacy_descriptive_source_" * 6)
        + "__63e3b37316eb.pdf"
    )

    path = retained_source_scan_path(
        "paper_data",
        intake_date="2026-09-30",
        retained_filename=legacy_filename,
    )

    assert len(legacy_filename) > RETAINED_SOURCE_FILENAME_MAX_LENGTH
    assert path.name == legacy_filename
