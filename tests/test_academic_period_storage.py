from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pds_core.academic_period_queries import AcademicPeriodLookupError
from pds_core.academic_period_storage import (
    ACADEMIC_PERIOD_CURRENT_RECORD_TYPE,
    ACADEMIC_PERIOD_CURRENT_SCHEMA_VERSION,
    AcademicPeriodCalendarConflictError,
    AcademicPeriodCalendarIntegrityError,
    AcademicPeriodCalendarNotFoundError,
    AcademicPeriodCalendarReadError,
    AcademicPeriodCalendarWriteError,
    academic_period_current_path,
    academic_period_revision_path,
    academic_period_revisions_dir,
    academic_period_school_year_dir,
    academic_periods_dir,
    get_current_academic_period_calendar_revision,
    list_academic_period_calendar_revisions,
    list_academic_period_calendar_school_years,
    load_academic_period_calendar_revision,
    load_current_academic_period_calendar,
    resolve_academic_period_ref,
    write_academic_period_calendar,
)
from pds_core.academic_periods import (
    ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
    ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
    AcademicPeriod,
    AcademicPeriodCalendar,
    AcademicPeriodRef,
    AcademicPeriodValidationError,
    academic_period_calendar_to_dict,
)
from pds_core.school_years import SchoolYearValidationError
from pds_core.school_years import close_school_year, open_school_year
from pds_core.class_metadata import (
    create_class_metadata,
    load_class_metadata_for_class,
    write_class_metadata_for_class,
)
from pds_core.workspace import ensure_workspace_root


def _calendar(
    revision: int = 1,
    *,
    school_year: str = "2026-2027",
    label: str = "Marking Period 1",
) -> AcademicPeriodCalendar:
    start_year = int(school_year[:4])
    created = datetime(start_year, 7, 1, tzinfo=timezone.utc)
    period = AcademicPeriod(
        period_id="mp1",
        period_type="marking_period",
        label=label,
        start_date=date(start_year, 9, 1),
        end_date=date(start_year, 11, 1),
        parent_period_id=None,
        sequence=1,
        lifecycle="active",
    )
    return AcademicPeriodCalendar(
        schema_version=ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
        record_type=ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
        school_year=school_year,
        calendar_revision=revision,
        created_at=created,
        updated_at=created + timedelta(days=revision - 1),
        periods=(period,),
    )


def _write_raw_revision(root: Path, calendar: AcademicPeriodCalendar) -> Path:
    path = academic_period_revision_path(
        root, calendar.school_year, calendar.calendar_revision
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(academic_period_calendar_to_dict(calendar)), encoding="utf-8"
    )
    return path


