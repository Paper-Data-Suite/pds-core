"""Prepare one journal candidate and registry stage under separate native guards.

Core #238 Slice 3G1: internal two-phase create-only orchestration. Success is
recovery-review evidence, never durable admission, atomic pairing, metadata
replacement, an OS-owner binding or Notes write authority. No cleanup/retry.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_journal_provision as journal_create
from pds_core import _teacher_private_linux_stage_mutation_guard as linux_stage
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_mutation_aware_journal_guard as linux_journal
from pds_core import _teacher_private_registry_stage_provision as stage_create
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_journal_mutation_guard as windows_journal
from pds_core import _teacher_private_windows_stage_mutation_guard as windows_stage


class PrivatePairedPreparationState(str, Enum):
    PREPARED_REVIEW_REQUIRED = "prepared_review_required"
    INVALID_REQUEST = "invalid_request"
    INITIALIZATION_REFUSED = "initialization_refused"
    UNSUPPORTED = "unsupported"
    JOURNAL_REVIEW_REQUIRED = "journal_review_required"
    STAGE_REVIEW_REQUIRED = "stage_review_required"


_MESSAGES = {
    PrivatePairedPreparationState.PREPARED_REVIEW_REQUIRED: "Journal and registry stage were observed; independent durability and recovery review required.",
    PrivatePairedPreparationState.INVALID_REQUEST: "Invalid private transaction preparation request.",
    PrivatePairedPreparationState.INITIALIZATION_REFUSED: "Initial binding requires its own protected absence protocol.",
    PrivatePairedPreparationState.UNSUPPORTED: "Platform or private storage scope unsupported.",
    PrivatePairedPreparationState.JOURNAL_REVIEW_REQUIRED: "Journal creation or its guard was unqualified; preserve pending evidence for review.",
    PrivatePairedPreparationState.STAGE_REVIEW_REQUIRED: "Stage creation or its guard was unqualified; preserve both artifacts for review.",
}


@dataclass(frozen=True, slots=True)
class PrivatePairedPreparationReview:
    """Bounded advisory result: no paths, bytes, OS IDs or commit handle."""

    state: PrivatePairedPreparationState
    message: str


def _result(state: PrivatePairedPreparationState) -> PrivatePairedPreparationReview:
    return PrivatePairedPreparationReview(state, _MESSAGES[state])


class _PhaseStopped(Exception):
    """Internal control flow: deliberately skip guard success exit on write failure."""


def prepare_private_journal_and_registry_stage(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivatePairedPreparationReview:
    """Create candidates only, never commit or authorize replay.

    Phase 1 and phase 2 EACH retain their native locks and guards. The locks
    are released between phases; phase 2 revalidates the exact journal and
    before-images, rejecting concurrent or unexpected changes. Even successful
    phase 2 is not a cross-file transaction, atomicity or durability proof.
    Any failure may leave one or both files. Never retry or remove them here.
    """
    platform = sys.platform
    if platform not in {"linux", "win32"}:
        return _result(PrivatePairedPreparationState.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivatePairedPreparationState.INVALID_REQUEST)
    try:
        if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            return _result(PrivatePairedPreparationState.INITIALIZATION_REFUSED)
        raw = intents.encode_private_transaction_intent(proposed)
        decoded = intents.decode_private_transaction_intent(raw)
        if (
            decoded != proposed
            or intents.encode_private_transaction_intent(decoded) != raw
        ):
            return _result(PrivatePairedPreparationState.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivatePairedPreparationState.INVALID_REQUEST)

    # Do not enter old triple-retained read-only scope: Linux directory
    # timestamps intentionally change on CREATE_NEW. Each mutation guard has
    # an explicit one-entry before/after namespace contract.
    journal_scope = (
        linux_journal.hold_expected_private_journal_creation
        if platform == "linux"
        else windows_journal.hold_expected_windows_private_journal_creation
    )
    stage_scope = (
        linux_stage.hold_expected_linux_private_registry_stage_creation
        if platform == "linux"
        else windows_stage.hold_expected_windows_private_registry_stage_creation
    )

    try:
        with journal_scope(proposed, existing_private_root, existing_workspace_root):
            created = journal_create.create_private_transaction_intent_file(
                existing_private_root / "transactions", raw
            )
            if (
                created.state
                is not journal_create.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
            ):
                raise _PhaseStopped
    except (
        _PhaseStopped,
        linux_journal.PrivateJournalMutationGuardError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivatePairedPreparationState.JOURNAL_REVIEW_REQUIRED)

    # Important: the first guarded phase has ended. This is NOT one global
    # held-lock transaction. The stage guard MUST re-observe the same journal,
    # the exact before-images, owner, private root and stage namespace.
    try:
        with stage_scope(proposed, existing_private_root, existing_workspace_root):
            staged = stage_create.create_private_registry_after_image_stage(
                proposed, existing_private_root
            )
            if (
                staged.state
                is not stage_create.PrivateRegistryStageState.STAGED_UNQUALIFIED
            ):
                raise _PhaseStopped
    except (
        _PhaseStopped,
        linux_stage.PrivateLinuxStageMutationError,
        windows_stage.PrivateWindowsStageMutationError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(PrivatePairedPreparationState.STAGE_REVIEW_REQUIRED)
    return _result(PrivatePairedPreparationState.PREPARED_REVIEW_REQUIRED)
