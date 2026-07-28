"""Strict canonical persistence for immutable Publication Records."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Final, NoReturn, cast

from pds_core.academic_work_registration_storage import (
    AcademicWorkRegistrationStorageError,
    load_academic_work_registration_revision,
    load_current_academic_work_registration,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.publication_records import (
    PublicationKind,
    PublicationRecord,
    PublicationRecordValidationError,
    PublicationWithdrawal,
    is_publication_kind,
    publication_record_from_dict,
    publication_record_to_dict,
    publication_withdrawal_from_dict,
    publication_withdrawal_to_dict,
    validate_publication_manifest_path,
    validate_publication_record,
    validate_publication_record_series,
    validate_publication_supersession,
    validate_publication_withdrawal,
    validate_publication_withdrawal_relationship,
)
from pds_core.registry_paths import (
    publication_record_path,
    publication_withdrawal_path,
    publication_withdrawals_dir,
    publications_dir,
    registry_dir,
)
from pds_core.routes import module_work_dir
from pds_core.routing_models import ModuleWorkRef, RoutingModelError, validate_module_work_ref
from pds_core.workspace import WorkspaceRootError, _normalize_workspace_root

_PUBLICATION_FILE: Final[re.Pattern[str]] = re.compile(
    r"^(pub_[0-9a-f]{32})\.json$"
)
_DIGEST_CHUNK_SIZE: Final[int] = 1024 * 1024


class PublicationManifestError(RuntimeError):
    """Base error for manifest path and digest failures."""


class PublicationManifestNotFoundError(PublicationManifestError):
    """Raised when the bound manifest is absent or not a regular file."""


class PublicationManifestIntegrityError(PublicationManifestError):
    """Raised when manifest containment or digest validation fails."""


class PublicationStorageError(RuntimeError):
    """Base error for canonical publication storage."""


class PublicationReadError(PublicationStorageError):
    """Raised when canonical publication storage cannot be read."""


class PublicationWriteError(PublicationStorageError):
    """Raised when publication storage cannot be written safely."""


class PublicationNotFoundError(PublicationReadError):
    """Raised when one explicitly requested Publication Record is absent."""


class PublicationConflictError(PublicationWriteError):
    """Raised for collisions, concurrent writes, or stale series state."""


class PublicationIntegrityError(PublicationStorageError):
    """Raised when canonical publication records disagree or are corrupted."""


class _DuplicateJsonKeyError(ValueError):
    pass


class _InvalidJsonConstantError(ValueError):
    pass


def resolve_publication_manifest_path(
    workspace_root: str | Path, publication: PublicationRecord
) -> Path:
    """Resolve a publication's exact manifest while enforcing containment."""
    record = _publication(publication)
    validate_publication_manifest_path(record.work, record.manifest_path)
    try:
        root = _normalize_workspace_root(workspace_root)
        resolved_root = root.resolve(strict=True)
    except (OSError, RuntimeError, WorkspaceRootError) as error:
        raise PublicationManifestNotFoundError(
            f"Workspace root is unavailable: {workspace_root}"
        ) from error
    work_root = module_work_dir(root, record.work)
    candidate = root.joinpath(*record.manifest_path.split("/"))
    try:
        resolved_work_root = work_root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise PublicationManifestNotFoundError(
            f"Publication manifest was not found: {candidate}"
        ) from error
    except (OSError, RuntimeError) as error:
        raise PublicationManifestIntegrityError(
            f"Could not safely resolve publication manifest {candidate}: {error}"
        ) from error
    if not _is_relative_to(resolved_work_root, resolved_root):
        raise PublicationManifestIntegrityError(
            "Referenced module work root resolves outside the workspace."
        )
    if not _is_relative_to(resolved, resolved_root) or not _is_relative_to(
        resolved, resolved_work_root
    ):
        raise PublicationManifestIntegrityError(
            f"Publication manifest resolves outside its referenced work root: {candidate}"
        )
    try:
        is_file = resolved.is_file()
    except OSError as error:
        raise PublicationManifestNotFoundError(
            f"Could not inspect publication manifest {resolved}: {error}"
        ) from error
    if not is_file:
        raise PublicationManifestNotFoundError(
            f"Publication manifest is not a regular file: {resolved}"
        )
    return resolved


def calculate_publication_manifest_digest(
    workspace_root: str | Path, publication: PublicationRecord
) -> str:
    """Calculate lowercase SHA-256 for the exact producer manifest bytes."""
    record = _publication(publication)
    path = resolve_publication_manifest_path(workspace_root, record)
    return _calculate_sha256_for_path(path)


