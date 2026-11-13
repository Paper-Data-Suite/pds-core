"""Core #238 3G28: native checkpoint + single admitted synthetic writer step.

All native parent/registry/descriptor/journal interaction belongs to 3G22's
already-tested retained guard, emulated here to verify the integration contract.
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import (
    _teacher_private_recovery_native_writer_checkpoint_admission as gate,
)
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents

State = gate.PrivateNativeWriterCheckpointState
ParentState = parents.PrivateRecoveryParentContinuityState
Kind = scratch.PrivateScratchWriterStep


def _intent() -> intents.PrivateTransactionIntent:
    # No user metadata, filenames, owner values, or mutable production state.
    return object.__new__(intents.PrivateTransactionIntent)


def _review(
    root: Path,
    operation: Kind = Kind.STAGE_TO_REGISTRY,
    revision: int = 7,
    proposed: intents.PrivateTransactionIntent | None = None,
) -> gate.PrivateNativeWriterCheckpointReview:
    return gate.review_native_private_writer_checkpoint_admission(
        operation, revision, _intent() if proposed is None else proposed, root, root
    )


def _simulate(
    monkeypatch: pytest.MonkeyPatch,
    result: object,
) -> list[tuple[object, ...]]:
    calls: list[tuple[object, ...]] = []

    def read(*args: object) -> object:
        calls.append(args)
        return result

    monkeypatch.setattr(
        parents, "review_native_private_recovery_parent_continuity", read
    )
    return calls


def _parent(state: ParentState) -> parents.PrivateRecoveryParentContinuityReview:
    return parents.PrivateRecoveryParentContinuityReview(state, "internal-native-image")


def test_prepared_checkpoint_calls_exact_real_native_reader_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proposed = _intent()
    calls = _simulate(monkeypatch, _parent(ParentState.PARENTS_STABLE_REVIEW_REQUIRED))
    report = _review(tmp_path, proposed=proposed)
    assert report.state is State.PREPARED_EVIDENCE_REVIEW_ONLY
    assert calls == [
        (
            actions.PrivateRecoveryProposedStep.REVIEW_PREPARED_RESTART,
            7,
            proposed,
            tmp_path,
            tmp_path,
        )
    ]
    assert "released" in report.message and "refused" in report.message


_FAILURES = (
    (ParentState.PARENT_IDENTITY_UNQUALIFIED, State.PARENT_IDENTITY_CONFLICT_PRESERVE),
    (ParentState.PARENT_DRIFT_PRESERVE, State.PARENT_IDENTITY_CONFLICT_PRESERVE),
    (ParentState.FILE_IDENTITY_UNQUALIFIED, State.FILE_IDENTITY_CONFLICT_PRESERVE),
    (ParentState.FILE_IDENTITY_DRIFT_PRESERVE, State.FILE_IDENTITY_CONFLICT_PRESERVE),
    (ParentState.IMAGE_CONFLICT_PRESERVE, State.IMAGE_CONFLICT_PRESERVE),
    (ParentState.IMAGE_DRIFT_PRESERVE, State.IMAGE_CONFLICT_PRESERVE),
    (ParentState.CHECKPOINT_CONFLICT_PRESERVE, State.CHECKPOINT_CONFLICT_PRESERVE),
    (ParentState.NAMESPACE_CHANGED_PRESERVE, State.NAMESPACE_CONFLICT_PRESERVE),
    (ParentState.OWNER_CHANGED, State.OWNER_CHANGED),
    (ParentState.GUARD_REFUSED, State.GUARD_REFUSED),
    (ParentState.REVISION_MISMATCH_REFUSED, State.REVISION_MISMATCH_REFUSED),
    (ParentState.ACTION_MISMATCH_REFUSED, State.ACTION_MISMATCH_REFUSED),
    (ParentState.INITIALIZATION_REFUSED, State.INITIALIZATION_REFUSED),
    (ParentState.INTERRUPTED_PRESERVE, State.INTERRUPTED_PRESERVE),
    (ParentState.INVALID_REQUEST, State.INVALID_REQUEST),
    (ParentState.UNSUPPORTED, State.UNSUPPORTED),
    (ParentState.IO_ERROR, State.IO_ERROR),
)


@pytest.mark.parametrize("native,expected", _FAILURES)
def test_native_failure_cannot_become_writer_admission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    native: ParentState,
    expected: State,
) -> None:
    calls = _simulate(monkeypatch, _parent(native))
    report = _review(tmp_path)
    assert report.state is expected
    assert len(calls) == 1
    assert report.state is not State.PREPARED_EVIDENCE_REVIEW_ONLY


@pytest.mark.parametrize(
    "operation", [x for x in Kind if x is not Kind.STAGE_TO_REGISTRY]
)
def test_non_stage_operations_denied_without_native_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: Kind
) -> None:
    calls = _simulate(monkeypatch, _parent(ParentState.PARENTS_STABLE_REVIEW_REQUIRED))
    assert _review(tmp_path, operation).state is State.OPERATION_NOT_ADMITTED
    assert calls == []


@pytest.mark.parametrize(
    "invalid", [None, "stage_to_registry", True, 1, 0, object(), (), {}]
)
def test_invalid_operation_denied_before_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    calls = _simulate(monkeypatch, _parent(ParentState.PARENTS_STABLE_REVIEW_REQUIRED))
    assert _review(tmp_path, cast(Kind, invalid)).state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("invalid", [-1, 0, True, 7.0, "7", None, {}, object()])
def test_invalid_revision_denied_before_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    calls = _simulate(monkeypatch, _parent(ParentState.PARENTS_STABLE_REVIEW_REQUIRED))
    assert _review(tmp_path, revision=cast(int, invalid)).state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("invalid", [None, False, [], {}, object(), b"forged"])
def test_invalid_intent_denied_before_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    calls = _simulate(monkeypatch, _parent(ParentState.PARENTS_STABLE_REVIEW_REQUIRED))
    assert (
        gate.review_native_private_writer_checkpoint_admission(
            Kind.STAGE_TO_REGISTRY,
            7,
            cast(intents.PrivateTransactionIntent, invalid),
            tmp_path,
            tmp_path,
        ).state
        is State.INVALID_REQUEST
    )
    assert calls == []


@pytest.mark.parametrize("bad", [None, "C:/data", b"path", object(), 22])
@pytest.mark.parametrize("which", ["private", "workspace"])
def test_invalid_root_denied_before_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    which: str,
    bad: object,
) -> None:
    calls = _simulate(monkeypatch, _parent(ParentState.PARENTS_STABLE_REVIEW_REQUIRED))
    first: object = bad if which == "private" else tmp_path
    second: object = bad if which == "workspace" else tmp_path
    assert (
        gate.review_native_private_writer_checkpoint_admission(
            Kind.STAGE_TO_REGISTRY,
            7,
            _intent(),
            cast(Path, first),
            cast(Path, second),
        ).state
        is State.INVALID_REQUEST
    )
    assert calls == []


@pytest.mark.parametrize(
    "bad",
    [
        None,
        object(),
        ParentState.PARENTS_STABLE_REVIEW_REQUIRED,
        "parents_stable_review_required",
        (ParentState.PARENTS_STABLE_REVIEW_REQUIRED,),
    ],
)
def test_forged_native_result_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    _simulate(monkeypatch, bad)
    assert _review(tmp_path).state is State.INVALID_REQUEST


@pytest.mark.parametrize("bad", [None, "parents_stable_review_required", 0, object()])
def test_forged_native_state_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    _simulate(
        monkeypatch,
        parents.PrivateRecoveryParentContinuityReview(
            cast(ParentState, bad), "untrusted"
        ),
    )
    assert _review(tmp_path).state is State.INVALID_REQUEST


@pytest.mark.parametrize(
    "failure,expected",
    [
        (KeyboardInterrupt(), State.INTERRUPTED_PRESERVE),
        (PermissionError("sensitive-private-path"), State.GUARD_REFUSED),
        (FileNotFoundError("sensitive-private-path"), State.IO_ERROR),
        (OSError("sensitive-private-path"), State.IO_ERROR),
        (ValueError("sensitive-private-path"), State.IO_ERROR),
        (TypeError("sensitive-private-path"), State.IO_ERROR),
        (AttributeError("sensitive-private-path"), State.IO_ERROR),
        (OverflowError("sensitive-private-path"), State.IO_ERROR),
    ],
)
def test_native_exception_sanitized_without_permit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: BaseException,
    expected: State,
) -> None:
    def fail(*_args: object) -> None:
        raise failure

    monkeypatch.setattr(
        parents, "review_native_private_recovery_parent_continuity", fail
    )
    report = _review(tmp_path)
    assert report.state is expected
    assert "sensitive-private-path" not in report.message
    assert not any(
        hasattr(report, x)
        for x in (
            "path",
            "root",
            "owner",
            "handle",
            "permit",
            "token",
            "image",
            "bytes",
        )
    )


@pytest.mark.parametrize("state", list(State))
def test_every_return_status_is_sanitized_and_frozen(state: State) -> None:
    result = gate._result(state)
    assert result.state is state
    assert (
        result.message and "C:/" not in result.message and "\\\\" not in result.message
    )
    assert not any(
        hasattr(result, name)
        for name in (
            "file_id",
            "handle",
            "path",
            "root",
            "permit",
            "token",
            "bytes",
            "write",
        )
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.INVALID_REQUEST)


def test_no_reentrant_guard_or_real_writer_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _simulate(monkeypatch, _parent(ParentState.PARENTS_STABLE_REVIEW_REQUIRED))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no writer or second retained guard")

    monkeypatch.setattr(scratch, "rehearse_synthetic_writer_owned_admission", forbidden)
    assert _review(tmp_path).state is State.PREPARED_EVIDENCE_REVIEW_ONLY


def test_real_parent_reader_is_the_only_native_checkpoint_entrypoint() -> None:
    source = inspect.getsource(gate.review_native_private_writer_checkpoint_admission)
    assert "parents.review_native_private_recovery_parent_continuity(" in source
    for forbidden in (
        "os.replace(",
        "write_bytes(",
        "rehearse_synthetic_writer_owned_admission(",
        "_hold_existing_retained_descriptor_guard(",
        "unlink(",
    ):
        assert forbidden not in source
    assert "guard has ALREADY" in source


def test_native_parent_coverage_is_complete() -> None:
    assert set(gate._PARENT_FAILURES) == (
        set(ParentState) - {ParentState.PARENTS_STABLE_REVIEW_REQUIRED}
    )
    assert len(gate._PARENT_FAILURES) == len(ParentState) - 1


def test_committed_parent_reviewer_owns_native_guard_and_exact_checkpoints() -> None:
    # Review the actual 3G22 function source. It, not this bridge, owns
    # the native guard and verifies exact checkpoint and identity evidence.
    source = inspect.getsource(parents.review_native_private_recovery_parent_continuity)
    for required in (
        "retained._hold_existing_retained_descriptor_guard(",
        "operation._same_native_namespace(",
        "recovery._classify_present(",
        "recovery._classify_absent(",
        "exact._images(",
        "bridge._census(",
        "_parents(",
    ):
        assert required in source
