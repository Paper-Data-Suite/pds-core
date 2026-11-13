"""Core #238 3G45: sealed one-shot canonical pre-attempt boundary."""

from __future__ import annotations

import hashlib
import inspect
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator, Literal, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
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
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_recovery_transition_registry_custody as native
from pds_core import _teacher_private_recovery_sealed_pre_attempt as sealed
from pds_core import _teacher_private_recovery_one_shot_transition_pair as one_shot
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = sealed.PrivateSealedPreAttemptState
Step = scratch.PrivateScratchWriterStep
Native = native.PrivateRegistryTransitionIdentityState
TX = "11111111-1111-4111-8111-111111111111"
ASSOCIATION = "22222222-2222-4222-8222-222222222222"
RAW = b"canonical-journal-fixture"
BEFORE = b"registry-before-fixture"
AFTER = b"registry-after-fixture"
SIDECAR = b"sidecar-fixture"
STAMPS: parents._Parents = (
    (1, 101, 0o40700, 10, 20),
    (1, 102, 0o40700, 10, 20),
    (1, 103, 0o40700, 10, 20),
    (1, 104, 0o40700, 10, 20),
)
FILES: bridge._Census = (
    (1, 201, len(RAW), 10, 20),
    (1, 202, len(BEFORE), 10, 20),
    (1, 203, len(SIDECAR), 10, 20),
    (1, 204, len(AFTER), 10, 20),
)
IMAGES: parents._Image = (RAW, BEFORE, SIDECAR, AFTER)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _intent() -> intents.PrivateTransactionIntent:
    request = object.__new__(intents.PrivateTransactionIntent)
    evidence = object.__new__(witness.PrivateTransactionWitness)
    for key, value in {
        "operation": witness.PrivateBindingOperation.REBIND_MOVE,
        "transaction_id": TX,
        "association_before": ASSOCIATION,
        "association_after": ASSOCIATION,
        "registry_revision_before": 7,
        "registry_revision_after": 8,
        "descriptor_sha256_before": _sha(SIDECAR),
        "descriptor_sha256_after": _sha(SIDECAR),
        "registry_sha256_before": _sha(BEFORE),
        "registry_sha256_after": _sha(AFTER),
    }.items():
        object.__setattr__(evidence, key, value)
    for key, value in {
        "witness": evidence,
        "registry_before": BEFORE,
        "registry_after": AFTER,
        "descriptor_before": SIDECAR,
        "descriptor_after": SIDECAR,
    }.items():
        object.__setattr__(request, key, value)
    return request


def _frame() -> scope._Frame:
    return scope._Frame(
        STAMPS,
        FILES,
        IMAGES,
        recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
    )


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    drift_native_at: int = 0,
    drift_image_at: int = 0,
    fail_guard_release: bool = False,
    fail_pair_release: bool = False,
) -> tuple[intents.PrivateTransactionIntent, list[str]]:
    proposed = _intent()
    events: list[str] = []
    kind = "windows_token_sid" if sys.platform == "win32" else "posix_euid"
    owner = inspection.EffectiveOSOwner(
        cast(Literal["windows_token_sid", "posix_euid"], kind),
        "S-1-5-21-111-222-333-1001" if sys.platform == "win32" else "1000",
    )
    guarded = [False]
    pair_held = [False]
    checks = [0]
    frames = [0]
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda *_: RAW)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: proposed
    )
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ),
    )
    monkeypatch.setattr(
        window, "_description", lambda *_: "unchanged-canonical-description"
    )
    monkeypatch.setattr(window, "_frame_state", lambda *_: None)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (None, owner))
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: None)
    monkeypatch.setattr(ordered, "_owner", lambda: owner)
    monkeypatch.setattr(
        recovery, "_namespace", lambda *_: (frozenset({TX}), frozenset({TX}), True)
    )
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: True)
    monkeypatch.setattr(parents, "_parents", lambda *_: STAMPS)

    @contextmanager
    def hold_guard(*_args: object) -> Iterator[None]:
        assert not guarded[0]
        events.append("guard-enter")
        guarded[0] = True
        try:
            yield
        finally:
            assert not pair_held[0]
            guarded[0] = False
            events.append("guard-exit")
            if fail_guard_release:
                raise transition._WriterGuardRefused(
                    transition.PrivateTransitionGuardState.GUARD_REFUSED
                )

    @contextmanager
    def hold_pair(*_args: object) -> Iterator[one_shot._AttemptWindow]:
        assert guarded[0]
        pair_held[0] = True
        events.append("pair-enter")

        def check() -> Native:
            assert guarded[0] and pair_held[0]
            checks[0] += 1
            events.append("native-check")
            if checks[0] == drift_native_at:
                return Native.REGISTRY_FOREIGN_PRESERVE
            return Native.PREPARED_IDENTITIES_OBSERVED_NO_WRITE

        held = one_shot._AttemptWindow(check)
        try:
            yield held
        finally:
            # The real 3G44 retained window checks this while its handles live.
            # In the fake this also proves no marker was set by the review.
            assert held.attempted is False
            assert held._finish() is Native.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
            pair_held[0] = False
            events.append("pair-exit")
            if fail_pair_release:
                raise one_shot._AttemptScopeRefused

    def observe(*_args: object) -> scope._Frame:
        assert guarded[0] and pair_held[0]
        frames[0] += 1
        events.append("frame")
        if frames[0] == drift_image_at:
            return scope._Frame(
                STAMPS,
                FILES,
                (RAW, BEFORE, SIDECAR, b"foreign"),
                recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
            )
        return _frame()

    monkeypatch.setattr(
        transition, "_hold_transitionable_journal_descriptor_guard", hold_guard
    )
    monkeypatch.setattr(one_shot, "_held_one_shot_transition_pair", hold_pair)
    monkeypatch.setattr(scope, "_observe", observe)
    return proposed, events


