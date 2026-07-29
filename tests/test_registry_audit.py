from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pds_core.registry_audit import (
    RegistryAuditFinding,
    RegistryAuditOptions,
    RegistryAuditValidationError,
    RegistryAuditConflictError,
    RegistryLockClearResult,
    RegistryLockObservation,
    audit_academic_registry,
    clear_registry_lock,
    get_academic_registry_status,
    get_registry_lock,
    list_registry_locks,
)
from pds_core.academic_period_storage import (
    academic_period_revision_path,
    load_academic_period_calendar_revision,
)
from pds_core.academic_work_registration_storage import (
    load_academic_work_registration_revision,
    write_academic_work_registration,
)
from pds_core.class_metadata import ClassMetadata, write_class_metadata_for_class
from pds_core.publication_storage import (
    verify_publication_manifest,
    write_publication_record,
)
from pds_core.publication_records import (
    PublicationRecord,
    PublicationWithdrawal,
    publication_record_to_dict,
    publication_withdrawal_to_dict,
)
from pds_core.registry_paths import (
    academic_catalog_path,
    academic_work_registration_current_path,
    academic_work_registration_revision_path,
    publication_record_path,
    publication_withdrawal_path,
)
from pds_core.routes import module_work_dir
from pds_core.routing_models import ModuleWorkRef
from tests.test_academic_period_storage import _calendar, _write_pointer, _write_raw_revision
from tests.test_publication_storage import publication
from tests.test_academic_work_registration_storage import (
    prepare as prepare_registration,
    registration,
)


def test_finding_is_frozen_normalized_and_defensive() -> None:
    related = ["registry/work"]
    identity = [("work_id", "essay"), ("class_id", "class_a")]
    finding = RegistryAuditFinding(
        "warning",
        "locks",
        "locks.present",
        "A coordination lock is present.",
        "registry/.locks/catalog.lock",
        related,  # type: ignore[arg-type]
        identity,  # type: ignore[arg-type]
        "clear_lock",
    )
    related.append("other")
    identity.append(("module_id", "quillan"))
    assert finding.related_paths == ("registry/work",)
    assert finding.identity == (("class_id", "class_a"), ("work_id", "essay"))
    with pytest.raises(FrozenInstanceError):
        finding.message = "changed"  # type: ignore[misc]


def test_options_normalize_scope_order_and_validate() -> None:
    value = RegistryAuditOptions(scopes=("locks", "catalog", "locks"))
    assert value.scopes == ("catalog", "locks")
    with pytest.raises(RegistryAuditValidationError):
        RegistryAuditOptions(scopes=("invalid",))  # type: ignore[arg-type]
    with pytest.raises(RegistryAuditValidationError):
        RegistryAuditOptions(module_id="Upper")


def test_empty_workspace_aggregates_catalog_warning(tmp_path: Path) -> None:
    report = audit_academic_registry(tmp_path)
    assert report.canonical_valid
    assert report.ok
    assert [item.code for item in report.findings] == ["catalog.missing"]
    assert report.counts.warning_findings == 1


def test_multiple_independent_malformed_records_are_aggregated(tmp_path: Path) -> None:
    period = tmp_path / "settings/academic_periods/2026-2027/revisions/1.json"
    publication = tmp_path / "registry/publications/pub_11111111111111111111111111111111.json"
    period.parent.mkdir(parents=True)
    publication.parent.mkdir(parents=True)
    period.write_text('{"schema_version":"1","schema_version":"1"}', encoding="utf-8")
    publication.write_text("not json", encoding="utf-8")
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(scopes=("academic_periods", "publications")),
    )
    codes = {item.code for item in report.findings}
    assert "academic_periods.revision_invalid" in codes
    assert "publications.record_invalid" in codes
    assert not report.canonical_valid


def test_clear_lock_requires_exact_fingerprint_and_preserves_parent(tmp_path: Path) -> None:
    lock = tmp_path / "registry/.locks/catalog.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"owner")
    digest = hashlib.sha256(b"owner").hexdigest()
    dry = clear_registry_lock(
        tmp_path, "catalog", expected_sha256=digest, dry_run=True
    )
    assert not dry.removed and lock.exists()
    with pytest.raises(RegistryAuditConflictError):
        clear_registry_lock(
            tmp_path, "catalog", expected_sha256="0" * 64, force=True
        )
    result = clear_registry_lock(
        tmp_path, "catalog", expected_sha256=digest, force=True
    )
    assert result.removed and not lock.exists() and lock.parent.exists()


