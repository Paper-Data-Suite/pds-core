from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import pds_core.academic_catalog as catalog_module
from pds_core.academic_catalog import (
    ACADEMIC_CATALOG_APPLICATION_ID,
    ACADEMIC_CATALOG_SCHEMA_VERSION,
    AcademicCatalogCompatibilityError,
    AcademicCatalogIntegrityError,
    AcademicCatalogReadError,
    AcademicCatalogConflictError,
    AcademicCatalogBuildError,
    AcademicCatalogNotFoundError,
    AcademicCatalogValidationError,
    AcademicPeriodCatalogQuery,
    AcademicWorkRegistrationCatalogQuery,
    PublicationCatalogQuery,
    PublicationCatalogState,
    _Source,
    _snapshot,
    load_academic_catalog_metadata,
    query_academic_period_catalog,
    query_academic_work_registration_catalog,
    query_publication_catalog,
    rebuild_academic_catalog,
    remove_academic_catalog,
)
from pds_core.academic_periods import (
    AcademicPeriod,
    AcademicPeriodCalendar,
    academic_period_calendar_to_dict,
)
from pds_core.academic_work_registrations import (
    AcademicWorkRegistration,
    academic_work_registration_to_dict,
)
from pds_core.class_metadata import ClassMetadata, write_class_metadata_for_class
from pds_core.publication_records import (
    PUBLICATION_CAPABILITIES,
    PublicationRecord,
    PublicationWithdrawal,
    publication_record_to_dict,
    publication_withdrawal_to_dict,
)
from pds_core.registry_paths import academic_catalog_lock_path, academic_catalog_path
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef


NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
WORK = ModuleWorkRef("scoreform", "math7_p1", "unit_1")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _calendar(root: Path) -> None:
    calendar = AcademicPeriodCalendar(
        schema_version="1",
        record_type="academic_period_calendar",
        school_year="2026-2027",
        calendar_revision=1,
        created_at=NOW,
        updated_at=NOW,
        periods=(
            AcademicPeriod(
                "semester_1",
                "semester",
                "Semester 1",
                date(2026, 8, 20),
                date(2026, 12, 20),
                None,
                1,
                "active",
            ),
            AcademicPeriod(
                "quarter_1",
                "quarter",
                "Quarter 1",
                date(2026, 8, 20),
                date(2026, 10, 20),
                "semester_1",
                1,
                "closed",
            ),
        ),
    )
    base = root / "settings" / "academic_periods" / "2026-2027"
    _write_json(
        base / "revisions" / "1.json", academic_period_calendar_to_dict(calendar)
    )
    _write_json(
        base / "current.json",
        {
            "schema_version": "1",
            "record_type": "academic_period_calendar_current",
            "school_year": "2026-2027",
            "calendar_revision": 1,
        },
    )


def _registration(root: Path, *, revision: int = 1, lifecycle: str = "active") -> None:
    registration = AcademicWorkRegistration(
        schema_version="1",
        record_type="academic_work_registration",
        work=WORK,
        registration_revision=revision,
        producer_contract_version="scoreform_1",
        title="Unit 1",
        work_kind="assessment",
        academic_intent="summative",
        lifecycle=lifecycle,  # type: ignore[arg-type]
        created_at=NOW,
        updated_at=NOW + timedelta(hours=revision - 1),
        source_records=(
            ModuleRecordRef("scoreform", "assignment", "assignment_1", "v1"),
        ),
    )
    base = root / "registry" / "work" / WORK.class_id / WORK.module_id / WORK.work_id
    _write_json(
        base / "revisions" / f"{revision}.json",
        academic_work_registration_to_dict(registration),
    )
    _write_json(
        base / "current.json",
        {
            "schema_version": "1",
            "record_type": "academic_work_registration_current",
            "work": {
                "module_id": WORK.module_id,
                "class_id": WORK.class_id,
                "work_id": WORK.work_id,
            },
            "registration_revision": revision,
        },
    )


def _publication(
    root: Path,
    publication_id: str,
    revision: int,
    *,
    supersedes: str | None = None,
    published_at: datetime = NOW,
) -> PublicationRecord:
    publication = PublicationRecord(
        schema_version="1",
        record_type="publication_record",
        publication_id=publication_id,
        work=WORK,
        source_record=ModuleRecordRef(
            "scoreform", "result_set", "results_1", "source_v1"
        ),
        publication_kind="academic_result_set",
        capabilities=("points", "standards_ratings"),
        record_set_id="primary",
        record_set_revision=revision,
        manifest_contract_version="manifest_v1",
        manifest_path="classes/math7_p1/modules/scoreform/work/unit_1/manifest.json",
        manifest_digest_algorithm="sha256",
        manifest_digest="a" * 64,
        published_at=published_at,
        academic_work_registration_revision=1,
        supersedes_publication_id=supersedes,
    )
    _write_json(
        root / "registry" / "publications" / f"{publication_id}.json",
        publication_record_to_dict(publication),
    )
    return publication


def _populated_workspace(root: Path) -> tuple[str, str]:
    write_class_metadata_for_class(
        root,
        ClassMetadata(WORK.class_id, "2026-2027", NOW, NOW, {}),
    )
    _calendar(root)
    _registration(root)
    first = "pub_11111111111111111111111111111111"
    second = "pub_22222222222222222222222222222222"
    _publication(root, first, 1)
    _publication(
        root, second, 3, supersedes=first, published_at=NOW + timedelta(hours=1)
    )
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", second, NOW + timedelta(hours=2), "Retracted"
    )
    _write_json(
        root / "registry" / "withdrawals" / f"{second}.json",
        publication_withdrawal_to_dict(withdrawal),
    )
    return first, second


