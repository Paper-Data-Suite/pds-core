"""Immutable workspace storage for neutral grouping-signal snapshots."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

from pds_core.grouping_signals import (
    GroupingSignalSet,
    GroupingSignalValidationError,
    grouping_signal_set_from_json,
    grouping_signal_set_to_json_bytes,
    validate_grouping_signal_set,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.workspace import WorkspaceRootError, _normalize_workspace_root

GROUPING_SIGNAL_DIGEST_ALGORITHM: Final[str] = "sha256"
_GROUPING_SIGNALS_RELATIVE_PARTS: Final[tuple[str, str]] = (
    "exchange",
    "grouping-signals",
)
_DIGEST_BYTES_RE: Final[re.Pattern[bytes]] = re.compile(rb"^[0-9a-f]{64}\n$")
_JSON_SUFFIX: Final[str] = ".json"
_DIGEST_SUFFIX: Final[str] = ".json.sha256"

GroupingSignalWriteDisposition: TypeAlias = Literal["created", "existing"]


class GroupingSignalStorageError(RuntimeError):
    """Base error for immutable grouping-signal exchange storage."""


class GroupingSignalReadError(GroupingSignalStorageError):
    """Raised when grouping-signal storage cannot be read or validated."""


class GroupingSignalWriteError(GroupingSignalStorageError):
    """Raised when grouping-signal storage cannot be written safely."""


class GroupingSignalNotFoundError(GroupingSignalReadError):
    """Raised when one explicitly requested grouping signal is absent."""


class GroupingSignalConflictError(GroupingSignalWriteError):
    """Raised when immutable signal identity collides with different contents."""


class GroupingSignalIntegrityError(GroupingSignalStorageError):
    """Raised when canonical path identity or digest binding is inconsistent."""


@dataclass(frozen=True, slots=True)
class StoredGroupingSignal:
    """One strictly verified immutable grouping signal and its byte digest."""

    signal: GroupingSignalSet
    digest_algorithm: str
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.signal, GroupingSignalSet):
            raise GroupingSignalStorageError(
                "signal must be a GroupingSignalSet."
            )
        try:
            validated_signal = validate_grouping_signal_set(self.signal)
        except GroupingSignalValidationError as error:
            raise GroupingSignalStorageError(
                f"stored signal is invalid: {error}"
            ) from error
        object.__setattr__(self, "signal", validated_signal)
        if self.digest_algorithm != GROUPING_SIGNAL_DIGEST_ALGORITHM:
            raise GroupingSignalStorageError(
                f'digest_algorithm must be "{GROUPING_SIGNAL_DIGEST_ALGORITHM}".'
            )
        if re.fullmatch(r"[0-9a-f]{64}", self.digest) is None:
            raise GroupingSignalStorageError(
                "digest must be exactly 64 lowercase hexadecimal characters."
            )
        expected_digest = hashlib.sha256(
            grouping_signal_set_to_json_bytes(validated_signal)
        ).hexdigest()
        if not hmac.compare_digest(self.digest, expected_digest):
            raise GroupingSignalStorageError(
                "digest does not match the canonical stored signal bytes."
            )


@dataclass(frozen=True, slots=True)
class GroupingSignalWriteResult:
    """Result of an immutable grouping-signal write attempt."""

    disposition: GroupingSignalWriteDisposition
    stored: StoredGroupingSignal

    def __post_init__(self) -> None:
        if self.disposition not in {"created", "existing"}:
            raise GroupingSignalStorageError(
                'disposition must be "created" or "existing".'
            )
        if not isinstance(self.stored, StoredGroupingSignal):
            raise GroupingSignalStorageError(
                "stored must be a StoredGroupingSignal."
            )


def grouping_signals_dir(workspace_root: str | Path) -> Path:
    """Return the neutral grouping-signal exchange collection root."""
    root = _root(workspace_root)
    return root.joinpath(*_GROUPING_SIGNALS_RELATIVE_PARTS)


def grouping_signal_class_dir(workspace_root: str | Path, class_id: str) -> Path:
    """Return the exchange directory for one exact Core class identity."""
    return grouping_signals_dir(workspace_root) / _identifier(class_id, "class_id")


def grouping_signal_path(
    workspace_root: str | Path, class_id: str, signal_set_id: str
) -> Path:
    """Return the canonical immutable JSON path for one grouping signal."""
    identifier = _identifier(signal_set_id, "signal_set_id")
    return grouping_signal_class_dir(workspace_root, class_id) / f"{identifier}.json"


def grouping_signal_digest_path(
    workspace_root: str | Path, class_id: str, signal_set_id: str
) -> Path:
    """Return the canonical SHA-256 sidecar path for one grouping signal."""
    identifier = _identifier(signal_set_id, "signal_set_id")
    return grouping_signal_class_dir(workspace_root, class_id) / (
        f"{identifier}.json.sha256"
    )


def calculate_grouping_signal_digest(signal: GroupingSignalSet) -> str:
    """Return lowercase SHA-256 for the exact #180 canonical signal bytes."""
    candidate = validate_grouping_signal_set(signal)
    return hashlib.sha256(grouping_signal_set_to_json_bytes(candidate)).hexdigest()