def test_direct_models_reject_malformed_iterables_without_raw_errors(
    tmp_path: Path,
) -> None:
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("locks",))
    )
    status = get_academic_registry_status(tmp_path)
    with pytest.raises(RegistryAuditValidationError):
        replace(report, findings=[object()])  # type: ignore[arg-type]
    with pytest.raises(RegistryAuditValidationError):
        replace(status, findings="bad")  # type: ignore[arg-type]
    observation = RegistryLockObservation(
        "catalog",
        "catalog",
        "registry/.locks/catalog.lock",
        0,
        hashlib.sha256(b"").hexdigest(),
        datetime.now(UTC),
    )
    with pytest.raises(RegistryAuditValidationError):
        RegistryLockClearResult(observation, True, True)
    with pytest.raises(RegistryAuditValidationError):
        RegistryLockClearResult("bad", True, False)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    ["registry/work", b"registry/work", {"registry/work": True}, (None,)],
)
def test_registry_finding_rejects_malformed_related_path_collections(
    value: object,
) -> None:
    with pytest.raises(RegistryAuditValidationError):
        RegistryAuditFinding(
            "warning",
            "locks",
            "locks.present",
            "lock",
            related_paths=value,  # type: ignore[arg-type]
        )


def test_registry_options_rejects_mapping_scopes() -> None:
    with pytest.raises(RegistryAuditValidationError):
        RegistryAuditOptions(scopes={"locks": True})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value", [1, True, 1.5, b"pub", {"id": "pub"}, ["pub"], object()]
)
def test_registry_audit_options_rejects_non_string_publication_id(
    value: object,
) -> None:
    with pytest.raises(RegistryAuditValidationError):
        RegistryAuditOptions(publication_id=value)  # type: ignore[arg-type]


def test_lock_scope_independently_discovers_all_four_kinds(tmp_path: Path) -> None:
    paths = {
        "catalog": tmp_path / "registry/.locks/catalog.lock",
        "period:2026-2027": tmp_path / "settings/academic_periods/2026-2027/.write.lock",
        "registration:class_a/quillan/essay": tmp_path / "registry/work/class_a/quillan/essay/.write.lock",
        "publication:class_a/quillan/essay/academic_result_set/results": tmp_path / "registry/.locks/publications/class_a/quillan/essay/academic_result_set/results.lock",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"owner")
    observations = list_registry_locks(tmp_path)
    assert {item.lock_id for item in observations} == set(paths)
    assert get_registry_lock(tmp_path, "catalog") == next(
        item for item in observations if item.lock_id == "catalog"
    )
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("locks",))
    )
    assert report.counts.locks == 4
    assert [item.code for item in report.findings].count("locks.present") == 4


@pytest.mark.parametrize(
    "relative",
    [
        "registry/.locks/publications/.hidden",
        "registry/.locks/publications/class_a/Upper/essay/academic_result_set/results.lock",
        "registry/.locks/publications/class_a/quillan/essay/bad/results.lock",
        "registry/.locks/publications/class_a/quillan/essay/academic_result_set/results.tmp",
        "registry/.locks/publications/class_a/quillan/essay/academic_result_set/extra/nested.lock",
    ],
)
def test_malformed_lock_namespace_is_never_silently_omitted(
    tmp_path: Path, relative: str
) -> None:
    path = tmp_path / relative
    if relative.endswith("nested.lock"):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"owner")
    elif relative.endswith(".hidden"):
        path.mkdir(parents=True)
    else:
        path.parent.mkdir(parents=True)
        path.write_bytes(b"owner")
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("locks",))
    )
    assert "locks.unexpected_entry" in {item.code for item in report.findings}
    assert not report.ok


def test_academic_period_audit_valid_pointer_orphan_hidden_and_filter(
    tmp_path: Path,
) -> None:
    first = _calendar(school_year="2026-2027")
    _write_raw_revision(tmp_path, first)
    _write_pointer(tmp_path, school_year="2026-2027")
    hidden = tmp_path / "settings/academic_periods/2026-2027/.unknown"
    hidden.write_text("artifact", encoding="utf-8")
    unrelated = academic_period_revision_path(tmp_path, "2027-2028", 1)
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("bad", encoding="utf-8")
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("academic_periods",), school_year="2026-2027"
        ),
    )
    assert report.counts.calendar_revisions == 1
    assert "academic_periods.hidden_artifact" in {
        item.code for item in report.findings
    }
    assert all("2027-2028" not in (item.path or "") for item in report.findings)


