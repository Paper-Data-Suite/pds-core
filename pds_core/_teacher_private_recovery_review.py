"""Pure, non-authorizing review of interrupted private-metadata transactions.

Core #238: distinguish an absent document from an unreadable document and
classify exact byte observations against a previously validated intent.
No filesystem access, repair, lock, trust decision, or Notes service occurs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witnesses


class DocumentObservationKind(str, Enum):
    """An inaccessible document is never equivalent to an absent document."""

    ABSENT = "absent"
    PRESENT = "present"
    UNREADABLE = "unreadable"


class PrivateRecoveryReviewState(str, Enum):
    """All results require independent native/lock/currentness review."""

    BEFORE_STATE = "before_state"
    DESCRIPTOR_ONLY = "descriptor_only"
    REGISTRY_ONLY = "registry_only"
    AFTER_STATE_REVIEW_REQUIRED = "after_state_review_required"
    CONFLICT = "conflict"
    CORRUPT_METADATA = "corrupt_metadata"
    ACCESS_UNVERIFIED = "access_unverified"


class PrivateRecoveryReviewError(ValueError):
    """Refuse invalid synthetic observations without disclosing their bytes."""

    def __init__(self) -> None:
        super().__init__("Private recovery review refused: invalid observation.")


@dataclass(frozen=True, slots=True)
class ObservedPrivateDocument:
    """Exact observed bytes or an explicit non-byte observation state.

    This is a testable value model, not a file-opening API or native proof.
    A future guarded reader must never turn an I/O error into ABSENT.
    """

    kind: DocumentObservationKind
    body: bytes | None = field(repr=False, default=None)

    def __post_init__(self) -> None:
        if type(self.kind) is not DocumentObservationKind:
            raise PrivateRecoveryReviewError
        if self.kind is DocumentObservationKind.PRESENT:
            if type(self.body) is not bytes:
                raise PrivateRecoveryReviewError
        elif self.body is not None:
            raise PrivateRecoveryReviewError


_MESSAGES = {
    PrivateRecoveryReviewState.BEFORE_STATE: (
        "Both metadata documents match the reviewed before-state; no replay authorized."
    ),
    PrivateRecoveryReviewState.DESCRIPTOR_ONLY: (
        "Descriptor-only change observed; guarded recovery review required."
    ),
    PrivateRecoveryReviewState.REGISTRY_ONLY: (
        "Registry-only change observed; guarded recovery review required."
    ),
    PrivateRecoveryReviewState.AFTER_STATE_REVIEW_REQUIRED: (
        "Both documents match the proposed after-state; finalization unverified."
    ),
    PrivateRecoveryReviewState.CONFLICT: (
        "Metadata differs from the reviewed transaction; manual review required."
    ),
    PrivateRecoveryReviewState.CORRUPT_METADATA: (
        "Observed metadata is malformed or unsupported; do not overwrite."
    ),
    PrivateRecoveryReviewState.ACCESS_UNVERIFIED: (
        "Metadata was not readable; absence and currentness cannot be established."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryReview:
    """Sanitized non-authorizing review; never a storage handle or READY state."""

    state: PrivateRecoveryReviewState
    message: str


def _result(state: PrivateRecoveryReviewState) -> PrivateRecoveryReview:
    return PrivateRecoveryReview(state=state, message=_MESSAGES[state])


def _bytes_or_absent(
    observation: ObservedPrivateDocument, *, limit: int
) -> bytes | None:
    if type(observation) is not ObservedPrivateDocument:
        raise PrivateRecoveryReviewError
    if observation.kind is DocumentObservationKind.ABSENT:
        return None
    if observation.kind is DocumentObservationKind.UNREADABLE:
        raise PrivateRecoveryReviewError
    body = observation.body
    if type(body) is not bytes:
        raise PrivateRecoveryReviewError
    if len(body) > limit:
        raise metadata.PrivateMetadataError(
            metadata.PrivateMetadataErrorCode.SIZE_LIMIT
        )
    return body


def _digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def review_private_transaction_observation(
    intent: intents.PrivateTransactionIntent,
    *,
    descriptor: ObservedPrivateDocument,
    registry: ObservedPrivateDocument,
) -> PrivateRecoveryReview:
    """Evaluate only an already captured pair of observations, without I/O.

    A caller must separately qualify actual OS account, file handles, locks,
    paths, currentness and crash durability. Even AFTER_STATE is not READY.
    A failed filesystem read must be supplied as UNREADABLE, not ABSENT.
    """
    if type(intent) is not intents.PrivateTransactionIntent:
        raise PrivateRecoveryReviewError
    if (
        type(descriptor) is not ObservedPrivateDocument
        or type(registry) is not ObservedPrivateDocument
    ):
        raise PrivateRecoveryReviewError
    if (
        descriptor.kind is DocumentObservationKind.UNREADABLE
        or registry.kind is DocumentObservationKind.UNREADABLE
    ):
        return _result(PrivateRecoveryReviewState.ACCESS_UNVERIFIED)
    try:
        descriptor_bytes = _bytes_or_absent(
            descriptor, limit=metadata.MAX_ASSOCIATION_BYTES
        )
        registry_bytes = _bytes_or_absent(registry, limit=metadata.MAX_REGISTRY_BYTES)
        # Validate *even unexpected* observed documents; malformed bytes must
        # never be treated as an ordinary stale digest or an empty collection.
        parsed_descriptor = (
            metadata.decode_association_descriptor(descriptor_bytes)
            if descriptor_bytes is not None
            else None
        )
        parsed_registry = (
            metadata.decode_private_registry(registry_bytes)
            if registry_bytes is not None
            else None
        )
    except metadata.PrivateMetadataError:
        return _result(PrivateRecoveryReviewState.CORRUPT_METADATA)
    # A syntactically valid registry with a different owner is a conflicting
    # observation, not evidence that the current OS user is authenticated.
    proposed_owner = metadata.decode_private_registry(intent.registry_after).owner
    if parsed_registry is not None and parsed_registry.owner != proposed_owner:
        return _result(PrivateRecoveryReviewState.CONFLICT)
    # A different but valid descriptor is a conflicting workspace identity.
    expected_ids = {
        value
        for value in (
            intent.witness.association_before,
            intent.witness.association_after,
        )
        if value is not None
    }
    if (
        parsed_descriptor is not None
        and parsed_descriptor.association_id not in expected_ids
    ):
        return _result(PrivateRecoveryReviewState.CONFLICT)
    observation = witnesses.classify_private_transaction_observation(
        intent.witness,
        descriptor_sha256=_digest(descriptor_bytes),
        registry_sha256=_digest(registry_bytes),
    )
    mapping = {
        witnesses.PrivateTransactionObservation.NOT_APPLIED: PrivateRecoveryReviewState.BEFORE_STATE,
        witnesses.PrivateTransactionObservation.DESCRIPTOR_ONLY: PrivateRecoveryReviewState.DESCRIPTOR_ONLY,
        witnesses.PrivateTransactionObservation.REGISTRY_ONLY: PrivateRecoveryReviewState.REGISTRY_ONLY,
        witnesses.PrivateTransactionObservation.BOTH_APPLIED_REVIEW_REQUIRED: PrivateRecoveryReviewState.AFTER_STATE_REVIEW_REQUIRED,
        witnesses.PrivateTransactionObservation.CONFLICT: PrivateRecoveryReviewState.CONFLICT,
    }
    return _result(mapping[observation])
