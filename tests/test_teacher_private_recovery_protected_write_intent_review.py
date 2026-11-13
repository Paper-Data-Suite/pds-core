"""Core #238 Slice 3G33: inert intent revalidation under one native guard."""

from __future__ import annotations

import hashlib
import inspect
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_protected_write_intent_review as review
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = review.PrivateProtectedWriteIntentState
Step = scratch.PrivateScratchWriterStep
TX = "11111111-1111-4111-8111-111111111111"
JOURNAL = b"canonical-journal-in-scope"
BEFORE = b"canonical-registry-before"
AFTER = b"canonical-registry-after"
DESCRIPTOR = b"canonical-descriptor-before"
DESCRIPTOR_AFTER = b"canonical-descriptor-after"
IMAGES: parents._Image = (JOURNAL, BEFORE, DESCRIPTOR, AFTER)
PARENTS: parents._Parents = (
    (1, 201, 0o40700, 10, 20),
    (1, 202, 0o40700, 10, 20),
    (1, 203, 0o40700, 10, 20),
    (1, 204, 0o40700, 10, 20),
)
FILES = (
    (1, 101, len(JOURNAL), 10, 20),
    (1, 102, len(BEFORE), 10, 20),
    (1, 103, len(DESCRIPTOR), 10, 20),
    (1, 104, len(AFTER), 10, 20),
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _intent() -> intents.PrivateTransactionIntent:
    item = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(item, "witness", SimpleNamespace(transaction_id=TX))
    for key, value in {
        "registry_before": BEFORE,
        "registry_after": AFTER,
        "descriptor_before": DESCRIPTOR,
        "descriptor_after": DESCRIPTOR_AFTER,
    }.items():
        object.__setattr__(item, key, value)
    return item


CANDIDATE = _intent()


def _description() -> prepared.PrivatePreparedWriteDescription:
    return prepared.PrivatePreparedWriteDescription(
        step=Step.STAGE_TO_REGISTRY,
        binding_operation=witness.PrivateBindingOperation.REBIND_MOVE,
        expected_revision=7,
        resulting_revision=8,
        transaction_id=TX,
        pending_intent_sha256=_sha(JOURNAL),
        registry_before_sha256=_sha(BEFORE),
        staged_registry_sha256=_sha(AFTER),
        descriptor_before_sha256=_sha(DESCRIPTOR),
        descriptor_after_sha256=_sha(DESCRIPTOR_AFTER),
    )


def _frame(images: parents._Image = IMAGES) -> scope._Frame:
    return scope._Frame(
        PARENTS,
        FILES,
        images,
        recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
    )


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    frames: list[object] | None = None,
    owners: list[object] | None = None,
    namespaces: list[object] | None = None,
    same: list[object] | None = None,
    release_error: BaseException | None = None,
    frame_error: BaseException | None = None,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: JOURNAL
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: CANDIDATE
    )
    original_description = _description()
    active = [False]
    calls_to_describe = [0]

    def describe(*_args: object) -> prepared.PrivatePreparedWriteIntentReview:
        calls.append("describe")
        calls_to_describe[0] += 1
        if calls_to_describe[0] >= 2:
            assert active[0], "Second canonical description must be inside native guard"
        return prepared.PrivatePreparedWriteIntentReview(
            prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED,
            prepared._MESSAGES[
                prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
            ],
            original_description,
        )

    monkeypatch.setattr(
        prepared, "describe_private_prepared_stage_write_intent", describe
    )

    @contextmanager
    def guard(*_args: object) -> Iterator[None]:
        calls.append("enter")
        assert not active[0]
        active[0] = True
        try:
            yield
        finally:
            active[0] = False
            calls.append("exit")
            if release_error is not None:
                raise release_error

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)

    def observer(
        label: str, items: list[object] | None, default: object
    ) -> Callable[..., object]:
        iterator = iter(items) if items is not None else None

        def call(*_args: object, **_kwargs: object) -> object:
            calls.append(label)
            assert active[0], "Native evidence was read outside the guard"
            if label == "frame" and frame_error is not None:
                raise frame_error
            return next(iterator) if iterator is not None else default

        return call

    owner = SimpleNamespace(uid="synthetic-local-owner")
    namespace = (frozenset({TX + ".json"}), frozenset({TX + ".stage"}), True)
    monkeypatch.setattr(ordered, "_owner", observer("owner", owners, owner))
    monkeypatch.setattr(
        recovery, "_namespace", observer("namespace", namespaces, namespace)
    )
    monkeypatch.setattr(
        operation, "_same_native_namespace", observer("same", same, True)
    )
    monkeypatch.setattr(scope, "_observe", observer("frame", frames, _frame()))
    monkeypatch.setattr(parents, "_parents", observer("final-parent", None, PARENTS))


def _review(
    root: Path, revision: int = 7, step: Step = Step.STAGE_TO_REGISTRY
) -> review.PrivateProtectedWriteIntentReview:
    return review.review_protected_native_prepared_write_intent(
        step, revision, CANDIDATE, root, root
    )


def test_one_guard_three_frames_two_descriptions_no_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    result = _review(tmp_path)
    assert result.state is State.PROTECTED_INTENT_REVIEW_ONLY
    assert calls.count("describe") == 2
    assert calls.count("enter") == calls.count("exit") == 1
    assert calls.count("frame") == 3
    assert calls.index("describe") < calls.index("enter")
    assert calls[-1] == "exit"
    assert not any(
        hasattr(result, key)
        for key in ("path", "handle", "bytes", "permit", "writer", "token")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


@pytest.mark.parametrize("revision", [None, True, -1, 0, 7.0, "7", {}, object()])
def test_invalid_revision_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, revision: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, cast(int, revision)).state is State.INVALID_REQUEST
    assert not calls


