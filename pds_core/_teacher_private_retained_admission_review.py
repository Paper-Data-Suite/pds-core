"""Read-only journal/metadata review within a retained native guard (#238 3D6).

The registry and workspace coordination locks and native transactions-directory
handle remain held throughout both journal censuses and metadata comparisons.
All observations are advisory; neither a matched intent nor an empty journal
is a commit token, journal admission, or authority to write private metadata.
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
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_pending_journal_review as pending
from pds_core import _teacher_private_retained_journal_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRetainedAdmissionState(str, Enum):
    RECHECKED_RETAINED_REVIEW_REQUIRED = "rechecked_retained_review_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    INITIALIZATION_ABSENCE_REVIEW = "initialization_absence_review"
    PRIOR_UNQUALIFIED = "prior_unqualified"
    RETAINED_GUARD_REFUSED = "retained_guard_refused"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    PENDING_RECOVERY_REQUIRED = "pending_recovery_required"
    JOURNAL_DIRECTORY_UNQUALIFIED = "journal_directory_unqualified"
    JOURNAL_OBSERVATION_CHANGED = "journal_observation_changed"
    CURRENT_OBSERVATION_UNQUALIFIED = "current_observation_unqualified"
    OBSERVATION_STALE = "observation_stale"
    PRECONDITION_REFUSED = "precondition_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateRetainedAdmissionState.RECHECKED_RETAINED_REVIEW_REQUIRED: "Local retained-handle and metadata observations agree; no write authorized.",
    PrivateRetainedAdmissionState.INVALID_REQUEST: "Invalid retained private pre-admission request.",
    PrivateRetainedAdmissionState.UNSUPPORTED: "Retained private pre-admission review unsupported.",
    PrivateRetainedAdmissionState.INITIALIZATION_ABSENCE_REVIEW: "Initialization needs separate guarded absence verification and review.",
    PrivateRetainedAdmissionState.PRIOR_UNQUALIFIED: "Earlier private metadata observation is unqualified.",
    PrivateRetainedAdmissionState.RETAINED_GUARD_REFUSED: "Native retained journal guard could not be established or maintained.",
    PrivateRetainedAdmissionState.OWNER_UNAVAILABLE: "Effective OS owner is unqualified.",
    PrivateRetainedAdmissionState.OWNER_CHANGED: "Effective OS owner changed during review.",
    PrivateRetainedAdmissionState.PENDING_RECOVERY_REQUIRED: "Existing journal entries require recovery review.",
    PrivateRetainedAdmissionState.JOURNAL_DIRECTORY_UNQUALIFIED: "Transaction directory census is unqualified.",
    PrivateRetainedAdmissionState.JOURNAL_OBSERVATION_CHANGED: "Transaction directory census changed during review.",
    PrivateRetainedAdmissionState.CURRENT_OBSERVATION_UNQUALIFIED: "Current private metadata observations are unqualified.",
    PrivateRetainedAdmissionState.OBSERVATION_STALE: "Current private metadata differs from the earlier observation.",
    PrivateRetainedAdmissionState.PRECONDITION_REFUSED: "Proposed private binding preconditions do not match.",
    PrivateRetainedAdmissionState.IO_ERROR: "Retained private pre-admission review could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateRetainedAdmissionReview:
    """Sanitized advisory result; no path, owner, file ID, or capability."""

    state: PrivateRetainedAdmissionState
    message: str


def _result(state: PrivateRetainedAdmissionState) -> PrivateRetainedAdmissionReview:
    return PrivateRetainedAdmissionReview(state, _MESSAGES[state])


def _census(
    directory: Path, owner: inspection.EffectiveOSOwner
) -> pending.PrivatePendingJournalState:
    """Call a lock-free internal reader; never recursively acquire locks."""
    if sys.platform == "linux":
        return pending._scan_linux(directory, owner)
    if sys.platform == "win32":
        return pending._scan_windows(directory, owner)
    return pending.PrivatePendingJournalState.UNSUPPORTED


def _census_refusal(
    state: pending.PrivatePendingJournalState,
) -> PrivateRetainedAdmissionState | None:
    if state is pending.PrivatePendingJournalState.EMPTY_REVIEW_REQUIRED:
        return None
    if state is pending.PrivatePendingJournalState.PENDING_REVIEW_REQUIRED:
        return PrivateRetainedAdmissionState.PENDING_RECOVERY_REQUIRED
    if state is pending.PrivatePendingJournalState.CHANGED_DURING_REVIEW:
        return PrivateRetainedAdmissionState.JOURNAL_OBSERVATION_CHANGED
    if state is pending.PrivatePendingJournalState.OWNER_CHANGED:
        return PrivateRetainedAdmissionState.OWNER_CHANGED
    if state is pending.PrivatePendingJournalState.OWNER_UNAVAILABLE:
        return PrivateRetainedAdmissionState.OWNER_UNAVAILABLE
    return PrivateRetainedAdmissionState.JOURNAL_DIRECTORY_UNQUALIFIED


def _guard_refusal(
    code: retained.RetainedJournalGuardCode,
) -> PrivateRetainedAdmissionState:
    if code is retained.RetainedJournalGuardCode.OWNER_CHANGED:
        return PrivateRetainedAdmissionState.OWNER_CHANGED
    if code is retained.RetainedJournalGuardCode.OWNER_UNAVAILABLE:
        return PrivateRetainedAdmissionState.OWNER_UNAVAILABLE
    if code is retained.RetainedJournalGuardCode.UNSUPPORTED:
        return PrivateRetainedAdmissionState.UNSUPPORTED
    return PrivateRetainedAdmissionState.RETAINED_GUARD_REFUSED


def review_retained_private_journal_preconditions(
    proposed: intents.PrivateTransactionIntent,
    prior: paired.PrivatePairObservation,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRetainedAdmissionReview:
    """Double census and exact prior comparison inside one retained local scope.

    No nested lock acquisition; registry coordination is already held by the
    retained guard. No intent is written, no CAS is reserved, and no private
    binding/Notes scope is approved. Directory ancestry, synced workspace
    participants, and later write-handle continuity remain unqualified.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateRetainedAdmissionState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or type(prior) is not paired.PrivatePairObservation
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateRetainedAdmissionState.INVALID_REQUEST)
    if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
        return _result(PrivateRetainedAdmissionState.INITIALIZATION_ABSENCE_REVIEW)
    if prior.state is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED:
        return _result(PrivateRetainedAdmissionState.PRIOR_UNQUALIFIED)

    try:
        with retained._hold_existing_retained_journal_guard(
            existing_private_root, existing_workspace_root
        ):
            first_owner = ordered._owner()
            directory = existing_private_root / "transactions"
            first_census = _census(directory, first_owner)
            refusal = _census_refusal(first_census)
            if refusal is not None:
                return _result(refusal)
            first_registry = paired._registry_read(existing_private_root)
            first_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_registry = paired._registry_read(existing_private_root)
            second_census = _census(directory, first_owner)
            refusal = _census_refusal(second_census)
            if refusal is not None:
                return _result(refusal)
            second_owner = ordered._owner()
            if first_owner != second_owner:
                return _result(PrivateRetainedAdmissionState.OWNER_CHANGED)
            current = paired._classify(
                first_registry, first_descriptor, second_descriptor, second_registry
            )
            if (
                current.state
                is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
            ):
                return _result(
                    PrivateRetainedAdmissionState.CURRENT_OBSERVATION_UNQUALIFIED
                )
            if not currentness._exact_prior_match(prior, current):
                return _result(PrivateRetainedAdmissionState.OBSERVATION_STALE)
            matched = preconditions.review_binding_preconditions(
                proposed, current, existing_workspace_root, second_owner
            )
            if (
                matched.state
                is not preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
            ):
                return _result(PrivateRetainedAdmissionState.PRECONDITION_REFUSED)
            return _result(
                PrivateRetainedAdmissionState.RECHECKED_RETAINED_REVIEW_REQUIRED
            )
    except retained.RetainedJournalGuardError as error:
        return _result(_guard_refusal(error.code))
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            return _result(PrivateRetainedAdmissionState.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            return _result(PrivateRetainedAdmissionState.OWNER_UNAVAILABLE)
        return _result(PrivateRetainedAdmissionState.RETAINED_GUARD_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateRetainedAdmissionState.IO_ERROR)
