"""Independent native recovery-review convergence fence (Core #238 Slice 3G13).

Combine 3G11 protected checkpoint classification with 3G12 exact-image and
revision evidence; repeat both checks to detect non-convergent observations.
Each underlying review obtains/releases its OWN native guard. The two scopes
are deliberately NOT continuous: a matching result is a retrospective advisory
finding, never CAS, transaction reservation, write authority, replay, durable
commit, journal retirement, or a Notes capability.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_recovery_action_preconditions as steps
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_mutation_boundary as boundary
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness


class PrivateRecoveryConvergenceState(str, Enum):
    PREPARED_REVIEW_CONVERGED_NO_WRITE = "prepared_review_converged_no_write"
    DESCRIPTOR_REVIEW_CONVERGED_NO_WRITE = "descriptor_review_converged_no_write"
    JOURNAL_REVIEW_CONVERGED_NO_WRITE = "journal_review_converged_no_write"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    CHECKPOINT_DISAGREEMENT_PRESERVE = "checkpoint_disagreement_preserve"
    OBSERVATION_CHANGED_PRESERVE = "observation_changed_preserve"
    EVIDENCE_UNQUALIFIED_PRESERVE = "evidence_unqualified_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivateRecoveryConvergenceState.PREPARED_REVIEW_CONVERGED_NO_WRITE: "Independent protected prepared-state reviews converged; no write or replay authority.",
    PrivateRecoveryConvergenceState.DESCRIPTOR_REVIEW_CONVERGED_NO_WRITE: "Independent protected descriptor-pending reviews converged; no completion authority.",
    PrivateRecoveryConvergenceState.JOURNAL_REVIEW_CONVERGED_NO_WRITE: "Independent protected journal-pending reviews converged; no retirement authority.",
    PrivateRecoveryConvergenceState.REVISION_MISMATCH_REFUSED: "Requested registry revision disagrees with the transaction witness.",
    PrivateRecoveryConvergenceState.CHECKPOINT_DISAGREEMENT_PRESERVE: "Independent checkpoint and exact-image reviews disagree; preserve all evidence.",
    PrivateRecoveryConvergenceState.OBSERVATION_CHANGED_PRESERVE: "Recovery review changed across independently guarded observations; preserve evidence.",
    PrivateRecoveryConvergenceState.EVIDENCE_UNQUALIFIED_PRESERVE: "Protected recovery evidence was refused, incomplete or unqualified; preserve artifacts.",
    PrivateRecoveryConvergenceState.INTERRUPTED_PRESERVE: "Native recovery convergence review interrupted; preserve evidence without mutation.",
    PrivateRecoveryConvergenceState.INVALID_REQUEST: "Recovery convergence request invalid.",
    PrivateRecoveryConvergenceState.INITIALIZATION_REFUSED: "First binding requires a separately qualified absence-and-admission protocol.",
    PrivateRecoveryConvergenceState.UNSUPPORTED: "Recovery convergence review unsupported on this platform.",
}


@dataclass(frozen=True, slots=True)
class PrivateRecoveryConvergenceReview:
    """Sanitized retrospective finding, never a write permit or capability."""

    state: PrivateRecoveryConvergenceState
    message: str


def _result(state: PrivateRecoveryConvergenceState) -> PrivateRecoveryConvergenceReview:
    return PrivateRecoveryConvergenceReview(state, _MESSAGES[state])


_EXPECTED = {
    steps.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART: (
        exact.PrivateRecoveryExactRevisionState.PREPARED_EXACT_REVIEW_REQUIRED,
        PrivateRecoveryConvergenceState.PREPARED_REVIEW_CONVERGED_NO_WRITE,
    ),
    steps.PrivateRecoveryProposedStep.REVIEW_DESCRIPTOR_COMPLETION: (
        exact.PrivateRecoveryExactRevisionState.DESCRIPTOR_PENDING_EXACT_REVIEW_REQUIRED,
        PrivateRecoveryConvergenceState.DESCRIPTOR_REVIEW_CONVERGED_NO_WRITE,
    ),
    steps.PrivateRecoveryProposedStep.REVIEW_JOURNAL_RETIREMENT: (
        exact.PrivateRecoveryExactRevisionState.JOURNAL_PENDING_EXACT_REVIEW_REQUIRED,
        PrivateRecoveryConvergenceState.JOURNAL_REVIEW_CONVERGED_NO_WRITE,
    ),
}


def review_private_recovery_convergence_fence(
    requested_step: steps.PrivateRecoveryProposedStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateRecoveryConvergenceReview:
    """Reconcile two independent retained reviews, twice; perform ZERO writes.

    A successful result explicitly means only agreement observed after all
    four separately protected reads. Between calls the native locks are not
    held, so ABA changes, hostile same-user writers, power loss and durable
    completion are NOT excluded. Never use this result to authorize mutation.
    """
    state = PrivateRecoveryConvergenceState
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if (
        type(requested_step) is not steps.PrivateRecoveryProposedStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(state.INVALID_REQUEST)
    try:
        raw = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(state.INVALID_REQUEST)
        if checked.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(state.INITIALIZATION_REFUSED)
        if (
            type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
            or type(checked.descriptor_after) is not bytes
        ):
            return _result(state.INVALID_REQUEST)
        required_revision = (
            checked.witness.registry_revision_before
            if requested_step
            is steps.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART
            else checked.witness.registry_revision_after
        )
        if type(required_revision) is not int or required_revision < 1:
            return _result(state.INVALID_REQUEST)
        if expected_revision != required_revision:
            return _result(state.REVISION_MISMATCH_REFUSED)
    except (
        intents.PrivateIntentError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.INVALID_REQUEST)

    expected_exact, matching_state = _EXPECTED[requested_step]
    retained_matching = (
        boundary.PrivateRecoveryMutationBoundaryState.MATCHING_RETAINED_REVIEW_REQUIRED
    )
    exact_revision_mismatch = (
        exact.PrivateRecoveryExactRevisionState.REVISION_MISMATCH_REFUSED
    )
    prior: (
        tuple[
            boundary.PrivateRecoveryMutationBoundaryState,
            exact.PrivateRecoveryExactRevisionState,
        ]
        | None
    ) = None
    try:
        for _ in range(2):
            coarse = boundary.review_retained_private_recovery_mutation_boundary(
                requested_step, checked, existing_private_root, existing_workspace_root
            )
            if type(coarse) is not boundary.PrivateRecoveryMutationBoundaryReview or (
                type(coarse.state) is not boundary.PrivateRecoveryMutationBoundaryState
            ):
                return _result(state.EVIDENCE_UNQUALIFIED_PRESERVE)
            observed = exact.review_retained_private_recovery_exact_revision(
                requested_step,
                expected_revision,
                checked,
                existing_private_root,
                existing_workspace_root,
            )
            if type(observed) is not exact.PrivateRecoveryExactRevisionReview or (
                type(observed.state) is not exact.PrivateRecoveryExactRevisionState
            ):
                return _result(state.EVIDENCE_UNQUALIFIED_PRESERVE)
            current = (coarse.state, observed.state)
            if prior is not None and current != prior:
                return _result(state.OBSERVATION_CHANGED_PRESERVE)
            if coarse.state is not retained_matching:
                return _result(state.EVIDENCE_UNQUALIFIED_PRESERVE)
            if observed.state is exact_revision_mismatch:
                return _result(state.REVISION_MISMATCH_REFUSED)
            if observed.state is not expected_exact:
                return _result(state.CHECKPOINT_DISAGREEMENT_PRESERVE)
            prior = current
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except (
        OSError,
        PermissionError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.EVIDENCE_UNQUALIFIED_PRESERVE)
    return _result(matching_state)
