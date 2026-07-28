from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import pds_core.registry_services as services
from pds_core.academic_work_registration_storage import (
    AcademicWorkRegistrationConflictError,
    AcademicWorkRegistrationIntegrityError,
    AcademicWorkRegistrationReadError,
    AcademicWorkRegistrationWriteError,
    list_academic_work_registration_revisions,
    load_academic_work_registration_revision,
    load_current_academic_work_registration,
    write_academic_work_registration,
)
from pds_core.academic_work_registrations import (
    AcademicWorkRegistration,
    academic_work_registration_to_dict,
)
from pds_core.publication_records import (
    PublicationRecord,
    PublicationRecordValidationError,
    PublicationWithdrawal,
)
from pds_core.publication_storage import (
    PublicationConflictError,
    PublicationIntegrityError,
    PublicationManifestError,
    PublicationManifestIntegrityError,
    PublicationManifestNotFoundError,
    PublicationNotFoundError,
    PublicationReadError,
    PublicationStorageError,
    PublicationWriteError,
    load_publication_record,
    load_publication_withdrawal,
    write_publication_record,
    write_publication_withdrawal,
)
from pds_core.routes import module_work_dir
from pds_core.registry_paths import (
    academic_work_registration_current_path,
    academic_work_registration_revision_path,
    publication_record_path,
    publication_withdrawal_path,
)
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef


NOW = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
PUB1 = "pub_11111111111111111111111111111111"
PUB2 = "pub_22222222222222222222222222222222"


def registration_request(
    work: ModuleWorkRef, **changes: object
) -> services.AcademicWorkRegistrationRequest:
    values = dict(
        work=work,
        producer_contract_version="1",
        title="Essay",
        work_kind="assignment",
        academic_intent="summative",
        lifecycle="active",
        source_records=(),
    )
    values.update(changes)
    return services.AcademicWorkRegistrationRequest(**values)  # type: ignore[arg-type]


def manifest_request(
    root: Path, work: ModuleWorkRef, revision: int, *, kind: str = "intervention_record_set"
) -> services.PublicationManifestRequest:
    relative = (
        f"classes/{work.class_id}/modules/{work.module_id}/work/{work.work_id}/"
        f"exports/{revision}.json"
    )
    path = root.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f'{{"revision":{revision}}}\n'.encode())
    return services.PublicationManifestRequest(
        work=work,
        source_record=None,
        publication_kind=kind,  # type: ignore[arg-type]
        capabilities=("intervention_status",) if kind == "intervention_record_set" else ("points",),
        record_set_id="results",
        record_set_revision=revision,
        manifest_contract_version="1",
        manifest_path=relative,
        academic_work_registration_revision=1 if kind == "academic_result_set" else None,
    )


def test_request_models_are_frozen_slotted_and_defensive() -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    records = [
        ModuleRecordRef("quillan", "source", "z"),
        ModuleRecordRef("quillan", "source", "a"),
    ]
    request = registration_request(work, source_records=records)
    records.clear()
    assert tuple(item.record_id for item in request.source_records) == ("a", "z")
    assert not hasattr(request, "__dict__")
    with pytest.raises(FrozenInstanceError):
        request.title = "Changed"  # type: ignore[misc]
    with pytest.raises(services.RegistryServiceValidationError):
        registration_request(work, source_records=(ModuleRecordRef("portia", "x", "y"),))
    with pytest.raises(services.RegistryServiceValidationError):
        services.PublicationWithdrawalRequest("bad", "reason")


def test_registration_create_replay_update_and_strict_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    request = registration_request(work)
    created = services.register_academic_work(tmp_path, request)
    assert created.disposition == "created"
    assert created.registration.registration_revision == 1
    assert created.registration.created_at == created.registration.updated_at == NOW
    replay = services.register_academic_work(tmp_path, request)
    assert replay.disposition == "existing"
    assert list_academic_work_registration_revisions(tmp_path, work) == (1,)
    with pytest.raises(services.RegistryServiceConflictError):
        services.register_academic_work(tmp_path, registration_request(work, title="Other"))
    update = registration_request(work, title="Revised", lifecycle="closed")
    updated = services.update_academic_work_registration(
        tmp_path, update, expected_current_revision=1
    )
    assert updated.disposition == "updated"
    assert updated.registration.registration_revision == 2
    assert updated.registration.created_at == NOW
    assert services.update_academic_work_registration(
        tmp_path, update, expected_current_revision=1
    ).disposition == "existing"
    with pytest.raises(AcademicWorkRegistrationConflictError):
        write_academic_work_registration(
            tmp_path, updated.registration, expected_current_revision=1
        )


def test_publication_replay_supersession_withdrawal_and_strict_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class_a", "support")
    ids = iter((PUB1, PUB2))
    monkeypatch.setattr(services, "_new_publication_id", lambda: next(ids))
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    first_request = manifest_request(tmp_path, work, 1)
    first = services.publish_manifest_revision(tmp_path, first_request)
    assert first.disposition == "created"
    assert first.publication.publication_id == PUB1
    assert first.publication.manifest_digest == hashlib.sha256(b'{"revision":1}\n').hexdigest()
    assert services.publish_manifest_revision(tmp_path, first_request).publication == first.publication
    second_request = manifest_request(tmp_path, work, 2)
    with pytest.raises(services.RegistryServiceConflictError):
        services.publish_manifest_revision(tmp_path, second_request)
    second = services.supersede_manifest_revision(
        tmp_path, second_request, expected_current_publication_id=PUB1
    )
    assert second.publication.supersedes_publication_id == PUB1
    assert services.supersede_manifest_revision(
        tmp_path, second_request, expected_current_publication_id=PUB1
    ).disposition == "existing"
    withdrawal_request = services.PublicationWithdrawalRequest(PUB2, "Replaced upstream")
    withdrawn = services.withdraw_publication(tmp_path, withdrawal_request)
    assert withdrawn.disposition == "created"
    assert services.withdraw_publication(tmp_path, withdrawal_request).disposition == "existing"
    replay = services.supersede_manifest_revision(
        tmp_path, second_request, expected_current_publication_id=PUB1
    )
    assert replay.withdrawal == withdrawn.withdrawal
    assert load_publication_record(tmp_path, PUB2) == second.publication
    assert load_publication_withdrawal(tmp_path, PUB2) == withdrawn.withdrawal
    with pytest.raises(PublicationConflictError):
        write_publication_record(tmp_path, first.publication)
    with pytest.raises(PublicationConflictError):
        write_publication_withdrawal(tmp_path, withdrawn.withdrawal)


