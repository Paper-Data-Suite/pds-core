"""Core #238 3G39: bounded synthetic transition and conservative refusal contract."""

from __future__ import annotations

import errno
import inspect
import sys
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from pds_core import _teacher_private_recovery_native_replace_transition as transition
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_windows_share as sharing
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission

State = transition.PrivateNativeReplaceTransitionState
Refusal = transition.PrivateNativeReplaceRefusal
Fault = canonical.PrivateCanonicalReplaceFault
Original = canonical.PrivateCanonicalReplaceState
Step = admission.PrivateScratchWriterStep


def _original(state: Original) -> canonical.PrivateCanonicalReplaceReview:
    return canonical.PrivateCanonicalReplaceReview(state, "redacted")


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    platform: str = "linux",
    original_state: Original = Original.SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED,
    share_state: sharing.PrivateSyntheticWindowsShareState = sharing.PrivateSyntheticWindowsShareState.NO_DELETE_SHARE_BLOCKED_UNQUALIFIED,
) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(sys, "platform", platform)

    def scratch(step: Step, fault: Fault) -> canonical.PrivateCanonicalReplaceReview:
        calls.append("scratch")
        assert step is Step.STAGE_TO_REGISTRY
        assert type(fault) is Fault
        return _original(original_state)

    def share(
        mode: sharing.PrivateSyntheticWindowsShareMode,
    ) -> sharing.PrivateSyntheticWindowsShareReview:
        calls.append("windows-share")
        assert mode is sharing.PrivateSyntheticWindowsShareMode.NO_DELETE_SHARE
        return sharing.PrivateSyntheticWindowsShareReview(share_state, "scratch")

    monkeypatch.setattr(
        canonical, "rehearse_synthetic_canonical_two_root_replace", scratch
    )
    monkeypatch.setattr(sharing, "rehearse_synthetic_private_windows_sharing", share)
    return calls


def test_fixed_linux_disposable_transition_has_no_production_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _setup(monkeypatch)
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED
    assert result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain
    assert result.unqualified_requirements == barrier._REQUIRED
    assert calls == ["scratch"]
    assert "non_authorizing=True" in repr(result)
    with pytest.raises(FrozenInstanceError):
        setattr(result, "replacement_may_have_occurred", False)


def test_windows_share_probe_precedes_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _setup(monkeypatch, platform="win32")
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED
    assert calls == ["windows-share", "scratch"]


@pytest.mark.parametrize(
    "share_state",
    [
        item
        for item in sharing.PrivateSyntheticWindowsShareState
        if item
        is not sharing.PrivateSyntheticWindowsShareState.NO_DELETE_SHARE_BLOCKED_UNQUALIFIED
    ],
)
def test_windows_share_refusal_never_calls_replace(
    monkeypatch: pytest.MonkeyPatch,
    share_state: sharing.PrivateSyntheticWindowsShareState,
) -> None:
    calls = _setup(monkeypatch, platform="win32", share_state=share_state)
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.WINDOWS_SHARING_PROBE_REFUSED
    assert not result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain
    assert calls == ["windows-share"]


