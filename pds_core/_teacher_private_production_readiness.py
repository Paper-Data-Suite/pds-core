"""Fail-closed, non-authorizing production-readiness gap review (#238 3G79).

The nine barriers are *requirements*, not claims that previous scratch tests
satisfied production security. Read-only effective-owner/private-root probes
are deliberately released before this review returns, and no filesystem path,
principal, credential, handle, or write permit escapes. A positive native
observation NEVER upgrades the production admission state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier


class PrivateProductionReadinessState(str, Enum):
    PRODUCTION_BLOCKED = "production_blocked"
    PROBE_REFUSED_PRODUCTION_BLOCKED = "probe_refused_production_blocked"
    REQUIREMENT_CONTRACT_CHANGED_BLOCKED = "requirement_contract_changed_blocked"


# A change to a barrier requirement requires deliberate review, not silent
# agreement between two dynamically imported lists or a fallback to READY.
_REQUIRED: tuple[str, ...] = (
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


@dataclass(frozen=True, slots=True, repr=False)
class PrivateProductionReadinessReview:
    state: PrivateProductionReadinessState
    root_observation: str
    native_root_observation: str
    owner_observed: bool
    unqualified_requirements: tuple[str, ...] = field(repr=False)
    production_mutation_admitted: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateProductionReadinessReview(non_authorizing=True)"


def review_private_production_readiness() -> PrivateProductionReadinessReview:
    """Observe current *process* owner/root without exposing a write capability.

    This accepts no paths, owner claims, intent, decision tokens, booleans, or
    callbacks. Read-only probes cannot replace a continuously held production
    lock, private ACL enforcement, durable transaction or recovery protocol.
    """
    actual = tuple(item.value for item in barrier._REQUIRED)
    if actual != _REQUIRED:
        return PrivateProductionReadinessReview(
            PrivateProductionReadinessState.REQUIREMENT_CONTRACT_CHANGED_BLOCKED,
            "unavailable",
            "unavailable",
            False,
            _REQUIRED,
        )
    root_label = "unavailable"
    native_label = "unavailable"
    owner_seen = False
    refused = False
    try:
        preliminary = inspection.inspect_private_root()
        if not isinstance(preliminary.state, inspection.PrivateRootState):
            raise ValueError("Unexpected preliminary state")
        root_label = preliminary.state.value
        owner_seen = type(preliminary.owner) is inspection.EffectiveOSOwner
        native = preflight.inspect_native_private_preflight()
        if not isinstance(native.state, preflight.NativePrivatePreflightState):
            raise ValueError("Unexpected native state")
        native_label = native.state.value
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError):
        refused = True
        root_label = "unavailable"
        native_label = "unavailable"
        owner_seen = False
    return PrivateProductionReadinessReview(
        PrivateProductionReadinessState.PROBE_REFUSED_PRODUCTION_BLOCKED
        if refused
        else PrivateProductionReadinessState.PRODUCTION_BLOCKED,
        root_label,
        native_label,
        owner_seen,
        _REQUIRED,
    )