def test_academic_period_missing_pointer_reports_orphan(tmp_path: Path) -> None:
    _write_raw_revision(tmp_path, _calendar())
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("academic_periods",))
    )
    codes = {item.code for item in report.findings}
    assert {"academic_periods.pointer_missing", "academic_periods.orphan_revision"}.issubset(codes)


def test_calendar_revision_and_pointer_races_have_canonical_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = _calendar()
    revision_path = _write_raw_revision(tmp_path, value)
    _write_pointer(tmp_path)
    original = load_academic_period_calendar_revision

    def race_revision(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        revision_path.unlink()
        return result

    monkeypatch.setattr(
        "pds_core.registry_audit.load_academic_period_calendar_revision",
        race_revision,
    )
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("academic_periods",))
    )
    assert "academic_periods.changed_during_audit" in {
        item.code for item in report.findings
    }


def test_academic_period_revision_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = _calendar()
    path = _write_raw_revision(tmp_path, value)
    _write_pointer(tmp_path)
    original = load_academic_period_calendar_revision

    def racing(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        path.unlink()
        return result

    monkeypatch.setattr("pds_core.registry_audit.load_academic_period_calendar_revision", racing)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("academic_periods",)))
    assert "academic_periods.changed_during_audit" in {item.code for item in report.findings}


def test_academic_period_pointer_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_raw_revision(tmp_path, _calendar())
    pointer = _write_pointer(tmp_path)
    original = __import__("pds_core.registry_audit", fromlist=["load_current_academic_period_calendar"]).load_current_academic_period_calendar

    def racing(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        pointer.unlink()
        return result

    monkeypatch.setattr("pds_core.registry_audit.load_current_academic_period_calendar", racing)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("academic_periods",)))
    assert "academic_periods.changed_during_audit" in {item.code for item in report.findings}


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing", "manifests.missing"),
        ("directory", "manifests.not_regular_file"),
        ("digest", "manifests.digest_mismatch"),
    ],
)
def test_manifest_auditor_classifies_direct_outcomes(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    record = publication(tmp_path, work)
    manifest = tmp_path.joinpath(*record.manifest_path.split("/"))
    write_publication_record(tmp_path, record)
    if mutation == "missing":
        manifest.unlink()
    elif mutation == "directory":
        manifest.unlink()
        manifest.mkdir()
    elif mutation == "digest":
        manifest.write_bytes(manifest.read_bytes() + b"changed")
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications", "manifests"),
            discover_installed_producer_profiles=False,
        ),
    )
    assert expected in {item.code for item in report.findings}


def test_manifest_unreadable_race_cache_contradictory_digest_and_non_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    first = publication(tmp_path, work)
    manifest = tmp_path.joinpath(*first.manifest_path.split("/"))
    manifest.write_bytes(b"\xff\xfe")
    digest = hashlib.sha256(b"\xff\xfe").hexdigest()
    first = replace(first, manifest_digest=digest)
    second = replace(
        first,
        publication_id="pub_22222222222222222222222222222222",
        record_set_id="other",
    )
    write_publication_record(tmp_path, first)
    write_publication_record(tmp_path, second)
    calls = 0
    original = verify_publication_manifest

    def counted(*args: object, **kwargs: object) -> Path:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("pds_core.registry_audit.verify_publication_manifest", counted)
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("manifests",))
    )
    assert report.manifests_valid and report.counts.verified_manifests == 2
    assert calls == 1


def test_manifest_changed_during_hash_is_not_digest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    record = publication(tmp_path, work)
    write_publication_record(tmp_path, record)
    manifest = tmp_path.joinpath(*record.manifest_path.split("/"))
    original = verify_publication_manifest

    def racing(*args: object, **kwargs: object) -> Path:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        manifest.write_bytes(manifest.read_bytes() + b"changed")
        return result

    monkeypatch.setattr("pds_core.registry_audit.verify_publication_manifest", racing)
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("manifests",))
    )
    codes = {item.code for item in report.findings}
    assert "manifests.changed_during_audit" in codes
    assert "manifests.digest_mismatch" not in codes


def test_manifest_resolved_path_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    first = publication(tmp_path, work)
    second = replace(first, publication_id="pub_22222222222222222222222222222222", record_set_id="other")
    write_publication_record(tmp_path, first)
    write_publication_record(tmp_path, second)
    calls = 0
    original = verify_publication_manifest

    def counted(*args: object, **kwargs: object) -> Path:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("pds_core.registry_audit.verify_publication_manifest", counted)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("manifests",)))
    assert report.counts.verified_manifests == 2 and calls == 1


