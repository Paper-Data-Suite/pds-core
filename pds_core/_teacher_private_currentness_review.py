"""Locked, non-authorizing binding-currentness recheck for Core #238 Slice 3C7.

Reacquires private registry coordination, rereads both files twice, checks the
native owner twice, then re-evaluates the proposed before-state under that
lock. This is NOT a CAS reservation, cross-tree atomicity, binding approval,
recovery action, Notes service, or authority to mutate either document.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateCurrentnessReviewState(str, Enum):
    RECHECKED_REVIEW_REQUIRED = "rechecked_review_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    INITIALIZATION_ABSENCE_REVIEW = "initialization_absence_review"
    PRIOR_OBSERVATION_UNQUALIFIED = "prior_observation_unqualified"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    CURRENT_OBSERVATION_UNQUALIFIED = "current_observation_unqualified"
    OBSERVATION_STALE = "observation_stale"
    PRECONDITION_REFUSED = "precondition_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateCurrentnessReviewState.RECHECKED_REVIEW_REQUIRED: "Rechecked observations agree; no mutation or binding authorization granted.",
    PrivateCurrentnessReviewState.INVALID_REQUEST: "Invalid private currentness-review request.",
    PrivateCurrentnessReviewState.UNSUPPORTED: "Native currentness review unsupported.",
    PrivateCurrentnessReviewState.INITIALIZATION_ABSENCE_REVIEW: "Initialization requires independent guarded proof of absent metadata.",
    PrivateCurrentnessReviewState.PRIOR_OBSERVATION_UNQUALIFIED: "Prior metadata observation was not qualified for comparison.",
    PrivateCurrentnessReviewState.COORDINATION_UNAVAILABLE: "Private registry lock unavailable or unsafe.",
    PrivateCurrentnessReviewState.OWNER_UNAVAILABLE: "Native owner could not be observed reliably.",
    PrivateCurrentnessReviewState.OWNER_CHANGED: "Effective OS owner differed during the recheck.",
    PrivateCurrentnessReviewState.CURRENT_OBSERVATION_UNQUALIFIED: "Current metadata could not be observed consistently.",
    PrivateCurrentnessReviewState.OBSERVATION_STALE: "Previously observed metadata no longer matches the current observation.",
    PrivateCurrentnessReviewState.PRECONDITION_REFUSED: "The proposed before-state failed guarded comparison.",
    PrivateCurrentnessReviewState.IO_ERROR: "Guarded metadata recheck could not finish reliably.",
}


@dataclass(frozen=True, slots=True)
class PrivateCurrentnessReview:
    """Sanitized advisory classification; never a commit token or write handle."""

    state: PrivateCurrentnessReviewState
    message: str
    precondition_state: preconditions.PrivateBindingPreconditionState | None = field(
        default=None, repr=False
    )


def _result(
    state: PrivateCurrentnessReviewState,
    comparison: preconditions.PrivateBindingPreconditionState | None = None,
) -> PrivateCurrentnessReview:
    return PrivateCurrentnessReview(state, _MESSAGES[state], comparison)


def _exact_prior_match(
    old: paired.PrivatePairObservation, new: paired.PrivatePairObservation
) -> bool:
    """Prior digests/revisions are comparison values, never write authority."""
    return (
        old.state is paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
        and new.state is paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
        and old.registry_revision is not None
        and old.registry_binding_count is not None
        and old.registry_sha256 is not None
        and old.association_id is not None
        and old.descriptor_sha256 is not None
        and old.registry_revision == new.registry_revision
        and old.registry_binding_count == new.registry_binding_count
        and old.registry_sha256 == new.registry_sha256
        and old.association_id == new.association_id
        and old.descriptor_sha256 == new.descriptor_sha256
    )


def review_current_private_binding_preconditions(
    proposed: intents.PrivateTransactionIntent,
    prior: paired.PrivatePairObservation,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateCurrentnessReview:
    """Recheck preconditions *inside* the private registry lock without writes.

    A synced workspace descriptor is not protected by this lock against
    outsiders or cloud changes. No durable cross-tree lock, compare-and-swap,
    verified registry-member lookup or commit authorization is provided.
    A later writer MUST independently retain/requalify native handles and
    redo exact comparisons under its own complete commit lock set.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateCurrentnessReviewState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or type(prior) is not paired.PrivatePairObservation
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_provision._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateCurrentnessReviewState.INVALID_REQUEST)
    if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
        return _result(PrivateCurrentnessReviewState.INITIALIZATION_ABSENCE_REVIEW)
    if prior.state is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED:
        return _result(PrivateCurrentnessReviewState.PRIOR_OBSERVATION_UNQUALIFIED)
    try:
        with locking.hold_existing_private_lock(
            existing_private_root / ".registry.lock"
        ):
            try:
                owner_before = inspection._effective_owner(sys.platform)
                if owner_before.kind not in {"posix_euid", "windows_token_sid"}:
                    return _result(PrivateCurrentnessReviewState.OWNER_UNAVAILABLE)
                first_registry = paired._registry_read(existing_private_root)
                first_descriptor = descriptor.inspect_workspace_descriptor(
                    existing_workspace_root
                )
                second_descriptor = descriptor.inspect_workspace_descriptor(
                    existing_workspace_root
                )
                second_registry = paired._registry_read(existing_private_root)
                owner_after = inspection._effective_owner(sys.platform)
            except inspection._OwnerUnverifiable:
                return _result(PrivateCurrentnessReviewState.OWNER_UNAVAILABLE)
            if owner_before != owner_after:
                return _result(PrivateCurrentnessReviewState.OWNER_CHANGED)
            current = paired._classify(
                first_registry, first_descriptor, second_descriptor, second_registry
            )
            if (
                current.state
                is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
            ):
                return _result(
                    PrivateCurrentnessReviewState.CURRENT_OBSERVATION_UNQUALIFIED
                )
            if not _exact_prior_match(prior, current):
                return _result(PrivateCurrentnessReviewState.OBSERVATION_STALE)
            compared = preconditions.review_binding_preconditions(
                proposed, current, existing_workspace_root, owner_after
            )
            if (
                compared.state
                is not preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
            ):
                return _result(
                    PrivateCurrentnessReviewState.PRECONDITION_REFUSED, compared.state
                )
            return _result(PrivateCurrentnessReviewState.RECHECKED_REVIEW_REQUIRED)
    except locking.PrivateExistingFileLockError:
        return _result(PrivateCurrentnessReviewState.COORDINATION_UNAVAILABLE)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(PrivateCurrentnessReviewState.IO_ERROR)
