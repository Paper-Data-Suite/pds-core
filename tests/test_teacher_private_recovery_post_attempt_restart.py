"""Core #238 3G47: independent native restart outcome and no-retry boundary."""

from __future__ import annotations

import inspect
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_post_attempt_restart as restart
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents

State = restart.PrivatePostAttemptRestartState
Native = recovery.PrivatePostcrashReconciliationState
Step = scratch.PrivateScratchWriterStep


@pytest.fixture(autouse=True)
def _native_reader_test_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only tests may supply native-owner, path and reconciliation fakes."""
    monkeypatch.setattr(lock_file, "_requested_root", lambda *args: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *args: True)
    monkeypatch.setattr(
        preflight, "_native_observation", lambda *args: (None, object())
    )
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *args: None)
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *args: recovery._result(Native.STAGED_BEFORE_REVIEW_REQUIRED),
    )


def _request() -> intents.PrivateTransactionIntent:
    return canonical._canonical()


def _review() -> restart.PrivatePostAttemptRestartReview:
    return restart.review_private_post_attempt_native_restart(
        Step.STAGE_TO_REGISTRY, 2, _request(), Path("/private"), Path("/workspace")
    )


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        (Native.STAGED_BEFORE_REVIEW_REQUIRED, State.PREPARED_STAGE_PENDING_REVIEW),
        (
            Native.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
            State.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW,
        ),
        (
            Native.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
            State.BOTH_AFTER_JOURNAL_PENDING_REVIEW,
        ),
        (
            Native.STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED,
            State.STAGE_REMAINS_OTHER_CHECKPOINT_PRESERVE,
        ),
        (Native.STAGE_MISSING_BEFORE_REFUSED, State.STAGE_MISSING_BEFORE_PRESERVE),
        (Native.STAGE_MISSING_PARTIAL_REFUSED, State.STAGE_MISSING_PARTIAL_PRESERVE),
        (Native.IMAGES_UNQUALIFIED, State.IMAGE_UNQUALIFIED_PRESERVE),
        (Native.NAMESPACE_UNQUALIFIED, State.NAMESPACE_CONFLICT_PRESERVE),
        (Native.INVALID_REQUEST, State.INTENT_UNQUALIFIED),
        (Native.INITIALIZATION_REFUSED, State.INITIALIZATION_REFUSED),
        (Native.UNSUPPORTED, State.UNSUPPORTED),
        (Native.OWNER_CHANGED, State.OWNER_CHANGED),
        (Native.GUARD_REFUSED, State.GUARD_REFUSED),
        (Native.IO_ERROR, State.IO_ERROR),
    ],
)
def test_native_checkpoint_is_rebuilt_not_promoted(
    monkeypatch: pytest.MonkeyPatch, native: Native, expected: State
) -> None:
    calls: list[object] = []

    def fresh(
        proposed: intents.PrivateTransactionIntent, private: Path, workspace: Path
    ) -> recovery.PrivatePostcrashReconciliationReview:
        calls.append((proposed, private, workspace))
        return recovery._result(native)

    monkeypatch.setattr(
        recovery, "reconcile_native_private_pending_registry_after_interruption", fresh
    )
    result = _review()
    assert result.state is expected
    assert len(calls) == 1
    assert result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain
    assert result.automatic_retry_forbidden
    assert result.production_writes_blocked
    assert result.unqualified_requirements == barrier._REQUIRED
    assert "non_authorizing=True" in repr(result)


@pytest.mark.parametrize(
    "bad", [None, False, True, 0, 2, "stage_to_registry", object()]
)
def test_invalid_step_never_reads_native(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    hits: list[str] = []
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *a: hits.append("read"),
    )
    output = restart.review_private_post_attempt_native_restart(
        cast(Step, bad), 2, _request(), Path("/private"), Path("/workspace")
    )
    assert output.state is State.INVALID_REQUEST
    assert not hits


@pytest.mark.parametrize("bad", [None, False, True, 0, -1, 2.0, "2", object()])
def test_invalid_revision_never_reads_native(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    hits: list[str] = []
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *a: hits.append("read"),
    )
    output = restart.review_private_post_attempt_native_restart(
        Step.STAGE_TO_REGISTRY,
        cast(int, bad),
        _request(),
        Path("/private"),
        Path("/workspace"),
    )
    assert output.state is State.INVALID_REQUEST
    assert not hits


def test_valid_but_other_operation_never_reads_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hits: list[str] = []
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *a: hits.append("read"),
    )
    result = restart.review_private_post_attempt_native_restart(
        Step.DESCRIPTOR_COMPLETION, 2, _request(), Path("/private"), Path("/workspace")
    )
    assert result.state is State.OPERATION_NOT_ADMITTED
    assert not hits


@pytest.mark.parametrize(
    ("root", "workspace"),
    [
        (None, Path("/workspace")),
        (Path("/private"), None),
        ("invalid", Path("/workspace")),
        (Path("/private"), "invalid"),
    ],
)
def test_invalid_paths_never_read_native(
    monkeypatch: pytest.MonkeyPatch, root: object, workspace: object
) -> None:
    hits: list[str] = []
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *a: hits.append("read"),
    )
    result = restart.review_private_post_attempt_native_restart(
        Step.STAGE_TO_REGISTRY, 2, _request(), cast(Path, root), cast(Path, workspace)
    )
    assert result.state is State.INVALID_REQUEST
    assert not hits


def test_unqualified_roots_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *args: False)
    assert _review().state is State.ROOT_UNQUALIFIED


def test_unqualified_workspace_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(descriptor, "_valid_root", lambda *args: False)
    assert _review().state is State.ROOT_UNQUALIFIED


def test_mismatched_barrier_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *a: barrier._result(
            barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ),
    )
    assert _review().state is State.REVISION_MISMATCH_REFUSED


def test_relaxed_barrier_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class Forged:
        def __init__(self) -> None:
            self.state = barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
            self.unqualified_requirements = barrier._REQUIRED

    monkeypatch.setattr(
        barrier, "review_private_production_write_barrier", lambda *a: Forged()
    )
    assert _review().state is State.INTENT_UNQUALIFIED


def test_mismatched_requirements_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *a: replace(
            barrier._result(
                barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
            ),
            unqualified_requirements=(),
        ),
    )
    assert _review().state is State.INTENT_UNQUALIFIED


def test_noncanonical_intent_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda *a: None)
    assert _review().state is State.INTENT_UNQUALIFIED


def test_revision_mismatch_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = _request()
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *a: b"canonical"
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *a: baseline
    )
    monkeypatch.setattr(
        metadata,
        "decode_private_registry",
        lambda raw: SimpleNamespace(
            revision=18 if raw == baseline.registry_before else 19
        ),
    )
    monkeypatch.setattr(
        metadata,
        "encode_private_registry",
        lambda raw: (
            baseline.registry_before if raw.revision == 18 else baseline.registry_after
        ),
    )
    result = restart.review_private_post_attempt_native_restart(
        Step.STAGE_TO_REGISTRY, 2, baseline, Path("/private"), Path("/workspace")
    )
    assert result.state is State.REVISION_MISMATCH_REFUSED


def test_owner_unqualified_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "_native_observation", lambda *a: (object(), None))
    assert _review().state is State.OWNER_OR_PROTECTION_REFUSED


def test_binding_mismatch_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "_intent_owner_and_binding", lambda *a: object())
    assert _review().state is State.BINDING_MISMATCH


def test_native_shape_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *a: object(),
    )
    assert _review().state is State.CHECKPOINT_CONFLICT_PRESERVE


def test_native_state_shape_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        recovery,
        "reconcile_native_private_pending_registry_after_interruption",
        lambda *a: replace(
            recovery._result(Native.STAGED_BEFORE_REVIEW_REQUIRED),
            state=cast(Native, "corrupt"),
        ),
    )
    assert _review().state is State.CHECKPOINT_CONFLICT_PRESERVE


@pytest.mark.parametrize(
    "raised",
    [KeyboardInterrupt, PermissionError, FileNotFoundError, ValueError, RuntimeError],
)
def test_native_exceptions_fail_closed(
    monkeypatch: pytest.MonkeyPatch, raised: type[BaseException]
) -> None:
    def stop(*args: object) -> None:
        raise raised()

    monkeypatch.setattr(
        recovery, "reconcile_native_private_pending_registry_after_interruption", stop
    )
    result = _review()
    assert result.state is (
        State.INTERRUPTED_PRESERVE if raised is KeyboardInterrupt else State.IO_ERROR
    )
    assert result.automatic_retry_forbidden


def test_unsupported_platform_prevents_native_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _review().state is State.UNSUPPORTED


def test_return_is_frozen_and_sanitized() -> None:
    item = _review()
    with pytest.raises(FrozenInstanceError):
        setattr(item, "state", State.IO_ERROR)
    assert "private" not in repr(item)
    assert "workspace" not in repr(item)
    assert "registry.json" not in item.message


def test_source_never_contains_production_mutation() -> None:
    source = inspect.getsource(restart)
    assert "os.replace(" not in source
    assert "os.unlink(" not in source
    assert 'open("w' not in source
    assert "journal_retirement" not in source
    assert "reconcile_native_private_pending_registry_after_interruption" in source
    assert "review_private_production_write_barrier" in source


@pytest.mark.parametrize("state", list(State))
def test_all_return_states_are_pathless_and_non_authorizing(state: State) -> None:
    review = restart._result(state)
    assert review.automatic_retry_forbidden
    assert review.pending_evidence_must_remain
    assert review.production_writes_blocked
    assert review.replacement_may_have_occurred
    assert "non_authorizing=True" in repr(review)
    assert "C:\\" not in review.message
    assert "/home/" not in review.message
