"""Pure, non-authorizing private transaction journal crash checkpoint (#238 3E3).

Classify a *supplied* exact journal image alongside two observed metadata images.
This code cannot attest that observations came from protected native handles, that
journal bytes were durably flushed, or that a filesystem operation is authorized.
No filesystem I/O, cleanup, replay, mutation, or Notes service occurs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pds_core import _teacher_private_exact_image_recovery as recovery
from pds_core import _teacher_private_transaction_intent as intents


class PrivateJournalCrashCheckpointState(str, Enum):
    """Sanitized recovery observations; none grants permission to write."""

    NO_JOURNAL_BEFORE_REVIEW_REQUIRED = "no_journal_before_review_required"
    JOURNAL_BEFORE_REVIEW_REQUIRED = "journal_before_review_required"
    JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED = "journal_descriptor_only_review_required"
    JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED = "journal_registry_only_review_required"
    JOURNAL_AFTER_REVIEW_REQUIRED = "journal_after_review_required"
    UNJOURNALED_PARTIAL_REFUSED = "unjournaled_partial_refused"
    UNJOURNALED_AFTER_REFUSED = "unjournaled_after_refused"
    JOURNAL_IMAGE_REFUSED = "journal_image_refused"
    FOREIGN_METADATA_REFUSED = "foreign_metadata_refused"
    OBSERVATION_UNQUALIFIED = "observation_unqualified"
    INTENT_REFUSED = "intent_refused"


_MESSAGES = {
    PrivateJournalCrashCheckpointState.NO_JOURNAL_BEFORE_REVIEW_REQUIRED: "No journal image supplied and metadata matches before-state; independent review required.",
    PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED: "Journal image matches the intent and metadata matches before-state; recovery review required.",
    PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED: "Journal image matches but only descriptor after-state was observed; recovery review required.",
    PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED: "Journal image matches but only registry after-state was observed; recovery review required.",
    PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED: "Journal image and both after-images match; completion review required.",
    PrivateJournalCrashCheckpointState.UNJOURNALED_PARTIAL_REFUSED: "Partial metadata transition without an observed journal image is refused.",
    PrivateJournalCrashCheckpointState.UNJOURNALED_AFTER_REFUSED: "After-state without an observed journal image is refused.",
    PrivateJournalCrashCheckpointState.JOURNAL_IMAGE_REFUSED: "The supplied journal image is invalid or not the canonical proposed intent.",
    PrivateJournalCrashCheckpointState.FOREIGN_METADATA_REFUSED: "Observed metadata is unrelated to the proposed transaction; preserve existing state.",
    PrivateJournalCrashCheckpointState.OBSERVATION_UNQUALIFIED: "Metadata or journal image observations are unqualified.",
    PrivateJournalCrashCheckpointState.INTENT_REFUSED: "Proposed transaction intent is not canonical and valid.",
}


@dataclass(frozen=True, slots=True)
class PrivateJournalCrashCheckpointReview:
    """No bytes, owner, transaction ID, path, native handle, or commit token."""

    state: PrivateJournalCrashCheckpointState
    message: str


def _result(
    state: PrivateJournalCrashCheckpointState,
) -> PrivateJournalCrashCheckpointReview:
    return PrivateJournalCrashCheckpointReview(state, _MESSAGES[state])


def classify_private_journal_crash_checkpoint(
    proposed: intents.PrivateTransactionIntent,
    *,
    observed_journal: bytes | None,
    observed_registry: bytes | None,
    observed_descriptor: bytes | None,
) -> PrivateJournalCrashCheckpointReview:
    """Classify a supplied exact journal image and supplied metadata images.

    Required upstream evidence (NOT established here): ordered local locks,
    effective OS owner, retained native identity/protection, qualified local
    journal backing, exact reads and absence checks, and flush durability.
    A successful classification is not journal admission, recovery permission,
    a CAS reservation, approval to retire a journal, or binding authority.

    A rebind can have identical before/after descriptor bytes. This classifier
    delegates image matching to Slice 3E2, which correctly treats that case
    as before/after registry status rather than a phantom partial write.
    """
    if type(proposed) is not intents.PrivateTransactionIntent:
        return _result(PrivateJournalCrashCheckpointState.INTENT_REFUSED)
    try:
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
        ):
            return _result(PrivateJournalCrashCheckpointState.INTENT_REFUSED)
    except (
        intents.PrivateIntentError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivateJournalCrashCheckpointState.INTENT_REFUSED)

    if observed_journal is not None and (
        type(observed_journal) is not bytes
        or len(observed_journal) > intents.MAX_INTENT_BYTES
    ):
        return _result(PrivateJournalCrashCheckpointState.OBSERVATION_UNQUALIFIED)
    if observed_journal is not None and observed_journal != canonical:
        return _result(PrivateJournalCrashCheckpointState.JOURNAL_IMAGE_REFUSED)

    images = recovery.classify_private_exact_image_recovery(
        checked,
        observed_registry=observed_registry,
        observed_descriptor=observed_descriptor,
    ).state
    if images is recovery.PrivateExactImageRecoveryState.INTENT_REFUSED:
        return _result(PrivateJournalCrashCheckpointState.INTENT_REFUSED)
    if images is recovery.PrivateExactImageRecoveryState.OBSERVATION_UNQUALIFIED:
        return _result(PrivateJournalCrashCheckpointState.OBSERVATION_UNQUALIFIED)
    if images is recovery.PrivateExactImageRecoveryState.FOREIGN_IMAGE_REFUSED:
        return _result(PrivateJournalCrashCheckpointState.FOREIGN_METADATA_REFUSED)

    if observed_journal is None:
        if (
            images
            is recovery.PrivateExactImageRecoveryState.BEFORE_IMAGES_REVIEW_REQUIRED
        ):
            return _result(
                PrivateJournalCrashCheckpointState.NO_JOURNAL_BEFORE_REVIEW_REQUIRED
            )
        if (
            images
            is recovery.PrivateExactImageRecoveryState.AFTER_IMAGES_REVIEW_REQUIRED
        ):
            return _result(PrivateJournalCrashCheckpointState.UNJOURNALED_AFTER_REFUSED)
        return _result(PrivateJournalCrashCheckpointState.UNJOURNALED_PARTIAL_REFUSED)

    if images is recovery.PrivateExactImageRecoveryState.BEFORE_IMAGES_REVIEW_REQUIRED:
        return _result(
            PrivateJournalCrashCheckpointState.JOURNAL_BEFORE_REVIEW_REQUIRED
        )
    if (
        images
        is recovery.PrivateExactImageRecoveryState.DESCRIPTOR_ONLY_REVIEW_REQUIRED
    ):
        return _result(
            PrivateJournalCrashCheckpointState.JOURNAL_DESCRIPTOR_ONLY_REVIEW_REQUIRED
        )
    if images is recovery.PrivateExactImageRecoveryState.REGISTRY_ONLY_REVIEW_REQUIRED:
        return _result(
            PrivateJournalCrashCheckpointState.JOURNAL_REGISTRY_ONLY_REVIEW_REQUIRED
        )
    return _result(PrivateJournalCrashCheckpointState.JOURNAL_AFTER_REVIEW_REQUIRED)