def test_digest_contradiction_expected_digest_and_academic_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class_a", "essay")
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    request = manifest_request(tmp_path, work, 1)
    services.publish_manifest_revision(tmp_path, request)
    path = tmp_path.joinpath(*request.manifest_path.split("/"))
    original = path.read_bytes()
    path.write_bytes(b"changed")
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.publish_manifest_revision(tmp_path, request)
    path.write_bytes(original)
    wrong = replace(request, expected_manifest_digest="0" * 64)
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.publish_manifest_revision(tmp_path, wrong)

    academic_work = ModuleWorkRef("quillan", "class_b", "quiz")
    academic = manifest_request(tmp_path, academic_work, 1, kind="academic_result_set")
    with pytest.raises(services.RegistryServiceConflictError):
        services.publish_manifest_revision(tmp_path, academic)


def test_retrieval_and_validation_errors(tmp_path: Path) -> None:
    with pytest.raises(services.RegistryServiceValidationError):
        services.get_canonical_publication_record(tmp_path, "bad")
    with pytest.raises(services.RegistryServiceNotFoundError):
        services.get_canonical_publication_record(tmp_path, PUB1)
    with pytest.raises(services.RegistryServiceValidationError):
        services.PublicationManifestRequest(
            work=ModuleWorkRef("portia", "class", "work"),
            source_record=None,
            publication_kind="intervention_record_set",
            capabilities=("points",),
            record_set_id="results",
            record_set_revision=1,
            manifest_contract_version="1",
            manifest_path="classes/class/modules/portia/work/work/result.json",
            academic_work_registration_revision=None,
        )


@pytest.mark.parametrize("digest", [None, "a" * 64])
def test_expected_digest_accepts_absent_and_valid(tmp_path: Path, digest: str | None) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    assert replace(request, expected_manifest_digest=digest).expected_manifest_digest == digest


@pytest.mark.parametrize(
    "digest",
    [123, b"a" * 64, True, "A" * 64, "a" * 63, "a" * 65, " a" * 32, "g" * 64],
)
def test_expected_digest_rejects_every_malformed_type_and_shape(
    tmp_path: Path, digest: object
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    with pytest.raises(services.RegistryServiceValidationError):
        replace(request, expected_manifest_digest=digest)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "generated",
    [None, 123, "PUB_" + "a" * 32, "pub_a", "pub_" + "a" * 31,
     "pub_" + "a" * 33, "bad_" + "a" * 32, "pub_../unsafe"],
)
def test_invalid_internal_publication_ids_are_integrity_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, generated: object
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: generated)
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.publish_manifest_revision(tmp_path, request)


@pytest.mark.parametrize(
    ("lower_error", "service_error"),
    [
        (PublicationManifestNotFoundError("gone"), services.RegistryServiceIntegrityError),
        (PublicationManifestIntegrityError("changed"), services.RegistryServiceIntegrityError),
        (PublicationManifestError("unreadable"), services.RegistryServiceIntegrityError),
        (PublicationNotFoundError("gone"), services.RegistryServiceIntegrityError),
        (PublicationReadError("bad"), services.RegistryServiceIntegrityError),
        (PublicationIntegrityError("bad"), services.RegistryServiceIntegrityError),
        (PublicationConflictError("busy"), services.RegistryServiceConflictError),
        (PublicationWriteError("write"), services.RegistryServiceWriteError),
        (PublicationStorageError("storage"), services.RegistryServiceWriteError),
        (OSError("filesystem"), services.RegistryServiceWriteError),
    ],
)
def test_publication_writer_exceptions_are_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lower_error: BaseException,
    service_error: type[services.RegistryServiceError],
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    monkeypatch.setattr(services, "write_publication_record", Mock(side_effect=lower_error))
    with pytest.raises(service_error) as caught:
        services.publish_manifest_revision(tmp_path, request)
    assert caught.value.__cause__ is lower_error


def _existing_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[services.PublicationServiceResult, bytes]:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    result = services.publish_manifest_revision(tmp_path, request)
    return result, publication_record_path(tmp_path, PUB1).read_bytes()


@pytest.mark.parametrize(
    ("lower_error", "service_error"),
    [
        (PublicationNotFoundError("gone"), services.RegistryServiceIntegrityError),
        (PublicationReadError("bad"), services.RegistryServiceIntegrityError),
        (PublicationIntegrityError("bad"), services.RegistryServiceIntegrityError),
        (PublicationConflictError("busy"), services.RegistryServiceConflictError),
        (PublicationWriteError("write"), services.RegistryServiceWriteError),
        (PublicationStorageError("storage"), services.RegistryServiceWriteError),
        (OSError("filesystem"), services.RegistryServiceWriteError),
    ],
)
def test_withdrawal_writer_exceptions_are_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lower_error: BaseException,
    service_error: type[services.RegistryServiceError],
) -> None:
    _existing_publication(tmp_path, monkeypatch)
    monkeypatch.setattr(services, "write_publication_withdrawal", Mock(side_effect=lower_error))
    request = services.PublicationWithdrawalRequest(PUB1, "Unavailable")
    with pytest.raises(service_error) as caught:
        services.withdraw_publication(tmp_path, request)
    assert caught.value.__cause__ is lower_error


def test_withdrawal_final_reload_failure_is_partial_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publication, original = _existing_publication(tmp_path, monkeypatch)
    real_load = load_publication_withdrawal
    calls = 0

    def load_once_then_fail(
        root: str | Path, publication_id: str
    ) -> PublicationWithdrawal | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_load(root, publication_id)
        raise PublicationReadError("final reload failed")

    real_writer = write_publication_withdrawal

    def durable_writer(root: str | Path, withdrawal: PublicationWithdrawal) -> Path:
        path = real_writer(root, withdrawal)
        assert path.exists()
        return path

    writer = Mock(side_effect=durable_writer)
    monkeypatch.setattr(services, "write_publication_withdrawal", writer)
    monkeypatch.setattr(
        "pds_core.registry_services.load_publication_withdrawal", load_once_then_fail
    )
    with pytest.raises(services.RegistryServicePartialSuccessError) as caught:
        services.withdraw_publication(
            tmp_path, services.PublicationWithdrawalRequest(PUB1, "Unavailable")
        )
    state = caught.value.state
    assert state.operation == "withdraw_publication"
    assert state.publication == publication.publication
    assert state.withdrawal is not None and state.withdrawal.reason == "Unavailable"
    assert state.canonical_path == publication_withdrawal_path(tmp_path, PUB1)
    assert state.registration is None and state.current_selected is None
    assert isinstance(caught.value.__cause__, services.RegistryServiceIntegrityError)
    assert writer.call_count == 1
    monkeypatch.setattr(
        "pds_core.registry_services.load_publication_withdrawal", real_load
    )
    assert load_publication_withdrawal(tmp_path, PUB1) == state.withdrawal
    assert publication_record_path(tmp_path, PUB1).read_bytes() == original


