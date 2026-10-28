"""Two-lock local precondition recheck without mutation (Core #238 Slice 3D0).

Recheck existing registry and potentially synced descriptor while holding the
ordered registry/workspace guards. A result is advisory only: the two locks
cannot establish cross-device serialization, native path continuity, durable
CAS, reviewed human consent or authority to stage/apply a transaction.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_currentness_review as currentness
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateOrderedReviewState(str, Enum):
    RECHECKED_REVIEW_REQUIRED = "rechecked_review_required"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    INITIALIZATION_ABSENCE_REVIEW = "initialization_absence_review"
    PRIOR_UNQUALIFIED = "prior_unqualified"
    COORDINATION_REFUSED = "coordination_refused"
    OWNER_CHANGED = "owner_changed"
    OWNER_UNAVAILABLE = "owner_unavailable"
    CURRENT_OBSERVATION_UNQUALIFIED = "current_observation_unqualified"
    OBSERVATION_STALE = "observation_stale"
    PRECONDITION_REFUSED = "precondition_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateOrderedReviewState.RECHECKED_REVIEW_REQUIRED: "Local ordered recheck agrees; no journal or binding write authorized.",
    PrivateOrderedReviewState.INVALID_REQUEST: "Invalid ordered review request.",
    PrivateOrderedReviewState.UNSUPPORTED: "Ordered review unsupported.",
    PrivateOrderedReviewState.INITIALIZATION_ABSENCE_REVIEW: "Initialization needs a separate guarded absence review.",
    PrivateOrderedReviewState.PRIOR_UNQUALIFIED: "Prior private metadata was not qualified for recheck.",
    PrivateOrderedReviewState.COORDINATION_REFUSED: "Existing local coordination could not be acquired or verified.",
    PrivateOrderedReviewState.OWNER_CHANGED: "Effective OS principal changed during review.",
    PrivateOrderedReviewState.OWNER_UNAVAILABLE: "Effective OS principal cannot be reverified.",
    PrivateOrderedReviewState.CURRENT_OBSERVATION_UNQUALIFIED: "Current private documents cannot be consistently observed.",
    PrivateOrderedReviewState.OBSERVATION_STALE: "Current private metadata differs from the earlier observation.",
    PrivateOrderedReviewState.PRECONDITION_REFUSED: "Reviewed proposal does not match current private metadata.",
    PrivateOrderedReviewState.IO_ERROR: "Ordered private metadata review could not complete safely.",
}


@dataclass(frozen=True, slots=True)
class PrivateOrderedReview:
    """Sanitized advisory result; no owner, UUID, path, handle or write token."""

    state: PrivateOrderedReviewState
    message: str
    precondition_state: preconditions.PrivateBindingPreconditionState | None = field(
        default=None, repr=False
    )


def _result(
    state: PrivateOrderedReviewState,
    comparison: preconditions.PrivateBindingPreconditionState | None = None,
) -> PrivateOrderedReview:
    return PrivateOrderedReview(state, _MESSAGES[state], comparison)


def review_ordered_private_binding_preconditions(
    proposed: intents.PrivateTransactionIntent,
    prior: paired.PrivatePairObservation,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateOrderedReview:
    """Perform the *local* two-lock precondition review without any writes.

    The registry lock MUST be acquired first, workspace lock second. Never
    recursively reacquire registry coordination through the public snapshot
    helper. The lower-level readers still observe paths rather than retain a
    secure native parent/file handle chain; this function therefore can never
    authorize an intent journal, sidecar, registry, or Notes write.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivateOrderedReviewState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or type(prior) is not paired.PrivatePairObservation
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_provision._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivateOrderedReviewState.INVALID_REQUEST)
    if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
        return _result(PrivateOrderedReviewState.INITIALIZATION_ABSENCE_REVIEW)
    if prior.state is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED:
        return _result(PrivateOrderedReviewState.PRIOR_UNQUALIFIED)

    try:
        with ordered._hold_existing_ordered_coordination(
            existing_private_root, existing_workspace_root
        ):
            owner_first = ordered._owner()
            first_registry = paired._registry_read(existing_private_root)
            first_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_registry = paired._registry_read(existing_private_root)
            owner_second = ordered._owner()
            if owner_first != owner_second:
                return _result(PrivateOrderedReviewState.OWNER_CHANGED)
            current = paired._classify(
                first_registry, first_descriptor, second_descriptor, second_registry
            )
            if (
                current.state
                is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
            ):
                return _result(
                    PrivateOrderedReviewState.CURRENT_OBSERVATION_UNQUALIFIED
                )
            if not currentness._exact_prior_match(prior, current):
                return _result(PrivateOrderedReviewState.OBSERVATION_STALE)
            compared = preconditions.review_binding_preconditions(
                proposed, current, existing_workspace_root, owner_second
            )
            if (
                compared.state
                is not preconditions.PrivateBindingPreconditionState.MATCHED_REVIEW_REQUIRED
            ):
                return _result(
                    PrivateOrderedReviewState.PRECONDITION_REFUSED, compared.state
                )
            return _result(PrivateOrderedReviewState.RECHECKED_REVIEW_REQUIRED)
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code in {
            ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED,
            ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE,
        }:
            state = (
                PrivateOrderedReviewState.OWNER_CHANGED
                if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED
                else PrivateOrderedReviewState.OWNER_UNAVAILABLE
            )
            return _result(state)
        return _result(PrivateOrderedReviewState.COORDINATION_REFUSED)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        return _result(PrivateOrderedReviewState.IO_ERROR)
