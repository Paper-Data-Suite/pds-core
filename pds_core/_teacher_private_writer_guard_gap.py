"""Fail-closed writer-owned exclusivity gap review (Core #238, Slice 3G86).

The 3G85 stage inventory is a cooperating, read-only guarded observation.
It cannot establish exclusion of uncooperative same-user writers, a retained
writer-owned transaction, or durable replacement. Even a prepared checkpoint
never leaves this module as authorization. Native scratch tests document the
separate-file locking limitation; no real teacher-private file is modified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_stage_to_registry_pre_admission as stage


class PrivateWriterGuardGapState(str, Enum):
    PREPARED_BUT_EXCLUSIVITY_UNQUALIFIED = "prepared_but_exclusivity_unqualified"
    STAGE_REVIEW_REFUSED_PRESERVE = "stage_review_refused_preserve"
    REQUIREMENT_DRIFT_BLOCKED = "requirement_drift_blocked"
    REVIEW_FAILURE_PRESERVE = "review_failure_preserve"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateWriterGuardGapReview:
    state: PrivateWriterGuardGapState
    unqualified_requirements: tuple[str, ...] = field(
        default_factory=lambda: stage._REQUIRED, repr=False
    )
    stage_read_review_only: bool = False
    cooperative_lock_exclusion_is_production_exclusion: bool = False
    operation_owned_guard_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    native_parent_custody_for_write_qualified: bool = False
    exact_preimage_cas_for_write_qualified: bool = False
    native_replace_postimage_qualified: bool = False
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateWriterGuardGapReview(non_authorizing=True)"


def _result(
    state: PrivateWriterGuardGapState, *, observed: bool = False
) -> PrivateWriterGuardGapReview:
    return PrivateWriterGuardGapReview(state=state, stage_read_review_only=observed)


def review_private_writer_owned_exclusivity_gap(
    existing_workspace_root: Path, transaction_id: str, expected_registry_revision: int
) -> PrivateWriterGuardGapReview:
    """Repeat the current stage check, then refuse transfer of read authority.

    Inputs are lookups only. No lock, file descriptor, writer, native handle,
    callback, task, transaction certificate or bytes are returned. A future
    exclusive writer must establish its own native parent/file custody and
    preimage comparison *during the irreversible operation*, independently of
    anything returned by this function.
    """
    state = PrivateWriterGuardGapState
    if (
        len(readiness._REQUIRED) != 9
        or tuple(requirement.value for requirement in barrier._REQUIRED)
        != readiness._REQUIRED
        or stage._REQUIRED != readiness._REQUIRED
    ):
        return _result(state.REQUIREMENT_DRIFT_BLOCKED)
    try:
        prior = stage.review_existing_stage_to_registry_pre_admission(
            existing_workspace_root, transaction_id, expected_registry_revision
        )
        if (
            type(prior) is not stage.PrivateStagePreAdmissionReview
            or prior.unqualified_requirements != readiness._REQUIRED
            or prior.production_mutation_admitted
            or prior.operation_owned_write_guard_qualified
            or prior.exclusive_noncooperating_writer_guard_qualified
            or prior.native_replace_postimage_qualified
            or prior.automatic_replay_allowed
            or prior.journal_retirement_allowed
            or prior.notes_records_available
            or prior.directory_crash_durability_qualified
            or prior.multi_document_atomic_commit_qualified
        ):
            return _result(state.REVIEW_FAILURE_PRESERVE)
        if prior.state is stage.PrivateStagePreAdmissionState.PREPARED_REVIEW_BLOCKED:
            if not (
                prior.existing_two_root_read_guard_observed
                and prior.two_preimage_rounds_rechecked
            ):
                return _result(state.REVIEW_FAILURE_PRESERVE)
            return _result(state.PREPARED_BUT_EXCLUSIVITY_UNQUALIFIED, observed=True)
        return _result(state.STAGE_REVIEW_REFUSED_PRESERVE)
    except KeyboardInterrupt:
        return _result(state.REVIEW_FAILURE_PRESERVE)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.REVIEW_FAILURE_PRESERVE)