def _review(
    item: intents.PrivateTransactionIntent,
    root: Path,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
) -> sealed.PrivateSealedPreAttemptReview:
    return sealed.review_sealed_native_pre_attempt_boundary(
        step, revision, item, root, root
    )


def test_four_canonical_frames_and_nine_one_shot_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    outcome = _review(item, tmp_path)
    assert outcome.state is State.ONE_SHOT_PREATTEMPT_BLOCKED
    assert outcome.pending_evidence_must_remain is True
    assert outcome.unqualified_requirements == barrier._REQUIRED
    assert events.count("frame") == 4
    assert events.count("native-check") == 10
    assert events[0:2] == ["guard-enter", "pair-enter"]
    assert events[-2:] == ["pair-exit", "guard-exit"]
    assert "non_authorizing=True" in repr(outcome)
    with pytest.raises(FrozenInstanceError):
        setattr(outcome, "state", State.IO_ERROR)


@pytest.mark.parametrize("index", range(1, 10))
def test_native_drift_never_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, index: int
) -> None:
    item, events = _setup(monkeypatch, drift_native_at=index)
    assert _review(item, tmp_path).state is State.NATIVE_IDENTITY_CHANGED_PRESERVE
    assert events[-2:] == ["pair-exit", "guard-exit"]


@pytest.mark.parametrize("index", range(1, 5))
def test_canonical_image_drift_never_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, index: int
) -> None:
    item, events = _setup(monkeypatch, drift_image_at=index)

    # Assert real byte-image comparison, not just stable synthetic observations.
    def check(
        frame: scope._Frame,
        _baseline: scope._Frame | None,
        images: parents._Image,
        *_: object,
    ) -> object | None:
        return None if frame.images == images else object()

    monkeypatch.setattr(window, "_frame_state", check)
    assert _review(item, tmp_path).state is State.IMAGE_CONFLICT_PRESERVE
    assert events[-2:] == ["pair-exit", "guard-exit"]


@pytest.mark.parametrize("invalid", [None, 0, True, -1, 7.0, "7", {}, object()])
def test_invalid_revision_does_not_enter_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    item, events = _setup(monkeypatch)
    result = _review(item, tmp_path, revision=cast(int, invalid))
    assert result.state is State.INVALID_REQUEST
    assert not events


@pytest.mark.parametrize("invalid", [None, True, 0, "stage_to_registry", {}, object()])
def test_invalid_operation_does_not_enter_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    item, events = _setup(monkeypatch)
    assert _review(item, tmp_path, cast(Step, invalid)).state is State.INVALID_REQUEST
    assert not events


@pytest.mark.parametrize("other", [x for x in Step if x is not Step.STAGE_TO_REGISTRY])
def test_non_stage_operation_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, other: Step
) -> None:
    item, events = _setup(monkeypatch)
    assert _review(item, tmp_path, other).state is State.OPERATION_NOT_ADMITTED
    assert not events