def load_grouping_signal(
    workspace_root: str | Path,
    class_id: str,
    signal_set_id: str,
) -> StoredGroupingSignal:
    """Strictly load one exact immutable grouping signal and verify its digest."""
    root = _root(workspace_root)
    validated_class_id = _identifier(class_id, "class_id")
    validated_signal_set_id = _identifier(signal_set_id, "signal_set_id")
    identity_description = (
        f"class_id={validated_class_id!r}, "
        f"signal_set_id={validated_signal_set_id!r}"
    )
    class_dir = root.joinpath(*_GROUPING_SIGNALS_RELATIVE_PARTS, validated_class_id)
    _validate_storage_chain(root, class_dir)
    json_path = class_dir / f"{validated_signal_set_id}.json"
    digest_path = class_dir / f"{validated_signal_set_id}.json.sha256"

    json_exists = _supported_file_exists(json_path, "grouping-signal JSON")
    digest_exists = _supported_file_exists(digest_path, "grouping-signal digest")
    if not json_exists and not digest_exists:
        raise GroupingSignalNotFoundError(
            f"Grouping signal not found for {identity_description}."
        )
    if json_exists != digest_exists:
        raise GroupingSignalIntegrityError(
            "Grouping-signal storage pair is incomplete for "
            f"{identity_description}."
        )

    raw_json = _read_bytes(json_path, "grouping-signal JSON")
    raw_digest = _read_bytes(digest_path, "grouping-signal digest")
    expected_digest = _parse_digest_sidecar(raw_digest, digest_path)
    actual_digest = hashlib.sha256(raw_json).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise GroupingSignalIntegrityError(
            "Grouping-signal canonical-byte digest does not match its sidecar for "
            f"{identity_description}."
        )

    try:
        signal = grouping_signal_set_from_json(raw_json)
    except GroupingSignalValidationError as error:
        raise GroupingSignalReadError(
            "Stored grouping-signal JSON is invalid or noncanonical for "
            f"{identity_description}: {error}"
        ) from error
    if signal.class_id != validated_class_id:
        raise GroupingSignalIntegrityError(
            "Stored grouping-signal class_id does not match its canonical path."
        )
    if signal.signal_set_id != validated_signal_set_id:
        raise GroupingSignalIntegrityError(
            "Stored grouping-signal signal_set_id does not match its canonical path."
        )
    if grouping_signal_set_to_json_bytes(signal) != raw_json:
        raise GroupingSignalIntegrityError(
            "Stored grouping-signal bytes differ from canonical serialization."
        )
    return StoredGroupingSignal(
        signal=signal,
        digest_algorithm=GROUPING_SIGNAL_DIGEST_ALGORITHM,
        digest=actual_digest,
    )


def write_grouping_signal(
    workspace_root: str | Path,
    signal: GroupingSignalSet,
) -> GroupingSignalWriteResult:
    """Create one immutable signal pair, or reconcile an exact idempotent retry."""
    candidate = validate_grouping_signal_set(signal)
    canonical_bytes = grouping_signal_set_to_json_bytes(candidate)
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    digest_bytes = f"{digest}\n".encode("ascii")

    root = _root(workspace_root)
    class_dir = root.joinpath(
        *_GROUPING_SIGNALS_RELATIVE_PARTS,
        candidate.class_id,
    )
    _validate_storage_chain(root, class_dir)
    json_path = class_dir / f"{candidate.signal_set_id}.json"
    digest_path = class_dir / f"{candidate.signal_set_id}.json.sha256"

    json_exists = _supported_file_exists(json_path, "grouping-signal JSON")
    digest_exists = _supported_file_exists(digest_path, "grouping-signal digest")
    if json_exists or digest_exists:
        if json_exists != digest_exists:
            raise GroupingSignalIntegrityError(
                "Grouping-signal storage pair is incomplete for the requested identity."
            )
        return _existing_write_result(
            root,
            candidate,
            canonical_bytes,
        )

    try:
        class_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise GroupingSignalWriteError(
            f"Could not create grouping-signal exchange directory {class_dir}: {error}"
        ) from error
    _validate_storage_chain(root, class_dir, require_class_dir=True)

    created_json = False
    created_digest = False
    try:
        try:
            _write_bytes_exclusively(json_path, canonical_bytes)
            created_json = True
        except FileExistsError:
            return _existing_write_result(root, candidate, canonical_bytes)

        try:
            _write_bytes_exclusively(digest_path, digest_bytes)
            created_digest = True
        except FileExistsError as error:
            raise GroupingSignalIntegrityError(
                "Grouping-signal digest sidecar appeared during immutable creation."
            ) from error

        try:
            stored = load_grouping_signal(
                root,
                candidate.class_id,
                candidate.signal_set_id,
            )
        except GroupingSignalStorageError as error:
            raise GroupingSignalWriteError(
                "New grouping-signal storage could not be verified after write: "
                f"{error}"
            ) from error
        if stored.signal != candidate or stored.digest != digest:
            raise GroupingSignalWriteError(
                "Persisted grouping signal differs from the validated candidate."
            )
        return GroupingSignalWriteResult(disposition="created", stored=stored)
    except Exception:
        if created_digest:
            _remove_if_exact(digest_path, digest_bytes)
        if created_json:
            _remove_if_exact(json_path, canonical_bytes)
        raise