@pytest.mark.parametrize("value", [None, False, 0, "stage_to_registry", {}, object()])
def test_wrong_step_type_never_calls_scratch(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    calls = _setup(monkeypatch, platform="win32")
    result = transition.rehearse_synthetic_native_replace_transition(cast(Step, value))
    assert result.state is State.INVALID_REQUEST
    assert not result.replacement_may_have_occurred
    assert not calls


@pytest.mark.parametrize("value", [None, False, 0, "before_replace", {}, object()])
def test_wrong_fault_type_never_calls_scratch(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    calls = _setup(monkeypatch, platform="win32")
    result = transition.rehearse_synthetic_native_replace_transition(
        interruption=cast(Fault, value)
    )
    assert result.state is State.INVALID_REQUEST
    assert not result.replacement_may_have_occurred
    assert not calls


@pytest.mark.parametrize(
    "step", [entry for entry in Step if entry is not Step.STAGE_TO_REGISTRY]
)
def test_only_prepared_stage_step(monkeypatch: pytest.MonkeyPatch, step: Step) -> None:
    calls = _setup(monkeypatch, platform="win32")
    result = transition.rehearse_synthetic_native_replace_transition(step)
    assert result.state is State.OPERATION_NOT_ADMITTED
    assert not calls


def test_unsupported_platform_has_no_probe_or_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _setup(monkeypatch, platform="darwin")
    assert (
        transition.rehearse_synthetic_native_replace_transition().state
        is State.UNSUPPORTED
    )
    assert not calls


@pytest.mark.parametrize(
    "fault", sorted(transition._BEFORE_ATTEMPT, key=lambda x: cast(Fault, x).value)
)
def test_injected_pre_attempt_interruption_cannot_claim_replace(
    monkeypatch: pytest.MonkeyPatch, fault: Fault
) -> None:
    _setup(monkeypatch, original_state=Original.INTERRUPTED_PRESERVE)
    result = transition.rehearse_synthetic_native_replace_transition(interruption=fault)
    assert result.state is State.PRE_ATTEMPT_INTERRUPTED_PRESERVE
    assert not result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain


@pytest.mark.parametrize(
    "fault", sorted(transition._AFTER_ATTEMPT, key=lambda x: cast(Fault, x).value)
)
def test_injected_post_attempt_interruption_requires_restart_review(
    monkeypatch: pytest.MonkeyPatch, fault: Fault
) -> None:
    _setup(monkeypatch, original_state=Original.INTERRUPTED_PRESERVE)
    result = transition.rehearse_synthetic_native_replace_transition(interruption=fault)
    assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain


def test_unscheduled_interruption_is_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(monkeypatch, original_state=Original.INTERRUPTED_PRESERVE)
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert result.replacement_may_have_occurred


@pytest.mark.parametrize("fault", [item for item in Fault if item is not Fault.NONE])
def test_success_cannot_coexist_with_selected_injection(
    monkeypatch: pytest.MonkeyPatch, fault: Fault
) -> None:
    _setup(monkeypatch)
    result = transition.rehearse_synthetic_native_replace_transition(interruption=fault)
    assert result.state is State.PROTOCOL_CONFLICT_PRESERVE
    assert result.replacement_may_have_occurred


@pytest.mark.parametrize(
    "original_state",
    sorted(transition._PRE_REFUSALS, key=lambda x: cast(Original, x).value),
)
def test_pre_attempt_native_refusal_is_not_execution(
    monkeypatch: pytest.MonkeyPatch, original_state: Original
) -> None:
    _setup(monkeypatch, original_state=original_state)
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.PRE_ATTEMPT_REFUSED_PRESERVE
    assert not result.replacement_may_have_occurred


@pytest.mark.parametrize(
    "original_state",
    [
        Original.IMAGE_CONFLICT_PRESERVE,
        Original.FILE_CONFLICT_PRESERVE,
        Original.PARENT_CONFLICT_PRESERVE,
        Original.POSTIMAGE_CONFLICT_PRESERVE,
    ],
)
def test_unknown_native_conflict_is_not_safe_to_retry(
    monkeypatch: pytest.MonkeyPatch, original_state: Original
) -> None:
    _setup(monkeypatch, original_state=original_state)
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.POSTIMAGE_CONFLICT_PRESERVE
    assert result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain


@pytest.mark.parametrize(
    "original_state,expected,possibly_attempted",
    [
        (Original.CANONICAL_INTENT_REFUSED, State.CANONICAL_INTENT_REFUSED, False),
        (
            Original.REPLACEMENT_REFUSED_PRESERVE,
            State.NATIVE_REPLACEMENT_REFUSED_PRESERVE,
            True,
        ),
        (Original.GUARD_REFUSED, State.GUARD_REFUSED_PRESERVE, True),
        (Original.IO_ERROR, State.POST_ATTEMPT_UNKNOWN_PRESERVE, True),
        (Original.UNSUPPORTED, State.UNSUPPORTED, False),
        (Original.INVALID_REQUEST, State.POST_ATTEMPT_UNKNOWN_PRESERVE, True),
        (Original.OPERATION_NOT_ADMITTED, State.PROTOCOL_CONFLICT_PRESERVE, True),
    ],
)
def test_exhaustive_other_native_states(
    monkeypatch: pytest.MonkeyPatch,
    original_state: Original,
    expected: State,
    possibly_attempted: bool,
) -> None:
    _setup(monkeypatch, original_state=original_state)
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is expected
    assert result.replacement_may_have_occurred is possibly_attempted


@pytest.mark.parametrize(
    "winerror,expected",
    [
        (5, Refusal.WINDOWS_ACCESS_DENIED),
        (32, Refusal.WINDOWS_SHARING_VIOLATION),
        (33, Refusal.WINDOWS_LOCK_VIOLATION),
        (2, Refusal.UNKNOWN_IO_REFUSED),
        (87, Refusal.UNKNOWN_IO_REFUSED),
    ],
)
def test_windows_native_error_mapping(winerror: int, expected: Refusal) -> None:
    error = OSError(123, "native refusal")
    setattr(error, "winerror", winerror)
    assert transition.classify_native_replace_refusal(error) is expected


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM])
def test_posix_permission_mapping(code: int) -> None:
    assert (
        transition.classify_native_replace_refusal(OSError(code, "permission"))
        is Refusal.POSIX_PERMISSION_REFUSED
    )