def _write_pointer(
    root: Path,
    *,
    school_year: str = "2026-2027",
    revision: int = 1,
    updates: dict[str, object] | None = None,
) -> Path:
    data: dict[str, object] = {
        "schema_version": ACADEMIC_PERIOD_CURRENT_SCHEMA_VERSION,
        "record_type": ACADEMIC_PERIOD_CURRENT_RECORD_TYPE,
        "school_year": school_year,
        "calendar_revision": revision,
    }
    if updates:
        data.update(updates)
    path = academic_period_current_path(root, school_year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _assert_write_cleanup(root: Path, revision: int, *, remains: bool) -> None:
    school_year_dir = academic_period_school_year_dir(root, "2026-2027")
    assert academic_period_revision_path(root, "2026-2027", revision).exists() is remains
    assert not (school_year_dir / ".write.lock").exists()
    assert not list(school_year_dir.glob(".current.json.*.tmp"))


def test_paths_are_exact_normalized_and_nonmutating(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / ".." / "workspace"
    normalized = (tmp_path / "workspace").resolve()
    assert academic_periods_dir(str(root)) == normalized / "settings/academic_periods"
    assert academic_period_school_year_dir(root, "2026-2027") == (
        normalized / "settings/academic_periods/2026-2027"
    )
    assert academic_period_revisions_dir(root, "2026-2027") == (
        normalized / "settings/academic_periods/2026-2027/revisions"
    )
    assert academic_period_revision_path(root, "2026-2027", 1).name == "1.json"
    assert academic_period_current_path(root, "2026-2027").name == "current.json"
    assert not normalized.exists()
    with pytest.raises(SchoolYearValidationError):
        academic_period_current_path(root, "2026")
    for value in (True, 0, -1, 1.5, "1"):
        with pytest.raises(AcademicPeriodValidationError):
            academic_period_revision_path(root, "2026-2027", value)  # type: ignore[arg-type]


def test_initial_write_has_stable_bytes_pointer_and_round_trips(tmp_path: Path) -> None:
    calendar = _calendar()
    path = write_academic_period_calendar(
        tmp_path, calendar, expected_current_revision=None
    )
    expected = (
        json.dumps(
            academic_period_calendar_to_dict(calendar),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()
    assert path.read_bytes() == expected
    assert load_academic_period_calendar_revision(tmp_path, "2026-2027", 1) == calendar
    assert load_current_academic_period_calendar(tmp_path, "2026-2027") == calendar
    assert get_current_academic_period_calendar_revision(tmp_path, "2026-2027") == 1
    assert json.loads(academic_period_current_path(tmp_path, "2026-2027").read_text()) == {
        "schema_version": ACADEMIC_PERIOD_CURRENT_SCHEMA_VERSION,
        "record_type": ACADEMIC_PERIOD_CURRENT_RECORD_TYPE,
        "school_year": "2026-2027",
        "calendar_revision": 1,
    }
    assert not (academic_period_school_year_dir(tmp_path, "2026-2027") / ".write.lock").exists()


def test_updates_preserve_history_allow_gaps_and_reject_stale_writes(
    tmp_path: Path,
) -> None:
    first = _calendar()
    write_academic_period_calendar(tmp_path, first, expected_current_revision=None)
    old_bytes = academic_period_revision_path(tmp_path, "2026-2027", 1).read_bytes()
    third = _calendar(3, label="Renamed")
    write_academic_period_calendar(tmp_path, third, expected_current_revision=1)
    assert load_current_academic_period_calendar(tmp_path, "2026-2027") == third
    assert academic_period_revision_path(tmp_path, "2026-2027", 1).read_bytes() == old_bytes
    assert list_academic_period_calendar_revisions(tmp_path, "2026-2027") == (1, 3)
    with pytest.raises(AcademicPeriodCalendarConflictError):
        write_academic_period_calendar(
            tmp_path, _calendar(4), expected_current_revision=1
        )


def test_absent_current_is_not_empty_and_orphans_are_not_promoted(tmp_path: Path) -> None:
    assert load_current_academic_period_calendar(tmp_path, "2026-2027") is None
    assert list_academic_period_calendar_revisions(tmp_path, "2026-2027") == ()
    assert list_academic_period_calendar_school_years(tmp_path) == ()
    _write_raw_revision(tmp_path, _calendar())
    assert load_current_academic_period_calendar(tmp_path, "2026-2027") is None
    assert list_academic_period_calendar_school_years(tmp_path) == ()
    with pytest.raises(AcademicPeriodCalendarIntegrityError):
        write_academic_period_calendar(
            tmp_path, _calendar(), expected_current_revision=None
        )


@pytest.mark.parametrize("payload", ["{", "[]", '{"x": NaN}', '{"x": 1, "x": 2}'])
def test_pointer_loading_is_strict(tmp_path: Path, payload: str) -> None:
    path = academic_period_current_path(tmp_path, "2026-2027")
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        get_current_academic_period_calendar_revision(tmp_path, "2026-2027")


def test_revision_loading_is_strict_and_checks_path_identity(tmp_path: Path) -> None:
    path = _write_raw_revision(tmp_path, _calendar())
    data = academic_period_calendar_to_dict(_calendar())
    data["calendar_revision"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarIntegrityError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)
    path.write_text('{"schema_version": "1", "schema_version": "1"}', encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)
    with pytest.raises(AcademicPeriodCalendarNotFoundError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 2)


def test_revision_reader_rejects_invalid_utf8_and_nonstandard_numbers(
    tmp_path: Path,
) -> None:
    path = academic_period_revision_path(tmp_path, "2026-2027", 1)
    path.parent.mkdir(parents=True)
    for payload in (
        b"\xff\xfe",
        b'{"calendar_revision": Infinity}',
        b'{"calendar_revision": -Infinity}',
    ):
        path.write_bytes(payload)
        with pytest.raises(AcademicPeriodCalendarReadError):
            load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)


def test_revision_reader_rejects_nested_duplicates_and_model_failures(
    tmp_path: Path,
) -> None:
    data = academic_period_calendar_to_dict(_calendar())
    payload = json.dumps(data).replace(
        '"label": "Marking Period 1"',
        '"label": "first", "label": "second"',
    )
    path = academic_period_revision_path(tmp_path, "2026-2027", 1)
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)

    periods = data["periods"]
    assert isinstance(periods, list)
    assert isinstance(periods[0], dict)
    periods[0]["period_type"] = "unsupported"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)


def test_revision_reader_rejects_both_canonical_identity_mismatches(
    tmp_path: Path,
) -> None:
    data = academic_period_calendar_to_dict(_calendar(school_year="2027-2028"))
    path = academic_period_revision_path(tmp_path, "2026-2027", 1)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarIntegrityError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)
    data = academic_period_calendar_to_dict(_calendar())
    data["calendar_revision"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarIntegrityError):
        load_academic_period_calendar_revision(tmp_path, "2026-2027", 1)