def _calculate_sha256_for_path(path: Path) -> str:
    """Hash one already-resolved path without resolving or interpreting it."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while True:
                chunk = source.read(_DIGEST_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
    except (OSError, ValueError) as error:
        raise PublicationManifestError(
            f"Could not read publication manifest {path}: {error}"
        ) from error
    return digest.hexdigest()


def verify_publication_manifest(
    workspace_root: str | Path, publication: PublicationRecord
) -> Path:
    """Verify the exact manifest's safe path and bound SHA-256 digest."""
    record = _publication(publication)
    path = resolve_publication_manifest_path(workspace_root, record)
    actual_digest = _calculate_sha256_for_path(path)
    if not hmac.compare_digest(actual_digest, record.manifest_digest):
        raise PublicationManifestIntegrityError(
            f"Publication manifest digest does not match at {path}."
        )
    return path


def load_publication_record(
    workspace_root: str | Path, publication_id: str
) -> PublicationRecord:
    """Strictly load one exact canonical Publication Record."""
    path = publication_record_path(workspace_root, publication_id)
    data = _load_json(path, missing_publication=True)
    try:
        record = publication_record_from_dict(data)
    except PublicationRecordValidationError as error:
        raise PublicationReadError(
            f"Publication Record is invalid at {path}: {error}"
        ) from error
    if record.publication_id != publication_id:
        raise PublicationIntegrityError(
            f"Persisted publication ID does not match its canonical path at {path}."
        )
    return record


def load_publication_withdrawal(
    workspace_root: str | Path, publication_id: str
) -> PublicationWithdrawal | None:
    """Strictly load an exact canonical withdrawal, or return None if absent."""
    path = publication_withdrawal_path(workspace_root, publication_id)
    try:
        data = _load_json(path, missing_publication=False)
    except FileNotFoundError:
        return None
    try:
        withdrawal = publication_withdrawal_from_dict(data)
    except PublicationRecordValidationError as error:
        raise PublicationReadError(
            f"Publication Withdrawal is invalid at {path}: {error}"
        ) from error
    if withdrawal.publication_id != publication_id:
        raise PublicationIntegrityError(
            f"Persisted withdrawal ID does not match its canonical path at {path}."
        )
    return withdrawal


def list_publication_ids(workspace_root: str | Path) -> tuple[str, ...]:
    """List validated canonical publication IDs without workspace crawling."""
    directory = publications_dir(workspace_root)
    entries = _collection_entries(directory, "publication")
    identifiers: list[str] = []
    for entry in entries:
        match = _PUBLICATION_FILE.fullmatch(entry.name)
        if match is None:
            raise PublicationReadError(f"Malformed publication filename: {entry}")
        publication_id = match.group(1)
        load_publication_record(workspace_root, publication_id)
        identifiers.append(publication_id)
    return tuple(sorted(identifiers))


def list_publication_records(
    workspace_root: str | Path,
) -> tuple[PublicationRecord, ...]:
    """List all validated canonical publications by opaque ID."""
    return tuple(
        load_publication_record(workspace_root, publication_id)
        for publication_id in list_publication_ids(workspace_root)
    )


def list_publication_withdrawals(
    workspace_root: str | Path,
) -> tuple[PublicationWithdrawal, ...]:
    """List all validated canonical withdrawals by publication ID."""
    directory = publication_withdrawals_dir(workspace_root)
    entries = _collection_entries(directory, "withdrawal")
    withdrawals: list[PublicationWithdrawal] = []
    for entry in entries:
        match = _PUBLICATION_FILE.fullmatch(entry.name)
        if match is None:
            raise PublicationReadError(f"Malformed withdrawal filename: {entry}")
        publication_id = match.group(1)
        withdrawal = load_publication_withdrawal(workspace_root, publication_id)
        if withdrawal is None:
            raise PublicationIntegrityError(
                f"Withdrawal disappeared during canonical listing: {entry}"
            )
        try:
            publication = load_publication_record(workspace_root, publication_id)
        except PublicationNotFoundError as error:
            raise PublicationIntegrityError(
                f"Withdrawal references a missing publication: {publication_id}"
            ) from error
        try:
            validate_publication_withdrawal_relationship(publication, withdrawal)
        except PublicationRecordValidationError as error:
            raise PublicationIntegrityError(
                f"Withdrawal relationship is invalid for {publication_id}: {error}"
            ) from error
        withdrawals.append(withdrawal)
    return tuple(sorted(withdrawals, key=lambda item: item.publication_id))