def test_unknown_error_has_no_retry_permission() -> None:
    assert (
        transition.classify_native_replace_refusal(OSError(errno.EIO, "I/O"))
        is Refusal.UNKNOWN_IO_REFUSED
    )
    assert (
        transition.classify_native_replace_refusal(cast(OSError, None))
        is Refusal.INVALID_ERROR
    )


@pytest.mark.parametrize("original_state", list(Original))
def test_no_original_result_can_authorize_production(original_state: Original) -> None:
    result = transition._classify_scratch_result(_original(original_state), Fault.NONE)
    assert result.pending_evidence_must_remain
    assert result.unqualified_requirements == barrier._REQUIRED
    assert "non_authorizing=True" in repr(result)
    assert not any(
        hasattr(result, name)
        for name in ("permit", "execute", "writer", "path", "handle", "bytes")
    )


@pytest.mark.parametrize("state", list(State))
def test_status_strings_are_sanitized(state: State) -> None:
    result = transition._result(state)
    assert "C:" not in result.message
    assert "/tmp" not in result.message
    assert "\\\\" not in result.message
    assert result.pending_evidence_must_remain


def test_windows_probe_raises_before_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _setup(monkeypatch, platform="win32")

    def fail(*_args: object) -> None:
        calls.append("probe-failure")
        raise OSError(32, "sharing")

    monkeypatch.setattr(sharing, "rehearse_synthetic_private_windows_sharing", fail)
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.WINDOWS_SHARING_PROBE_REFUSED
    assert not result.replacement_may_have_occurred
    assert calls == ["probe-failure"]


def test_synthetic_operation_raises_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(monkeypatch)

    def fail(*_args: object) -> canonical.PrivateCanonicalReplaceReview:
        raise OSError(errno.EIO, "I/O")

    monkeypatch.setattr(
        canonical, "rehearse_synthetic_canonical_two_root_replace", fail
    )
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert result.replacement_may_have_occurred


def test_canonical_untrusted_result_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(monkeypatch)
    monkeypatch.setattr(
        canonical, "rehearse_synthetic_canonical_two_root_replace", lambda *_: object()
    )
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state is State.PROTOCOL_CONFLICT_PRESERVE
    assert result.replacement_may_have_occurred


def test_no_production_writer_paths_or_callbacks() -> None:
    source = inspect.getsource(transition)
    signature = inspect.signature(
        transition.rehearse_synthetic_native_replace_transition
    )
    assert tuple(signature.parameters) == ("step", "interruption")
    assert not any(
        fragment in source
        for fragment in (
            "os.replace(",
            "unlink(",
            "mkdir(",
            "fsync(",
            "CreateFileW(",
            "_hold_existing_retained_descriptor_guard(",
            "review_protected_pre_replace_window(",
        )
    )
    assert not any(
        hasattr(transition, name)
        for name in (
            "commit_registry",
            "retire_journal",
            "authorize_writer",
            "open_writable",
        )
    )


def test_synthetic_fault_partition_is_complete() -> None:
    assert transition._BEFORE_ATTEMPT.isdisjoint(transition._AFTER_ATTEMPT)
    assert transition._BEFORE_ATTEMPT | transition._AFTER_ATTEMPT == set(Fault) - {
        Fault.NONE
    }


def test_actual_disposable_linux_replacement_when_supported() -> None:
    """Real 3G34 execution only on non-root Linux; Windows suite tests native separately."""
    if sys.platform != "linux":
        pytest.skip("Separate Windows native qualification")
    result = transition.rehearse_synthetic_native_replace_transition()
    assert result.state in {
        State.SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED,
        State.PRE_ATTEMPT_REFUSED_PRESERVE,
        State.GUARD_REFUSED_PRESERVE,
        State.POST_ATTEMPT_UNKNOWN_PRESERVE,
    }
    assert result.pending_evidence_must_remain
