"""Expected Windows journal CREATE_NEW under retained native anchors (#238 3F8).

Only an internal, explicitly invoked context. The caller may invoke the existing
create-only journal provisioner inside the scope; this module never creates or
retires files and never returns a write handle/commit token. This is a local,
fail-closed observation, not durable admission or distributed serialization.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, NoReturn

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_mutation_aware_journal_guard as common
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

Code = common.PrivateJournalMutationGuardCode
Error = common.PrivateJournalMutationGuardError


def _refuse(reason: Code) -> NoReturn:
    raise Error(reason)


def _names(directory: Path) -> set[str]:
    """Two observations of current namespace; native directory handle held outside."""
    with os.scandir(directory) as iterator:
        first = {entry.name for entry in iterator}
    with os.scandir(directory) as iterator:
        second = {entry.name for entry in iterator}
    if first != second:
        _refuse(Code.UNEXPECTED_MUTATION)
    return first


def _image_pair(
    private_root: Path,
    workspace_root: Path,
    owner: inspection.EffectiveOSOwner,
    proposed: intents.PrivateTransactionIntent,
) -> None:
    """Native exact-before images, with two observations of both files."""
    registry_first = registry_image._read_windows(private_root, owner)
    descriptor_first = descriptor_image._read_windows(workspace_root)
    descriptor_second = descriptor_image._read_windows(workspace_root)
    registry_second = registry_image._read_windows(private_root, owner)
    if (
        registry_first.state
        is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
        or registry_second.state
        is not registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
        or descriptor_first.state
        is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
        or descriptor_second.state
        is not descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
        or type(registry_first.image) is not bytes
        or type(registry_second.image) is not bytes
        or type(descriptor_first.image) is not bytes
        or type(descriptor_second.image) is not bytes
    ):
        _refuse(Code.RETAINED_ANCHOR_REFUSED)
    if (
        registry_first.image != registry_second.image
        or descriptor_first.image != descriptor_second.image
    ):
        _refuse(Code.UNEXPECTED_MUTATION)
    if (
        registry_first.image != proposed.registry_before
        or descriptor_first.image != proposed.descriptor_before
    ):
        _refuse(Code.RETAINED_ANCHOR_REFUSED)


def _expected_entry(
    directory: Path,
    tx: str,
    canonical: bytes,
    owner: inspection.EffectiveOSOwner,
) -> None:
    name = tx + ".json"
    if _names(directory) != {name}:
        _refuse(Code.UNEXPECTED_MUTATION)
    for _ in range(2):
        seen = journal._read_windows(directory, tx, owner)
        if (
            seen.state is not journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
            or type(seen.image) is not bytes
            or seen.image != canonical
        ):
            _refuse(Code.FILE_UNQUALIFIED)
    if _names(directory) != {name}:
        _refuse(Code.UNEXPECTED_MUTATION)


@contextmanager
def _hold_windows_expected_journal_create(
    private_root: Path,
    workspace_root: Path,
    proposed: intents.PrivateTransactionIntent,
    canonical: bytes,
) -> Iterator[None]:
    """Retain Windows local locks, registry, workspace and journal handles.

    The native journal guard intentionally checks file ID and DACL rather than
    immutable directory timestamps. Any post-creation refusal preserves the
    candidate for manual recovery review; no automatic cleanup or retry.
    """
    with ordered._hold_existing_ordered_coordination(private_root, workspace_root):
        owner = ordered._owner()
        if owner.kind != "windows_token_sid" or not owner.value:
            _refuse(Code.OWNER_UNAVAILABLE)
        directory = private_root / "transactions"
        with registry_guard._held_windows_registry(private_root, owner):
            with descriptor_guard._held_windows_descriptor(workspace_root):
                with journal_guard._held_windows(directory, owner):
                    if _names(directory):
                        _refuse(Code.PENDING_RECOVERY_REQUIRED)
                    _image_pair(private_root, workspace_root, owner, proposed)
                    if _names(directory):
                        _refuse(Code.PENDING_RECOVERY_REQUIRED)
                    if ordered._owner() != owner:
                        _refuse(Code.OWNER_CHANGED)
                    yield
                    if ordered._owner() != owner:
                        _refuse(Code.OWNER_CHANGED)
                    if not _names(directory):
                        _refuse(Code.MISSING_EXPECTED_ENTRY)
                    _expected_entry(
                        directory, proposed.witness.transaction_id, canonical, owner
                    )
                    _image_pair(private_root, workspace_root, owner, proposed)
                    if _names(directory) != {proposed.witness.transaction_id + ".json"}:
                        _refuse(Code.UNEXPECTED_MUTATION)
                    if ordered._owner() != owner:
                        _refuse(Code.OWNER_CHANGED)


@contextmanager
def hold_expected_windows_private_journal_creation(
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> Iterator[None]:
    """Qualify one expected Windows journal candidate, not its admission.

    Explicitly Windows-only; no write token/registry CAS/Notes capability.
    Local locks do not exclude same-user uncooperative writers or cloud sync.
    """
    if sys.platform != "win32":
        _refuse(Code.UNSUPPORTED)
    if (
        type(proposed) is not intents.PrivateTransactionIntent
        or not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_file._requested_root(existing_private_root, "win32")
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(Code.INVALID_REQUEST)
    try:
        if proposed.witness.operation is witness.PrivateBindingOperation.INITIALIZE:
            _refuse(Code.INVALID_REQUEST)
        canonical = intents.encode_private_transaction_intent(proposed)
        checked = intents.decode_private_transaction_intent(canonical)
        if (
            checked != proposed
            or intents.encode_private_transaction_intent(checked) != canonical
            or type(checked.registry_before) is not bytes
            or type(checked.descriptor_before) is not bytes
        ):
            _refuse(Code.INVALID_REQUEST)
    except (
        intents.PrivateIntentError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ):
        _refuse(Code.INVALID_REQUEST)
    try:
        with _hold_windows_expected_journal_create(
            existing_private_root, existing_workspace_root, proposed, canonical
        ):
            yield
    except ordered.PrivateOrderedCoordinationError as error:
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED:
            _refuse(Code.OWNER_CHANGED)
        if error.code is ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE:
            _refuse(Code.OWNER_UNAVAILABLE)
        _refuse(Code.COORDINATION_REFUSED)
    except (
        registry_guard.RetainedRegistryGuardError,
        descriptor_guard.RetainedDescriptorGuardError,
        journal_guard.RetainedJournalGuardError,
    ):
        _refuse(Code.RETAINED_ANCHOR_REFUSED)
    except FileNotFoundError:
        _refuse(Code.UNEXPECTED_MUTATION)
    except PermissionError:
        _refuse(Code.ACCESS_DENIED)
    except (OSError, TypeError, ValueError, AttributeError, OverflowError):
        _refuse(Code.IO_ERROR)