def list_publication_record_set(
    workspace_root: str | Path,
    work: ModuleWorkRef,
    publication_kind: PublicationKind,
    record_set_id: str,
) -> tuple[PublicationRecord, ...]:
    """Load and validate one exact logical publication series."""
    validated_work = _work(work)
    kind = _kind(publication_kind)
    identifier = _record_set_id(record_set_id)
    records = tuple(
        item
        for item in list_publication_records(workspace_root)
        if item.work == validated_work
        and item.publication_kind == kind
        and item.record_set_id == identifier
    )
    try:
        return validate_publication_record_series(records)
    except PublicationRecordValidationError as error:
        raise PublicationIntegrityError(
            f"Canonical publication series is invalid: {error}"
        ) from error


def get_current_publication_record(
    workspace_root: str | Path,
    work: ModuleWorkRef,
    publication_kind: PublicationKind,
    record_set_id: str,
) -> PublicationRecord | None:
    """Resolve the unique explicit series head, accounting for withdrawal."""
    records = list_publication_record_set(
        workspace_root, work, publication_kind, record_set_id
    )
    if not records:
        return None
    superseded = {
        item.supersedes_publication_id
        for item in records
        if item.supersedes_publication_id is not None
    }
    heads = [item for item in records if item.publication_id not in superseded]
    if len(heads) != 1:
        raise PublicationIntegrityError(
            "Canonical publication series does not have one unique head."
        )
    head = heads[0]
    withdrawal = load_publication_withdrawal(workspace_root, head.publication_id)
    if withdrawal is None:
        return head
    try:
        validate_publication_withdrawal_relationship(head, withdrawal)
    except PublicationRecordValidationError as error:
        raise PublicationIntegrityError(
            f"Current publication withdrawal is invalid: {error}"
        ) from error
    return None


def write_publication_record(
    workspace_root: str | Path, publication: PublicationRecord
) -> Path:
    """Exclusively create one strict, non-idempotent Publication Record."""
    record = _publication(publication)
    verify_publication_manifest(workspace_root, record)
    _validate_registration_relationship(workspace_root, record)
    content = _publication_json(record)
    target = publication_record_path(workspace_root, record.publication_id)
    lock_path = _series_lock_path(workspace_root, record)
    _create_write_directories(target.parent, lock_path.parent)
    lock_created = False
    candidate_created = False
    completed = False
    try:
        _acquire_lock(lock_path)
        lock_created = True
        verify_publication_manifest(workspace_root, record)
        _validate_registration_relationship(workspace_root, record)
        if target.exists():
            raise PublicationConflictError(
                f"Publication Record already exists: {target}"
            )
        try:
            existing = list_publication_record_set(
                workspace_root,
                record.work,
                record.publication_kind,
                record.record_set_id,
            )
        except PublicationReadError as error:
            raise PublicationIntegrityError(
                f"Could not validate canonical publication history: {error}"
            ) from error
        for prior in existing:
            if prior.record_set_revision == record.record_set_revision:
                if _logical_revision_metadata(prior) == _logical_revision_metadata(
                    record
                ):
                    raise PublicationConflictError(
                        "The logical record-set revision already exists."
                    )
                raise PublicationIntegrityError(
                    "The logical record-set revision is already bound to "
                    "contradictory publication metadata."
                )
        if not existing:
            if record.supersedes_publication_id is not None:
                raise PublicationConflictError(
                    "The first publication in a series must not name a predecessor."
                )
        else:
            head = _series_head(existing)
            if record.supersedes_publication_id != head.publication_id:
                raise PublicationConflictError(
                    "A later publication must supersede the unique canonical series head."
                )
            try:
                validate_publication_supersession(head, record)
            except PublicationRecordValidationError as error:
                raise PublicationConflictError(str(error)) from error
        _write_exclusively(target, content, "Publication Record")
        candidate_created = True
        try:
            persisted = load_publication_record(workspace_root, record.publication_id)
        except PublicationStorageError as error:
            raise PublicationWriteError(
                f"Could not verify new Publication Record {target}: {error}"
            ) from error
        if persisted != record:
            raise PublicationWriteError(
                f"Persisted Publication Record differs at {target}."
            )
        verify_publication_manifest(workspace_root, record)
        completed = True
        return target
    finally:
        if candidate_created and not completed:
            _remove_file(target)
        if lock_created:
            _remove_file(lock_path)


