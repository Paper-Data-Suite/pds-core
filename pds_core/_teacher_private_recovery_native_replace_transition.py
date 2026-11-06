"""Bounded, non-authorizing native replacement outcome contract (#238 3G39).

Only a fixed, canonical, *disposable* two-root replacement (3G34) can be
rehearsed. On Windows an independent, disposable NO_DELETE_SHARE probe must
first observe the expected sharing refusal. The probe does not establish
sharing on the later replacement and never qualifies a production operation.

Classify interruption boundaries, native refusal families and post-attempt
ambiguity conservatively. No caller paths, bytes, transactions, handles,
callbacks, previous 3G38 reviews, retries, production writers, journal
retirement or Notes API are accepted. Even the success state is only scratch
observation, NOT an authorization or durable-commit proof.
"""

from __future__ import annotations

import errno
import sys
from dataclasses import dataclass, field
from enum import Enum

from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_windows_share as sharing
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission


class PrivateNativeReplaceRefusal(str, Enum):
    WINDOWS_ACCESS_DENIED = "windows_access_denied"
    WINDOWS_SHARING_VIOLATION = "windows_sharing_violation"
    WINDOWS_LOCK_VIOLATION = "windows_lock_violation"
    POSIX_PERMISSION_REFUSED = "posix_permission_refused"
    UNKNOWN_IO_REFUSED = "unknown_io_refused"
    INVALID_ERROR = "invalid_error"


class PrivateNativeReplaceTransitionState(str, Enum):
    SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED = (
        "scratch_replacement_observed_unqualified"
    )
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    WINDOWS_SHARING_PROBE_REFUSED = "windows_sharing_probe_refused"
    CANONICAL_INTENT_REFUSED = "canonical_intent_refused"
    PRE_ATTEMPT_REFUSED_PRESERVE = "pre_attempt_refused_preserve"
    PRE_ATTEMPT_INTERRUPTED_PRESERVE = "pre_attempt_interrupted_preserve"
    NATIVE_REPLACEMENT_REFUSED_PRESERVE = "native_replacement_refused_preserve"
    POST_ATTEMPT_UNKNOWN_PRESERVE = "post_attempt_unknown_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    GUARD_REFUSED_PRESERVE = "guard_refused_preserve"
    PROTOCOL_CONFLICT_PRESERVE = "protocol_conflict_preserve"


