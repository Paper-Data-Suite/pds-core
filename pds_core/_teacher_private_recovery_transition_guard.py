"""Production transition-capable guard composition, read-only (#238 3G41).

The existing retained-registry review guard requires the original registry
identity to survive __exit__, which cannot serve a stage-to-registry *writer*.
This distinct journal+descriptor scope preserves ordered local locks and native
journal/descriptor custody without inheriting that old-registry exit invariant.
It never writes, authorizes replacement or exposes any guard/FD/HANDLE to a
caller. Registry/stage currentness is rechecked as untrusted evidence inside
its own scope, but a future mutation path still needs an operation-owned,
transition-aware registry handle and postimage/durability protocol.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_exclusive_pair_checkpoint as pair
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_pre_replace_window as window
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_retained_stage_custody as custody
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_transaction_intent as intents


class PrivateTransitionGuardState(str, Enum):
    TRANSITION_SCOPE_OBSERVED_NO_WRITE = "transition_scope_observed_no_write"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    INTENT_UNQUALIFIED = "intent_unqualified"
    REVISION_MISMATCH_REFUSED = "revision_mismatch_refused"
    ROOT_UNQUALIFIED = "root_unqualified"
    OWNER_OR_PROTECTION_REFUSED = "owner_or_protection_refused"
    BINDING_MISMATCH = "binding_mismatch"
    OWNER_CHANGED = "owner_changed"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    STAGE_CUSTODY_REFUSED = "stage_custody_refused"
    STAGE_CHANGED_PRESERVE = "stage_changed_preserve"
    PREIMAGE_CONFLICT_PRESERVE = "preimage_conflict_preserve"
    DESCRIPTION_CHANGED_PRESERVE = "description_changed_preserve"
    GUARD_REFUSED = "guard_refused"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateTransitionGuardState, str] = {
    PrivateTransitionGuardState.TRANSITION_SCOPE_OBSERVED_NO_WRITE: (
        "Journal and workspace descriptor remained guarded without an immutable old-registry "
        "release requirement; native preimages matched. No mutation permitted."
    ),
    PrivateTransitionGuardState.INVALID_REQUEST: "Invalid private transition-scope request.",
    PrivateTransitionGuardState.OPERATION_NOT_ADMITTED: "Only prepared stage-to-registry is in scope.",
    PrivateTransitionGuardState.UNSUPPORTED: "Native transition guard is unsupported on this platform.",
    PrivateTransitionGuardState.INTENT_UNQUALIFIED: "Canonical private transaction intent is unqualified.",
    PrivateTransitionGuardState.REVISION_MISMATCH_REFUSED: "Expected registry revision was refused.",
    PrivateTransitionGuardState.ROOT_UNQUALIFIED: "Existing private or workspace root is unqualified.",
    PrivateTransitionGuardState.OWNER_OR_PROTECTION_REFUSED: "Native ownership or protection is unqualified.",
    PrivateTransitionGuardState.BINDING_MISMATCH: "Workspace association does not match the owner binding.",
    PrivateTransitionGuardState.OWNER_CHANGED: "Native process ownership changed during the guard.",
    PrivateTransitionGuardState.NAMESPACE_CONFLICT_PRESERVE: "Pending journal/stage namespace conflicted; preserve evidence.",
    PrivateTransitionGuardState.STAGE_CUSTODY_REFUSED: "Retained stage guard could not be established.",
    PrivateTransitionGuardState.STAGE_CHANGED_PRESERVE: "Retained stage identity or protection changed; preserve evidence.",
    PrivateTransitionGuardState.PREIMAGE_CONFLICT_PRESERVE: "Native transaction preimages or identities conflicted; preserve evidence.",
    PrivateTransitionGuardState.DESCRIPTION_CHANGED_PRESERVE: "Canonical transaction description changed during custody.",
    PrivateTransitionGuardState.GUARD_REFUSED: "Native journal/descriptor scope could not be retained or released.",
    PrivateTransitionGuardState.INTERRUPTED_PRESERVE: "Guard interrupted; preserve pending evidence.",
    PrivateTransitionGuardState.IO_ERROR: "Transition-scope observation could not complete safely.",
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateTransitionGuardReview:
    """Sanitized after-release observation, never a handle or execution permit."""

    state: PrivateTransitionGuardState
    message: str
    pending_evidence_must_remain: bool
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateTransitionGuardReview(non_authorizing=True)"


def _result(state: PrivateTransitionGuardState) -> PrivateTransitionGuardReview:
    return PrivateTransitionGuardReview(
        state, _MESSAGES[state], True, barrier._REQUIRED
    )


class _WriterGuardRefused(Exception):
    def __init__(self, state: PrivateTransitionGuardState) -> None:
        self.state = state
        super().__init__("Private transition guard refused.")


@contextmanager
def _hold_transitionable_journal_descriptor_guard(
    existing_private_root: Path, existing_workspace_root: Path
) -> Iterator[None]:
    """Hold locks+journal+descriptor, WITHOUT old-registry identity exit veto.

    No registry replacement is performed. This private context yields None,
    never a handle/permit/writer callback; only an operation-owned future writer
    may safely implement a separately qualified registry transition protocol.
    """
    state = PrivateTransitionGuardState
    if sys.platform not in {"linux", "win32"}:
        raise _WriterGuardRefused(state.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        raise _WriterGuardRefused(state.INVALID_REQUEST)
    try:
        with journal_guard._hold_existing_retained_journal_guard(
            existing_private_root, existing_workspace_root
        ):
            expected = ordered._owner()
            held = (
                retained._held_linux_descriptor(existing_workspace_root)
                if sys.platform == "linux"
                else retained._held_windows_descriptor(existing_workspace_root)
            )
            with held:
                if ordered._owner() != expected:
                    raise _WriterGuardRefused(state.OWNER_CHANGED)
                try:
                    yield
                finally:
                    if ordered._owner() != expected:
                        raise _WriterGuardRefused(state.OWNER_CHANGED)
    except journal_guard.RetainedJournalGuardError as exc:
        if exc.code is journal_guard.RetainedJournalGuardCode.OWNER_CHANGED:
            raise _WriterGuardRefused(state.OWNER_CHANGED) from None
        if exc.code is journal_guard.RetainedJournalGuardCode.UNSUPPORTED:
            raise _WriterGuardRefused(state.UNSUPPORTED) from None
        raise _WriterGuardRefused(state.GUARD_REFUSED) from None
    except retained.RetainedDescriptorGuardError as exc:
        if exc.code is retained.RetainedDescriptorGuardCode.OWNER_CHANGED:
            raise _WriterGuardRefused(state.OWNER_CHANGED) from None
        if exc.code is retained.RetainedDescriptorGuardCode.UNSUPPORTED:
            raise _WriterGuardRefused(state.UNSUPPORTED) from None
        raise _WriterGuardRefused(state.GUARD_REFUSED) from None


def review_native_transitionable_production_scope(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateTransitionGuardReview:
    """Read-only observation in a writer-compatible, existing native guard.

    No prior review, approval flag, writable path, callback, or injected handle
    may substitute for live in-scope preimages. Returns only after guard exit.
    """
    state = PrivateTransitionGuardState
    if (
        type(step) is not scratch.PrivateScratchWriterStep
        or type(expected_revision) is not int
        or expected_revision < 1
        or type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
    ):
        return _result(state.INVALID_REQUEST)
    if step is not scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    if not lock_file._requested_root(
        existing_private_root, sys.platform
    ) or not descriptor._valid_root(existing_workspace_root):
        return _result(state.ROOT_UNQUALIFIED)
    try:
        decision = barrier.review_private_production_write_barrier(
            step, expected_revision, proposed
        )
        if type(decision) is not barrier.PrivateProductionWriteBarrierReview:
            return _result(state.INTENT_UNQUALIFIED)
        if (
            decision.state
            is barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ):
            return _result(state.REVISION_MISMATCH_REFUSED)
        if (
            decision.state
            is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ):
            return _result(state.INTENT_UNQUALIFIED)
        initial = window._description(step, expected_revision, proposed)
        if initial is None:
            return _result(state.INTENT_UNQUALIFIED)
        raw = intents.encode_private_transaction_intent(proposed)
        if type(raw) is not bytes or len(raw) > intents.MAX_INTENT_BYTES:
            return _result(state.INTENT_UNQUALIFIED)
        checked = intents.decode_private_transaction_intent(raw)
        if (
            type(checked) is not intents.PrivateTransactionIntent
            or checked != proposed
            or intents.encode_private_transaction_intent(checked) != raw
            or type(checked.registry_before) is not bytes
            or type(checked.registry_after) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        before = checked.registry_before
        after = checked.registry_after
        descriptor_before = checked.descriptor_before
        if (
            type(before) is not bytes
            or type(after) is not bytes
            or type(descriptor_before) is not bytes
        ):
            return _result(state.INTENT_UNQUALIFIED)
        refusal, owner = preflight._native_observation(existing_private_root)
        if refusal is not None or owner is None:
            return _result(state.OWNER_OR_PROTECTION_REFUSED)
        if (
            preflight._intent_owner_and_binding(checked, owner, existing_workspace_root)
            is not None
        ):
            return _result(state.BINDING_MISMATCH)
        tx = checked.witness.transaction_id
        with _hold_transitionable_journal_descriptor_guard(
            existing_private_root, existing_workspace_root
        ):
            if ordered._owner() != owner:
                return _result(state.OWNER_CHANGED)
            inside = intents.decode_private_transaction_intent(raw)
            if (
                type(inside) is not intents.PrivateTransactionIntent
                or inside != checked
                or inside != proposed
                or intents.encode_private_transaction_intent(inside) != raw
            ):
                return _result(state.INTENT_UNQUALIFIED)
            if window._description(step, expected_revision, inside) != initial:
                return _result(state.DESCRIPTION_CHANGED_PRESERVE)
            expected_namespace = recovery._namespace(existing_private_root, tx)
            if (
                type(expected_namespace) is not tuple
                or len(expected_namespace) != 3
                or expected_namespace[2] is not True
            ):
                return _result(state.NAMESPACE_CONFLICT_PRESERVE)
            wanted = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
            images: parents._Image = (raw, before, descriptor_before, after)
            with custody._held_stage(
                existing_private_root, tx, owner, len(after)
            ) as stage_held:
                baseline: scope._Frame | None = None
                for frame_number in range(4):
                    preflight_refusal, current_owner = preflight._native_observation(
                        existing_private_root, owner
                    )
                    if (
                        preflight_refusal is not None
                        or current_owner is None
                        or ordered._owner() != owner
                    ):
                        return _result(state.OWNER_CHANGED)
                    if not stage_held():
                        return _result(state.STAGE_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root, tx, owner, expected_namespace, wanted
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    if (
                        frame_number == 2
                        and window._description(step, expected_revision, inside)
                        != initial
                    ):
                        return _result(state.DESCRIPTION_CHANGED_PRESERVE)
                    frame = scope._observe(
                        existing_private_root,
                        existing_workspace_root,
                        inside,
                        owner,
                        len(raw),
                    )
                    if not stage_held():
                        return _result(state.STAGE_CHANGED_PRESERVE)
                    if not operation._same_native_namespace(
                        existing_private_root, tx, owner, expected_namespace, wanted
                    ):
                        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                    refused = window._frame_state(
                        frame, baseline, images, initial, inside
                    )
                    if refused is not None:
                        return _result(state.PREIMAGE_CONFLICT_PRESERVE)
                    if baseline is None:
                        baseline = frame
                final_refusal, final_owner = preflight._native_observation(
                    existing_private_root, owner
                )
                if (
                    final_refusal is not None
                    or final_owner is None
                    or ordered._owner() != owner
                ):
                    return _result(state.OWNER_CHANGED)
                if not stage_held():
                    return _result(state.STAGE_CHANGED_PRESERVE)
                if not operation._same_native_namespace(
                    existing_private_root, tx, owner, expected_namespace, wanted
                ):
                    return _result(state.NAMESPACE_CONFLICT_PRESERVE)
                if (
                    baseline is None
                    or parents._parents(existing_private_root, existing_workspace_root)
                    != baseline.parent_stamps
                ):
                    return _result(state.PREIMAGE_CONFLICT_PRESERVE)
        return _result(state.TRANSITION_SCOPE_OBSERVED_NO_WRITE)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE)
    except _WriterGuardRefused as exc:
        return _result(exc.state)
    except custody._StageChanged:
        return _result(state.STAGE_CHANGED_PRESERVE)
    except custody._StageRefused:
        return _result(state.STAGE_CUSTODY_REFUSED)
    except (
        scope._ImageUnqualified,
        parents._ParentUnqualified,
        bridge._IdentityUnqualified,
    ):
        return _result(state.PREIMAGE_CONFLICT_PRESERVE)
    except pair._NamespaceChanged:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except FileNotFoundError:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except PermissionError:
        return _result(state.GUARD_REFUSED)
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        intents.PrivateIntentError,
        RuntimeError,
    ):
        return _result(state.IO_ERROR)
