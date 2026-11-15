"""Non-authorizing stage-to-registry pre-admission review (#238 Slice 3G85).

A request supplies only an existing workspace path, UUID lookup hint and expected
revision. Journal bytes, not caller claims, determine canonical intent inside the
existing two-root retained native guard. Two complete preimage/namespace/owner
rounds must agree before returning a sanitized BLOCKED observation. The held
scope is a cooperative, read-only observation, NOT a production write permit,
noncooperating-writer exclusion, replacement CAS, durable commit, replay,
journal retirement or Notes activation. No native handles or metadata escape.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_guarded_canonical_consistency as canonical
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_operation_preconditions as preconditions
from pds_core import _teacher_private_postcrash_reconciliation as reconciliation
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_root_custody as custody
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents

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


class PrivateStagePreAdmissionState(str, Enum):
    PREPARED_REVIEW_BLOCKED = "prepared_review_blocked"
    INVALID_REQUEST_BLOCKED = "invalid_request_blocked"
    UNSUPPORTED_BLOCKED = "unsupported_blocked"
    REQUIREMENT_DRIFT_BLOCKED = "requirement_drift_blocked"
    PRECONDITION_REFUSED_BLOCKED = "precondition_refused_blocked"
    ROOT_OR_OWNER_REFUSED_BLOCKED = "root_or_owner_refused_blocked"
    NATIVE_CUSTODY_REFUSED_BLOCKED = "native_custody_refused_blocked"
    STAGE_NOT_PREPARED_PRESERVE = "stage_not_prepared_preserve"
    NAMESPACE_REFUSED_PRESERVE = "namespace_refused_preserve"
    CANONICAL_IMAGE_REFUSED_PRESERVE = "canonical_image_refused_preserve"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    IMAGE_DRIFT_PRESERVE = "image_drift_preserve"
    GUARD_REFUSED_PRESERVE = "guard_refused_preserve"
    OBSERVATION_REFUSED_PRESERVE = "observation_refused_preserve"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateStagePreAdmissionReview:
    state: PrivateStagePreAdmissionState
    unqualified_requirements: tuple[str, ...] = field(default=_REQUIRED, repr=False)
    existing_two_root_read_guard_observed: bool = False
    two_preimage_rounds_rechecked: bool = False
    production_mutation_admitted: bool = False
    operation_owned_write_guard_qualified: bool = False
    exclusive_noncooperating_writer_guard_qualified: bool = False
    native_replace_postimage_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateStagePreAdmissionReview(non_authorizing=True)"


def _outcome(
    state: PrivateStagePreAdmissionState, *, observed: bool = False
) -> PrivateStagePreAdmissionReview:
    return PrivateStagePreAdmissionReview(
        state=state,
        existing_two_root_read_guard_observed=observed,
        two_preimage_rounds_rechecked=observed,
    )


def review_existing_stage_to_registry_pre_admission(
    existing_workspace_root: Path,
    transaction_id: str,
    expected_registry_revision: int,
) -> PrivateStagePreAdmissionReview:
    """Read-only local preimage review while holding the *existing* native guard.

    Only the prepared stage-to-registry checkpoint is in scope; all other
    checkpoints preserve pending evidence. Even PREPARED_REVIEW_BLOCKED cannot
    be carried into a later writer: that writer must independently hold and
    qualify its *own* exclusive production transaction boundary.
    """
    state = PrivateStagePreAdmissionState
    if sys.platform not in {"linux", "win32"}:
        return _outcome(state.UNSUPPORTED_BLOCKED)
    if (
        type(existing_workspace_root) is not type(Path())
        or not descriptor._valid_root(existing_workspace_root)
        or not canonical._valid_tx(transaction_id)
        or type(expected_registry_revision) is not int
        or expected_registry_revision < 1
    ):
        return _outcome(state.INVALID_REQUEST_BLOCKED)
    if (
        readiness._REQUIRED != _REQUIRED
        or tuple(item.value for item in barrier._REQUIRED) != _REQUIRED
    ):
        return _outcome(state.REQUIREMENT_DRIFT_BLOCKED)
    try:
        prior = preconditions.review_private_operation_preconditions()
        if (
            type(prior) is not preconditions.PrivateOperationPreconditionReview
            or prior.state
            is not preconditions.PrivateOperationPreconditionState.PRODUCTION_BLOCKED
            or prior.unqualified_requirements != _REQUIRED
            or prior.production_mutation_admitted
            or prior.automatic_replay_allowed
            or prior.journal_retirement_allowed
            or prior.notes_records_available
        ):
            return _outcome(state.PRECONDITION_REFUSED_BLOCKED)
        root = inspection.inspect_private_root()
        if (
            type(root) is not inspection.PrivateRootInspection
            or root.state is not inspection.PrivateRootState.PRESENT_UNVERIFIED
            or type(root.owner) is not inspection.EffectiveOSOwner
            or not isinstance(root.candidate, Path)
            or root.owner.kind
            != ("windows_token_sid" if sys.platform == "win32" else "posix_euid")
        ):
            return _outcome(state.ROOT_OR_OWNER_REFUSED_BLOCKED)
        private_root = root.candidate
        owner = root.owner
        with retained._hold_existing_retained_descriptor_guard(
            private_root, existing_workspace_root
        ):
            if (
                inspection._effective_owner(sys.platform) != owner
                or inspection.inspect_private_root() != root
            ):
                return _outcome(state.ROOT_OR_OWNER_REFUSED_BLOCKED)
            if (
                custody._probe_existing(private_root, owner)
                is not custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
            ):
                return _outcome(state.NATIVE_CUSTODY_REFUSED_BLOCKED)
            namespace = reconciliation._namespace(private_root, transaction_id)
            if not namespace[2]:
                return _outcome(state.STAGE_NOT_PREPARED_PRESERVE)
            expected_inventory = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            first: tuple[bytes, bytes, bytes, bytes | None] | None = None
            for _ in range(2):
                if (
                    readers._inventory(private_root, owner) is not expected_inventory
                    or reconciliation._namespace(private_root, transaction_id)
                    != namespace
                ):
                    return _outcome(state.NAMESPACE_REFUSED_PRESERVE)
                if (
                    inspection._effective_owner(sys.platform) != owner
                    or inspection.inspect_private_root() != root
                ):
                    return _outcome(state.ROOT_OR_OWNER_REFUSED_BLOCKED)
                current = exact._images(
                    private_root,
                    existing_workspace_root,
                    transaction_id,
                    owner,
                    True,
                )
                if current is None:
                    return _outcome(state.CANONICAL_IMAGE_REFUSED_PRESERVE)
                canonical_state = canonical._classify_canonical_images(
                    current, transaction_id, owner, existing_workspace_root, True
                )
                if (
                    canonical_state
                    is not canonical.PrivateGuardedCanonicalState.PREPARED_CANONICAL_BLOCKED
                ):
                    return _outcome(state.CANONICAL_IMAGE_REFUSED_PRESERVE)
                # Current journal bytes, never a caller-provided intent, are
                # re-decoded on EACH round before the requested revision agrees.
                try:
                    intent = intents.decode_private_transaction_intent(current[0])
                    if (
                        intents.encode_private_transaction_intent(intent) != current[0]
                        or intent.witness.transaction_id != transaction_id
                        or intent.witness.registry_revision_before
                        != expected_registry_revision
                        or intent.witness.registry_revision_after
                        != expected_registry_revision + 1
                    ):
                        return _outcome(state.REVISION_MISMATCH_REFUSED)
                except (
                    intents.PrivateIntentError,
                    OSError,
                    ValueError,
                    TypeError,
                    AttributeError,
                    OverflowError,
                ):
                    return _outcome(state.CANONICAL_IMAGE_REFUSED_PRESERVE)
                if first is None:
                    first = current
                elif first != current:
                    return _outcome(state.IMAGE_DRIFT_PRESERVE)
            if (
                readers._inventory(private_root, owner) is not expected_inventory
                or reconciliation._namespace(private_root, transaction_id) != namespace
            ):
                return _outcome(state.NAMESPACE_REFUSED_PRESERVE)
            if (
                inspection._effective_owner(sys.platform) != owner
                or inspection.inspect_private_root() != root
                or custody._probe_existing(private_root, owner)
                is not custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
            ):
                return _outcome(state.ROOT_OR_OWNER_REFUSED_BLOCKED)
        return _outcome(state.PREPARED_REVIEW_BLOCKED, observed=True)
    except retained.RetainedDescriptorGuardError:
        return _outcome(state.GUARD_REFUSED_PRESERVE)
    except KeyboardInterrupt:
        return _outcome(state.OBSERVATION_REFUSED_PRESERVE)
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _outcome(state.OBSERVATION_REFUSED_PRESERVE)
