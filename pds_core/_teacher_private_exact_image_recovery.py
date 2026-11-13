"""Pure exact-byte interrupted private binding recovery assessment (#238 3E2).

No filesystem reads, writes, locks, admission, replay, or Notes services.
These classifications are non-authorizing; supplying bytes does not prove they
came from a protected/current native file or that absence was verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_transaction_intent as intent


class PrivateExactImageRecoveryState(str, Enum):
    """Content classifications, never safe-to-apply instructions."""

    BEFORE_IMAGES_REVIEW_REQUIRED = "before_images_review_required"
    REGISTRY_ONLY_REVIEW_REQUIRED = "registry_only_review_required"
    DESCRIPTOR_ONLY_REVIEW_REQUIRED = "descriptor_only_review_required"
    AFTER_IMAGES_REVIEW_REQUIRED = "after_images_review_required"
    FOREIGN_IMAGE_REFUSED = "foreign_image_refused"
    OBSERVATION_UNQUALIFIED = "observation_unqualified"
    INTENT_REFUSED = "intent_refused"


_MESSAGES = {
    PrivateExactImageRecoveryState.BEFORE_IMAGES_REVIEW_REQUIRED: "Both metadata images match the proposed before-state; recovery review required.",
    PrivateExactImageRecoveryState.REGISTRY_ONLY_REVIEW_REQUIRED: "Only the registry matches the proposed after-state; recovery review required.",
    PrivateExactImageRecoveryState.DESCRIPTOR_ONLY_REVIEW_REQUIRED: "Only the descriptor matches the proposed after-state; recovery review required.",
    PrivateExactImageRecoveryState.AFTER_IMAGES_REVIEW_REQUIRED: "Both metadata images match the proposed after-state; completion review required.",
    PrivateExactImageRecoveryState.FOREIGN_IMAGE_REFUSED: "At least one metadata image is unrelated to the proposed transition; preserve all existing state.",
    PrivateExactImageRecoveryState.OBSERVATION_UNQUALIFIED: "The supplied metadata observations cannot be evaluated safely.",
    PrivateExactImageRecoveryState.INTENT_REFUSED: "Transaction intent could not be validated canonically.",
}


@dataclass(frozen=True, slots=True)
class PrivateExactImageRecoveryReview:
    """Sanitized outcome; contains no private bytes, identities or paths."""

    state: PrivateExactImageRecoveryState
    message: str


def _result(state: PrivateExactImageRecoveryState) -> PrivateExactImageRecoveryReview:
    return PrivateExactImageRecoveryReview(state, _MESSAGES[state])


def _image(raw: object, maximum: int) -> bool:
    return raw is None or (type(raw) is bytes and len(raw) <= maximum)


def _matches(observed: bytes | None, expected: bytes | None) -> bool:
    """Compare actual bytes, not SHA digests or a caller's declared revision."""
    return observed == expected


def classify_private_exact_image_recovery(
    proposed: intent.PrivateTransactionIntent,
    *,
    observed_registry: bytes | None,
    observed_descriptor: bytes | None,
) -> PrivateExactImageRecoveryReview:
    """Classify exactly observed two-file images against one canonical intent.

    The caller MUST first establish that observed bytes/absence were obtained
    from verified current native file handles while coordination remains held.
    This pure classifier itself cannot establish any of those prerequisites.
    In particular, matching both after-images NEVER permits journal deletion,
    automatic replay, a binding commit, or record access.

    REBIND_MOVE legitimately has identical before/after descriptor bytes. Its
    registry image alone determines before/after content classification; no
    false partial descriptor-write claim is made for this operation.
    """
    if type(proposed) is not intent.PrivateTransactionIntent:
        return _result(PrivateExactImageRecoveryState.INTENT_REFUSED)
    if not _image(observed_registry, metadata.MAX_REGISTRY_BYTES) or not _image(
        observed_descriptor, metadata.MAX_ASSOCIATION_BYTES
    ):
        return _result(PrivateExactImageRecoveryState.OBSERVATION_UNQUALIFIED)
    try:
        # Revalidate the original proposal rather than trusting a dataclass
        # whose frozen fields could have been overwritten through object APIs.
        canonical = intent.encode_private_transaction_intent(proposed)
        checked = intent.decode_private_transaction_intent(canonical)
        if checked != proposed:
            return _result(PrivateExactImageRecoveryState.INTENT_REFUSED)
    except (
        intent.PrivateIntentError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivateExactImageRecoveryState.INTENT_REFUSED)

    before_registry = _matches(observed_registry, checked.registry_before)
    after_registry = _matches(observed_registry, checked.registry_after)
    before_descriptor = _matches(observed_descriptor, checked.descriptor_before)
    after_descriptor = _matches(observed_descriptor, checked.descriptor_after)
    if not (before_registry or after_registry) or not (
        before_descriptor or after_descriptor
    ):
        return _result(PrivateExactImageRecoveryState.FOREIGN_IMAGE_REFUSED)

    # The validated intent forbids equal registry before/after images; however
    # REBIND_MOVE explicitly permits an unchanged descriptor. In that case
    # matching descriptor content is not evidence of a descriptor write.
    if before_registry:
        if before_descriptor:
            return _result(PrivateExactImageRecoveryState.BEFORE_IMAGES_REVIEW_REQUIRED)
        return _result(PrivateExactImageRecoveryState.DESCRIPTOR_ONLY_REVIEW_REQUIRED)
    if after_descriptor:
        return _result(PrivateExactImageRecoveryState.AFTER_IMAGES_REVIEW_REQUIRED)
    return _result(PrivateExactImageRecoveryState.REGISTRY_ONLY_REVIEW_REQUIRED)
