from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from typing import Any, cast
from unittest.mock import Mock

import pytest

import pds_core.publication_storage as storage
from pds_core.academic_work_registration_storage import (
    AcademicWorkRegistrationStorageError,
    load_academic_work_registration_revision,
    load_current_academic_work_registration,
    write_academic_work_registration,
)
from pds_core.academic_work_registrations import AcademicWorkRegistration
from pds_core.academic_period_storage import (
    academic_period_current_path,
    academic_period_revision_path,
    load_academic_period_calendar_revision,
    load_current_academic_period_calendar,
    write_academic_period_calendar,
)
from pds_core.academic_periods import AcademicPeriodCalendar
from pds_core.class_metadata import (
    create_class_metadata,
    load_class_metadata_for_class,
    write_class_metadata_for_class,
)
from pds_core.core_menu import main as core_menu_main
from pds_core.publication_records import PublicationRecord, PublicationWithdrawal
from pds_core.publication_records import (
    publication_record_to_dict,
    publication_withdrawal_to_dict,
)
from pds_core.publication_storage import (
    PublicationConflictError,
    PublicationIntegrityError,
    PublicationManifestIntegrityError,
    PublicationManifestNotFoundError,
    PublicationNotFoundError,
    PublicationReadError,
    PublicationWriteError,
    calculate_publication_manifest_digest,
    get_current_publication_record,
    list_publication_ids,
    list_publication_record_set,
    list_publication_records,
    list_publication_withdrawals,
    load_publication_record,
    load_publication_withdrawal,
    resolve_publication_manifest_path,
    verify_publication_manifest,
    write_publication_record,
    write_publication_withdrawal,
)
from pds_core.registry_paths import (
    academic_work_registration_current_path,
    academic_work_registration_revision_path,
    publication_record_path,
    publication_withdrawal_path,
    publication_withdrawals_dir,
    publications_dir,
)
from pds_core.rosters import create_roster, load_roster, write_roster
from pds_core.route_registrations import load_route_registration, write_route_registration
from pds_core.routes import class_roster_path, module_work_dir
from pds_core.routing_models import (
    PDS2_SCHEMA,
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RouteRegistration,
)
from pds_core.scan_retention import retain_source_scan
from pds_core.school_years import (
    close_school_year,
    load_school_year_state,
    open_school_year,
    school_year_state_path,
)
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    load_workspace_standards_library,
    standards_library_path,
    write_workspace_standards_library,
)
from pds_core.workspace import ensure_workspace_root

NOW = datetime(2026, 7, 27, 14, tzinfo=timezone.utc)
PUB1 = "pub_11111111111111111111111111111111"
PUB2 = "pub_22222222222222222222222222222222"


def prepare_manifest(tmp_path: Path, work: ModuleWorkRef, revision: int) -> tuple[str, str]:
    relative = (
        f"classes/{work.class_id}/modules/{work.module_id}/work/{work.work_id}/"
        f"exports/{revision}.json"
    )
    path = tmp_path.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = f'{{"revision":{revision}}}\n'.encode()
    path.write_bytes(payload)
    return relative, hashlib.sha256(payload).hexdigest()


def publication(
    tmp_path: Path, work: ModuleWorkRef, *, publication_id: str = PUB1,
    revision: int = 1, supersedes: str | None = None,
    kind: str = "intervention_record_set",
) -> PublicationRecord:
    path, digest = prepare_manifest(tmp_path, work, revision)
    return PublicationRecord(
        schema_version="1", record_type="publication_record",
        publication_id=publication_id, work=work, source_record=None,
        publication_kind=kind,  # type: ignore[arg-type]
        capabilities=("intervention_status",) if kind == "intervention_record_set" else (),
        record_set_id="results", record_set_revision=revision,
        manifest_contract_version="1", manifest_path=path,
        manifest_digest_algorithm="sha256", manifest_digest=digest,
        published_at=NOW + timedelta(minutes=revision),
        academic_work_registration_revision=1 if kind == "academic_result_set" else None,
        supersedes_publication_id=supersedes,
    )


def registration(work: ModuleWorkRef, lifecycle: str = "active") -> AcademicWorkRegistration:
    return AcademicWorkRegistration(
        schema_version="1", record_type="academic_work_registration", work=work,
        registration_revision=1, producer_contract_version="1", title="Essay",
        work_kind="assignment", academic_intent="summative",
        lifecycle=lifecycle,  # type: ignore[arg-type]
        created_at=NOW, updated_at=NOW, source_records=(),
    )


