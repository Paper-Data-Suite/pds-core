"""Windows post-attempt recovery policy for Core #238 Slice 3G50.

A successful Windows directory flush request is *not* an established on-disk
namespace guarantee for a two-document private transaction. Combine a fresh,
independently guarded native restart review (3G47) with the disposable native
three-parent flush census (3G49). Both are required before returning a bounded
recovery disposition. A scratch probe is never evidence about the actual
private root, and no disposition grants a write, retry, commit, or retirement.

Only the existing native restart reader can inspect a caller's real private
root. This module itself has no mutation code, lock release token, or writer.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_recovery_post_attempt_restart as restart
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import (
    _teacher_private_recovery_windows_directory_durability_probe as probe,
)
from pds_core import _teacher_private_transaction_intent as intents


class PrivateWindowsRestartPolicyState(str, Enum):
    """Non-authorizing recovery dispositions for current native observations."""

    PREPARED_STAGE_HOLD_NO_RETRY = "prepared_stage_hold_no_retry"
    REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD = "registry_after_descriptor_pending_hold"
    BOTH_AFTER_JOURNAL_PENDING_HOLD = "both_after_journal_pending_hold"
    NATIVE_RESTART_UNQUALIFIED_PRESERVE = "native_restart_unqualified_preserve"
    DIRECTORY_PROBE_UNQUALIFIED_PRESERVE = "directory_probe_unqualified_preserve"
    CONTRADICTORY_EVIDENCE_PRESERVE = "contradictory_evidence_preserve"
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR_PRESERVE = "io_error_preserve"


_MESSAGES: dict[PrivateWindowsRestartPolicyState, str] = {
    state: "Windows recovery policy remains unqualified; preserve pending evidence."
    for state in PrivateWindowsRestartPolicyState
}
_MESSAGES[PrivateWindowsRestartPolicyState.PREPARED_STAGE_HOLD_NO_RETRY] = (
    "Prepared registry and stage were independently observed; do not automatically "
    "retry a possibly attempted operation."
)
_MESSAGES[PrivateWindowsRestartPolicyState.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD] = (
    "Registry after-image was independently observed; descriptor completion "
    "requires a distinct qualified operation and restart protocol."
)
_MESSAGES[PrivateWindowsRestartPolicyState.BOTH_AFTER_JOURNAL_PENDING_HOLD] = (
    "Both metadata after-images were independently observed; no durable commit "
    "or journal retirement is established."
)
_MESSAGES[PrivateWindowsRestartPolicyState.DIRECTORY_PROBE_UNQUALIFIED_PRESERVE] = (
    "Scratch directory flush requests were refused or unavailable; the native "
    "recovery checkpoint remains pending."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateWindowsRestartPolicyReview:
    """Sanitized decision, never an operation or persistence certificate."""

    state: PrivateWindowsRestartPolicyState
    message: str
    native_restart_state: restart.PrivatePostAttemptRestartState | None = field(
        default=None, repr=False
    )
    scratch_directory_state: probe.PrivateDirectoryFlushState | None = field(
        default=None, repr=False
    )
    pending_evidence_must_remain: bool = True
    automatic_retry_forbidden: bool = True
    journal_retirement_forbidden: bool = True
    production_writes_blocked: bool = True
    directory_durability_unqualified: bool = True
    durable_commit_unqualified: bool = True

    def __repr__(self) -> str:
        return "PrivateWindowsRestartPolicyReview(non_authorizing=True)"


def _result(
    state: PrivateWindowsRestartPolicyState,
    native: restart.PrivatePostAttemptRestartState | None = None,
    directory: probe.PrivateDirectoryFlushState | None = None,
) -> PrivateWindowsRestartPolicyReview:
    return PrivateWindowsRestartPolicyReview(state, _MESSAGES[state], native, directory)


_RECOVERY_STATES: dict[
    restart.PrivatePostAttemptRestartState, PrivateWindowsRestartPolicyState
] = {
    restart.PrivatePostAttemptRestartState.PREPARED_STAGE_PENDING_REVIEW: PrivateWindowsRestartPolicyState.PREPARED_STAGE_HOLD_NO_RETRY,
    restart.PrivatePostAttemptRestartState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW: PrivateWindowsRestartPolicyState.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
    restart.PrivatePostAttemptRestartState.BOTH_AFTER_JOURNAL_PENDING_REVIEW: PrivateWindowsRestartPolicyState.BOTH_AFTER_JOURNAL_PENDING_HOLD,
}


def _qualified_returned_probe(observed: probe.PrivateDirectoryFlushReview) -> bool:
    """All three scratch calls returned, without producing a durability claim."""
    kind = probe.PrivateDirectoryFlushObservation
    return (
        observed.state is probe.PrivateDirectoryFlushState.REQUESTS_RETURNED_UNQUALIFIED
        and type(observed.observations) is tuple
        and observed.observations
        == (
            ("journal", kind.RETURNED_UNQUALIFIED),
            ("registry", kind.RETURNED_UNQUALIFIED),
            ("descriptor", kind.RETURNED_UNQUALIFIED),
        )
    )


def review_windows_private_pending_recovery_policy(
    step: scratch.PrivateScratchWriterStep,
    expected_revision: int,
    proposed: intents.PrivateTransactionIntent,
    existing_private_root: Path,
    existing_workspace_root: Path,
) -> PrivateWindowsRestartPolicyReview:
    """Perform fresh native restart review then a disposable flush diagnostic.

    The diagnostic runs independently on newly created scratch directories,
    not under the teacher-private root. Neither a returned flush nor a matching
    checkpoint authorizes a production write, automatic retry, journal deletion,
    or normal Notes access. The pending journal remains required even when
    both metadata after-images match.
    """
    state = PrivateWindowsRestartPolicyState
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
    if sys.platform != "win32":
        return _result(state.UNSUPPORTED)
    native_state: restart.PrivatePostAttemptRestartState | None = None
    try:
        # Independent native owner/binding/journal/registry/descriptor reader.
        native = restart.review_private_post_attempt_native_restart(
            step,
            expected_revision,
            proposed,
            existing_private_root,
            existing_workspace_root,
        )
        if type(native) is not restart.PrivatePostAttemptRestartReview:
            return _result(state.CONTRADICTORY_EVIDENCE_PRESERVE)
        if (
            native.pending_evidence_must_remain is not True
            or native.automatic_retry_forbidden is not True
            or native.production_writes_blocked is not True
            or type(native.state) is not restart.PrivatePostAttemptRestartState
        ):
            return _result(state.CONTRADICTORY_EVIDENCE_PRESERVE)
        native_state = native.state
        disposition = _RECOVERY_STATES.get(native_state)
        if disposition is None:
            return _result(state.NATIVE_RESTART_UNQUALIFIED_PRESERVE, native_state)

        # This DOES NOT sample the private root's filesystem capabilities.
        # Even successful scratch calls cannot qualify directory persistence.
        sample = probe.probe_private_windows_directory_flush_contract()
        if type(sample) is not probe.PrivateDirectoryFlushReview:
            return _result(state.CONTRADICTORY_EVIDENCE_PRESERVE, native_state)
        if (
            sample.production_writes_blocked is not True
            or sample.journal_retirement_forbidden is not True
            or sample.pending_evidence_must_remain is not True
            or sample.directory_durability_unqualified is not True
            or type(sample.state) is not probe.PrivateDirectoryFlushState
        ):
            return _result(state.CONTRADICTORY_EVIDENCE_PRESERVE, native_state)
        if not _qualified_returned_probe(sample):
            return _result(
                state.DIRECTORY_PROBE_UNQUALIFIED_PRESERVE,
                native_state,
                sample.state,
            )
        return _result(disposition, native_state, sample.state)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE, native_state)
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.IO_ERROR_PRESERVE, native_state)