@pytest.mark.parametrize("operation", ["first", "supersession"])
def test_publication_final_reload_failure_has_exact_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    first_request = manifest_request(tmp_path, work, 1)
    if operation == "supersession":
        monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
        services.publish_manifest_revision(tmp_path, first_request)
        request = manifest_request(tmp_path, work, 2)
        publication_id = PUB2
        predecessor = PUB1
    else:
        request = first_request
        publication_id = PUB1
        predecessor = None
    monkeypatch.setattr(services, "_new_publication_id", lambda: publication_id)
    real_load = load_publication_record

    def fail_only_final(root: str | Path, value: str) -> object:
        if value == publication_id:
            if not publication_record_path(root, value).exists():
                raise PublicationNotFoundError("not allocated")
            raise PublicationReadError("final reload failed")
        return real_load(root, value)

    real_writer = write_publication_record

    def durable_writer(root: str | Path, candidate: PublicationRecord) -> Path:
        path = real_writer(root, candidate)
        assert path.exists()
        return path

    writer = Mock(side_effect=durable_writer)
    monkeypatch.setattr(services, "write_publication_record", writer)
    monkeypatch.setattr("pds_core.registry_services.load_publication_record", fail_only_final)
    with pytest.raises(services.RegistryServicePartialSuccessError) as caught:
        if predecessor is None:
            services.publish_manifest_revision(tmp_path, request)
        else:
            services.supersede_manifest_revision(
                tmp_path, request, expected_current_publication_id=predecessor
            )
    state = caught.value.state
    assert state.operation == (
        "publish_manifest_revision" if predecessor is None else "supersede_manifest_revision"
    )
    assert state.publication is not None and state.publication.publication_id == publication_id
    assert state.canonical_path == publication_record_path(tmp_path, publication_id)
    assert state.registration is None and state.withdrawal is None
    assert state.current_selected is None
    assert isinstance(caught.value.__cause__, PublicationReadError)
    assert writer.call_count == 1
    monkeypatch.setattr(
        "pds_core.registry_services.load_publication_record", real_load
    )
    assert load_publication_record(tmp_path, publication_id) == state.publication


def test_concurrent_different_update_is_conflict_and_orphan_is_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    initial = services.register_academic_work(tmp_path, registration_request(work)).registration
    original_writer = write_academic_work_registration

    def competing_writer(
        root: str | Path,
        candidate: AcademicWorkRegistration,
        *,
        expected_current_revision: int | None,
    ) -> Path:
        other = replace(candidate, title="Competing")
        original_writer(root, other, expected_current_revision=expected_current_revision)
        raise AcademicWorkRegistrationConflictError("lost race")

    monkeypatch.setattr(
        "pds_core.registry_services.write_academic_work_registration", competing_writer
    )
    with pytest.raises(services.RegistryServiceConflictError):
        services.update_academic_work_registration(
            tmp_path, registration_request(work, title="Intended"), expected_current_revision=1
        )
    assert initial.registration_revision == 1

    # Restore revision 1 as authoritative to turn the occupied revision into an orphan.
    pointer = academic_work_registration_current_path(tmp_path, work)
    pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
    pointer_data["registration_revision"] = 1
    pointer.write_text(json.dumps(pointer_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        "pds_core.registry_services.write_academic_work_registration", original_writer
    )
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.update_academic_work_registration(
            tmp_path, registration_request(work, title="Intended"), expected_current_revision=1
        )


def test_malformed_or_wrong_identity_orphans_are_integrity_errors(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    current = services.register_academic_work(tmp_path, registration_request(work)).registration
    path = academic_work_registration_revision_path(tmp_path, work, 2)
    path.write_bytes(b"not json")
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.update_academic_work_registration(
            tmp_path, registration_request(work, title="Next"), expected_current_revision=1
        )
    path.unlink()
    payload = academic_work_registration_to_dict(replace(current, registration_revision=3))
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.update_academic_work_registration(
            tmp_path, registration_request(work, title="Next"), expected_current_revision=1
        )


@pytest.mark.parametrize(
    "intent",
    ["formative", "summative", "diagnostic", "practice", "feedback_only", "reporting_only"],
)
@pytest.mark.parametrize("lifecycle", ["planned", "active", "closed", "cancelled"])
def test_registration_request_accepts_every_intent_and_lifecycle(
    intent: str, lifecycle: str
) -> None:
    request = registration_request(
        ModuleWorkRef("quillan", "class", "work"),
        academic_intent=intent,
        lifecycle=lifecycle,
    )
    assert hash(request)


@pytest.mark.parametrize(
    "changes",
    [
        {"producer_contract_version": "bad value"},
        {"title": ""},
        {"title": " surrounding "},
        {"work_kind": "Upper"},
        {"academic_intent": "unknown"},
        {"lifecycle": "unknown"},
        {"source_records": (ModuleRecordRef("quillan", "kind", "id"),) * 2},
    ],
)
def test_registration_request_rejects_invalid_metadata(changes: dict[str, object]) -> None:
    with pytest.raises(services.RegistryServiceValidationError):
        registration_request(ModuleWorkRef("quillan", "class", "work"), **changes)


@pytest.mark.parametrize(
    ("kind", "capability"),
    [
        ("academic_result_set", "points"),
        ("academic_result_set", "question_evidence"),
        ("academic_result_set", "multiple_attempts"),
        ("academic_result_set", "standards_ratings"),
        ("academic_result_set", "criterion_scores"),
        ("academic_result_set", "moderated_scores"),
        ("intervention_record_set", "intervention_history"),
        ("intervention_record_set", "intervention_status"),
        ("intervention_record_set", "intervention_outcomes"),
    ],
)
def test_publication_request_accepts_every_capability(
    tmp_path: Path, kind: str, capability: str
) -> None:
    request = manifest_request(
        tmp_path, ModuleWorkRef("portia", "class", "work"), 1, kind=kind
    )
    request = replace(request, capabilities=[capability])  # type: ignore[arg-type]
    assert request.capabilities == (capability,)
    assert hash(request)
    assert not hasattr(request, "__dict__")


@pytest.mark.parametrize("revision", [0, -1, 1.5, True])
def test_publication_request_rejects_invalid_revisions(
    tmp_path: Path, revision: object
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    with pytest.raises(services.RegistryServiceValidationError):
        replace(request, record_set_revision=revision)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path",
    ["", "/absolute.json", "C:/absolute.json", "../escape.json", "classes//x.json",
     "classes/class/modules/portia/work/work/../x.json", "classes/class/modules/portia/work/work/x.txt",
     r"classes\class\modules\portia\work\work\x.json"],
)
def test_publication_request_rejects_unsafe_paths(tmp_path: Path, path: str) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    with pytest.raises(services.RegistryServiceValidationError):
        replace(request, manifest_path=path)


def test_withdrawal_and_result_models_are_frozen_slotted_hashable() -> None:
    request = services.PublicationWithdrawalRequest(PUB1, "Évaluation retirée")
    assert hash(request) and not hasattr(request, "__dict__")
    with pytest.raises(FrozenInstanceError):
        request.reason = "Changed"  # type: ignore[misc]
    with pytest.raises(services.RegistryServiceValidationError):
        services.PublicationWithdrawalRequest(PUB1, "line one\nline two")
    state = services.RegistryServicePartialState(
        operation="withdraw_publication", registration=None, publication=None,
        withdrawal=None, canonical_path=Path("x"), current_selected=None, message="partial"
    )
    error = services.RegistryServicePartialSuccessError("partial", state)
    assert error.state == state and hash(state)
    assert not hasattr(state, "__dict__")
    with pytest.raises(FrozenInstanceError):
        state.message = "changed"  # type: ignore[misc]
    for disposition in ("created", "existing", "updated"):
        result = services.AcademicWorkRegistrationServiceResult(
            registration=object(), disposition=disposition  # type: ignore[arg-type]
        )
        assert result.disposition == disposition


def test_registration_clock_and_missing_root_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    request = registration_request(work)
    with pytest.raises(services.RegistryServiceWriteError):
        services.register_academic_work(tmp_path, request)
    module_work_dir(tmp_path, work).mkdir(parents=True)
    clock = Mock(return_value=NOW.astimezone(timezone.utc))
    monkeypatch.setattr(services, "_utc_now", clock)
    created = services.register_academic_work(tmp_path, request)
    assert clock.call_count == 1
    assert created.registration.created_at == created.registration.updated_at == NOW
    clock.reset_mock()
    assert services.register_academic_work(tmp_path, request).disposition == "existing"
    clock.assert_not_called()
    naive_work = ModuleWorkRef("quillan", "class", "naive")
    module_work_dir(tmp_path, naive_work).mkdir(parents=True)
    monkeypatch.setattr(services, "_utc_now", lambda: NOW.replace(tzinfo=None))
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.register_academic_work(tmp_path, registration_request(naive_work))


def test_generated_id_collisions_retry_with_one_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "one"), 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    services.publish_manifest_revision(tmp_path, first)
    second = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "two"), 1)
    generated = iter((PUB1, PUB1, PUB2))
    monkeypatch.setattr(services, "_new_publication_id", lambda: next(generated))
    clock = Mock(return_value=NOW)
    monkeypatch.setattr(services, "_utc_now", clock)
    result = services.publish_manifest_revision(tmp_path, second)
    assert result.publication.publication_id == PUB2
    assert result.publication.published_at == NOW
    assert clock.call_count == 1

    third = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "three"), 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    with pytest.raises(services.RegistryServiceConflictError):
        services.publish_manifest_revision(tmp_path, third)