@pytest.mark.parametrize(
    "updates",
    [
        {"schema_version": "2"},
        {"record_type": "wrong"},
        {"extra": True},
    ],
)
def test_pointer_reader_rejects_wrong_or_unknown_fields(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    _write_pointer(tmp_path, updates=updates)
    with pytest.raises(AcademicPeriodCalendarReadError):
        get_current_academic_period_calendar_revision(tmp_path, "2026-2027")


def test_pointer_reader_rejects_missing_key_and_path_identity_mismatch(
    tmp_path: Path,
) -> None:
    path = _write_pointer(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["record_type"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        get_current_academic_period_calendar_revision(tmp_path, "2026-2027")

    data["record_type"] = ACADEMIC_PERIOD_CURRENT_RECORD_TYPE
    data["school_year"] = "2027-2028"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarIntegrityError):
        get_current_academic_period_calendar_revision(tmp_path, "2026-2027")


def test_current_loader_rejects_missing_and_malformed_referenced_revision(
    tmp_path: Path,
) -> None:
    _write_pointer(tmp_path)
    with pytest.raises(AcademicPeriodCalendarIntegrityError):
        load_current_academic_period_calendar(tmp_path, "2026-2027")
    path = academic_period_revision_path(tmp_path, "2026-2027", 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        load_current_academic_period_calendar(tmp_path, "2026-2027")


def test_current_loader_follows_pointer_and_does_not_promote_orphan(
    tmp_path: Path,
) -> None:
    first = _calendar()
    second = _calendar(2, label="Orphan")
    write_academic_period_calendar(tmp_path, first, expected_current_revision=None)
    _write_raw_revision(tmp_path, second)
    assert load_current_academic_period_calendar(tmp_path, "2026-2027") == first
    assert get_current_academic_period_calendar_revision(tmp_path, "2026-2027") == 1


def test_listing_validates_names_and_embedded_values(tmp_path: Path) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    write_academic_period_calendar(
        tmp_path,
        _calendar(school_year="2027-2028"),
        expected_current_revision=None,
    )
    assert list_academic_period_calendar_school_years(tmp_path) == (
        "2026-2027",
        "2027-2028",
    )
    invalid = academic_period_revisions_dir(tmp_path, "2026-2027") / "01.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(AcademicPeriodCalendarReadError):
        list_academic_period_calendar_revisions(tmp_path, "2026-2027")


def test_listing_wraps_school_year_entry_inspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = academic_period_school_year_dir(tmp_path, "2026-2027")
    entry.mkdir(parents=True)
    original = Path.is_dir

    def fail_is_dir(path: Path) -> bool:
        if path == entry:
            raise OSError("simulated inspection failure")
        return original(path)

    monkeypatch.setattr(Path, "is_dir", fail_is_dir)
    with pytest.raises(AcademicPeriodCalendarReadError) as raised:
        list_academic_period_calendar_school_years(tmp_path)
    assert str(entry) in str(raised.value)


def test_listing_wraps_revision_entry_inspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _write_raw_revision(tmp_path, _calendar())
    original = Path.is_file

    def fail_is_file(path: Path) -> bool:
        if path == entry:
            raise OSError("simulated inspection failure")
        return original(path)

    monkeypatch.setattr(Path, "is_file", fail_is_file)
    with pytest.raises(AcademicPeriodCalendarReadError) as raised:
        list_academic_period_calendar_revisions(tmp_path, "2026-2027")
    assert str(entry) in str(raised.value)


def test_preexisting_lock_causes_conflict_without_mutating_state(tmp_path: Path) -> None:
    first = _calendar()
    write_academic_period_calendar(tmp_path, first, expected_current_revision=None)
    pointer = academic_period_current_path(tmp_path, "2026-2027")
    before = pointer.read_bytes()
    lock = academic_period_school_year_dir(tmp_path, "2026-2027") / ".write.lock"
    lock.touch()
    with pytest.raises(AcademicPeriodCalendarConflictError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert lock.exists()
    assert pointer.read_bytes() == before
    assert not academic_period_revision_path(tmp_path, "2026-2027", 2).exists()


def test_pointer_replace_failure_leaves_old_selection_and_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("pds_core.academic_period_storage.os.replace", fail_replace)
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert get_current_academic_period_calendar_revision(tmp_path, "2026-2027") == 1
    assert academic_period_revision_path(tmp_path, "2026-2027", 2).exists()
    assert not list(
        academic_period_school_year_dir(tmp_path, "2026-2027").glob(".current.json.*.tmp")
    )
    assert not (
        academic_period_school_year_dir(tmp_path, "2026-2027") / ".write.lock"
    ).exists()


def test_revision_directory_creation_failure_creates_no_write_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    revisions = academic_period_revisions_dir(tmp_path, "2026-2027")
    original = Path.mkdir

    def fail_mkdir(path: Path, *args: object, **kwargs: object) -> None:
        if path == revisions:
            raise OSError("simulated directory creation failure")
        original(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(), expected_current_revision=None
        )
    assert not academic_periods_dir(tmp_path).exists()


def test_revision_open_failure_preserves_pointer_and_cleans_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    pointer = academic_period_current_path(tmp_path, "2026-2027")
    before = pointer.read_bytes()
    target = academic_period_revision_path(tmp_path, "2026-2027", 2)
    original = Path.open

    def fail_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> object:
        if path == target and mode == "x":
            raise OSError("simulated revision open failure")
        return original(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert pointer.read_bytes() == before
    _assert_write_cleanup(tmp_path, 2, remains=False)


def test_revision_fsync_failure_removes_incomplete_revision_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    pointer = academic_period_current_path(tmp_path, "2026-2027")
    before = pointer.read_bytes()
    monkeypatch.setattr(
        "pds_core.academic_period_storage._fsync_directory_if_supported",
        lambda _path: None,
    )

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("simulated revision fsync failure")

    monkeypatch.setattr("pds_core.academic_period_storage.os.fsync", fail_fsync)
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert pointer.read_bytes() == before
    _assert_write_cleanup(tmp_path, 2, remains=False)


def test_persisted_revision_reload_failure_removes_candidate_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    pointer = academic_period_current_path(tmp_path, "2026-2027")
    before = pointer.read_bytes()
    original = load_academic_period_calendar_revision

    def fail_candidate_reload(
        root: str | Path, school_year: str, revision: int
    ) -> AcademicPeriodCalendar:
        if revision == 2:
            raise AcademicPeriodCalendarReadError("simulated reload failure")
        return original(root, school_year, revision)

    monkeypatch.setattr(
        "pds_core.academic_period_storage.load_academic_period_calendar_revision",
        fail_candidate_reload,
    )
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert pointer.read_bytes() == before
    _assert_write_cleanup(tmp_path, 2, remains=False)


def test_persisted_revision_inequality_removes_candidate_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    pointer = academic_period_current_path(tmp_path, "2026-2027")
    before = pointer.read_bytes()
    original = load_academic_period_calendar_revision

    def unequal_candidate_reload(
        root: str | Path, school_year: str, revision: int
    ) -> AcademicPeriodCalendar:
        if revision == 2:
            return _calendar(2, label="Different persisted value")
        return original(root, school_year, revision)

    monkeypatch.setattr(
        "pds_core.academic_period_storage.load_academic_period_calendar_revision",
        unequal_candidate_reload,
    )
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert pointer.read_bytes() == before
    _assert_write_cleanup(tmp_path, 2, remains=False)


def test_pointer_temporary_creation_failure_preserves_verified_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    pointer = academic_period_current_path(tmp_path, "2026-2027")
    before = pointer.read_bytes()

    def fail_temporary_file(*args: object, **kwargs: object) -> object:
        raise OSError("simulated pointer temporary-file failure")

    monkeypatch.setattr(
        "pds_core.academic_period_storage.tempfile.NamedTemporaryFile",
        fail_temporary_file,
    )
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert pointer.read_bytes() == before
    _assert_write_cleanup(tmp_path, 2, remains=True)


def test_pointer_temporary_fsync_failure_preserves_verified_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    pointer = academic_period_current_path(tmp_path, "2026-2027")
    before = pointer.read_bytes()
    monkeypatch.setattr(
        "pds_core.academic_period_storage._fsync_directory_if_supported",
        lambda _path: None,
    )
    calls = 0

    def fail_second_fsync(_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated pointer fsync failure")

    monkeypatch.setattr("pds_core.academic_period_storage.os.fsync", fail_second_fsync)
    with pytest.raises(AcademicPeriodCalendarWriteError):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert pointer.read_bytes() == before
    _assert_write_cleanup(tmp_path, 2, remains=True)


def test_final_reload_failure_is_integrity_error_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)

    def fail_final_reload(
        _root: str | Path, _school_year: str
    ) -> AcademicPeriodCalendar | None:
        raise AcademicPeriodCalendarReadError("simulated final reload failure")

    monkeypatch.setattr(
        "pds_core.academic_period_storage.load_current_academic_period_calendar",
        fail_final_reload,
    )
    with pytest.raises(AcademicPeriodCalendarIntegrityError, match="was published"):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert get_current_academic_period_calendar_revision(tmp_path, "2026-2027") == 2
    _assert_write_cleanup(tmp_path, 2, remains=True)


def test_final_reload_inequality_is_integrity_error_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _calendar()
    write_academic_period_calendar(tmp_path, first, expected_current_revision=None)
    monkeypatch.setattr(
        "pds_core.academic_period_storage.load_current_academic_period_calendar",
        lambda _root, _school_year: first,
    )
    with pytest.raises(AcademicPeriodCalendarIntegrityError, match="did not resolve"):
        write_academic_period_calendar(
            tmp_path, _calendar(2), expected_current_revision=1
        )
    assert get_current_academic_period_calendar_revision(tmp_path, "2026-2027") == 2
    _assert_write_cleanup(tmp_path, 2, remains=True)


def test_directory_fsync_failure_is_best_effort_and_final_verification_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_academic_period_calendar(tmp_path, _calendar(), expected_current_revision=None)
    original_open = os.open
    original_fsync = os.fsync
    original_close = os.close
    fake_directory_descriptor = 987654

    def directory_open(
        path: str | os.PathLike[str], flags: int, mode: int = 0o777
    ) -> int:
        candidate = Path(path)
        if candidate.is_dir():
            return fake_directory_descriptor
        return original_open(path, flags, mode)

    def directory_fsync(descriptor: int) -> None:
        if descriptor == fake_directory_descriptor:
            raise OSError("simulated directory fsync failure")
        original_fsync(descriptor)

    def directory_close(descriptor: int) -> None:
        if descriptor != fake_directory_descriptor:
            original_close(descriptor)

    verified = 0
    original_load_current = load_current_academic_period_calendar

    def count_final_verification(
        root: str | Path, school_year: str
    ) -> AcademicPeriodCalendar | None:
        nonlocal verified
        verified += 1
        return original_load_current(root, school_year)

    monkeypatch.setattr("pds_core.academic_period_storage.os.open", directory_open)
    monkeypatch.setattr("pds_core.academic_period_storage.os.fsync", directory_fsync)
    monkeypatch.setattr("pds_core.academic_period_storage.os.close", directory_close)
    monkeypatch.setattr(
        "pds_core.academic_period_storage.load_current_academic_period_calendar",
        count_final_verification,
    )
    candidate = _calendar(2)
    write_academic_period_calendar(tmp_path, candidate, expected_current_revision=1)
    assert verified == 1
    assert original_load_current(tmp_path, "2026-2027") == candidate
    _assert_write_cleanup(tmp_path, 2, remains=True)


def test_reference_resolution_is_exact_and_school_year_qualified(tmp_path: Path) -> None:
    first = _calendar()
    write_academic_period_calendar(tmp_path, first, expected_current_revision=None)
    second = _calendar(2, label="Current label")
    write_academic_period_calendar(tmp_path, second, expected_current_revision=1)
    reference = AcademicPeriodRef("2026-2027", "mp1")
    assert resolve_academic_period_ref(tmp_path, reference).label == "Current label"
    assert resolve_academic_period_ref(
        tmp_path, reference, calendar_revision=1
    ).label == "Marking Period 1"
    with pytest.raises(AcademicPeriodLookupError):
        resolve_academic_period_ref(
            tmp_path, AcademicPeriodRef("2026-2027", "missing")
        )
    with pytest.raises(AcademicPeriodLookupError):
        resolve_academic_period_ref(
            tmp_path, AcademicPeriodRef("2027-2028", "mp1")
        )
    with pytest.raises(AcademicPeriodCalendarNotFoundError):
        resolve_academic_period_ref(tmp_path, reference, calendar_revision=99)
    with pytest.raises(AcademicPeriodLookupError):
        resolve_academic_period_ref(
            tmp_path, AcademicPeriodRef("2026-2027", "fallback_label")
        )


def test_same_period_id_resolves_independently_across_school_years(
    tmp_path: Path,
) -> None:
    write_academic_period_calendar(
        tmp_path,
        _calendar(label="First-year label"),
        expected_current_revision=None,
    )
    write_academic_period_calendar(
        tmp_path,
        _calendar(school_year="2027-2028", label="Second-year label"),
        expected_current_revision=None,
    )
    assert resolve_academic_period_ref(
        tmp_path, AcademicPeriodRef("2026-2027", "mp1")
    ).label == "First-year label"
    assert resolve_academic_period_ref(
        tmp_path, AcademicPeriodRef("2027-2028", "mp1")
    ).label == "Second-year label"


def test_invalid_inputs_create_nothing(tmp_path: Path) -> None:
    with pytest.raises(AcademicPeriodValidationError):
        write_academic_period_calendar(
            tmp_path, object(), expected_current_revision=None  # type: ignore[arg-type]
        )
    with pytest.raises(AcademicPeriodCalendarConflictError):
        write_academic_period_calendar(
            tmp_path, replace(_calendar(), calendar_revision=2), expected_current_revision=None
        )
    assert not academic_periods_dir(tmp_path).exists()


def test_workspace_school_year_and_class_workflows_do_not_create_storage(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    ensure_workspace_root(workspace)
    assert not academic_periods_dir(workspace).exists()

    opened = datetime(2026, 8, 1, tzinfo=timezone.utc)
    open_school_year(workspace, "2026-2027", opened_at=opened)
    assert not academic_periods_dir(workspace).exists()
    close_school_year(workspace, closed_at=opened + timedelta(days=1))
    assert not academic_periods_dir(workspace).exists()

    metadata = create_class_metadata(
        "english10_p2", "2026-2027", created_at=opened
    )
    assert metadata.school_year == "2026-2027"
    assert not academic_periods_dir(workspace).exists()
    write_class_metadata_for_class(workspace, metadata)
    assert load_class_metadata_for_class(workspace, "english10_p2") == metadata
    assert not academic_periods_dir(workspace).exists()


def test_school_year_and_class_updates_preserve_calendar_bytes(tmp_path: Path) -> None:
    calendar = _calendar()
    write_academic_period_calendar(
        tmp_path, calendar, expected_current_revision=None
    )
    revision_path = academic_period_revision_path(tmp_path, "2026-2027", 1)
    pointer_path = academic_period_current_path(tmp_path, "2026-2027")
    original_bytes = (revision_path.read_bytes(), pointer_path.read_bytes())
    opened = datetime(2026, 8, 1, tzinfo=timezone.utc)

    open_school_year(tmp_path, "2026-2027", opened_at=opened)
    close_school_year(tmp_path, closed_at=opened + timedelta(days=1))
    open_school_year(
        tmp_path,
        "2026-2027",
        opened_at=opened + timedelta(days=2),
        overwrite=True,
    )

    metadata = create_class_metadata(
        "english10_p2", "2026-2027", created_at=opened
    )
    write_class_metadata_for_class(tmp_path, metadata)
    updated = create_class_metadata(
        "english10_p2",
        "2026-2027",
        created_at=opened,
        updated_at=opened + timedelta(days=3),
        module_details={"example": True},
    )
    write_class_metadata_for_class(tmp_path, updated, overwrite=True)

    assert (revision_path.read_bytes(), pointer_path.read_bytes()) == original_bytes
