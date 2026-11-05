"""Core #238 3G30: protected operation-owned dry-run, never execution."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = scope.PrivateProtectedWriterScopeState
Step = scratch.PrivateScratchWriterStep
TX = "11111111-1111-4111-8111-111111111111"


def _intent() -> intents.PrivateTransactionIntent:
    item = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        item,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            transaction_id=TX,
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(item, "registry_before", b"private-registry-7")
    object.__setattr__(item, "registry_after", b"private-registry-8")
    object.__setattr__(item, "descriptor_before", b"private-descriptor-7")
    object.__setattr__(item, "descriptor_after", b"private-descriptor-8")
    return item


_INTENT = _intent()
_IMAGES: parents._Image = (
    b"canonical-intent",
    b"private-registry-7",
    b"private-descriptor-7",
    b"private-registry-8",
)
_STAMPS: parents._Parents = (
    (1, 201, 0o40700, 10, 20),
    (1, 202, 0o40700, 10, 20),
    (1, 203, 0o40700, 10, 20),
    (1, 204, 0o40700, 10, 20),
)
_FILES: bridge._Census = (
    (1, 101, len(_IMAGES[0]), 10, 20),
    (1, 102, len(_IMAGES[1]), 10, 20),
    (1, 103, len(_IMAGES[2]), 10, 20),
    (1, 104, len(_IMAGES[3] or b""), 10, 20),
)
_CHECKPOINT = recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED


def _frame(
    *,
    parents_value: parents._Parents = _STAMPS,
    files_value: bridge._Census = _FILES,
    image_value: parents._Image = _IMAGES,
    checkpoint: recovery.PrivatePostcrashReconciliationState = _CHECKPOINT,
) -> scope._Frame:
    return scope._Frame(parents_value, files_value, image_value, checkpoint)


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    frames: list[object] | None = None,
    owners: list[object] | None = None,
    namespaces: list[object] | None = None,
    same: list[object] | None = None,
    error_at: str = "",
    exception: BaseException | None = None,
    release_error: BaseException | None = None,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: b"canonical-intent"
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: _INTENT
    )
    monkeypatch.setattr(
        metadata,
        "decode_private_registry",
        lambda raw: SimpleNamespace(revision=7 if raw == b"private-registry-7" else 8),
    )
    monkeypatch.setattr(
        metadata,
        "encode_private_registry",
        lambda item: b"private-registry-" + str(item.revision).encode(),
    )
    active = [False]

    @contextmanager
    def hold(*_args: object) -> Iterator[None]:
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

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", hold)

    def observer(
        label: str, values: list[object] | None, default: object
    ) -> Callable[..., object]:
        iterator = iter(values) if values is not None else None

        def call(*_args: object, **_kwargs: object) -> object:
            calls.append(label)
            assert active[0], "Native state was read outside the retained guard"
            if error_at == label and exception is not None:
                raise exception
            return next(iterator) if iterator is not None else default

        return call

    owner = SimpleNamespace(uid="teacher-synthetic")
    namespace = (frozenset({TX + ".json"}), frozenset({"." + TX + ".stage"}), True)
    monkeypatch.setattr(ordered, "_owner", observer("owner", owners, owner))
    monkeypatch.setattr(
        recovery, "_namespace", observer("namespace", namespaces, namespace)
    )
    monkeypatch.setattr(
        operation, "_same_native_namespace", observer("same", same, True)
    )
    monkeypatch.setattr(scope, "_observe", observer("frame", frames, _frame()))
    monkeypatch.setattr(parents, "_parents", observer("final-parent", None, _STAMPS))


def _review(
    root: Path,
    *,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
    proposed: intents.PrivateTransactionIntent = _INTENT,
) -> scope.PrivateProtectedWriterScopeReview:
    return scope.review_protected_native_writer_scope_dry_run(
        step, revision, proposed, root, root
    )


def test_three_frames_one_guard_no_writer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    report = _review(tmp_path)
    assert report.state is State.PREPARED_SCOPE_DRY_RUN_ONLY
    assert calls.count("enter") == calls.count("exit") == 1
    assert calls.count("frame") == 3
    assert calls[0] == "enter" and calls[-1] == "exit"
    assert not any(
        hasattr(report, key)
        for key in ("path", "handle", "bytes", "token", "permit", "writer")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(report, "state", State.INVALID_REQUEST)


@pytest.mark.parametrize("invalid", [None, False, 0, 1, -1, 7.0, "7", {}, object()])
def test_invalid_revision_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, revision=cast(int, invalid)).state in {
        State.INVALID_REQUEST,
        State.REVISION_MISMATCH_REFUSED,
    }
    assert not calls


@pytest.mark.parametrize("invalid", [None, 0, True, "stage_to_registry", {}, object()])
def test_invalid_step_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, step=cast(Step, invalid)).state is State.INVALID_REQUEST
    assert not calls


@pytest.mark.parametrize(
    "step", [part for part in Step if part is not Step.STAGE_TO_REGISTRY]
)
def test_only_prepared_registry_step_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, step=step).state is State.OPERATION_NOT_ADMITTED
    assert not calls


@pytest.mark.parametrize("part", range(4))
def test_parent_drift_between_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    altered = list(_STAMPS)
    old = altered[part]
    altered[part] = (old[0], old[1] + 100, old[2], old[3], old[4])
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        frames=[_frame(), _frame(parents_value=cast(parents._Parents, tuple(altered)))],
    )
    assert _review(tmp_path).state is State.PARENT_CONFLICT_PRESERVE
    assert calls.count("exit") == 1


@pytest.mark.parametrize("part", range(4))
def test_file_identity_drift_between_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    altered = list(_FILES)
    original = altered[part]
    assert original is not None
    altered[part] = (
        original[0],
        original[1] + 1,
        original[2],
        original[3],
        original[4],
    )
    _setup(
        monkeypatch,
        [],
        frames=[_frame(), _frame(files_value=cast(bridge._Census, tuple(altered)))],
    )
    assert _review(tmp_path).state is State.FILE_CONFLICT_PRESERVE


@pytest.mark.parametrize("part", range(4))
def test_byte_drift_between_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    altered = list(_IMAGES)
    altered[part] = b"changed"
    _setup(
        monkeypatch,
        [],
        frames=[_frame(), _frame(image_value=cast(parents._Image, tuple(altered)))],
    )
    assert _review(tmp_path).state is State.IMAGE_CONFLICT_PRESERVE


@pytest.mark.parametrize("part", range(4))
def test_file_size_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: int
) -> None:
    altered = list(_FILES)
    stamp = altered[part]
    assert stamp is not None
    altered[part] = (stamp[0], stamp[1], stamp[2] + 1, stamp[3], stamp[4])
    _setup(
        monkeypatch,
        [],
        frames=[_frame(files_value=cast(bridge._Census, tuple(altered)))],
    )
    assert _review(tmp_path).state is State.FILE_CONFLICT_PRESERVE


@pytest.mark.parametrize(
    "checkpoint",
    [
        entry
        for entry in recovery.PrivatePostcrashReconciliationState
        if entry is not _CHECKPOINT
    ],
)
def test_wrong_checkpoint_preserves(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    checkpoint: recovery.PrivatePostcrashReconciliationState,
) -> None:
    _setup(monkeypatch, [], frames=[_frame(checkpoint=checkpoint)])
    assert _review(tmp_path).state is State.CHECKPOINT_CONFLICT_PRESERVE


@pytest.mark.parametrize("wrong", [None, False, (), [], {}, "garbled"])
def test_malformed_native_frames_preserve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, wrong: object
) -> None:
    _setup(monkeypatch, [], frames=[wrong])
    assert _review(tmp_path).state in {State.INVALID_REQUEST, State.IO_ERROR}


@pytest.mark.parametrize(
    "label,exception,expected",
    [
        ("frame", parents._ParentUnqualified(), State.PARENT_CONFLICT_PRESERVE),
        ("frame", bridge._IdentityUnqualified(), State.FILE_CONFLICT_PRESERVE),
        ("frame", FileNotFoundError(), State.NAMESPACE_CONFLICT_PRESERVE),
        ("frame", PermissionError(), State.GUARD_REFUSED),
        ("frame", KeyboardInterrupt(), State.INTERRUPTED_PRESERVE),
        ("frame", OSError(), State.IO_ERROR),
    ],
)
def test_observer_error_releases_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    label: str,
    exception: BaseException,
    expected: State,
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, error_at=label, exception=exception)
    assert _review(tmp_path).state is expected
    assert calls.count("exit") == 1


def test_guard_release_failure_fails_closed(
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


def test_namespace_changed_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [], same=[True, True, False])
    assert _review(tmp_path).state is State.NAMESPACE_CONFLICT_PRESERVE


def test_owner_changed_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(
        monkeypatch, [], owners=[SimpleNamespace(uid="one"), SimpleNamespace(uid="two")]
    )
    assert _review(tmp_path).state is State.OWNER_CHANGED


def test_initialization_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed = _intent()
    object.__setattr__(
        changed.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    calls: list[str] = []
    _setup(monkeypatch, calls)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: changed
    )
    assert _review(tmp_path, proposed=changed).state is State.INITIALIZATION_REFUSED
    assert not calls


def test_unsupported_platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _review(tmp_path).state is State.UNSUPPORTED


@pytest.mark.parametrize("state", list(State))
def test_status_messages_are_sanitized(state: State) -> None:
    report = scope._result(state)
    assert "C:" not in report.message and "/tmp/" not in report.message
    assert not any(
        hasattr(report, name) for name in ("bytes", "path", "handle", "permit", "token")
    )


def test_no_writer_api_exports() -> None:
    assert not hasattr(scope, "commit_registry")
    assert not hasattr(scope, "run_writer")
    assert "os.replace" not in (scope.__doc__ or "")


def test_observe_reuses_actual_read_only_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Protected observer directly composes the established helper functions."""
    calls: list[str] = []

    def record(label: str, value: object) -> Callable[..., object]:
        def observe(*_args: object) -> object:
            calls.append(label)
            return value

        return observe

    monkeypatch.setattr(parents, "_parents", record("parents", _STAMPS))
    monkeypatch.setattr(bridge, "_census", record("files", _FILES))
    monkeypatch.setattr(exact, "_images", record("images", _IMAGES))
    monkeypatch.setattr(
        recovery, "_classify_present", record("checkpoint", _CHECKPOINT)
    )
    result = scope._observe(
        tmp_path,
        tmp_path,
        _INTENT,
        cast(inspection.EffectiveOSOwner, SimpleNamespace(uid="owner")),
        len(_IMAGES[0]),
    )
    assert result == _frame()
    assert calls == ["images", "parents", "files", "checkpoint"]


def test_observe_rejects_unqualified_byte_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(exact, "_images", lambda *_: None)
    with pytest.raises(scope._ImageUnqualified):
        scope._observe(
            tmp_path,
            tmp_path,
            _INTENT,
            cast(inspection.EffectiveOSOwner, SimpleNamespace(uid="owner")),
            15,
        )


def test_incorrect_registry_revision_rejected_pre_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    assert _review(tmp_path, revision=8).state is State.REVISION_MISMATCH_REFUSED
    assert not calls