def test_manifest_resolution_digest_and_missing(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    resolved = resolve_publication_manifest_path(tmp_path, value)
    assert resolved == Path(tmp_path, *value.manifest_path.split("/")).resolve()
    assert verify_publication_manifest(tmp_path, value) == resolved
    with pytest.raises(PublicationManifestIntegrityError):
        verify_publication_manifest(tmp_path, replace(value, manifest_digest="0" * 64))
    resolved.unlink()
    with pytest.raises(PublicationManifestNotFoundError):
        verify_publication_manifest(tmp_path, value)


def test_verification_resolves_once_and_hashes_exact_returned_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    first = Path(tmp_path, *value.manifest_path.split("/")).resolve()
    second = first.with_name("changed.json")
    second.write_bytes(b"different bytes")
    resolve = Mock(side_effect=[first, second])
    monkeypatch.setattr(storage, "resolve_publication_manifest_path", resolve)
    assert verify_publication_manifest(tmp_path, value) == first
    resolve.assert_called_once()


def test_digest_calculation_resolves_once_reads_chunks_and_never_parses_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    path = Path(tmp_path, *value.manifest_path.split("/")).resolve()
    payload = b"not JSON at all\x00\xff" * 10
    path.write_bytes(payload)
    resolve = Mock(return_value=path)
    monkeypatch.setattr(storage, "resolve_publication_manifest_path", resolve)
    monkeypatch.setattr(storage, "_DIGEST_CHUNK_SIZE", 7)
    sizes: list[int] = []
    original_open = Path.open

    class TrackingReader:
        def __init__(self, source: object) -> None:
            self.source = source

        def __enter__(self) -> "TrackingReader":
            self.source.__enter__()  # type: ignore[attr-defined]
            return self

        def __exit__(self, *args: object) -> object:
            return self.source.__exit__(*args)  # type: ignore[attr-defined]

        def read(self, size: int) -> bytes:
            sizes.append(size)
            return self.source.read(size)  # type: ignore[attr-defined,no-any-return]

    def tracking_open(self: Path, *args: object, **kwargs: object) -> object:
        return TrackingReader(cast(Any, original_open)(self, *args, **kwargs))

    monkeypatch.setattr(Path, "open", tracking_open)
    assert calculate_publication_manifest_digest(tmp_path, value) == hashlib.sha256(
        payload
    ).hexdigest()
    resolve.assert_called_once()
    assert sizes and set(sizes) == {7}


@pytest.mark.parametrize("missing", ["workspace", "work", "manifest"])
def test_manifest_resolution_missing_components(tmp_path: Path, missing: str) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    manifest = Path(tmp_path, *value.manifest_path.split("/"))
    if missing == "manifest":
        manifest.unlink()
        root = tmp_path
    elif missing == "work":
        manifest.unlink()
        manifest.parent.rmdir()
        root = tmp_path
    else:
        root = tmp_path / "absent"
    with pytest.raises(PublicationManifestNotFoundError):
        resolve_publication_manifest_path(root, value)


def test_manifest_directory_and_contained_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    manifest = Path(tmp_path, *value.manifest_path.split("/"))
    manifest.unlink()
    manifest.mkdir()
    with pytest.raises(PublicationManifestNotFoundError):
        resolve_publication_manifest_path(tmp_path, value)
    manifest.rmdir()
    target = manifest.with_name("target.json")
    target.write_bytes(b"target")
    try:
        manifest.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    assert resolve_publication_manifest_path(tmp_path, value) == target.resolve()


def test_manifest_symlink_escape_is_rejected(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    manifest = Path(tmp_path, *value.manifest_path.split("/"))
    manifest.unlink()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    try:
        manifest.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(PublicationManifestIntegrityError):
        resolve_publication_manifest_path(tmp_path, value)


def test_work_root_symlink_escape_is_rejected(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    work_root = tmp_path / "classes" / "class_a" / "modules" / "portia" / "work" / "support"
    shutil.rmtree(work_root)
    outside = tmp_path / "outside-work"
    (outside / "exports").mkdir(parents=True)
    (outside / "exports" / "1.json").write_bytes(b"outside")
    try:
        work_root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is not permitted")
    with pytest.raises(PublicationManifestIntegrityError):
        resolve_publication_manifest_path(tmp_path, value)


def test_manifest_resolution_and_binary_io_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    original_resolve = Path.resolve

    def fail_manifest_resolve(self: Path, strict: bool = False) -> Path:
        if self.name == "1.json":
            raise OSError("resolve failed")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_manifest_resolve)
    with pytest.raises(PublicationManifestIntegrityError):
        resolve_publication_manifest_path(tmp_path, value)


def test_manifest_is_file_inspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    manifest = Path(tmp_path, *value.manifest_path.split("/")).resolve()
    original_is_file = Path.is_file

    def failing_is_file(self: Path) -> bool:
        if self == manifest:
            raise OSError("inspection failed")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", failing_is_file)
    with pytest.raises(PublicationManifestNotFoundError):
        resolve_publication_manifest_path(tmp_path, value)


@pytest.mark.parametrize("failure", ["open", "read"])
def test_manifest_binary_failures_are_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    path = Path(tmp_path, *value.manifest_path.split("/")).resolve()
    monkeypatch.setattr(storage, "resolve_publication_manifest_path", lambda *_: path)
    if failure == "open":
        monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("open")))
    else:
        class BrokenReader(io.BytesIO):
            def read(self, size: int | None = -1) -> bytes:
                raise OSError("read")
        monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: BrokenReader())
    with pytest.raises(storage.PublicationManifestError):
        calculate_publication_manifest_digest(tmp_path, value)


def test_write_chain_load_list_current_withdraw_and_preserve(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    first = publication(tmp_path, work)
    path = write_publication_record(tmp_path, first)
    original = path.read_bytes()
    expected = (
        json.dumps(
            publication_record_to_dict(first), indent=2, sort_keys=True, allow_nan=False
        ) + "\n"
    ).encode("utf-8")
    assert original == expected
    manifest = Path(tmp_path, *first.manifest_path.split("/"))
    manifest_bytes = manifest.read_bytes()
    assert original.endswith(b"\n")
    assert path == publication_record_path(tmp_path, PUB1)
    assert load_publication_record(tmp_path, PUB1) == first
    assert list_publication_ids(tmp_path) == (PUB1,)
    assert get_current_publication_record(
        tmp_path, work, "intervention_record_set", "results"
    ) == first
    second = publication(
        tmp_path, work, publication_id=PUB2, revision=3, supersedes=PUB1
    )
    write_publication_record(tmp_path, second)
    assert path.read_bytes() == original
    assert manifest.read_bytes() == manifest_bytes
    assert not tuple((tmp_path / "registry").rglob("*.lock"))
    assert not (tmp_path / "registry" / "publications" / "current.json").exists()
    assert list_publication_record_set(
        tmp_path, work, "intervention_record_set", "results"
    ) == (first, second)
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB2,
        second.published_at + timedelta(minutes=1), "Producer correction required.",
    )
    withdrawal_path = write_publication_withdrawal(tmp_path, withdrawal)
    assert withdrawal_path == publication_withdrawal_path(tmp_path, PUB2)
    assert load_publication_withdrawal(tmp_path, PUB2) == withdrawal
    assert withdrawal_path.read_bytes() == (
        json.dumps(
            publication_withdrawal_to_dict(withdrawal),
            indent=2, sort_keys=True, allow_nan=False,
        ) + "\n"
    ).encode("utf-8")
    assert list_publication_withdrawals(tmp_path) == (withdrawal,)
    assert get_current_publication_record(
        tmp_path, work, "intervention_record_set", "results"
    ) is None
    assert path.read_bytes() == original
    with pytest.raises(PublicationConflictError):
        write_publication_record(tmp_path, first)
    with pytest.raises(PublicationConflictError):
        write_publication_withdrawal(tmp_path, withdrawal)


