"""Stable producer-facing orchestration for the canonical Core registry."""

from __future__ import annotations

import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, NoReturn, TypeAlias, cast

from pds_core.academic_work_registration_storage import (
    AcademicWorkRegistrationConflictError,
    AcademicWorkRegistrationIntegrityError,
    AcademicWorkRegistrationNotFoundError,
    AcademicWorkRegistrationReadError,
    AcademicWorkRegistrationStorageError,
    AcademicWorkRegistrationWriteError,
    list_academic_work_registration_revisions,
    load_academic_work_registration_revision,
    load_current_academic_work_registration,
    write_academic_work_registration,
)
from pds_core.academic_work_registrations import (
    ACADEMIC_WORK_REGISTRATION_RECORD_TYPE,
    ACADEMIC_WORK_REGISTRATION_SCHEMA_VERSION,
    AcademicWorkIntent,
    AcademicWorkRegistration,
    AcademicWorkRegistrationLifecycle,
    AcademicWorkRegistrationValidationError,
)
from pds_core.publication_records import (
    PUBLICATION_RECORD_SCHEMA_VERSION,
    PUBLICATION_RECORD_TYPE,
    PUBLICATION_WITHDRAWAL_RECORD_TYPE,
    PUBLICATION_WITHDRAWAL_SCHEMA_VERSION,
    PublicationCapability,
    PublicationKind,
    PublicationRecord,
    PublicationRecordValidationError,
    PublicationWithdrawal,
    validate_publication_withdrawal_relationship,
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
    calculate_publication_manifest_digest,
    list_publication_record_set,
    load_publication_record,
    load_publication_withdrawal,
    write_publication_record,
    write_publication_withdrawal,
)
from pds_core.registry_paths import (
    academic_work_registration_revision_path,
    publication_record_path,
    publication_withdrawal_path,
)
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef


class RegistryServiceError(Exception):
    """Base error for producer-facing registry services."""


class RegistryServiceValidationError(RegistryServiceError, ValueError):
    """Raised when a service request is invalid."""


class RegistryServiceNotFoundError(RegistryServiceError):
    """Raised when an explicitly requested canonical record does not exist."""


class RegistryServiceConflictError(RegistryServiceError):
    """Raised when caller intent conflicts with canonical current state."""


class RegistryServiceIntegrityError(RegistryServiceError):
    """Raised when canonical or producer-owned state is contradictory."""


class RegistryServiceWriteError(RegistryServiceError):
    """Raised when a canonical operation could not be completed safely."""


class RegistryServicePartialSuccessError(RegistryServiceError):
    """Raised when durable state remains but completion is uncertain."""

    def __init__(self, message: str, state: RegistryServicePartialState) -> None:
        super().__init__(message)
        self.state = state


RegistrationServiceDisposition: TypeAlias = Literal["created", "existing", "updated"]
PublicationServiceDisposition: TypeAlias = Literal["created", "existing"]
PublicationWithdrawalServiceDisposition: TypeAlias = Literal["created", "existing"]
RegistryServiceOperation: TypeAlias = Literal[
    "register_academic_work",
    "update_academic_work_registration",
    "publish_manifest_revision",
    "supersede_manifest_revision",
    "withdraw_publication",
]


@dataclass(frozen=True, slots=True)
class AcademicWorkRegistrationRequest:
    work: ModuleWorkRef
    producer_contract_version: str
    title: str
    work_kind: str
    academic_intent: AcademicWorkIntent
    lifecycle: AcademicWorkRegistrationLifecycle
    source_records: tuple[ModuleRecordRef, ...]

    def __post_init__(self) -> None:
        try:
            probe = AcademicWorkRegistration(
                schema_version=ACADEMIC_WORK_REGISTRATION_SCHEMA_VERSION,
                record_type=ACADEMIC_WORK_REGISTRATION_RECORD_TYPE,
                work=self.work,
                registration_revision=1,
                producer_contract_version=self.producer_contract_version,
                title=self.title,
                work_kind=self.work_kind,
                academic_intent=self.academic_intent,
                lifecycle=self.lifecycle,
                created_at=_VALIDATION_TIME,
                updated_at=_VALIDATION_TIME,
                source_records=self.source_records,
            )
        except (AcademicWorkRegistrationValidationError, TypeError) as error:
            raise RegistryServiceValidationError(str(error)) from error
        object.__setattr__(self, "work", probe.work)
        object.__setattr__(self, "source_records", probe.source_records)