def test_manifest_contradictory_expected_digests(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    first = publication(tmp_path, work)
    second = replace(first, publication_id="pub_22222222222222222222222222222222", record_set_id="other", manifest_digest="0" * 64)
    write_publication_record(tmp_path, first)
    _write_publication_json(tmp_path, second)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("manifests",)))
    assert report.counts.verified_manifests == 1
    assert "manifests.digest_mismatch" in {item.code for item in report.findings}


def test_manifest_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    monkeypatch.setattr("pds_core.registry_audit.resolve_publication_manifest_path", lambda *_args: (_ for _ in ()).throw(OSError("denied")))
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("manifests",)))
    assert "manifests.unreadable" in {item.code for item in report.findings}


def test_registration_audit_valid_history_hidden_missing_root_and_filter(
    tmp_path: Path,
) -> None:
    selected = ModuleWorkRef("quillan", "class_a", "essay")
    unrelated = ModuleWorkRef("quillan", "class_b", "essay")
    for work in (selected, unrelated):
        prepare_registration(tmp_path, work)
        write_academic_work_registration(
            tmp_path, registration(work), expected_current_revision=None
        )
    hidden = academic_work_registration_current_path(tmp_path, selected).parent / ".unknown"
    hidden.write_text("artifact", encoding="utf-8")
    unrelated_revision = academic_work_registration_revision_path(
        tmp_path, unrelated, 1
    )
    unrelated_revision.write_text("bad", encoding="utf-8")
    producer_root = module_work_dir(tmp_path, selected)
    producer_root.rename(producer_root.with_name("essay_missing"))
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("registrations",),
            class_id="class_a",
            module_id="quillan",
            work_id="essay",
        ),
    )
    codes = {item.code for item in report.findings}
    assert "registrations.hidden_artifact" in codes
    assert "registrations.producer_work_missing" in codes
    assert all("class_b" not in (item.path or "") for item in report.findings)


def test_registration_malformed_pointer_revision_and_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare_registration(tmp_path, work)
    value = registration(work)
    write_academic_work_registration(
        tmp_path, value, expected_current_revision=None
    )
    pointer = academic_work_registration_current_path(tmp_path, work)
    pointer.write_text("bad", encoding="utf-8")
    revision = academic_work_registration_revision_path(tmp_path, work, 1)
    original = load_academic_work_registration_revision

    def racing(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        revision.unlink()
        return result

    monkeypatch.setattr(
        "pds_core.registry_audit.load_academic_work_registration_revision",
        racing,
    )
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("registrations",))
    )
    codes = {item.code for item in report.findings}
    assert "registrations.changed_during_audit" in codes
    assert "registrations.pointer_invalid" in codes


def test_registration_revision_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare_registration(tmp_path, work)
    write_academic_work_registration(tmp_path, registration(work), expected_current_revision=None)
    path = academic_work_registration_revision_path(tmp_path, work, 1)
    original = load_academic_work_registration_revision

    def racing(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        path.unlink()
        return result

    monkeypatch.setattr("pds_core.registry_audit.load_academic_work_registration_revision", racing)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("registrations",)))
    assert "registrations.changed_during_audit" in {item.code for item in report.findings}


def test_registration_pointer_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare_registration(tmp_path, work)
    write_academic_work_registration(tmp_path, registration(work), expected_current_revision=None)
    pointer = academic_work_registration_current_path(tmp_path, work)
    from pds_core import registry_audit as audit_module
    original = getattr(audit_module, "load_current_academic_work_registration")

    def racing(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        pointer.unlink()
        return result

    monkeypatch.setattr(audit_module, "load_current_academic_work_registration", racing)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("registrations",)))
    assert "registrations.changed_during_audit" in {item.code for item in report.findings}


