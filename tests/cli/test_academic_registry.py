from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from tests.cli.conftest import run_cli
import pds_core.cli_support.academic_registry as academic_registry_cli
from pds_core import academic_catalog
from pds_core.cli import main
from pds_core.academic_catalog import ACADEMIC_CATALOG_APPLICATION_ID
from pds_core.academic_work_registration_storage import (
    write_academic_work_registration,
)
from pds_core.publication_records import (
    PublicationWithdrawal,
    publication_record_to_dict,
    publication_withdrawal_to_dict,
)
from pds_core.publication_storage import (
    write_publication_record,
    write_publication_withdrawal,
)
from pds_core.routing_models import ModuleWorkRef
from pds_core.registry_paths import (
    academic_work_registration_current_path,
    academic_work_registration_revision_path,
)
from tests.test_academic_work_registration_storage import prepare, registration
from tests.test_publication_storage import publication


def test_validate_text_and_json_on_empty_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "validate", capsys=capsys
    )
    assert code == 0 and not error
    assert "catalog.missing" in output
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "validate",
        "--format",
        "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 0 and not error and payload["schema_version"] == "1"
    assert payload["command"] == "academic registry validate"


def test_strict_promotes_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, _ = run_cli(
        tmp_path, "academic", "registry", "validate", "--strict", capsys=capsys
    )
    assert code == 1


def test_registry_validate_strict_json_ok_matches_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    normal = run_cli(
        tmp_path, "academic", "registry", "validate", "--format", "json",
        capsys=capsys,
    )
    strict = run_cli(
        tmp_path, "academic", "registry", "validate", "--strict",
        "--format", "json", capsys=capsys,
    )
    normal_payload, strict_payload = json.loads(normal[1]), json.loads(strict[1])
    assert normal[0] == 0 and normal_payload["ok"] is True
    assert strict[0] == 1 and strict_payload["ok"] is False
    assert normal_payload["data"] == strict_payload["data"]
    assert normal_payload["findings"] == strict_payload["findings"]


def test_registry_validate_json_ok_matches_exit_for_error_and_healthy_strict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    malformed = tmp_path / "registry/publications/pub_11111111111111111111111111111111.json"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("bad", encoding="utf-8")
    for strict in (False, True):
        arguments = ["academic", "registry", "validate", "--scope", "publications"]
        if strict:
            arguments.append("--strict")
        arguments.extend(("--format", "json"))
        code, output, _error = run_cli(tmp_path, *arguments, capsys=capsys)
        assert code == 1 and json.loads(output)["ok"] is False
    malformed.unlink()
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "validate", "--scope", "locks",
        "--strict", "--format", "json", capsys=capsys,
    )
    assert code == 0 and error == "" and json.loads(output)["ok"] is True


def test_status_does_not_load_malformed_standards_library(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "standards/library.json"
    path.parent.mkdir(parents=True)
    path.write_text("malformed", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "status", capsys=capsys
    )
    assert code == 0 and "Canonical status: valid" in output and not error


def test_clear_lock_dry_run_and_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock = tmp_path / "registry/.locks/catalog.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"owner")
    digest = hashlib.sha256(b"owner").hexdigest()
    code, output, _ = run_cli(
        tmp_path,
        "academic",
        "registry",
        "clear-lock",
        "catalog",
        "--expected-sha256",
        digest,
        "--dry-run",
        capsys=capsys,
    )
    assert code == 0 and "would be removed" in output and lock.exists()
    code, output, _ = run_cli(
        tmp_path,
        "academic",
        "registry",
        "clear-lock",
        "catalog",
        "--expected-sha256",
        digest,
        "--force",
        capsys=capsys,
    )
    assert code == 0 and "removed" in output and not lock.exists()


def test_rebuild_catalog_dry_run_is_nonmutating(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "rebuild-catalog",
        "--dry-run",
        capsys=capsys,
    )
    assert code == 0 and "no files were written" in output and not error
    assert not (tmp_path / "registry/catalog.sqlite").exists()


def test_rebuild_reports_the_installed_snapshot_after_preflight_source_change(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight_digest = academic_catalog._load_projection(tmp_path).snapshot_sha256
    original = academic_catalog.rebuild_academic_catalog

    def changed_rebuild(root: Path) -> object:
        work = ModuleWorkRef("quillan", "class_a", "essay")
        prepare(root, work)
        write_academic_work_registration(
            root,
            registration(work),
            expected_current_revision=None,
        )
        return original(root)

    monkeypatch.setattr(
        academic_catalog,
        "rebuild_academic_catalog",
        changed_rebuild,
    )
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "rebuild-catalog",
        capsys=capsys,
    )
    installed = academic_catalog.load_academic_catalog_metadata(tmp_path)
    assert code == 0 and error == ""
    assert installed.source_snapshot_sha256 in output
    assert installed.source_snapshot_sha256 != preflight_digest


def test_rebuild_verify_manifests_text_includes_optional_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    tmp_path.joinpath(*record.manifest_path.split("/")).unlink()
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "rebuild-catalog",
        "--verify-manifests", capsys=capsys,
    )
    assert code == 0 and error == ""
    assert "manifests.missing" in output
    assert (tmp_path / "registry/catalog.sqlite").is_file()