@dataclass(frozen=True, slots=True)
class PublicationManifestRequest:
    work: ModuleWorkRef
    source_record: ModuleRecordRef | None
    publication_kind: PublicationKind
    capabilities: tuple[PublicationCapability, ...]
    record_set_id: str
    record_set_revision: int
    manifest_contract_version: str
    manifest_path: str
    academic_work_registration_revision: int | None
    expected_manifest_digest: str | None = None

    def __post_init__(self) -> None:
        if self.expected_manifest_digest is not None:
            if (
                not isinstance(self.expected_manifest_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", self.expected_manifest_digest) is None
            ):
                raise RegistryServiceValidationError(
                    "expected_manifest_digest must be exactly "
                    "64 lowercase hexadecimal characters."
                )
        try:
            probe = _publication_from_request(
                self,
                publication_id="pub_00000000000000000000000000000000",
                digest="0" * 64,
                published_at=_VALIDATION_TIME,
                predecessor=None,
            )
        except (PublicationRecordValidationError, TypeError) as error:
            raise RegistryServiceValidationError(str(error)) from error
        object.__setattr__(self, "work", probe.work)
        object.__setattr__(self, "capabilities", probe.capabilities)


@dataclass(frozen=True, slots=True)
class PublicationWithdrawalRequest:
    publication_id: str
    reason: str

    def __post_init__(self) -> None:
        try:
            PublicationWithdrawal(
                schema_version=PUBLICATION_WITHDRAWAL_SCHEMA_VERSION,
                record_type=PUBLICATION_WITHDRAWAL_RECORD_TYPE,
                publication_id=self.publication_id,
                withdrawn_at=_VALIDATION_TIME,
                reason=self.reason,
            )
        except PublicationRecordValidationError as error:
            raise RegistryServiceValidationError(str(error)) from error


@dataclass(frozen=True, slots=True)
class AcademicWorkRegistrationServiceResult:
    registration: AcademicWorkRegistration
    disposition: RegistrationServiceDisposition


@dataclass(frozen=True, slots=True)
class PublicationServiceResult:
    publication: PublicationRecord
    withdrawal: PublicationWithdrawal | None
    disposition: PublicationServiceDisposition


@dataclass(frozen=True, slots=True)
class PublicationWithdrawalServiceResult:
    publication: PublicationRecord
    withdrawal: PublicationWithdrawal
    disposition: PublicationWithdrawalServiceDisposition


@dataclass(frozen=True, slots=True)
class RegistryServicePartialState:
    operation: RegistryServiceOperation
    registration: AcademicWorkRegistration | None
    publication: PublicationRecord | None
    withdrawal: PublicationWithdrawal | None
    canonical_path: Path | None
    current_selected: bool | None
    message: str


_VALIDATION_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)
_PUBLICATION_ID_ATTEMPTS = 8


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_publication_id() -> str:
    return f"pub_{uuid.uuid4().hex}"


def register_academic_work(
    workspace_root: str | Path,
    request: AcademicWorkRegistrationRequest,
) -> AcademicWorkRegistrationServiceResult:
    request = _registration_request(request)
    current = _load_current_registration(workspace_root, request.work)
    if current is not None:
        if _registration_metadata(current) == _request_registration_metadata(request):
            return AcademicWorkRegistrationServiceResult(current, "existing")
        raise RegistryServiceConflictError(
            "A different current Academic Work Registration exists; use the update service."
        )
    if _list_registration_revisions(workspace_root, request.work):
        raise RegistryServiceIntegrityError(
            "Orphan Academic Work Registration revisions exist without a current selection."
        )
    timestamp = _service_time()
    candidate = _registration_from_request(request, 1, timestamp, timestamp)
    return _write_registration_candidate(
        workspace_root, request, candidate, None, "register_academic_work", "created"
    )


def update_academic_work_registration(
    workspace_root: str | Path,
    request: AcademicWorkRegistrationRequest,
    *,
    expected_current_revision: int,
) -> AcademicWorkRegistrationServiceResult:
    request = _registration_request(request)
    expected = _positive_int(expected_current_revision, "expected_current_revision")
    current = _load_current_registration(workspace_root, request.work)
    if current is None:
        raise RegistryServiceNotFoundError("Academic Work Registration does not exist.")
    matches = _registration_metadata(current) == _request_registration_metadata(request)
    if current.registration_revision > expected:
        if matches:
            return AcademicWorkRegistrationServiceResult(current, "existing")
        raise RegistryServiceConflictError("The expected registration revision is stale.")
    if current.registration_revision < expected:
        raise RegistryServiceConflictError("The expected registration revision is in the future.")
    if matches:
        return AcademicWorkRegistrationServiceResult(current, "existing")
    revisions = _list_registration_revisions(workspace_root, request.work)
    candidate_revision = current.registration_revision + 1
    if candidate_revision in revisions:
        raise RegistryServiceIntegrityError(
            "The next registration revision already exists as an orphan; repair is required."
        )
    timestamp = max(_service_time(), _utc_floor(current.updated_at))
    candidate = _registration_from_request(
        request, candidate_revision, current.created_at, timestamp
    )
    return _write_registration_candidate(
        workspace_root,
        request,
        candidate,
        current.registration_revision,
        "update_academic_work_registration",
        "updated",
    )