def test_withdrawal_disappearance_and_inequality_after_writer_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publication, _ = _existing_publication(tmp_path, monkeypatch)
    request = services.PublicationWithdrawalRequest(PUB1, "Unavailable")
    real_writer = write_publication_withdrawal

    def write_then_remove(root: str | Path, withdrawal: PublicationWithdrawal) -> Path:
        path = real_writer(root, withdrawal)
        assert path.exists()
        path.unlink()
        return path

    monkeypatch.setattr(services, "write_publication_withdrawal", write_then_remove)
    with pytest.raises(services.RegistryServicePartialSuccessError):
        services.withdraw_publication(tmp_path, request)

    different = PublicationWithdrawal(
        schema_version="1", record_type="publication_withdrawal", publication_id=PUB1,
        withdrawn_at=publication.publication.published_at, reason="Different"
    )
    def durable_writer(root: str | Path, withdrawal: PublicationWithdrawal) -> Path:
        return real_writer(root, withdrawal)

    monkeypatch.setattr(services, "write_publication_withdrawal", durable_writer)
    calls = iter((None, different))
    monkeypatch.setattr(
        "pds_core.registry_services.load_publication_withdrawal", lambda *_: next(calls)
    )
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.withdraw_publication(tmp_path, request)


def test_identical_and_contradictory_initial_registration_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = write_academic_work_registration
    for work_id, contradictory in (("same", False), ("different", True)):
        work = ModuleWorkRef("quillan", "class", work_id)
        module_work_dir(tmp_path, work).mkdir(parents=True)

        def racing_writer(
            root: str | Path,
            candidate: AcademicWorkRegistration,
            *,
            expected_current_revision: int | None,
            different: bool = contradictory,
        ) -> Path:
            persisted = replace(candidate, title="Competing") if different else candidate
            original(root, persisted, expected_current_revision=expected_current_revision)
            raise AcademicWorkRegistrationConflictError("reported race")

        monkeypatch.setattr(services, "write_academic_work_registration", racing_writer)
        request = registration_request(work)
        if contradictory:
            with pytest.raises(services.RegistryServiceConflictError):
                services.register_academic_work(tmp_path, request)
        else:
            assert services.register_academic_work(tmp_path, request).disposition == "existing"


