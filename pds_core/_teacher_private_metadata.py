"""Strict, side-effect-free v1 teacher-private association metadata codecs.

Private infrastructure for Core #238. Parsing metadata never authenticates a
caller, qualifies filesystem permissions, creates a directory or binds Notes.
Nothing in this module is a public Notes service or a storage capability.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Literal, NoReturn
from uuid import UUID

ASSOCIATION_SCHEMA = "pds.teacher-private-association"
REGISTRY_SCHEMA = "pds.teacher-private-registry"
SCHEMA_VERSION = 1
MAX_ASSOCIATION_BYTES = 4096
MAX_REGISTRY_BYTES = 524288
MAX_REGISTRY_BINDINGS = 1024

_OWNER_KINDS = frozenset({"windows_token_sid", "posix_euid"})
_SID_PATTERN = re.compile(r"S-1-(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*))+\Z")
_UID_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_FINGERPRINT_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


class PrivateMetadataErrorCode(str, Enum):
    """Sanitized, non-path-bearing parse/validation failure reasons."""

    INVALID_ENCODING = "invalid_encoding"
    INVALID_SHAPE = "invalid_shape"
    INVALID_FIELD = "invalid_field"
    INVALID_IDENTITY = "invalid_identity"
    DUPLICATE_KEY = "duplicate_key"
    DUPLICATE_ASSOCIATION = "duplicate_association"
    UNSUPPORTED_VERSION = "unsupported_version"
    SIZE_LIMIT = "size_limit"


class PrivateMetadataError(ValueError):
    """Bounded validation error with no private metadata in the message."""

    def __init__(self, code: PrivateMetadataErrorCode):
        self.code = code
        super().__init__(f"Private metadata refused: {code.value}.")


def _reject(code: PrivateMetadataErrorCode) -> NoReturn:
    raise PrivateMetadataError(code)


def _is_safe_text(value: object, *, max_chars: int) -> bool:
    if not isinstance(value, str) or not value or len(value) > max_chars:
        return False
    return all(unicodedata.category(char) not in {"Cc", "Cf", "Cs"} for char in value)


def _uuid4(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _integer(value: object) -> bool:
    return type(value) is int and value > 0


def _owner_value(kind: str, value: object) -> bool:
    if not isinstance(value, str) or len(value) > 256:
        return False
    if kind == "windows_token_sid":
        return _SID_PATTERN.fullmatch(value) is not None
    if kind == "posix_euid":
        return _UID_PATTERN.fullmatch(value) is not None
    return False


def _absolute_root(value: object, kind: str) -> bool:
    if not _is_safe_text(value, max_chars=4096) or not isinstance(value, str):
        return False
    if kind == "windows_token_sid":
        # Syntax check only. Native locality, reparse, and ACL proof is later.
        if value.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\")):
            return False
        windows_path = PureWindowsPath(value)
        return bool(
            windows_path.is_absolute() and windows_path.drive and windows_path.root
        ) and all(
            part not in {".", ".."} for part in value.replace("/", "\\").split("\\")
        )
    if kind == "posix_euid":
        posix_path = PurePosixPath(value)
        if not posix_path.is_absolute() or value.startswith("//"):
            return False
        return all(part not in {".", ".."} for part in value.split("/"))
    return False


def _exact_keys(value: object, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _reject(PrivateMetadataErrorCode.INVALID_SHAPE)
    return value


def _validate_schema(value: dict[str, Any], name: str) -> None:
    if value.get("schema") != name:
        _reject(PrivateMetadataErrorCode.INVALID_SHAPE)
    version = value.get("version")
    if type(version) is not int:
        _reject(PrivateMetadataErrorCode.INVALID_SHAPE)
    if version != SCHEMA_VERSION:
        _reject(PrivateMetadataErrorCode.UNSUPPORTED_VERSION)


@dataclass(frozen=True, slots=True)
class PrivateAssociationDescriptor:
    association_id: str

    def __post_init__(self) -> None:
        if not _uuid4(self.association_id):
            _reject(PrivateMetadataErrorCode.INVALID_IDENTITY)


@dataclass(frozen=True, slots=True)
class PrivateRegistryOwner:
    kind: Literal["windows_token_sid", "posix_euid"]
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not str
            or self.kind not in _OWNER_KINDS
            or not _owner_value(self.kind, self.value)
        ):
            _reject(PrivateMetadataErrorCode.INVALID_IDENTITY)


@dataclass(frozen=True, slots=True)
class PrivateRegistryBinding:
    association_id: str
    binding_revision: int
    accepted_root: str = field(repr=False)
    root_fingerprint: str | None = field(default=None, repr=False)
    state: Literal["active"] = "active"

    def __post_init__(self) -> None:
        if not _uuid4(self.association_id):
            _reject(PrivateMetadataErrorCode.INVALID_IDENTITY)
        if not _integer(self.binding_revision) or self.state != "active":
            _reject(PrivateMetadataErrorCode.INVALID_FIELD)
        if self.root_fingerprint is not None and (
            not isinstance(self.root_fingerprint, str)
            or _FINGERPRINT_PATTERN.fullmatch(self.root_fingerprint) is None
        ):
            _reject(PrivateMetadataErrorCode.INVALID_FIELD)


@dataclass(frozen=True, slots=True)
class PrivateRegistry:
    owner: PrivateRegistryOwner = field(repr=False)
    revision: int
    bindings: tuple[PrivateRegistryBinding, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.owner, PrivateRegistryOwner) or not _integer(
            self.revision
        ):
            _reject(PrivateMetadataErrorCode.INVALID_FIELD)
        if (
            type(self.bindings) is not tuple
            or len(self.bindings) > MAX_REGISTRY_BINDINGS
        ):
            _reject(PrivateMetadataErrorCode.SIZE_LIMIT)
        seen: set[str] = set()
        for binding in self.bindings:
            if not isinstance(binding, PrivateRegistryBinding):
                _reject(PrivateMetadataErrorCode.INVALID_FIELD)
            if binding.association_id in seen:
                _reject(PrivateMetadataErrorCode.DUPLICATE_ASSOCIATION)
            seen.add(binding.association_id)
            if not _absolute_root(binding.accepted_root, self.owner.kind):
                _reject(PrivateMetadataErrorCode.INVALID_FIELD)


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject(PrivateMetadataErrorCode.DUPLICATE_KEY)
        result[key] = value
    return result


def _refuse_constant(_value: str) -> None:
    _reject(PrivateMetadataErrorCode.INVALID_FIELD)


def _decode_json(raw: bytes, limit: int) -> object:
    if type(raw) is not bytes:
        _reject(PrivateMetadataErrorCode.INVALID_SHAPE)
    if len(raw) > limit:
        _reject(PrivateMetadataErrorCode.SIZE_LIMIT)
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _reject(PrivateMetadataErrorCode.INVALID_ENCODING)
    try:
        return json.loads(
            decoded,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_refuse_constant,
        )
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        if isinstance(exc, PrivateMetadataError):
            raise
        raise PrivateMetadataError(PrivateMetadataErrorCode.INVALID_SHAPE) from None


def _encode_json(value: dict[str, Any], limit: int) -> bytes:
    data = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(data) > limit:
        _reject(PrivateMetadataErrorCode.SIZE_LIMIT)
    return data


def decode_association_descriptor(raw: bytes) -> PrivateAssociationDescriptor:
    obj = _exact_keys(
        _decode_json(raw, MAX_ASSOCIATION_BYTES),
        frozenset({"schema", "version", "association_id"}),
    )
    _validate_schema(obj, ASSOCIATION_SCHEMA)
    return PrivateAssociationDescriptor(association_id=obj["association_id"])


def encode_association_descriptor(value: PrivateAssociationDescriptor) -> bytes:
    if not isinstance(value, PrivateAssociationDescriptor):
        _reject(PrivateMetadataErrorCode.INVALID_SHAPE)
    return _encode_json(
        {
            "schema": ASSOCIATION_SCHEMA,
            "version": SCHEMA_VERSION,
            "association_id": value.association_id,
        },
        MAX_ASSOCIATION_BYTES,
    )


def decode_private_registry(raw: bytes) -> PrivateRegistry:
    obj = _exact_keys(
        _decode_json(raw, MAX_REGISTRY_BYTES),
        frozenset({"schema", "version", "owner", "revision", "bindings"}),
    )
    _validate_schema(obj, REGISTRY_SCHEMA)
    owner_raw = _exact_keys(obj["owner"], frozenset({"kind", "value"}))
    owner = PrivateRegistryOwner(kind=owner_raw["kind"], value=owner_raw["value"])
    entries = obj["bindings"]
    if not isinstance(entries, list):
        _reject(PrivateMetadataErrorCode.INVALID_SHAPE)
    if len(entries) > MAX_REGISTRY_BINDINGS:
        _reject(PrivateMetadataErrorCode.SIZE_LIMIT)
    bindings: list[PrivateRegistryBinding] = []
    for entry in entries:
        binding = _exact_keys(
            entry,
            frozenset(
                {
                    "association_id",
                    "binding_revision",
                    "accepted_root",
                    "root_fingerprint",
                    "state",
                }
            ),
        )
        bindings.append(
            PrivateRegistryBinding(
                association_id=binding["association_id"],
                binding_revision=binding["binding_revision"],
                accepted_root=binding["accepted_root"],
                root_fingerprint=binding["root_fingerprint"],
                state=binding["state"],
            )
        )
    return PrivateRegistry(
        owner=owner, revision=obj["revision"], bindings=tuple(bindings)
    )


def encode_private_registry(value: PrivateRegistry) -> bytes:
    if not isinstance(value, PrivateRegistry):
        _reject(PrivateMetadataErrorCode.INVALID_SHAPE)
    return _encode_json(
        {
            "schema": REGISTRY_SCHEMA,
            "version": SCHEMA_VERSION,
            "owner": {"kind": value.owner.kind, "value": value.owner.value},
            "revision": value.revision,
            "bindings": [
                {
                    "association_id": item.association_id,
                    "binding_revision": item.binding_revision,
                    "accepted_root": item.accepted_root,
                    "root_fingerprint": item.root_fingerprint,
                    "state": item.state,
                }
                for item in value.bindings
            ],
        },
        MAX_REGISTRY_BYTES,
    )
