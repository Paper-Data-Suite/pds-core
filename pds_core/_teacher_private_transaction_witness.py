"""Pure, non-authorizing transaction/recovery witnesses for Core #238.

This private module never reads, writes, locks, authenticates or commits files.
A witness represents a *proposed* transition between hashed metadata states.
Classifying observations is not proof of a completed, secure transaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PrivateBindingOperation(str, Enum):
    """Exact reviewed operations; no implicit change of workspace identity."""

    INITIALIZE = "initialize"
    REBIND_MOVE = "rebind_move"
    FORK_COPY = "fork_copy"


class PrivateTransactionObservation(str, Enum):
    """Read-only comparisons. No outcome authorizes replay or file mutation."""

    NOT_APPLIED = "not_applied"
    DESCRIPTOR_ONLY = "descriptor_only"
    REGISTRY_ONLY = "registry_only"
    BOTH_APPLIED_REVIEW_REQUIRED = "both_applied_review_required"
    CONFLICT = "conflict"


class PrivateTransactionError(ValueError):
    """Reject an invalid witness without echoing private evidence."""

    def __init__(self) -> None:
        super().__init__("Private transaction witness refused: invalid state.")


def _uuid4(value: object) -> bool:
    if type(value) is not str or len(value) != 36:
        return False
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _sha(value: object, *, optional: bool) -> bool:
    return (value is None and optional) or (
        type(value) is str and _SHA256.fullmatch(value) is not None
    )


@dataclass(frozen=True, slots=True)
class PrivateTransactionWitness:
    """Immutable proposed two-document metadata transition; not a commit token.

    The digest fields are evidence of exact bytes *when those bytes have been
    checked by a future guarded caller*. The object does not verify the bytes
    or guard the current filesystem; callers must not accept it as authority.
    """

    operation: PrivateBindingOperation
    transaction_id: str = field(repr=False)
    association_before: str | None = field(repr=False)
    association_after: str = field(repr=False)
    registry_revision_before: int
    registry_revision_after: int
    descriptor_sha256_before: str | None = field(repr=False)
    descriptor_sha256_after: str = field(repr=False)
    registry_sha256_before: str | None = field(repr=False)
    registry_sha256_after: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.operation) is not PrivateBindingOperation:
            raise PrivateTransactionError
        if not _uuid4(self.transaction_id) or not _uuid4(self.association_after):
            raise PrivateTransactionError
        if self.association_before is not None and not _uuid4(self.association_before):
            raise PrivateTransactionError
        if (
            type(self.registry_revision_before) is not int
            or self.registry_revision_before < 0
            or type(self.registry_revision_after) is not int
            or self.registry_revision_after != self.registry_revision_before + 1
        ):
            raise PrivateTransactionError
        if not _sha(self.descriptor_sha256_before, optional=True) or not _sha(
            self.descriptor_sha256_after, optional=False
        ):
            raise PrivateTransactionError
        if not _sha(self.registry_sha256_before, optional=True) or not _sha(
            self.registry_sha256_after, optional=False
        ):
            raise PrivateTransactionError
        if (self.registry_revision_before == 0) != (
            self.registry_sha256_before is None
        ):
            raise PrivateTransactionError
        if self.registry_sha256_before == self.registry_sha256_after:
            raise PrivateTransactionError
        if self.operation is PrivateBindingOperation.INITIALIZE:
            if (
                self.association_before is not None
                or self.descriptor_sha256_before is not None
            ):
                raise PrivateTransactionError
        elif self.operation is PrivateBindingOperation.REBIND_MOVE:
            if (
                self.association_before != self.association_after
                or self.descriptor_sha256_before != self.descriptor_sha256_after
            ):
                raise PrivateTransactionError
        elif self.operation is PrivateBindingOperation.FORK_COPY:
            if (
                self.association_before is None
                or self.association_before == self.association_after
                or self.descriptor_sha256_before is None
                or self.descriptor_sha256_before == self.descriptor_sha256_after
            ):
                raise PrivateTransactionError


def classify_private_transaction_observation(
    witness: PrivateTransactionWitness,
    *,
    descriptor_sha256: str | None,
    registry_sha256: str | None,
) -> PrivateTransactionObservation:
    """Classify observed byte digests without I/O or automatic reconciliation.

    A caller must separately verify owner, permissions, handles, locks,
    revisions and the actual documents. All partially applied or fully
    applied states still require guarded human-reviewed resolution later.
    """
    if not isinstance(witness, PrivateTransactionWitness):
        raise PrivateTransactionError
    if not _sha(descriptor_sha256, optional=True) or not _sha(
        registry_sha256, optional=True
    ):
        raise PrivateTransactionError
    before_descriptor = descriptor_sha256 == witness.descriptor_sha256_before
    after_descriptor = descriptor_sha256 == witness.descriptor_sha256_after
    before_registry = registry_sha256 == witness.registry_sha256_before
    after_registry = registry_sha256 == witness.registry_sha256_after
    if before_descriptor and before_registry:
        return PrivateTransactionObservation.NOT_APPLIED
    if after_descriptor and after_registry:
        return PrivateTransactionObservation.BOTH_APPLIED_REVIEW_REQUIRED
    if after_descriptor and before_registry:
        return PrivateTransactionObservation.DESCRIPTOR_ONLY
    if before_descriptor and after_registry:
        return PrivateTransactionObservation.REGISTRY_ONLY
    return PrivateTransactionObservation.CONFLICT
