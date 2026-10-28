"""Read-only, combined journal/metadata pre-admission review (Core #238 3D2).

One ordered local lock scope brackets TWO native transaction-directory scans and
repeated existing registry/descriptor reads. This is not a durable reservation,
a journal admission grant, binding approval, or a Notes record capability.
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
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_pending_journal_review as pending
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateJournalAdmissionReviewState(str, Enum):
    """Sanitized advisory statuses. No member constitutes write authority."""

    RECHECKED_JOURNAL_FREE_REVIEW_REQUIRED = "rechecked_journal_free_review_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    INITIALIZATION_ABSENCE_REVIEW = "initialization_absence_review"
    PRIOR_UNQUALIFIED = "prior_unqualified"
    COORDINATION_REFUSED = "coordination_refused"
    OWNER_CHANGED = "owner_changed"
    OWNER_UNAVAILABLE = "owner_unavailable"
    PENDING_RECOVERY_REQUIRED = "pending_recovery_required"
    JOURNAL_DIRECTORY_UNQUALIFIED = "journal_directory_unqualified"
    JOURNAL_OBSERVATION_CHANGED = "journal_observation_changed"
    CURRENT_OBSERVATION_UNQUALIFIED = "current_observation_unqualified"
    OBSERVATION_STALE = "observation_stale"
    PRECONDITION_REFUSED = "precondition_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateJournalAdmissionReviewState.RECHECKED_JOURNAL_FREE_REVIEW_REQUIRED: "Local journal and metadata observations agree; no journal admission or binding write authorized.",
    PrivateJournalAdmissionReviewState.INVALID_REQUEST: "Private journal pre-admission request invalid.",
    PrivateJournalAdmissionReviewState.UNSUPPORTED: "Native journal pre-admission review unsupported.",
    PrivateJournalAdmissionReviewState.INITIALIZATION_ABSENCE_REVIEW: "First binding requires separate guarded absence and authorization review.",
    PrivateJournalAdmissionReviewState.PRIOR_UNQUALIFIED: "Prior private metadata observation is not usable.",
    PrivateJournalAdmissionReviewState.COORDINATION_REFUSED: "Local coordination unavailable or unsafe.",
    PrivateJournalAdmissionReviewState.OWNER_CHANGED: "Effective OS owner changed during review.",
    PrivateJournalAdmissionReviewState.OWNER_UNAVAILABLE: "Effective OS owner could not be verified.",
    PrivateJournalAdmissionReviewState.PENDING_RECOVERY_REQUIRED: "Pending private transaction entries require recovery review.",
    PrivateJournalAdmissionReviewState.JOURNAL_DIRECTORY_UNQUALIFIED: "Private transaction directory is missing or unqualified.",
    PrivateJournalAdmissionReviewState.JOURNAL_OBSERVATION_CHANGED: "Transaction directory changed or cannot be observed consistently.",
    PrivateJournalAdmissionReviewState.CURRENT_OBSERVATION_UNQUALIFIED: "Private registry/descriptor observation is inconsistent or unqualified.",
    PrivateJournalAdmissionReviewState.OBSERVATION_STALE: "Prior private metadata no longer matches current state.",
    PrivateJournalAdmissionReviewState.PRECONDITION_REFUSED: "Proposed transaction does not match guarded metadata preconditions.",
    PrivateJournalAdmissionReviewState.IO_ERROR: "Private journal pre-admission review could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateJournalAdmissionReview:
    """No sensitive path, owner, digest, journal content, or commit token."""

    state: PrivateJournalAdmissionReviewState
    message: str


def _result(state: PrivateJournalAdmissionReviewState) -> PrivateJournalAdmissionReview:
    return PrivateJournalAdmissionReview(state, _MESSAGES[state])


def _scan(
    existing_private_root: Path, principal: inspection.EffectiveOSOwner
) -> pending.PrivatePendingJournalState:
    """Reuse the native, fail-closed scanner WITHOUT reacquiring either lock."""
    if type(principal) is not inspection.EffectiveOSOwner:
        return pending.PrivatePendingJournalState.OWNER_UNAVAILABLE
    location = existing_private_root / "transactions"
    if sys.platform == "linux":
        return pending._scan_linux(location, principal)
    if sys.platform == "win32":
        return pending._scan_windows(location, principal)
    return pending.PrivatePendingJournalState.UNSUPPORTED


def _census_refusal(
    state: pending.PrivatePendingJournalState,
) -> PrivateJournalAdmissionReviewState | None:
    if state is pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED:
        return None
    if state is pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED:
        return PrivateJournalAdmissionReviewState.PENDING_RECOVERY_REQUIRED
    if state is pending.PrivatePendingJournalState.CHANGED_DURING_REVIEW:
        return PrivateJournalAdmissionReviewState.JOURNAL_OBSERVATION_CHANGED
    if state is pending.PrivatePendingJournalState.OWNER_CHANGED:
        return PrivateJournalAdmissionReviewState.OWNER_CHANGED
    if state is pending.PrivatePendingJournalState.OWNER_UNAVAILABLE:
        return PrivateJournalAdmissionReviewState.OWNER_UNAVAILABLE
    return PrivateJournalAdmissionReviewState.JOURNAL_DIRECTORY_UNQUALIFIED


def review_private_journal_admission_preconditions(
    proposed: intents.PrivateTransactionIntent,
    prior: paired.PrivatePairObservation,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateJournalAdmissionReview:
    """Advisory double-census + metadata recheck under ONE ordered lock scope.

    This function NEVER creates or admits a journal. It refuses INITIALIZE,
    which needs a separate full absence/owner authorization protocol. Native
    scans are independently read-only, do not retain secure parent handles
    across calls, and cannot establish same-user or cloud-writer exclusion.
    Any future writer must redo each check under native handle continuity,
    verify actual registry membership, enforce durable CAS and teacher consent,
    and reconcile pending intents BEFORE it may attempt protected creation.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateJournalAdmissionReviewState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or type(prior) is not paired.PrivatePairObservation
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_provision._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateJournalAdmissionReviewState.INVALID_REQUEST)
    if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
        return _result(PrivateJournalAdmissionReviewState.INITIALIZATION_ABSENCE_REVIEW)
    if prior.state is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED:
        return _result(PrivateJournalAdmissionReviewState.PRIOR_UNQUALIFIED)

    try:
        with ordered._hold_existing_ordered_coordination(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            initial_journal = _scan(existing_private_root, first_owner)
            issue = _census_refusal(initial_journal)
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

            final_journal = _scan(existing_private_root, first_owner)
            final_owner = ordered._owner()
            if first_owner != final_owner:
                return _result(PrivateJournalAdmissionReviewState.OWNER_CHANGED)
            issue = _census_refusal(final_journal)
            if issue is not None:
                return _result(issue)

            current = paired._classify(
                first_registry, first_descriptor, second_descriptor, second_registry
            )
            if (
                current.state
                is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
            ):
                return _result(
                    PrivateJournalAdmissionReviewState.CURRENT_OBSERVATION_UNQUALIFIED
                )
            if not currentness._exact_prior_match(prior, current):
                return _result(PrivateJournalAdmissionReviewState.OBSERVATION_STALE)
            compared = preconditions.review_binding_preconditions(
                proposed, current, existing_workspace_root, final_owner
            )
            if (
                compared.state
                is not preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
            ):
                return _result(PrivateJournalAdmissionReviewState.PRECONDITION_REFUSED)
            return _result(
                PrivateJournalAdmissionReviewState.RECHECKED_JOURNAL_FREE_REVIEW_REQUIRED
            )
    except ordered.PrivateOrderedCoordinationError as exc:
        if exc.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateJournalAdmissionReviewState.OWNER_CHANGED)
        if exc.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateJournalAdmissionReviewState.OWNER_UNAVAILABLE)
        return _result(PrivateJournalAdmissionReviewState.COORDINATION_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateJournalAdmissionReviewState.IO_ERROR)