def test_academic_publication_requires_current_noncancelled_registration(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    value = publication(tmp_path, work, kind="academic_result_set")
    with pytest.raises(PublicationConflictError):
        write_publication_record(tmp_path, value)
    assert not publication_record_path(tmp_path, PUB1).exists()
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    assert write_publication_record(tmp_path, value).exists()


def test_registration_stale_and_cancelled_are_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    value = publication(tmp_path, work, kind="academic_result_set")
    current = registration(work)
    monkeypatch.setattr(storage, "load_current_academic_work_registration", lambda *_: current)
    with pytest.raises(PublicationConflictError, match="current"):
        storage._validate_registration_relationship(
            tmp_path, replace(value, academic_work_registration_revision=2)
        )
    cancelled = replace(current, lifecycle="cancelled")
    monkeypatch.setattr(storage, "load_current_academic_work_registration", lambda *_: cancelled)
    monkeypatch.setattr(storage, "load_academic_work_registration_revision", lambda *_: cancelled)
    with pytest.raises(PublicationConflictError, match="cancelled"):
        storage._validate_registration_relationship(tmp_path, value)


@pytest.mark.parametrize("corruption", ["malformed_pointer", "missing_revision", "invalid_revision"])
def test_registration_corruption_is_publication_integrity_failure(
    tmp_path: Path, corruption: str
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    value = publication(tmp_path, work, kind="academic_result_set")
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    pointer = academic_work_registration_current_path(tmp_path, work)
    revision = academic_work_registration_revision_path(tmp_path, work, 1)
    if corruption == "malformed_pointer":
        pointer.write_text("{bad", encoding="utf-8")
    elif corruption == "missing_revision":
        revision.unlink()
    else:
        revision.write_text("{bad", encoding="utf-8")
    with pytest.raises(PublicationIntegrityError):
        storage._validate_registration_relationship(tmp_path, value)


def test_exact_registration_disappearance_is_integrity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    value = publication(tmp_path, work, kind="academic_result_set")
    current = registration(work)
    monkeypatch.setattr(storage, "load_current_academic_work_registration", lambda *_: current)
    monkeypatch.setattr(
        storage,
        "load_academic_work_registration_revision",
        Mock(side_effect=AcademicWorkRegistrationStorageError("disappeared")),
    )
    with pytest.raises(PublicationIntegrityError):
        storage._validate_registration_relationship(tmp_path, value)


def test_registration_identity_mismatch_is_integrity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    value = publication(tmp_path, work, kind="academic_result_set")
    current = registration(work)
    wrong = replace(current, work=ModuleWorkRef("quillan", "other", "essay"))
    monkeypatch.setattr(storage, "load_current_academic_work_registration", lambda *_: current)
    monkeypatch.setattr(storage, "load_academic_work_registration_revision", lambda *_: wrong)
    with pytest.raises(PublicationIntegrityError):
        storage._validate_registration_relationship(tmp_path, value)


@pytest.mark.parametrize("payload", [b"\xff", b'{"x":NaN}', b'{"x":1,"x":2}', b"[]"])
def test_strict_reader_rejects_invalid_json(tmp_path: Path, payload: bytes) -> None:
    path = publication_record_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    with pytest.raises(PublicationReadError):
        load_publication_record(tmp_path, PUB1)


@pytest.mark.parametrize(
    "payload",
    [
        b"{", b'{"x":Infinity}', b'{"x":-Infinity}',
        b'{"work":{"module_id":"a","module_id":"b"}}',
        b'{"source_record":{"module_id":"a","module_id":"b"}}',
        b'null', b'"text"', b'1',
    ],
)
def test_publication_reader_additional_strict_json(tmp_path: Path, payload: bytes) -> None:
    path = publication_record_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    with pytest.raises(PublicationReadError):
        load_publication_record(tmp_path, PUB1)


@pytest.mark.parametrize("field,value", [("schema_version", "2"), ("record_type", "wrong"), ("record_set_revision", 0)])
def test_publication_reader_rejects_invalid_models(
    tmp_path: Path, field: str, value: object
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    record = publication(tmp_path, work)
    data = publication_record_to_dict(record)
    data[field] = value
    path = publication_record_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PublicationReadError):
        load_publication_record(tmp_path, PUB1)


def test_reader_rejects_embedded_publication_id_mismatch(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    data = publication_record_to_dict(publication(tmp_path, work))
    data["publication_id"] = PUB2
    path = publication_record_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PublicationIntegrityError):
        load_publication_record(tmp_path, PUB1)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff", b"{", b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
        b'{"x":1,"x":2}', b"[]", b"null",
    ],
)
def test_withdrawal_reader_strict_json(tmp_path: Path, payload: bytes) -> None:
    path = publication_withdrawal_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    with pytest.raises(PublicationReadError):
        load_publication_withdrawal(tmp_path, PUB1)


@pytest.mark.parametrize("field,value", [("schema_version", "2"), ("record_type", "wrong"), ("reason", "")])
def test_withdrawal_reader_rejects_invalid_models(
    tmp_path: Path, field: str, value: object
) -> None:
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, NOW, "Correction."
    )
    data = publication_withdrawal_to_dict(withdrawal)
    data[field] = value
    path = publication_withdrawal_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PublicationReadError):
        load_publication_withdrawal(tmp_path, PUB1)