def test_rebuild_require_manifests_valid_preserves_existing_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    academic_catalog.rebuild_academic_catalog(tmp_path)
    catalog = tmp_path / "registry/catalog.sqlite"
    before = hashlib.sha256(catalog.read_bytes()).hexdigest()
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    tmp_path.joinpath(*record.manifest_path.split("/")).unlink()
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "rebuild-catalog",
        "--require-manifests-valid", "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert "manifests.missing" in {
        finding["code"] for finding in payload["findings"]
    }
    assert hashlib.sha256(catalog.read_bytes()).hexdigest() == before


@pytest.mark.parametrize(
    "arguments",
    [
        ("academic", "registry", "show", "registration", "quillan", "class_a", "essay"),
        ("academic", "registry", "show", "publication", "pub_11111111111111111111111111111111"),
        ("academic", "registry", "show", "withdrawal", "pub_11111111111111111111111111111111"),
        ("academic", "registry", "show", "catalog"),
        ("academic", "registry", "show", "lock", "catalog"),
        ("academic", "periods", "list", "--school-year", "2026-2027", "--calendar-revision", "1"),
    ],
)
def test_every_missing_entity_json_failure_is_one_clean_envelope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
) -> None:
    code, output, error = run_cli(
        tmp_path, *arguments, "--format", "json", capsys=capsys
    )
    payload = json.loads(output)
    assert code == 1 and error == ""
    assert payload["ok"] is False
    assert payload["data"] == {}


@pytest.mark.parametrize("duplicate_key", [False, True])
def test_malformed_exact_publication_is_record_invalid_not_not_found(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    duplicate_key: bool,
) -> None:
    publication_id = "pub_11111111111111111111111111111111"
    path = tmp_path / f"registry/publications/{publication_id}.json"
    path.parent.mkdir(parents=True)
    content = (
        '{"publication_id":"' + publication_id + '",'
        '"publication_id":"' + publication_id + '"}'
        if duplicate_key
        else "not-json"
    )
    path.write_text(content, encoding="utf-8")
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        publication_id, "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    codes = {finding["code"] for finding in payload["findings"]}
    assert code == 1 and error == "" and payload["ok"] is False
    assert "publications.record_invalid" in codes
    assert "publications.not_found" not in codes
    assert len(payload["findings"]) == 1
    assert "findings" not in payload["data"]
    assert output.endswith("\n") and output.count("\n") == 1


def test_malformed_exact_publication_text_preserves_record_invalid_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    publication_id = "pub_11111111111111111111111111111111"
    path = tmp_path / f"registry/publications/{publication_id}.json"
    path.parent.mkdir(parents=True)
    path.write_text("bad", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        publication_id, capsys=capsys,
    )
    assert code == 1 and error == ""
    assert "publications.record_invalid" in output
    assert "publications.not_found" not in output


