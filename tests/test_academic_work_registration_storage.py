from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, cast

import pytest

import pds_core.academic_work_registration_storage as storage
from pds_core.academic_period_storage import (
    academic_period_current_path,
    academic_period_revision_path,
    write_academic_period_calendar,
)
from pds_core.academic_periods import AcademicPeriodCalendar
from pds_core.academic_work_registrations import (
    AcademicWorkRegistration,
    AcademicWorkRegistrationLifecycle,
    academic_work_registration_to_dict,
)
from pds_core.academic_work_registration_storage import (
    ACADEMIC_WORK_REGISTRATION_CURRENT_RECORD_TYPE,
    ACADEMIC_WORK_REGISTRATION_CURRENT_SCHEMA_VERSION,
    AcademicWorkRegistrationConflictError,
    AcademicWorkRegistrationIntegrityError,
    AcademicWorkRegistrationNotFoundError,
    AcademicWorkRegistrationReadError,
    AcademicWorkRegistrationWriteError,
    get_current_academic_work_registration_revision,
    list_academic_work_registration_refs,
    list_academic_work_registration_revisions,
    load_academic_work_registration_revision,
    load_current_academic_work_registration,
    write_academic_work_registration,
)
from pds_core.registry_paths import (
    academic_work_registration_current_path,
    academic_work_registration_revision_path,
)
from pds_core.class_metadata import create_class_metadata, write_class_metadata_for_class
from pds_core.route_registrations import write_route_registration
from pds_core.routes import module_work_dir
from pds_core.routing_models import (
    PDS2_SCHEMA,
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RouteRegistration,
)
from pds_core.school_years import close_school_year, open_school_year, school_year_state_path
from pds_core.workspace import ensure_workspace_root


NOW = datetime(2026, 7, 27, 13, tzinfo=timezone.utc)


def registration(work: ModuleWorkRef, revision: int = 1) -> AcademicWorkRegistration:
    return AcademicWorkRegistration(
        schema_version="1",
        record_type="academic_work_registration",
        work=work,
        registration_revision=revision,
        producer_contract_version="1",
        title="Essay",
        work_kind="assignment",
        academic_intent="summative",
        lifecycle="active",
        created_at=NOW,
        updated_at=NOW,
        source_records=(),
    )


def prepare(tmp_path: Path, work: ModuleWorkRef) -> None:
    module_work_dir(tmp_path, work).mkdir(parents=True)


def test_write_load_update_list_and_preserve_history(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class_b", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    path = write_academic_work_registration(
        tmp_path, first, expected_current_revision=None
    )
    original = path.read_bytes()
    assert original.endswith(b"\n")
    assert load_current_academic_work_registration(tmp_path, work) == first
    assert get_current_academic_work_registration_revision(tmp_path, work) == 1
    second = replace(first, registration_revision=3, title="Revised Essay")
    write_academic_work_registration(tmp_path, second, expected_current_revision=1)
    assert list_academic_work_registration_revisions(tmp_path, work) == (1, 3)
    assert load_current_academic_work_registration(tmp_path, work) == second
    assert path.read_bytes() == original
    assert list_academic_work_registration_refs(tmp_path) == (work,)


