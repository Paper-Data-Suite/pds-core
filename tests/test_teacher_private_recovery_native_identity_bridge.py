"""Core #238 3G21: native recovery path identities within one retained guard."""

from __future__ import annotations

import os
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
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = bridge.PrivateNativeIdentityBridgeState
Step = actions.PrivateRecoveryProposedStep
Checkpoint = recovery.PrivatePostcrashReconciliationState
TX = "11111111-1111-4111-8111-111111111111"


def _intent() -> intents.PrivateTransactionIntent:
    proposal = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        proposal,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            transaction_id=TX,
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(proposal, "registry_before", b"private-registry-7")
    object.__setattr__(proposal, "registry_after", b"private-registry-8")
    object.__setattr__(proposal, "descriptor_before", b"private-descriptor-7")
    object.__setattr__(proposal, "descriptor_after", b"private-descriptor-8")
    return proposal


_INTENT = _intent()
_CASES: dict[Step, tuple[int, bool, Checkpoint, State]] = {
    Step.REVIEW_PREPARED_RESTART: (
        7,
        True,
        Checkpoint.STAGED_BEFORE_REVIEW_REQUIRED,
        State.PREPARED_IDENTITY_REVIEW_REQUIRED,
    ),
    Step.REVIEW_DESCRIPTOR_COMPLETION: (
        8,
        False,
        Checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED,
        State.DESCRIPTOR_PENDING_IDENTITY_REVIEW_REQUIRED,
    ),
    Step.REVIEW_JOURNAL_RETIREMENT: (
        8,
        False,
        Checkpoint.BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED,
        State.JOURNAL_PENDING_IDENTITY_REVIEW_REQUIRED,
    ),
}


def _images(step: Step) -> tuple[bytes, bytes, bytes, bytes | None]:
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


def _stamps(step: Step) -> bridge._Census:
    raw = _images(step)
    one: bridge._Stamp = (1, 100, len(raw[0]), 1000, 2000)
    two: bridge._Stamp = (1, 101, len(raw[1]), 1000, 2000)
    three: bridge._Stamp = (1, 102, len(raw[2]), 1000, 2000)
    stage: bridge._Stamp | None = (
        (1, 103, len(_INTENT.registry_after), 1000, 2000) if _CASES[step][1] else None
    )
    return (one, two, three, stage)


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    signatures: list[object] | None = None,
    images: list[object] | None = None,
    checkpoints: list[object] | None = None,
    inventories: list[object] | None = None,
    namespaces: list[object] | None = None,
    owners: list[object] | None = None,
    raise_at: str = "",
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
        "encode_private_registry",
        lambda data: b"private-registry-" + str(data.revision).encode(),
    )
    monkeypatch.setattr(
        metadata,
        "decode_private_registry",
        lambda raw: SimpleNamespace(revision=7 if raw == b"private-registry-7" else 8),
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
        label: str, sequence: list[object] | None, default: object
    ) -> Callable[..., object]:
        iterator = iter(sequence) if sequence is not None else None

        def wrapped(*_args: object) -> object:
            calls.append(label)
            assert active[0], "identity or image access outside native guard"
            if label == raise_at and thrown is not None:
                raise thrown
            return next(iterator) if iterator is not None else default

        return wrapped

    owner = SimpleNamespace(uid="local-teacher")
    monkeypatch.setattr(ordered, "_owner", native("owner", owners, owner))
    stage = _CASES[step][1]
    ns = (
        frozenset({TX + ".json"}),
        frozenset({"." + TX + ".registry-stage"}) if stage else frozenset(),
        stage,
    )
    monkeypatch.setattr(recovery, "_namespace", native("namespace", namespaces, ns))
    iv = (
        inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
        if stage
        else inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED
    )
    monkeypatch.setattr(readers, "_inventory", native("inventory", inventories, iv))
    monkeypatch.setattr(operation, "_same_native_namespace", native("same", None, True))
    monkeypatch.setattr(bridge, "_census", native("census", signatures, _stamps(step)))
    monkeypatch.setattr(
        recovery,
        "_classify_present",
        native("checkpoint", checkpoints, _CASES[step][2]),
    )
    monkeypatch.setattr(
        recovery, "_classify_absent", native("checkpoint", checkpoints, _CASES[step][2])
    )
    monkeypatch.setattr(exact, "_images", native("images", images, _images(step)))


