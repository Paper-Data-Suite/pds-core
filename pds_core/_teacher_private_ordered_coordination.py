"""Local, ordered two-file coordination for Core #238 Slice 3C9.

The owner-private registry lock is ALWAYS acquired before the (possibly
cloud-synced) workspace lock. This helper creates no file, emits no credential,
and grants no binding/metadata/Notes-write authority. The locks coordinate only
processes on the same local filesystem that honor the protocol. No code may
infer distributed/OneDrive locking, native handle continuity, or a CAS grant.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack, contextmanager
from enum import Enum
from pathlib import Path
from typing import Iterator, NoReturn

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as registry_provision

_REGISTRY_LOCK = ".registry.lock"
_WORKSPACE_METADATA = ".pds"
_WORKSPACE_LOCK = ".teacher-private-association.lock"


class PrivateOrderedCoordinationCode(str, Enum):
    """Sanitized failure categories; never contain a private path/owner."""

    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_CHANGED = "owner_changed"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"
    IO_ERROR = "io_error"


class PrivateOrderedCoordinationError(RuntimeError):
    """No path, OS principal, or metadata bytes escape in the error."""

    def __init__(self, code: PrivateOrderedCoordinationCode) -> None:
        self.code = code
        super().__init__(f"Private ordered coordination refused: {code.value}.")


def _refuse(code: PrivateOrderedCoordinationCode) -> NoReturn:
    raise PrivateOrderedCoordinationError(code)


def _owner() -> inspection.EffectiveOSOwner:
    try:
        result = inspection._effective_owner(sys.platform)
    except (inspection._OwnerUnverifiable, OSError, AttributeError, ValueError):
        _refuse(PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE)
    expected = "windows_token_sid" if sys.platform == "win32" else "posix_euid"
    if result.kind != expected or not result.value:
        _refuse(PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE)
    if sys.platform == "linux":
        # A local root login falls outside this ordinary-user trust boundary.
        if not result.value.isdecimal() or int(result.value) <= 0:
            _refuse(PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE)
    return result


def _acquire(stack: ExitStack, file: Path) -> None:
    """No automatic lock creation, polling, stale-lock deletion or retry."""
    try:
        stack.enter_context(locking.hold_existing_private_lock(file))
    except locking.PrivateExistingFileLockError:
        _refuse(PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        _refuse(PrivateOrderedCoordinationCode.IO_ERROR)


@contextmanager
def _hold_existing_ordered_coordination(
    existing_private_root: Path, existing_workspace_root: Path
) -> Iterator[None]:
    """Acquire registry then workspace local locks; release in reverse order.

    The private root must match the exact v1 OS-user-local candidate and the
    workspace must have acceptable Core syntax. Both lock files must already
    exist and be qualified by the lower-level existing-file lock primitive.
    Owner identity is sampled before and after acquisition. Neither a lock nor
    matching owner establishes a safe metadata commit: a subsequent writer
    MUST revalidate protected native parent/file handles, registry membership,
    exact expected bytes/revisions and recoverable journal state *while held*.
    Only a dedicated future transaction service may use these guards to write.
    """
    if sys.platform not in {"linux", "win32"}:
        _refuse(PrivateOrderedCoordinationCode.UNSUPPORTED)
    if (
        not isinstance(existing_private_root, Path)
        or not isinstance(existing_workspace_root, Path)
        or not registry_provision._requested_root(existing_private_root, sys.platform)
        or not descriptor._valid_root(existing_workspace_root)
    ):
        _refuse(PrivateOrderedCoordinationCode.INVALID_REQUEST)

    before = _owner()
    with ExitStack() as stack:
        _acquire(stack, existing_private_root / _REGISTRY_LOCK)
        _acquire(
            stack,
            existing_workspace_root / _WORKSPACE_METADATA / _WORKSPACE_LOCK,
        )
        if before != _owner():
            _refuse(PrivateOrderedCoordinationCode.OWNER_CHANGED)
        yield