def test_registration_school_year_filtering_has_exact_counts_and_findings(tmp_path: Path) -> None:
    works = (
        ModuleWorkRef("quillan", "class_a", "essay"),
        ModuleWorkRef("quillan", "class_b", "essay"),
        ModuleWorkRef("quillan", "class_c", "essay"),
    )
    now = datetime(2026, 7, 28, tzinfo=UTC)
    for work, year in zip(works[:2], ("2026-2027", "2027-2028")):
        write_class_metadata_for_class(tmp_path, ClassMetadata(work.class_id, year, now, now, {}))
    for work in works:
        prepare_registration(tmp_path, work)
        write_academic_work_registration(tmp_path, registration(work), expected_current_revision=None)
    academic_work_registration_revision_path(tmp_path, works[1], 1).write_text("bad", encoding="utf-8")
    academic_work_registration_revision_path(tmp_path, works[2], 1).write_text("bad", encoding="utf-8")
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("registrations",), school_year="2026-2027"))
    assert report.counts.registration_works == 1
    assert report.counts.registration_revisions == 1
    assert report.canonical_valid
    assert all("class_b" not in (item.path or "") and "class_c" not in (item.path or "") for item in report.findings)


def _write_publication_json(tmp_path: Path, record: PublicationRecord) -> None:
    path = publication_record_path(tmp_path, record.publication_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(publication_record_to_dict(record)),
        encoding="utf-8",
    )


@pytest.mark.parametrize("defect", ["missing_predecessor", "branch", "cycle"])
def test_publication_auditor_rejects_invalid_complete_series(
    tmp_path: Path, defect: str
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    first = publication(tmp_path, work)
    second = replace(
        publication(
            tmp_path,
            work,
            publication_id="pub_22222222222222222222222222222222",
            revision=2,
        ),
        supersedes_publication_id=first.publication_id,
    )
    values = [first, second]
    if defect == "missing_predecessor":
        values = [replace(second, supersedes_publication_id="pub_33333333333333333333333333333333")]
    elif defect == "branch":
        third = replace(
            publication(
                tmp_path,
                work,
                publication_id="pub_33333333333333333333333333333333",
                revision=3,
            ),
            supersedes_publication_id=first.publication_id,
        )
        values.append(third)
    elif defect == "cycle":
        values = [
            replace(first, supersedes_publication_id=second.publication_id),
            second,
        ]
    for value in values:
        _write_publication_json(tmp_path, value)
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("publications",))
    )
    assert "publications.series_invalid" in {
        item.code for item in report.findings
    }


def test_publication_logical_duplicate_competing_head_and_registration_missing(
    tmp_path: Path,
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    first = publication(tmp_path, work, kind="academic_result_set")
    duplicate = replace(
        first, publication_id="pub_22222222222222222222222222222222"
    )
    _write_publication_json(tmp_path, first)
    _write_publication_json(tmp_path, duplicate)
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("publications",))
    )
    codes = {item.code for item in report.findings}
    assert "publications.logical_revision_duplicate" in codes
    assert "publications.competing_head" in codes
    assert "publications.registration_missing" in codes


def test_publication_only_audit_ignores_unrelated_registration_corruption(
    tmp_path: Path,
) -> None:
    selected = publication(
        tmp_path, ModuleWorkRef("portia", "class_a", "support")
    )
    _write_publication_json(tmp_path, selected)
    unrelated = ModuleWorkRef("quillan", "class_b", "essay")
    bad = academic_work_registration_revision_path(tmp_path, unrelated, 1)
    bad.parent.mkdir(parents=True)
    bad.write_text("bad", encoding="utf-8")
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("publications",))
    )
    assert report.canonical_valid
    assert report.counts.registration_revisions == 0
    assert all(finding.domain != "registrations" for finding in report.findings)


def test_publication_only_audit_counts_only_selected_registration_relationship(
    tmp_path: Path,
) -> None:
    selected_work = ModuleWorkRef("quillan", "class_a", "essay")
    unrelated_work = ModuleWorkRef("quillan", "class_b", "essay")
    for work in (selected_work, unrelated_work):
        prepare_registration(tmp_path, work)
        write_academic_work_registration(
            tmp_path, registration(work), expected_current_revision=None
        )
    selected = publication(tmp_path, selected_work, kind="academic_result_set")
    _write_publication_json(tmp_path, selected)
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications",), publication_id=selected.publication_id
        ),
    )
    assert report.canonical_valid
    assert report.counts.registration_works == 1
    assert report.counts.registration_revisions == 1


def test_publication_plus_explicit_registration_scope_audits_complete_registration_state(
    tmp_path: Path,
) -> None:
    selected_work = ModuleWorkRef("quillan", "class_a", "essay")
    unrelated_work = ModuleWorkRef("quillan", "class_b", "essay")
    prepare_registration(tmp_path, selected_work)
    write_academic_work_registration(
        tmp_path, registration(selected_work), expected_current_revision=None
    )
    malformed = academic_work_registration_revision_path(
        tmp_path, unrelated_work, 1
    )
    malformed.parent.mkdir(parents=True)
    malformed.write_text("bad", encoding="utf-8")
    selected = publication(tmp_path, selected_work, kind="academic_result_set")
    _write_publication_json(tmp_path, selected)
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications", "registrations")
        ),
    )
    assert not report.canonical_valid
    assert any(finding.domain == "registrations" for finding in report.findings)