def write_publication_withdrawal(
    workspace_root: str | Path, withdrawal: PublicationWithdrawal
) -> Path:
    """Exclusively create one strict, non-idempotent withdrawal record."""
    result = _withdrawal(withdrawal)
    publication = load_publication_record(workspace_root, result.publication_id)
    try:
        validate_publication_withdrawal_relationship(publication, result)
    except PublicationRecordValidationError as error:
        raise PublicationWriteError(f"Invalid withdrawal relationship: {error}") from error
    content = _withdrawal_json(result)
    target = publication_withdrawal_path(workspace_root, result.publication_id)
    lock_path = _series_lock_path(workspace_root, publication)
    _create_write_directories(target.parent, lock_path.parent)
    lock_created = False
    candidate_created = False
    completed = False
    try:
        _acquire_lock(lock_path)
        lock_created = True
        publication = load_publication_record(workspace_root, result.publication_id)
        if load_publication_withdrawal(workspace_root, result.publication_id) is not None:
            raise PublicationConflictError(
                f"Publication Withdrawal already exists: {target}"
            )
        try:
            validate_publication_withdrawal_relationship(publication, result)
        except PublicationRecordValidationError as error:
            raise PublicationWriteError(
                f"Invalid withdrawal relationship: {error}"
            ) from error
        _write_exclusively(target, content, "Publication Withdrawal")
        candidate_created = True
        try:
            persisted = load_publication_withdrawal(
                workspace_root, result.publication_id
            )
        except PublicationStorageError as error:
            raise PublicationWriteError(
                f"Could not verify new Publication Withdrawal {target}: {error}"
            ) from error
        if persisted != result:
            raise PublicationWriteError(
                f"Persisted Publication Withdrawal differs at {target}."
            )
        completed = True
        return target
    finally:
        if candidate_created and not completed:
            _remove_file(target)
        if lock_created:
            _remove_file(lock_path)


def _validate_registration_relationship(
    workspace_root: str | Path, publication: PublicationRecord
) -> None:
    if publication.publication_kind != "academic_result_set":
        return
    revision = publication.academic_work_registration_revision
    assert revision is not None
    try:
        current = load_current_academic_work_registration(
            workspace_root, publication.work
        )
    except AcademicWorkRegistrationStorageError as error:
        raise PublicationIntegrityError(
            "Canonical Academic Work Registration state is invalid for "
            f"{publication.work}: {error}"
        ) from error
    if current is None:
        raise PublicationConflictError(
            "No current Academic Work Registration exists for this publication."
        )
    if current.registration_revision != revision:
        raise PublicationConflictError(
            "The publication must reference the current Academic Work "
            "Registration revision."
        )
    try:
        exact = load_academic_work_registration_revision(
            workspace_root, publication.work, revision
        )
    except AcademicWorkRegistrationStorageError as error:
        raise PublicationIntegrityError(
            "The referenced Academic Work Registration revision could not be "
            f"validated for {publication.work}: {error}"
        ) from error
    if exact.work != publication.work:
        raise PublicationIntegrityError(
            "Referenced Academic Work Registration has the wrong work identity."
        )
    if exact.lifecycle == "cancelled":
        raise PublicationConflictError(
            "A cancelled Academic Work Registration cannot be published."
        )


def _load_json(path: Path, *, missing_publication: bool) -> object:
    try:
        with path.open("r", encoding="utf-8") as source:
            data = json.load(
                source,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_invalid_constant,
            )
    except FileNotFoundError as error:
        if missing_publication:
            raise PublicationNotFoundError(
                f"Publication Record not found: {path}"
            ) from error
        raise
    except (
        json.JSONDecodeError,
        UnicodeError,
        _DuplicateJsonKeyError,
        _InvalidJsonConstantError,
    ) as error:
        raise PublicationReadError(
            f"Canonical publication storage contains invalid JSON at {path}: {error}"
        ) from error
    except OSError as error:
        raise PublicationReadError(
            f"Could not read canonical publication storage {path}: {error}"
        ) from error
    if not isinstance(data, dict):
        raise PublicationReadError(
            f"Canonical publication storage must contain a JSON object at {path}."
        )
    return data


