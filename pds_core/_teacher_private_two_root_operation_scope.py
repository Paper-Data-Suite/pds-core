"""Read-only two-root native operation scope, still production-blocked (#238 3G83).

The existing Core ordered private/workspace locks and retained descriptor guard
remain continuously held during native private-root and descriptor observations.
A caller selects only an EXISTING workspace root. The OS selects the exact
private root and current owner; no caller principal/private root/intent/handle
or permission token is accepted. Missing locks or metadata are never created.

This is a read-only verification of a cooperating local operation scope, not
exclusive access against hostile writers, production association binding,
write CAS, crash durability, replay, journal retirement or Notes access.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_operation_preconditions as preconditions
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_root_custody as custody


# Independent contract witness: a changed requirement set fails before probing.
_FIXED_REQUIREMENTS: tuple[str, ...] = (
    "effective_os_owner_and_private_acl",
    "workspace_descriptor_binding",
    "two_root_native_parent_custody",
    "exclusive_operation_owned_guard",
    "canonical_intent_recheck_in_guard",
    "exact_registry_journal_stage_images",
    "native_replace_sharing_and_postimage",
    "directory_durability_and_crash_recovery",
    "recovery_and_journal_retirement_protocol",
)


class PrivateTwoRootOperationState(str, Enum):
    GUARDED_OBSERVED_PRODUCTION_BLOCKED = "guarded_observed_production_blocked"
    INVALID_REQUEST_BLOCKED = "invalid_request_blocked"
    UNSUPPORTED_BLOCKED = "unsupported_blocked"
    REQUIREMENTS_DRIFT_BLOCKED = "requirements_drift_blocked"
    PRECONDITIONS_REFUSED_BLOCKED = "preconditions_refused_blocked"
    PRIVATE_ROOT_MISSING_BLOCKED = "private_root_missing_blocked"
    PRIVATE_ROOT_REFUSED_BLOCKED = "private_root_refused_blocked"
    OWNER_OR_ROOT_CHANGED_BLOCKED = "owner_or_root_changed_blocked"
    NATIVE_CUSTODY_REFUSED_BLOCKED = "native_custody_refused_blocked"
    DESCRIPTOR_REFUSED_BLOCKED = "descriptor_refused_blocked"
    DESCRIPTOR_CHANGED_BLOCKED = "descriptor_changed_blocked"
    NATIVE_GUARD_REFUSED_BLOCKED = "native_guard_refused_blocked"
    OBSERVATION_ERROR_BLOCKED = "observation_error_blocked"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateTwoRootOperationReview:
    state: PrivateTwoRootOperationState
    private_custody_observation: str = "unavailable"
    descriptor_observation: str = "unavailable"
    unqualified_requirements: tuple[str, ...] = field(
        default=_FIXED_REQUIREMENTS, repr=False
    )
    read_only_guard_observed: bool = False
    two_root_observations_rechecked: bool = False
    operation_owned_write_guard_qualified: bool = False
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateTwoRootOperationReview(non_authorizing=True)"


def _result(
    state: PrivateTwoRootOperationState,
    *,
    native: str = "unavailable",
    sidecar: str = "unavailable",
    observed: bool = False,
    rechecked: bool = False,
) -> PrivateTwoRootOperationReview:
    return PrivateTwoRootOperationReview(
        state=state,
        private_custody_observation=native,
        descriptor_observation=sidecar,
        read_only_guard_observed=observed,
        two_root_observations_rechecked=rechecked,
    )


def review_existing_two_root_operation_scope(
    existing_workspace_root: Path,
) -> PrivateTwoRootOperationReview:
    """Observe two existing roots inside one held read-only guard; never READY.

    Root/owner evidence and descriptor bytes are discarded before returning.
    A positive review is still *not* an operation-owned production write guard:
    no content CAS, no noncooperating-writer exclusion, no durability proof.
    """
    state = PrivateTwoRootOperationState
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED_BLOCKED)
    if type(existing_workspace_root) is not type(Path()) or not descriptor._valid_root(
        existing_workspace_root
    ):
        return _result(state.INVALID_REQUEST_BLOCKED)
    if (
        readiness._REQUIRED != _FIXED_REQUIREMENTS
        or tuple(item.value for item in barrier._REQUIRED) != _FIXED_REQUIREMENTS
    ):
        return _result(state.REQUIREMENTS_DRIFT_BLOCKED)
    try:
        prior = preconditions.review_private_operation_preconditions()
        if (
            type(prior) is not preconditions.PrivateOperationPreconditionReview
            or prior.state
            is not preconditions.PrivateOperationPreconditionState.PRODUCTION_BLOCKED
            or prior.unqualified_requirements != _FIXED_REQUIREMENTS
            or prior.production_mutation_admitted
            or prior.automatic_replay_allowed
            or prior.journal_retirement_allowed
            or prior.operation_owned_guard_qualified
            or prior.notes_records_available
        ):
            return _result(state.PRECONDITIONS_REFUSED_BLOCKED)
        first = inspection.inspect_private_root()
        if type(first) is not inspection.PrivateRootInspection:
            return _result(state.PRIVATE_ROOT_REFUSED_BLOCKED)
        if first.state is inspection.PrivateRootState.MISSING:
            return _result(state.PRIVATE_ROOT_MISSING_BLOCKED)
        if (
            first.state is not inspection.PrivateRootState.PRESENT_UNVERIFIED
            or not isinstance(first.owner, inspection.EffectiveOSOwner)
            or not isinstance(first.candidate, Path)
            or first.owner.kind
            != ("windows_token_sid" if sys.platform == "win32" else "posix_euid")
        ):
            return _result(state.PRIVATE_ROOT_REFUSED_BLOCKED)
        private_root = first.candidate
        owner = first.owner
        with retained._hold_existing_retained_descriptor_guard(
            private_root, existing_workspace_root
        ):
            if (
                inspection._effective_owner(sys.platform) != owner
                or inspection.inspect_private_root() != first
            ):
                return _result(state.OWNER_OR_ROOT_CHANGED_BLOCKED)
            native = custody._probe_existing(private_root, owner)
            if (
                type(native) is not custody.PrivateRetainedRootState
                or native
                is not custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
            ):
                return _result(state.NATIVE_CUSTODY_REFUSED_BLOCKED)
            before = descriptor.inspect_workspace_descriptor(existing_workspace_root)
            if (
                type(before) is not descriptor.PrivateDescriptorSnapshot
                or before.state
                is not descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
            ):
                return _result(state.DESCRIPTOR_REFUSED_BLOCKED, native=native.value)
            after = descriptor.inspect_workspace_descriptor(existing_workspace_root)
            if (
                type(after) is not descriptor.PrivateDescriptorSnapshot
                or after != before
            ):
                return _result(
                    state.DESCRIPTOR_CHANGED_BLOCKED,
                    native=native.value,
                    sidecar=before.state.value,
                )
            if (
                inspection._effective_owner(sys.platform) != owner
                or inspection.inspect_private_root() != first
            ):
                return _result(
                    state.OWNER_OR_ROOT_CHANGED_BLOCKED,
                    native=native.value,
                    sidecar=before.state.value,
                )
        # The lock and native handles have been released. No result is a permit.
        return _result(
            state.GUARDED_OBSERVED_PRODUCTION_BLOCKED,
            native=native.value,
            sidecar=before.state.value,
            observed=True,
            rechecked=True,
        )
    except retained.RetainedDescriptorGuardError:
        return _result(state.NATIVE_GUARD_REFUSED_BLOCKED)
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        inspection._OwnerUnverifiable,
    ):
        return _result(state.OBSERVATION_ERROR_BLOCKED)