_MESSAGES: dict[PrivateNativeReplaceTransitionState, str] = {
    PrivateNativeReplaceTransitionState.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED: (
        "Disposable canonical replacement was observed. No production admission or durable commit."
    ),
    PrivateNativeReplaceTransitionState.INVALID_REQUEST: "Invalid bounded transition request.",
    PrivateNativeReplaceTransitionState.OPERATION_NOT_ADMITTED: "Only the prepared stage-to-registry step is modeled.",
    PrivateNativeReplaceTransitionState.UNSUPPORTED: "Native synthetic transition is unsupported on this platform.",
    PrivateNativeReplaceTransitionState.WINDOWS_SHARING_PROBE_REFUSED: (
        "Independent Windows scratch sharing probe did not show required refusal."
    ),
    PrivateNativeReplaceTransitionState.CANONICAL_INTENT_REFUSED: "Canonical synthetic transaction did not qualify.",
    PrivateNativeReplaceTransitionState.PRE_ATTEMPT_REFUSED_PRESERVE: (
        "Synthetic evidence was refused before a replace attempt; preserve pending evidence."
    ),
    PrivateNativeReplaceTransitionState.PRE_ATTEMPT_INTERRUPTED_PRESERVE: (
        "Injected interruption occurred before the modeled native replacement attempt."
    ),
    PrivateNativeReplaceTransitionState.NATIVE_REPLACEMENT_REFUSED_PRESERVE: (
        "Native scratch replacement was refused; no fallback or automatic retry."
    ),
    PrivateNativeReplaceTransitionState.POST_ATTEMPT_UNKNOWN_PRESERVE: (
        "Replacement may have occurred; exact restart review is required, never blind retry."
    ),
    PrivateNativeReplaceTransitionState.POSTIMAGE_CONFLICT_PRESERVE: (
        "After-image or retained custody conflicted; preserve transaction evidence."
    ),
    PrivateNativeReplaceTransitionState.GUARD_REFUSED_PRESERVE: (
        "Native scratch guard acquisition or release failed; no durable-state assertion."
    ),
    PrivateNativeReplaceTransitionState.PROTOCOL_CONFLICT_PRESERVE: (
        "Synthetic transition result contradicted its selected interruption boundary."
    ),
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateNativeReplaceTransitionReview:
    """Sanitized observation, always requiring pending evidence preservation.

    `replacement_may_have_occurred` is an intentionally conservative recovery
    hint, NOT a verified commit, a write permission or a replay decision.
    """

    state: PrivateNativeReplaceTransitionState
    message: str
    replacement_may_have_occurred: bool
    pending_evidence_must_remain: bool
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateNativeReplaceTransitionReview(non_authorizing=True)"


def _result(
    state: PrivateNativeReplaceTransitionState,
    *,
    attempted_or_unknown: bool = True,
) -> PrivateNativeReplaceTransitionReview:
    return PrivateNativeReplaceTransitionReview(
        state,
        _MESSAGES[state],
        attempted_or_unknown,
        True,
        barrier._REQUIRED,
    )


def classify_native_replace_refusal(error: OSError) -> PrivateNativeReplaceRefusal:
    """Classify one native error without returning a retry/fallback instruction.

    The Windows codes are 5 (access denied), 32 (sharing violation) and 33
    (lock violation). Unknown cases are NOT normalized into permission to retry.
    The classification is descriptive even if `error` is artificially supplied.
    """
    kind = PrivateNativeReplaceRefusal
    if not isinstance(error, OSError):
        return kind.INVALID_ERROR
    winerror = getattr(error, "winerror", None)
    if type(winerror) is int:
        by_winerror = {
            5: kind.WINDOWS_ACCESS_DENIED,
            32: kind.WINDOWS_SHARING_VIOLATION,
            33: kind.WINDOWS_LOCK_VIOLATION,
        }
        return by_winerror.get(winerror, kind.UNKNOWN_IO_REFUSED)
    if isinstance(error, PermissionError) or error.errno in {errno.EACCES, errno.EPERM}:
        return kind.POSIX_PERMISSION_REFUSED
    return kind.UNKNOWN_IO_REFUSED


_BEFORE_ATTEMPT = frozenset(
    {
        canonical.PrivateCanonicalReplaceFault.AFTER_LOCK,
        canonical.PrivateCanonicalReplaceFault.AFTER_PARENTS,
        canonical.PrivateCanonicalReplaceFault.AFTER_CANONICAL_ADMISSION,
        canonical.PrivateCanonicalReplaceFault.AFTER_PREIMAGE,
        canonical.PrivateCanonicalReplaceFault.AFTER_READER_RELEASE,
        canonical.PrivateCanonicalReplaceFault.BEFORE_REPLACE,
    }
)
_AFTER_ATTEMPT = frozenset(
    {
        canonical.PrivateCanonicalReplaceFault.AFTER_REPLACE,
        canonical.PrivateCanonicalReplaceFault.AFTER_POSTIMAGE,
        canonical.PrivateCanonicalReplaceFault.AFTER_FILE_SYNC,
        canonical.PrivateCanonicalReplaceFault.AFTER_PARENT_RELEASE,
    }
)
_PRE_REFUSALS = frozenset(
    {
        canonical.PrivateCanonicalReplaceState.PREIMAGE_REFUSED,
        canonical.PrivateCanonicalReplaceState.NAMESPACE_CONFLICT_PRESERVE,
        canonical.PrivateCanonicalReplaceState.READER_CONFLICT_PRESERVE,
        canonical.PrivateCanonicalReplaceState.ADMISSION_DRIFT_PRESERVE,
    }
)


def _classify_scratch_result(
    observed: canonical.PrivateCanonicalReplaceReview,
    fault: canonical.PrivateCanonicalReplaceFault,
) -> PrivateNativeReplaceTransitionReview:
    """Map only exact 3G34 result shapes; fail closed on contradictions."""
    state = PrivateNativeReplaceTransitionState
    old = canonical.PrivateCanonicalReplaceState
    if (
        type(observed) is not canonical.PrivateCanonicalReplaceReview
        or type(observed.state) is not old
    ):
        return _result(state.PROTOCOL_CONFLICT_PRESERVE)
    outcome = observed.state
    if fault is not canonical.PrivateCanonicalReplaceFault.NONE:
        if outcome is old.INTERRUPTED_PRESERVE:
            if fault in _BEFORE_ATTEMPT:
                return _result(
                    state.PRE_ATTEMPT_INTERRUPTED_PRESERVE, attempted_or_unknown=False
                )
            if fault in _AFTER_ATTEMPT:
                return _result(state.POST_ATTEMPT_UNKNOWN_PRESERVE)
        # Injection not reached: a refusal may occur before the requested boundary.
        if outcome is old.SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED:
            return _result(state.PROTOCOL_CONFLICT_PRESERVE)
    elif outcome is old.INTERRUPTED_PRESERVE:
        # An unscheduled real interruption cannot be placed before the native call.
        return _result(state.POST_ATTEMPT_UNKNOWN_PRESERVE)
    if outcome is old.SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED:
        return _result(state.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED)
    if outcome is old.CANONICAL_INTENT_REFUSED:
        return _result(state.CANONICAL_INTENT_REFUSED, attempted_or_unknown=False)
    if outcome in _PRE_REFUSALS:
        return _result(state.PRE_ATTEMPT_REFUSED_PRESERVE, attempted_or_unknown=False)
    if outcome is old.REPLACEMENT_REFUSED_PRESERVE:
        return _result(state.NATIVE_REPLACEMENT_REFUSED_PRESERVE)
    if outcome in {
        old.POSTIMAGE_CONFLICT_PRESERVE,
        old.IMAGE_CONFLICT_PRESERVE,
        old.FILE_CONFLICT_PRESERVE,
        old.PARENT_CONFLICT_PRESERVE,
    }:
        return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
    if outcome is old.GUARD_REFUSED:
        return _result(state.GUARD_REFUSED_PRESERVE)
    if outcome is old.UNSUPPORTED:
        return _result(state.UNSUPPORTED, attempted_or_unknown=False)
    if outcome is old.OPERATION_NOT_ADMITTED:
        return _result(state.PROTOCOL_CONFLICT_PRESERVE)
    # An I/O error, malformed result, or unknown phase cannot establish whether
    # a replace was attempted. Preserve and require an independent restart review.
    return _result(state.POST_ATTEMPT_UNKNOWN_PRESERVE)


def rehearse_synthetic_native_replace_transition(
    step: admission.PrivateScratchWriterStep = admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
    interruption: canonical.PrivateCanonicalReplaceFault = canonical.PrivateCanonicalReplaceFault.NONE,
) -> PrivateNativeReplaceTransitionReview:
    """Run only 3G34's internally generated disposable canonical transaction.

    On Windows first run 3G24's independent NO_DELETE_SHARE scratch probe.
    This is an environmental diagnostic, not a retained destination handle;
    it never makes the subsequent replacement safe for production.
    """
    state = PrivateNativeReplaceTransitionState
    if (
        type(step) is not admission.PrivateScratchWriterStep
        or type(interruption) is not canonical.PrivateCanonicalReplaceFault
    ):
        return _result(state.INVALID_REQUEST, attempted_or_unknown=False)
    if step is not admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED, attempted_or_unknown=False)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED, attempted_or_unknown=False)
    try:
        if sys.platform == "win32":
            try:
                observed_share = sharing.rehearse_synthetic_private_windows_sharing(
                    sharing.PrivateSyntheticWindowsShareMode.NO_DELETE_SHARE
                )
            except (
                KeyboardInterrupt,
                OSError,
                TypeError,
                ValueError,
                RuntimeError,
                AttributeError,
            ):
                # The actual canonical scratch replacement has not been called.
                return _result(
                    state.WINDOWS_SHARING_PROBE_REFUSED, attempted_or_unknown=False
                )
            if (
                type(observed_share) is not sharing.PrivateSyntheticWindowsShareReview
                or observed_share.state
                is not sharing.PrivateSyntheticWindowsShareState.NO_DELETE_SHARE_BLOCKED_UNQUALIFIED
            ):
                return _result(
                    state.WINDOWS_SHARING_PROBE_REFUSED, attempted_or_unknown=False
                )
        observed = canonical.rehearse_synthetic_canonical_two_root_replace(
            step, interruption
        )
        return _classify_scratch_result(observed, interruption)
    except KeyboardInterrupt:
        return _result(state.POST_ATTEMPT_UNKNOWN_PRESERVE)
    except (
        OSError,
        TypeError,
        ValueError,
        RuntimeError,
        AttributeError,
        OverflowError,
    ):
        return _result(state.POST_ATTEMPT_UNKNOWN_PRESERVE)
