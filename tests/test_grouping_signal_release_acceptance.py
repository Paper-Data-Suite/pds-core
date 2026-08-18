"""Standalone v0.6.1 acceptance for the neutral grouping-signal interchange."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pds_core.grouping_signal_csv import (
    GroupingSignalCsvError,
    grouping_signal_csv_to_signal_set,
    grouping_signal_set_from_csv,
    grouping_signal_set_to_csv_bytes,
    parse_grouping_signal_csv,
)
from pds_core.grouping_signal_diagnostics import (
    GroupingSignalDiagnosticsInputError,
    GroupingSignalDiagnosticsRosterError,
    diagnose_grouping_signal,
)
from pds_core.grouping_signal_storage import (
    GroupingSignalConflictError,
    GroupingSignalReadError,
    grouping_signal_digest_path,
    grouping_signal_path,
    load_grouping_signal,
    write_grouping_signal,
)
from pds_core.grouping_signals import (
    GroupingSignalValidationError,
    grouping_signal_set_from_json,
    grouping_signal_set_to_dict,
    grouping_signal_set_to_json_bytes,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "grouping_signals" / "v1"


def _read(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _copy_rosters(workspace: Path) -> None:
    shutil.copytree(FIXTURE_ROOT / "classes", workspace / "classes")


def _manifest_entries() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in _read("SHA256SUMS.txt").decode("ascii").splitlines():
        digest, relative_path = line.split("  ", maxsplit=1)
        entries[relative_path] = digest
    return entries


def test_release_fixture_checksums_and_privacy_boundary() -> None:
    entries = _manifest_entries()
    expected = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    assert set(entries) == expected
    for relative_path, expected_digest in entries.items():
        payload = (FIXTURE_ROOT / relative_path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_digest

    combined = b"\n".join((FIXTURE_ROOT / path).read_bytes() for path in sorted(entries))
    lowered = combined.lower()
    assert b"hillside" not in lowered
    assert b"severino" not in lowered
    assert b"@" not in combined
    assert b"c:\\" not in lowered
    assert b"/users/" not in lowered



def test_fixture_archive_builder_is_deterministic(tmp_path: Path) -> None:
    script = PROJECT_ROOT / "scripts" / "build_v061_fixture_archive.py"
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    for output in (first, second):
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--fixtures",
                str(FIXTURE_ROOT),
                "--output",
                str(output),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    assert first.read_bytes() == second.read_bytes()


def test_complete_json_csv_round_trip_is_exact() -> None:
    canonical = _read("teacher_complete.json")
    signal = grouping_signal_set_from_json(canonical)
    assert grouping_signal_set_to_json_bytes(signal) == canonical

    golden_csv = _read("teacher_complete.csv")
    assert grouping_signal_set_to_csv_bytes(signal, "discussion_support") == golden_csv
    round_tripped = grouping_signal_set_from_csv(golden_csv)
    assert round_tripped == signal
    assert grouping_signal_set_to_json_bytes(round_tripped) == canonical


def test_multi_dimension_projection_requires_new_identity() -> None:
    source = grouping_signal_set_from_json(_read("module_multi_dimension.json"))
    projection = _read("module_selected_dimension_projection.csv")
    assert grouping_signal_set_to_csv_bytes(source, "reading_analysis") == projection

    document = parse_grouping_signal_csv(projection)
    assert document.requires_new_identity
    with pytest.raises(GroupingSignalCsvError):
        grouping_signal_csv_to_signal_set(document)

    projected = grouping_signal_csv_to_signal_set(
        document,
        new_signal_set_id="reading_projection_qualified_001",
        new_created_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
    )
    assert projected.signal_set_id == "reading_projection_qualified_001"
    assert projected.class_id == source.class_id
    assert tuple(item.dimension_id for item in projected.dimensions) == (
        "reading_analysis",
    )
    assert all(item.dimension_id == "reading_analysis" for item in projected.student_bands)


def test_immutable_storage_and_digest_binding(tmp_path: Path) -> None:
    signal = grouping_signal_set_from_json(_read("teacher_complete.json"))
    first = write_grouping_signal(tmp_path, signal)
    second = write_grouping_signal(tmp_path, signal)

    assert first.disposition == "created"
    assert second.disposition == "existing"
    assert first.stored == second.stored
    assert first.stored.digest == hashlib.sha256(_read("teacher_complete.json")).hexdigest()
    assert grouping_signal_path(
        tmp_path, signal.class_id, signal.signal_set_id
    ).read_bytes() == _read("teacher_complete.json")
    assert grouping_signal_digest_path(
        tmp_path, signal.class_id, signal.signal_set_id
    ).read_text(encoding="ascii") == f"{first.stored.digest}\n"

    changed_entry = replace(signal.student_bands[0], band=2)
    changed = replace(
        signal,
        student_bands=(changed_entry,) + signal.student_bands[1:],
    )
    before_json = grouping_signal_path(
        tmp_path, signal.class_id, signal.signal_set_id
    ).read_bytes()
    before_digest = grouping_signal_digest_path(
        tmp_path, signal.class_id, signal.signal_set_id
    ).read_bytes()
    with pytest.raises(GroupingSignalConflictError):
        write_grouping_signal(tmp_path, changed)
    assert grouping_signal_path(
        tmp_path, signal.class_id, signal.signal_set_id
    ).read_bytes() == before_json
    assert grouping_signal_digest_path(
        tmp_path, signal.class_id, signal.signal_set_id
    ).read_bytes() == before_digest

    class_dir = grouping_signal_path(
        tmp_path, signal.class_id, signal.signal_set_id
    ).parent
    assert not any(
        (class_dir / alias).exists()
        for alias in ("latest.json", "current.json", "active.json", "head.json")
    )


def test_rehashed_noncanonical_storage_still_fails(tmp_path: Path) -> None:
    signal = grouping_signal_set_from_json(_read("teacher_complete.json"))
    write_grouping_signal(tmp_path, signal)
    json_path = grouping_signal_path(tmp_path, signal.class_id, signal.signal_set_id)
    digest_path = grouping_signal_digest_path(
        tmp_path, signal.class_id, signal.signal_set_id
    )

    altered = json_path.read_bytes().replace(
        b'  "schema_version": "1",', b'   "schema_version": "1",', 1
    )
    assert altered != json_path.read_bytes()
    json_path.write_bytes(altered)
    digest_path.write_text(
        hashlib.sha256(altered).hexdigest() + "\n", encoding="ascii", newline="\n"
    )

    with pytest.raises(GroupingSignalReadError):
        load_grouping_signal(tmp_path, signal.class_id, signal.signal_set_id)


def test_roster_diagnostics_cover_wrong_unknown_missing_and_class_mismatch(
    tmp_path: Path,
) -> None:
    _copy_rosters(tmp_path)
    signal = grouping_signal_set_from_json(_read("module_multi_dimension.json"))
    before = grouping_signal_set_to_json_bytes(signal)
    roster_hashes = {
        path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / "classes").rglob("roster.csv")
    }

    report = diagnose_grouping_signal(tmp_path, signal)
    assert report.has_errors
    assert report.has_warnings
    finding_keys = {
        (item.code, item.dimension_id, item.student_id, item.other_class_ids)
        for item in report.findings
    }
    assert (
        "wrong_class_student",
        "reading_analysis",
        "student_004",
        ("english10_p4",),
    ) in finding_keys
    assert (
        "unknown_student",
        "reading_analysis",
        "student_999",
        (),
    ) in finding_keys
    assert (
        "missing_student_signal",
        "reading_analysis",
        "student_002",
        (),
    ) in finding_keys
    assert (
        "missing_student_signal",
        "reading_analysis",
        "student_003",
        (),
    ) in finding_keys
    assert (
        "missing_student_signal",
        "writing_claim_evidence",
        "student_003",
        (),
    ) in finding_keys

    dimensions = {item.dimension_id: item for item in report.dimensions}
    reading = dimensions["reading_analysis"]
    assert reading.roster_student_count == 3
    assert reading.signal_entry_count == 3
    assert reading.matched_student_count == 1
    assert reading.wrong_class_student_count == 1
    assert reading.unknown_student_count == 1
    assert reading.missing_student_count == 2
    assert reading.band_counts == ((1, 0), (2, 1), (3, 0), (4, 0))

    mismatch = diagnose_grouping_signal(
        tmp_path,
        grouping_signal_set_from_json(_read("teacher_complete.json")),
        expected_class_id="english10_p4",
    )
    assert mismatch.findings[0].code == "class_mismatch"
    assert mismatch.signal_class_id == "english10_p2"
    assert mismatch.target_class_id == "english10_p4"

    assert grouping_signal_set_to_json_bytes(signal) == before
    assert roster_hashes == {
        path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / "classes").rglob("roster.csv")
    }


def test_structural_failures_precede_roster_diagnostics(tmp_path: Path) -> None:
    _copy_rosters(tmp_path)
    signal = grouping_signal_set_from_json(_read("teacher_complete.json"))
    mapping = grouping_signal_set_to_dict(signal)
    raw_student_bands = mapping["student_bands"]
    assert isinstance(raw_student_bands, list)
    student_bands = list(raw_student_bands)
    student_bands.append(dict(student_bands[0]))
    mapping["student_bands"] = student_bands

    with pytest.raises(GroupingSignalDiagnosticsInputError) as caught:
        diagnose_grouping_signal(tmp_path, mapping)
    assert isinstance(caught.value.__cause__, GroupingSignalValidationError)

    invalid_band = grouping_signal_set_to_dict(signal)
    raw_invalid_rows = invalid_band["student_bands"]
    assert isinstance(raw_invalid_rows, list)
    invalid_rows = list(raw_invalid_rows)
    invalid_rows[0] = {**invalid_rows[0], "band": 0}
    invalid_band["student_bands"] = invalid_rows
    with pytest.raises(GroupingSignalDiagnosticsInputError):
        diagnose_grouping_signal(tmp_path, invalid_band)


def test_incomplete_other_roster_lookup_does_not_assert_unknown(tmp_path: Path) -> None:
    _copy_rosters(tmp_path)
    broken_dir = tmp_path / "classes" / "english10_p6"
    broken_dir.mkdir(parents=True)
    (broken_dir / "roster.csv").write_text(
        "class_id,student_id,last_name,first_name,period\n"
        "english10_p6,student_777,Broken\n",
        encoding="utf-8",
        newline="\n",
    )
    signal = grouping_signal_set_from_json(_read("module_multi_dimension.json"))
    with pytest.raises(GroupingSignalDiagnosticsRosterError):
        diagnose_grouping_signal(tmp_path, signal)


def test_representative_adversarial_json_and_csv_fail_closed() -> None:
    canonical = _read("teacher_complete.json")
    with pytest.raises(GroupingSignalValidationError):
        grouping_signal_set_from_json(
            canonical.replace(
                b'"created_at": "2026-09-01T18:00:00+00:00"',
                b'"created_at": "2026-09-01T18:00:00Z"',
            )
        )
    with pytest.raises(GroupingSignalValidationError):
        grouping_signal_set_from_json(
            b'{"schema_version":"1","schema_version":"1"}\n'
        )

    csv_bytes = _read("teacher_complete.csv")
    with pytest.raises(GroupingSignalCsvError):
        parse_grouping_signal_csv(
            csv_bytes.replace(b"student_id,band", b"student_name,band")
        )
    with pytest.raises(GroupingSignalCsvError):
        parse_grouping_signal_csv(
            csv_bytes + b"student_001,2\n"
        )
