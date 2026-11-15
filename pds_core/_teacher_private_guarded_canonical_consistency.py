"""Read-only canonical journal/registry/descriptor consistency under one guard (#238 3G84).

A transaction UUID is a lookup hint, not caller-provided intent or authority.
Current journal bytes are decoded canonically INSIDE Core's existing retained
private-registry/workspace-descriptor guard. Two native image observations,
namespace, OS owner, registry owner, and accepted workspace root must agree.
No locks, handles, paths, SIDs, metadata images, transaction IDs or write permits
are returned. No mutation, replay, retirement or Notes activation is possible.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePath, PureWindowsPath

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_metadata as metadata
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
from pds_core import _teacher_private_transaction_witness as witness

_REQUIRED = (
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


class PrivateGuardedCanonicalState(str, Enum):
    PREPARED_CANONICAL_BLOCKED = "prepared_canonical_blocked"
    DESCRIPTOR_PENDING_CANONICAL_BLOCKED = "descriptor_pending_canonical_blocked"
    JOURNAL_PENDING_CANONICAL_BLOCKED = "journal_pending_canonical_blocked"
    INVALID_REQUEST_BLOCKED = "invalid_request_blocked"
    UNSUPPORTED_BLOCKED = "unsupported_blocked"
    REQUIREMENT_DRIFT_BLOCKED = "requirement_drift_blocked"
    PRECONDITION_REFUSED_BLOCKED = "precondition_refused_blocked"
    ROOT_OR_OWNER_REFUSED_BLOCKED = "root_or_owner_refused_blocked"
    NATIVE_CUSTODY_REFUSED_BLOCKED = "native_custody_refused_blocked"
    NAMESPACE_REFUSED_PRESERVE = "namespace_refused_preserve"
    JOURNAL_INTENT_REFUSED_PRESERVE = "journal_intent_refused_preserve"
    OWNER_BINDING_REFUSED_PRESERVE = "owner_binding_refused_preserve"
    IMAGE_MISMATCH_PRESERVE = "image_mismatch_preserve"
    IMAGE_DRIFT_PRESERVE = "image_drift_preserve"
    GUARD_REFUSED_PRESERVE = "guard_refused_preserve"
    OBSERVATION_REFUSED_PRESERVE = "observation_refused_preserve"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateGuardedCanonicalReview:
    state: PrivateGuardedCanonicalState
    unqualified_requirements: tuple[str, ...] = field(default=_REQUIRED, repr=False)
    read_only_guard_observed: bool = False
    exact_images_rechecked: bool = False
    production_mutation_admitted: bool = False
    operation_owned_write_guard_qualified: bool = False
    automatic_replay_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateGuardedCanonicalReview(non_authorizing=True)"


def _outcome(
    state: PrivateGuardedCanonicalState,
    *,
    observed: bool = False,
    rechecked: bool = False,
) -> PrivateGuardedCanonicalReview:
    return PrivateGuardedCanonicalReview(
        state=state, read_only_guard_observed=observed, exact_images_rechecked=rechecked
    )


def _valid_tx(value: object) -> bool:
    if type(value) is not str or len(value) != 36:
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _same_workspace(accepted: str, root: PurePath, kind: str) -> bool:
    if kind == "windows_token_sid":
        return PureWindowsPath(accepted) == PureWindowsPath(str(root))
    return accepted == str(root)


def _classify_canonical_images(
    images: tuple[bytes, bytes, bytes, bytes | None],
    transaction_id: str,
    owner: inspection.EffectiveOSOwner,
    workspace: PurePath,
    staged: bool,
) -> PrivateGuardedCanonicalState:
    """Pure exact-image classifier; no serialized bytes or identity leave the guard."""
    state = PrivateGuardedCanonicalState
    journal, registry, sidecar, stage_image = images
    if (
        type(journal) is not bytes
        or type(registry) is not bytes
        or type(sidecar) is not bytes
        or (stage_image is not None and type(stage_image) is not bytes)
    ):
        return state.IMAGE_MISMATCH_PRESERVE
    try:
        proposed = intents.decode_private_transaction_intent(journal)
        if (
            intents.encode_private_transaction_intent(proposed) != journal
            or proposed.witness.transaction_id != transaction_id
            or proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE
            or type(proposed.registry_before) is not bytes
            or type(proposed.descriptor_before) is not bytes
        ):
            return state.JOURNAL_INTENT_REFUSED_PRESERVE
        before = metadata.decode_private_registry(proposed.registry_before)
        after = metadata.decode_private_registry(proposed.registry_after)
        if (
            metadata.encode_private_registry(before) != proposed.registry_before
            or metadata.encode_private_registry(after) != proposed.registry_after
            or before.owner.kind != owner.kind
            or before.owner.value != owner.value
            or after.owner != before.owner
            or after.revision != before.revision + 1
            or before.revision != proposed.witness.registry_revision_before
            or after.revision != proposed.witness.registry_revision_after
        ):
            return state.OWNER_BINDING_REFUSED_PRESERVE
        matching = [
            entry
            for entry in after.bindings
            if entry.association_id == proposed.witness.association_after
        ]
        if len(matching) != 1 or not _same_workspace(
            matching[0].accepted_root, workspace, owner.kind
        ):
            return state.OWNER_BINDING_REFUSED_PRESERVE
        if staged:
            if (
                registry == proposed.registry_before
                and sidecar == proposed.descriptor_before
                and stage_image == proposed.registry_after
            ):
                return state.PREPARED_CANONICAL_BLOCKED
        elif stage_image is None and registry == proposed.registry_after:
            if sidecar == proposed.descriptor_before:
                return state.DESCRIPTOR_PENDING_CANONICAL_BLOCKED
            if sidecar == proposed.descriptor_after:
                return state.JOURNAL_PENDING_CANONICAL_BLOCKED
        return state.IMAGE_MISMATCH_PRESERVE
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        witness.PrivateTransactionError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return state.JOURNAL_INTENT_REFUSED_PRESERVE


def review_existing_guarded_canonical_consistency(
    existing_workspace_root: Path,
    transaction_id: str,
) -> PrivateGuardedCanonicalReview:
    """Check one existing pending transaction under one retained native scope.

    The transaction ID selects a *read*, not a write. Never trust it as intent.
    All authoritative candidate intent bytes come from the protected journal,
    and every observation is rechecked BEFORE the guard releases. All returned
    states remain blocked, even when exact canonical images match.
    """
    state = PrivateGuardedCanonicalState
    if sys.platform not in {"linux", "win32"}:
        return _outcome(state.UNSUPPORTED_BLOCKED)
    if (
        type(existing_workspace_root) is not type(Path())
        or not descriptor._valid_root(existing_workspace_root)
        or not _valid_tx(transaction_id)
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
            expected_inventory = (
                inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
                if namespace[2]
                else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
            )
            observed: tuple[bytes, bytes, bytes, bytes | None] | None = None
            first_state: PrivateGuardedCanonicalState | None = None
            for _ in range(2):
                if (
                    readers._inventory(private_root, owner) is not expected_inventory
                    or reconciliation._namespace(private_root, transaction_id)
                    != namespace
                ):
                    return _outcome(state.NAMESPACE_REFUSED_PRESERVE)
                if inspection._effective_owner(sys.platform) != owner:
                    return _outcome(state.ROOT_OR_OWNER_REFUSED_BLOCKED)
                current = exact._images(
                    private_root,
                    existing_workspace_root,
                    transaction_id,
                    owner,
                    namespace[2],
                )
                if current is None:
                    return _outcome(state.IMAGE_MISMATCH_PRESERVE)
                classified = _classify_canonical_images(
                    current,
                    transaction_id,
                    owner,
                    existing_workspace_root,
                    namespace[2],
                )
                if classified not in {
                    state.PREPARED_CANONICAL_BLOCKED,
                    state.DESCRIPTOR_PENDING_CANONICAL_BLOCKED,
                    state.JOURNAL_PENDING_CANONICAL_BLOCKED,
                }:
                    return _outcome(classified)
                if observed is None:
                    observed, first_state = current, classified
                elif observed != current or first_state is not classified:
                    return _outcome(state.IMAGE_DRIFT_PRESERVE)
            if (
                readers._inventory(private_root, owner) is not expected_inventory
                or reconciliation._namespace(private_root, transaction_id) != namespace
            ):
                return _outcome(state.NAMESPACE_REFUSED_PRESERVE)
            if (
                inspection._effective_owner(sys.platform) != owner
                or inspection.inspect_private_root() != root
            ):
                return _outcome(state.ROOT_OR_OWNER_REFUSED_BLOCKED)
            if first_state is None:
                return _outcome(state.OBSERVATION_REFUSED_PRESERVE)
        return _outcome(first_state, observed=True, rechecked=True)
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
        FileNotFoundError,
    ):
        return _outcome(state.OBSERVATION_REFUSED_PRESERVE)