def list_grouping_signal_ids(
    workspace_root: str | Path,
    class_id: str,
) -> tuple[str, ...]:
    """List all strictly verified signal identities for one exact class."""
    root = _root(workspace_root)
    validated_class_id = _identifier(class_id, "class_id")
    class_dir = root.joinpath(*_GROUPING_SIGNALS_RELATIVE_PARTS, validated_class_id)
    _validate_storage_chain(root, class_dir)
    if not class_dir.exists():
        return ()
    if class_dir.is_symlink() or not class_dir.is_dir():
        raise GroupingSignalReadError(
            f"Grouping-signal class storage is not a canonical directory: {class_dir}"
        )

    try:
        entries = tuple(sorted(class_dir.iterdir(), key=lambda item: item.name))
    except OSError as error:
        raise GroupingSignalReadError(
            f"Could not enumerate grouping-signal storage {class_dir}: {error}"
        ) from error

    json_ids: set[str] = set()
    digest_ids: set[str] = set()
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_symlink():
            raise GroupingSignalReadError(
                f"Unexpected symlink in grouping-signal storage: {entry}"
            )
        try:
            is_file = entry.is_file()
        except OSError as error:
            raise GroupingSignalReadError(
                f"Could not inspect grouping-signal storage entry {entry}: {error}"
            ) from error
        if not is_file:
            raise GroupingSignalReadError(
                f"Unexpected visible grouping-signal storage entry: {entry}"
            )
        if entry.name.endswith(_DIGEST_SUFFIX):
            identifier = entry.name[: -len(_DIGEST_SUFFIX)]
            validated = _listing_identifier(identifier, entry)
            digest_ids.add(validated)
        elif entry.name.endswith(_JSON_SUFFIX):
            identifier = entry.name[: -len(_JSON_SUFFIX)]
            validated = _listing_identifier(identifier, entry)
            json_ids.add(validated)
        else:
            raise GroupingSignalReadError(
                f"Unexpected visible grouping-signal storage entry: {entry}"
            )

    if json_ids != digest_ids:
        missing_digests = sorted(json_ids - digest_ids)
        missing_json = sorted(digest_ids - json_ids)
        details: list[str] = []
        if missing_digests:
            details.append("missing digest sidecar for: " + ", ".join(missing_digests))
        if missing_json:
            details.append("missing JSON for: " + ", ".join(missing_json))
        raise GroupingSignalIntegrityError(
            "Grouping-signal storage contains incomplete pair(s): "
            + "; ".join(details)
            + "."
        )

    identifiers = tuple(sorted(json_ids))
    for identifier in identifiers:
        load_grouping_signal(root, validated_class_id, identifier)
    return identifiers


def _existing_write_result(
    workspace_root: Path,
    candidate: GroupingSignalSet,
    canonical_bytes: bytes,
) -> GroupingSignalWriteResult:
    try:
        stored = load_grouping_signal(
            workspace_root,
            candidate.class_id,
            candidate.signal_set_id,
        )
    except GroupingSignalNotFoundError as error:
        raise GroupingSignalIntegrityError(
            "Grouping-signal storage changed concurrently during immutable creation."
        ) from error
    if grouping_signal_set_to_json_bytes(stored.signal) != canonical_bytes:
        raise GroupingSignalConflictError(
            "Grouping-signal identity already exists with different canonical contents."
        )
    return GroupingSignalWriteResult(disposition="existing", stored=stored)