def test_json_failures_for_malformed_collection_catalog_lock_and_rebuild(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    malformed = tmp_path / "registry/publications/bad.json"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("bad", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "list",
        "publications",
        "--format",
        "json",
        capsys=capsys,
    )
    assert code == 1 and error == "" and json.loads(output)["ok"] is False

    malformed.unlink()
    catalog = tmp_path / "registry/catalog.sqlite"
    connection = sqlite3.connect(catalog)
    connection.execute(f"PRAGMA application_id={ACADEMIC_CATALOG_APPLICATION_ID + 1}")
    connection.close()
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "show",
        "catalog",
        "--format",
        "json",
        capsys=capsys,
    )
    assert code == 1 and error == "" and json.loads(output)["ok"] is False

    lock = tmp_path / "registry/.locks/catalog.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"owner")
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "clear-lock",
        "catalog",
        "--expected-sha256",
        "0" * 64,
        "--force",
        "--format",
        "json",
        capsys=capsys,
    )
    assert code == 1 and error == "" and json.loads(output)["ok"] is False
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "rebuild-catalog",
        "--format",
        "json",
        capsys=capsys,
    )
    assert code == 1 and error == "" and json.loads(output)["ok"] is False


def test_json_operational_failure_uses_shared_error_helper(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        academic_registry_cli,
        "_audit_academic_registry_observation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("injected read failure")
        ),
    )
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "list",
        "publications",
        "--format",
        "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert payload["findings"][0]["message"] == "injected read failure"


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        (("academic", "registry", "list", "registrations"), "registrations.changed_during_audit"),
        (("academic", "registry", "list", "publications"), "publications.changed_during_audit"),
        (("academic", "registry", "list", "withdrawals"), "publications.changed_during_audit"),
        (("academic", "registry", "show", "catalog"), "catalog.changed_during_audit"),
    ],
)
def test_initial_registry_namespace_guard_race_is_normalized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
    code: str,
) -> None:
    if arguments[-1] == "catalog":
        catalog = tmp_path / "registry/catalog.sqlite"
        catalog.parent.mkdir(parents=True)
        catalog.write_bytes(b"present")
    changed = getattr(academic_registry_cli, "_NamespaceChangedError")
    monkeypatch.setattr(
        academic_registry_cli,
        "_namespace_guard",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(changed("race")),
    )
    exit_code, output, error = run_cli(
        tmp_path, *arguments, "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert exit_code == 1 and error == "" and payload["ok"] is False
    assert [finding["code"] for finding in payload["findings"]] == [code]


def test_initial_withdrawal_namespace_guard_race_is_normalized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = getattr(academic_registry_cli, "_namespace_guard")
    changed = getattr(academic_registry_cli, "_NamespaceChangedError")

    def changing(path: Path, depth: int) -> object:
        if path.name == "withdrawals":
            raise changed("withdrawal race")
        return original(path, depth)

    monkeypatch.setattr(academic_registry_cli, "_namespace_guard", changing)
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "list", "withdrawals",
        "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert [finding["code"] for finding in payload["findings"]] == [
        "publications.changed_during_audit"
    ]


def test_status_warning_and_strict_json_are_consistent_one_observation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = getattr(academic_registry_cli, "get_academic_registry_status")

    def counted(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        resolved: Path = original(*args, **kwargs)
        return resolved

    monkeypatch.setattr(academic_registry_cli, "get_academic_registry_status", counted)
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "status",
        "--format",
        "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 0 and error == "" and payload["ok"] is True
    assert payload["findings"][0]["code"] == "catalog.missing"
    assert "findings" not in payload["data"]
    assert calls == 1
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "status",
        "--strict",
        "--format",
        "json",
        capsys=capsys,
    )
    strict = json.loads(output)
    assert code == 1 and error == "" and strict["ok"] is False
    assert strict["findings"] == payload["findings"]
    assert calls == 2