def test_withdrawal_reader_rejects_embedded_id_mismatch(tmp_path: Path) -> None:
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB2, NOW, "Correction."
    )
    path = publication_withdrawal_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(publication_withdrawal_to_dict(withdrawal)), encoding="utf-8")
    with pytest.raises(PublicationIntegrityError):
        load_publication_withdrawal(tmp_path, PUB1)


def test_loading_is_independent_of_manifest_and_bounded_listing(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    write_publication_record(tmp_path, value)
    Path(tmp_path, *value.manifest_path.split("/")).unlink()
    assert load_publication_record(tmp_path, PUB1) == value
    assert list_publication_records(tmp_path) == (value,)
    (tmp_path / "classes" / "unrelated.json").write_text("not json", encoding="utf-8")
    assert list_publication_ids(tmp_path) == (PUB1,)


def test_missing_and_invalid_canonical_entries(tmp_path: Path) -> None:
    assert list_publication_records(tmp_path) == ()
    assert load_publication_withdrawal(tmp_path, PUB1) is None
    with pytest.raises(PublicationNotFoundError):
        load_publication_record(tmp_path, PUB1)
    directory = tmp_path / "registry" / "publications"
    directory.mkdir(parents=True)
    (directory / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PublicationReadError):
        list_publication_ids(tmp_path)


@pytest.mark.parametrize("collection", ["publications", "withdrawals"])
@pytest.mark.parametrize("entry_kind", ["hidden_file", "hidden_directory", "visible_directory"])
def test_canonical_collections_reject_unexpected_entries(
    tmp_path: Path, collection: str, entry_kind: str
) -> None:
    directory = (
        publications_dir(tmp_path)
        if collection == "publications"
        else publication_withdrawals_dir(tmp_path)
    )
    directory.mkdir(parents=True)
    name = ".unexpected" if entry_kind.startswith("hidden") else "unexpected"
    entry = directory / name
    if entry_kind.endswith("directory"):
        entry.mkdir()
    else:
        entry.write_text("corrupt", encoding="utf-8")
    with pytest.raises(PublicationReadError):
        if collection == "publications":
            list_publication_ids(tmp_path)
        else:
            list_publication_withdrawals(tmp_path)


@pytest.mark.parametrize("collection", ["publications", "withdrawals"])
def test_collection_enumeration_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collection: str
) -> None:
    directory = publications_dir(tmp_path) if collection == "publications" else publication_withdrawals_dir(tmp_path)
    directory.mkdir(parents=True)
    original_iterdir = Path.iterdir

    def failing_iterdir(self: Path) -> object:
        if self == directory:
            raise OSError("enumeration failed")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", failing_iterdir)
    with pytest.raises(PublicationReadError):
        if collection == "publications":
            list_publication_ids(tmp_path)
        else:
            list_publication_withdrawals(tmp_path)


def test_collection_entry_inspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = publications_dir(tmp_path)
    directory.mkdir(parents=True)
    entry = directory / f"{PUB1}.json"
    entry.write_text("{}", encoding="utf-8")
    original_is_file = Path.is_file

    def failing_is_file(self: Path) -> bool:
        if self == entry:
            raise OSError("inspection failed")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", failing_is_file)
    with pytest.raises(PublicationReadError):
        list_publication_ids(tmp_path)


def test_deterministic_publication_and_withdrawal_ordering(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    second = publication(tmp_path, work, publication_id=PUB2)
    write_publication_record(tmp_path, second)
    other = replace(
        publication(tmp_path, work, publication_id=PUB1, revision=2),
        record_set_id="other",
    )
    write_publication_record(tmp_path, other)
    assert list_publication_ids(tmp_path) == (PUB1, PUB2)
    withdrawal_two = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB2, second.published_at, "Correction two."
    )
    withdrawal_one = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, other.published_at, "Correction one."
    )
    write_publication_withdrawal(tmp_path, withdrawal_two)
    write_publication_withdrawal(tmp_path, withdrawal_one)
    assert list_publication_withdrawals(tmp_path) == (withdrawal_one, withdrawal_two)


def test_listing_never_traverses_producer_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    write_publication_record(tmp_path, value)
    producer_root = tmp_path / "classes"
    original_iterdir = Path.iterdir

    def guarded_iterdir(self: Path) -> object:
        if self == producer_root or producer_root in self.parents:
            raise AssertionError("producer storage was traversed")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    assert list_publication_records(tmp_path) == (value,)


def test_invalid_withdrawal_timestamp_relationship_in_listing(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    write_publication_record(tmp_path, value)
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1,
        value.published_at - timedelta(seconds=1), "Correction."
    )
    path = publication_withdrawal_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(publication_withdrawal_to_dict(withdrawal)), encoding="utf-8")
    with pytest.raises(PublicationIntegrityError):
        list_publication_withdrawals(tmp_path)


def test_orphan_withdrawal_is_integrity_failure(tmp_path: Path) -> None:
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, NOW, "No longer current."
    )
    path = publication_withdrawal_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "schema_version": withdrawal.schema_version,
            "record_type": withdrawal.record_type,
            "publication_id": withdrawal.publication_id,
            "withdrawn_at": withdrawal.withdrawn_at.isoformat(),
            "reason": withdrawal.reason,
        }), encoding="utf-8",
    )
    with pytest.raises(PublicationIntegrityError):
        list_publication_withdrawals(tmp_path)


