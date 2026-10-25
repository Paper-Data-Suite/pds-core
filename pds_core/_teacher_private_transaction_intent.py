"""Pure, bounded, private transaction-intent envelope for Core #238.

A decoded intent is untrusted metadata, not an OS owner credential or a
permission to replay, create, reconcile, or change teacher-private files.
No I/O, locks, sidecar writes, or private-directory creation occur here.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, NoReturn

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_transaction_witness as transaction

INTENT_SCHEMA = "pds.teacher-private-transaction-intent"
INTENT_VERSION = 1
# Two potentially full 512-KiB registries, two 4-KiB descriptors, framing.
MAX_INTENT_BYTES = (
    4 * metadata.MAX_REGISTRY_BYTES + 4 * metadata.MAX_ASSOCIATION_BYTES + 32768
)
_FIELDS = frozenset(
    {
        "schema",
        "version",
        "operation",
        "transaction_id",
        "association_before",
        "association_after",
        "registry_revision_before",
        "registry_revision_after",
        "descriptor_sha256_before",
        "descriptor_sha256_after",
        "registry_sha256_before",
        "registry_sha256_after",
        "descriptor_before_b64",
        "descriptor_after_b64",
        "registry_before_b64",
        "registry_after_b64",
    }
)


class PrivateIntentError(ValueError):
    """Bounded refusal; never include metadata, private paths, or values."""

    def __init__(self) -> None:
        super().__init__("Private transaction intent refused: invalid state.")


def _reject() -> NoReturn:
    raise PrivateIntentError


def _digest(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _validate_bytes(raw: object, *, optional: bool, maximum: int) -> None:
    if raw is None and optional:
        return
    if not isinstance(raw, bytes) or type(raw) is not bytes or len(raw) > maximum:
        _reject()


def _identity_mapping(
    registry: metadata.PrivateRegistry,
) -> dict[str, metadata.PrivateRegistryBinding]:
    return {binding.association_id: binding for binding in registry.bindings}


def _check_transition(
    witness: transaction.PrivateTransactionWitness,
    before: metadata.PrivateRegistry | None,
    after: metadata.PrivateRegistry,
) -> None:
    if after.revision != witness.registry_revision_after:
        _reject()
    if before is None:
        if witness.registry_revision_before != 0:
            _reject()
        if witness.operation is not transaction.PrivateBindingOperation.INITIALIZE:
            _reject()
        old: dict[str, metadata.PrivateRegistryBinding] = {}
    else:
        if (
            before.revision != witness.registry_revision_before
            or before.owner != after.owner
        ):
            _reject()
        old = _identity_mapping(before)
    new = _identity_mapping(after)
    previous_id = witness.association_before
    current_id = witness.association_after
    if witness.operation is transaction.PrivateBindingOperation.REBIND_MOVE:
        if previous_id is None or previous_id not in old:
            _reject()
        prior_binding = old[previous_id]
        moved = new.get(current_id)
        if (
            moved is None
            or moved.binding_revision != prior_binding.binding_revision + 1
            or moved.accepted_root == prior_binding.accepted_root
            or moved.state != prior_binding.state
            or set(new) != set(old)
        ):
            _reject()
        if {k: v for k, v in old.items() if k != previous_id} != {
            k: v for k, v in new.items() if k != current_id
        }:
            _reject()
    else:
        created = new.get(current_id)
        if (
            current_id in old
            or created is None
            or created.binding_revision != 1
            or {k: v for k, v in new.items() if k != current_id} != old
        ):
            _reject()
        if created.accepted_root in {binding.accepted_root for binding in old.values()}:
            _reject()
        if witness.operation is transaction.PrivateBindingOperation.FORK_COPY:
            if previous_id is None or previous_id not in old:
                _reject()


@dataclass(frozen=True, slots=True, repr=False)
class PrivateTransactionIntent:
    """Exact before/after metadata bytes, for a future guarded private journal.

    Full registry bytes include an owner value and local root; every field is
    intentionally excluded from repr. The object cannot authorize storage.
    """

    witness: transaction.PrivateTransactionWitness = field(repr=False)
    descriptor_before: bytes | None = field(repr=False)
    descriptor_after: bytes = field(repr=False)
    registry_before: bytes | None = field(repr=False)
    registry_after: bytes = field(repr=False)

    def __post_init__(self) -> None:
        w = self.witness
        if not isinstance(w, transaction.PrivateTransactionWitness):
            _reject()
        _validate_bytes(
            self.descriptor_before,
            optional=True,
            maximum=metadata.MAX_ASSOCIATION_BYTES,
        )
        _validate_bytes(
            self.descriptor_after,
            optional=False,
            maximum=metadata.MAX_ASSOCIATION_BYTES,
        )
        _validate_bytes(
            self.registry_before, optional=True, maximum=metadata.MAX_REGISTRY_BYTES
        )
        _validate_bytes(
            self.registry_after, optional=False, maximum=metadata.MAX_REGISTRY_BYTES
        )
        if (
            _digest(self.descriptor_before) != w.descriptor_sha256_before
            or _digest(self.descriptor_after) != w.descriptor_sha256_after
            or _digest(self.registry_before) != w.registry_sha256_before
            or _digest(self.registry_after) != w.registry_sha256_after
        ):
            _reject()
        try:
            before_descriptor = (
                metadata.decode_association_descriptor(self.descriptor_before)
                if self.descriptor_before is not None
                else None
            )
            after_descriptor = metadata.decode_association_descriptor(
                self.descriptor_after
            )
            before_registry = (
                metadata.decode_private_registry(self.registry_before)
                if self.registry_before is not None
                else None
            )
            after_registry = metadata.decode_private_registry(self.registry_after)
        except metadata.PrivateMetadataError:
            raise PrivateIntentError from None
        if (
            (before_descriptor.association_id if before_descriptor else None)
            != w.association_before
            or after_descriptor.association_id != w.association_after
        ):
            _reject()
        _check_transition(w, before_registry, after_registry)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _reject_constant(_constant: str) -> NoReturn:
    _reject()


def _b64_encode(raw: bytes | None) -> str | None:
    return base64.b64encode(raw).decode("ascii") if raw is not None else None


def _b64_decode(value: object, *, optional: bool, maximum: int) -> bytes | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or type(value) is not str
        or len(value) > ((maximum + 2) // 3 * 4)
    ):
        _reject()
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise PrivateIntentError from None
    if len(raw) > maximum or _b64_encode(raw) != value:
        _reject()
    return raw


def encode_private_transaction_intent(value: PrivateTransactionIntent) -> bytes:
    """Serialize a validated private intent, without touching the filesystem."""
    if not isinstance(value, PrivateTransactionIntent):
        _reject()
    w = value.witness
    record = {
        "schema": INTENT_SCHEMA,
        "version": INTENT_VERSION,
        "operation": w.operation.value,
        "transaction_id": w.transaction_id,
        "association_before": w.association_before,
        "association_after": w.association_after,
        "registry_revision_before": w.registry_revision_before,
        "registry_revision_after": w.registry_revision_after,
        "descriptor_sha256_before": w.descriptor_sha256_before,
        "descriptor_sha256_after": w.descriptor_sha256_after,
        "registry_sha256_before": w.registry_sha256_before,
        "registry_sha256_after": w.registry_sha256_after,
        "descriptor_before_b64": _b64_encode(value.descriptor_before),
        "descriptor_after_b64": _b64_encode(value.descriptor_after),
        "registry_before_b64": _b64_encode(value.registry_before),
        "registry_after_b64": _b64_encode(value.registry_after),
    }
    encoded = (
        json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_INTENT_BYTES:
        _reject()
    return encoded


def decode_private_transaction_intent(raw: bytes) -> PrivateTransactionIntent:
    """Strictly decode untrusted metadata; never treat it as authorization."""
    if (
        not isinstance(raw, bytes)
        or type(raw) is not bytes
        or len(raw) > MAX_INTENT_BYTES
    ):
        _reject()
    try:
        obj = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, TypeError):
        raise PrivateIntentError from None
    if not isinstance(obj, dict) or set(obj) != _FIELDS:
        _reject()
    if (
        obj["schema"] != INTENT_SCHEMA
        or type(obj["version"]) is not int
        or obj["version"] != INTENT_VERSION
    ):
        _reject()
    try:
        operation = transaction.PrivateBindingOperation(obj["operation"])
        witness = transaction.PrivateTransactionWitness(
            operation=operation,
            transaction_id=obj["transaction_id"],
            association_before=obj["association_before"],
            association_after=obj["association_after"],
            registry_revision_before=obj["registry_revision_before"],
            registry_revision_after=obj["registry_revision_after"],
            descriptor_sha256_before=obj["descriptor_sha256_before"],
            descriptor_sha256_after=obj["descriptor_sha256_after"],
            registry_sha256_before=obj["registry_sha256_before"],
            registry_sha256_after=obj["registry_sha256_after"],
        )
        descriptor_before = _b64_decode(
            obj["descriptor_before_b64"],
            optional=True,
            maximum=metadata.MAX_ASSOCIATION_BYTES,
        )
        descriptor_after = _b64_decode(
            obj["descriptor_after_b64"],
            optional=False,
            maximum=metadata.MAX_ASSOCIATION_BYTES,
        )
        registry_before = _b64_decode(
            obj["registry_before_b64"],
            optional=True,
            maximum=metadata.MAX_REGISTRY_BYTES,
        )
        registry_after = _b64_decode(
            obj["registry_after_b64"],
            optional=False,
            maximum=metadata.MAX_REGISTRY_BYTES,
        )
        if descriptor_after is None or registry_after is None:
            _reject()
        return PrivateTransactionIntent(
            witness,
            descriptor_before,
            descriptor_after,
            registry_before,
            registry_after,
        )
    except (ValueError, KeyError, TypeError, transaction.PrivateTransactionError):
        raise PrivateIntentError from None
