from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

import pds_core.grouping_signal_diagnostics as diagnostics_module
from pds_core.classes import write_class_roster
from pds_core.grouping_signal_csv import (
    grouping_signal_set_from_csv,
    grouping_signal_set_to_csv,
)
from pds_core.grouping_signal_diagnostics import (
    GroupingSignalDiagnostic,
    GroupingSignalDiagnosticsInputError,
    GroupingSignalDiagnosticsRosterError,
    diagnose_grouping_signal,
)
from pds_core.grouping_signal_storage import (
    grouping_signal_digest_path,
    grouping_signal_path,
    load_grouping_signal,
    write_grouping_signal,
)
from pds_core.grouping_signals import (
    GROUPING_SIGNAL_RECORD_TYPE,
    GROUPING_SIGNAL_SCHEMA_VERSION,
    GroupingSignalDimension,
    GroupingSignalSet,
    GroupingSignalSource,
    GroupingSignalStudentBand,
    grouping_signal_set_to_dict,
    grouping_signal_set_to_json_bytes,
)
from pds_core.rosters import create_roster


def _student(student_id: str, *, first_name: str | None = None) -> dict[str, str]:
    return {
        "student_id": student_id,
        "last_name": f"Last_{student_id}",
        "first_name": first_name or f"First_{student_id}",
        "period": "2",
    }


def _write_roster(
    root: Path,
    class_id: str,
    student_ids: list[str],
    *,
    reverse: bool = False,
) -> None:
    ids = list(reversed(student_ids)) if reverse else student_ids
    roster = create_roster(class_id, [_student(student_id) for student_id in ids])
    write_class_roster(root, roster)


def _source() -> GroupingSignalSource:
    return GroupingSignalSource(
        kind="teacher_authored",
        module_id=None,
        snapshot_id=None,
        snapshot_digest_algorithm=None,
        snapshot_digest=None,
    )


def _signal(
    *,
    class_id: str = "class_a",
    signal_set_id: str = "signal_001",
    dimensions: tuple[tuple[str, int], ...] = (("reading", 3),),
    bands: tuple[tuple[str, str, int], ...] = (
        ("student_001", "reading", 1),
        ("student_002", "reading", 2),
    ),
) -> GroupingSignalSet:
    return GroupingSignalSet(
        schema_version=GROUPING_SIGNAL_SCHEMA_VERSION,
        record_type=GROUPING_SIGNAL_RECORD_TYPE,
        signal_set_id=signal_set_id,
        class_id=class_id,
        created_at=datetime(2026, 9, 1, 18, 0, tzinfo=UTC),
        source=_source(),
        dimensions=tuple(
            GroupingSignalDimension(dimension_id=dimension_id, band_count=band_count)
            for dimension_id, band_count in dimensions
        ),
        student_bands=tuple(
            GroupingSignalStudentBand(
                student_id=student_id,
                dimension_id=dimension_id,
                band=band,
            )
            for student_id, dimension_id, band in bands
        ),
    )


