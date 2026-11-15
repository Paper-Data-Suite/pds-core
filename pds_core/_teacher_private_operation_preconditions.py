"""Non-authorizing, operation-boundary precondition inventory (#238 3G82).

This parameterless review couples the existing read-only current-owner/root
observation, retained-native-custody observation, canonical intent description,
and permanent production write barrier. It compares an initial and final
private-root observation to refuse obvious drift, but does NOT hold a production
lock across either observation, revalidate descriptor/journal/registry paths,
or authorize any writes. A future guarded *operation* must establish those
requirements itself. No caller paths, SID/UID assertions, guards, booleans,
callbacks, intents or decision tokens are accepted or returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_retained_root_custody as custody


class PrivateOperationPreconditionState(str, Enum):
    PRODUCTION_BLOCKED = "production_blocked"
    REQUIREMENT_DRIFT_BLOCKED = "requirement_drift_blocked"
    OBSERVATION_REFUSED_BLOCKED = "observation_refused_blocked"
    ROOT_CHANGED_BLOCKED = "root_changed_blocked"
    CANONICAL_DESCRIPTION_REFUSED_BLOCKED = "canonical_description_refused_blocked"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateOperationPreconditionReview:
    state: PrivateOperationPreconditionState
    retained_root_observation: str
    root_observation: str
    owner_observed: bool
    unqualified_requirements: tuple[str, ...] = field(repr=False)
    root_rechecked_in_review: bool = False
    canonical_intent_description_checked: bool = False
    operation_owned_guard_qualified: bool = False
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    transaction_commit_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateOperationPreconditionReview(non_authorizing=True)"


def _result(
    state: PrivateOperationPreconditionState,
    *,
    root: str = "unavailable",
    retained: str = "unavailable",
    owner_seen: bool = False,
    rechecked: bool = False,
    description: bool = False,
) -> PrivateOperationPreconditionReview:
    return PrivateOperationPreconditionReview(
        state=state,
        retained_root_observation=retained,
        root_observation=root,
        owner_observed=owner_seen,
        unqualified_requirements=readiness._REQUIRED,
        root_rechecked_in_review=rechecked,
        canonical_intent_description_checked=description,
    )


def review_private_operation_preconditions() -> PrivateOperationPreconditionReview:
    """Review the CURRENT operation boundary, with no caller authority.

    Consecutive read-only checks are not a continuously held native guard.
    Even if every native observation succeeds, all nine production requirements
    remain unqualified, and every returned state is an explicit refusal.
    """
    state = PrivateOperationPreconditionState
    if (
        tuple(item.value for item in barrier._REQUIRED) != readiness._REQUIRED
        or len(readiness._REQUIRED) != 9
    ):
        return _result(state.REQUIREMENT_DRIFT_BLOCKED)
    try:
        first = inspection.inspect_private_root()
        if (
            type(first) is not inspection.PrivateRootInspection
            or type(first.state) is not inspection.PrivateRootState
        ):
            return _result(state.OBSERVATION_REFUSED_BLOCKED)
        root = first.state.value
        owner_seen = type(first.owner) is inspection.EffectiveOSOwner
        current = readiness.review_private_production_readiness()
        if (
            type(current) is not readiness.PrivateProductionReadinessReview
            or current.unqualified_requirements != readiness._REQUIRED
            or current.state
            not in {
                readiness.PrivateProductionReadinessState.PRODUCTION_BLOCKED,
                readiness.PrivateProductionReadinessState.PROBE_REFUSED_PRODUCTION_BLOCKED,
            }
            or current.production_mutation_admitted
            or current.automatic_replay_allowed
            or current.journal_retirement_allowed
            or current.notes_records_available
        ):
            return _result(state.OBSERVATION_REFUSED_BLOCKED)
        if (
            current.state
            is readiness.PrivateProductionReadinessState.PROBE_REFUSED_PRODUCTION_BLOCKED
        ):
            return _result(
                state.OBSERVATION_REFUSED_BLOCKED, root=root, owner_seen=owner_seen
            )
        if current.root_observation != root or current.owner_observed != owner_seen:
            return _result(state.ROOT_CHANGED_BLOCKED, root=root, owner_seen=owner_seen)
        native = custody.review_existing_private_root_native_custody()
        if (
            type(native) is not custody.PrivateRetainedRootReview
            or type(native.state) is not custody.PrivateRetainedRootState
            or native.production_mutation_admitted
            or native.automatic_replay_allowed
            or native.journal_retirement_allowed
            or native.notes_records_available
        ):
            return _result(state.OBSERVATION_REFUSED_BLOCKED)
        retained = native.state.value
        # Canonical intent below is *synthetic*. It proves only that the
        # permanent barrier still blocks a valid description, not that any
        # real registry/descriptor/journal image belongs to this OS owner.
        intent = canon._canonical_fork_intent()
        blocked = barrier.review_private_production_write_barrier(
            scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
            intent.witness.registry_revision_before,
            intent,
        )
        if (
            type(blocked) is not barrier.PrivateProductionWriteBarrierReview
            or blocked.state
            is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
            or tuple(item.value for item in blocked.unqualified_requirements)
            != readiness._REQUIRED
        ):
            return _result(
                state.CANONICAL_DESCRIPTION_REFUSED_BLOCKED,
                root=root,
                retained=retained,
                owner_seen=owner_seen,
            )
        last = inspection.inspect_private_root()
        if type(last) is not inspection.PrivateRootInspection or last != first:
            return _result(
                state.ROOT_CHANGED_BLOCKED,
                root=root,
                retained=retained,
                owner_seen=owner_seen,
                description=True,
            )
        return _result(
            state.PRODUCTION_BLOCKED,
            root=root,
            retained=retained,
            owner_seen=owner_seen,
            rechecked=True,
            description=True,
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.OBSERVATION_REFUSED_BLOCKED)