def test_registration_write_failure_and_both_partial_selection_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    services.register_academic_work(tmp_path, registration_request(work))
    request = registration_request(work, title="Next")

    monkeypatch.setattr(
        services,
        "write_academic_work_registration",
        Mock(side_effect=AcademicWorkRegistrationWriteError("no candidate")),
    )
    with pytest.raises(services.RegistryServiceWriteError):
        services.update_academic_work_registration(
            tmp_path, request, expected_current_revision=1
        )

    def orphan_writer(
        root: str | Path,
        candidate: AcademicWorkRegistration,
        *,
        expected_current_revision: int | None,
    ) -> Path:
        path = academic_work_registration_revision_path(
            root, candidate.work, candidate.registration_revision
        )
        path.write_text(
            json.dumps(academic_work_registration_to_dict(candidate), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        raise AcademicWorkRegistrationWriteError("pointer failed")

    monkeypatch.setattr(services, "write_academic_work_registration", orphan_writer)
    with pytest.raises(services.RegistryServicePartialSuccessError) as caught:
        services.update_academic_work_registration(
            tmp_path, request, expected_current_revision=1
        )
    assert caught.value.state.current_selected is False
    academic_work_registration_revision_path(tmp_path, work, 2).unlink()

    original = write_academic_work_registration

    def selected_writer(
        root: str | Path,
        candidate: AcademicWorkRegistration,
        *,
        expected_current_revision: int | None,
    ) -> Path:
        original(root, candidate, expected_current_revision=expected_current_revision)
        raise AcademicWorkRegistrationIntegrityError("final strict verification failed")

    monkeypatch.setattr(services, "write_academic_work_registration", selected_writer)
    with pytest.raises(services.RegistryServicePartialSuccessError) as caught:
        services.update_academic_work_registration(
            tmp_path, request, expected_current_revision=1
        )
    assert caught.value.state.current_selected is True


def test_identical_and_contradictory_first_publication_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = write_publication_record
    for work_id, contradictory, publication_id in (
        ("same", False, PUB1), ("different", True, PUB2)
    ):
        request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", work_id), 1)
        monkeypatch.setattr(services, "_new_publication_id", lambda value=publication_id: value)

        def racing_writer(
            root: str | Path,
            candidate: PublicationRecord,
            *,
            different: bool = contradictory,
        ) -> Path:
            persisted = (
                replace(candidate, capabilities=("intervention_history",))
                if different
                else candidate
            )
            original(root, persisted)
            raise PublicationConflictError("reported race")

        monkeypatch.setattr(services, "write_publication_record", racing_writer)
        if contradictory:
            with pytest.raises(services.RegistryServiceIntegrityError):
                services.publish_manifest_revision(tmp_path, request)
        else:
            result = services.publish_manifest_revision(tmp_path, request)
            assert result.disposition == "existing" and result.publication.publication_id == PUB1


def test_identical_and_contradictory_withdrawal_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publication, _ = _existing_publication(tmp_path, monkeypatch)
    original = write_publication_withdrawal

    def identical_writer(root: str | Path, withdrawal: PublicationWithdrawal) -> Path:
        original(root, withdrawal)
        raise PublicationConflictError("reported race")

    monkeypatch.setattr(services, "write_publication_withdrawal", identical_writer)
    request = services.PublicationWithdrawalRequest(PUB1, "Unavailable")
    assert services.withdraw_publication(tmp_path, request).disposition == "existing"

    work = ModuleWorkRef("portia", "class", "other")
    other_request = manifest_request(tmp_path, work, 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB2)
    monkeypatch.setattr(services, "write_publication_record", write_publication_record)
    services.publish_manifest_revision(tmp_path, other_request)

    def contradictory_writer(root: str | Path, withdrawal: PublicationWithdrawal) -> Path:
        different = replace(withdrawal, reason="Competing")
        original(root, different)
        raise PublicationConflictError("reported race")

    monkeypatch.setattr(services, "write_publication_withdrawal", contradictory_writer)
    with pytest.raises(services.RegistryServiceConflictError):
        services.withdraw_publication(
            tmp_path, services.PublicationWithdrawalRequest(PUB2, "Unavailable")
        )
    assert publication.publication.publication_id == PUB1


def test_canonical_withdrawal_relationship_is_always_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publication, _ = _existing_publication(tmp_path, monkeypatch)
    path = publication_withdrawal_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True, exist_ok=True)
    invalid_time = publication.publication.published_at.replace(year=2025)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "record_type": "publication_withdrawal",
                "publication_id": PUB1,
                "withdrawn_at": invalid_time.isoformat(),
                "reason": "Invalid relationship",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(services.RegistryServiceIntegrityError) as caught:
        services.get_canonical_publication_withdrawal(tmp_path, PUB1)
    assert isinstance(caught.value.__cause__, PublicationRecordValidationError)


@pytest.mark.parametrize("supersession", [False, True])
def test_publication_disappearance_during_exact_replay_is_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, supersession: bool
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    ids = iter((PUB1, PUB2))
    monkeypatch.setattr(services, "_new_publication_id", lambda: next(ids))
    first_request = manifest_request(tmp_path, work, 1)
    services.publish_manifest_revision(tmp_path, first_request)
    if supersession:
        request = manifest_request(tmp_path, work, 2)
        services.supersede_manifest_revision(
            tmp_path, request, expected_current_publication_id=PUB1
        )
    else:
        request = first_request
    monkeypatch.setattr(
        services,
        "get_canonical_publication_withdrawal",
        Mock(side_effect=services.RegistryServiceNotFoundError("disappeared")),
    )
    with pytest.raises(services.RegistryServiceIntegrityError):
        if supersession:
            services.supersede_manifest_revision(
                tmp_path, request, expected_current_publication_id=PUB1
            )
        else:
            services.publish_manifest_revision(tmp_path, request)


def test_withdrawal_conflict_absent_and_publication_disappearance_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _existing_publication(tmp_path, monkeypatch)
    request = services.PublicationWithdrawalRequest(PUB1, "Unavailable")
    monkeypatch.setattr(
        services,
        "write_publication_withdrawal",
        Mock(side_effect=PublicationConflictError("busy")),
    )
    with pytest.raises(services.RegistryServiceConflictError):
        services.withdraw_publication(tmp_path, request)

    def disappear_then_conflict(*_args: object, **_kwargs: object) -> Path:
        publication_record_path(tmp_path, PUB1).unlink()
        raise PublicationConflictError("busy")

    monkeypatch.setattr(services, "write_publication_withdrawal", disappear_then_conflict)
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.withdraw_publication(tmp_path, request)


def test_optional_withdrawal_operational_failure_after_real_publication_is_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    monkeypatch.setattr(
        services,
        "get_canonical_publication_withdrawal",
        Mock(side_effect=services.RegistryServiceWriteError("operational")),
    )
    with pytest.raises(services.RegistryServicePartialSuccessError) as caught:
        services.publish_manifest_revision(tmp_path, request)
    assert publication_record_path(tmp_path, PUB1).exists()
    assert caught.value.state.publication == load_publication_record(tmp_path, PUB1)
    assert isinstance(caught.value.__cause__, services.RegistryServiceWriteError)


def test_invalid_withdrawal_relationship_after_real_publication_is_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    real_writer = write_publication_record

    def write_with_invalid_withdrawal(
        root: str | Path, publication: PublicationRecord
    ) -> Path:
        path = real_writer(root, publication)
        withdrawal_path = publication_withdrawal_path(root, publication.publication_id)
        withdrawal_path.parent.mkdir(parents=True, exist_ok=True)
        withdrawal_path.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "record_type": "publication_withdrawal",
                    "publication_id": publication.publication_id,
                    "withdrawn_at": publication.published_at.replace(year=2025).isoformat(),
                    "reason": "Invalid relationship",
                }
            ),
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr(services, "write_publication_record", write_with_invalid_withdrawal)
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.publish_manifest_revision(tmp_path, request)
    assert publication_record_path(tmp_path, PUB1).exists()