def test_writer_requires_existing_producer_root_without_registry_mutation(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    with pytest.raises(AcademicWorkRegistrationWriteError):
        write_academic_work_registration(
            tmp_path, registration(work), expected_current_revision=None
        )
    assert not (tmp_path / "registry").exists()


def test_strict_collisions_expectations_and_lock(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    with pytest.raises(AcademicWorkRegistrationConflictError):
        write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    with pytest.raises(AcademicWorkRegistrationConflictError):
        write_academic_work_registration(
            tmp_path, replace(first, registration_revision=2), expected_current_revision=99
        )
    lock = academic_work_registration_current_path(tmp_path, work).parent / ".write.lock"
    lock.write_text("occupied", encoding="utf-8")
    with pytest.raises(AcademicWorkRegistrationConflictError):
        write_academic_work_registration(
            tmp_path, replace(first, registration_revision=2), expected_current_revision=1
        )
    assert lock.read_text(encoding="utf-8") == "occupied"


@pytest.mark.parametrize("payload", [b"\xff", b'{"x": NaN}', b'{"x":1,"x":2}'])
def test_revision_reader_rejects_invalid_json(tmp_path: Path, payload: bytes) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    path = academic_work_registration_revision_path(tmp_path, work, 1)
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    with pytest.raises(AcademicWorkRegistrationReadError):
        load_academic_work_registration_revision(tmp_path, work, 1)


def test_missing_revision_and_missing_pointer_are_distinct(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    assert load_current_academic_work_registration(tmp_path, work) is None
    with pytest.raises(AcademicWorkRegistrationNotFoundError):
        load_academic_work_registration_revision(tmp_path, work, 1)


def test_pointer_never_promotes_orphan_and_validates_identity(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    write_academic_work_registration(tmp_path, registration(work), expected_current_revision=None)
    pointer = academic_work_registration_current_path(tmp_path, work)
    data = json.loads(pointer.read_text(encoding="utf-8"))
    data["work"]["work_id"] = "other"
    pointer.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AcademicWorkRegistrationIntegrityError):
        load_current_academic_work_registration(tmp_path, work)


def test_orphan_only_work_is_omitted(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    path = academic_work_registration_revision_path(tmp_path, work, 1)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "schema_version": "1", "record_type": "academic_work_registration",
            "work": {"module_id": "quillan", "class_id": "class", "work_id": "essay"},
            "registration_revision": 1, "producer_contract_version": "1",
            "title": "Essay", "work_kind": "assignment", "academic_intent": "summative",
            "lifecycle": "active", "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(), "source_records": [],
        }), encoding="utf-8"
    )
    assert list_academic_work_registration_refs(tmp_path) == ()


def revision_bytes(value: AcademicWorkRegistration) -> bytes:
    return (
        json.dumps(
            academic_work_registration_to_dict(value),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def pointer_bytes(value: AcademicWorkRegistration) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": ACADEMIC_WORK_REGISTRATION_CURRENT_SCHEMA_VERSION,
                "record_type": ACADEMIC_WORK_REGISTRATION_CURRENT_RECORD_TYPE,
                "work": {
                    "module_id": value.work.module_id,
                    "class_id": value.work.class_id,
                    "work_id": value.work.work_id,
                },
                "registration_revision": value.registration_revision,
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_raw_revision(tmp_path: Path, value: AcademicWorkRegistration, raw: bytes) -> Path:
    path = academic_work_registration_revision_path(
        tmp_path, value.work, value.registration_revision
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def test_initial_producer_root_file_fails_without_registry(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    path = module_work_dir(tmp_path, work)
    path.parent.mkdir(parents=True)
    path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(AcademicWorkRegistrationWriteError, match="directory"):
        write_academic_work_registration(
            tmp_path, registration(work), expected_current_revision=None
        )
    assert not (tmp_path / "registry").exists()


@pytest.mark.parametrize("lifecycle", ["closed", "cancelled"])
def test_update_and_history_survive_removed_producer_root(
    tmp_path: Path, lifecycle: str
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    shutil.rmtree(module_work_dir(tmp_path, work))
    later = replace(
        first,
        registration_revision=2,
        lifecycle=cast(AcademicWorkRegistrationLifecycle, lifecycle),
    )
    write_academic_work_registration(tmp_path, later, expected_current_revision=1)
    assert load_current_academic_work_registration(tmp_path, work) == later
    assert load_academic_work_registration_revision(tmp_path, work, 1) == first


def test_initial_write_exact_bytes_paths_and_cleanup(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "english10_p2", "literary_analysis")
    prepare(tmp_path, work)
    value = registration(work)
    path = write_academic_work_registration(
        tmp_path, value, expected_current_revision=None
    )
    assert path == academic_work_registration_revision_path(tmp_path, work, 1)
    assert path.read_bytes() == revision_bytes(value)
    pointer = academic_work_registration_current_path(tmp_path, work)
    assert pointer.read_bytes() == pointer_bytes(value)
    assert load_academic_work_registration_revision(tmp_path, work, 1) == value
    assert load_current_academic_work_registration(tmp_path, work) == value
    assert get_current_academic_work_registration_revision(tmp_path, work) == 1
    assert not (pointer.parent / ".write.lock").exists()
    assert not tuple(pointer.parent.glob(".current.json.*.tmp"))


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"{",
        b'{"value": NaN}',
        b'{"value": Infinity}',
        b'{"value": -Infinity}',
        b'{"schema_version":"1","schema_version":"1"}',
        b'{"work":{"module_id":"quillan","module_id":"quillan"}}',
        b'{"source_records":[{"module_id":"quillan","module_id":"quillan"}]}',
        b"[]",
    ],
)
def test_revision_reader_rejects_all_strict_json_failures(
    tmp_path: Path, raw: bytes
) -> None:
    value = registration(ModuleWorkRef("quillan", "class", "essay"))
    write_raw_revision(tmp_path, value, raw)
    before = tuple(tmp_path.rglob("*"))
    with pytest.raises(AcademicWorkRegistrationReadError):
        load_academic_work_registration_revision(tmp_path, value.work, 1)
    assert tuple(tmp_path.rglob("*")) == before


@pytest.mark.parametrize(
    ("field", "replacement", "error_type"),
    [
        ("schema_version", "2", AcademicWorkRegistrationReadError),
        ("record_type", "wrong", AcademicWorkRegistrationReadError),
        ("title", "", AcademicWorkRegistrationReadError),
        ("registration_revision", 2, AcademicWorkRegistrationIntegrityError),
    ],
)
def test_revision_reader_rejects_model_and_embedded_revision_errors(
    tmp_path: Path, field: str, replacement: object, error_type: type[Exception]
) -> None:
    value = registration(ModuleWorkRef("quillan", "class", "essay"))
    data = academic_work_registration_to_dict(value)
    data[field] = replacement
    write_raw_revision(tmp_path, value, json.dumps(data).encode())
    with pytest.raises(error_type):
        load_academic_work_registration_revision(tmp_path, value.work, 1)


def test_revision_reader_rejects_embedded_work_and_needs_no_producer(
    tmp_path: Path,
) -> None:
    value = registration(ModuleWorkRef("quillan", "class", "essay"))
    data = academic_work_registration_to_dict(value)
    work_data = data["work"]
    assert isinstance(work_data, dict)
    work_data["work_id"] = "other"
    write_raw_revision(tmp_path, value, json.dumps(data).encode())
    assert not module_work_dir(tmp_path, value.work).exists()
    with pytest.raises(AcademicWorkRegistrationIntegrityError):
        load_academic_work_registration_revision(tmp_path, value.work, 1)


def test_valid_historical_load_needs_no_producer_root(tmp_path: Path) -> None:
    value = registration(ModuleWorkRef("uninstalled_producer", "class", "essay"))
    write_raw_revision(tmp_path, value, revision_bytes(value))
    assert load_academic_work_registration_revision(tmp_path, value.work, 1) == value


def write_pointer(tmp_path: Path, work: ModuleWorkRef, raw: bytes) -> Path:
    path = academic_work_registration_current_path(tmp_path, work)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff", b"{", b"[]", b'{"x":NaN}', b'{"x":Infinity}',
        b'{"x":-Infinity}', b'{"schema_version":"1","schema_version":"1"}',
        b'{"work":{"module_id":"quillan","module_id":"quillan"}}',
    ],
)
def test_current_pointer_rejects_strict_json_failures(tmp_path: Path, raw: bytes) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    write_pointer(tmp_path, work, raw)
    with pytest.raises(AcademicWorkRegistrationReadError):
        load_current_academic_work_registration(tmp_path, work)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2"},
        {"record_type": "wrong"},
        {"registration_revision": 0},
        {"registration_revision": True},
        {"unknown": 1},
    ],
)
def test_current_pointer_rejects_invalid_shape(
    tmp_path: Path, change: dict[str, object]
) -> None:
    value = registration(ModuleWorkRef("quillan", "class", "essay"))
    data = json.loads(pointer_bytes(value))
    data.update(change)
    write_pointer(tmp_path, value.work, json.dumps(data).encode())
    with pytest.raises(AcademicWorkRegistrationReadError):
        load_current_academic_work_registration(tmp_path, value.work)


def test_current_pointer_rejects_each_missing_key(tmp_path: Path) -> None:
    value = registration(ModuleWorkRef("quillan", "class", "essay"))
    for key in ("schema_version", "record_type", "work", "registration_revision"):
        data = json.loads(pointer_bytes(value))
        data.pop(key)
        write_pointer(tmp_path, value.work, json.dumps(data).encode())
        with pytest.raises(AcademicWorkRegistrationReadError):
            load_current_academic_work_registration(tmp_path, value.work)


def test_pointer_missing_malformed_and_mismatched_revisions(tmp_path: Path) -> None:
    value = registration(ModuleWorkRef("quillan", "class", "essay"))
    write_pointer(tmp_path, value.work, pointer_bytes(value))
    with pytest.raises(AcademicWorkRegistrationIntegrityError):
        load_current_academic_work_registration(tmp_path, value.work)
    write_raw_revision(tmp_path, value, b"{")
    with pytest.raises(AcademicWorkRegistrationReadError):
        load_current_academic_work_registration(tmp_path, value.work)
    data = academic_work_registration_to_dict(value)
    data["registration_revision"] = 2
    write_raw_revision(tmp_path, value, json.dumps(data).encode())
    with pytest.raises(AcademicWorkRegistrationIntegrityError):
        load_current_academic_work_registration(tmp_path, value.work)


def test_pointer_does_not_promote_higher_orphan(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    orphan = replace(first, registration_revision=2)
    write_raw_revision(tmp_path, orphan, revision_bytes(orphan))
    assert load_current_academic_work_registration(tmp_path, work) == first


@pytest.mark.parametrize("name", ["0.json", "01.json", "+1.json", "-1.json", "one.json", "1.JSON"])
def test_revision_listing_rejects_noncanonical_names(tmp_path: Path, name: str) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    directory = academic_work_registration_revision_path(tmp_path, work, 1).parent
    directory.mkdir(parents=True)
    (directory / name).write_text("{}", encoding="utf-8")
    with pytest.raises(AcademicWorkRegistrationReadError):
        list_academic_work_registration_revisions(tmp_path, work)


def test_revision_listing_numeric_order_hidden_artifacts_and_absence(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    assert list_academic_work_registration_revisions(tmp_path, work) == ()
    for revision in (10, 2, 1):
        value = registration(work, revision)
        write_raw_revision(tmp_path, value, revision_bytes(value))
    revisions = academic_work_registration_revision_path(tmp_path, work, 1).parent
    (revisions / ".interrupted.tmp").write_text("ignored", encoding="utf-8")
    assert list_academic_work_registration_revisions(tmp_path, work) == (1, 2, 10)


def test_revision_listing_rejects_visible_directory(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    directory = academic_work_registration_revision_path(tmp_path, work, 1)
    directory.mkdir(parents=True)
    with pytest.raises(AcademicWorkRegistrationReadError):
        list_academic_work_registration_revisions(tmp_path, work)


def test_registration_ref_listing_order_and_identity_dimensions(tmp_path: Path) -> None:
    works = [
        ModuleWorkRef("zeta", "class_b", "same"),
        ModuleWorkRef("alpha", "class_b", "same"),
        ModuleWorkRef("alpha", "class_a", "same"),
        ModuleWorkRef("alpha", "class_a", "another"),
    ]
    for work in works:
        prepare(tmp_path, work)
        write_academic_work_registration(
            tmp_path, registration(work), expected_current_revision=None
        )
    assert list_academic_work_registration_refs(tmp_path) == tuple(sorted(
        works, key=lambda item: (item.class_id, item.module_id, item.work_id)
    ))


@pytest.mark.parametrize(
    "relative",
    ["bad class", "class/bad module", "class/quillan/bad work"],
)
def test_ref_listing_rejects_invalid_directory_names(tmp_path: Path, relative: str) -> None:
    (tmp_path / "registry" / "work" / Path(relative)).mkdir(parents=True)
    with pytest.raises(AcademicWorkRegistrationReadError):
        list_academic_work_registration_refs(tmp_path)


def test_ref_listing_rejects_uppercase_module_and_visible_entries(tmp_path: Path) -> None:
    root = tmp_path / "registry" / "work"
    (root / "class" / "Quillan" / "work").mkdir(parents=True)
    with pytest.raises(AcademicWorkRegistrationReadError):
        list_academic_work_registration_refs(tmp_path)
    shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(AcademicWorkRegistrationReadError):
        list_academic_work_registration_refs(tmp_path)


def test_ref_listing_never_discovers_producer_work(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    assert list_academic_work_registration_refs(tmp_path) == ()
    assert not (tmp_path / "registry").exists()


def test_update_conflicts_and_newer_orphan(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    orphan = replace(first, registration_revision=5)
    write_raw_revision(tmp_path, orphan, revision_bytes(orphan))
    with pytest.raises(AcademicWorkRegistrationIntegrityError):
        write_academic_work_registration(
            tmp_path, replace(first, registration_revision=2), expected_current_revision=1
        )


def test_initial_non_one_and_update_without_pointer_conflicts(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    with pytest.raises(AcademicWorkRegistrationConflictError):
        write_academic_work_registration(
            tmp_path, registration(work, 2), expected_current_revision=None
        )
    with pytest.raises(AcademicWorkRegistrationConflictError):
        write_academic_work_registration(
            tmp_path, registration(work, 2), expected_current_revision=1
        )


def test_pointer_failure_preserves_verified_orphan_and_old_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    pointer_before = academic_work_registration_current_path(tmp_path, work).read_bytes()
    candidate = replace(first, registration_revision=2)
    monkeypatch.setattr(os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace")))
    with pytest.raises(AcademicWorkRegistrationWriteError):
        write_academic_work_registration(tmp_path, candidate, expected_current_revision=1)
    assert academic_work_registration_current_path(tmp_path, work).read_bytes() == pointer_before
    assert academic_work_registration_revision_path(tmp_path, work, 2).read_bytes() == revision_bytes(candidate)
    directory = academic_work_registration_current_path(tmp_path, work).parent
    assert not (directory / ".write.lock").exists()
    assert not tuple(directory.glob(".current.json.*.tmp"))


def test_persisted_reload_failure_removes_candidate_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    original_loader = storage.load_academic_work_registration_revision

    def fail_candidate(root: str | Path, requested: ModuleWorkRef, revision: int) -> AcademicWorkRegistration:
        if revision == 2:
            raise AcademicWorkRegistrationReadError("injected")
        return original_loader(root, requested, revision)

    monkeypatch.setattr(storage, "load_academic_work_registration_revision", fail_candidate)
    with pytest.raises(AcademicWorkRegistrationWriteError):
        write_academic_work_registration(
            tmp_path, replace(first, registration_revision=2), expected_current_revision=1
        )
    assert not academic_work_registration_revision_path(tmp_path, work, 2).exists()
    assert not (academic_work_registration_current_path(tmp_path, work).parent / ".write.lock").exists()


def test_final_verification_failure_has_no_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    candidate = replace(first, registration_revision=2)
    original_current = storage.load_current_academic_work_registration
    calls = 0

    def fail_final(root: str | Path, requested: ModuleWorkRef) -> AcademicWorkRegistration | None:
        nonlocal calls
        calls += 1
        if calls >= 1:
            raise AcademicWorkRegistrationReadError("injected final failure")
        return original_current(root, requested)

    monkeypatch.setattr(storage, "load_current_academic_work_registration", fail_final)
    with pytest.raises(AcademicWorkRegistrationIntegrityError):
        write_academic_work_registration(tmp_path, candidate, expected_current_revision=1)
    assert json.loads(academic_work_registration_current_path(tmp_path, work).read_text())["registration_revision"] == 2
    assert academic_work_registration_revision_path(tmp_path, work, 2).exists()
    assert not (academic_work_registration_current_path(tmp_path, work).parent / ".write.lock").exists()


def test_directory_fsync_failure_is_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    original_open = os.open

    def fail_directory_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if flags == os.O_RDONLY:
            raise OSError("dir fsync")
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", fail_directory_open)
    value = registration(work)
    write_academic_work_registration(tmp_path, value, expected_current_revision=None)
    assert load_current_academic_work_registration(tmp_path, work) == value


def test_unrelated_workflows_do_not_create_registration_storage(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    ensure_workspace_root(workspace)
    registry = workspace / "registry" / "work"
    assert not registry.exists()
    open_school_year(workspace, "2026-2027", opened_at=NOW)
    close_school_year(workspace, closed_at=NOW.replace(hour=14))
    assert not registry.exists()
    metadata = create_class_metadata(
        "english10_p2", "2026-2027", created_at=NOW
    )
    write_class_metadata_for_class(workspace, metadata)
    assert not registry.exists()
    calendar = AcademicPeriodCalendar(
        schema_version="1",
        record_type="academic_period_calendar",
        school_year="2026-2027",
        calendar_revision=1,
        created_at=NOW,
        updated_at=NOW,
        periods=(),
    )
    write_academic_period_calendar(
        workspace, calendar, expected_current_revision=None
    )
    assert not registry.exists()
    work = ModuleWorkRef("quillan", "english10_p2", "essay")
    locator = RouteLocator(PDS2_SCHEMA, work, "route_1")
    route = RouteRegistration(
        schema_version="1",
        locator=locator,
        target=ModuleRecordRef("quillan", "page", "page_1", "1"),
        created_at=NOW.isoformat(),
        status="active",
        human_fallback="Essay page",
        module_details={},
    )
    write_route_registration(workspace, route)
    assert not registry.exists()


def test_registration_write_preserves_all_unrelated_canonical_bytes(
    tmp_path: Path,
) -> None:
    ensure_workspace_root(tmp_path)
    open_school_year(tmp_path, "2026-2027", opened_at=NOW)
    metadata = create_class_metadata("english10_p2", "2026-2027", created_at=NOW)
    class_path = write_class_metadata_for_class(tmp_path, metadata)
    calendar = AcademicPeriodCalendar(
        schema_version="1", record_type="academic_period_calendar",
        school_year="2026-2027", calendar_revision=1,
        created_at=NOW, updated_at=NOW, periods=(),
    )
    write_academic_period_calendar(tmp_path, calendar, expected_current_revision=None)
    work = ModuleWorkRef("quillan", "english10_p2", "essay")
    producer = module_work_dir(tmp_path, work)
    producer.mkdir(parents=True)
    producer_file = producer / "assignment.json"
    producer_file.write_bytes(b'{"producer":true}\n')
    locator = RouteLocator(PDS2_SCHEMA, work, "route_1")
    route = RouteRegistration(
        schema_version="1", locator=locator,
        target=ModuleRecordRef("quillan", "page", "page_1", "1"),
        created_at=NOW.isoformat(), status="active", human_fallback="Essay page",
        module_details={},
    )
    route_path = write_route_registration(tmp_path, route)
    paths = (
        school_year_state_path(tmp_path),
        class_path,
        academic_period_revision_path(tmp_path, "2026-2027", 1),
        academic_period_current_path(tmp_path, "2026-2027"),
        route_path,
        producer_file,
    )
    before = tuple(path.read_bytes() for path in paths)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    assert tuple(path.read_bytes() for path in paths) == before


def assert_clean_failed_update(
    tmp_path: Path, work: ModuleWorkRef, pointer_before: bytes, revision: int = 2
) -> None:
    directory = academic_work_registration_current_path(tmp_path, work).parent
    assert academic_work_registration_current_path(tmp_path, work).read_bytes() == pointer_before
    assert not academic_work_registration_revision_path(tmp_path, work, revision).exists()
    assert not (directory / ".write.lock").exists()
    assert not tuple(directory.glob(".current.json.*.tmp"))


def test_revision_directory_creation_failure_creates_no_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    target = academic_work_registration_revision_path(tmp_path, work, 1).parent
    original_mkdir = Path.mkdir

    def fail_target(path: Path, *args: object, **kwargs: object) -> None:
        if path == target:
            raise OSError("injected mkdir failure")
        original_mkdir(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", fail_target)
    with pytest.raises(AcademicWorkRegistrationWriteError):
        write_academic_work_registration(
            tmp_path, registration(work), expected_current_revision=None
        )
    assert not academic_work_registration_revision_path(tmp_path, work, 1).exists()


@pytest.mark.parametrize("phase", ["open", "write", "flush"])
def test_revision_file_phase_failures_clean_candidate_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    pointer = academic_work_registration_current_path(tmp_path, work)
    pointer_before = pointer.read_bytes()
    target = academic_work_registration_revision_path(tmp_path, work, 2)
    original_open = Path.open

    class FaultyOutput:
        def __init__(self, wrapped: object) -> None:
            self.wrapped = wrapped

        def __enter__(self) -> "FaultyOutput":
            self.wrapped.__enter__()  # type: ignore[attr-defined]
            return self

        def __exit__(self, *args: object) -> object:
            return self.wrapped.__exit__(*args)  # type: ignore[attr-defined]

        def write(self, content: str) -> object:
            if phase == "write":
                raise OSError("injected write failure")
            return self.wrapped.write(content)  # type: ignore[attr-defined]

        def flush(self) -> None:
            if phase == "flush":
                raise OSError("injected flush failure")
            self.wrapped.flush()  # type: ignore[attr-defined]

        def fileno(self) -> int:
            return cast(int, self.wrapped.fileno())  # type: ignore[attr-defined]

    def patched_open(path: Path, *args: Any, **kwargs: Any) -> object:
        if path == target:
            if phase == "open":
                raise OSError("injected open failure")
            return FaultyOutput(original_open(path, *args, **kwargs))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", patched_open)
    with pytest.raises(AcademicWorkRegistrationWriteError):
        write_academic_work_registration(
            tmp_path, replace(first, registration_revision=2), expected_current_revision=1
        )
    assert_clean_failed_update(tmp_path, work, pointer_before)


def test_revision_fsync_failure_cleans_candidate_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    pointer_before = academic_work_registration_current_path(tmp_path, work).read_bytes()
    monkeypatch.setattr(storage, "_fsync_directory_if_supported", lambda _path: None)
    monkeypatch.setattr(os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("fsync")))
    with pytest.raises(AcademicWorkRegistrationWriteError):
        write_academic_work_registration(
            tmp_path, replace(first, registration_revision=2), expected_current_revision=1
        )
    assert_clean_failed_update(tmp_path, work, pointer_before)


def test_persisted_revision_inequality_cleans_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    pointer_before = academic_work_registration_current_path(tmp_path, work).read_bytes()
    original = storage.load_academic_work_registration_revision

    def unequal(root: str | Path, requested: ModuleWorkRef, revision: int) -> AcademicWorkRegistration:
        value = original(root, requested, revision)
        return replace(value, title="Unequal") if revision == 2 else value

    monkeypatch.setattr(storage, "load_academic_work_registration_revision", unequal)
    with pytest.raises(AcademicWorkRegistrationWriteError, match="differs"):
        write_academic_work_registration(
            tmp_path, replace(first, registration_revision=2), expected_current_revision=1
        )
    assert_clean_failed_update(tmp_path, work, pointer_before)


@pytest.mark.parametrize("phase", ["create", "write", "flush", "fsync"])
def test_pointer_temporary_phase_failures_preserve_verified_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    pointer = academic_work_registration_current_path(tmp_path, work)
    pointer_before = pointer.read_bytes()
    candidate = replace(first, registration_revision=2)
    original_named = tempfile.NamedTemporaryFile

    class FaultyTemporary:
        def __init__(self, wrapped: object) -> None:
            self.wrapped = wrapped
            self.name = wrapped.name  # type: ignore[attr-defined]

        def __enter__(self) -> "FaultyTemporary":
            self.wrapped.__enter__()  # type: ignore[attr-defined]
            return self

        def __exit__(self, *args: object) -> object:
            return self.wrapped.__exit__(*args)  # type: ignore[attr-defined]

        def write(self, content: str) -> object:
            if phase == "write":
                raise OSError("pointer write")
            return self.wrapped.write(content)  # type: ignore[attr-defined]

        def flush(self) -> None:
            if phase == "flush":
                raise OSError("pointer flush")
            self.wrapped.flush()  # type: ignore[attr-defined]

        def fileno(self) -> int:
            return cast(int, self.wrapped.fileno())  # type: ignore[attr-defined]

    def patched_named(*args: Any, **kwargs: Any) -> object:
        if phase == "create":
            raise OSError("pointer create")
        return FaultyTemporary(original_named(*args, **kwargs))

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", patched_named)
    if phase == "fsync":
        original_fsync = os.fsync
        calls = 0

        def fail_pointer_fsync(fd: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("pointer fsync")
            original_fsync(fd)

        monkeypatch.setattr(storage, "_fsync_directory_if_supported", lambda _path: None)
        monkeypatch.setattr(os, "fsync", fail_pointer_fsync)
    with pytest.raises(AcademicWorkRegistrationWriteError):
        write_academic_work_registration(tmp_path, candidate, expected_current_revision=1)
    assert pointer.read_bytes() == pointer_before
    assert academic_work_registration_revision_path(tmp_path, work, 2).read_bytes() == revision_bytes(candidate)
    assert not (pointer.parent / ".write.lock").exists()
    assert not tuple(pointer.parent.glob(".current.json.*.tmp"))


def test_final_verification_inequality_preserves_published_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    candidate = replace(first, registration_revision=2)
    monkeypatch.setattr(
        storage,
        "load_current_academic_work_registration",
        lambda _root, _work: first,
    )
    with pytest.raises(AcademicWorkRegistrationIntegrityError):
        write_academic_work_registration(tmp_path, candidate, expected_current_revision=1)
    assert json.loads(academic_work_registration_current_path(tmp_path, work).read_text())["registration_revision"] == 2
    assert academic_work_registration_revision_path(tmp_path, work, 2).exists()
    assert not (academic_work_registration_current_path(tmp_path, work).parent / ".write.lock").exists()


def test_revision_listing_enumeration_and_inspection_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "essay")
    value = registration(work)
    path = write_raw_revision(tmp_path, value, revision_bytes(value))
    directory = path.parent
    original_iterdir = Path.iterdir

    def fail_iterdir(target: Path) -> object:
        if target == directory:
            raise OSError("enumeration")
        return original_iterdir(target)

    monkeypatch.setattr(Path, "iterdir", fail_iterdir)
    with pytest.raises(AcademicWorkRegistrationReadError, match="enumerate"):
        list_academic_work_registration_revisions(tmp_path, work)
    monkeypatch.undo()
    original_is_file = Path.is_file

    def fail_is_file(target: Path) -> bool:
        if target == path:
            raise OSError("inspection")
        return original_is_file(target)

    monkeypatch.setattr(Path, "is_file", fail_is_file)
    with pytest.raises(AcademicWorkRegistrationReadError, match="inspect"):
        list_academic_work_registration_revisions(tmp_path, work)


@pytest.mark.parametrize("level", ["module", "work"])
def test_ref_listing_rejects_visible_entries_at_nested_levels(
    tmp_path: Path, level: str
) -> None:
    module = tmp_path / "registry" / "work" / "class" / "quillan"
    work = module / "essay"
    work.mkdir(parents=True)
    target = module / "unexpected.txt" if level == "module" else work / "unexpected.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(AcademicWorkRegistrationReadError):
        list_academic_work_registration_refs(tmp_path)