def test_clean_signal_has_no_findings(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    report = diagnose_grouping_signal(tmp_path, _signal())

    assert report.is_clean
    assert not report.has_errors
    assert not report.has_warnings
    assert report.signal_set_id == "signal_001"
    assert report.signal_class_id == "class_a"
    assert report.target_class_id == "class_a"
    assert report.roster_student_count == 2
    assert report.dimensions[0].band_counts == ((1, 1), (2, 1), (3, 0))


def test_partial_coverage_is_dimension_local_warning(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    signal = _signal(
        dimensions=(("reading", 3), ("writing", 2)),
        bands=(
            ("student_001", "reading", 2),
            ("student_001", "writing", 1),
            ("student_002", "writing", 2),
        ),
    )
    report = diagnose_grouping_signal(tmp_path, signal)

    assert [finding.code for finding in report.findings] == ["missing_student_signal"]
    finding = report.findings[0]
    assert finding.student_id == "student_002"
    assert finding.dimension_id == "reading"
    assert finding.severity == "warning"
    assert report.has_warnings
    assert not report.has_errors
    assert report.dimensions[0].missing_student_count == 1
    assert report.dimensions[1].missing_student_count == 0


def test_unknown_student_is_reported_and_does_not_cover_roster(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    signal = _signal(
        bands=(
            ("student_001", "reading", 1),
            ("student_999", "reading", 3),
        )
    )
    report = diagnose_grouping_signal(tmp_path, signal)

    assert [finding.code for finding in report.findings] == [
        "unknown_student",
        "missing_student_signal",
    ]
    assert report.findings[0].student_id == "student_999"
    assert report.findings[1].student_id == "student_002"
    summary = report.dimensions[0]
    assert summary.signal_entry_count == 2
    assert summary.matched_student_count == 1
    assert summary.unknown_student_count == 1
    assert summary.missing_student_count == 1
    assert summary.band_counts == ((1, 1), (2, 0), (3, 0))


def test_wrong_class_student_reports_all_other_classes(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    _write_roster(tmp_path, "class_b", ["student_777"])
    _write_roster(tmp_path, "class_c", ["student_777"])
    signal = _signal(
        bands=(
            ("student_001", "reading", 1),
            ("student_777", "reading", 3),
        )
    )
    report = diagnose_grouping_signal(tmp_path, signal)

    wrong = report.findings[0]
    assert wrong.code == "wrong_class_student"
    assert wrong.student_id == "student_777"
    assert wrong.other_class_ids == ("class_b", "class_c")
    assert report.dimensions[0].wrong_class_student_count == 1
    assert report.dimensions[0].unknown_student_count == 0


def test_student_in_target_and_other_class_is_not_wrong_class(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    _write_roster(tmp_path, "class_b", ["student_001"])
    report = diagnose_grouping_signal(tmp_path, _signal())
    assert report.is_clean


def test_class_mismatch_continues_against_explicit_target(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_a"])
    _write_roster(tmp_path, "class_b", ["student_b"])
    signal = _signal(
        class_id="class_a",
        bands=(("student_a", "reading", 2),),
    )
    before = grouping_signal_set_to_json_bytes(signal)
    report = diagnose_grouping_signal(
        tmp_path,
        signal,
        expected_class_id="class_b",
    )

    assert [finding.code for finding in report.findings] == [
        "class_mismatch",
        "wrong_class_student",
        "missing_student_signal",
    ]
    assert report.target_class_id == "class_b"
    assert report.signal_class_id == "class_a"
    assert grouping_signal_set_to_json_bytes(signal) == before


def test_signal_student_in_explicit_target_is_valid_despite_class_mismatch(
    tmp_path: Path,
) -> None:
    _write_roster(tmp_path, "class_a", ["student_a"])
    _write_roster(tmp_path, "class_b", ["student_b"])
    signal = _signal(
        class_id="class_a",
        bands=(("student_b", "reading", 2),),
    )
    report = diagnose_grouping_signal(
        tmp_path,
        signal,
        expected_class_id="class_b",
    )
    assert [finding.code for finding in report.findings] == ["class_mismatch"]
    assert report.dimensions[0].matched_student_count == 1


def test_same_student_can_appear_in_multiple_dimensions(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001"])
    signal = _signal(
        dimensions=(("reading", 3), ("writing", 4)),
        bands=(
            ("student_001", "reading", 2),
            ("student_001", "writing", 4),
        ),
    )
    report = diagnose_grouping_signal(tmp_path, signal)
    assert report.is_clean
    assert report.dimensions[0].band_counts == ((1, 0), (2, 1), (3, 0))
    assert report.dimensions[1].band_counts == (
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 1),
    )


def test_duplicate_signal_entry_remains_structural_failure(tmp_path: Path) -> None:
    data = grouping_signal_set_to_dict(_signal())
    raw_bands = data["student_bands"]
    assert isinstance(raw_bands, list)
    bands = list(raw_bands)
    bands.insert(1, dict(bands[0]))
    data["student_bands"] = bands

    with pytest.raises(GroupingSignalDiagnosticsInputError) as captured:
        diagnose_grouping_signal(tmp_path, data)
    assert captured.value.__cause__ is not None
    assert "duplicate" in str(captured.value).lower()


@pytest.mark.parametrize("band", [0, 4, True, "2"])
def test_invalid_band_remains_structural_failure(tmp_path: Path, band: object) -> None:
    data = grouping_signal_set_to_dict(_signal())
    raw_entries = data["student_bands"]
    assert isinstance(raw_entries, list)
    entries = list(raw_entries)
    first = dict(entries[0])
    first["band"] = band
    entries[0] = first
    data["student_bands"] = entries

    with pytest.raises(GroupingSignalDiagnosticsInputError) as captured:
        diagnose_grouping_signal(tmp_path, data)
    assert captured.value.__cause__ is not None


def test_structural_failure_occurs_before_roster_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_roster(*args: object, **kwargs: object) -> object:
        raise AssertionError("roster must not be loaded")

    monkeypatch.setattr(diagnostics_module, "load_class_roster", fail_roster)
    data = grouping_signal_set_to_dict(_signal())
    data["schema_version"] = "2"
    with pytest.raises(GroupingSignalDiagnosticsInputError):
        diagnose_grouping_signal(tmp_path, data)


def test_invalid_expected_class_fails_before_roster_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_roster(*args: object, **kwargs: object) -> object:
        raise AssertionError("roster must not be loaded")

    monkeypatch.setattr(diagnostics_module, "load_class_roster", fail_roster)
    with pytest.raises(GroupingSignalDiagnosticsInputError):
        diagnose_grouping_signal(
            tmp_path,
            _signal(),
            expected_class_id="../unsafe",
        )


def test_missing_target_roster_is_operational_error(tmp_path: Path) -> None:
    with pytest.raises(GroupingSignalDiagnosticsRosterError):
        diagnose_grouping_signal(tmp_path, _signal())


def test_invalid_target_roster_is_operational_error(tmp_path: Path) -> None:
    roster_path = tmp_path / "classes" / "class_a" / "roster.csv"
    roster_path.parent.mkdir(parents=True)
    roster_path.write_text("student_id,band\nstudent_001,2\n", encoding="utf-8")

    with pytest.raises(GroupingSignalDiagnosticsRosterError):
        diagnose_grouping_signal(tmp_path, _signal())


def test_invalid_other_roster_blocks_unknown_classification(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001"])
    broken = tmp_path / "classes" / "class_b" / "roster.csv"
    broken.parent.mkdir(parents=True)
    broken.write_text("broken\nvalue\n", encoding="utf-8")
    signal = _signal(bands=(("student_999", "reading", 2),))

    with pytest.raises(GroupingSignalDiagnosticsRosterError):
        diagnose_grouping_signal(tmp_path, signal)


def test_invalid_other_roster_is_not_scanned_when_all_ids_match_target(
    tmp_path: Path,
) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    broken = tmp_path / "classes" / "class_b" / "roster.csv"
    broken.parent.mkdir(parents=True)
    broken.write_text("broken\nvalue\n", encoding="utf-8")

    assert diagnose_grouping_signal(tmp_path, _signal()).is_clean


def test_arbitrary_csv_outside_canonical_classes_does_not_resolve_student(
    tmp_path: Path,
) -> None:
    _write_roster(tmp_path, "class_a", ["student_001"])
    unrelated = tmp_path / "backups" / "roster.csv"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("student_id\nstudent_999\n", encoding="utf-8")
    signal = _signal(bands=(("student_999", "reading", 2),))

    report = diagnose_grouping_signal(tmp_path, signal)
    assert report.findings[0].code == "unknown_student"


def test_exchange_files_do_not_resolve_student_identity(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001"])
    exchange = tmp_path / "exchange" / "other.csv"
    exchange.parent.mkdir(parents=True)
    exchange.write_text("student_id\nstudent_999\n", encoding="utf-8")
    signal = _signal(bands=(("student_999", "reading", 2),))

    report = diagnose_grouping_signal(tmp_path, signal)
    assert report.findings[0].code == "unknown_student"


def test_report_order_is_independent_of_roster_and_class_creation_order(
    tmp_path: Path,
) -> None:
    _write_roster(
        tmp_path,
        "class_a",
        ["student_001", "student_002", "student_003"],
        reverse=True,
    )
    _write_roster(tmp_path, "class_z", ["student_777"])
    _write_roster(tmp_path, "class_b", ["student_777"])
    signal = _signal(
        dimensions=(("z_dim", 2), ("a_dim", 3)),
        bands=(
            ("student_999", "z_dim", 2),
            ("student_001", "a_dim", 1),
            ("student_777", "a_dim", 3),
            ("student_001", "z_dim", 1),
        ),
    )

    report = diagnose_grouping_signal(tmp_path, signal)
    assert [dimension.dimension_id for dimension in report.dimensions] == [
        "a_dim",
        "z_dim",
    ]
    assert [finding.code for finding in report.findings[:4]] == [
        "wrong_class_student",
        "missing_student_signal",
        "missing_student_signal",
        "unknown_student",
    ]
    assert report.findings[0].other_class_ids == ("class_b", "class_z")


def test_names_do_not_participate_in_identity_or_findings(tmp_path: Path) -> None:
    roster_a = create_roster(
        "class_a",
        [
            _student("student_001", first_name="SharedName"),
            _student("student_002", first_name="SharedName"),
        ],
    )
    roster_b = create_roster(
        "class_b",
        [_student("student_777", first_name="SharedName")],
    )
    write_class_roster(tmp_path, roster_a)
    write_class_roster(tmp_path, roster_b)
    signal = _signal(bands=(("student_999", "reading", 2),))

    report = diagnose_grouping_signal(tmp_path, signal)
    assert report.findings[0].code == "unknown_student"
    assert "SharedName" not in repr(report)


def test_band_distribution_counts_only_target_matched_students(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    _write_roster(tmp_path, "class_b", ["student_777"])
    signal = _signal(
        bands=(
            ("student_001", "reading", 1),
            ("student_777", "reading", 2),
            ("student_999", "reading", 3),
        )
    )
    summary = diagnose_grouping_signal(tmp_path, signal).dimensions[0]

    assert summary.signal_entry_count == 3
    assert summary.matched_student_count == 1
    assert summary.wrong_class_student_count == 1
    assert summary.unknown_student_count == 1
    assert summary.missing_student_count == 1
    assert summary.band_counts == ((1, 1), (2, 0), (3, 0))


def test_diagnostics_do_not_mutate_signal_or_roster(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    roster_path = tmp_path / "classes" / "class_a" / "roster.csv"
    roster_before = roster_path.read_bytes()
    signal = _signal(bands=(("student_001", "reading", 2),))
    signal_before = grouping_signal_set_to_json_bytes(signal)

    diagnose_grouping_signal(tmp_path, signal)

    assert roster_path.read_bytes() == roster_before
    assert grouping_signal_set_to_json_bytes(signal) == signal_before


def test_diagnostic_values_are_immutable(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    report = diagnose_grouping_signal(
        tmp_path,
        _signal(bands=(("student_001", "reading", 2),)),
    )
    with pytest.raises(FrozenInstanceError):
        report.target_class_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.findings[0].code = "unknown_student"  # type: ignore[misc]


def test_csv_conversion_composes_with_diagnostics(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    original = _signal()
    csv_text = grouping_signal_set_to_csv(original, "reading")
    imported = grouping_signal_set_from_csv(csv_text)

    assert diagnose_grouping_signal(tmp_path, imported) == diagnose_grouping_signal(
        tmp_path,
        original,
    )


def test_stored_signal_composes_without_changing_storage(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    original = _signal()
    write_grouping_signal(tmp_path, original)
    json_path = grouping_signal_path(tmp_path, "class_a", "signal_001")
    digest_path = grouping_signal_digest_path(tmp_path, "class_a", "signal_001")
    json_before = json_path.read_bytes()
    digest_before = digest_path.read_bytes()

    stored = load_grouping_signal(tmp_path, "class_a", "signal_001")
    report = diagnose_grouping_signal(tmp_path, stored.signal)

    assert report.is_clean
    assert json_path.read_bytes() == json_before
    assert digest_path.read_bytes() == digest_before


def test_runtime_construction_order_does_not_change_report(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    ordered = _signal(
        dimensions=(("a_dim", 2), ("z_dim", 3)),
        bands=(
            ("student_001", "a_dim", 1),
            ("student_002", "a_dim", 2),
            ("student_001", "z_dim", 3),
            ("student_002", "z_dim", 1),
        ),
    )
    reversed_input = _signal(
        dimensions=(("z_dim", 3), ("a_dim", 2)),
        bands=(
            ("student_002", "z_dim", 1),
            ("student_001", "z_dim", 3),
            ("student_002", "a_dim", 2),
            ("student_001", "a_dim", 1),
        ),
    )
    assert diagnose_grouping_signal(tmp_path, ordered) == diagnose_grouping_signal(
        tmp_path,
        reversed_input,
    )


def test_missing_student_does_not_create_band_zero(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    report = diagnose_grouping_signal(
        tmp_path,
        _signal(bands=(("student_001", "reading", 1),)),
    )
    summary = report.dimensions[0]
    assert summary.band_counts == ((1, 1), (2, 0), (3, 0))
    assert all(band >= 1 for band, _ in summary.band_counts)


def test_wrong_class_is_reported_per_dimension(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001"])
    _write_roster(tmp_path, "class_b", ["student_777"])
    signal = _signal(
        dimensions=(("reading", 3), ("writing", 2)),
        bands=(
            ("student_777", "reading", 2),
            ("student_777", "writing", 1),
        ),
    )
    report = diagnose_grouping_signal(tmp_path, signal)
    wrong = [item for item in report.findings if item.code == "wrong_class_student"]
    assert [(item.student_id, item.dimension_id) for item in wrong] == [
        ("student_777", "reading"),
        ("student_777", "writing"),
    ]


def test_unknown_is_reported_per_dimension(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001"])
    signal = _signal(
        dimensions=(("reading", 3), ("writing", 2)),
        bands=(
            ("student_999", "reading", 2),
            ("student_999", "writing", 1),
        ),
    )
    report = diagnose_grouping_signal(tmp_path, signal)
    unknown = [item for item in report.findings if item.code == "unknown_student"]
    assert [(item.student_id, item.dimension_id) for item in unknown] == [
        ("student_999", "reading"),
        ("student_999", "writing"),
    ]


def test_convenience_properties_distinguish_errors_and_warnings(tmp_path: Path) -> None:
    _write_roster(tmp_path, "class_a", ["student_001", "student_002"])
    warning_report = diagnose_grouping_signal(
        tmp_path,
        _signal(bands=(("student_001", "reading", 1),)),
    )
    error_report = diagnose_grouping_signal(
        tmp_path,
        _signal(bands=(("student_999", "reading", 1),)),
    )

    assert warning_report.has_warnings and not warning_report.has_errors
    assert error_report.has_warnings and error_report.has_errors
    assert not warning_report.is_clean
    assert not error_report.is_clean


def test_diagnostic_model_rejects_name_like_extra_identity() -> None:
    finding = GroupingSignalDiagnostic(
        code="unknown_student",
        severity="error",
        message="synthetic",
        student_id="student_001",
        dimension_id="reading",
    )
    assert not hasattr(finding, "student_name")
    assert not hasattr(finding, "email")