def _collection_entries(directory: Path, description: str) -> tuple[Path, ...]:
    try:
        entries = tuple(directory.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise PublicationReadError(f"Could not enumerate {directory}: {error}") from error
    visible: list[Path] = []
    for entry in sorted(entries, key=lambda item: item.name):
        try:
            is_file = entry.is_file()
        except OSError as error:
            raise PublicationReadError(f"Could not inspect {entry}: {error}") from error
        if not is_file:
            raise PublicationReadError(
                f"Unexpected visible {description} entry: {entry}"
            )
        visible.append(entry)
    return tuple(visible)


def _series_lock_path(
    workspace_root: str | Path, publication: PublicationRecord
) -> Path:
    root = registry_dir(workspace_root) / ".locks" / "publications"
    return (
        root
        / publication.work.class_id
        / publication.work.module_id
        / publication.work.work_id
        / publication.publication_kind
        / f"{publication.record_set_id}.lock"
    )


def _create_write_directories(*directories: Path) -> None:
    try:
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise PublicationWriteError(
            f"Could not create publication storage directories: {error}"
        ) from error


def _acquire_lock(path: Path) -> None:
    created = False
    try:
        with path.open("x", encoding="utf-8", newline="") as output:
            created = True
            output.write("publication write in progress\n")
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        raise PublicationConflictError(
            f"Publication series lock already exists: {path}"
        ) from error
    except (OSError, UnicodeError) as error:
        if created:
            _remove_file(path)
        raise PublicationWriteError(
            f"Could not acquire publication series lock {path}: {error}"
        ) from error


def _write_exclusively(path: Path, content: str, description: str) -> None:
    created = False
    try:
        with path.open("x", encoding="utf-8", newline="") as output:
            created = True
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory_if_supported(path.parent)
    except FileExistsError as error:
        if created:
            _remove_file(path)
        raise PublicationConflictError(f"{description} already exists: {path}") from error
    except (OSError, UnicodeError) as error:
        if created:
            _remove_file(path)
        raise PublicationWriteError(f"Could not write {description} {path}: {error}") from error


def _publication_json(publication: PublicationRecord) -> str:
    return json.dumps(
        publication_record_to_dict(publication),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def _withdrawal_json(withdrawal: PublicationWithdrawal) -> str:
    return json.dumps(
        publication_withdrawal_to_dict(withdrawal),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def _series_head(records: tuple[PublicationRecord, ...]) -> PublicationRecord:
    superseded = {
        item.supersedes_publication_id
        for item in records
        if item.supersedes_publication_id is not None
    }
    heads = [item for item in records if item.publication_id not in superseded]
    if len(heads) != 1:
        raise PublicationIntegrityError("Publication series has competing heads.")
    return heads[0]


def _logical_revision_metadata(publication: PublicationRecord) -> tuple[object, ...]:
    """Return immutable logical-revision metadata excluding its opaque record ID."""
    return (
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
        publication.supersedes_publication_id,
    )


def _publication(value: object) -> PublicationRecord:
    if not isinstance(value, PublicationRecord):
        raise PublicationRecordValidationError(
            "publication must be a PublicationRecord."
        )
    return validate_publication_record(value)


def _withdrawal(value: object) -> PublicationWithdrawal:
    if not isinstance(value, PublicationWithdrawal):
        raise PublicationRecordValidationError(
            "withdrawal must be a PublicationWithdrawal."
        )
    return validate_publication_withdrawal(value)


def _work(value: object) -> ModuleWorkRef:
    if not isinstance(value, ModuleWorkRef):
        raise PublicationRecordValidationError("work must be a ModuleWorkRef.")
    try:
        return validate_module_work_ref(value)
    except RoutingModelError as error:
        raise PublicationRecordValidationError(f"work is invalid: {error}") from error


def _kind(value: object) -> PublicationKind:
    if not is_publication_kind(value):
        raise PublicationRecordValidationError("publication_kind is invalid.")
    return cast(PublicationKind, value)


def _record_set_id(value: object) -> str:
    if not isinstance(value, str):
        raise PublicationRecordValidationError("record_set_id must be a string.")
    try:
        identifier = validate_identifier(value, "record_set_id")
    except IdentifierValidationError as error:
        raise PublicationRecordValidationError(str(error)) from error
    if identifier != identifier.lower():
        raise PublicationRecordValidationError("record_set_id must be lowercase.")
    return identifier


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _reject_duplicate_keys(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_invalid_constant(value: str) -> NoReturn:
    raise _InvalidJsonConstantError(f"invalid JSON numeric constant: {value}")


def _fsync_directory_if_supported(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