@pytest.mark.parametrize("reported", ["conflict", "write"])
def test_identical_supersession_completion_reconciles_reported_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reported: str
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    ids = iter((PUB1, PUB2))
    monkeypatch.setattr(services, "_new_publication_id", lambda: next(ids))
    services.publish_manifest_revision(tmp_path, manifest_request(tmp_path, work, 1))
    historical = publication_record_path(tmp_path, PUB1).read_bytes()
    request = manifest_request(tmp_path, work, 3)
    real_writer = write_publication_record

    def racing_writer(root: str | Path, publication: PublicationRecord) -> Path:
        real_writer(root, publication)
        if reported == "conflict":
            raise PublicationConflictError("reported after completion")
        raise PublicationWriteError("reported after completion")

    monkeypatch.setattr(services, "write_publication_record", racing_writer)
    result = services.supersede_manifest_revision(
        tmp_path, request, expected_current_publication_id=PUB1
    )
    assert result.disposition == "existing"
    assert result.publication.publication_id == PUB2
    assert publication_record_path(tmp_path, PUB1).read_bytes() == historical


def test_contradictory_supersession_race_and_withdrawn_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    ids = iter((PUB1, PUB2))
    monkeypatch.setattr(services, "_new_publication_id", lambda: next(ids))
    services.publish_manifest_revision(tmp_path, manifest_request(tmp_path, work, 1))
    services.withdraw_publication(
        tmp_path, services.PublicationWithdrawalRequest(PUB1, "Retired")
    )
    request = manifest_request(tmp_path, work, 2)
    real_writer = write_publication_record

    def contradictory_writer(root: str | Path, publication: PublicationRecord) -> Path:
        real_writer(root, replace(publication, capabilities=("intervention_history",)))
        raise PublicationConflictError("reported race")

    monkeypatch.setattr(services, "write_publication_record", contradictory_writer)
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.supersede_manifest_revision(
            tmp_path, request, expected_current_publication_id=PUB1
        )
    assert len(services._load_series(tmp_path, request)) == 2


def test_service_operations_preserve_unrelated_and_producer_owned_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    representative_paths = [
        tmp_path / "school_years" / "current.json",
        tmp_path / "classes" / "class" / "class.json",
        tmp_path / "academic_periods" / "2026" / "revisions" / "1.json",
        tmp_path / "academic_periods" / "2026" / "current.json",
        tmp_path / "routes" / "route.json",
        tmp_path / "classes" / "class" / "roster.json",
        tmp_path / "scans" / "source" / "scan.pdf",
        tmp_path / "standards" / "library.json",
        tmp_path / "producer-native" / "record.json",
    ]
    for index, path in enumerate(representative_paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"unchanged-{index}".encode())

    unrelated_work = ModuleWorkRef("quillan", "class", "unrelated")
    module_work_dir(tmp_path, unrelated_work).mkdir(parents=True)
    services.register_academic_work(tmp_path, registration_request(unrelated_work))
    unrelated_registration_paths = [
        academic_work_registration_revision_path(tmp_path, unrelated_work, 1),
        academic_work_registration_current_path(tmp_path, unrelated_work),
    ]
    unrelated_publication_request = manifest_request(
        tmp_path, ModuleWorkRef("portia", "class", "unrelated"), 1
    )
    ids = iter((PUB1, PUB2, "pub_33333333333333333333333333333333"))
    monkeypatch.setattr(services, "_new_publication_id", lambda: next(ids))
    unrelated_publication = services.publish_manifest_revision(
        tmp_path, unrelated_publication_request
    )
    services.withdraw_publication(
        tmp_path, services.PublicationWithdrawalRequest(PUB1, "Unrelated withdrawal")
    )
    unrelated_paths = [
        *representative_paths,
        *unrelated_registration_paths,
        publication_record_path(tmp_path, PUB1),
        publication_withdrawal_path(tmp_path, PUB1),
        tmp_path.joinpath(*unrelated_publication_request.manifest_path.split("/")),
    ]
    before = {path: path.read_bytes() for path in unrelated_paths}

    target_work = ModuleWorkRef("portia", "class", "target")
    module_work_dir(tmp_path, target_work).mkdir(parents=True)
    services.register_academic_work(tmp_path, registration_request(target_work))
    first_request = manifest_request(tmp_path, target_work, 1)
    first = services.publish_manifest_revision(tmp_path, first_request)
    second_request = manifest_request(tmp_path, target_work, 2)
    second = services.supersede_manifest_revision(
        tmp_path,
        second_request,
        expected_current_publication_id=first.publication.publication_id,
    )
    services.withdraw_publication(
        tmp_path,
        services.PublicationWithdrawalRequest(
            second.publication.publication_id, "Target withdrawal"
        ),
    )

    assert {path: path.read_bytes() for path in unrelated_paths} == before
    assert unrelated_publication.publication.publication_id == PUB1
    assert not tuple(tmp_path.rglob("*.sqlite"))
    assert not tuple(tmp_path.rglob("*.sqlite3"))


@pytest.mark.parametrize(
    "field",
    ["source_record", "capabilities", "manifest_contract_version", "manifest_path",
     "manifest_bytes", "predecessor"],
)
def test_each_declarative_replay_field_contradiction_is_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    request = manifest_request(tmp_path, work, 1)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    created = services.publish_manifest_revision(tmp_path, request)
    original_id = created.publication.publication_id
    original_time = created.publication.published_at
    if field == "source_record":
        changed = replace(
            request, source_record=ModuleRecordRef("portia", "source", "other")
        )
    elif field == "capabilities":
        changed = replace(request, capabilities=("intervention_history",))
    elif field == "manifest_contract_version":
        changed = replace(request, manifest_contract_version="2")
    elif field == "manifest_path":
        alternate = request.manifest_path.replace("1.json", "alternate.json")
        alternate_path = tmp_path.joinpath(*alternate.split("/"))
        alternate_path.write_bytes(
            tmp_path.joinpath(*request.manifest_path.split("/")).read_bytes()
        )
        changed = replace(request, manifest_path=alternate)
    elif field == "manifest_bytes":
        tmp_path.joinpath(*request.manifest_path.split("/")).write_bytes(b"changed")
        changed = request
    else:
        with pytest.raises(services.RegistryServiceIntegrityError):
            services.supersede_manifest_revision(
                tmp_path, request, expected_current_publication_id=PUB2
            )
        return
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.publish_manifest_revision(tmp_path, changed)
    exact = load_publication_record(tmp_path, PUB1)
    assert exact.publication_id == original_id
    assert exact.published_at == original_time