def test_empty_workspace_builds_valid_distinct_empty_catalog(tmp_path: Path) -> None:
    result = rebuild_academic_catalog(tmp_path)
    assert result.catalog_path == tmp_path / "registry" / "catalog.sqlite"
    assert result.replaced_existing_catalog is False
    assert (
        result.metadata.source_snapshot_sha256
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert result.metadata.source_file_count == result.metadata.publication_count == 0
    assert query_academic_period_catalog(tmp_path) == ()
    assert query_academic_work_registration_catalog(tmp_path) == ()
    assert query_publication_catalog(tmp_path) == ()
    assert not Path(f"{result.catalog_path}-wal").exists()
    assert not Path(f"{result.catalog_path}-shm").exists()


def test_missing_catalog_read_has_no_side_effect(tmp_path: Path) -> None:
    with pytest.raises(AcademicCatalogNotFoundError):
        load_academic_catalog_metadata(tmp_path)
    assert not (tmp_path / "registry").exists()


def test_schema_pragmas_tables_and_counts(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    result = rebuild_academic_catalog(tmp_path)
    with sqlite3.connect(result.catalog_path) as connection:
        assert (
            connection.execute("PRAGMA application_id").fetchone()[0]
            == ACADEMIC_CATALOG_APPLICATION_ID
        )
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == ACADEMIC_CATALOG_SCHEMA_VERSION
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
    assert tables == {
        "catalog_metadata",
        "catalog_sources",
        "class_context",
        "academic_period_calendars",
        "academic_periods",
        "academic_work_registrations",
        "academic_work_registration_sources",
        "publications",
        "publication_capabilities",
    }
    assert result.metadata.class_count == 1
    assert result.metadata.calendar_revision_count == 1
    assert result.metadata.period_count == 2
    assert result.metadata.registration_revision_count == 1
    assert result.metadata.registration_source_count == 1
    assert result.metadata.publication_count == 2
    assert result.metadata.publication_capability_count == 4
    assert result.metadata.withdrawal_count == 1


def test_period_and_registration_queries(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    periods = query_academic_period_catalog(
        tmp_path,
        AcademicPeriodCatalogQuery(
            school_year="2026-2027", active_on=date(2026, 9, 1), lifecycle="closed"
        ),
    )
    assert [item.period_id for item in periods] == ["quarter_1"]
    registrations = query_academic_work_registration_catalog(
        tmp_path,
        AcademicWorkRegistrationCatalogQuery(
            school_year="2026-2027", class_id=WORK.class_id, academic_intent="summative"
        ),
    )
    assert len(registrations) == 1
    assert registrations[0].work == WORK
    assert registrations[0].source_records[0].contract_version == "v1"


def test_publication_state_capability_contract_and_time_queries(tmp_path: Path) -> None:
    first, second = _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    assert query_publication_catalog(tmp_path) == ()
    heads = query_publication_catalog(
        tmp_path, PublicationCatalogQuery(state="series_heads")
    )
    assert [item.publication_id for item in heads] == [second]
    assert heads[0].is_withdrawn and not heads[0].is_current_selectable
    historical = query_publication_catalog(
        tmp_path,
        PublicationCatalogQuery(
            required_capabilities=("standards_ratings", "points", "points"),
            manifest_contract_version="manifest_v1",
            source_contract_version="source_v1",
            producer_contract_version="scoreform_1",
            published_at_or_after=NOW.astimezone(timezone(timedelta(hours=-4))),
            published_before=NOW + timedelta(minutes=1),
            state="historical",
        ),
    )
    assert [item.publication_id for item in historical] == [first]
    assert historical[0].referenced_registration_lifecycle == "active"
    assert historical[0].current_registration_lifecycle == "active"
    withdrawn = query_publication_catalog(
        tmp_path, PublicationCatalogQuery(state="withdrawn")
    )
    assert [item.publication_id for item in withdrawn] == [second]


def test_missing_class_metadata_is_nullable_and_school_year_filter_excludes(
    tmp_path: Path,
) -> None:
    _registration(tmp_path)
    rebuild_academic_catalog(tmp_path)
    rows = query_academic_work_registration_catalog(tmp_path)
    assert len(rows) == 1 and rows[0].school_year is None
    assert (
        query_academic_work_registration_catalog(
            tmp_path, AcademicWorkRegistrationCatalogQuery(school_year="2026-2027")
        )
        == ()
    )


def test_rebuild_replaces_catalog_and_remove_is_idempotent(tmp_path: Path) -> None:
    assert rebuild_academic_catalog(tmp_path).replaced_existing_catalog is False
    assert rebuild_academic_catalog(tmp_path).replaced_existing_catalog is True
    assert remove_academic_catalog(tmp_path) is True
    assert remove_academic_catalog(tmp_path) is False


def test_existing_lock_conflicts_without_removal(tmp_path: Path) -> None:
    lock = academic_catalog_lock_path(tmp_path)
    lock.parent.mkdir(parents=True)
    lock.write_text("held", encoding="utf-8")
    with pytest.raises(AcademicCatalogConflictError):
        rebuild_academic_catalog(tmp_path)
    assert lock.read_text(encoding="utf-8") == "held"
    assert not academic_catalog_path(tmp_path).exists()


@pytest.mark.parametrize(
    "query",
    [
        lambda: AcademicPeriodCatalogQuery(limit=0),
        lambda: AcademicWorkRegistrationCatalogQuery(offset=-1),
        lambda: PublicationCatalogQuery(published_at_or_after=datetime(2026, 1, 1)),
        lambda: PublicationCatalogQuery(state="unknown"),  # type: ignore[arg-type]
    ],
)
def test_query_validation(query: object) -> None:
    with pytest.raises(AcademicCatalogValidationError):
        query()  # type: ignore[operator]


def test_wrong_application_and_schema_versions_are_compatibility_errors(
    tmp_path: Path,
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA application_id=123")
    with pytest.raises(AcademicCatalogCompatibilityError):
        load_academic_catalog_metadata(tmp_path)


def test_catalog_queries_do_not_mutate_database_bytes(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    query_academic_period_catalog(tmp_path)
    query_academic_work_registration_catalog(tmp_path)
    query_publication_catalog(tmp_path, PublicationCatalogQuery(state="all"))
    assert path.read_bytes() == before


def test_source_membership_race_preserves_existing_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    original = catalog_module._discover_base_paths
    calls = 0

    def racing_discovery(root: Path) -> tuple[Path, ...]:
        nonlocal calls
        calls += 1
        if calls == 2:
            _write_json(
                root
                / "registry"
                / "publications"
                / "pub_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json",
                {},
            )
        return original(root)

    monkeypatch.setattr(catalog_module, "_discover_base_paths", racing_discovery)
    with pytest.raises(AcademicCatalogConflictError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()
    assert not tuple(path.parent.glob(".catalog.sqlite.*.tmp"))


def test_insertion_failure_preserves_existing_catalog_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()

    def fail_insert(*_args: object) -> None:
        raise sqlite3.OperationalError("injected insertion failure")

    monkeypatch.setattr(catalog_module, "_insert_projection", fail_insert)
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()
    assert not tuple(path.parent.glob(".catalog.sqlite.*.tmp"))


def test_candidate_verification_failure_preserves_existing_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()

    def fail_verify(_connection: sqlite3.Connection) -> object:
        raise catalog_module.AcademicCatalogIntegrityError(
            "injected verification failure"
        )

    monkeypatch.setattr(catalog_module, "_verify", fail_verify)
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()
    assert not tuple(path.parent.glob(".catalog.sqlite.*.tmp"))


def test_atomic_replacement_failure_preserves_existing_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()
    assert not tuple(path.parent.glob(".catalog.sqlite.*.tmp"))


def test_post_replacement_verification_failure_preserves_installed_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    original_verify = catalog_module._verify
    calls = 0

    def fail_final(connection: sqlite3.Connection) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise catalog_module.AcademicCatalogIntegrityError(
                "injected final verification failure"
            )
        return original_verify(connection)

    monkeypatch.setattr(catalog_module, "_verify", fail_final)
    with pytest.raises(
        AcademicCatalogBuildError, match=str(path).replace("\\", "\\\\")
    ):
        rebuild_academic_catalog(tmp_path)
    assert path.exists()
    assert path.read_bytes() != before
    assert not academic_catalog_lock_path(tmp_path).exists()
    assert not tuple(path.parent.glob(".catalog.sqlite.*.tmp"))


def test_malformed_source_preserves_existing_catalog(tmp_path: Path) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    malformed = (
        tmp_path
        / "registry"
        / "publications"
        / "pub_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.json"
    )
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(catalog_module.AcademicCatalogSourceError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()


def test_rebuild_does_not_open_manifest_or_arbitrary_work_files(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    arbitrary = (
        tmp_path
        / "classes"
        / WORK.class_id
        / "modules"
        / WORK.module_id
        / "work"
        / WORK.work_id
        / "native"
        / "must-not-open.json"
    )
    _write_json(arbitrary, {"not": "canonical"})
    before = arbitrary.read_bytes()
    rebuild_academic_catalog(tmp_path)
    assert arbitrary.read_bytes() == before
    assert not arbitrary.with_name("manifest.json").exists()


def test_snapshot_encoding_fixed_vector_and_order_independence() -> None:
    first = _Source("a.json", 3, "0" * 64, b"abc")
    second = _Source("z.json", 0, "f" * 64, b"")
    assert _snapshot((first, second)) == _snapshot((second, first))
    assert (
        _snapshot((first, second))
        == "f6aca6bb2959a4aa7051f498bc9161f13c4366897730204b7aa1d7aa77ef7404"
    )


def _sidecars(path: Path) -> tuple[Path, Path, Path]:
    return tuple(Path(f"{path}-{suffix}") for suffix in ("journal", "wal", "shm"))  # type: ignore[return-value]


def test_remove_preserves_unrelated_sqlite_database_and_sidecars(
    tmp_path: Path,
) -> None:
    path = academic_catalog_path(tmp_path)
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA application_id=12345")
        connection.execute("CREATE TABLE unrelated(value TEXT)")
        connection.commit()
    finally:
        connection.close()
    before = path.read_bytes()
    for sidecar in _sidecars(path):
        sidecar.write_bytes(b"unrelated-sidecar")
    with pytest.raises(AcademicCatalogCompatibilityError):
        remove_academic_catalog(tmp_path)
    assert path.read_bytes() == before
    assert all(
        sidecar.read_bytes() == b"unrelated-sidecar" for sidecar in _sidecars(path)
    )


def test_remove_preserves_non_sqlite_content(tmp_path: Path) -> None:
    path = academic_catalog_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a sqlite database")
    before = path.read_bytes()
    with pytest.raises(AcademicCatalogReadError):
        remove_academic_catalog(tmp_path)
    assert path.read_bytes() == before


def test_existing_lock_prevents_removal_and_is_preserved(tmp_path: Path) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    lock = academic_catalog_lock_path(tmp_path)
    lock.write_text("other operation", encoding="utf-8")
    with pytest.raises(AcademicCatalogConflictError):
        remove_academic_catalog(tmp_path)
    assert path.read_bytes() == before
    assert lock.read_text(encoding="utf-8") == "other operation"


def test_remove_known_pds_catalog_with_damaged_schema(tmp_path: Path) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TABLE academic_periods")
        connection.commit()
    finally:
        connection.close()
    assert remove_academic_catalog(tmp_path) is True
    assert not path.exists()


@pytest.mark.parametrize(
    "sidecar_names",
    [("journal",), ("wal",), ("shm",), ("journal", "wal", "shm")],
)
def test_successful_rebuild_removes_stale_target_sidecars(
    tmp_path: Path, sidecar_names: tuple[str, ...]
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    for name in sidecar_names:
        Path(f"{path}-{name}").write_bytes(b"stale")
    rebuild_academic_catalog(tmp_path)
    assert all(not sidecar.exists() for sidecar in _sidecars(path))


@pytest.mark.parametrize(
    "sidecar_names",
    [("journal",), ("wal",), ("shm",), ("journal", "wal", "shm")],
)
def test_successful_removal_removes_known_catalog_sidecars(
    tmp_path: Path, sidecar_names: tuple[str, ...]
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    for name in sidecar_names:
        Path(f"{path}-{name}").write_bytes(b"stale")
    assert remove_academic_catalog(tmp_path) is True
    assert not path.exists()
    assert all(not sidecar.exists() for sidecar in _sidecars(path))


def test_sidecar_cleanup_failure_after_replacement_preserves_installed_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    sidecar = Path(f"{path}-wal")
    sidecar.write_bytes(b"stale")
    original_unlink = Path.unlink

    def fail_sidecar_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self == sidecar:
            raise OSError("injected target sidecar cleanup failure")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", fail_sidecar_unlink)
    with pytest.raises(AcademicCatalogBuildError, match="preserved at"):
        rebuild_academic_catalog(tmp_path)
    assert path.exists()
    assert sidecar.exists()


def test_removal_changes_no_canonical_or_producer_owned_file(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    producer = (
        tmp_path
        / "classes"
        / WORK.class_id
        / "modules"
        / "scoreform"
        / "work"
        / "unit_1"
        / "native.json"
    )
    _write_json(producer, {"producer": True})
    canonical = {
        path: path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and path != academic_catalog_path(tmp_path)
    }
    rebuild_academic_catalog(tmp_path)
    assert remove_academic_catalog(tmp_path)
    assert {path: path.read_bytes() for path in canonical} == canonical


def _add_calendar_and_registration_history(root: Path) -> None:
    calendar_path = root / "settings" / "academic_periods" / "2026-2027"
    calendar_data = json.loads(
        (calendar_path / "revisions" / "1.json").read_text(encoding="utf-8")
    )
    calendar_data["calendar_revision"] = 2
    calendar_data["updated_at"] = (NOW + timedelta(hours=1)).isoformat()
    calendar_data["periods"][0]["lifecycle"] = "closed"
    _write_json(calendar_path / "revisions" / "2.json", calendar_data)
    pointer = json.loads((calendar_path / "current.json").read_text(encoding="utf-8"))
    pointer["calendar_revision"] = 2
    _write_json(calendar_path / "current.json", pointer)
    _registration(root, revision=2, lifecycle="closed")


def _tamper(path: Path, *statements: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("PRAGMA ignore_check_constraints=ON")
        for statement in statements:
            connection.execute(statement)


def test_calendar_and_registration_history_projection(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    rebuild_academic_catalog(tmp_path)
    periods = query_academic_period_catalog(
        tmp_path, AcademicPeriodCatalogQuery(current_calendar_only=False)
    )
    assert {item.calendar_revision for item in periods} == {1, 2}
    assert all(
        item.calendar_revision == 2 for item in query_academic_period_catalog(tmp_path)
    )
    registrations = query_academic_work_registration_catalog(
        tmp_path, AcademicWorkRegistrationCatalogQuery(current_only=False)
    )
    assert [
        (item.registration_revision, item.is_current_registration)
        for item in registrations
    ] == [
        (1, False),
        (2, True),
    ]
    publications = query_publication_catalog(
        tmp_path, PublicationCatalogQuery(state="all")
    )
    assert publications[0].referenced_registration_lifecycle == "active"
    assert publications[0].current_registration_lifecycle == "closed"


def test_older_calendar_pointer_is_rejected(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    pointer = tmp_path / "settings" / "academic_periods" / "2026-2027" / "current.json"
    data = json.loads(pointer.read_text(encoding="utf-8"))
    data["calendar_revision"] = 1
    _write_json(pointer, data)
    with pytest.raises(catalog_module.AcademicCatalogSourceError):
        rebuild_academic_catalog(tmp_path)


def test_older_registration_pointer_is_rejected(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    pointer = (
        tmp_path
        / "registry"
        / "work"
        / WORK.class_id
        / WORK.module_id
        / WORK.work_id
        / "current.json"
    )
    data = json.loads(pointer.read_text(encoding="utf-8"))
    data["registration_revision"] = 1
    _write_json(pointer, data)
    with pytest.raises(catalog_module.AcademicCatalogSourceError):
        rebuild_academic_catalog(tmp_path)


@pytest.mark.parametrize("corruption", ["hierarchy", "transition"])
def test_malformed_calendar_hierarchy_and_transition_are_rejected(
    tmp_path: Path, corruption: str
) -> None:
    _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    revision = (
        tmp_path
        / "settings"
        / "academic_periods"
        / "2026-2027"
        / "revisions"
        / "2.json"
    )
    data = json.loads(revision.read_text(encoding="utf-8"))
    if corruption == "hierarchy":
        data["periods"][1]["parent_period_id"] = "missing_parent"
    else:
        data["periods"][0]["period_type"] = "custom"
    _write_json(revision, data)
    with pytest.raises(catalog_module.AcademicCatalogSourceError):
        rebuild_academic_catalog(tmp_path)


def test_semantic_current_calendar_tampering_is_detected_by_metadata_and_query(
    tmp_path: Path,
) -> None:
    _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    _tamper(
        path,
        "UPDATE academic_period_calendars SET is_current=CASE calendar_revision WHEN 1 THEN 1 ELSE 0 END",
    )
    with pytest.raises(AcademicCatalogIntegrityError):
        load_academic_catalog_metadata(tmp_path)
    with pytest.raises(AcademicCatalogIntegrityError):
        query_academic_period_catalog(tmp_path)


def test_semantic_current_registration_tampering_is_detected(
    tmp_path: Path,
) -> None:
    _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    _tamper(
        path,
        "UPDATE academic_work_registrations SET is_current=CASE registration_revision WHEN 1 THEN 1 ELSE 0 END",
    )
    for operation in (
        load_academic_catalog_metadata,
        query_academic_work_registration_catalog,
        query_publication_catalog,
    ):
        with pytest.raises(AcademicCatalogIntegrityError):
            operation(tmp_path)


def test_semantic_publication_head_tampering_is_detected(tmp_path: Path) -> None:
    first, second = _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    _tamper(
        path,
        f"UPDATE publications SET is_series_head=1,is_current_selectable=1 WHERE publication_id='{first}'",
        f"UPDATE publications SET is_series_head=0,is_current_selectable=0 WHERE publication_id='{second}'",
    )
    with pytest.raises(AcademicCatalogIntegrityError):
        load_academic_catalog_metadata(tmp_path)
    with pytest.raises(AcademicCatalogIntegrityError):
        query_publication_catalog(tmp_path, PublicationCatalogQuery(state="all"))


def test_semantic_swapped_withdrawal_flags_are_detected(tmp_path: Path) -> None:
    first, second = _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    withdrawn_at = "2026-07-28T14:00:00.000000+00:00"
    _tamper(
        path,
        f"UPDATE publications SET is_withdrawn=1,withdrawn_at_utc='{withdrawn_at}' WHERE publication_id='{first}'",
        f"UPDATE publications SET is_withdrawn=0,withdrawn_at_utc=NULL,is_current_selectable=1 WHERE publication_id='{second}'",
    )
    with pytest.raises(AcademicCatalogIntegrityError):
        load_academic_catalog_metadata(tmp_path)
    with pytest.raises(AcademicCatalogIntegrityError):
        query_publication_catalog(tmp_path, PublicationCatalogQuery(state="all"))


def test_noncontiguous_registration_source_positions_are_detected(
    tmp_path: Path,
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    _tamper(
        academic_catalog_path(tmp_path),
        "UPDATE academic_work_registration_sources SET position=2",
    )
    with pytest.raises(AcademicCatalogIntegrityError):
        load_academic_catalog_metadata(tmp_path)
    with pytest.raises(AcademicCatalogIntegrityError):
        query_academic_work_registration_catalog(tmp_path)


@pytest.mark.parametrize(
    ("corruption", "query_name"),
    [
        ("registration_source_module", "registration"),
        ("registration_source_kind", "registration"),
        ("publication_source_record", "publication"),
        ("work_identity", "registration"),
        ("period_schema", "period"),
        ("registration_timestamp", "registration"),
        ("capability", "publication"),
        ("period_label", "period"),
    ],
)
def test_public_queries_normalize_corrupt_result_rows_to_integrity_errors(
    tmp_path: Path, corruption: str, query_name: str
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    statements = {
        "registration_source_module": (
            "UPDATE academic_work_registration_sources SET source_module_id='BadModule'",
        ),
        "registration_source_kind": (
            "UPDATE academic_work_registration_sources SET source_record_kind='BadKind'",
        ),
        "publication_source_record": ("UPDATE publications SET source_record_id=''",),
        "work_identity": (
            "UPDATE academic_work_registration_sources SET module_id='BadModule'",
            "UPDATE academic_work_registrations SET module_id='BadModule'",
            "UPDATE publications SET module_id='BadModule'",
        ),
        "period_schema": (
            "UPDATE academic_period_calendars SET schema_version='future'",
        ),
        "registration_timestamp": (
            "UPDATE academic_work_registrations SET created_at_utc='not-a-time'",
        ),
        "capability": (
            "UPDATE publication_capabilities SET capability='unsupported' WHERE capability='points'",
        ),
        "period_label": ("UPDATE academic_periods SET label=''",),
    }[corruption]
    _tamper(path, *statements)
    with pytest.raises(AcademicCatalogIntegrityError) as raised:
        if query_name == "period":
            query_academic_period_catalog(tmp_path)
        elif query_name == "registration":
            query_academic_work_registration_catalog(tmp_path)
        else:
            query_publication_catalog(tmp_path, PublicationCatalogQuery(state="all"))
    assert not isinstance(raised.value.__cause__, (TypeError,))


def test_publication_and_registration_models_copy_mutable_iterables(
    tmp_path: Path,
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    registration = query_academic_work_registration_catalog(tmp_path)[0]
    publication = query_publication_catalog(
        tmp_path, PublicationCatalogQuery(state="all")
    )[0]
    source_list = list(registration.source_records)
    copied_registration = catalog_module.CatalogAcademicWorkRegistration(
        registration.school_year,
        registration.work,
        registration.registration_revision,
        registration.schema_version,
        registration.producer_contract_version,
        registration.title,
        registration.work_kind,
        registration.academic_intent,
        registration.lifecycle,
        registration.created_at,
        registration.updated_at,
        registration.is_current_registration,
        source_list,  # type: ignore[arg-type]
    )
    capability_list = list(publication.capabilities)
    copied_publication = catalog_module.CatalogPublication(
        publication.school_year,
        publication.publication_id,
        publication.work,
        publication.source_record,
        publication.publication_kind,
        capability_list,  # type: ignore[arg-type]
        publication.record_set_id,
        publication.record_set_revision,
        publication.manifest_contract_version,
        publication.manifest_path,
        publication.manifest_digest_algorithm,
        publication.manifest_digest,
        publication.published_at,
        publication.academic_work_registration_revision,
        publication.referenced_registration_lifecycle,
        publication.current_registration_revision,
        publication.current_registration_lifecycle,
        publication.supersedes_publication_id,
        publication.is_series_head,
        publication.is_withdrawn,
        publication.withdrawn_at,
        publication.is_current_selectable,
    )
    source_list.clear()
    capability_list.clear()
    assert copied_registration.source_records == registration.source_records
    assert copied_publication.capabilities == publication.capabilities
    assert isinstance(copied_registration.source_records, tuple)
    assert isinstance(copied_publication.capabilities, tuple)
    assert hash(copied_registration)
    assert hash(copied_publication)


def test_period_model_copies_canonical_period_and_validates_schema(
    tmp_path: Path,
) -> None:
    _calendar(tmp_path)
    rebuild_academic_catalog(tmp_path)
    period = query_academic_period_catalog(tmp_path)[0]
    copied = catalog_module.CatalogAcademicPeriod(
        period.school_year,
        period.calendar_revision,
        period.schema_version,
        period.calendar_created_at,
        period.calendar_updated_at,
        period.is_current_calendar,
        period.period,
    )
    assert copied.period == period.period
    assert copied.period is not period.period
    assert hash(copied)
    with pytest.raises(AcademicCatalogValidationError):
        catalog_module.CatalogAcademicPeriod(
            period.school_year,
            period.calendar_revision,
            "future",
            period.calendar_created_at,
            period.calendar_updated_at,
            period.is_current_calendar,
            period.period,
        )


@pytest.mark.parametrize("bad_revision", [True, "1", 1.5, 0])
def test_catalog_result_models_normalize_invalid_revision_types(
    tmp_path: Path, bad_revision: object
) -> None:
    _calendar(tmp_path)
    rebuild_academic_catalog(tmp_path)
    period = query_academic_period_catalog(tmp_path)[0]
    with pytest.raises(AcademicCatalogValidationError):
        catalog_module.CatalogAcademicPeriod(
            period.school_year,
            bad_revision,  # type: ignore[arg-type]
            period.schema_version,
            period.calendar_created_at,
            period.calendar_updated_at,
            period.is_current_calendar,
            period.period,
        )


def test_publication_model_rejects_inconsistent_optional_registration_fields(
    tmp_path: Path,
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    publication = query_publication_catalog(
        tmp_path, PublicationCatalogQuery(state="all")
    )[0]
    with pytest.raises(AcademicCatalogValidationError):
        catalog_module.CatalogPublication(
            publication.school_year,
            publication.publication_id,
            publication.work,
            publication.source_record,
            publication.publication_kind,
            publication.capabilities,
            publication.record_set_id,
            publication.record_set_revision,
            publication.manifest_contract_version,
            publication.manifest_path,
            publication.manifest_digest_algorithm,
            publication.manifest_digest,
            publication.published_at,
            publication.academic_work_registration_revision,
            publication.referenced_registration_lifecycle,
            2,
            None,
            publication.supersedes_publication_id,
            publication.is_series_head,
            publication.is_withdrawn,
            publication.withdrawn_at,
            publication.is_current_selectable,
        )


@pytest.mark.parametrize("bad", [True, "1", 1.5, 0, -1])
def test_positive_integer_query_fields_reject_invalid_types(bad: object) -> None:
    with pytest.raises(AcademicCatalogValidationError):
        PublicationCatalogQuery(minimum_record_set_revision=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["ScoreForm", "SCOREFORM"])
def test_query_module_id_must_be_lowercase(bad: str) -> None:
    with pytest.raises(AcademicCatalogValidationError):
        AcademicWorkRegistrationCatalogQuery(module_id=bad)
    with pytest.raises(AcademicCatalogValidationError):
        PublicationCatalogQuery(module_id=bad)


@pytest.mark.parametrize("bad", [[], {}, 1, None])
def test_publication_state_invalid_types_use_catalog_validation(bad: object) -> None:
    with pytest.raises(AcademicCatalogValidationError):
        PublicationCatalogQuery(state=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["points", b"points", {"points": True}])
def test_capability_query_rejects_non_tuple_like_values(bad: object) -> None:
    with pytest.raises(AcademicCatalogValidationError):
        PublicationCatalogQuery(required_capabilities=bad)  # type: ignore[arg-type]


def _write_registration(
    root: Path,
    work: ModuleWorkRef,
    revision: int,
    intent: str,
    lifecycle: str,
    sources: tuple[ModuleRecordRef, ...],
) -> None:
    registration = AcademicWorkRegistration(
        "1",
        "academic_work_registration",
        work,
        revision,
        f"{work.module_id}_v1",
        f"Work {work.work_id}",
        "assessment",
        intent,  # type: ignore[arg-type]
        lifecycle,  # type: ignore[arg-type]
        NOW,
        NOW + timedelta(minutes=revision),
        sources,
    )
    base = root / "registry" / "work" / work.class_id / work.module_id / work.work_id
    _write_json(
        base / "revisions" / f"{revision}.json",
        academic_work_registration_to_dict(registration),
    )
    _write_json(
        base / "current.json",
        {
            "schema_version": "1",
            "record_type": "academic_work_registration_current",
            "work": {
                "module_id": work.module_id,
                "class_id": work.class_id,
                "work_id": work.work_id,
            },
            "registration_revision": revision,
        },
    )


def _write_publication(
    root: Path,
    publication_id: str,
    work: ModuleWorkRef,
    kind: str,
    capabilities: tuple[str, ...],
    record_set_id: str,
    revision: int,
    *,
    published_at: datetime,
    supersedes: str | None = None,
    registration_revision: int | None = None,
    manifest_contract: str = "manifest_v1",
    source_contract: str | None = "source_v1",
) -> PublicationRecord:
    source = ModuleRecordRef(
        work.module_id, "result_set", f"source_{publication_id[-4:]}", source_contract
    )
    publication = PublicationRecord(
        "1",
        "publication_record",
        publication_id,
        work,
        source,
        kind,  # type: ignore[arg-type]
        capabilities,  # type: ignore[arg-type]
        record_set_id,
        revision,
        manifest_contract,
        f"classes/{work.class_id}/modules/{work.module_id}/work/{work.work_id}/manifest.json",
        "sha256",
        publication_id.removeprefix("pub_") * 2,
        published_at,
        registration_revision,
        supersedes,
    )
    _write_json(
        root / "registry" / "publications" / f"{publication_id}.json",
        publication_record_to_dict(publication),
    )
    return publication


def test_all_period_types_lifecycles_and_sequence_order(tmp_path: Path) -> None:
    types = (
        "marking_period",
        "semester",
        "quarter",
        "trimester",
        "progress_window",
        "custom",
    )
    lifecycles = ("planned", "active", "closed", "cancelled", "planned", "active")
    periods = tuple(
        AcademicPeriod(
            f"period_{index}",
            period_type,  # type: ignore[arg-type]
            f"Period {index}",
            date(2026, 8, 20),
            date(2026, 8, 21),
            None,
            index,
            lifecycles[index - 1],  # type: ignore[arg-type]
        )
        for index, period_type in enumerate(types, start=1)
    )
    calendar = AcademicPeriodCalendar(
        "1", "academic_period_calendar", "2026-2027", 1, NOW, NOW, periods
    )
    base = tmp_path / "settings" / "academic_periods" / "2026-2027"
    _write_json(
        base / "revisions" / "1.json", academic_period_calendar_to_dict(calendar)
    )
    _write_json(
        base / "current.json",
        {
            "schema_version": "1",
            "record_type": "academic_period_calendar_current",
            "school_year": "2026-2027",
            "calendar_revision": 1,
        },
    )
    rebuild_academic_catalog(tmp_path)
    rows = query_academic_period_catalog(tmp_path)
    assert [row.sequence for row in rows] == list(range(1, 7))
    assert {row.period_type for row in rows} == set(types)
    assert {row.lifecycle for row in rows} == set(lifecycles)


def test_all_registration_intents_lifecycles_and_source_order(tmp_path: Path) -> None:
    write_class_metadata_for_class(
        tmp_path, ClassMetadata(WORK.class_id, "2026-2027", NOW, NOW, {})
    )
    intents = (
        "formative",
        "summative",
        "diagnostic",
        "practice",
        "feedback_only",
        "reporting_only",
    )
    lifecycles = ("planned", "active", "closed", "cancelled", "active", "closed")
    expected_sources = (
        ModuleRecordRef("scoreform", "assignment", "source_a", "v1"),
        ModuleRecordRef("scoreform", "assignment", "source_b", "v2"),
    )
    for index, (intent, lifecycle) in enumerate(zip(intents, lifecycles, strict=True)):
        _write_registration(
            tmp_path,
            ModuleWorkRef("scoreform", WORK.class_id, f"work_{index}"),
            1,
            intent,
            lifecycle,
            expected_sources,
        )
    rebuild_academic_catalog(tmp_path)
    rows = query_academic_work_registration_catalog(tmp_path)
    assert {row.academic_intent for row in rows} == set(intents)
    assert {row.lifecycle for row in rows} == set(lifecycles)
    assert all(row.source_records == expected_sources for row in rows)


def test_complete_publication_projection_state_capability_and_pagination_matrix(
    tmp_path: Path,
) -> None:
    write_class_metadata_for_class(
        tmp_path, ClassMetadata(WORK.class_id, "2026-2027", NOW, NOW, {})
    )
    _write_registration(
        tmp_path,
        WORK,
        1,
        "summative",
        "active",
        (ModuleRecordRef("scoreform", "assignment", "assignment_1", "v1"),),
    )
    intervention_work = ModuleWorkRef("portia", WORK.class_id, "support_1")
    first = "pub_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    current = "pub_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    withdrawn_head = "pub_cccccccccccccccccccccccccccccccc"
    intervention = "pub_dddddddddddddddddddddddddddddddd"
    _write_publication(
        tmp_path,
        first,
        WORK,
        "academic_result_set",
        ("points",),
        "primary",
        1,
        published_at=NOW,
        registration_revision=1,
    )
    _write_publication(
        tmp_path,
        current,
        WORK,
        "academic_result_set",
        (
            "points",
            "question_evidence",
            "multiple_attempts",
            "standards_ratings",
            "criterion_scores",
            "moderated_scores",
        ),
        "primary",
        4,
        published_at=NOW + timedelta(hours=1),
        supersedes=first,
        registration_revision=1,
        manifest_contract="manifest_v2",
        source_contract="source_v2",
    )
    _write_publication(
        tmp_path,
        withdrawn_head,
        WORK,
        "academic_result_set",
        ("points",),
        "secondary",
        2,
        published_at=NOW + timedelta(hours=1),
        registration_revision=1,
    )
    _write_publication(
        tmp_path,
        intervention,
        intervention_work,
        "intervention_record_set",
        ("intervention_history", "intervention_status", "intervention_outcomes"),
        "support",
        1,
        published_at=NOW + timedelta(hours=1),
    )
    for publication_id in (first, withdrawn_head):
        withdrawal = PublicationWithdrawal(
            "1",
            "publication_withdrawal",
            publication_id,
            NOW + timedelta(hours=2),
            "Withdrawn fixture",
        )
        _write_json(
            tmp_path / "registry" / "withdrawals" / f"{publication_id}.json",
            publication_withdrawal_to_dict(withdrawal),
        )
    rebuild_academic_catalog(tmp_path)
    query_states: tuple[PublicationCatalogState, ...] = (
        "current",
        "series_heads",
        "historical",
        "withdrawn",
        "all",
    )
    states = {
        state: [
            row.publication_id
            for row in query_publication_catalog(
                tmp_path,
                PublicationCatalogQuery(state=state),
            )
        ]
        for state in query_states
    }
    assert set(states["current"]) == {current, intervention}
    assert set(states["series_heads"]) == {current, withdrawn_head, intervention}
    assert states["historical"] == [first]
    assert set(states["withdrawn"]) == {first, withdrawn_head}
    assert set(states["all"]) == {first, current, withdrawn_head, intervention}
    all_of = query_publication_catalog(
        tmp_path,
        PublicationCatalogQuery(
            required_capabilities=("points", "standards_ratings", "moderated_scores"),
            producer_contract_version="scoreform_v1",
            manifest_contract_version="manifest_v2",
            source_contract_version="source_v2",
            record_set_id="primary",
            minimum_record_set_revision=4,
            state="all",
        ),
    )
    assert [row.publication_id for row in all_of] == [current]
    tied = query_publication_catalog(
        tmp_path, PublicationCatalogQuery(state="all", limit=2, offset=1)
    )
    expected_tied = sorted((current, withdrawn_head, intervention))[1:3]
    assert [row.publication_id for row in tied] == expected_tied
    capabilities = {
        capability
        for row in query_publication_catalog(
            tmp_path, PublicationCatalogQuery(state="all")
        )
        for capability in row.capabilities
    }
    assert capabilities == PUBLICATION_CAPABILITIES
    intervention_row = next(
        row
        for row in query_publication_catalog(
            tmp_path, PublicationCatalogQuery(state="all")
        )
        if row.publication_id == intervention
    )
    assert intervention_row.academic_work_registration_revision is None
    assert intervention_row.referenced_registration_lifecycle is None


def test_every_identity_lifecycle_and_kind_filter_is_exercised(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    periods = query_academic_period_catalog(
        tmp_path,
        AcademicPeriodCatalogQuery(
            school_year="2026-2027",
            period_type="quarter",
            lifecycle="closed",
            current_calendar_only=True,
            active_on=date(2026, 9, 1),
            limit=1,
            offset=0,
        ),
    )
    assert [row.period_id for row in periods] == ["quarter_1"]
    registrations = query_academic_work_registration_catalog(
        tmp_path,
        AcademicWorkRegistrationCatalogQuery(
            school_year="2026-2027",
            class_id=WORK.class_id,
            module_id=WORK.module_id,
            work_id=WORK.work_id,
            producer_contract_version="scoreform_1",
            academic_intent="summative",
            lifecycle="active",
            current_only=True,
            limit=1,
            offset=0,
        ),
    )
    assert len(registrations) == 1
    publications = query_publication_catalog(
        tmp_path,
        PublicationCatalogQuery(
            school_year="2026-2027",
            class_id=WORK.class_id,
            module_id=WORK.module_id,
            work_id=WORK.work_id,
            publication_kind="academic_result_set",
            producer_contract_version="scoreform_1",
            manifest_contract_version="manifest_v1",
            source_contract_version="source_v1",
            referenced_registration_lifecycle="active",
            current_registration_lifecycle="active",
            record_set_id="primary",
            minimum_record_set_revision=1,
            state="all",
            limit=1,
            offset=1,
        ),
    )
    assert len(publications) == 1
    assert publications[0].publication_kind == "academic_result_set"


def test_exact_schema_constraints_indexes_and_query_plans(tmp_path: Path) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    with sqlite3.connect(path) as connection:
        user_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert user_tables == set(catalog_module._REQUIRED_COLUMNS)
        for table, expected_columns in catalog_module._REQUIRED_COLUMNS.items():
            info = connection.execute(f"PRAGMA table_info({table})").fetchall()
            assert tuple(row[1] for row in info) == expected_columns
        assert tuple(
            row[1]
            for row in connection.execute("PRAGMA table_info(catalog_sources)")
            if row[5]
        ) == ("relative_path",)
        publication_indexes = {
            row[1]: tuple(
                item[2] for item in connection.execute(f"PRAGMA index_info({row[1]})")
            )
            for row in connection.execute("PRAGMA index_list(publications)")
        }
        assert publication_indexes["idx_publications_work_kind"] == (
            "class_id",
            "module_id",
            "work_id",
            "publication_kind",
        )
        assert publication_indexes["idx_publications_current_kind_time"] == (
            "is_current_selectable",
            "publication_kind",
            "published_at_utc",
        )
        assert any(
            row[2] == "academic_work_registrations"
            for row in connection.execute("PRAGMA foreign_key_list(publications)")
        )
        schema_sql = "\n".join(
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_schema WHERE type='table' ORDER BY name"
            )
        )
        assert "CHECK" in schema_sql
        assert (
            "UNIQUE(class_id,module_id,work_id,publication_kind,record_set_id,record_set_revision)"
            in schema_sql
        )
        plans = {
            "idx_publications_current_kind_time": connection.execute(
                "EXPLAIN QUERY PLAN SELECT publication_id FROM publications "
                "INDEXED BY idx_publications_current_kind_time "
                "WHERE is_current_selectable=1 AND publication_kind=?",
                ("academic_result_set",),
            ).fetchall(),
            "idx_registration_work": connection.execute(
                "EXPLAIN QUERY PLAN SELECT registration_revision FROM academic_work_registrations "
                "INDEXED BY idx_registrations_work_current WHERE class_id=? AND module_id=? "
                "AND work_id=? AND is_current=1",
                (WORK.class_id, WORK.module_id, WORK.work_id),
            ).fetchall(),
            "idx_periods_lifecycle_type": connection.execute(
                "EXPLAIN QUERY PLAN SELECT period_id FROM academic_periods "
                "INDEXED BY idx_periods_lifecycle_type WHERE school_year=? "
                "AND lifecycle=? AND period_type=?",
                ("2026-2027", "closed", "quarter"),
            ).fetchall(),
        }
    assert "idx_publications_current_kind_time" in " ".join(
        str(row) for row in plans["idx_publications_current_kind_time"]
    )
    assert "idx_registrations_work_current" in " ".join(
        str(row) for row in plans["idx_registration_work"]
    )
    assert "idx_periods_lifecycle_type" in " ".join(
        str(row) for row in plans["idx_periods_lifecycle_type"]
    )


@pytest.mark.parametrize(
    "source_kind",
    [
        "class_metadata",
        "calendar_pointer",
        "calendar_revision",
        "registration_pointer",
        "registration_revision",
        "publication",
        "withdrawal",
    ],
)
def test_each_canonical_source_content_race_preserves_existing_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_kind: str
) -> None:
    first, second = _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    rebuild_academic_catalog(tmp_path)
    catalog_path = academic_catalog_path(tmp_path)
    before = catalog_path.read_bytes()
    paths = {
        "class_metadata": tmp_path / "classes" / WORK.class_id / "class.json",
        "calendar_pointer": tmp_path
        / "settings"
        / "academic_periods"
        / "2026-2027"
        / "current.json",
        "calendar_revision": tmp_path
        / "settings"
        / "academic_periods"
        / "2026-2027"
        / "revisions"
        / "2.json",
        "registration_pointer": tmp_path
        / "registry"
        / "work"
        / WORK.class_id
        / WORK.module_id
        / WORK.work_id
        / "current.json",
        "registration_revision": tmp_path
        / "registry"
        / "work"
        / WORK.class_id
        / WORK.module_id
        / WORK.work_id
        / "revisions"
        / "2.json",
        "publication": tmp_path / "registry" / "publications" / f"{first}.json",
        "withdrawal": tmp_path / "registry" / "withdrawals" / f"{second}.json",
    }
    original = catalog_module._read_sources
    calls = 0

    def racing_read(root: Path, source_paths: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 3:
            target = paths[source_kind]
            target.write_bytes(target.read_bytes() + b" ")
        return original(root, source_paths)  # type: ignore[arg-type]

    monkeypatch.setattr(catalog_module, "_read_sources", racing_read)
    with pytest.raises(AcademicCatalogConflictError):
        rebuild_academic_catalog(tmp_path)
    assert catalog_path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()


def test_temporary_database_creation_failure_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()

    def fail_mkstemp(*_args: object, **_kwargs: object) -> tuple[int, str]:
        raise OSError("injected temporary creation failure")

    monkeypatch.setattr(tempfile, "mkstemp", fail_mkstemp)
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before


def test_schema_creation_failure_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(catalog_module, "_SCHEMA", "THIS IS NOT SQL;")
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure_point", ["integrity", "commit"])
def test_integrity_and_commit_failures_preserve_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()

    def fail(_connection: sqlite3.Connection) -> None:
        if failure_point == "integrity":
            raise AcademicCatalogIntegrityError("injected integrity failure")
        raise sqlite3.OperationalError("injected commit failure")

    monkeypatch.setattr(
        catalog_module,
        "_check_candidate_integrity"
        if failure_point == "integrity"
        else "_commit_candidate",
        fail,
    )
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before


def test_file_fsync_failure_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before


def test_temporary_readback_failure_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    original = catalog_module._read_connection

    def fail_candidate_read(candidate: Path) -> sqlite3.Connection:
        if candidate.name.startswith(".catalog.sqlite."):
            raise AcademicCatalogReadError("injected temporary read-back failure")
        return original(candidate)

    monkeypatch.setattr(catalog_module, "_read_connection", fail_candidate_read)
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before


def test_source_reinventory_failure_is_conflict_and_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    original = catalog_module._read_sources
    calls = 0

    def fail_second_inventory(root: Path, source_paths: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise catalog_module.AcademicCatalogSourceError(
                "injected inventory failure"
            )
        return original(root, source_paths)  # type: ignore[arg-type]

    monkeypatch.setattr(catalog_module, "_read_sources", fail_second_inventory)
    with pytest.raises(AcademicCatalogConflictError):
        rebuild_academic_catalog(tmp_path)
    assert path.read_bytes() == before


def test_directory_fsync_failure_is_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        catalog_module._fsync_directory(tmp_path)
        return

    def fail_open(*_args: object, **_kwargs: object) -> int:
        raise OSError("injected directory fsync open failure")

    monkeypatch.setattr(os, "open", fail_open)
    catalog_module._fsync_directory(tmp_path)


@pytest.mark.parametrize("collection", ["publications", "withdrawals"])
@pytest.mark.parametrize(
    "entry_kind", ["hidden_file", "hidden_directory", "malformed_file", "directory"]
)
def test_strict_publication_collections_reject_every_arbitrary_entry(
    tmp_path: Path, collection: str, entry_kind: str
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    catalog_path = academic_catalog_path(tmp_path)
    before = catalog_path.read_bytes()
    directory = tmp_path / "registry" / collection
    name = ".hidden.json" if entry_kind.startswith("hidden") else "arbitrary.json"
    entry = directory / name
    if entry_kind.endswith("directory") or entry_kind == "directory":
        entry.mkdir()
    else:
        entry.write_text("{}\n", encoding="utf-8")
    entry_bytes = None if entry.is_dir() else entry.read_bytes()

    with pytest.raises(catalog_module.AcademicCatalogSourceError):
        rebuild_academic_catalog(tmp_path)

    assert catalog_path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()
    assert not tuple(catalog_path.parent.glob(".catalog.sqlite.*.tmp*"))
    assert entry.exists()
    if entry_bytes is not None:
        assert entry.read_bytes() == entry_bytes


@pytest.mark.parametrize("collection", ["publications", "withdrawals"])
def test_strict_publication_collection_inspection_failure_preserves_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collection: str
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    catalog_path = academic_catalog_path(tmp_path)
    before = catalog_path.read_bytes()
    entry = next((tmp_path / "registry" / collection).iterdir())
    original_is_file = Path.is_file

    def fail_inspection(self: Path) -> bool:
        if self == entry:
            raise OSError("injected collection inspection failure")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", fail_inspection)
    with pytest.raises(catalog_module.AcademicCatalogSourceError):
        rebuild_academic_catalog(tmp_path)
    assert catalog_path.read_bytes() == before
    assert entry.exists()
    assert not academic_catalog_lock_path(tmp_path).exists()
    assert not tuple(catalog_path.parent.glob(".catalog.sqlite.*.tmp*"))


@pytest.mark.parametrize("collection", ["publications", "withdrawals"])
def test_strict_publication_collections_accept_valid_files_only(
    tmp_path: Path, collection: str
) -> None:
    _populated_workspace(tmp_path)
    assert all(
        item.is_file() and catalog_module._PUBLICATION_FILE.fullmatch(item.name)
        for item in (tmp_path / "registry" / collection).iterdir()
    )
    rebuild_academic_catalog(tmp_path)


def _assert_every_catalog_read_rejects_history(root: Path) -> None:
    operations = (
        load_academic_catalog_metadata,
        query_academic_period_catalog,
        query_academic_work_registration_catalog,
        query_publication_catalog,
    )
    for operation in operations:
        with pytest.raises(AcademicCatalogIntegrityError):
            operation(root)


@pytest.mark.parametrize(
    "corruption",
    [
        "successor_below",
        "successor_timestamp",
        "registration_transition",
        "calendar_transition",
        "withdrawal_chronology",
    ],
)
def test_complete_semantic_history_tampering_is_rejected_by_every_read(
    tmp_path: Path, corruption: str
) -> None:
    first, second = _populated_workspace(tmp_path)
    _add_calendar_and_registration_history(tmp_path)
    rebuild_academic_catalog(tmp_path)
    statements = {
        "successor_below": (
            f"UPDATE publications SET record_set_revision=4 WHERE publication_id='{first}'",
        ),
        "successor_timestamp": (
            f"UPDATE publications SET published_at_utc='2026-07-28T11:00:00.000000+00:00' WHERE publication_id='{second}'",
        ),
        "registration_transition": (
            "UPDATE academic_work_registrations SET created_at_utc='2026-07-28T13:00:00.000000+00:00' WHERE registration_revision=2",
        ),
        "calendar_transition": (
            "UPDATE academic_period_calendars SET created_at_utc='2026-07-28T13:00:00.000000+00:00' WHERE calendar_revision=2",
        ),
        "withdrawal_chronology": (
            f"UPDATE publications SET withdrawn_at_utc='2026-07-28T12:30:00.000000+00:00' WHERE publication_id='{second}'",
        ),
    }[corruption]
    _tamper(academic_catalog_path(tmp_path), *statements)
    _assert_every_catalog_read_rejects_history(tmp_path)


def test_equal_successor_revision_is_blocked_by_supported_schema(
    tmp_path: Path,
) -> None:
    first, _ = _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"):
        _tamper(
            academic_catalog_path(tmp_path),
            f"UPDATE publications SET record_set_revision=3 WHERE publication_id='{first}'",
        )


def test_catalog_publication_direct_model_rejects_early_withdrawal(
    tmp_path: Path,
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    publication = query_publication_catalog(
        tmp_path, PublicationCatalogQuery(state="withdrawn")
    )[0]
    with pytest.raises(AcademicCatalogValidationError, match="must not precede"):
        replace(publication, withdrawn_at=publication.published_at - timedelta(seconds=1))


def _replace_catalog_schema(root: Path, transform: object) -> None:
    path = academic_catalog_path(root)
    replacement = path.with_name("incompatible.sqlite")
    schema = transform(catalog_module._SCHEMA)  # type: ignore[operator]
    source = sqlite3.connect(path)
    target = sqlite3.connect(replacement)
    try:
        target.execute(f"PRAGMA application_id={ACADEMIC_CATALOG_APPLICATION_ID}")
        target.execute(f"PRAGMA user_version={ACADEMIC_CATALOG_SCHEMA_VERSION}")
        target.execute("PRAGMA foreign_keys=OFF")
        target.executescript(schema)
        source.row_factory = sqlite3.Row
        for row in source.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        ):
            table = row["name"]
            columns = [
                item[1] for item in source.execute(f'PRAGMA table_info("{table}")')
            ]
            placeholders = ",".join("?" for _ in columns)
            target.executemany(
                f'INSERT INTO "{table}" VALUES ({placeholders})',
                source.execute(f'SELECT * FROM "{table}"').fetchall(),
            )
        target.commit()
    finally:
        target.close()
        source.close()
    os.replace(replacement, path)


@pytest.mark.parametrize(
    "schema_change",
    [
        "missing_primary_key",
        "primary_key_order",
        "removed_foreign_key",
        "wrong_foreign_target",
        "wrong_index_columns",
        "changed_index_order",
        "removed_unique",
        "removed_check",
        "extra_table",
        "extra_index",
    ],
)
def test_exact_runtime_schema_signature_rejects_structural_tampering(
    tmp_path: Path, schema_change: str
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)

    def transform(schema: str) -> str:
        changes = {
            "missing_primary_key": (
                "relative_path TEXT PRIMARY KEY",
                "relative_path TEXT",
            ),
            "primary_key_order": (
                "PRIMARY KEY(school_year, calendar_revision, period_id)",
                "PRIMARY KEY(calendar_revision, school_year, period_id)",
            ),
            "removed_foreign_key": (
                ", FOREIGN KEY(class_id) REFERENCES class_context(class_id)",
                "",
            ),
            "wrong_foreign_target": (
                "FOREIGN KEY(class_id) REFERENCES class_context(class_id)",
                "FOREIGN KEY(class_id) REFERENCES catalog_sources(relative_path)",
            ),
            "wrong_index_columns": (
                "idx_publications_work_kind ON publications(class_id,module_id,work_id,publication_kind)",
                "idx_publications_work_kind ON publications(publication_id)",
            ),
            "changed_index_order": (
                "idx_publications_record_set ON publications(record_set_id,record_set_revision)",
                "idx_publications_record_set ON publications(record_set_revision,record_set_id)",
            ),
            "removed_unique": (
                "supersedes_publication_id TEXT UNIQUE",
                "supersedes_publication_id TEXT",
            ),
            "removed_check": ("position INTEGER NOT NULL CHECK(position>=0)", "position INTEGER NOT NULL"),
            "extra_table": ("", "CREATE TABLE unexpected_table (value TEXT);\n"),
            "extra_index": (
                "",
                "CREATE INDEX unexpected_index ON publications(publication_id);\n",
            ),
        }
        old, new = changes[schema_change]
        if old:
            assert old in schema
            return schema.replace(old, new, 1)
        return schema + new

    _replace_catalog_schema(tmp_path, transform)
    for operation in (load_academic_catalog_metadata, query_publication_catalog):
        with pytest.raises(AcademicCatalogCompatibilityError):
            operation(tmp_path)


def _rename_inventory_source(root: Path, old: str, new: str) -> None:
    path = academic_catalog_path(root)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "UPDATE catalog_sources SET relative_path=? WHERE relative_path=?",
            (new, old),
        )
        sources = tuple(
            _Source(row["relative_path"], row["size_bytes"], row["sha256"], b"")
            for row in connection.execute(
                "SELECT relative_path,size_bytes,sha256 FROM catalog_sources"
            )
        )
        connection.execute(
            "UPDATE catalog_metadata SET source_snapshot_sha256=?",
            (_snapshot(sources),),
        )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "registry/publications/pub_11111111111111111111111111111111.json",
            "registry/routes/pub_11111111111111111111111111111111.json",
        ),
        (
            "registry/publications/pub_11111111111111111111111111111111.json",
            "registry/publications/pub_33333333333333333333333333333333.json",
        ),
    ],
)
def test_catalog_source_namespace_rejects_arbitrary_and_mismatched_paths(
    tmp_path: Path, old: str, new: str
) -> None:
    _populated_workspace(tmp_path)
    rebuild_academic_catalog(tmp_path)
    _rename_inventory_source(tmp_path, old, new)
    _assert_every_catalog_read_rejects_history(tmp_path)


@pytest.mark.parametrize("sidecar", ["", "-journal", "-wal", "-shm"])
def test_candidate_cleanup_failure_reports_exact_remaining_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sidecar: str
) -> None:
    rebuild_academic_catalog(tmp_path)
    catalog_path = academic_catalog_path(tmp_path)
    before = catalog_path.read_bytes()
    created: list[Path] = []
    original_mkstemp = tempfile.mkstemp
    original_unlink = Path.unlink

    def tracked_mkstemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | os.PathLike[str] | None = None,
        text: bool = False,
    ) -> tuple[int, str]:
        descriptor, name = original_mkstemp(suffix, prefix, dir, text)
        candidate = Path(name)
        created.append(candidate)
        return descriptor, name

    def fail_unlink(self: Path, *args: object, **kwargs: object) -> None:
        failed = Path(f"{created[0]}{sidecar}") if created else None
        if self == failed:
            raise OSError("injected candidate cleanup failure")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    original_read_connection = catalog_module._read_connection

    def fail_candidate_read(candidate: Path) -> sqlite3.Connection:
        if created and candidate == created[0]:
            if sidecar:
                Path(f"{created[0]}{sidecar}").write_bytes(b"injected")
            raise AcademicCatalogReadError("injected primary failure")
        return original_read_connection(candidate)

    monkeypatch.setattr(tempfile, "mkstemp", tracked_mkstemp)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    monkeypatch.setattr(catalog_module, "_read_connection", fail_candidate_read)
    with pytest.raises(AcademicCatalogBuildError) as captured:
        rebuild_academic_catalog(tmp_path)
    failed_path = Path(f"{created[0]}{sidecar}")
    assert str(failed_path) in str(captured.value)
    assert failed_path.exists()
    assert catalog_path.read_bytes() == before
    assert not academic_catalog_lock_path(tmp_path).exists()


@pytest.mark.parametrize("replacement_succeeds", [False, True])
def test_rebuild_lock_cleanup_failure_never_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement_succeeds: bool
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    before = path.read_bytes()
    lock = academic_catalog_lock_path(tmp_path)
    original_unlink = Path.unlink

    def fail_lock(self: Path, *args: object, **kwargs: object) -> None:
        if self == lock:
            raise OSError("injected lock cleanup failure")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", fail_lock)
    if not replacement_succeeds:
        monkeypatch.setattr(
            catalog_module,
            "_load_projection",
            lambda _root: (_ for _ in ()).throw(
                catalog_module.AcademicCatalogSourceError("injected source failure")
            ),
        )
    with pytest.raises(AcademicCatalogBuildError) as captured:
        rebuild_academic_catalog(tmp_path)
    assert str(lock) in str(captured.value)
    assert lock.exists()
    if not replacement_succeeds:
        assert path.read_bytes() == before
        assert isinstance(captured.value.__cause__, catalog_module.AcademicCatalogSourceError)
    else:
        assert path.exists()
        assert "installed catalog is preserved" in str(captured.value)


def test_removal_lock_cleanup_failure_reports_completed_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    lock = academic_catalog_lock_path(tmp_path)
    original_unlink = Path.unlink

    def fail_lock(self: Path, *args: object, **kwargs: object) -> None:
        if self == lock:
            raise OSError("injected removal lock failure")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", fail_lock)
    with pytest.raises(AcademicCatalogBuildError, match="removal completed") as captured:
        remove_academic_catalog(tmp_path)
    assert not path.exists()
    assert lock.exists()
    assert str(lock) in str(captured.value)


def test_descriptor_close_failure_still_cleans_known_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    created: list[Path] = []
    descriptor_to_fail: list[int] = []
    original_mkstemp = tempfile.mkstemp
    original_close = os.close

    def tracked_mkstemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | os.PathLike[str] | None = None,
        text: bool = False,
    ) -> tuple[int, str]:
        descriptor, name = original_mkstemp(suffix, prefix, dir, text)
        descriptor_to_fail.append(descriptor)
        created.append(Path(name))
        return descriptor, name

    def fail_close(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor_to_fail and descriptor == descriptor_to_fail[0]:
            raise OSError("injected descriptor close failure")

    monkeypatch.setattr(tempfile, "mkstemp", tracked_mkstemp)
    monkeypatch.setattr(os, "close", fail_close)
    with pytest.raises(AcademicCatalogBuildError):
        rebuild_academic_catalog(tmp_path)
    assert created and not created[0].exists()
    assert all(not Path(f"{created[0]}{suffix}").exists() for suffix in ("-journal", "-wal", "-shm"))
    assert not academic_catalog_lock_path(tmp_path).exists()


def test_multiple_candidate_cleanup_failures_are_all_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    created: list[Path] = []
    original_mkstemp = tempfile.mkstemp
    original_unlink = Path.unlink

    def tracked_mkstemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | os.PathLike[str] | None = None,
        text: bool = False,
    ) -> tuple[int, str]:
        descriptor, name = original_mkstemp(suffix, prefix, dir, text)
        created.append(Path(name))
        for suffix in ("-wal", "-shm"):
            Path(f"{name}{suffix}").write_bytes(b"injected")
        return descriptor, name

    def fail_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if created and self in {Path(f"{created[0]}-wal"), Path(f"{created[0]}-shm")}:
            raise OSError(f"injected cleanup failure for {self.name}")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tempfile, "mkstemp", tracked_mkstemp)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    monkeypatch.setattr(
        catalog_module,
        "_check_candidate_integrity",
        lambda _connection: (_ for _ in ()).throw(
            AcademicCatalogIntegrityError("injected primary failure")
        ),
    )
    with pytest.raises(AcademicCatalogBuildError) as captured:
        rebuild_academic_catalog(tmp_path)
    assert f"{created[0]}-wal" in str(captured.value)
    assert f"{created[0]}-shm" in str(captured.value)


def test_removal_sidecar_failure_preserves_main_and_reports_truthfully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuild_academic_catalog(tmp_path)
    path = academic_catalog_path(tmp_path)
    journal, wal, shm = _sidecars(path)
    for sidecar in (journal, wal, shm):
        sidecar.write_bytes(sidecar.name.encode())
    unrelated = path.parent / "unrelated.txt"
    unrelated.write_bytes(b"unchanged")
    original_unlink = Path.unlink

    def fail_wal(self: Path, *args: object, **kwargs: object) -> None:
        if self == wal:
            raise OSError("injected removal sidecar failure")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", fail_wal)
    with pytest.raises(AcademicCatalogBuildError) as captured:
        remove_academic_catalog(tmp_path)
    assert path.exists()
    assert not journal.exists()
    assert wal.exists()
    assert not shm.exists()
    assert unrelated.read_bytes() == b"unchanged"
    assert "catalog is preserved" in str(captured.value)
    assert str(wal) in str(captured.value)
    assert not academic_catalog_lock_path(tmp_path).exists()