@pytest.mark.parametrize("bad", [None, True, 1, "stage_to_registry", {}, object()])
def test_invalid_step_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, step=cast(Step, bad)).state is State.INVALID_REQUEST
    assert not calls


@pytest.mark.parametrize("step", [s for s in Step if s is not Step.STAGE_TO_REGISTRY])
def test_other_operations_not_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, step=step).state is State.OPERATION_NOT_ADMITTED
    assert not calls


def test_first_description_refusal_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    monkeypatch.setattr(
        prepared,
        "describe_private_prepared_stage_write_intent",
        lambda *_: prepared.PrivatePreparedWriteIntentReview(
            prepared.PrivatePreparedWriteIntentState.NONCANONICAL_INTENT_REFUSED,
            "Refused",
            None,
        ),
    )
    assert _review(tmp_path).state is State.NONCANONICAL_INTENT_REFUSED
    assert "enter" not in calls


def test_changed_description_inside_guard_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    index = [0]

    def swapped(*_args: object) -> prepared.PrivatePreparedWriteIntentReview:
        index[0] += 1
        entry = _description()
        if index[0] == 2:
            entry = replace(entry, staged_registry_sha256="0" * 64)
        return prepared.PrivatePreparedWriteIntentReview(
            prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED,
            "Synthetic only",
            entry,
        )

    monkeypatch.setattr(
        prepared, "describe_private_prepared_stage_write_intent", swapped
    )
    assert _review(tmp_path).state is State.INTENT_DRIFT_PRESERVE
    assert calls.count("enter") == calls.count("exit") == 1
    assert "frame" not in calls


def test_tampered_pending_journal_digest_fails_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [])
    wrong = replace(_description(), pending_intent_sha256="0" * 64)
    monkeypatch.setattr(
        prepared,
        "describe_private_prepared_stage_write_intent",
        lambda *_: prepared.PrivatePreparedWriteIntentReview(
            prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED,
            "Synthetic only",
            wrong,
        ),
    )
    assert _review(tmp_path).state is State.INTENT_DRIFT_PRESERVE


@pytest.mark.parametrize("part", range(4))
def test_native_byte_image_drift_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    altered = list(IMAGES)
    altered[part] = b"wrong-image"
    _setup(
        monkeypatch, [], frames=[_frame(), _frame(cast(parents._Image, tuple(altered)))]
    )
    assert _review(tmp_path).state is State.IMAGE_CONFLICT_PRESERVE


def test_descriptor_after_digest_not_a_native_after_image() -> None:
    forged = replace(_description(), descriptor_after_sha256="0" * 64)
    assert not review._fingerprints_match(_frame(), forged, CANDIDATE)


def test_native_owner_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [], owners=[SimpleNamespace(uid="A"), SimpleNamespace(uid="B")])
    assert _review(tmp_path).state is State.OWNER_CHANGED


def test_native_namespace_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [], same=[True, True, False])
    assert _review(tmp_path).state is State.NAMESPACE_CONFLICT_PRESERVE


def test_guard_release_failure_overrides_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(
        monkeypatch,
        [],
        release_error=retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
        ),
    )
    assert _review(tmp_path).state is State.GUARD_REFUSED


@pytest.mark.parametrize(
    "error,state",
    [
        (PermissionError(), State.GUARD_REFUSED),
        (KeyboardInterrupt(), State.INTERRUPTED_PRESERVE),
        (FileNotFoundError(), State.NAMESPACE_CONFLICT_PRESERVE),
        (OSError(), State.IO_ERROR),
    ],
)
def test_observer_failure_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: BaseException, state: State
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, frame_error=error)
    assert _review(tmp_path).state is state
    assert calls.count("exit") == 1


def test_unsupported_platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _review(tmp_path).state is State.UNSUPPORTED


@pytest.mark.parametrize("state", list(State))
def test_sanitized_advisory_states(state: State) -> None:
    result = review._result(state)
    assert result.message == review._MESSAGES[state]
    assert "C:" not in result.message and "/tmp" not in result.message
    assert not hasattr(result, "description")
    assert "non_authorizing" in repr(result)


def test_no_writer_or_callback_interface() -> None:
    source = inspect.getsource(review)
    for fragment in (
        "os.replace(",
        "unlink(",
        "write_bytes(",
        "open(",
        "TemporaryDirectory(",
    ):
        assert fragment not in source
    signature = inspect.signature(review.review_protected_native_prepared_write_intent)
    for forbidden in ("callback", "writer", "handle", "permit", "guard", "description"):
        assert forbidden not in signature.parameters


def test_forged_description_digest_rejected_even_if_frame_classifier_stubbed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [])
    false_description = replace(_description(), staged_registry_sha256="0" * 64)
    monkeypatch.setattr(
        prepared,
        "describe_private_prepared_stage_write_intent",
        lambda *_: prepared.PrivatePreparedWriteIntentReview(
            prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED,
            "synthetic",
            false_description,
        ),
    )
    monkeypatch.setattr(scope, "_frame_state", lambda *_: None)
    assert _review(tmp_path).state is State.IMAGE_CONFLICT_PRESERVE