def test_publication_collision_and_supersession_conflicts(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    first = publication(tmp_path, work)
    write_publication_record(tmp_path, first)
    same_revision = replace(first, publication_id=PUB2)
    with pytest.raises(PublicationConflictError):
        write_publication_record(tmp_path, same_revision)
    contradictory = replace(
        same_revision, manifest_contract_version="2"
    )
    with pytest.raises(PublicationIntegrityError):
        write_publication_record(tmp_path, contradictory)
    next_value = publication(tmp_path, work, publication_id=PUB2, revision=3)
    with pytest.raises(PublicationConflictError):
        write_publication_record(tmp_path, next_value)
    with pytest.raises(PublicationConflictError):
        write_publication_record(
            tmp_path, replace(next_value, supersedes_publication_id="pub_33333333333333333333333333333333")
        )


def test_first_publication_cannot_name_predecessor(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    value = replace(value, supersedes_publication_id=PUB2)
    with pytest.raises(PublicationConflictError):
        write_publication_record(tmp_path, value)


def test_malformed_existing_history_blocks_write(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    path = publication_record_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True)
    path.write_text("{bad", encoding="utf-8")
    later = publication(tmp_path, work, publication_id=PUB2, revision=2, supersedes=PUB1)
    with pytest.raises(PublicationIntegrityError):
        write_publication_record(tmp_path, later)
    assert path.read_text(encoding="utf-8") == "{bad"


def test_series_lock_identity_and_preexisting_lock_preservation(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    base = publication(tmp_path, work)
    locks = {
        storage._series_lock_path(tmp_path, base),
        storage._series_lock_path(tmp_path, replace(base, record_set_id="other")),
        storage._series_lock_path(
            tmp_path,
            replace(
                base, publication_kind="academic_result_set", capabilities=(),
                academic_work_registration_revision=1,
            ),
        ),
        storage._series_lock_path(
            tmp_path,
            replace(
                base, work=ModuleWorkRef("portia", "class_a", "other"),
                manifest_path="classes/class_a/modules/portia/work/other/exports/1.json",
            ),
        ),
    }
    assert len(locks) == 4
    lock = storage._series_lock_path(tmp_path, base)
    lock.parent.mkdir(parents=True)
    lock.write_text("occupied", encoding="utf-8")
    with pytest.raises(PublicationConflictError):
        write_publication_record(tmp_path, base)
    assert lock.read_text(encoding="utf-8") == "occupied"


@pytest.mark.parametrize(
    "failure",
    ["reload", "inequality", "post_manifest", "post_manifest_missing",
     "post_manifest_read", "helper_contract_violation"],
)
def test_publication_failure_cleanup_after_candidate_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    target = publication_record_path(tmp_path, PUB1)
    lock = storage._series_lock_path(tmp_path, value)
    manifest = Path(tmp_path, *value.manifest_path.split("/"))
    original_manifest = manifest.read_bytes()
    if failure == "reload":
        monkeypatch.setattr(
            storage, "load_publication_record",
            Mock(side_effect=PublicationReadError("reload failed")),
        )
    elif failure == "inequality":
        monkeypatch.setattr(
            storage, "load_publication_record",
            Mock(return_value=replace(value, manifest_contract_version="2")),
        )
    elif failure.startswith("post_manifest"):
        resolved = manifest.resolve()
        final_error: Exception
        if failure == "post_manifest_missing":
            final_error = PublicationManifestNotFoundError("missing")
        elif failure == "post_manifest_read":
            final_error = storage.PublicationManifestError("read failed")
        else:
            final_error = PublicationManifestIntegrityError("changed")
        monkeypatch.setattr(
            storage, "verify_publication_manifest",
            Mock(side_effect=[resolved, resolved, final_error]),
        )
    else:
        monkeypatch.setattr(
            storage, "_fsync_directory_if_supported",
            Mock(side_effect=OSError("directory fsync")),
        )
    with pytest.raises((PublicationWriteError, storage.PublicationManifestError)):
        write_publication_record(tmp_path, value)
    assert not target.exists()
    assert not lock.exists()
    assert manifest.read_bytes() == original_manifest


@pytest.mark.parametrize("failure", ["directory", "lock"])
def test_publication_failure_before_candidate_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    if failure == "directory":
        monkeypatch.setattr(storage, "_create_write_directories", Mock(side_effect=PublicationWriteError("mkdir")))
    else:
        monkeypatch.setattr(storage, "_acquire_lock", Mock(side_effect=PublicationWriteError("lock")))
    with pytest.raises(PublicationWriteError):
        write_publication_record(tmp_path, value)
    assert not publication_record_path(tmp_path, PUB1).exists()


class FailingTextWriter:
    def __init__(self, source: object, failure: str) -> None:
        self.source = source
        self.failure = failure

    def __enter__(self) -> "FailingTextWriter":
        self.source.__enter__()  # type: ignore[attr-defined]
        return self

    def __exit__(self, *args: object) -> object:
        return self.source.__exit__(*args)  # type: ignore[attr-defined]

    def write(self, value: str) -> int:
        if self.failure == "write":
            raise OSError("injected write failure")
        return self.source.write(value)  # type: ignore[attr-defined,no-any-return]

    def flush(self) -> None:
        if self.failure == "flush":
            raise OSError("injected flush failure")
        self.source.flush()  # type: ignore[attr-defined]

    def fileno(self) -> int:
        return self.source.fileno()  # type: ignore[attr-defined,no-any-return]


@pytest.mark.parametrize(
    "stage",
    ["lock_open", "lock_write", "lock_flush", "lock_fsync",
     "publication_open", "publication_write", "publication_flush", "publication_fsync"],
)
def test_low_level_publication_io_failure_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    target = publication_record_path(tmp_path, PUB1)
    lock = storage._series_lock_path(tmp_path, value)
    manifest = Path(tmp_path, *value.manifest_path.split("/"))
    manifest_bytes = manifest.read_bytes()
    original_open = Path.open

    def injected_open(self: Path, *args: object, **kwargs: object) -> object:
        selected = (
            (stage.startswith("lock_") and self == lock)
            or (stage.startswith("publication_") and self == target)
        )
        operation = stage.rsplit("_", 1)[-1]
        if selected and operation == "open":
            raise OSError("injected open failure")
        source = cast(Any, original_open)(self, *args, **kwargs)
        if selected and operation in {"write", "flush"}:
            return FailingTextWriter(source, operation)
        return source

    monkeypatch.setattr(Path, "open", injected_open)
    if stage.endswith("fsync"):
        original_fsync = os.fsync
        calls = 0

        def injected_fsync(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            wanted = 1 if stage == "lock_fsync" else 2
            if calls == wanted:
                raise OSError("injected fsync failure")
            original_fsync(descriptor)

        monkeypatch.setattr(os, "fsync", injected_fsync)
    with pytest.raises(PublicationWriteError):
        write_publication_record(tmp_path, value)
    assert not target.exists()
    assert not lock.exists()
    assert manifest.read_bytes() == manifest_bytes


def test_withdrawal_missing_publication_and_invalid_relationship(tmp_path: Path) -> None:
    missing = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, NOW, "Correction."
    )
    with pytest.raises(PublicationNotFoundError):
        write_publication_withdrawal(tmp_path, missing)
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    write_publication_record(tmp_path, value)
    invalid = replace(missing, withdrawn_at=value.published_at - timedelta(seconds=1))
    with pytest.raises(PublicationWriteError):
        write_publication_withdrawal(tmp_path, invalid)


def test_withdrawal_preexisting_series_lock_is_preserved(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    write_publication_record(tmp_path, value)
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, value.published_at, "Correction."
    )
    lock = storage._series_lock_path(tmp_path, value)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("occupied", encoding="utf-8")
    with pytest.raises(PublicationConflictError):
        write_publication_withdrawal(tmp_path, withdrawal)
    assert lock.read_text(encoding="utf-8") == "occupied"
    assert not publication_withdrawal_path(tmp_path, PUB1).exists()


@pytest.mark.parametrize("failure", ["reload", "inequality"])
def test_withdrawal_failure_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    publication_path = write_publication_record(tmp_path, value)
    publication_bytes = publication_path.read_bytes()
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, value.published_at, "Correction."
    )
    target = publication_withdrawal_path(tmp_path, PUB1)
    lock = storage._series_lock_path(tmp_path, value)
    if failure == "reload":
        monkeypatch.setattr(
            storage, "load_publication_withdrawal",
            Mock(side_effect=[None, PublicationReadError("reload failed")]),
        )
    else:
        monkeypatch.setattr(
            storage, "load_publication_withdrawal",
            Mock(side_effect=[None, replace(withdrawal, reason="Different.")]),
        )
    with pytest.raises(PublicationWriteError):
        write_publication_withdrawal(tmp_path, withdrawal)
    assert not target.exists()
    assert not lock.exists()
    assert publication_path.read_bytes() == publication_bytes


@pytest.mark.parametrize(
    "stage", ["open", "write", "flush", "fsync"]
)
def test_low_level_withdrawal_io_failure_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    publication_path = write_publication_record(tmp_path, value)
    publication_bytes = publication_path.read_bytes()
    manifest = Path(tmp_path, *value.manifest_path.split("/"))
    manifest_bytes = manifest.read_bytes()
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, value.published_at, "Correction."
    )
    target = publication_withdrawal_path(tmp_path, PUB1)
    lock = storage._series_lock_path(tmp_path, value)
    original_open = Path.open

    def injected_open(self: Path, *args: object, **kwargs: object) -> object:
        mode = args[0] if args else kwargs.get("mode", "r")
        if self == target and mode == "x" and stage == "open":
            raise OSError("injected open failure")
        source = cast(Any, original_open)(self, *args, **kwargs)
        if self == target and mode == "x" and stage in {"write", "flush"}:
            return FailingTextWriter(source, stage)
        return source

    monkeypatch.setattr(Path, "open", injected_open)
    if stage == "fsync":
        original_fsync = os.fsync
        calls = 0

        def injected_fsync(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected fsync failure")
            original_fsync(descriptor)

        monkeypatch.setattr(os, "fsync", injected_fsync)
    with pytest.raises(PublicationWriteError):
        write_publication_withdrawal(tmp_path, withdrawal)
    assert not target.exists()
    assert not lock.exists()
    assert publication_path.read_bytes() == publication_bytes
    assert manifest.read_bytes() == manifest_bytes


@pytest.mark.parametrize("lifecycle", ["planned", "active", "closed"])
def test_academic_publication_supported_registration_lifecycles(
    tmp_path: Path, lifecycle: str
) -> None:
    work = ModuleWorkRef("quillan", "class_a", f"essay_{lifecycle}")
    value = publication(tmp_path, work, kind="academic_result_set")
    write_academic_work_registration(
        tmp_path, registration(work, lifecycle), expected_current_revision=None
    )
    revision_path = academic_work_registration_revision_path(tmp_path, work, 1)
    pointer_path = academic_work_registration_current_path(tmp_path, work)
    revision_bytes = revision_path.read_bytes()
    pointer_bytes = pointer_path.read_bytes()
    assert write_publication_record(tmp_path, value).exists()
    assert revision_path.read_bytes() == revision_bytes
    assert pointer_path.read_bytes() == pointer_bytes


@pytest.mark.parametrize("module_id", ["portia", "supports", "any_module"])
def test_intervention_publication_has_no_module_blacklist(
    tmp_path: Path, module_id: str
) -> None:
    work = ModuleWorkRef(module_id, "class_a", "support")
    value = publication(tmp_path, work)
    assert write_publication_record(tmp_path, value).exists()
    assert load_publication_record(tmp_path, PUB1).capabilities == (
        "intervention_status",
    )
    assert not academic_work_registration_current_path(tmp_path, work).exists()


def _calendar() -> AcademicPeriodCalendar:
    return AcademicPeriodCalendar(
        schema_version="1",
        record_type="academic_period_calendar",
        school_year="2026-2027",
        calendar_revision=1,
        created_at=NOW,
        updated_at=NOW,
        periods=(),
    )


def _route(work: ModuleWorkRef) -> RouteRegistration:
    locator = RouteLocator(PDS2_SCHEMA, work, "route_1")
    return RouteRegistration(
        schema_version="1",
        locator=locator,
        target=ModuleRecordRef(work.module_id, "page", "page_1", "1"),
        created_at=NOW.isoformat(),
        status="active",
        human_fallback="Essay page",
        module_details={},
    )


def _standards_library() -> StandardsLibrary:
    definition = StandardDefinition(
        standard_id="njsls-ela:RL.CR.11-12.1",
        code="RL.CR.11-12.1",
        source="NJSLS-ELA",
        short_name="Close Reading Evidence",
        description="Cite strong textual evidence.",
        subject="English Language Arts",
        category_path=("English Language Arts", "Reading Literature"),
    )
    return StandardsLibrary(
        standards=(definition,),
        profiles=(
            StandardsProfile(
                profile_id="english_12_njsls",
                standards=(definition.standard_id,),
                subject="English Language Arts",
            ),
        ),
    )


def _canonical_publication_snapshot(root: Path) -> tuple[object, ...]:
    collection_data: list[tuple[str, bytes]] = []
    for directory in (publications_dir(root), publication_withdrawals_dir(root)):
        if directory.exists():
            collection_data.extend(
                (str(path.relative_to(root)), path.read_bytes())
                for path in sorted(directory.rglob("*"))
                if path.is_file()
            )
    lock_root = root / "registry" / ".locks" / "publications"
    locks = (
        tuple(str(path.relative_to(root)) for path in sorted(lock_root.rglob("*")))
        if lock_root.exists()
        else ()
    )
    return (
        publications_dir(root).exists(),
        publication_withdrawals_dir(root).exists(),
        tuple(collection_data),
        locks,
    )


def _assert_unrelated_operation_preserves_publication_storage(
    root: Path, operation: object,
) -> None:
    before = _canonical_publication_snapshot(root)
    cast(Any, operation)()
    assert _canonical_publication_snapshot(root) == before


def test_unrelated_workflows_do_not_create_or_modify_publication_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: ensure_workspace_root(workspace)
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: open_school_year(workspace, "2026-2027", opened_at=NOW),
    )
    loaded_school_year = load_school_year_state(workspace)
    assert loaded_school_year is not None
    assert loaded_school_year.active_school_year == "2026-2027"
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: close_school_year(workspace, closed_at=NOW + timedelta(hours=1))
    )
    metadata = create_class_metadata("class_a", "2026-2027", created_at=NOW)
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: write_class_metadata_for_class(workspace, metadata)
    )
    assert load_class_metadata_for_class(workspace, "class_a") == metadata
    updated_metadata = create_class_metadata(
        "class_a", "2026-2027", created_at=NOW,
        updated_at=NOW + timedelta(minutes=1),
        module_details={"quillan": {"label": "Updated Class"}},
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: write_class_metadata_for_class(
            workspace, updated_metadata, overwrite=True
        ),
    )
    calendar = _calendar()
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: write_academic_period_calendar(
            workspace, calendar, expected_current_revision=None
        ),
    )
    assert load_academic_period_calendar_revision(workspace, "2026-2027", 1) == calendar
    assert load_current_academic_period_calendar(workspace, "2026-2027") == calendar
    work = ModuleWorkRef("quillan", "class_a", "essay")
    module_work_dir(workspace, work).mkdir(parents=True)
    work_registration = registration(work)
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: write_academic_work_registration(
            workspace, work_registration, expected_current_revision=None
        ),
    )
    assert load_academic_work_registration_revision(workspace, work, 1) == work_registration
    assert load_current_academic_work_registration(workspace, work) == work_registration
    route = _route(work)
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: write_route_registration(workspace, route)
    )
    assert load_route_registration(workspace, route.locator) == route
    roster = create_roster(
        "class_a",
        ({"student_id": "1001", "last_name": "Doe", "first_name": "Jane", "period": "2"},),
    )
    roster_path = class_roster_path(workspace, "class_a")
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: write_roster(roster_path, roster)
    )
    assert load_roster(roster_path).class_id == "class_a"
    source_scan = workspace / "scanner-export.pdf"
    source_scan.write_bytes(b"scan bytes")
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: retain_source_scan(workspace, source_scan, intake_timestamp=NOW),
    )
    library = _standards_library()
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: write_workspace_standards_library(workspace, library)
    )
    assert load_workspace_standards_library(workspace) == library
    monkeypatch.setattr("sys.stdin", io.StringIO("q\n"))
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: core_menu_main(["--workspace", str(workspace)])
    )
    capsys.readouterr()
    assert not publications_dir(workspace).exists()
    assert not publication_withdrawals_dir(workspace).exists()
    assert not tuple((workspace / "registry").rglob("*.lock"))

    published_work = ModuleWorkRef("portia", "class_a", "support")
    published = publication(workspace, published_work)
    publication_path = write_publication_record(workspace, published)
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, published.published_at, "Correction."
    )
    withdrawal_path = write_publication_withdrawal(workspace, withdrawal)
    publication_bytes = publication_path.read_bytes()
    withdrawal_bytes = withdrawal_path.read_bytes()
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: ensure_workspace_root(workspace)
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: open_school_year(
            workspace, "2026-2027", opened_at=NOW + timedelta(hours=2), overwrite=True
        ),
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: close_school_year(workspace, closed_at=NOW + timedelta(hours=3)),
    )
    final_metadata = create_class_metadata(
        "class_a", "2026-2027", created_at=NOW,
        updated_at=NOW + timedelta(minutes=2),
        module_details={"quillan": {"label": "Final Class"}},
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: write_class_metadata_for_class(
            workspace, final_metadata, overwrite=True
        ),
    )
    second_calendar = replace(
        calendar,
        calendar_revision=2,
        updated_at=NOW + timedelta(minutes=2),
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: write_academic_period_calendar(
            workspace, second_calendar, expected_current_revision=1
        ),
    )
    second_registration = replace(
        work_registration,
        registration_revision=2,
        updated_at=NOW + timedelta(minutes=2),
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: write_academic_work_registration(
            workspace, second_registration, expected_current_revision=1
        ),
    )
    second_route = replace(
        route, locator=RouteLocator(PDS2_SCHEMA, work, "route_2")
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: write_route_registration(workspace, second_route)
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: write_roster(roster_path, roster, overwrite=True)
    )
    second_scan = workspace / "scanner-export-2.pdf"
    second_scan.write_bytes(b"second scan bytes")
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: retain_source_scan(workspace, second_scan, intake_timestamp=NOW),
    )
    _assert_unrelated_operation_preserves_publication_storage(
        workspace,
        lambda: write_workspace_standards_library(
            workspace, library, overwrite=True
        ),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("q\n"))
    _assert_unrelated_operation_preserves_publication_storage(
        workspace, lambda: core_menu_main(["--workspace", str(workspace)])
    )
    capsys.readouterr()
    assert publication_path.read_bytes() == publication_bytes
    assert withdrawal_path.read_bytes() == withdrawal_bytes
    assert not tuple((workspace / "registry").rglob("*.lock"))