@pytest.mark.parametrize("malformed", [False, True])
def test_selected_referenced_registration_missing_or_malformed_is_reported(
    tmp_path: Path, malformed: bool
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    selected = publication(tmp_path, work, kind="academic_result_set")
    _write_publication_json(tmp_path, selected)
    if malformed:
        revision = academic_work_registration_revision_path(tmp_path, work, 1)
        revision.parent.mkdir(parents=True)
        revision.write_text("bad", encoding="utf-8")
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications",), publication_id=selected.publication_id
        ),
    )
    assert "publications.registration_missing" in {
        finding.code for finding in report.findings
    }
    assert report.counts.registration_revisions == 0


def test_withdrawal_orphan_chronology_and_exact_filter(tmp_path: Path) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    record = publication(tmp_path, work)
    _write_publication_json(tmp_path, record)
    invalid = PublicationWithdrawal(
        schema_version="1",
        record_type="publication_withdrawal",
        publication_id=record.publication_id,
        withdrawn_at=record.published_at - timedelta(seconds=1),
        reason="invalid chronology",
    )
    withdrawal_path = publication_withdrawal_path(tmp_path, record.publication_id)
    withdrawal_path.parent.mkdir(parents=True)
    withdrawal_path.write_text(
        json.dumps(publication_withdrawal_to_dict(invalid)), encoding="utf-8"
    )
    orphan = replace(
        invalid,
        publication_id="pub_33333333333333333333333333333333",
        withdrawn_at=record.published_at,
    )
    publication_withdrawal_path(tmp_path, orphan.publication_id).write_text(
        json.dumps(publication_withdrawal_to_dict(orphan)), encoding="utf-8"
    )
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("publications",))
    )
    codes = {item.code for item in report.findings}
    assert "publications.withdrawal_chronology_invalid" in codes
    assert "publications.withdrawal_orphan" in codes
    exact = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications",), publication_id=record.publication_id
        ),
    )
    assert any(
        orphan.publication_id in (item.path or "")
        and item.code == "publications.withdrawal_orphan"
        for item in exact.findings
    )


def test_selected_malformed_publication_under_work_filter_is_a_blocker(tmp_path: Path) -> None:
    path = publication_record_path(tmp_path, "pub_11111111111111111111111111111111")
    path.parent.mkdir(parents=True)
    path.write_text('{"work":{"class_id":"class_a","module_id":"portia","work_id":"support"}}', encoding="utf-8")
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("publications",), class_id="class_a", module_id="portia", work_id="support"))
    assert not report.canonical_valid
    assert "publications.record_invalid" in {item.code for item in report.findings}


def test_unassignable_malformed_publication_remains_namespace_blocker(
    tmp_path: Path,
) -> None:
    path = publication_record_path(
        tmp_path, "pub_11111111111111111111111111111111"
    )
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications",), class_id="class_unrelated"
        ),
    )
    assert not report.canonical_valid
    assert "publications.record_invalid" in {
        item.code for item in report.findings
    }


def test_unrelated_identifiable_malformed_publication_is_filtered_by_work(
    tmp_path: Path,
) -> None:
    path = publication_record_path(
        tmp_path, "pub_11111111111111111111111111111111"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "publication_id": "pub_11111111111111111111111111111111",
                "work": {
                    "class_id": "class_other",
                    "module_id": "portia",
                    "work_id": "support",
                },
                "publication_kind": "intervention_record_set",
                "record_set_id": "results",
            }
        ),
        encoding="utf-8",
    )
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications",), class_id="class_selected"
        ),
    )
    assert report.canonical_valid
    assert not report.findings


def test_unrelated_invalid_withdrawal_is_filtered_by_school_year(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 28, tzinfo=UTC)
    for class_id, year in (
        ("class_selected", "2026-2027"),
        ("class_other", "2027-2028"),
    ):
        write_class_metadata_for_class(
            tmp_path, ClassMetadata(class_id, year, now, now, {})
        )
    record = publication(
        tmp_path, ModuleWorkRef("portia", "class_other", "support")
    )
    _write_publication_json(tmp_path, record)
    withdrawal = PublicationWithdrawal(
        "1",
        "publication_withdrawal",
        record.publication_id,
        record.published_at - timedelta(seconds=1),
        "invalid",
    )
    path = publication_withdrawal_path(tmp_path, record.publication_id)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(publication_withdrawal_to_dict(withdrawal)), encoding="utf-8"
    )
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications",), school_year="2026-2027"
        ),
    )
    assert report.canonical_valid
    assert not report.findings