def test_dispatcher_level_json_workspace_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace_file = tmp_path / "not-a-workspace"
    workspace_file.write_text("file", encoding="utf-8")
    code = main(
        [
            "--workspace",
            str(workspace_file),
            "academic",
            "registry",
            "status",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 1 and captured.err == ""
    assert payload["command"] == "academic registry status"
    assert payload["ok"] is False and payload["data"] == {}


def test_show_registration_stale_pointer_fails_with_integrity_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    second = replace(
        first,
        registration_revision=2,
        updated_at=first.updated_at + timedelta(minutes=1),
    )
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    write_academic_work_registration(tmp_path, second, expected_current_revision=1)
    pointer = academic_work_registration_current_path(tmp_path, work)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    payload["registration_revision"] = 1
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "show", "registration",
        "quillan", "class_a", "essay", "--format", "json",
        capsys=capsys,
    )
    result = json.loads(output)
    assert code == 1 and error == "" and result["ok"] is False
    assert {item["code"] for item in result["findings"]} >= {
        "registrations.pointer_invalid", "registrations.orphan_revision"
    }


def test_show_registration_historical_revision_reports_exact_current_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    second = replace(
        first,
        registration_revision=2,
        updated_at=first.updated_at + timedelta(minutes=1),
    )
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    write_academic_work_registration(tmp_path, second, expected_current_revision=1)
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "show", "registration",
        "quillan", "class_a", "essay", "--revision", "1",
        "--format", "json", capsys=capsys,
    )
    data = json.loads(output)["data"]
    assert code == 0 and error == ""
    assert data["is_current"] is False and data["current_revision"] == 2


def test_registration_list_all_revisions_returns_valid_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    first = registration(work)
    second = replace(
        first,
        registration_revision=2,
        updated_at=first.updated_at + timedelta(minutes=1),
    )
    write_academic_work_registration(tmp_path, first, expected_current_revision=None)
    write_academic_work_registration(tmp_path, second, expected_current_revision=1)
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "list", "registrations",
        "--all-revisions", "--format", "json", capsys=capsys,
    )
    rows = json.loads(output)["data"]["rows"]
    assert code == 0 and error == ""
    assert [(row["revision"], row["current"]) for row in rows] == [
        (1, False), (2, True)
    ]


def test_registration_hidden_artifact_list_consistency(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    hidden = academic_work_registration_current_path(tmp_path, work).parent / ".interrupted"
    hidden.write_text("artifact", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "list", "registrations",
        "--format", "json", capsys=capsys,
    )
    assert code == 0 and error == ""
    assert len(json.loads(output)["data"]["rows"]) == 1


def test_registration_list_orphan_revision_fails_instead_of_omitting_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    academic_work_registration_current_path(tmp_path, work).unlink()
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "list", "registrations",
        "--all-revisions", "--format", "json", capsys=capsys,
    )
    result = json.loads(output)
    assert code == 1 and error == "" and result["ok"] is False
    assert "registrations.orphan_revision" in {
        item["code"] for item in result["findings"]
    }


def test_show_publication_invalid_withdrawal_is_top_level_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", record.publication_id,
        record.published_at - timedelta(seconds=1), "invalid chronology",
    )
    path = tmp_path / f"registry/withdrawals/{record.publication_id}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(publication_withdrawal_to_dict(withdrawal)), encoding="utf-8")
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "show", "publication", record.publication_id,
        "--format", "json", capsys=capsys,
    )
    result = json.loads(output)
    assert code == 1 and error == "" and result["ok"] is False
    assert "findings" not in result["data"]
    assert "publications.withdrawal_chronology_invalid" in {
        item["code"] for item in result["findings"]
    }
    assert result["data"]["derived_state"] is None
    assert "is_withdrawn" not in result["data"]


def test_exact_intervention_publication_ignores_unrelated_registration_corruption(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    bad = academic_work_registration_revision_path(
        tmp_path, ModuleWorkRef("quillan", "class_b", "essay"), 1
    )
    bad.parent.mkdir(parents=True)
    bad.write_text("bad", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        record.publication_id, "--format", "json", capsys=capsys,
    )
    assert code == 0 and error == ""
    assert json.loads(output)["data"]["publication"]["publication_id"] == record.publication_id


def test_exact_academic_publication_ignores_unrelated_missing_producer_work_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    record = publication(tmp_path, work, kind="academic_result_set")
    write_publication_record(tmp_path, record)
    producer_root = tmp_path / "classes/class_a/modules/quillan/work/essay"
    shutil.rmtree(producer_root)
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        record.publication_id, "--format", "json", capsys=capsys,
    )
    assert code == 0 and error == ""
    assert json.loads(output)["data"]["registration"] is not None