def test_publication_and_withdrawal_preserve_unrelated_canonical_bytes(
    tmp_path: Path,
) -> None:
    ensure_workspace_root(tmp_path)
    open_school_year(tmp_path, "2026-2027", opened_at=NOW)
    metadata = create_class_metadata("class_a", "2026-2027", created_at=NOW)
    class_path = write_class_metadata_for_class(tmp_path, metadata)
    calendar = _calendar()
    write_academic_period_calendar(tmp_path, calendar, expected_current_revision=None)
    work = ModuleWorkRef("quillan", "class_a", "essay")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    work_registration = registration(work)
    write_academic_work_registration(
        tmp_path, work_registration, expected_current_revision=None
    )
    route = _route(work)
    route_path = write_route_registration(tmp_path, route)
    roster = create_roster(
        "class_a",
        ({"student_id": "1001", "last_name": "Doe", "first_name": "Jane", "period": "2"},),
    )
    roster_path = class_roster_path(tmp_path, "class_a")
    write_roster(roster_path, roster)
    scan_input = tmp_path / "scanner-export.pdf"
    scan_input.write_bytes(b"source scan bytes")
    retained = retain_source_scan(tmp_path, scan_input, intake_timestamp=NOW)
    library = _standards_library()
    write_workspace_standards_library(tmp_path, library)
    standards_path = standards_library_path(tmp_path)
    value = publication(tmp_path, work, kind="academic_result_set")
    manifest_path = Path(tmp_path, *value.manifest_path.split("/"))
    producer_native_path = manifest_path.parent / "native-results.bin"
    producer_native_path.write_bytes(b"producer native bytes")
    protected_paths = (
        school_year_state_path(tmp_path),
        class_path,
        academic_period_revision_path(tmp_path, "2026-2027", 1),
        academic_period_current_path(tmp_path, "2026-2027"),
        academic_work_registration_revision_path(tmp_path, work, 1),
        academic_work_registration_current_path(tmp_path, work),
        route_path,
        roster_path,
        scan_input,
        retained.retained_source_path,
        standards_path,
        manifest_path,
        producer_native_path,
    )
    before_publication = tuple(path.read_bytes() for path in protected_paths)
    publication_path = write_publication_record(tmp_path, value)
    assert tuple(path.read_bytes() for path in protected_paths) == before_publication
    publication_bytes = publication_path.read_bytes()
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1,
        value.published_at + timedelta(minutes=1), "Producer correction required.",
    )
    before_withdrawal = tuple(path.read_bytes() for path in protected_paths)
    write_publication_withdrawal(tmp_path, withdrawal)
    assert tuple(path.read_bytes() for path in protected_paths) == before_withdrawal
    assert publication_path.read_bytes() == publication_bytes
    assert not tuple((tmp_path / "registry").rglob("*.lock"))


