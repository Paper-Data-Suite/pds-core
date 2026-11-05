"""Pure Windows native-handle sharing contract review (Core #238 Slice 3G25).

Accepts only exact, bounded observations of the existing read-only helper
CreateFileW access and share masks. No filesystem paths, handles, bytes,
callbacks, native calls, writer permits or mutable production state enter here.
An exact match records source-level compatibility ONLY; it does not prove
retained HANDLE custody, replacement safety, cloud coordination or durability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PrivateWindowsHandleRole(str, Enum):
    JOURNAL_DIRECTORY = "journal_directory"
    RETAINED_REGISTRY = "retained_registry"
    DESCRIPTOR_DIRECTORY = "descriptor_directory"
    RETAINED_DESCRIPTOR = "retained_descriptor"
    REGISTRY_IMAGE_READ = "registry_image_read"


class PrivateWindowsHandleContractState(str, Enum):
    ADVISORY_SHARING_REVIEW_REQUIRED = "advisory_sharing_review_required"
    CONTRACT_DRIFT_PRESERVE = "contract_drift_preserve"
    INCOMPLETE_OR_DUPLICATE_REFUSED = "incomplete_or_duplicate_refused"
    INVALID_REQUEST = "invalid_request"


_MESSAGES = {
    PrivateWindowsHandleContractState.ADVISORY_SHARING_REVIEW_REQUIRED: (
        "Supplied masks match the reviewed source contract: retained handles share delete "
        "while the separate registry image reader denies write/delete sharing. "
        "No production mutation, native custody or durability is authorized."
    ),
    PrivateWindowsHandleContractState.CONTRACT_DRIFT_PRESERVE: (
        "An observed read-only native handle access/share contract differs from "
        "the reviewed baseline; preserve evidence and requalify."
    ),
    PrivateWindowsHandleContractState.INCOMPLETE_OR_DUPLICATE_REFUSED: (
        "Every handle role must be reported once, with no extra entries."
    ),
    PrivateWindowsHandleContractState.INVALID_REQUEST: (
        "Only bounded exact Windows access/share-mask observations are accepted."
    ),
}


@dataclass(frozen=True, slots=True)
class PrivateWindowsHandleObservation:
    role: PrivateWindowsHandleRole
    desired_access: int
    share_mask: int


@dataclass(frozen=True, slots=True)
class PrivateWindowsHandleContractReview:
    state: PrivateWindowsHandleContractState
    message: str


def _result(
    state: PrivateWindowsHandleContractState,
) -> PrivateWindowsHandleContractReview:
    return PrivateWindowsHandleContractReview(state, _MESSAGES[state])


# Windows FILE_SHARE_READ/WRITE/DELETE mask = 0x7. The registry image reader's
# 0x1 mask allows READ sharing only; it is NOT a durable commit fence.
_EXPECTED: tuple[tuple[PrivateWindowsHandleRole, int, int], ...] = (
    (PrivateWindowsHandleRole.JOURNAL_DIRECTORY, 0x80 | 0x20000, 0x7),
    (PrivateWindowsHandleRole.RETAINED_REGISTRY, 0x80 | 0x20000, 0x7),
    (PrivateWindowsHandleRole.DESCRIPTOR_DIRECTORY, 0x80 | 0x1, 0x7),
    (PrivateWindowsHandleRole.RETAINED_DESCRIPTOR, 0x80 | 0x1, 0x7),
    (PrivateWindowsHandleRole.REGISTRY_IMAGE_READ, 0x80000000 | 0x20000, 0x1),
)


def review_native_private_windows_handle_contracts(
    observations: tuple[PrivateWindowsHandleObservation, ...],
) -> PrivateWindowsHandleContractReview:
    """Classify *supplied* mask observations without native I/O or authority.

    The function does not inspect a running OS or verify that the masks came
    from the actual helpers; qualification tests bind these values to the
    committed helper implementations. Results never confer replacement rights.
    """
    state = PrivateWindowsHandleContractState
    if type(observations) is not tuple or len(observations) != len(_EXPECTED):
        return _result(state.INVALID_REQUEST)
    if any(
        type(item) is not PrivateWindowsHandleObservation
        or type(item.role) is not PrivateWindowsHandleRole
        or type(item.desired_access) is not int
        or type(item.share_mask) is not int
        or item.desired_access < 0
        or item.desired_access > 0xFFFFFFFF
        or item.share_mask < 0
        or item.share_mask > 0x7
        for item in observations
    ):
        return _result(state.INVALID_REQUEST)
    unique = {item.role for item in observations}
    if len(unique) != len(_EXPECTED) or unique != {entry[0] for entry in _EXPECTED}:
        return _result(state.INCOMPLETE_OR_DUPLICATE_REFUSED)
    observed = {
        item.role: (item.desired_access, item.share_mask) for item in observations
    }
    if any(observed[role] != (access, share) for role, access, share in _EXPECTED):
        return _result(state.CONTRACT_DRIFT_PRESERVE)
    return _result(state.ADVISORY_SHARING_REVIEW_REQUIRED)