def publish_manifest_revision(
    workspace_root: str | Path,
    request: PublicationManifestRequest,
) -> PublicationServiceResult:
    request = _publication_request(request)
    digest = _manifest_digest(workspace_root, request)
    series = _load_series(workspace_root, request)
    replay = _reconcile_logical_revision(
        workspace_root, series, request, digest, predecessor=None
    )
    if replay is not None:
        return replay
    if series:
        raise RegistryServiceConflictError(
            "The publication series is nonempty; use the supersession service."
        )
    _validate_academic_registration(workspace_root, request)
    return _create_publication(workspace_root, request, digest, None, "publish_manifest_revision")


def supersede_manifest_revision(
    workspace_root: str | Path,
    request: PublicationManifestRequest,
    *,
    expected_current_publication_id: str,
) -> PublicationServiceResult:
    request = _publication_request(request)
    expected = _publication_id(expected_current_publication_id, "expected_current_publication_id")
    digest = _manifest_digest(workspace_root, request)
    series = _load_series(workspace_root, request)
    replay = _reconcile_logical_revision(
        workspace_root, series, request, digest, predecessor=expected
    )
    if replay is not None:
        return replay
    if not series:
        raise RegistryServiceNotFoundError(
            "Publication series does not exist; use the first-publication service."
        )
    head = _series_head(series)
    if head.publication_id != expected:
        raise RegistryServiceConflictError("The expected predecessor is not the current head.")
    if request.record_set_revision <= head.record_set_revision:
        raise RegistryServiceConflictError(
            "A superseding record-set revision must be greater than the current revision."
        )
    _validate_academic_registration(workspace_root, request)
    return _create_publication(
        workspace_root,
        request,
        digest,
        expected,
        "supersede_manifest_revision",
        minimum_published_at=head.published_at,
    )


def withdraw_publication(
    workspace_root: str | Path,
    request: PublicationWithdrawalRequest,
) -> PublicationWithdrawalServiceResult:
    request = _withdrawal_request(request)
    publication = get_canonical_publication_record(workspace_root, request.publication_id)
    try:
        existing = get_canonical_publication_withdrawal(
            workspace_root, request.publication_id
        )
    except RegistryServiceNotFoundError as error:
        raise RegistryServiceIntegrityError(
            "The canonical Publication Record disappeared during withdrawal preparation."
        ) from error
    if existing is not None:
        if existing.reason == request.reason:
            return PublicationWithdrawalServiceResult(publication, existing, "existing")
        raise RegistryServiceConflictError("Publication is already withdrawn for a different reason.")
    timestamp = max(_service_time(), _utc_floor(publication.published_at))
    withdrawal = PublicationWithdrawal(
        schema_version=PUBLICATION_WITHDRAWAL_SCHEMA_VERSION,
        record_type=PUBLICATION_WITHDRAWAL_RECORD_TYPE,
        publication_id=request.publication_id,
        withdrawn_at=timestamp,
        reason=request.reason,
    )
    try:
        write_publication_withdrawal(workspace_root, withdrawal)
    except PublicationConflictError as error:
        reconciled = _reconcile_withdrawal(workspace_root, publication, request, error)
        if reconciled is not None:
            return reconciled
        raise RegistryServiceConflictError(str(error)) from error
    except PublicationIntegrityError as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except (PublicationNotFoundError, PublicationReadError) as error:
        reconciled = _reconcile_withdrawal(workspace_root, publication, request, error)
        if reconciled is not None:
            return reconciled
        raise RegistryServiceIntegrityError(
            "Canonical publication state became invalid during withdrawal."
        ) from error
    except (PublicationWriteError, PublicationStorageError, OSError) as error:
        reconciled = _reconcile_withdrawal(workspace_root, publication, request, error)
        if reconciled is not None:
            return reconciled
        raise RegistryServiceWriteError("Could not create Publication Withdrawal.") from error
    try:
        persisted = get_canonical_publication_withdrawal(workspace_root, request.publication_id)
    except RegistryServiceError as error:
        _raise_withdrawal_partial(workspace_root, publication, withdrawal, error)
    if persisted is None:
        disappearance_error = RegistryServiceIntegrityError(
            "Created Publication Withdrawal disappeared during final verification."
        )
        _raise_withdrawal_partial(
            workspace_root, publication, withdrawal, disappearance_error
        )
    if persisted != withdrawal:
        raise RegistryServiceIntegrityError("Persisted Publication Withdrawal differs from candidate.")
    return PublicationWithdrawalServiceResult(publication, persisted, "created")


def get_canonical_publication_record(
    workspace_root: str | Path, publication_id: str
) -> PublicationRecord:
    identifier = _publication_id(publication_id, "publication_id")
    try:
        return load_publication_record(workspace_root, identifier)
    except PublicationNotFoundError as error:
        raise RegistryServiceNotFoundError(f"Publication Record not found: {identifier}") from error
    except PublicationReadError as error:
        if _has_oserror_cause(error):
            raise RegistryServiceWriteError(
                "Could not retrieve Publication Record."
            ) from error
        raise RegistryServiceIntegrityError(str(error)) from error
    except PublicationIntegrityError as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except (PublicationStorageError, OSError) as error:
        raise RegistryServiceWriteError("Could not retrieve Publication Record.") from error