def _review(
    root: Path,
    step: Step = Step.REVIEW_PREPARED_RESTART,
    expected: int = 7,
    proposed: intents.PrivateTransactionIntent = _INTENT,
) -> bridge.PrivateNativeIdentityBridgeReview:
    return bridge.review_native_private_recovery_identity_bridge(
        step, expected, proposed, root, root
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_all_three_checkpoints_use_one_guard_and_two_censuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step)
    report = _review(tmp_path, step, _CASES[step][0])
    assert report.state is _CASES[step][3]
    assert calls.count("enter") == calls.count("exit") == 1
    assert (
        calls.count("census") == calls.count("checkpoint") == calls.count("images") == 2
    )
    assert calls[0] == "enter" and calls[-1] == "exit"
    assert not hasattr(report, "handle") and not hasattr(report, "permit")
    assert not hasattr(report, "path") and not hasattr(report, "bytes")
    with pytest.raises(FrozenInstanceError):
        setattr(report, "state", State.IO_ERROR)


@pytest.mark.parametrize("step", list(_CASES))
@pytest.mark.parametrize("invalid", [None, True, 0, 1, 2, 7.0, "7", -1])
def test_wrong_revisions_fail_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step, invalid: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, step=step)
    report = _review(tmp_path, step, cast(int, invalid))
    assert report.state in {State.INVALID_REQUEST, State.REVISION_MISMATCH_REFUSED}
    assert calls == []


@pytest.mark.parametrize("step", list(_CASES))
@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_exact_native_byte_image_mismatch_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step, index: int
) -> None:
    values = list(_images(step))
    values[index] = b"wrong"
    _setup(monkeypatch, [], step=step, images=[tuple(values)])
    assert (
        _review(tmp_path, step, _CASES[step][0]).state is State.IMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_native_identity_drift_even_with_same_bytes_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    changed = list(_stamps(step))
    first = changed[0]
    assert first is not None
    changed[0] = (first[0], first[1] + 1, first[2], first[3], first[4])
    _setup(monkeypatch, [], step=step, signatures=[_stamps(step), tuple(changed)])
    assert (
        _review(tmp_path, step, _CASES[step][0]).state is State.IDENTITY_DRIFT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_byte_image_drift_with_stable_identity_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    changed = list(_images(step))
    changed[0] = b"foreign-intent"
    _setup(monkeypatch, [], step=step, images=[_images(step), tuple(changed)])
    assert _review(tmp_path, step, _CASES[step][0]).state is State.IMAGE_DRIFT_PRESERVE


@pytest.mark.parametrize("step", list(_CASES))
def test_identity_size_mismatch_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    values = list(_stamps(step))
    first = values[0]
    assert first is not None
    values[0] = (first[0], first[1], first[2] + 1, first[3], first[4])
    _setup(monkeypatch, [], step=step, signatures=[tuple(values)])
    assert _review(tmp_path, step, _CASES[step][0]).state is State.IDENTITY_UNQUALIFIED


@pytest.mark.parametrize("step", list(_CASES))
def test_conflicting_native_checkpoint_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(monkeypatch, [], step=step, checkpoints=[Checkpoint.IMAGES_UNQUALIFIED])
    assert (
        _review(tmp_path, step, _CASES[step][0]).state
        is State.CHECKPOINT_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("step", list(_CASES))
def test_owner_change_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    _setup(
        monkeypatch,
        [],
        step=step,
        owners=[SimpleNamespace(uid="one"), SimpleNamespace(uid="two")],
    )
    assert _review(tmp_path, step, _CASES[step][0]).state is State.OWNER_CHANGED


def test_namespace_change_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch, [], namespaces=[(frozenset(), frozenset(), False)])
    # Fake namespace does not match expected prepared step; conflict is preserved.
    assert _review(tmp_path).state in {
        State.ACTION_MISMATCH_REFUSED,
        State.NAMESPACE_CHANGED_PRESERVE,
    }


@pytest.mark.parametrize(
    "exc,expected",
    [
        (KeyboardInterrupt(), State.INTERRUPTED_PRESERVE),
        (FileNotFoundError(), State.NAMESPACE_CHANGED_PRESERVE),
        (PermissionError(), State.GUARD_REFUSED),
        (OSError(), State.IO_ERROR),
        (bridge._IdentityUnqualified(), State.IDENTITY_UNQUALIFIED),
    ],
)
def test_census_failures_release_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exc: BaseException, expected: State
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, raise_at="census", thrown=exc)
    assert _review(tmp_path).state is expected
    assert calls.count("exit") == 1


def test_guard_release_failure_blocks_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(
        monkeypatch,
        calls,
        release_error=retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
        ),
    )
    assert _review(tmp_path).state is State.GUARD_REFUSED
    assert calls[-1] == "exit"


