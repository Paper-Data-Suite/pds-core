"""One native replacement under 3G44 one-shot custody, SCRATCH ONLY (#238 3G46).

This executable rehearsal accepts only fixed operation/fault enums. It creates
its own disposable canonical stage, registry and journal, retains 3G44's native
file handles throughout ONE attempted replace, and checks expected postimages.
It accepts no private path, transaction, user data, callback or writer token.
The producer-facing production barrier is unchanged and always blocks writes.
A post-mark error is ALWAYS treated as possibly applied: never retry it.
File-sync/guard exit do not prove directory durability or a committed binding.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_recovery_one_shot_transition_pair as one_shot
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_recovery_transition_registry_custody as native
from pds_core import _teacher_private_transaction_intent as intents


class PrivateDisposableOneShotFault(str, Enum):
    NONE = "none"
    AFTER_LOCK = "after_lock"
    AFTER_CUSTODY = "after_custody"
    BEFORE_ATTEMPT_MARK = "before_attempt_mark"
    AFTER_ATTEMPT_MARK = "after_attempt_mark"
    AFTER_NATIVE_REPLACE = "after_native_replace"
    AFTER_POSTIMAGE = "after_postimage"


class PrivateDisposableOneShotState(str, Enum):
    DISPOSABLE_REPLACEMENT_OBSERVED_UNQUALIFIED = (
        "disposable_replacement_observed_unqualified"
    )
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    CANONICAL_INTENT_REFUSED = "canonical_intent_refused"
    SCRATCH_PREIMAGE_REFUSED = "scratch_preimage_refused"
    NATIVE_CUSTODY_REFUSED = "native_custody_refused"
    NATIVE_PREIMAGE_CHANGED_PRESERVE = "native_preimage_changed_preserve"
    PRE_ATTEMPT_INTERRUPTED = "pre_attempt_interrupted"
    POST_ATTEMPT_UNKNOWN_PRESERVE = "post_attempt_unknown_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    SCRATCH_GUARD_REFUSED = "scratch_guard_refused"
    IO_ERROR = "io_error"


_MESSAGES: dict[PrivateDisposableOneShotState, str] = {
    item: "Disposable one-shot transition was refused or unqualified; no production operation allowed."
    for item in PrivateDisposableOneShotState
}
_MESSAGES[PrivateDisposableOneShotState.DISPOSABLE_REPLACEMENT_OBSERVED_UNQUALIFIED] = (
    "One canonical replacement observed in internally generated scratch under "
    "one-shot retained native custody; durability and production writes unqualified."
)
_MESSAGES[PrivateDisposableOneShotState.POST_ATTEMPT_UNKNOWN_PRESERVE] = (
    "Scratch attempt was marked; the native replacement may have occurred. No retry."
)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDisposableOneShotReview:
    state: PrivateDisposableOneShotState
    message: str
    replacement_may_have_occurred: bool
    no_automatic_retry: bool = True
    production_writes_blocked: bool = True
    unqualified_requirements: tuple[barrier.PrivateProductionWriteRequirement, ...] = (
        field(default=barrier._REQUIRED, repr=False)
    )

    def __repr__(self) -> str:
        return "PrivateDisposableOneShotReview(non_authorizing=True)"


def _result(
    state: PrivateDisposableOneShotState, *, attempted: bool = False
) -> PrivateDisposableOneShotReview:
    return PrivateDisposableOneShotReview(state, _MESSAGES[state], attempted)


class _Interrupted(Exception):
    pass


def _stop(
    selected: PrivateDisposableOneShotFault, phase: PrivateDisposableOneShotFault
) -> None:
    if selected is phase:
        raise _Interrupted


def _expected(path: Path, image: bytes) -> bool:
    """Only for module-created disposable files, not a secure native file reader."""
    try:
        return canonical._exact(path, image)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return False


def rehearse_disposable_one_shot_native_replace(
    step: admission.PrivateScratchWriterStep = admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
    fault: PrivateDisposableOneShotFault = PrivateDisposableOneShotFault.NONE,
) -> PrivateDisposableOneShotReview:
    """Exercise one 3G44 retained-handle native attempt on newly owned scratch.

    The scratch layout is intentionally NOT a production verified private root.
    A native protection refusal may therefore be the correct result on Windows
    or a policy-restricted host. In no case is a refused operation retried.
    """
    state = PrivateDisposableOneShotState
    if (
        type(step) is not admission.PrivateScratchWriterStep
        or type(fault) is not PrivateDisposableOneShotFault
    ):
        return _result(state.INVALID_REQUEST)
    if step is not admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    attempted = False
    try:
        checked = canonical._canonical()
        raw = intents.encode_private_transaction_intent(checked)
        before, after, sidecar = (
            checked.registry_before,
            checked.registry_after,
            checked.descriptor_before,
        )
        if (
            type(raw) is not bytes
            or not (0 < len(raw) <= intents.MAX_INTENT_BYTES)
            or intents.decode_private_transaction_intent(raw) != checked
            or intents.encode_private_transaction_intent(checked) != raw
            or type(before) is not bytes
            or type(after) is not bytes
            or type(sidecar) is not bytes
            or not before
            or not after
            or before == after
        ):
            return _result(state.CANONICAL_INTENT_REFUSED)
        tx = checked.witness.transaction_id
        stage_name = "." + tx + ".registry-stage"
        journal_name = tx + ".json"
        with tempfile.TemporaryDirectory(prefix="core238_3g46_one_shot_") as temporary:
            base = Path(temporary)
            private = base / "private"
            journal_dir = private / "transactions"
            descriptor_dir = base / "workspace" / ".pds"
            journal_dir.mkdir(parents=True, mode=0o700)
            descriptor_dir.mkdir(parents=True, mode=0o700)
            scratch._write_new(private, "registry.json", before)
            scratch._write_new(private, stage_name, after)
            scratch._write_new(journal_dir, journal_name, raw)
            scratch._write_new(
                descriptor_dir, "teacher-private-association.json", sidecar
            )
            target = private / "registry.json"
            stage = private / stage_name
            journal = journal_dir / journal_name
            descriptor = descriptor_dir / "teacher-private-association.json"
            with scratch._scratch_lock(private / scratch._LOCK):
                _stop(fault, PrivateDisposableOneShotFault.AFTER_LOCK)
                if not all(
                    (
                        _expected(target, before),
                        _expected(stage, after),
                        _expected(journal, raw),
                        _expected(descriptor, sidecar),
                    )
                ):
                    return _result(state.SCRATCH_PREIMAGE_REFUSED)
                owner = ordered._owner()
                with one_shot._held_one_shot_transition_pair(
                    private, tx, owner, len(before), len(after)
                ) as window:
                    prepared = native.PrivateRegistryTransitionIdentityState.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
                    installed = native.PrivateRegistryTransitionIdentityState.EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED
                    if window.observe() is not prepared:
                        return _result(state.NATIVE_PREIMAGE_CHANGED_PRESERVE)
                    _stop(fault, PrivateDisposableOneShotFault.AFTER_CUSTODY)
                    if window.observe() is not prepared or not all(
                        (
                            _expected(target, before),
                            _expected(stage, after),
                            _expected(journal, raw),
                            _expected(descriptor, sidecar),
                        )
                    ):
                        return _result(state.NATIVE_PREIMAGE_CHANGED_PRESERVE)
                    _stop(fault, PrivateDisposableOneShotFault.BEFORE_ATTEMPT_MARK)
                    window.mark_attempt()
                    attempted = True
                    _stop(fault, PrivateDisposableOneShotFault.AFTER_ATTEMPT_MARK)
                    # The ONLY mutation attempt; both names are module-owned scratch.
                    os.replace(stage, target)
                    _stop(fault, PrivateDisposableOneShotFault.AFTER_NATIVE_REPLACE)
                    if (
                        window.observe() is not installed
                        or stage.exists()
                        or not all(
                            (
                                _expected(target, after),
                                _expected(journal, raw),
                                _expected(descriptor, sidecar),
                            )
                        )
                    ):
                        return _result(
                            state.POSTIMAGE_CONFLICT_PRESERVE, attempted=True
                        )
                    _stop(fault, PrivateDisposableOneShotFault.AFTER_POSTIMAGE)
                # Exit completed, meaning the 3G44 native terminal identity was
                # verified BEFORE the handles were released, not afterward.
            return _result(
                state.DISPOSABLE_REPLACEMENT_OBSERVED_UNQUALIFIED, attempted=True
            )
    except _Interrupted:
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE
            if attempted
            else state.PRE_ATTEMPT_INTERRUPTED,
            attempted=attempted,
        )
    except (one_shot._AttemptScopeRefused, scratch._GuardRefused):
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE
            if attempted
            else state.NATIVE_CUSTODY_REFUSED,
            attempted=attempted,
        )
    except KeyboardInterrupt:
        return _result(state.POST_ATTEMPT_UNKNOWN_PRESERVE, attempted=attempted)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(
            state.POST_ATTEMPT_UNKNOWN_PRESERVE if attempted else state.IO_ERROR,
            attempted=attempted,
        )