def test_wrong_revision_is_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ),
    )
    assert _review(item, tmp_path).state is State.REVISION_MISMATCH_REFUSED
    assert not events


def test_wrong_binding_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *_: object())
    assert _review(item, tmp_path).state is State.BINDING_MISMATCH
    assert not events


def test_wrong_native_owner_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (object(), None))
    assert _review(item, tmp_path).state is State.OWNER_OR_PROTECTION_REFUSED
    assert not events


def test_binding_drift_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    times = [0]

    def changed(*_args: object) -> object | None:
        times[0] += 1
        return object() if times[0] == 3 else None

    monkeypatch.setattr(preflight, "_intent_owner_and_binding", changed)
    assert _review(item, tmp_path).state is State.BINDING_MISMATCH
    assert events[-2:] == ["pair-exit", "guard-exit"]


def test_namespace_change_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: False)
    assert _review(item, tmp_path).state is State.NAMESPACE_CONFLICT_PRESERVE
    assert events[-2:] == ["pair-exit", "guard-exit"]


def test_owner_changes_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    monkeypatch.setattr(ordered, "_owner", lambda: None)
    assert _review(item, tmp_path).state is State.OWNER_CHANGED
    assert events[-1] == "guard-exit"


def test_guard_release_error_overrides_positive_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch, fail_guard_release=True)
    assert _review(item, tmp_path).state is State.GUARD_REFUSED
    assert events[-1] == "guard-exit"


def test_native_pair_release_error_overrides_positive_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch, fail_pair_release=True)
    assert _review(item, tmp_path).state is State.ONE_SHOT_SCOPE_REFUSED
    assert events[-2:] == ["pair-exit", "guard-exit"]


def test_invalid_canonical_intent_cannot_enter_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda *_: b"")
    assert _review(item, tmp_path).state is State.INTENT_UNQUALIFIED
    assert not events


def test_parent_drift_detected_at_final_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    monkeypatch.setattr(parents, "_parents", lambda *_: ())
    assert _review(item, tmp_path).state is State.PARENT_CHANGED_PRESERVE
    assert events[-2:] == ["pair-exit", "guard-exit"]


def test_positive_review_never_returns_write_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, _ = _setup(monkeypatch)
    result = _review(item, tmp_path)
    assert result.pending_evidence_must_remain
    assert not hasattr(result, "permit")
    assert not hasattr(result, "handle")
    assert not hasattr(result, "path")
    assert not hasattr(result, "writer")


def test_security_source_has_no_production_writer() -> None:
    source = inspect.getsource(sealed)
    assert "os.replace(" not in source
    assert "os.remove(" not in source
    assert "unlink(" not in source
    assert "def commit_" not in source
    assert "_hold_transitionable_journal_descriptor_guard" in source
    assert "_held_one_shot_transition_pair" in source
    assert "_frame_state" in source
    assert not hasattr(sealed, "activate_notes")


def test_final_barrier_changed_inside_native_scope_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    calls = [0]

    def second_check(*_args: object) -> barrier.PrivateProductionWriteBarrierReview:
        calls[0] += 1
        result = (
            barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
            if calls[0] == 1
            else barrier.PrivateProductionWriteBarrierState.DESCRIPTION_UNQUALIFIED
        )
        return barrier._result(result)

    monkeypatch.setattr(
        barrier, "review_private_production_write_barrier", second_check
    )
    assert _review(item, tmp_path).state is State.BARRIER_DRIFT_PRESERVE
    assert calls[0] == 2
    assert events[-2:] == ["pair-exit", "guard-exit"]


def test_released_scope_does_not_return_attempt_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    item, events = _setup(monkeypatch)
    report = _review(item, tmp_path)
    assert report.state is State.ONE_SHOT_PREATTEMPT_BLOCKED
    assert report.unqualified_requirements == barrier._REQUIRED
    assert report.pending_evidence_must_remain
    assert not hasattr(report, "attempted")
    assert not hasattr(report, "mark_attempt")
    assert not hasattr(report, "replace")
    assert events[-2:] == ["pair-exit", "guard-exit"]


def test_sealed_entry_has_no_writer_or_marker_call() -> None:
    source = inspect.getsource(sealed)
    assert ".mark_attempt(" not in source
    assert "os.replace(" not in source
    assert "_held_one_shot_transition_pair" in source
    assert "held.attempted" in source
    assert "final_barrier" in source
    assert "_frame_state" in source