def test_exact_academic_publication_ignores_unrelated_malformed_registration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    record = publication(tmp_path, work, kind="academic_result_set")
    write_publication_record(tmp_path, record)
    bad = academic_work_registration_revision_path(
        tmp_path, ModuleWorkRef("quillan", "class_b", "essay"), 1
    )
    bad.parent.mkdir(parents=True)
    bad.write_text("bad", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        record.publication_id, "--format", "json", capsys=capsys,
    )
    assert code == 0 and error == ""
    assert json.loads(output)["data"]["registration"] is not None


def test_exact_withdrawal_ignores_unrelated_registration_corruption(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    write_publication_withdrawal(
        tmp_path,
        PublicationWithdrawal(
            "1", "publication_withdrawal", record.publication_id,
            record.published_at + timedelta(seconds=1), "valid",
        ),
    )
    bad = academic_work_registration_revision_path(
        tmp_path, ModuleWorkRef("quillan", "class_b", "essay"), 1
    )
    bad.parent.mkdir(parents=True)
    bad.write_text("bad", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "withdrawal",
        record.publication_id, "--format", "json", capsys=capsys,
    )
    assert code == 0 and error == ""
    assert json.loads(output)["data"]["withdrawal"]["publication_id"] == record.publication_id


def test_missing_selected_registration_does_not_emit_derived_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    record = publication(tmp_path, work, kind="academic_result_set")
    path = tmp_path / f"registry/publications/{record.publication_id}.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(publication_record_to_dict(record)), encoding="utf-8"
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        record.publication_id, "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert payload["data"]["derived_state"] is None
    assert "is_series_head" not in payload["data"]


def test_invalid_publication_series_does_not_emit_derived_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    first = publication(tmp_path, work)
    second = replace(
        publication(
            tmp_path, work,
            publication_id="pub_22222222222222222222222222222222",
            revision=2,
        ),
        supersedes_publication_id=first.publication_id,
    )
    third = replace(
        publication(
            tmp_path, work,
            publication_id="pub_33333333333333333333333333333333",
            revision=3,
        ),
        supersedes_publication_id=first.publication_id,
    )
    for record in (first, second, third):
        path = tmp_path / f"registry/publications/{record.publication_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(publication_record_to_dict(record)), encoding="utf-8"
        )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        first.publication_id, "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert payload["data"]["derived_state"] is None
    assert "successors" not in payload["data"]


def test_show_publication_failed_manifest_verification_keeps_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    manifest = tmp_path.joinpath(*record.manifest_path.split("/"))
    manifest.write_bytes(manifest.read_bytes() + b"changed")
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "show", "publication", record.publication_id,
        "--verify-manifest", "--format", "json", capsys=capsys,
    )
    result = json.loads(output)
    assert code == 1 and error == "" and result["ok"] is False
    assert result["data"]["publication"]["publication_id"] == record.publication_id
    assert "findings" not in result["data"]
    assert "manifests.digest_mismatch" in {
        item["code"] for item in result["findings"]
    }