def _symlink_or_skip(link: Path, target: Path, *, directory: bool) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        pytest.skip(f"symlinks unavailable on this platform: {error}")


def test_academic_period_symlinked_root_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "outside-periods"
    target.mkdir()
    _symlink_or_skip(tmp_path / "settings/academic_periods", target, directory=True)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("academic_periods",)))
    assert not report.canonical_valid and report.findings


@pytest.mark.parametrize("level", ["school_year", "revisions"])
def test_academic_period_symlinked_directory_level_is_rejected(
    tmp_path: Path, level: str
) -> None:
    target = tmp_path / "outside"
    target.mkdir()
    if level == "school_year":
        link = tmp_path / "settings/academic_periods/2026-2027"
    else:
        school = tmp_path / "settings/academic_periods/2026-2027"
        school.mkdir(parents=True)
        link = school / "revisions"
    _symlink_or_skip(link, target, directory=True)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("academic_periods",)))
    assert not report.canonical_valid


def test_academic_period_symlinked_current_pointer_is_rejected(tmp_path: Path) -> None:
    _write_raw_revision(tmp_path, _calendar())
    target = tmp_path / "outside-pointer.json"
    target.write_text("{}", encoding="utf-8")
    _symlink_or_skip(tmp_path / "settings/academic_periods/2026-2027/current.json", target, directory=False)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("academic_periods",)))
    assert "academic_periods.pointer_invalid" in {item.code for item in report.findings}


@pytest.mark.parametrize("level", ["root", "class", "module", "work", "revisions"])
def test_registration_symlinked_directory_level_is_rejected(
    tmp_path: Path, level: str
) -> None:
    target = tmp_path / "outside-registration"
    target.mkdir()
    parts = {
        "root": "registry/work",
        "class": "registry/work/class_a",
        "module": "registry/work/class_a/quillan",
        "work": "registry/work/class_a/quillan/essay",
        "revisions": "registry/work/class_a/quillan/essay/revisions",
    }
    _symlink_or_skip(tmp_path / parts[level], target, directory=True)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("registrations",)))
    assert not report.canonical_valid


def test_registration_symlinked_current_pointer_is_rejected(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare_registration(tmp_path, work)
    revision = academic_work_registration_revision_path(tmp_path, work, 1)
    revision.parent.mkdir(parents=True)
    revision.write_text(json.dumps({}), encoding="utf-8")
    target = tmp_path / "outside-current.json"
    target.write_text("{}", encoding="utf-8")
    _symlink_or_skip(academic_work_registration_current_path(tmp_path, work), target, directory=False)
    report = audit_academic_registry(tmp_path, options=RegistryAuditOptions(scopes=("registrations",)))
    assert "registrations.pointer_invalid" in {item.code for item in report.findings}


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"class_id": "class_a"}, 1),
        ({"module_id": "portia"}, 2),
        ({"work_id": "support"}, 1),
        (
            {"class_id": "class_a", "module_id": "portia", "work_id": "support"},
            1,
        ),
        ({"publication_id": "pub_11111111111111111111111111111111"}, 1),
    ],
)
def test_publication_filters_have_exact_counts(
    tmp_path: Path, filters: dict[str, str], expected: int
) -> None:
    first = publication(
        tmp_path,
        ModuleWorkRef("portia", "class_a", "support"),
        publication_id="pub_11111111111111111111111111111111",
    )
    second = publication(
        tmp_path,
        ModuleWorkRef("portia", "class_b", "other"),
        publication_id="pub_22222222222222222222222222222222",
    )
    write_publication_record(tmp_path, first)
    write_publication_record(tmp_path, second)
    report = audit_academic_registry(
        tmp_path,
        options=RegistryAuditOptions(
            scopes=("publications", "manifests"), **filters  # type: ignore[arg-type]
        ),
    )
    assert report.counts.publication_records == expected
    assert report.counts.publication_series == expected
    assert report.counts.verified_manifests == expected


