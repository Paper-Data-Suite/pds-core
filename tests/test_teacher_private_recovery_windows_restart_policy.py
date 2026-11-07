"""Core #238 3G50: Windows native-restart/flush policy, never a write permit."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_recovery_post_attempt_restart as restart
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import (
    _teacher_private_recovery_windows_directory_durability_probe as probe,
)
from pds_core import _teacher_private_recovery_windows_restart_policy as policy
from pds_core import _teacher_private_transaction_intent as intents


_STEP = scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY
_ROLES = ("journal", "registry", "descriptor")


def _sample(
    kind: probe.PrivateDirectoryFlushState = (
        probe.PrivateDirectoryFlushState.REQUESTS_RETURNED_UNQUALIFIED
    ),
    names: tuple[str, ...] = _ROLES,
    directory_durability_unqualified: bool = True,
) -> probe.PrivateDirectoryFlushReview:
    return probe.PrivateDirectoryFlushReview(
        state=kind,
        message="scratch-only, no durability proof",
        observations=tuple(
            (name, probe.PrivateDirectoryFlushObservation.RETURNED_UNQUALIFIED)
            for name in names
        ),
        directory_durability_unqualified=directory_durability_unqualified,
    )


def _native(
    kind: restart.PrivatePostAttemptRestartState = (
        restart.PrivatePostAttemptRestartState.PREPARED_STAGE_PENDING_REVIEW
    ),
    production_writes_blocked: bool = True,
) -> restart.PrivatePostAttemptRestartReview:
    return restart.PrivatePostAttemptRestartReview(
        state=kind,
        message="pending recovery",
        production_writes_blocked=production_writes_blocked,
    )


def _call() -> policy.PrivateWindowsRestartPolicyReview:
    return policy.review_windows_private_pending_recovery_policy(
        _STEP,
        2,
        canonical._canonical(),
        Path("C:/synthetic-owner/private"),
        Path("C:/synthetic-workspace"),
    )


@pytest.fixture
def native_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[str] = []

    def native(*_args: object) -> restart.PrivatePostAttemptRestartReview:
        calls.append("native")
        return _native()

    def directory() -> probe.PrivateDirectoryFlushReview:
        calls.append("directory")
        return _sample()

    monkeypatch.setattr(restart, "review_private_post_attempt_native_restart", native)
    monkeypatch.setattr(
        probe, "probe_private_windows_directory_flush_contract", directory
    )
    return calls


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        (
            restart.PrivatePostAttemptRestartState.PREPARED_STAGE_PENDING_REVIEW,
            policy.PrivateWindowsRestartPolicyState.PREPARED_STAGE_HOLD_NO_RETRY,
        ),
        (
            restart.PrivatePostAttemptRestartState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW,
            policy.PrivateWindowsRestartPolicyState.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
        ),
        (
            restart.PrivatePostAttemptRestartState.BOTH_AFTER_JOURNAL_PENDING_REVIEW,
            policy.PrivateWindowsRestartPolicyState.BOTH_AFTER_JOURNAL_PENDING_HOLD,
        ),
    ],
)
def test_recovery_checkpoint_never_grants_completion(
    native_windows: list[str],
    monkeypatch: pytest.MonkeyPatch,
    observed: restart.PrivatePostAttemptRestartState,
    expected: policy.PrivateWindowsRestartPolicyState,
) -> None:
    def observed_native(*_args: object) -> restart.PrivatePostAttemptRestartReview:
        native_windows.append("fresh-native")
        return _native(observed)

    monkeypatch.setattr(
        restart,
        "review_private_post_attempt_native_restart",
        observed_native,
    )
    finding = _call()
    assert finding.state is expected
    assert finding.native_restart_state is observed
    assert (
        finding.scratch_directory_state
        is probe.PrivateDirectoryFlushState.REQUESTS_RETURNED_UNQUALIFIED
    )
    assert native_windows == ["fresh-native", "directory"]
    assert finding.pending_evidence_must_remain is True
    assert finding.automatic_retry_forbidden is True
    assert finding.journal_retirement_forbidden is True
    assert finding.production_writes_blocked is True
    assert finding.directory_durability_unqualified is True
    assert finding.durable_commit_unqualified is True
    assert repr(finding) == "PrivateWindowsRestartPolicyReview(non_authorizing=True)"


@pytest.mark.parametrize(
    "kind",
    [
        state
        for state in restart.PrivatePostAttemptRestartState
        if state
        not in {
            restart.PrivatePostAttemptRestartState.PREPARED_STAGE_PENDING_REVIEW,
            restart.PrivatePostAttemptRestartState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW,
            restart.PrivatePostAttemptRestartState.BOTH_AFTER_JOURNAL_PENDING_REVIEW,
        }
    ],
)
def test_native_refusal_skips_directory_probe(
    native_windows: list[str],
    monkeypatch: pytest.MonkeyPatch,
    kind: restart.PrivatePostAttemptRestartState,
) -> None:
    def refused_native(*_args: object) -> restart.PrivatePostAttemptRestartReview:
        native_windows.append("refusal")
        return _native(kind)

    monkeypatch.setattr(
        restart,
        "review_private_post_attempt_native_restart",
        refused_native,
    )
    found = _call()
    assert (
        found.state
        is policy.PrivateWindowsRestartPolicyState.NATIVE_RESTART_UNQUALIFIED_PRESERVE
    )
    assert found.native_restart_state is kind
    assert found.scratch_directory_state is None
    assert native_windows == ["refusal"]


@pytest.mark.parametrize(
    "kind",
    [
        state
        for state in probe.PrivateDirectoryFlushState
        if state is not probe.PrivateDirectoryFlushState.REQUESTS_RETURNED_UNQUALIFIED
    ],
)
def test_flush_refusal_never_converts_into_a_write_permit(
    native_windows: list[str],
    monkeypatch: pytest.MonkeyPatch,
    kind: probe.PrivateDirectoryFlushState,
) -> None:
    def refused_directory() -> probe.PrivateDirectoryFlushReview:
        native_windows.append("refused-directory")
        return _sample(kind)

    monkeypatch.setattr(
        probe,
        "probe_private_windows_directory_flush_contract",
        refused_directory,
    )
    found = _call()
    assert (
        found.state
        is policy.PrivateWindowsRestartPolicyState.DIRECTORY_PROBE_UNQUALIFIED_PRESERVE
    )
    assert (
        found.native_restart_state
        is restart.PrivatePostAttemptRestartState.PREPARED_STAGE_PENDING_REVIEW
    )
    assert found.scratch_directory_state is kind
    assert found.journal_retirement_forbidden
    assert native_windows == ["native", "refused-directory"]


@pytest.mark.parametrize(
    "names",
    [
        (),
        ("journal",),
        ("journal", "registry"),
        ("registry", "journal", "descriptor"),
        ("journal", "registry", "descriptor", "descriptor"),
        ("journal", "registry", "other"),
    ],
)
def test_probe_exact_role_order_and_count_required(
    native_windows: list[str],
    monkeypatch: pytest.MonkeyPatch,
    names: tuple[str, ...],
) -> None:
    monkeypatch.setattr(
        probe,
        "probe_private_windows_directory_flush_contract",
        lambda: _sample(names=names),
    )
    found = _call()
    assert (
        found.state
        is policy.PrivateWindowsRestartPolicyState.DIRECTORY_PROBE_UNQUALIFIED_PRESERVE
    )
    assert found.production_writes_blocked
    assert native_windows == ["native"]


@pytest.mark.parametrize(
    "problem",
    ["native-object", "native-evidence", "directory-object", "directory-evidence"],
)
def test_unqualified_response_shape_refused(
    native_windows: list[str],
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    if problem == "native-object":
        monkeypatch.setattr(
            restart, "review_private_post_attempt_native_restart", lambda *_: object()
        )
    elif problem == "native-evidence":
        monkeypatch.setattr(
            restart,
            "review_private_post_attempt_native_restart",
            lambda *_: _native(production_writes_blocked=False),
        )
    elif problem == "directory-object":
        monkeypatch.setattr(
            probe, "probe_private_windows_directory_flush_contract", lambda: object()
        )
    else:
        monkeypatch.setattr(
            probe,
            "probe_private_windows_directory_flush_contract",
            lambda: _sample(directory_durability_unqualified=False),
        )
    finding = _call()
    assert (
        finding.state
        is policy.PrivateWindowsRestartPolicyState.CONTRADICTORY_EVIDENCE_PRESERVE
    )
    assert finding.automatic_retry_forbidden


@pytest.mark.parametrize(
    "problem",
    [
        "negative-revision",
        "bool-revision",
        "wrong-step-type",
        "other-step",
        "bad-intent",
        "bad-private-root",
        "bad-workspace-root",
    ],
)
def test_invalid_requests_are_rejected_before_native_access(
    native_windows: list[str], problem: str
) -> None:
    step: object = _STEP
    revision: object = 2
    intent: object = canonical._canonical()
    private: object = Path("C:/private")
    workspace: object = Path("C:/workspace")
    if problem == "negative-revision":
        revision = -1
    elif problem == "bool-revision":
        revision = True
    elif problem == "wrong-step-type":
        step = "stage_to_registry"
    elif problem == "other-step":
        step = scratch.PrivateScratchWriterStep.INITIALIZE
    elif problem == "bad-intent":
        intent = object()
    elif problem == "bad-private-root":
        private = "C:/private"
    elif problem == "bad-workspace-root":
        workspace = "C:/workspace"
    # These deliberately malformed arguments test runtime validation.
    review = policy.review_windows_private_pending_recovery_policy(
        cast(scratch.PrivateScratchWriterStep, step),
        cast(int, revision),
        cast(intents.PrivateTransactionIntent, intent),
        cast(Path, private),
        cast(Path, workspace),
    )
    assert review.state is (
        policy.PrivateWindowsRestartPolicyState.OPERATION_NOT_ADMITTED
        if problem == "other-step"
        else policy.PrivateWindowsRestartPolicyState.INVALID_REQUEST
    )
    assert native_windows == []


@pytest.mark.parametrize("platform", ["linux", "darwin", "cygwin"])
def test_unsupported_platform_never_attempts_windows_calls(
    native_windows: list[str], monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    found = _call()
    assert found.state is policy.PrivateWindowsRestartPolicyState.UNSUPPORTED
    assert native_windows == []


@pytest.mark.parametrize("phase", ["native", "directory"])
@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, OSError, ValueError])
def test_native_or_probe_exception_preserves_pending_evidence(
    native_windows: list[str],
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    exception_type: type[BaseException],
) -> None:
    def fail_native(*_args: object) -> restart.PrivatePostAttemptRestartReview:
        raise exception_type("injected")

    def fail_directory() -> probe.PrivateDirectoryFlushReview:
        raise exception_type("injected")

    if phase == "native":
        monkeypatch.setattr(
            restart, "review_private_post_attempt_native_restart", fail_native
        )
    else:
        monkeypatch.setattr(
            probe, "probe_private_windows_directory_flush_contract", fail_directory
        )
    found = _call()
    assert found.state is (
        policy.PrivateWindowsRestartPolicyState.INTERRUPTED_PRESERVE
        if exception_type is KeyboardInterrupt
        else policy.PrivateWindowsRestartPolicyState.IO_ERROR_PRESERVE
    )
    assert found.production_writes_blocked
    assert found.journal_retirement_forbidden
    assert found.automatic_retry_forbidden
    assert found.pending_evidence_must_remain


def test_policy_does_not_publish_a_mutation_or_cleanup_verb() -> None:
    assert not hasattr(policy, "commit")
    assert not hasattr(policy, "replace")
    assert not hasattr(policy, "retire")
    assert not hasattr(policy, "replay")
    assert set(policy._RECOVERY_STATES.values()) == {
        policy.PrivateWindowsRestartPolicyState.PREPARED_STAGE_HOLD_NO_RETRY,
        policy.PrivateWindowsRestartPolicyState.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
        policy.PrivateWindowsRestartPolicyState.BOTH_AFTER_JOURNAL_PENDING_HOLD,
    }


def test_result_does_not_expose_private_paths_or_native_file_ids(
    native_windows: list[str],
) -> None:
    found = _call()
    assert "C:/private" not in repr(found)
    assert "C:/workspace" not in repr(found)
    assert "synthetic-owner" not in str(found.message)
    assert not hasattr(found, "write_token")
    assert not hasattr(found, "file_handle")


def test_qualified_probe_is_never_durability_qualified(
    native_windows: list[str],
) -> None:
    found = _call()
    assert (
        found.state
        is policy.PrivateWindowsRestartPolicyState.PREPARED_STAGE_HOLD_NO_RETRY
    )
    assert found.directory_durability_unqualified
    assert found.durable_commit_unqualified
    assert found.pending_evidence_must_remain