def test_academic_registration_revision_is_part_of_replay_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "academic")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    services.register_academic_work(tmp_path, registration_request(work))
    request = manifest_request(tmp_path, work, 1, kind="academic_result_set")
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB1)
    services.publish_manifest_revision(tmp_path, request)
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.publish_manifest_revision(
            tmp_path, replace(request, academic_work_registration_revision=2)
        )


def test_withdrawal_preflight_observed_publication_disappearance_is_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _existing_publication(tmp_path, monkeypatch)
    real_get = services.get_canonical_publication_record
    calls = 0

    def disappear_on_second_lookup(root: str | Path, publication_id: str) -> PublicationRecord:
        nonlocal calls
        calls += 1
        if calls == 2:
            publication_record_path(root, publication_id).unlink()
        return real_get(root, publication_id)

    monkeypatch.setattr(
        services, "get_canonical_publication_record", disappear_on_second_lookup
    )
    with pytest.raises(services.RegistryServiceIntegrityError) as caught:
        services.withdraw_publication(
            tmp_path, services.PublicationWithdrawalRequest(PUB1, "Unavailable")
        )
    assert isinstance(caught.value.__cause__, services.RegistryServiceNotFoundError)
    assert calls == 2


@pytest.mark.parametrize("api", ["first", "supersession"])
@pytest.mark.parametrize("operational", [False, True])
def test_publication_series_read_classification_preserves_cause_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    api: str,
    operational: bool,
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    expected: type[services.RegistryServiceError]
    if operational:
        filesystem_error = OSError("filesystem read failed")
        try:
            raise filesystem_error
        except OSError as cause:
            lower_error = PublicationReadError("could not enumerate")
            lower_error.__cause__ = cause
        expected = services.RegistryServiceWriteError
    else:
        lower_error = PublicationReadError("malformed canonical data")
        expected = services.RegistryServiceIntegrityError
    monkeypatch.setattr(
        services, "list_publication_record_set", Mock(side_effect=lower_error)
    )
    with pytest.raises(expected) as caught:
        if api == "first":
            services.publish_manifest_revision(tmp_path, request)
        else:
            services.supersede_manifest_revision(
                tmp_path, request, expected_current_publication_id=PUB1
            )
    assert caught.value.__cause__ is lower_error
    if operational:
        assert lower_error.__cause__ is filesystem_error


@pytest.mark.parametrize("operation", ["initial", "update"])
def test_registration_postwrite_reload_failure_is_real_durable_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    if operation == "update":
        services.register_academic_work(tmp_path, registration_request(work))
        request = registration_request(work, title="Updated")
        expected_revision = 2
    else:
        request = registration_request(work)
        expected_revision = 1
    real_loader = load_current_academic_work_registration
    calls = 0

    def fail_service_final_reload(
        root: str | Path, requested_work: ModuleWorkRef
    ) -> AcademicWorkRegistration | None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AcademicWorkRegistrationReadError("final reload failed")
        return real_loader(root, requested_work)

    real_writer = write_academic_work_registration
    writer = Mock(side_effect=real_writer)
    monkeypatch.setattr(
        "pds_core.registry_services.load_current_academic_work_registration",
        fail_service_final_reload,
    )
    monkeypatch.setattr(services, "write_academic_work_registration", writer)
    with pytest.raises(services.RegistryServicePartialSuccessError) as caught:
        if operation == "update":
            services.update_academic_work_registration(
                tmp_path, request, expected_current_revision=1
            )
        else:
            services.register_academic_work(tmp_path, request)
    state = caught.value.state
    assert state.operation == (
        "update_academic_work_registration" if operation == "update" else "register_academic_work"
    )
    assert state.registration is not None
    assert state.registration.registration_revision == expected_revision
    assert state.canonical_path == academic_work_registration_revision_path(
        tmp_path, work, expected_revision
    )
    assert state.current_selected is None
    assert state.publication is None and state.withdrawal is None
    assert writer.call_count == 1
    monkeypatch.setattr(
        "pds_core.registry_services.load_current_academic_work_registration", real_loader
    )
    assert real_loader(tmp_path, work) == state.registration
    assert list_academic_work_registration_revisions(tmp_path, work) == tuple(
        range(1, expected_revision + 1)
    )


def test_registration_postwrite_valid_current_movement_is_partial_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    services.register_academic_work(tmp_path, registration_request(work))
    real_loader = load_current_academic_work_registration
    real_writer = write_academic_work_registration
    calls = 0

    def move_current_after_write(
        root: str | Path, requested_work: ModuleWorkRef
    ) -> AcademicWorkRegistration | None:
        nonlocal calls
        calls += 1
        current = real_loader(root, requested_work)
        if calls == 2:
            assert current is not None and current.registration_revision == 2
            concurrent = replace(
                current, registration_revision=3, title="Concurrent update"
            )
            real_writer(root, concurrent, expected_current_revision=2)
            return real_loader(root, requested_work)
        return current

    writer = Mock(side_effect=real_writer)
    monkeypatch.setattr(
        "pds_core.registry_services.load_current_academic_work_registration",
        move_current_after_write,
    )
    monkeypatch.setattr(services, "write_academic_work_registration", writer)
    with pytest.raises(services.RegistryServicePartialSuccessError) as caught:
        services.update_academic_work_registration(
            tmp_path, registration_request(work, title="Intended"),
            expected_current_revision=1,
        )
    assert caught.value.state.current_selected is False
    assert caught.value.state.registration is not None
    assert caught.value.state.registration.registration_revision == 2
    assert load_academic_work_registration_revision(tmp_path, work, 2) == caught.value.state.registration
    assert real_loader(tmp_path, work).registration_revision == 3  # type: ignore[union-attr]
    assert writer.call_count == 1


def test_supersession_clock_moving_backward_uses_predecessor_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    ids = iter((PUB1, PUB2))
    monkeypatch.setattr(services, "_new_publication_id", lambda: next(ids))
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    first = services.publish_manifest_revision(tmp_path, manifest_request(tmp_path, work, 1))
    monkeypatch.setattr(services, "_utc_now", lambda: NOW.replace(year=2025))
    successor = services.supersede_manifest_revision(
        tmp_path,
        manifest_request(tmp_path, work, 2),
        expected_current_publication_id=PUB1,
    )
    assert successor.publication.published_at == first.publication.published_at