def test_identical_content_lock_replacement_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "registry/.locks/catalog.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"owner")
    digest = hashlib.sha256(b"owner").hexdigest()
    original = Path.lstat
    calls = 0

    def replacing(path: Path) -> os.stat_result:
        nonlocal calls
        if path == lock:
            calls += 1
            if calls == 3:
                replacement = lock.with_suffix(".replacement")
                replacement.write_bytes(b"owner")
                os.replace(replacement, lock)
        return original(path)

    monkeypatch.setattr(Path, "lstat", replacing)
    with pytest.raises(RegistryAuditConflictError):
        clear_registry_lock(tmp_path, "catalog", expected_sha256=digest, force=True)
    assert lock.read_bytes() == b"owner"


def _catalog_with_registration(tmp_path: Path) -> Path:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare_registration(tmp_path, work)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    from pds_core import academic_catalog
    academic_catalog.rebuild_academic_catalog(tmp_path)
    return academic_catalog_path(tmp_path)


def _catalog_codes(tmp_path: Path) -> set[str]:
    report = audit_academic_registry(
        tmp_path, options=RegistryAuditOptions(scopes=("catalog",))
    )
    return {item.code for item in report.findings}


def test_catalog_source_missing(tmp_path: Path) -> None:
    _catalog_with_registration(tmp_path)
    work = ModuleWorkRef("quillan", "class_a", "essay")
    first = registration(work)
    write_academic_work_registration(
        tmp_path,
        replace(first, registration_revision=2, updated_at=first.updated_at + timedelta(minutes=1)),
        expected_current_revision=1,
    )
    assert "catalog.source_missing" in _catalog_codes(tmp_path)


def test_catalog_source_extra(tmp_path: Path) -> None:
    _catalog_with_registration(tmp_path)
    work = ModuleWorkRef("quillan", "class_a", "essay")
    shutil.rmtree(academic_work_registration_current_path(tmp_path, work).parent)
    assert "catalog.source_extra" in _catalog_codes(tmp_path)


def test_catalog_source_changed(tmp_path: Path) -> None:
    _catalog_with_registration(tmp_path)
    work = ModuleWorkRef("quillan", "class_a", "essay")
    revision = academic_work_registration_revision_path(tmp_path, work, 1)
    revision.write_text(revision.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert "catalog.source_changed" in _catalog_codes(tmp_path)


def test_catalog_canonical_entity_missing(tmp_path: Path) -> None:
    _catalog_with_registration(tmp_path)
    work = ModuleWorkRef("quillan", "class_a", "essay")
    first = registration(work)
    write_academic_work_registration(
        tmp_path,
        replace(first, registration_revision=2, updated_at=first.updated_at + timedelta(minutes=1)),
        expected_current_revision=1,
    )
    assert "catalog.canonical_entity_missing" in _catalog_codes(tmp_path)


def test_catalog_orphan_entity(tmp_path: Path) -> None:
    _catalog_with_registration(tmp_path)
    work = ModuleWorkRef("quillan", "class_a", "essay")
    shutil.rmtree(academic_work_registration_current_path(tmp_path, work).parent)
    assert "catalog.orphan_entity" in _catalog_codes(tmp_path)


def test_catalog_content_mismatch(tmp_path: Path) -> None:
    path = _catalog_with_registration(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE academic_work_registrations SET title='Different'"
        )
    assert "catalog.snapshot_mismatch" in _catalog_codes(tmp_path)


def test_catalog_changed_during_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _catalog_with_registration(tmp_path)
    from pds_core import academic_catalog
    original = academic_catalog._read_connection

    def changing(candidate: Path) -> sqlite3.Connection:
        connection = original(candidate)
        path.touch()
        return connection

    monkeypatch.setattr(academic_catalog, "_read_connection", changing)
    assert "catalog.changed_during_audit" in _catalog_codes(tmp_path)


def test_status_uses_immutable_catalog_observation_after_audit_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _catalog_with_registration(tmp_path)
    from pds_core import registry_audit as audit_module
    original = audit_module._audit_academic_registry_observation

    def removing(*args: object, **kwargs: object) -> object:
        observation = original(*args, **kwargs)  # type: ignore[arg-type]
        path.unlink()
        return observation

    monkeypatch.setattr(
        audit_module, "_audit_academic_registry_observation", removing
    )
    status = get_academic_registry_status(tmp_path)
    assert status.catalog_state == "ready"
    assert status.catalog_sources_current is True
    assert status.catalog_built_at is not None
    assert status.catalog_source_snapshot_sha256 is not None
