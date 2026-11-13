"""Core #238 3G22: read-only parent continuity under existing native guards."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_action_preconditions as actions
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_recovery_native_identity_bridge as bridge
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as continuity
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = continuity.PrivateRecoveryParentContinuityState
Step = actions.PrivateRecoveryProposedStep
Checkpoint = recovery.PrivatePostcrashReconciliationState
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
_CASES: dict[Step, tuple[int, bool, Checkpoint]] = {
    Step.REVIEW_PREPARED_RESTART: (7, True, Checkpoint.STAGED_BEFORE_REVIEW_REQUIRED),
    Step.REVIEW_DESCRIPTOR_COMPLETION: (
        8,
        False,
        Checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
    ),
    Step.REVIEW_JOURNAL_RETIREMENT: (
        8,
        False,
        Checkpoint.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
    ),
}


def _images(step: Step) -> continuity._Image:
    stage = _CASES[step][1]
    return (
        b"canonical-intent",
        cast(bytes, _INTENT.registry_before if stage else _INTENT.registry_after),
        cast(
            bytes,
            _INTENT.descriptor_after
            if step is Step.REVIEW_JOURNAL_RETIREMENT
            else _INTENT.descriptor_before,
        ),
        _INTENT.registry_after if stage else None,
    )


def _file_stamps(step: Step) -> bridge._Census:
    images = _images(step)
    a: bridge._Stamp = (1, 100, len(images[0]), 10, 20)
    b: bridge._Stamp = (1, 101, len(images[1]), 10, 20)
    c: bridge._Stamp = (1, 102, len(images[2]), 10, 20)
    staged_image = images[3]
    d: bridge._Stamp | None = (
        (1, 103, len(staged_image), 10, 20) if staged_image is not None else None
    )
    return a, b, c, d


def _parent_stamps() -> continuity._Parents:
    return (
        (1, 201, 0o40700, 10, 20),
        (1, 202, 0o40700, 10, 20),
        (1, 203, 0o40700, 10, 20),
        (1, 204, 0o40700, 10, 20),
    )


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    parents: list[object] | None = None,
    files: list[object] | None = None,
    images: list[object] | None = None,
    checkpoints: list[object] | None = None,
    namespaces: list[object] | None = None,
    owners: list[object] | None = None,
    same: list[object] | None = None,
    error_at: str = "",
    thrown: BaseException | None = None,
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
        lambda value: b"private-registry-" + str(value.revision).encode(),
    )
    active = [False]

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

    def native(
        label: str, values: list[object] | None, default: object
    ) -> Callable[..., object]:
        sequence = iter(values) if values is not None else None

        def wrapped(*_args: object, **_kwargs: object) -> object:
            calls.append(label)
            assert active[0], "native observation escaped retained guard"
            if label == error_at and thrown is not None:
                raise thrown
            return next(sequence) if sequence is not None else default

        return wrapped

    owner = SimpleNamespace(uid="synthetic-teacher")
    stage = _CASES[step][1]
    ns: tuple[frozenset[str], frozenset[str], bool] = (
        frozenset({TX + ".json"}),
        frozenset({"." + TX + ".registry-stage"}) if stage else frozenset(),
        stage,
    )
    monkeypatch.setattr(ordered, "_owner", native("owner", owners, owner))
    monkeypatch.setattr(recovery, "_namespace", native("namespace", namespaces, ns))
    monkeypatch.setattr(operation, "_same_native_namespace", native("same", same, True))
    monkeypatch.setattr(
        continuity, "_parents", native("parents", parents, _parent_stamps())
    )
    monkeypatch.setattr(bridge, "_census", native("files", files, _file_stamps(step)))
    monkeypatch.setattr(
        recovery,
        "_classify_present",
        native("checkpoint", checkpoints, _CASES[step][2]),
    )
    monkeypatch.setattr(
        recovery, "_classify_absent", native("checkpoint", checkpoints, _CASES[step][2])
    )
    monkeypatch.setattr(exact, "_images", native("image", images, _images(step)))


def _review(
    root: Path,
    *,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    revision: int = 7,
    proposal: intents.PrivateTransactionIntent = _INTENT,
) -> continuity.PrivateRecoveryParentContinuityReview:
    return continuity.review_native_private_recovery_parent_continuity(
        step, revision, proposal, root, root
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_three_readonly_rounds_share_one_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step)
    result = _review(tmp_path, step=step, revision=_CASES[step][0])
    assert result.state is State.PARENTS_STABLE_REVIEW_REQUIRED
    assert calls.count("enter") == calls.count("exit") == 1
    assert calls.count("parents") == 4  # three rounds plus final check
    assert (
        calls.count("files") == calls.count("image") == calls.count("checkpoint") == 3
    )
    assert calls[0] == "enter" and calls[-1] == "exit"
    assert not any(
        hasattr(result, name)
        for name in ("path", "bytes", "token", "permit", "handle", "owner")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


@pytest.mark.parametrize("step", list(_CASES))
@pytest.mark.parametrize("wrong", [None, False, True, 0, -1, 1, 7.0, "7"])
def test_revisions_fail_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step, wrong: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step)
    assert _review(tmp_path, step=step, revision=cast(int, wrong)).state in {
        State.INVALID_REQUEST,
        State.REVISION_MISMATCH_REFUSED,
    }
    assert not calls


@pytest.mark.parametrize("step", list(_CASES))
@pytest.mark.parametrize("part", range(4))
def test_parent_id_drift_between_frames_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step, part: int
) -> None:
    changed = list(_parent_stamps())
    old = changed[part]
    changed[part] = (old[0], old[1] + 50, old[2], old[3], old[4])
    _setup(monkeypatch, [], step=step, parents=[_parent_stamps(), tuple(changed)])
    assert (
        _review(tmp_path, step=step, revision=_CASES[step][0]).state
        is State.PARENT_DRIFT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_parent_changed_on_final_check_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    changed = list(_parent_stamps())
    old = changed[0]
    changed[0] = (old[0], old[1] + 1, old[2], old[3], old[4])
    _setup(
        monkeypatch, [], step=step, parents=[_parent_stamps()] * 3 + [tuple(changed)]
    )
    assert (
        _review(tmp_path, step=step, revision=_CASES[step][0]).state
        is State.PARENT_DRIFT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_file_identity_drift_refused_with_same_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    changed = list(_file_stamps(step))
    before = changed[0]
    assert before is not None
    changed[0] = (before[0], before[1] + 100, before[2], before[3], before[4])
    _setup(monkeypatch, [], step=step, files=[_file_stamps(step), tuple(changed)])
    assert (
        _review(tmp_path, step=step, revision=_CASES[step][0]).state
        is State.FILE_IDENTITY_DRIFT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_byte_drift_refused_with_same_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    altered = list(_images(step))
    altered[0] = b"different-pending-journal"
    _setup(monkeypatch, [], step=step, images=[_images(step), tuple(altered)])
    assert (
        _review(tmp_path, step=step, revision=_CASES[step][0]).state
        is State.IMAGE_DRIFT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_first_image_conflict_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    altered = list(_images(step))
    altered[1] = b"foreign-registry"
    _setup(monkeypatch, [], step=step, images=[tuple(altered)])
    assert (
        _review(tmp_path, step=step, revision=_CASES[step][0]).state
        is State.IMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_file_size_disagrees_with_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    altered = list(_file_stamps(step))
    before = altered[0]
    assert before is not None
    altered[0] = (before[0], before[1], before[2] + 1, before[3], before[4])
    _setup(monkeypatch, [], step=step, files=[tuple(altered)])
    assert (
        _review(tmp_path, step=step, revision=_CASES[step][0]).state
        is State.FILE_IDENTITY_UNQUALIFIED
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_checkpoint_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(monkeypatch, [], step=step, checkpoints=[Checkpoint.IMAGES_UNQUALIFIED])
    assert (
        _review(tmp_path, step=step, revision=_CASES[step][0]).state
        is State.CHECKPOINT_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize(
    "where,exception,expected",
    [
        ("parents", continuity._ParentUnqualified(), State.PARENT_IDENTITY_UNQUALIFIED),
        ("parents", FileNotFoundError(), State.NAMESPACE_CHANGED_PRESERVE),
        ("parents", PermissionError(), State.GUARD_REFUSED),
        ("parents", KeyboardInterrupt(), State.INTERRUPTED_PRESERVE),
        ("files", bridge._IdentityUnqualified(), State.FILE_IDENTITY_UNQUALIFIED),
        ("image", OSError(), State.IO_ERROR),
    ],
)
def test_refusals_release_retained_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    where: str,
    exception: BaseException,
    expected: State,
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, error_at=where, thrown=exception)
    assert _review(tmp_path).state is expected
    assert calls.count("exit") == 1


def test_release_failure_refuses(
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


def test_namespace_failure_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [], same=[False])
    assert _review(tmp_path).state is State.NAMESPACE_CHANGED_PRESERVE


def test_owner_change_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _setup(monkeypatch, [], owners=[SimpleNamespace(uid="A"), SimpleNamespace(uid="B")])
    assert _review(tmp_path).state is State.OWNER_CHANGED


def test_initialization_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    changed = _intent()
    object.__setattr__(
        changed.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: changed
    )
    assert _review(tmp_path, proposal=changed).state is State.INITIALIZATION_REFUSED
    assert calls == []


def test_unsupported_platform_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _review(tmp_path).state is State.UNSUPPORTED


@pytest.mark.parametrize("state", list(State))
def test_all_messages_sanitized(state: State) -> None:
    report = continuity._result(state)
    assert (
        report.message and "C:" not in report.message and "/tmp/" not in report.message
    )
    assert not any(
        hasattr(report, name) for name in ("bytes", "path", "handle", "token")
    )


@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native directory IDs"
)
def test_real_parent_directory_path_census(tmp_path: Path) -> None:
    private = tmp_path / "private"
    workspace = tmp_path / "workspace"
    (private / "transactions").mkdir(parents=True)
    (workspace / ".pds").mkdir(parents=True)
    first = continuity._parents(private, workspace)
    second = continuity._parents(private, workspace)
    assert first == second
    assert first[0][:2] != first[1][:2]
    assert first[2][:2] != first[3][:2]


@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native directory IDs"
)
def test_same_name_directory_replacement_changes_identity(tmp_path: Path) -> None:
    before = tmp_path / "root"
    before.mkdir()
    one = continuity._directory_stamp(before)
    before.rename(tmp_path / "old")
    before.mkdir()
    two = continuity._directory_stamp(before)
    assert one[:2] != two[:2]


@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native directory IDs"
)
def test_symlink_directory_refused(tmp_path: Path) -> None:
    target = tmp_path / "actual"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink privilege unavailable")
    with pytest.raises(continuity._ParentUnqualified):
        continuity._directory_stamp(link)


@pytest.mark.skipif(
    sys.platform not in {"linux", "win32"}, reason="native directory IDs"
)
def test_regular_file_cannot_masquerade_as_parent(tmp_path: Path) -> None:
    file = tmp_path / "ordinary"
    file.write_bytes(b"fixed")
    with pytest.raises(continuity._ParentUnqualified):
        continuity._directory_stamp(file)


def test_module_has_no_writer_or_notes_exports() -> None:
    assert not any(
        hasattr(continuity, name)
        for name in ("write", "commit", "retire", "activate_notes", "open_for_write")
    )