def _root(workspace_root: str | Path) -> Path:
    try:
        return _normalize_workspace_root(workspace_root)
    except (WorkspaceRootError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise GroupingSignalStorageError(
            f"Invalid workspace root for grouping-signal storage: {workspace_root!r}."
        ) from error


def _identifier(value: object, field_name: str) -> str:
    try:
        return validate_identifier(value, field_name)  # type: ignore[arg-type]
    except IdentifierValidationError as error:
        raise GroupingSignalStorageError(str(error)) from error


def _listing_identifier(value: str, path: Path) -> str:
    try:
        return validate_identifier(value, "signal_set_id")
    except IdentifierValidationError as error:
        raise GroupingSignalReadError(
            f"Malformed grouping-signal filename {path}: {error}"
        ) from error


def _validate_storage_chain(
    root: Path,
    class_dir: Path,
    *,
    require_class_dir: bool = False,
) -> None:
    exchange_dir = root / _GROUPING_SIGNALS_RELATIVE_PARTS[0]
    grouping_dir = exchange_dir / _GROUPING_SIGNALS_RELATIVE_PARTS[1]
    candidates = (exchange_dir, grouping_dir, class_dir)
    for path in candidates:
        try:
            exists = path.exists()
            is_symlink = path.is_symlink()
        except OSError as error:
            raise GroupingSignalIntegrityError(
                "Could not inspect grouping-signal storage directory "
                f"{path}: {error}"
            ) from error
        if is_symlink:
            raise GroupingSignalIntegrityError(
                f"Grouping-signal storage directory must not be a symlink: {path}"
            )
        if exists:
            try:
                if not path.is_dir():
                    raise GroupingSignalIntegrityError(
                        f"Grouping-signal storage path is not a directory: {path}"
                    )
            except OSError as error:
                raise GroupingSignalIntegrityError(
                    "Could not inspect grouping-signal storage directory "
                f"{path}: {error}"
                ) from error
    if require_class_dir and not class_dir.is_dir():
        raise GroupingSignalWriteError(
            f"Grouping-signal class directory was not created: {class_dir}"
        )
    if class_dir.exists():
        try:
            resolved_root = root.resolve(strict=False)
            resolved_class_dir = class_dir.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise GroupingSignalIntegrityError(
                "Could not resolve grouping-signal storage directory "
                f"{class_dir}: {error}"
            ) from error
        if not _is_relative_to(resolved_class_dir, resolved_root):
            raise GroupingSignalIntegrityError(
                "Grouping-signal storage resolves outside the workspace root."
            )


def _supported_file_exists(path: Path, description: str) -> bool:
    try:
        if path.is_symlink():
            raise GroupingSignalIntegrityError(
                f"{description} must not be a symlink: {path}"
            )
        if not path.exists():
            return False
        if not path.is_file():
            raise GroupingSignalIntegrityError(
                f"{description} must be a regular file: {path}"
            )
        return True
    except GroupingSignalStorageError:
        raise
    except OSError as error:
        raise GroupingSignalReadError(
            f"Could not inspect {description} {path}: {error}"
        ) from error


def _read_bytes(path: Path, description: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise GroupingSignalReadError(
            f"Could not read {description} {path}: {error}"
        ) from error


def _parse_digest_sidecar(data: bytes, path: Path) -> str:
    if _DIGEST_BYTES_RE.fullmatch(data) is None:
        raise GroupingSignalReadError(
            f"Grouping-signal digest sidecar is malformed at {path}."
        )
    return data[:-1].decode("ascii")


def _write_bytes_exclusively(path: Path, content: bytes) -> None:
    created_stat: os.stat_result | None = None
    try:
        with path.open("xb") as output:
            created_stat = os.fstat(output.fileno())
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory_if_supported(path.parent)
    except FileExistsError:
        raise
    except OSError as error:
        if created_stat is not None:
            _remove_if_same_file(path, created_stat)
        raise GroupingSignalWriteError(
            f"Could not create immutable grouping-signal file {path}: {error}"
        ) from error


def _remove_if_same_file(path: Path, expected_stat: os.stat_result) -> None:
    try:
        if path.is_symlink():
            return
        current = path.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (
            expected_stat.st_dev,
            expected_stat.st_ino,
        ):
            return
        path.unlink()
        _fsync_directory_if_supported(path.parent)
    except (FileNotFoundError, OSError):
        pass


def _remove_if_exact(path: Path, expected: bytes) -> None:
    try:
        if path.is_symlink() or not path.is_file():
            return
        if path.read_bytes() != expected:
            return
        path.unlink()
        _fsync_directory_if_supported(path.parent)
    except OSError:
        pass


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