def get_canonical_publication_withdrawal(
    workspace_root: str | Path, publication_id: str
) -> PublicationWithdrawal | None:
    identifier = _publication_id(publication_id, "publication_id")
    publication = get_canonical_publication_record(workspace_root, identifier)
    try:
        withdrawal = load_publication_withdrawal(workspace_root, identifier)
    except PublicationReadError as error:
        if _has_oserror_cause(error):
            raise RegistryServiceWriteError(
                "Could not retrieve Publication Withdrawal."
            ) from error
        raise RegistryServiceIntegrityError(str(error)) from error
    except PublicationIntegrityError as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except (PublicationStorageError, OSError) as error:
        raise RegistryServiceWriteError("Could not retrieve Publication Withdrawal.") from error
    if withdrawal is None:
        return None
    try:
        return validate_publication_withdrawal_relationship(publication, withdrawal)
    except PublicationRecordValidationError as error:
        raise RegistryServiceIntegrityError(
            "Canonical Publication Withdrawal relationship is invalid."
        ) from error


def _registration_request(value: object) -> AcademicWorkRegistrationRequest:
    if not isinstance(value, AcademicWorkRegistrationRequest):
        raise RegistryServiceValidationError(
            "request must be an AcademicWorkRegistrationRequest."
        )
    return value


def _publication_request(value: object) -> PublicationManifestRequest:
    if not isinstance(value, PublicationManifestRequest):
        raise RegistryServiceValidationError("request must be a PublicationManifestRequest.")
    return value


def _withdrawal_request(value: object) -> PublicationWithdrawalRequest:
    if not isinstance(value, PublicationWithdrawalRequest):
        raise RegistryServiceValidationError("request must be a PublicationWithdrawalRequest.")
    return value


def _service_time() -> datetime:
    value = _utc_now()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RegistryServiceIntegrityError("The service clock must return an aware datetime.")
    return value.astimezone(timezone.utc)