def test_manifest_containment_is_re_resolved_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    changed = getattr(academic_registry_cli, "resolve_publication_manifest_path")

    def containment_changed(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("containment changed")

    monkeypatch.setattr(
        academic_registry_cli,
        "resolve_publication_manifest_path",
        containment_changed,
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        record.publication_id, "--verify-manifest", "--format", "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert changed is not containment_changed
    assert code == 1 and error == "" and payload["ok"] is False
    assert [finding["code"] for finding in payload["findings"]] == [
        "manifests.changed_during_audit"
    ]


def test_manifest_parent_symlink_replacement_after_verification_is_detected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    manifest = tmp_path.joinpath(*record.manifest_path.split("/"))
    parent = manifest.parent
    external = tmp_path / "external"
    external.mkdir()
    (external / manifest.name).write_bytes(manifest.read_bytes())
    original = getattr(
        academic_registry_cli, "resolve_publication_manifest_path"
    )

    def replacing(*args: object, **kwargs: object) -> Path:
        saved = parent.with_name("exports.saved")
        parent.rename(saved)
        try:
            parent.symlink_to(external, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable on this platform: {exc}")
        resolved: Path = original(*args, **kwargs)
        return resolved

    monkeypatch.setattr(
        academic_registry_cli, "resolve_publication_manifest_path", replacing
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        record.publication_id, "--verify-manifest", "--format", "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert [finding["code"] for finding in payload["findings"]] == [
        "manifests.changed_during_audit"
    ]


def test_show_catalog_drift_exit_behavior_preserves_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    academic_catalog.rebuild_academic_catalog(tmp_path)
    revision = academic_work_registration_revision_path(tmp_path, work, 1)
    revision.write_text(revision.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "show", "catalog", "--format", "json",
        capsys=capsys,
    )
    result = json.loads(output)
    assert code == 1 and error == "" and result["ok"] is False
    assert "metadata" in result["data"] and "findings" not in result["data"]
    assert any(item["code"].startswith("catalog.") for item in result["findings"])


def test_show_publication_changed_after_audit_is_guarded_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    path = tmp_path / f"registry/publications/{record.publication_id}.json"
    original = getattr(academic_registry_cli, "_audit_academic_registry_observation")

    def changing(*args: object, **kwargs: object) -> object:
        report = original(*args, **kwargs)
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return report

    monkeypatch.setattr(
        academic_registry_cli, "_audit_academic_registry_observation", changing
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "publication",
        record.publication_id, "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert "publications.changed_during_audit" in {
        item["code"] for item in payload["findings"]
    }


def test_show_withdrawal_changed_after_audit_is_guarded_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    withdrawal = PublicationWithdrawal(
        "1", "publication_withdrawal", record.publication_id,
        record.published_at + timedelta(seconds=1), "valid",
    )
    write_publication_withdrawal(tmp_path, withdrawal)
    path = tmp_path / f"registry/withdrawals/{record.publication_id}.json"
    original = getattr(academic_registry_cli, "_audit_academic_registry_observation")

    def changing(*args: object, **kwargs: object) -> object:
        report = original(*args, **kwargs)
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return report

    monkeypatch.setattr(
        academic_registry_cli, "_audit_academic_registry_observation", changing
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "withdrawal",
        record.publication_id, "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert "publications.changed_during_audit" in {
        item["code"] for item in payload["findings"]
    }


def test_show_catalog_replaced_after_audit_is_guarded_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    academic_catalog.rebuild_academic_catalog(tmp_path)
    path = tmp_path / "registry/catalog.sqlite"
    original = getattr(academic_registry_cli, "audit_academic_registry")

    def replacing(*args: object, **kwargs: object) -> object:
        report = original(*args, **kwargs)
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(path.read_bytes())
        os.replace(replacement, path)
        return report

    monkeypatch.setattr(academic_registry_cli, "audit_academic_registry", replacing)
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "catalog", "--format", "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert "metadata" not in payload["data"]
    assert "catalog.changed_during_audit" in {
        item["code"] for item in payload["findings"]
    }


def test_show_catalog_sources_replaced_after_metadata_observation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    academic_catalog.rebuild_academic_catalog(tmp_path)
    path = tmp_path / "registry/catalog.sqlite"
    original = academic_catalog.load_academic_catalog_metadata
    calls = 0

    def replacing(root: Path) -> object:
        nonlocal calls
        metadata = original(root)
        calls += 1
        if calls == 2:
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(path.read_bytes())
            os.replace(replacement, path)
        return metadata

    monkeypatch.setattr(academic_catalog, "load_academic_catalog_metadata", replacing)
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "show", "catalog", "--sources",
        "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert "sources" not in payload["data"] and "metadata" not in payload["data"]


def _publication_state_fixture(tmp_path: Path) -> dict[str, str]:
    work = ModuleWorkRef("portia", "class_a", "support")
    a1 = publication(tmp_path, work)
    a2 = replace(
        publication(
            tmp_path,
            work,
            publication_id="pub_22222222222222222222222222222222",
            revision=2,
        ),
        supersedes_publication_id=a1.publication_id,
    )
    b1 = replace(
        publication(
            tmp_path,
            work,
            publication_id="pub_33333333333333333333333333333333",
            revision=3,
        ),
        record_set_id="other",
        record_set_revision=1,
        supersedes_publication_id=None,
    )
    b2 = replace(
        publication(
            tmp_path,
            work,
            publication_id="pub_44444444444444444444444444444444",
            revision=4,
        ),
        record_set_id="other",
        record_set_revision=2,
        supersedes_publication_id=b1.publication_id,
    )
    for value in (a1, a2, b1, b2):
        write_publication_record(tmp_path, value)
    write_publication_withdrawal(
        tmp_path,
        PublicationWithdrawal(
            "1",
            "publication_withdrawal",
            a2.publication_id,
            a2.published_at + timedelta(minutes=1),
            "head withdrawn",
        ),
    )
    write_publication_withdrawal(
        tmp_path,
        PublicationWithdrawal(
            "1",
            "publication_withdrawal",
            b1.publication_id,
            b1.published_at + timedelta(minutes=2),
            "history withdrawn",
        ),
    )
    return {"a1": a1.publication_id, "a2": a2.publication_id, "b1": b1.publication_id, "b2": b2.publication_id}


@pytest.mark.parametrize(
    ("state", "expected_keys"),
    [
        ("current", {"b2"}),
        ("series-heads", {"a2", "b2"}),
        ("historical", {"a1", "b1"}),
        ("withdrawn", {"a2", "b1"}),
        ("all", {"a1", "a2", "b1", "b2"}),
    ],
)
def test_publication_state_matrix_and_independent_booleans(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    state: str,
    expected_keys: set[str],
) -> None:
    ids = _publication_state_fixture(tmp_path)
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "registry",
        "list",
        "publications",
        "--state",
        state,
        "--format",
        "json",
        capsys=capsys,
    )
    rows = json.loads(output)["data"]["rows"]
    assert code == 0 and error == ""
    assert {row["publication_id"] for row in rows} == {
        ids[key] for key in expected_keys
    }
    for row in rows:
        assert row["is_historical"] is (not row["is_series_head"])
        assert row["is_current_selectable"] is (
            row["is_series_head"] and not row["is_withdrawn"]
        )


def test_publication_order_pagination_and_repeatability(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _publication_state_fixture(tmp_path)
    arguments = (
        "academic", "registry", "list", "publications", "--state", "all",
        "--limit", "2", "--offset", "1", "--format", "json",
    )
    first = run_cli(tmp_path, *arguments, capsys=capsys)
    second = run_cli(tmp_path, *arguments, capsys=capsys)
    assert first == second
    rows = json.loads(first[1])["data"]["rows"]
    assert len(rows) == 2
    order = [(row["published_at"], row["publication_id"]) for row in rows]
    assert order == sorted(order, key=lambda value: (value[0], value[1]), reverse=True)


def test_filtered_publication_list_ignores_unrelated_assignable_malformed_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selected = publication(
        tmp_path, ModuleWorkRef("portia", "class_a", "selected")
    )
    write_publication_record(tmp_path, selected)
    malformed = tmp_path / "registry/publications/pub_99999999999999999999999999999999.json"
    malformed.write_text(
        json.dumps({
            "publication_id": "pub_99999999999999999999999999999999",
            "work": {"class_id": "class_b", "module_id": "portia", "work_id": "other"},
            "publication_kind": "intervention_record_set",
            "record_set_id": "results",
        }),
        encoding="utf-8",
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "list", "publications",
        "--work-id", "selected", "--format", "json", capsys=capsys,
    )
    rows = json.loads(output)["data"]["rows"]
    assert code == 0 and error == ""
    assert [row["publication_id"] for row in rows] == [selected.publication_id]


def test_filtered_withdrawal_list_ignores_unrelated_assignable_invalid_withdrawal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selected = publication(
        tmp_path, ModuleWorkRef("portia", "class_a", "selected")
    )
    unrelated = publication(
        tmp_path,
        ModuleWorkRef("portia", "class_b", "other"),
        publication_id="pub_99999999999999999999999999999999",
    )
    for record in (selected, unrelated):
        write_publication_record(tmp_path, record)
    write_publication_withdrawal(
        tmp_path,
        PublicationWithdrawal(
            "1", "publication_withdrawal", selected.publication_id,
            selected.published_at + timedelta(seconds=1), "valid",
        ),
    )
    invalid = PublicationWithdrawal(
        "1", "publication_withdrawal", unrelated.publication_id,
        unrelated.published_at - timedelta(seconds=1), "invalid",
    )
    invalid_path = tmp_path / f"registry/withdrawals/{unrelated.publication_id}.json"
    invalid_path.write_text(
        json.dumps(publication_withdrawal_to_dict(invalid)), encoding="utf-8"
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "list", "withdrawals",
        "--work-id", "selected", "--format", "json", capsys=capsys,
    )
    rows = json.loads(output)["data"]["rows"]
    assert code == 0 and error == ""
    assert [row["publication_id"] for row in rows] == [selected.publication_id]


def test_selected_invalid_withdrawal_fails_list_chronology_validation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = publication(
        tmp_path, ModuleWorkRef("portia", "class_a", "selected")
    )
    write_publication_record(tmp_path, record)
    invalid = PublicationWithdrawal(
        "1", "publication_withdrawal", record.publication_id,
        record.published_at - timedelta(seconds=1), "invalid",
    )
    path = tmp_path / f"registry/withdrawals/{record.publication_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(publication_withdrawal_to_dict(invalid)), encoding="utf-8"
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "list", "withdrawals",
        "--work-id", "selected", "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert "publications.withdrawal_chronology_invalid" in {
        item["code"] for item in payload["findings"]
    }


@pytest.mark.parametrize("entity", ["publications", "withdrawals"])
def test_publication_list_collection_race_is_normalized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    entity: str,
) -> None:
    record = publication(tmp_path, ModuleWorkRef("portia", "class_a", "support"))
    write_publication_record(tmp_path, record)
    if entity == "withdrawals":
        write_publication_withdrawal(
            tmp_path,
            PublicationWithdrawal(
                "1", "publication_withdrawal", record.publication_id,
                record.published_at + timedelta(seconds=1), "valid",
            ),
        )
    original = getattr(
        academic_registry_cli, "_audit_academic_registry_observation"
    )

    def changing(*args: object, **kwargs: object) -> object:
        observed = original(*args, **kwargs)
        collection = tmp_path / f"registry/{entity}"
        (collection / ".new-entry").write_text("race", encoding="utf-8")
        return observed

    monkeypatch.setattr(
        academic_registry_cli, "_audit_academic_registry_observation", changing
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "list", entity,
        "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert {item["code"] for item in payload["findings"]} == {
        "publications.changed_during_audit"
    }


def test_registration_list_history_race_is_normalized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    write_academic_work_registration(
        tmp_path, registration(work), expected_current_revision=None
    )
    pointer = academic_work_registration_current_path(tmp_path, work)
    original = getattr(
        academic_registry_cli, "_audit_academic_registry_observation"
    )

    def changing(*args: object, **kwargs: object) -> object:
        observed = original(*args, **kwargs)
        pointer.write_text(pointer.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return observed

    monkeypatch.setattr(
        academic_registry_cli, "_audit_academic_registry_observation", changing
    )
    code, output, error = run_cli(
        tmp_path, "academic", "registry", "list", "registrations",
        "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert {item["code"] for item in payload["findings"]} == {
        "registrations.changed_during_audit"
    }


def test_successful_list_show_entities_and_catalog_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    prepare(tmp_path, work)
    value = registration(work)
    write_academic_work_registration(
        tmp_path, value, expected_current_revision=None
    )
    pub_work = ModuleWorkRef("portia", "class_a", "support")
    pub = publication(tmp_path, pub_work)
    write_publication_record(tmp_path, pub)
    withdrawal = PublicationWithdrawal(
        "1",
        "publication_withdrawal",
        pub.publication_id,
        pub.published_at + timedelta(minutes=1),
        "complete",
    )
    write_publication_withdrawal(tmp_path, withdrawal)
    for arguments in (
        ("academic", "registry", "show", "registration", "quillan", "class_a", "essay"),
        ("academic", "registry", "show", "publication", pub.publication_id),
        ("academic", "registry", "show", "withdrawal", pub.publication_id),
    ):
        code, output, error = run_cli(
            tmp_path, *arguments, "--format", "json", capsys=capsys
        )
        assert code == 0 and error == "" and json.loads(output)["ok"] is True
    code, _, _ = run_cli(
        tmp_path, "academic", "registry", "rebuild-catalog", capsys=capsys
    )
    assert code == 0
    code, output, error = run_cli(
        tmp_path,
        "academic", "registry", "show", "catalog", "--format", "json",
        capsys=capsys,
    )
    assert code == 0 and error == "" and json.loads(output)["ok"] is True