def test_directory_fsync_failures_are_best_effort_for_both_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    value = publication(tmp_path, work)
    original_open = os.open

    def fail_directory_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if flags == os.O_RDONLY:
            raise OSError("injected directory-open failure")
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    verify = Mock(wraps=storage.verify_publication_manifest)
    directory_sync = Mock(wraps=storage._fsync_directory_if_supported)
    monkeypatch.setattr(os, "open", fail_directory_open)
    monkeypatch.setattr(storage, "verify_publication_manifest", verify)
    monkeypatch.setattr(storage, "_fsync_directory_if_supported", directory_sync)
    publication_path = write_publication_record(tmp_path, value)
    assert verify.call_count == 3
    assert directory_sync.call_count == 1
    assert load_publication_record(tmp_path, PUB1) == value
    assert verify_publication_manifest(tmp_path, value) == Path(
        tmp_path, *value.manifest_path.split("/")
    ).resolve()
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", PUB1, value.published_at, "Correction."
    )
    withdrawal_path = write_publication_withdrawal(tmp_path, withdrawal)
    assert directory_sync.call_count == 2
    assert load_publication_withdrawal(tmp_path, PUB1) == withdrawal
    assert publication_path.exists() and withdrawal_path.exists()
    assert not tuple((tmp_path / "registry").rglob("*.lock"))
    assert not tuple(publications_dir(tmp_path).glob(".*"))
    assert not tuple(publication_withdrawals_dir(tmp_path).glob(".*"))