def _utc_floor(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RegistryServiceIntegrityError(
            "Canonical timestamp floor must be timezone-aware."
        )
    return value.astimezone(timezone.utc)


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RegistryServiceValidationError(f"{name} must be a positive integer.")
    return value


def _has_oserror_cause(error: BaseException) -> bool:
    cause = error.__cause__
    while cause is not None:
        if isinstance(cause, OSError):
            return True
        cause = cause.__cause__
    return False


def _publication_id(value: object, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"pub_[0-9a-f]{32}", value) is None:
        raise RegistryServiceValidationError(
            f"{name} must use the format pub_<32 lowercase hexadecimal characters>."
        )
    return value


def _registration_from_request(
    request: AcademicWorkRegistrationRequest,
    revision: int,
    created_at: datetime,
    updated_at: datetime,
) -> AcademicWorkRegistration:
    return AcademicWorkRegistration(
        schema_version=ACADEMIC_WORK_REGISTRATION_SCHEMA_VERSION,
        record_type=ACADEMIC_WORK_REGISTRATION_RECORD_TYPE,
        work=request.work,
        registration_revision=revision,
        producer_contract_version=request.producer_contract_version,
        title=request.title,
        work_kind=request.work_kind,
        academic_intent=request.academic_intent,
        lifecycle=request.lifecycle,
        created_at=created_at,
        updated_at=updated_at,
        source_records=request.source_records,
    )


def _registration_metadata(registration: AcademicWorkRegistration) -> tuple[object, ...]:
    return (
        registration.work,
        registration.producer_contract_version,
        registration.title,
        registration.work_kind,
        registration.academic_intent,
        registration.lifecycle,
        registration.source_records,
    )


def _request_registration_metadata(request: AcademicWorkRegistrationRequest) -> tuple[object, ...]:
    return (
        request.work,
        request.producer_contract_version,
        request.title,
        request.work_kind,
        request.academic_intent,
        request.lifecycle,
        request.source_records,
    )


def _load_current_registration(
    workspace_root: str | Path, work: ModuleWorkRef
) -> AcademicWorkRegistration | None:
    try:
        return load_current_academic_work_registration(workspace_root, work)
    except AcademicWorkRegistrationReadError as error:
        if _has_oserror_cause(error):
            raise RegistryServiceWriteError(
                "Could not load Academic Work Registration."
            ) from error
        raise RegistryServiceIntegrityError(str(error)) from error
    except AcademicWorkRegistrationIntegrityError as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except (AcademicWorkRegistrationStorageError, OSError) as error:
        raise RegistryServiceWriteError("Could not load Academic Work Registration.") from error


def _list_registration_revisions(
    workspace_root: str | Path, work: ModuleWorkRef
) -> tuple[int, ...]:
    try:
        return list_academic_work_registration_revisions(workspace_root, work)
    except AcademicWorkRegistrationReadError as error:
        if _has_oserror_cause(error):
            raise RegistryServiceWriteError(
                "Could not inspect registration revisions."
            ) from error
        raise RegistryServiceIntegrityError(str(error)) from error
    except AcademicWorkRegistrationIntegrityError as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except (AcademicWorkRegistrationStorageError, OSError) as error:
        raise RegistryServiceWriteError("Could not inspect registration revisions.") from error


def _write_registration_candidate(
    workspace_root: str | Path,
    request: AcademicWorkRegistrationRequest,
    candidate: AcademicWorkRegistration,
    expected: int | None,
    operation: RegistryServiceOperation,
    disposition: Literal["created", "updated"],
) -> AcademicWorkRegistrationServiceResult:
    try:
        write_academic_work_registration(
            workspace_root, candidate, expected_current_revision=expected
        )
    except AcademicWorkRegistrationConflictError as error:
        current = _load_current_registration(workspace_root, request.work)
        if current is not None and _registration_metadata(current) == _request_registration_metadata(request):
            return AcademicWorkRegistrationServiceResult(current, "existing")
        _raise_registration_write_state(workspace_root, candidate, operation, error)
        raise RegistryServiceConflictError(str(error)) from error
    except AcademicWorkRegistrationIntegrityError as error:
        _raise_registration_write_state(workspace_root, candidate, operation, error)
        raise RegistryServiceIntegrityError(str(error)) from error
    except (AcademicWorkRegistrationWriteError, OSError) as error:
        _raise_registration_write_state(workspace_root, candidate, operation, error)
        raise RegistryServiceWriteError("Could not write Academic Work Registration.") from error
    try:
        selected = _load_current_registration(workspace_root, request.work)
    except RegistryServiceError as error:
        _raise_registration_postwrite_partial(
            workspace_root,
            candidate,
            operation,
            current_selected=None,
            cause=error,
        )
    if selected != candidate:
        movement_error = RegistryServiceConflictError(
            "Canonical current registration moved after the strict writer completed."
        )
        _raise_registration_postwrite_partial(
            workspace_root,
            candidate,
            operation,
            current_selected=False,
            cause=movement_error,
        )
    return AcademicWorkRegistrationServiceResult(selected, disposition)


def _raise_registration_postwrite_partial(
    workspace_root: str | Path,
    candidate: AcademicWorkRegistration,
    operation: RegistryServiceOperation,
    *,
    current_selected: bool | None,
    cause: BaseException,
) -> NoReturn:
    message = (
        "Academic Work Registration was written, but final service verification "
        "did not confirm it as current."
    )
    state = RegistryServicePartialState(
        operation=operation,
        registration=candidate,
        publication=None,
        withdrawal=None,
        canonical_path=academic_work_registration_revision_path(
            workspace_root, candidate.work, candidate.registration_revision
        ),
        current_selected=current_selected,
        message=message,
    )
    raise RegistryServicePartialSuccessError(message, state) from cause


def _raise_registration_write_state(
    workspace_root: str | Path,
    candidate: AcademicWorkRegistration,
    operation: RegistryServiceOperation,
    cause: BaseException,
) -> None:
    path = academic_work_registration_revision_path(
        workspace_root, candidate.work, candidate.registration_revision
    )
    try:
        persisted = load_academic_work_registration_revision(
            workspace_root, candidate.work, candidate.registration_revision
        )
    except AcademicWorkRegistrationNotFoundError:
        return
    except AcademicWorkRegistrationStorageError as error:
        raise RegistryServiceIntegrityError(
            "The candidate registration revision exists but cannot be validated."
        ) from error
    if persisted != candidate:
        try:
            current = load_current_academic_work_registration(workspace_root, candidate.work)
        except AcademicWorkRegistrationStorageError as error:
            raise RegistryServiceIntegrityError(
                "The candidate registration revision number is occupied by contradictory "
                "state and current selection cannot be validated."
            ) from error
        if current == persisted:
            raise RegistryServiceConflictError(
                "Another valid concurrent registration update selected the intended revision."
            ) from cause
        raise RegistryServiceIntegrityError(
            "The candidate registration revision number is occupied by contradictory orphan state."
        ) from cause
    try:
        current = load_current_academic_work_registration(workspace_root, candidate.work)
        selected = current == candidate
    except AcademicWorkRegistrationStorageError:
        selected = None
    message = (
        "Registration revision became canonical but is not current."
        if selected is False
        else "Registration revision became canonical but final selection is uncertain."
    )
    state = RegistryServicePartialState(
        operation=operation,
        registration=persisted,
        publication=None,
        withdrawal=None,
        canonical_path=path,
        current_selected=selected,
        message=message,
    )
    raise RegistryServicePartialSuccessError(message, state) from cause


def _publication_from_request(
    request: PublicationManifestRequest,
    *,
    publication_id: str,
    digest: str,
    published_at: datetime,
    predecessor: str | None,
) -> PublicationRecord:
    return PublicationRecord(
        schema_version=PUBLICATION_RECORD_SCHEMA_VERSION,
        record_type=PUBLICATION_RECORD_TYPE,
        publication_id=publication_id,
        work=request.work,
        source_record=request.source_record,
        publication_kind=request.publication_kind,
        capabilities=request.capabilities,
        record_set_id=request.record_set_id,
        record_set_revision=request.record_set_revision,
        manifest_contract_version=request.manifest_contract_version,
        manifest_path=request.manifest_path,
        manifest_digest_algorithm="sha256",
        manifest_digest=digest,
        published_at=published_at,
        academic_work_registration_revision=request.academic_work_registration_revision,
        supersedes_publication_id=predecessor,
    )


def _manifest_digest(
    workspace_root: str | Path, request: PublicationManifestRequest
) -> str:
    probe = _publication_from_request(
        request,
        publication_id="pub_00000000000000000000000000000000",
        digest="0" * 64,
        published_at=_VALIDATION_TIME,
        predecessor=None,
    )
    try:
        actual = calculate_publication_manifest_digest(workspace_root, probe)
    except PublicationManifestNotFoundError as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except (PublicationManifestIntegrityError, PublicationManifestError) as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except OSError as error:
        raise RegistryServiceIntegrityError("Could not read publication manifest.") from error
    expected = request.expected_manifest_digest
    if expected is not None and not hmac.compare_digest(actual, expected):
        raise RegistryServiceIntegrityError("Publication manifest digest does not match expected digest.")
    return actual


def _load_series(
    workspace_root: str | Path, request: PublicationManifestRequest
) -> tuple[PublicationRecord, ...]:
    try:
        return list_publication_record_set(
            workspace_root, request.work, request.publication_kind, request.record_set_id
        )
    except PublicationReadError as error:
        if _has_oserror_cause(error):
            raise RegistryServiceWriteError(
                "Could not load canonical publication series."
            ) from error
        raise RegistryServiceIntegrityError(str(error)) from error
    except PublicationIntegrityError as error:
        raise RegistryServiceIntegrityError(str(error)) from error
    except (PublicationStorageError, OSError) as error:
        raise RegistryServiceWriteError("Could not load canonical publication series.") from error


def _logical_key(record: PublicationRecord) -> tuple[object, ...]:
    return (
        record.work,
        record.publication_kind,
        record.record_set_id,
        record.record_set_revision,
    )


def _request_logical_key(request: PublicationManifestRequest) -> tuple[object, ...]:
    return (
        request.work,
        request.publication_kind,
        request.record_set_id,
        request.record_set_revision,
    )


def _replay_metadata(record: PublicationRecord) -> tuple[object, ...]:
    return (
        record.work,
        record.source_record,
        record.publication_kind,
        record.capabilities,
        record.record_set_id,
        record.record_set_revision,
        record.manifest_contract_version,
        record.manifest_path,
        record.manifest_digest_algorithm,
        record.manifest_digest,
        record.academic_work_registration_revision,
        record.supersedes_publication_id,
    )


def _request_replay_metadata(
    request: PublicationManifestRequest, digest: str, predecessor: str | None
) -> tuple[object, ...]:
    return (
        request.work,
        request.source_record,
        request.publication_kind,
        request.capabilities,
        request.record_set_id,
        request.record_set_revision,
        request.manifest_contract_version,
        request.manifest_path,
        "sha256",
        digest,
        request.academic_work_registration_revision,
        predecessor,
    )


def _reconcile_logical_revision(
    workspace_root: str | Path,
    series: tuple[PublicationRecord, ...],
    request: PublicationManifestRequest,
    digest: str,
    predecessor: str | None,
) -> PublicationServiceResult | None:
    matches = [item for item in series if _logical_key(item) == _request_logical_key(request)]
    if not matches:
        return None
    if len(matches) != 1:
        raise RegistryServiceIntegrityError("Canonical logical publication revision is duplicated.")
    record = matches[0]
    if _replay_metadata(record) != _request_replay_metadata(request, digest, predecessor):
        raise RegistryServiceIntegrityError(
            "The logical record-set revision has contradictory publication metadata."
        )
    try:
        withdrawal = get_canonical_publication_withdrawal(
            workspace_root, record.publication_id
        )
    except RegistryServiceNotFoundError as error:
        raise RegistryServiceIntegrityError(
            "A Publication Record disappeared during replay reconciliation."
        ) from error
    return PublicationServiceResult(record, withdrawal, "existing")


def _series_head(series: tuple[PublicationRecord, ...]) -> PublicationRecord:
    superseded = {
        item.supersedes_publication_id
        for item in series
        if item.supersedes_publication_id is not None
    }
    heads = [item for item in series if item.publication_id not in superseded]
    if len(heads) != 1:
        raise RegistryServiceIntegrityError("Canonical publication series has competing heads.")
    return heads[0]


def _validate_academic_registration(
    workspace_root: str | Path, request: PublicationManifestRequest
) -> None:
    if request.publication_kind != "academic_result_set":
        return
    current = _load_current_registration(workspace_root, request.work)
    if current is None:
        raise RegistryServiceConflictError("No current Academic Work Registration exists.")
    revision = cast(int, request.academic_work_registration_revision)
    if current.registration_revision != revision:
        raise RegistryServiceConflictError(
            "The publication must reference the exact current registration revision."
        )
    if current.lifecycle == "cancelled":
        raise RegistryServiceConflictError("A cancelled Academic Work Registration cannot be published.")


def _create_publication(
    workspace_root: str | Path,
    request: PublicationManifestRequest,
    digest: str,
    predecessor: str | None,
    operation: RegistryServiceOperation,
    *,
    minimum_published_at: datetime | None = None,
) -> PublicationServiceResult:
    timestamp = _service_time()
    if minimum_published_at is not None:
        timestamp = max(timestamp, _utc_floor(minimum_published_at))
    last_collision: BaseException | None = None
    for _ in range(_PUBLICATION_ID_ATTEMPTS):
        publication_id = _generated_publication_id()
        try:
            load_publication_record(workspace_root, publication_id)
        except PublicationNotFoundError:
            pass
        except PublicationReadError as error:
            if _has_oserror_cause(error):
                raise RegistryServiceWriteError(
                    "Could not inspect a generated publication ID."
                ) from error
            raise RegistryServiceIntegrityError(str(error)) from error
        except PublicationIntegrityError as error:
            raise RegistryServiceIntegrityError(str(error)) from error
        except (PublicationStorageError, OSError) as error:
            raise RegistryServiceWriteError(
                "Could not validate a generated publication ID against canonical storage."
            ) from error
        else:
            last_collision = PublicationConflictError(
                f"Generated Publication Record ID already exists: {publication_id}"
            )
            continue
        candidate = _publication_from_request(
            request,
            publication_id=publication_id,
            digest=digest,
            published_at=timestamp,
            predecessor=predecessor,
        )
        try:
            write_publication_record(workspace_root, candidate)
        except PublicationConflictError as error:
            reconciled = _reconcile_after_publication_error(
                workspace_root, request, digest, predecessor, error
            )
            if reconciled is not None:
                return reconciled
            try:
                load_publication_record(workspace_root, publication_id)
            except PublicationNotFoundError:
                raise RegistryServiceConflictError(str(error)) from error
            except PublicationReadError as load_error:
                if _has_oserror_cause(load_error):
                    raise RegistryServiceWriteError(
                        "Could not inspect the generated publication ID after conflict."
                    ) from load_error
                raise RegistryServiceIntegrityError(str(load_error)) from load_error
            except PublicationIntegrityError as load_error:
                raise RegistryServiceIntegrityError(str(load_error)) from load_error
            except (PublicationStorageError, OSError) as load_error:
                raise RegistryServiceWriteError(
                    "Could not inspect the generated publication ID after conflict."
                ) from load_error
            last_collision = error
            continue
        except PublicationIntegrityError as error:
            reconciled = _reconcile_after_publication_error(
                workspace_root, request, digest, predecessor, error
            )
            if reconciled is not None:
                return reconciled
            raise RegistryServiceIntegrityError(str(error)) from error
        except PublicationManifestError as error:
            try:
                reconciled = _reconcile_after_publication_error(
                    workspace_root, request, digest, predecessor, error
                )
            except RegistryServiceError as reconciliation_error:
                raise RegistryServiceIntegrityError(str(reconciliation_error)) from error
            if reconciled is not None:
                return reconciled
            raise RegistryServiceIntegrityError(str(error)) from error
        except (PublicationNotFoundError, PublicationReadError) as error:
            try:
                reconciled = _reconcile_after_publication_error(
                    workspace_root, request, digest, predecessor, error
                )
            except RegistryServiceError as reconciliation_error:
                raise RegistryServiceIntegrityError(str(reconciliation_error)) from error
            if reconciled is not None:
                return reconciled
            raise RegistryServiceIntegrityError(str(error)) from error
        except (PublicationWriteError, OSError) as error:
            reconciled = _reconcile_after_publication_error(
                workspace_root, request, digest, predecessor, error
            )
            if reconciled is not None:
                return reconciled
            raise RegistryServiceWriteError("Could not create Publication Record.") from error
        except PublicationStorageError as error:
            try:
                reconciled = _reconcile_after_publication_error(
                    workspace_root, request, digest, predecessor, error
                )
            except RegistryServiceError as reconciliation_error:
                raise RegistryServiceIntegrityError(str(reconciliation_error)) from error
            if reconciled is not None:
                return reconciled
            raise RegistryServiceWriteError("Could not create Publication Record.") from error
        try:
            persisted = load_publication_record(workspace_root, publication_id)
        except (PublicationStorageError, OSError) as error:
            state = RegistryServicePartialState(
                operation=operation,
                registration=None,
                publication=candidate,
                withdrawal=None,
                canonical_path=publication_record_path(workspace_root, publication_id),
                current_selected=None,
                message="Publication Record was written but final verification failed.",
            )
            raise RegistryServicePartialSuccessError(state.message, state) from error
        if persisted != candidate:
            raise RegistryServiceIntegrityError("Persisted Publication Record differs from candidate.")
        try:
            withdrawal = get_canonical_publication_withdrawal(
                workspace_root, publication_id
            )
        except RegistryServiceWriteError as error:
            _raise_publication_partial(workspace_root, candidate, operation, error)
        except RegistryServiceNotFoundError as error:
            raise RegistryServiceIntegrityError(
                "The newly canonical Publication Record disappeared during withdrawal lookup."
            ) from error
        return PublicationServiceResult(persisted, withdrawal, "created")
    raise RegistryServiceConflictError(
        f"Could not allocate a unique publication ID after {_PUBLICATION_ID_ATTEMPTS} attempts."
    ) from last_collision


def _generated_publication_id() -> str:
    value = _new_publication_id()
    if not isinstance(value, str) or re.fullmatch(r"pub_[0-9a-f]{32}", value) is None:
        raise RegistryServiceIntegrityError(
            "The internal publication ID generator returned an invalid identifier."
        )
    return value


def _reconcile_after_publication_error(
    workspace_root: str | Path,
    request: PublicationManifestRequest,
    digest: str,
    predecessor: str | None,
    cause: BaseException,
) -> PublicationServiceResult | None:
    reconciled_digest = _manifest_digest(workspace_root, request)
    if not hmac.compare_digest(reconciled_digest, digest):
        raise RegistryServiceIntegrityError(
            "Publication manifest changed while the operation was being reconciled."
        ) from cause
    series = _load_series(workspace_root, request)
    try:
        return _reconcile_logical_revision(
            workspace_root, series, request, digest, predecessor
        )
    except RegistryServiceIntegrityError as error:
        raise error from cause


def _reconcile_withdrawal(
    workspace_root: str | Path,
    publication: PublicationRecord,
    request: PublicationWithdrawalRequest,
    cause: BaseException,
) -> PublicationWithdrawalServiceResult | None:
    try:
        canonical_publication = get_canonical_publication_record(
            workspace_root, request.publication_id
        )
    except RegistryServiceNotFoundError as error:
        raise RegistryServiceIntegrityError(
            "The canonical Publication Record disappeared during withdrawal reconciliation."
        ) from error
    if canonical_publication != publication:
        raise RegistryServiceIntegrityError(
            "The canonical Publication Record changed during withdrawal reconciliation."
        ) from cause
    try:
        existing = get_canonical_publication_withdrawal(
            workspace_root, request.publication_id
        )
    except RegistryServiceNotFoundError as error:
        raise RegistryServiceIntegrityError(
            "The canonical Publication Record disappeared during withdrawal reconciliation."
        ) from error
    if existing is None:
        return None
    if existing.reason != request.reason:
        raise RegistryServiceConflictError(
            "Publication is already withdrawn for a different reason."
        ) from cause
    return PublicationWithdrawalServiceResult(publication, existing, "existing")


def _raise_publication_partial(
    workspace_root: str | Path,
    publication: PublicationRecord,
    operation: RegistryServiceOperation,
    cause: BaseException,
) -> None:
    message = (
        "Publication Record became canonical but optional withdrawal retrieval failed."
    )
    state = RegistryServicePartialState(
        operation=operation,
        registration=None,
        publication=publication,
        withdrawal=None,
        canonical_path=publication_record_path(
            workspace_root, publication.publication_id
        ),
        current_selected=None,
        message=message,
    )
    raise RegistryServicePartialSuccessError(message, state) from cause


def _raise_withdrawal_partial(
    workspace_root: str | Path,
    publication: PublicationRecord,
    withdrawal: PublicationWithdrawal,
    cause: BaseException,
) -> None:
    message = "Withdrawal writer completed but final service verification failed."
    state = RegistryServicePartialState(
        operation="withdraw_publication",
        registration=None,
        publication=publication,
        withdrawal=withdrawal,
        canonical_path=publication_withdrawal_path(workspace_root, publication.publication_id),
        current_selected=None,
        message=message,
    )
    raise RegistryServicePartialSuccessError(message, state) from cause


__all__ = [
    "AcademicWorkRegistrationRequest",
    "AcademicWorkRegistrationServiceResult",
    "PublicationManifestRequest",
    "PublicationServiceResult",
    "PublicationWithdrawalRequest",
    "PublicationWithdrawalServiceResult",
    "RegistrationServiceDisposition",
    "PublicationServiceDisposition",
    "PublicationWithdrawalServiceDisposition",
    "RegistryServiceOperation",
    "RegistryServicePartialState",
    "RegistryServiceError",
    "RegistryServiceValidationError",
    "RegistryServiceNotFoundError",
    "RegistryServiceConflictError",
    "RegistryServiceIntegrityError",
    "RegistryServiceWriteError",
    "RegistryServicePartialSuccessError",
    "register_academic_work",
    "update_academic_work_registration",
    "publish_manifest_revision",
    "supersede_manifest_revision",
    "withdraw_publication",
    "get_canonical_publication_record",
    "get_canonical_publication_withdrawal",
]
