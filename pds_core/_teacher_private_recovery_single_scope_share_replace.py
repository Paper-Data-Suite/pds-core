"""Single-scope native sharing and canonical scratch replacement (#238 3G40).

A fixed canonical transaction is staged in an internally created, disposable
TWO-root layout. One synthetic lock and four retained native directory handles
span both preimage admission and a single os.replace. A target read handle and
stage read handle are opened with FILE_SHARE_DELETE on Windows and held across
the replacement attempt. Retained bytes/identities and exact namespace are
rechecked after any reported success. Refusal is not retried.

This module accepts no caller path, byte image, transaction, HANDLE, callback,
writer credential or review certificate. It NEVER mutates real teacher-private
metadata, grants production admission, proves durable directory persistence,
retires a journal, or exposes Notes.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Iterator

from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_native_replace_transition as transition
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_owned_scope as owned
from pds_core import _teacher_private_recovery_synthetic_two_root_replace as two
from pds_core import _teacher_private_recovery_synthetic_windows_share as sharing
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_transaction_intent as intents


class PrivateSingleScopeReplaceFault(str, Enum):
    NONE = "none"
    AFTER_LOCK = "after_lock"
    AFTER_PARENTS = "after_parents"
    AFTER_SHARE_OPEN = "after_share_open"
    AFTER_CANONICAL_ADMISSION = "after_canonical_admission"
    AFTER_READER_CHECK = "after_reader_check"
    BEFORE_REPLACE = "before_replace"
    AFTER_REPLACE = "after_replace"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_FILE_SYNC = "after_file_sync"
    AFTER_GUARD_RELEASE = "after_guard_release"


class PrivateSingleScopeReplaceState(str, Enum):
    SCRATCH_SHARE_SAFE_REPLACEMENT_UNQUALIFIED = (
        "scratch_share_safe_replacement_unqualified"
    )
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    CANONICAL_INTENT_REFUSED = "canonical_intent_refused"
    PREIMAGE_REFUSED = "preimage_refused"
    PARENT_CONFLICT_PRESERVE = "parent_conflict_preserve"
    NATIVE_HANDLE_CONFLICT_PRESERVE = "native_handle_conflict_preserve"
    SHARING_OPEN_REFUSED_PRESERVE = "sharing_open_refused_preserve"
    ADMISSION_DRIFT_PRESERVE = "admission_drift_preserve"
    PRE_ATTEMPT_INTERRUPTED_PRESERVE = "pre_attempt_interrupted_preserve"
    NATIVE_REPLACE_REFUSED_PRESERVE = "native_replace_refused_preserve"
    POST_ATTEMPT_UNKNOWN_PRESERVE = "post_attempt_unknown_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    GUARD_REFUSED_PRESERVE = "guard_refused_preserve"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateSingleScopeReplaceState, str] = {
    PrivateSingleScopeReplaceState.SCRATCH_SHARE_SAFE_REPLACEMENT_UNQUALIFIED: (
        "Disposable canonical replacement observed under held share-safe handles; "
        "no production writer, durable commit or journal retirement."
    ),
    PrivateSingleScopeReplaceState.INVALID_REQUEST: "Unqualified synthetic replacement request.",
    PrivateSingleScopeReplaceState.OPERATION_NOT_ADMITTED: "Only disposable stage-to-registry is modeled.",
    PrivateSingleScopeReplaceState.UNSUPPORTED: "Native scratch sharing rehearsal unsupported.",
    PrivateSingleScopeReplaceState.CANONICAL_INTENT_REFUSED: "Canonical fixed synthetic intent was unqualified.",
    PrivateSingleScopeReplaceState.PREIMAGE_REFUSED: "Disposable starting evidence conflicted.",
    PrivateSingleScopeReplaceState.PARENT_CONFLICT_PRESERVE: "Held synthetic parent identity conflicted.",
    PrivateSingleScopeReplaceState.NATIVE_HANDLE_CONFLICT_PRESERVE: "Held synthetic file identity or bytes conflicted.",
    PrivateSingleScopeReplaceState.SHARING_OPEN_REFUSED_PRESERVE: "Native scratch read handle could not be held with delete sharing.",
    PrivateSingleScopeReplaceState.ADMISSION_DRIFT_PRESERVE: "Final synthetic native preimages drifted.",
    PrivateSingleScopeReplaceState.PRE_ATTEMPT_INTERRUPTED_PRESERVE: "Synthetic interruption occurred before the replacement attempt.",
    PrivateSingleScopeReplaceState.NATIVE_REPLACE_REFUSED_PRESERVE: "Native scratch replacement was refused; no retry.",
    PrivateSingleScopeReplaceState.POST_ATTEMPT_UNKNOWN_PRESERVE: "Native replacement may have occurred; preserve evidence for restart review.",
    PrivateSingleScopeReplaceState.POSTIMAGE_CONFLICT_PRESERVE: "Native scratch postimages, held handles or namespace conflicted.",
    PrivateSingleScopeReplaceState.GUARD_REFUSED_PRESERVE: "Scratch guard acquisition or release refused.",
    PrivateSingleScopeReplaceState.IO_ERROR: "Native synthetic sharing rehearsal encountered unqualified I/O.",
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateSingleScopeReplaceReview:
    """Pathless observation, never an operation permit or replay instruction."""

    state: PrivateSingleScopeReplaceState
    message: str
    replacement_may_have_occurred: bool
    pending_evidence_must_remain: bool
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateSingleScopeReplaceReview(non_authorizing=True)"


def _result(
    state: PrivateSingleScopeReplaceState,
    *,
    attempted: bool = False,
) -> PrivateSingleScopeReplaceReview:
    return PrivateSingleScopeReplaceReview(
        state,
        _MESSAGES[state],
        attempted,
        True,
        barrier._REQUIRED,
    )


class _Interrupted(Exception):
    """In-process synthetic fault, never a simulated power-loss guarantee."""


def _interrupt(
    selected: PrivateSingleScopeReplaceFault, at: PrivateSingleScopeReplaceFault
) -> None:
    if selected is at:
        raise _Interrupted


@contextmanager
def _share_safe_reader(path: Path) -> Iterator[BinaryIO]:
    """Hold native delete-sharing read custody; no write share or write rights.

    A Win32 native open with FILE_SHARE_DELETE permits an OS replace *attempt*,
    not necessarily a successful replacement. The handle remains open until
    the after-image census and original held-file checks finish.
    """
    if sys.platform == "win32":
        with sharing._native_target(
            path, sharing.PrivateSyntheticWindowsShareMode.ALLOW_DELETE_SHARE
        ) as stream:
            yield stream
    elif sys.platform == "linux":
        with path.open("rb") as stream:
            yield stream
    else:
        raise OSError("Native share-safe scratch open unsupported")


def _held_exact(
    stream: BinaryIO,
    expected_id: tuple[int, int],
    expected_bytes: bytes,
    *,
    after_target: bool = False,
) -> bool:
    """Recheck original HANDLE/FD identity and bytes before and after rename.

    The prior destination may be unlinked after replacement. Only in that
    after-target case is a zero link count permitted; this is not evidence of
    file or directory durability.
    """
    info = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(info.st_mode)
        or (info.st_dev, info.st_ino) != expected_id
        or info.st_size != len(expected_bytes)
        or info.st_nlink not in ((0, 1) if after_target else (1,))
    ):
        return False
    stream.seek(0)
    return stream.read(len(expected_bytes) + 1) == expected_bytes


def _holds(
    target: BinaryIO,
    stage: BinaryIO,
    baseline: canonical._Census,
    checked: intents.PrivateTransactionIntent,
    *,
    replaced: bool,
) -> bool:
    before = checked.registry_before
    after = checked.registry_after
    if (
        type(before) is not bytes
        or type(after) is not bytes
        or baseline.stage is None
        or baseline.stage == baseline.registry
    ):
        return False
    return _held_exact(
        target, baseline.registry, before, after_target=replaced
    ) and _held_exact(stage, baseline.stage, after)


def rehearse_synthetic_share_safe_single_scope_replace(
    step: admission.PrivateScratchWriterStep = admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
    interruption: PrivateSingleScopeReplaceFault = PrivateSingleScopeReplaceFault.NONE,
) -> PrivateSingleScopeReplaceReview:
    """Attempt one canonical replacement only in a newly owned scratch layout.

    No external path, transaction or callback can be supplied. Both read handles
    and all four parent handles survive until exact postimage verification. No
    real teacher files or user-supplied bytes are touched.
    """
    state = PrivateSingleScopeReplaceState
    fault = PrivateSingleScopeReplaceFault
    if (
        type(step) is not admission.PrivateScratchWriterStep
        or type(interruption) is not fault
    ):
        return _result(state.INVALID_REQUEST)
    if step is not admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)

    attempted = False
    share_open = False
    try:
        checked = canonical._canonical()
        raw = intents.encode_private_transaction_intent(checked)
        if (
            intents.decode_private_transaction_intent(raw) != checked
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(state.CANONICAL_INTENT_REFUSED)
        initial = prepared.describe_private_prepared_stage_write_intent(
            step, 2, checked
        )
        if (
            initial.state
            is not prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
            or initial.description is None
            or initial.description.pending_intent_sha256 != canonical._sha(raw)
        ):
            return _result(state.CANONICAL_INTENT_REFUSED)

        with tempfile.TemporaryDirectory(prefix="core238_3g40_share_") as temporary:
            paths = canonical._make_layout(Path(temporary), checked, raw)
            with scratch._scratch_lock(paths.private / scratch._LOCK):
                _interrupt(interruption, fault.AFTER_LOCK)
                with ExitStack() as stack:
                    parents = tuple(
                        stack.enter_context(owned._held_native_parent(path))
                        for path in two._parents(paths)
                    )
                    if not canonical._held(parents):
                        return _result(state.PARENT_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_PARENTS)

                    # No separate unprotected sharing probe. These are the
                    # actual read handles retained over the native attempt.
                    try:
                        target = stack.enter_context(
                            _share_safe_reader(paths.private / scratch._REGISTRY)
                        )
                        stage = stack.enter_context(
                            _share_safe_reader(paths.private / scratch._STAGE)
                        )
                    except OSError:
                        # The outer synthetic advisory-lock helper deliberately
                        # maps PermissionError to guard refusal. Catch native
                        # target/stage sharing failures *here*, before they
                        # can be mistaken for a lock-acquisition failure.
                        # ExitStack still closes a target opened before stage
                        # refusal, and neither path attempts replacement.
                        return _result(state.SHARING_OPEN_REFUSED_PRESERVE)
                    share_open = True
                    _interrupt(interruption, fault.AFTER_SHARE_OPEN)
                    second = prepared.describe_private_prepared_stage_write_intent(
                        step, 2, checked
                    )
                    if (
                        second.state is not initial.state
                        or second.description != initial.description
                    ):
                        return _result(state.CANONICAL_INTENT_REFUSED)
                    if not canonical._held(parents):
                        return _result(state.PARENT_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_CANONICAL_ADMISSION)

                    baseline = canonical._observe(paths, checked, raw, stage=True)
                    if baseline.stage is None or baseline.stage == baseline.registry:
                        return _result(state.PREIMAGE_REFUSED)
                    if not _holds(target, stage, baseline, checked, replaced=False):
                        return _result(state.NATIVE_HANDLE_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_READER_CHECK)

                    # No intervening reader release or new lock scope.
                    # Fresh observations directly before the native operation.
                    for _ in range(3):
                        if not canonical._held(parents):
                            return _result(state.PARENT_CONFLICT_PRESERVE)
                        if (
                            canonical._observe(paths, checked, raw, stage=True)
                            != baseline
                        ):
                            return _result(state.ADMISSION_DRIFT_PRESERVE)
                        if not _holds(target, stage, baseline, checked, replaced=False):
                            return _result(state.NATIVE_HANDLE_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.BEFORE_REPLACE)
                    if not canonical._held(parents):
                        return _result(state.PARENT_CONFLICT_PRESERVE)
                    if not _holds(target, stage, baseline, checked, replaced=False):
                        return _result(state.NATIVE_HANDLE_CONFLICT_PRESERVE)
                    attempted = True
                    try:
                        os.replace(
                            paths.private / scratch._STAGE,
                            paths.private / scratch._REGISTRY,
                        )
                    except OSError as error:
                        # Even a native sharing refusal cannot grant retry.
                        classified = transition.classify_native_replace_refusal(error)
                        if classified in {
                            transition.PrivateNativeReplaceRefusal.WINDOWS_ACCESS_DENIED,
                            transition.PrivateNativeReplaceRefusal.WINDOWS_SHARING_VIOLATION,
                            transition.PrivateNativeReplaceRefusal.WINDOWS_LOCK_VIOLATION,
                            transition.PrivateNativeReplaceRefusal.POSIX_PERMISSION_REFUSED,
                        }:
                            # A reported refusal does not prove the mutation
                            # wasn't applied: confirm the exact scratch preimage.
                            try:
                                still_before = canonical._observe(
                                    paths, checked, raw, stage=True
                                ) == baseline and _holds(
                                    target, stage, baseline, checked, replaced=False
                                )
                            except (
                                OSError,
                                ValueError,
                                canonical._Namespace,
                                canonical._Images,
                                canonical._Files,
                            ):
                                still_before = False
                            if not still_before:
                                return _result(
                                    state.POST_ATTEMPT_UNKNOWN_PRESERVE, attempted=True
                                )
                            return _result(
                                state.NATIVE_REPLACE_REFUSED_PRESERVE, attempted=True
                            )
                        return _result(
                            state.POST_ATTEMPT_UNKNOWN_PRESERVE, attempted=True
                        )

                    _interrupt(interruption, fault.AFTER_REPLACE)
                    if not canonical._held(parents):
                        return _result(state.PARENT_CONFLICT_PRESERVE, attempted=True)
                    observed = canonical._observe(paths, checked, raw, stage=False)
                    if not canonical._post(baseline, observed):
                        return _result(
                            state.POSTIMAGE_CONFLICT_PRESERVE, attempted=True
                        )
                    if not _holds(target, stage, baseline, checked, replaced=True):
                        return _result(
                            state.POSTIMAGE_CONFLICT_PRESERVE, attempted=True
                        )
                    _interrupt(interruption, fault.AFTER_POSTIMAGE)
                    scratch._sync_target(paths.private)
                    _interrupt(interruption, fault.AFTER_FILE_SYNC)
                    if (
                        not canonical._held(parents)
                        or not canonical._post(
                            baseline,
                            canonical._observe(paths, checked, raw, stage=False),
                        )
                        or not _holds(target, stage, baseline, checked, replaced=True)
                    ):
                        return _result(
                            state.POSTIMAGE_CONFLICT_PRESERVE, attempted=True
                        )
            _interrupt(interruption, fault.AFTER_GUARD_RELEASE)
            return _result(
                state.SCRATCH_SHARE_SAFE_REPLACEMENT_UNQUALIFIED, attempted=True
            )
    except (_Interrupted, KeyboardInterrupt):
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE
            if attempted
            else state.PRE_ATTEMPT_INTERRUPTED_PRESERVE,
            attempted=attempted,
        )
    except scratch._GuardRefused:
        return _result(state.GUARD_REFUSED_PRESERVE, attempted=attempted)
    except (owned._ParentUnqualified, admission._ParentUnqualified, canonical._Parents):
        return _result(state.PARENT_CONFLICT_PRESERVE, attempted=attempted)
    except (canonical._Namespace, canonical._Images, canonical._Files):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE if attempted else state.PREIMAGE_REFUSED,
            attempted=attempted,
        )
    except (FileNotFoundError, PermissionError):
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE
            if attempted
            else (
                state.SHARING_OPEN_REFUSED_PRESERVE
                if share_open is False
                else state.PREIMAGE_REFUSED
            ),
            attempted=attempted,
        )
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE if attempted else state.IO_ERROR,
            attempted=attempted,
        )
