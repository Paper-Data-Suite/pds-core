"""Read-only paired private-registry/workspace-sidecar observation (#238 3C5).

The protected registry lock brackets two individually verified registry reads
and two individually verified, untrusted workspace descriptor reads. This is
NOT an atomic cross-filesystem snapshot, approved association, CAS reservation,
workspace ownership decision, writable handle, or Notes service.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_registry_snapshot as registry


class PrivatePairObservationState(str, Enum):
    OBSERVED_UNQUALIFIED = "observed_unqualified"
    MISSING_REGISTRY = "missing_registry"
    MISSING_DESCRIPTOR = "missing_descriptor"
    REFUSED_REGISTRY = "refused_registry"
    REFUSED_DESCRIPTOR = "refused_descriptor"
    CHANGED_DURING_OBSERVATION = "changed_during_observation"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"


_MESSAGES = {
    PrivatePairObservationState.OBSERVED_UNQUALIFIED: "Both documents observed repeatedly; no association is authorized.",
    PrivatePairObservationState.MISSING_REGISTRY: "Private registry missing; absence does not establish a new store.",
    PrivatePairObservationState.MISSING_DESCRIPTOR: "Workspace association descriptor missing; no binding inferred.",
    PrivatePairObservationState.REFUSED_REGISTRY: "Registry inspection refused; no binding inferred.",
    PrivatePairObservationState.REFUSED_DESCRIPTOR: "Workspace descriptor inspection refused; no binding inferred.",
    PrivatePairObservationState.CHANGED_DURING_OBSERVATION: "Documents changed or could not be observed consistently; retry only after review.",
    PrivatePairObservationState.COORDINATION_UNAVAILABLE: "Private registry coordination unavailable.",
    PrivatePairObservationState.INVALID_REQUEST: "Paired observation request invalid.",
    PrivatePairObservationState.UNSUPPORTED: "Paired observation unsupported on this platform.",
}


@dataclass(frozen=True, slots=True)
class PrivatePairObservation:
    """Non-authorizing data from one completed observation, not commit tokens."""

    state: PrivatePairObservationState
    message: str
    registry_revision: int | None = None
    registry_binding_count: int | None = None
    association_id: str | None = field(default=None, repr=False)
    registry_sha256: str | None = field(default=None, repr=False)
    descriptor_sha256: str | None = field(default=None, repr=False)


def _result(state: PrivatePairObservationState) -> PrivatePairObservation:
    return PrivatePairObservation(state, _MESSAGES[state])


def _registry_read(root: Path) -> registry.PrivateRegistrySnapshot:
    """Caller already holds .registry.lock; never recursively reacquire it."""
    if sys.platform == "linux":
        return registry._linux_read(root)
    return registry._windows_read(root)


def _same_registry(
    before: registry.PrivateRegistrySnapshot, after: registry.PrivateRegistrySnapshot
) -> bool:
    return (
        before.state is after.state
        and before.revision == after.revision
        and before.binding_count == after.binding_count
        and before.sha256 == after.sha256
    )


def _same_descriptor(
    before: descriptor.PrivateDescriptorSnapshot,
    after: descriptor.PrivateDescriptorSnapshot,
) -> bool:
    return (
        before.state is after.state
        and before.association_id == after.association_id
        and before.sha256 == after.sha256
    )


def _classify(
    first_registry: registry.PrivateRegistrySnapshot,
    first_descriptor: descriptor.PrivateDescriptorSnapshot,
    second_descriptor: descriptor.PrivateDescriptorSnapshot,
    second_registry: registry.PrivateRegistrySnapshot,
) -> PrivatePairObservation:
    if not _same_registry(first_registry, second_registry) or not _same_descriptor(
        first_descriptor, second_descriptor
    ):
        return _result(PrivatePairObservationState.CHANGED_DURING_OBSERVATION)
    if first_registry.state is registry.PrivateRegistrySnapshotState.MISSING:
        return _result(PrivatePairObservationState.MISSING_REGISTRY)
    if (
        first_registry.state
        is not registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED
    ):
        return _result(PrivatePairObservationState.REFUSED_REGISTRY)
    if first_descriptor.state in {
        descriptor.PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR,
        descriptor.PrivateDescriptorSnapshotState.MISSING_METADATA_DIRECTORY,
    }:
        return _result(PrivatePairObservationState.MISSING_DESCRIPTOR)
    if (
        first_descriptor.state
        is not descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED
    ):
        return _result(PrivatePairObservationState.REFUSED_DESCRIPTOR)
    if (
        first_registry.revision is None
        or first_registry.binding_count is None
        or first_registry.sha256 is None
        or first_descriptor.association_id is None
        or first_descriptor.sha256 is None
    ):
        return _result(PrivatePairObservationState.CHANGED_DURING_OBSERVATION)
    return PrivatePairObservation(
        PrivatePairObservationState.OBSERVED_UNQUALIFIED,
        _MESSAGES[PrivatePairObservationState.OBSERVED_UNQUALIFIED],
        registry_revision=first_registry.revision,
        registry_binding_count=first_registry.binding_count,
        association_id=first_descriptor.association_id,
        registry_sha256=first_registry.sha256,
        descriptor_sha256=first_descriptor.sha256,
    )


def observe_private_registry_and_workspace_descriptor(
    existing_private_root: Path, existing_workspace_root: Path
) -> PrivatePairObservation:
    """Observe twice under the existing registry lock; never write or bind.

    The external/synced workspace is not locked against third-party changes.
    Even an OBSERVED_UNQUALIFIED result does not establish that the descriptor
    UUID is present in, owned by, or approved within the private registry.
    """
    if sys.platform not in {"linux", "win32"}:
        return _result(PrivatePairObservationState.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not lock_provision._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        return _result(PrivatePairObservationState.INVALID_REQUEST)
    try:
        with locking.hold_existing_private_lock(
            existing_private_root / ".registry.lock"
        ):
            first_registry = _registry_read(existing_private_root)
            first_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_descriptor = descriptor.inspect_workspace_descriptor(
                existing_workspace_root
            )
            second_registry = _registry_read(existing_private_root)
            return _classify(
                first_registry, first_descriptor, second_descriptor, second_registry
            )
    except locking.PrivateExistingFileLockError:
        return _result(PrivatePairObservationState.COORDINATION_UNAVAILABLE)
    except (OSError, ValueError, AttributeError, TypeError, OverflowError):
        return _result(PrivatePairObservationState.CHANGED_DURING_OBSERVATION)