def test_initialization_refused_without_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    replacement = _intent()
    object.__setattr__(
        replacement.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: replacement
    )
    assert _review(tmp_path, proposed=replacement).state is State.INITIALIZATION_REFUSED
    assert calls == []


def test_unsupported_platform_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _review(tmp_path).state is State.UNSUPPORTED


@pytest.mark.parametrize("candidate", list(State))
def test_sanitized_fixed_state_messages(candidate: State) -> None:
    result = bridge._result(candidate)
    assert result.state is candidate and result.message
    assert not hasattr(result, "handle") and not hasattr(result, "owner")
    assert "private-registry" not in repr(result)


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native file IDs")
def test_real_fixture_path_handle_identity_and_replacement(tmp_path: Path) -> None:
    original = tmp_path / "registry.json"
    staged = tmp_path / "replacement"
    original.write_bytes(b"fixed-synthetic-bytes")
    staged.write_bytes(b"fixed-synthetic-bytes")
    first = bridge._stamp(original, 128)
    staged_id = bridge._stamp(staged, 128)
    assert first[:2] != staged_id[:2]
    os.replace(staged, original)
    assert bridge._stamp(original, 128)[:2] == staged_id[:2]


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native file IDs")
def test_fixture_census_includes_exact_existing_journal_and_stage(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    workspace = tmp_path / "workspace"
    (private / "transactions").mkdir(parents=True)
    (workspace / ".pds").mkdir(parents=True)
    (private / "registry.json").write_bytes(b"reg")
    (private / "transactions" / (TX + ".json")).write_bytes(b"journal")
    (workspace / ".pds" / "teacher-private-association.json").write_bytes(b"desc")
    (private / ("." + TX + ".registry-stage")).write_bytes(b"stage")
    signatures = bridge._census(private, workspace, TX, True, 200)
    assert signatures[0][2] == 7 and signatures[1][2] == 3
    assert signatures[2][2] == 4 and signatures[3] is not None
    (private / ("." + TX + ".registry-stage")).unlink()
    assert bridge._census(private, workspace, TX, False, 200)[3] is None


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native file IDs")
def test_fixture_empty_or_oversize_refuses(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"")
    with pytest.raises(bridge._IdentityUnqualified):
        bridge._stamp(candidate, 20)
    candidate.write_bytes(b"more-than-four")
    with pytest.raises(bridge._IdentityUnqualified):
        bridge._stamp(candidate, 4)


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native file IDs")
def test_fixture_hard_link_or_symlink_refused(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"synthetic")
    linked = tmp_path / "linked"
    try:
        os.link(candidate, linked)
    except OSError:
        pytest.skip("hard links unavailable on scratch volume")
    with pytest.raises(bridge._IdentityUnqualified):
        bridge._stamp(candidate, 32)
    linked.unlink()
    shortcut = tmp_path / "shortcut"
    try:
        shortcut.symlink_to(candidate)
    except OSError:
        pytest.skip("symlinks unavailable on scratch volume")
    with pytest.raises(bridge._IdentityUnqualified):
        bridge._stamp(shortcut, 32)


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native file IDs")
@pytest.mark.parametrize("changed_field", ["st_ctime_ns", "st_mtime_ns"])
def test_handle_timestamp_disagreement_keeps_exact_file_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, changed_field: str
) -> None:
    """Path and handle can report different timestamps for one Windows file."""
    candidate = tmp_path / "same-file"
    candidate.write_bytes(b"synthetic")
    original = os.fstat

    def shifted(fd: int) -> SimpleNamespace:
        result = original(fd)
        values = {
            name: getattr(result, name)
            for name in (
                "st_mode",
                "st_nlink",
                "st_dev",
                "st_ino",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        }
        values[changed_field] += 1_000_000_000
        return SimpleNamespace(**values)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", shifted)
        observation = bridge._stamp(candidate, 64)
    actual = candidate.lstat()
    assert observation[:3] == (actual.st_dev, actual.st_ino, len(b"synthetic"))


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native file IDs")
def test_open_handle_identity_mismatch_still_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The timestamp compatibility fix must never excuse wrong file IDs."""
    candidate = tmp_path / "same-file"
    candidate.write_bytes(b"synthetic")
    original = os.fstat

    def swapped_identity(fd: int) -> SimpleNamespace:
        result = original(fd)
        return SimpleNamespace(
            st_mode=result.st_mode,
            st_nlink=result.st_nlink,
            st_dev=result.st_dev,
            st_ino=result.st_ino + 1,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns,
            st_ctime_ns=result.st_ctime_ns,
        )

    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", swapped_identity)
        with pytest.raises(bridge._IdentityUnqualified):
            bridge._stamp(candidate, 64)
