"""Combined, non-authorizing native-anchor/journal/metadata review (#238 3D4).

One ordered local lock scope brackets two independently verified native journal
anchor checks, double pending-entry scans, and paired registry/descriptor reads.
Even a fully matching result is NOT journal admission, native handle retention,
a durable CAS/commit reservation, cross-device coordination, or Notes storage.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_currentness_review as currentness
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_admission_review as admission
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateNativeAdmissionReviewState(str, Enum):
    """Sanitized local advisory classifications; no write-capable status."""

    RECHECKED_NATIVE_ANCHOR_REVIEW_REQUIRED = "rechecked_native_anchor_review_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    INITIALIZATION_ABSENCE_REVIEW = "initialization_absence_review"
    PRIOR_UNQUALIFIED = "prior_unqualified"
    COORDINATION_REFUSED = "coordination_refused"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    NATIVE_ANCHOR_UNQUALIFIED = "native_anchor_unqualified"
    NATIVE_ANCHOR_CHANGED = "native_anchor_changed"
    PENDING_RECOVERY_REQUIRED = "pending_recovery_required"
    JOURNAL_DIRECTORY_UNQUALIFIED = "journal_directory_unqualified"
    JOURNAL_OBSERVATION_CHANGED = "journal_observation_changed"
    CURRENT_OBSERVATION_UNQUALIFIED = "current_observation_unqualified"
    OBSERVATION_STALE = "observation_stale"
    PRECONDITION_REFUSED = "precondition_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateNativeAdmissionReviewState.RECHECKED_NATIVE_ANCHOR_REVIEW_REQUIRED: "Local native anchor, journal and metadata observations agreed; no write authorized.",
    PrivateNativeAdmissionReviewState.INVALID_REQUEST: "Invalid native journal pre-admission request.",
    PrivateNativeAdmissionReviewState.UNSUPPORTED: "Native pre-admission review unsupported.",
    PrivateNativeAdmissionReviewState.INITIALIZATION_ABSENCE_REVIEW: "Initialization requires separate guarded absence and teacher review.",
    PrivateNativeAdmissionReviewState.PRIOR_UNQUALIFIED: "Earlier metadata evidence cannot be rechecked.",
    PrivateNativeAdmissionReviewState.COORDINATION_REFUSED: "Ordered local coordination unavailable.",
    PrivateNativeAdmissionReviewState.OWNER_UNAVAILABLE: "Effective OS owner unavailable.",
    PrivateNativeAdmissionReviewState.OWNER_CHANGED: "Effective OS owner changed during review.",
    PrivateNativeAdmissionReviewState.NATIVE_ANCHOR_UNQUALIFIED: "Native journal directory identity or protection unqualified.",
    PrivateNativeAdmissionReviewState.NATIVE_ANCHOR_CHANGED: "Native journal directory identity changed during a probe.",
    PrivateNativeAdmissionReviewState.PENDING_RECOVERY_REQUIRED: "Existing transaction entries require recovery review.",
    PrivateNativeAdmissionReviewState.JOURNAL_DIRECTORY_UNQUALIFIED: "Transaction directory census unqualified.",
    PrivateNativeAdmissionReviewState.JOURNAL_OBSERVATION_CHANGED: "Transaction directory census changed during review.",
    PrivateNativeAdmissionReviewState.CURRENT_OBSERVATION_UNQUALIFIED: "Private metadata observations are unqualified.",
    PrivateNativeAdmissionReviewState.OBSERVATION_STALE: "Prior metadata differs from current observation.",
    PrivateNativeAdmissionReviewState.PRECONDITION_REFUSED: "Proposed transaction preconditions were not matched.",
    PrivateNativeAdmissionReviewState.IO_ERROR: "Native journal pre-admission review could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateNativeAdmissionReview:
    """No path, owner, journal content, identity tuple, handle or commit token."""

    state: PrivateNativeAdmissionReviewState
    message: str


def _result(state: PrivateNativeAdmissionReviewState) -> PrivateNativeAdmissionReview:
    return PrivateNativeAdmissionReview(state, _MESSAGES[state])


def _probe(
    existing_private_root: Path, owner: inspection.EffectiveOSOwner
) -> anchor.PrivateJournalAnchorState:
    """Native probe *without* recursively acquiring the two locks."""
    if type(owner) is not inspection.EffectiveOSOwner:
        return anchor.PrivateJournalAnchorState.OWNER_UNAVAILABLE
    directory = existing_private_root / "transactions"
    if sys.platform == "linux":
        return anchor._linux_anchor(directory, owner)
    if sys.platform == "win32":
        return anchor._windows_anchor(directory, owner)
    return anchor.PrivateJournalAnchorState.UNSUPPORTED


def _anchor_refusal(
    state: anchor.PrivateJournalAnchorState,
) -> PrivateNativeAdmissionReviewState | None:
    if state is anchor.PrivateJournalAnchorState.IDENTITY_OBSERVED_UNQUALIFIED:
        return None
    if state is anchor.PrivateJournalAnchorState.CHANGED_DURING_REVIEW:
        return PrivateNativeAdmissionReviewState.NATIVE_ANCHOR_CHANGED
    if state is anchor.PrivateJournalAnchorState.OWNER_CHANGED:
        return PrivateNativeAdmissionReviewState.OWNER_CHANGED
    if state is anchor.PrivateJournalAnchorState.OWNER_UNAVAILABLE:
        return PrivateNativeAdmissionReviewState.OWNER_UNAVAILABLE
    return PrivateNativeAdmissionReviewState.NATIVE_ANCHOR_UNQUALIFIED


def _census_refusal(
    state: admission.PrivateJournalAdmissionReviewState | None,
) -> PrivateNativeAdmissionReviewState | None:
    if state is None:
        return None
    if state is admission.PrivateJournalAdmissionReviewState.PENDING_RECOVERY_REQUIRED:
        return PrivateNativeAdmissionReviewState.PENDING_RECOVERY_REQUIRED
    if (
        state
        is admission.PrivateJournalAdmissionReviewState.JOURNAL_OBSERVATION_CHANGED
    ):
        return PrivateNativeAdmissionReviewState.JOURNAL_OBSERVATION_CHANGED
    if state is admission.PrivateJournalAdmissionReviewState.OWNER_CHANGED:
        return PrivateNativeAdmissionReviewState.OWNER_CHANGED
    if state is admission.PrivateJournalAdmissionReviewState.OWNER_UNAVAILABLE:
        return PrivateNativeAdmissionReviewState.OWNER_UNAVAILABLE
    return PrivateNativeAdmissionReviewState.JOURNAL_DIRECTORY_UNQUALIFIED


def review_native_anchored_private_journal_preconditions(
    proposed: intents.PrivateTransactionIntent,
    prior: paired.PrivatePairObservation,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateNativeAdmissionReview:
    """Read-only composite review while both local coordination locks are held.

    Each native probe retains handles only *during that individual probe*.
    Different successful probes do not establish the SAME directory identity
    across probes. This function never exposes an authority handle; writers
    MUST retain qualified native handles across the entire guarded operation,
    recheck exact-before CAS, journal and recovery state, and explicit consent.
    A cloud-synced workspace is not serialized across devices by these locks.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateNativeAdmissionReviewState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or type(prior) is not paired.PrivatePairObservation
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateNativeAdmissionReviewState.INVALID_REQUEST)
    if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
        return _result(PrivateNativeAdmissionReviewState.INITIALIZATION_ABSENCE_REVIEW)
    if prior.state is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED:
        return _result(PrivateNativeAdmissionReviewState.PRIOR_UNQUALIFIED)

    try:
        with ordered._hold_existing_ordered_coordination(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            issue = _anchor_refusal(_probe(existing_private_root, first_owner))
            if issue is not None:
                return _result(issue)
            issue = _census_refusal(
                admission._census_refusal(
                    admission._scan(existing_private_root, first_owner)
                )
            )
            if issue is not None:
                return _result(issue)

            first_registry = paired._registry_read(existing_private_root)
            first_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_registry = paired._registry_read(existing_private_root)

            issue = _census_refusal(
                admission._census_refusal(
                    admission._scan(existing_private_root, first_owner)
                )
            )
            if issue is not None:
                return _result(issue)
            issue = _anchor_refusal(_probe(existing_private_root, first_owner))
            if issue is not None:
                return _result(issue)
            last_owner = ordered._owner()
            if first_owner != last_owner:
                return _result(PrivateNativeAdmissionReviewState.OWNER_CHANGED)
            current = paired._classify(
                first_registry, first_descriptor, second_descriptor, second_registry
            )
            if (
                current.state
                is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
            ):
                return _result(
                    PrivateNativeAdmissionReviewState.CURRENT_OBSERVATION_UNQUALIFIED
                )
            if not currentness._exact_prior_match(prior, current):
                return _result(PrivateNativeAdmissionReviewState.OBSERVATION_STALE)
            comparison = preconditions.review_binding_preconditions(
                proposed, current, existing_workspace_root, last_owner
            )
            if (
                comparison.state
                is not preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
            ):
                return _result(PrivateNativeAdmissionReviewState.PRECONDITION_REFUSED)
            return _result(
                PrivateNativeAdmissionReviewState.RECHECKED_NATIVE_ANCHOR_REVIEW_REQUIRED
            )
    except ordered.PrivateOrderedCoordinationError as exc:
        if exc.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateNativeAdmissionReviewState.OWNER_CHANGED)
        if exc.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateNativeAdmissionReviewState.OWNER_UNAVAILABLE)
        return _result(PrivateNativeAdmissionReviewState.COORDINATION_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateNativeAdmissionReviewState.IO_ERROR)