def test_registration_update_normalizes_non_utc_timestamp_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    offset_time = datetime(2026, 7, 28, 12, tzinfo=timezone(timedelta(hours=-4)))
    request = registration_request(work)
    current = AcademicWorkRegistration(
        schema_version="1",
        record_type="academic_work_registration",
        work=work,
        registration_revision=1,
        producer_contract_version=request.producer_contract_version,
        title=request.title,
        work_kind=request.work_kind,
        academic_intent=request.academic_intent,
        lifecycle=request.lifecycle,
        created_at=offset_time,
        updated_at=offset_time,
        source_records=request.source_records,
    )
    write_academic_work_registration(tmp_path, current, expected_current_revision=None)
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    result = services.update_academic_work_registration(
        tmp_path, registration_request(work, title="Updated"), expected_current_revision=1
    )
    assert result.registration.created_at == offset_time
    assert result.registration.updated_at.utcoffset() == timedelta(0)
    assert result.registration.updated_at == offset_time.astimezone(timezone.utc)


def _strict_offset_publication(
    tmp_path: Path, work: ModuleWorkRef, published_at: datetime
) -> PublicationRecord:
    request = manifest_request(tmp_path, work, 1)
    digest = hashlib.sha256(
        tmp_path.joinpath(*request.manifest_path.split("/")).read_bytes()
    ).hexdigest()
    publication = services._publication_from_request(
        request,
        publication_id=PUB1,
        digest=digest,
        published_at=published_at,
        predecessor=None,
    )
    write_publication_record(tmp_path, publication)
    return publication


def test_withdrawal_normalizes_non_utc_publication_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    offset_time = datetime(2026, 7, 28, 18, tzinfo=timezone(timedelta(hours=1)))
    publication = _strict_offset_publication(tmp_path, work, offset_time)
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    result = services.withdraw_publication(
        tmp_path, services.PublicationWithdrawalRequest(PUB1, "Unavailable")
    )
    assert publication.published_at == offset_time
    assert result.withdrawal.withdrawn_at.utcoffset() == timedelta(0)
    assert result.withdrawal.withdrawn_at == offset_time.astimezone(timezone.utc)


def test_supersession_normalizes_non_utc_predecessor_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = ModuleWorkRef("portia", "class", "work")
    offset_time = datetime(2026, 7, 28, 12, tzinfo=timezone(timedelta(hours=-4)))
    predecessor = _strict_offset_publication(tmp_path, work, offset_time)
    monkeypatch.setattr(services, "_new_publication_id", lambda: PUB2)
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    successor = services.supersede_manifest_revision(
        tmp_path,
        manifest_request(tmp_path, work, 2),
        expected_current_publication_id=PUB1,
    )
    assert predecessor.published_at == offset_time
    assert successor.publication.published_at.utcoffset() == timedelta(0)
    assert successor.publication.published_at == offset_time.astimezone(timezone.utc)


@pytest.mark.parametrize("reader", ["current", "revisions"])
@pytest.mark.parametrize("operational", [False, True])
def test_registration_read_classification_through_public_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reader: str,
    operational: bool,
) -> None:
    work = ModuleWorkRef("quillan", "class", "work")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    lower_error = AcademicWorkRegistrationReadError(
        "filesystem failure" if operational else "malformed canonical state"
    )
    filesystem_error: OSError | None = None
    if operational:
        filesystem_error = OSError("read failed")
        lower_error.__cause__ = filesystem_error
    if reader == "current":
        monkeypatch.setattr(
            services,
            "load_current_academic_work_registration",
            Mock(side_effect=lower_error),
        )
    else:
        monkeypatch.setattr(
            services,
            "load_current_academic_work_registration",
            Mock(return_value=None),
        )
        monkeypatch.setattr(
            services,
            "list_academic_work_registration_revisions",
            Mock(side_effect=lower_error),
        )
    expected = (
        services.RegistryServiceWriteError
        if operational
        else services.RegistryServiceIntegrityError
    )
    with pytest.raises(expected) as caught:
        services.register_academic_work(tmp_path, registration_request(work))
    assert caught.value.__cause__ is lower_error
    if filesystem_error is not None:
        assert lower_error.__cause__ is filesystem_error


def _publication_read_with_oserror() -> tuple[PublicationReadError, OSError]:
    filesystem_error = OSError("generated ID read failed")
    lower_error = PublicationReadError("could not read generated ID")
    lower_error.__cause__ = filesystem_error
    return lower_error, filesystem_error


def test_generated_id_initial_lookup_operational_read_is_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    generator = Mock(return_value=PUB1)
    lower_error, filesystem_error = _publication_read_with_oserror()
    monkeypatch.setattr(services, "_new_publication_id", generator)
    monkeypatch.setattr(
        services, "load_publication_record", Mock(side_effect=lower_error)
    )
    with pytest.raises(services.RegistryServiceWriteError) as caught:
        services.publish_manifest_revision(tmp_path, request)
    assert caught.value.__cause__ is lower_error
    assert lower_error.__cause__ is filesystem_error
    assert generator.call_count == 1


def test_generated_id_malformed_canonical_lookup_is_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    path = publication_record_path(tmp_path, PUB1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not json")
    generator = Mock(return_value=PUB1)
    monkeypatch.setattr(services, "_new_publication_id", generator)
    monkeypatch.setattr(services, "list_publication_record_set", Mock(return_value=()))
    with pytest.raises(services.RegistryServiceIntegrityError):
        services.publish_manifest_revision(tmp_path, request)
    assert generator.call_count == 1


def test_generated_id_postconflict_operational_read_is_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = manifest_request(tmp_path, ModuleWorkRef("portia", "class", "work"), 1)
    generator = Mock(return_value=PUB1)
    lower_error, filesystem_error = _publication_read_with_oserror()
    calls = 0

    def absent_then_operational(
        _root: str | Path, _publication_id: str
    ) -> PublicationRecord:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PublicationNotFoundError("available ID")
        raise lower_error

    monkeypatch.setattr(services, "_new_publication_id", generator)
    monkeypatch.setattr(services, "load_publication_record", absent_then_operational)
    monkeypatch.setattr(
        services,
        "write_publication_record",
        Mock(side_effect=PublicationConflictError("reported conflict")),
    )
    with pytest.raises(services.RegistryServiceWriteError) as caught:
        services.publish_manifest_revision(tmp_path, request)
    assert caught.value.__cause__ is lower_error
    assert lower_error.__cause__ is filesystem_error
    assert calls == 2 and generator.call_count == 1
