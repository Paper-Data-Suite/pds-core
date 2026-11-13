"""Core #238 3G36: read-only native owner/protection preflight under guard."""

from __future__ import annotations

import inspect
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Literal, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_native_preflight as native
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_parent_continuity as parents
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_protected_writer_scope as scope
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = preflight.PrivateProductionNativePreflightState
Step = scratch.PrivateScratchWriterStep
TX = "11111111-1111-4111-8111-111111111111"
ASSOC = "22222222-2222-4222-8222-222222222222"
BEFORE = b"synthetic-before"
AFTER = b"synthetic-after"
SIDECAR = b"synthetic-descriptor"
RAW = b"synthetic-canonical-pending-intent"
PARENTS: parents._Parents = (
    (1, 11, 0o40700, 10, 20),
    (1, 12, 0o40700, 10, 20),
    (1, 13, 0o40700, 10, 20),
    (1, 14, 0o40700, 10, 20),
)


def _intent() -> intents.PrivateTransactionIntent:
    value = object.__new__(intents.PrivateTransactionIntent)
    inner = object.__new__(witness.PrivateTransactionWitness)
    for field_name, field_value in {
        "operation": witness.PrivateBindingOperation.REBIND_MOVE,
        "transaction_id": TX,
        "association_before": ASSOC,
        "association_after": ASSOC,
        "registry_revision_before": 7,
        "registry_revision_after": 8,
        "descriptor_sha256_before": "1" * 64,
        "descriptor_sha256_after": "1" * 64,
        "registry_sha256_before": "2" * 64,
        "registry_sha256_after": "3" * 64,
    }.items():
        object.__setattr__(inner, field_name, field_value)
    for field_name, field_value in {
        "witness": inner,
        "registry_before": BEFORE,
        "registry_after": AFTER,
        "descriptor_before": SIDECAR,
        "descriptor_after": SIDECAR,
    }.items():
        object.__setattr__(value, field_name, field_value)
    return value


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    workspace: Path,
    *,
    native_state: native.NativePrivatePreflightState = (
        native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ),
    release_error: Exception | None = None,
) -> tuple[intents.PrivateTransactionIntent, list[str]]:
    calls: list[str] = []
    proposed = _intent()
    kind: Literal["windows_token_sid", "posix_euid"] = (
        "windows_token_sid" if sys.platform == "win32" else "posix_euid"
    )
    owner = inspection.EffectiveOSOwner(
        kind,
        "S-1-5-21-111-222-333-1001" if sys.platform == "win32" else "1000",
    )
    root_before = str(workspace.parent / "previous")
    before = SimpleNamespace(
        owner=SimpleNamespace(kind=owner.kind, value=owner.value),
        bindings=[SimpleNamespace(association_id=ASSOC, accepted_root=root_before)],
    )
    after = SimpleNamespace(
        owner=before.owner,
        bindings=[SimpleNamespace(association_id=ASSOC, accepted_root=str(workspace))],
    )
    active = [False]

    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        ),
    )
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda *_: RAW)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: proposed
    )
    monkeypatch.setattr(
        inspection,
        "inspect_private_root",
        lambda: inspection.PrivateRootInspection(
            inspection.PrivateRootState.PRESENT_UNVERIFIED, owner, root, "synthetic"
        ),
    )
    monkeypatch.setattr(
        native,
        "inspect_native_private_preflight",
        lambda: native.NativePrivatePreflight(native_state, "synthetic"),
    )
    monkeypatch.setattr(
        metadata,
        "decode_private_registry",
        lambda raw: before if raw == BEFORE else after,
    )
    monkeypatch.setattr(
        metadata,
        "encode_private_registry",
        lambda record: BEFORE if record is before else AFTER,
    )

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

    def observe(*_args: object) -> scope._Frame:
        calls.append("frame")
        assert active[0]
        return scope._Frame(
            PARENTS,
            (
                (1, 20, len(RAW), 10, 20),
                (1, 21, len(BEFORE), 10, 20),
                (1, 22, len(SIDECAR), 10, 20),
                (1, 23, len(AFTER), 10, 20),
            ),
            (RAW, BEFORE, SIDECAR, AFTER),
            recovery.PrivatePostcrashReconciliationState.STAGED_BEFORE_REVIEW_REQUIRED,
        )

    monkeypatch.setattr(scope, "_observe", observe)
    monkeypatch.setattr(
        recovery, "_namespace", lambda *_: (frozenset(), frozenset(), True)
    )
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: True)
    monkeypatch.setattr(parents, "_parents", lambda *_: PARENTS)
    monkeypatch.setattr(ordered, "_owner", lambda: owner)
    return proposed, calls


def _review(
    intent: intents.PrivateTransactionIntent,
    private: Path,
    workspace: Path,
    *,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
) -> preflight.PrivateProductionNativePreflightReview:
    return preflight.review_protected_production_native_prerequisites(
        step, revision, intent, private, workspace
    )


def test_three_frames_inside_one_guard_never_authorize(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    outcome = _review(proposal, private, workspace)
    assert outcome.state is State.PROTECTION_OBSERVED_NO_WRITE
    assert calls == ["enter", "frame", "frame", "frame", "exit"]
    assert outcome.unqualified_requirements == tuple(
        barrier.PrivateProductionWriteRequirement
    )
    assert "non_authorizing=True" in repr(outcome)
    assert not any(
        hasattr(outcome, name)
        for name in ("path", "owner", "token", "handle", "callback", "execute", "write")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(outcome, "state", State.INVALID_REQUEST)


@pytest.mark.parametrize("bad", [None, False, 0, "7", 7.0, -1, {}, object()])
def test_invalid_revision_fails_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    assert (
        _review(proposal, private, workspace, revision=cast(int, bad)).state
        is State.INVALID_REQUEST
    )
    assert not calls


@pytest.mark.parametrize("bad", [None, False, 1, "stage_to_registry", {}, object()])
def test_invalid_step_fails_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    assert (
        _review(proposal, private, workspace, step=cast(Step, bad)).state
        is State.INVALID_REQUEST
    )
    assert not calls


@pytest.mark.parametrize(
    "step", [part for part in Step if part is not Step.STAGE_TO_REGISTRY]
)
def test_other_operations_not_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: Step
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    assert (
        _review(proposal, private, workspace, step=step).state
        is State.OPERATION_NOT_ADMITTED
    )
    assert not calls


@pytest.mark.parametrize("argument", [None, False, "path", {}, object()])
def test_invalid_private_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argument: object
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    assert (
        _review(proposal, cast(Path, argument), workspace).state
        is State.INVALID_REQUEST
    )
    assert not calls


@pytest.mark.parametrize("argument", [None, False, "path", {}, object()])
def test_invalid_workspace_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argument: object
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    assert (
        _review(proposal, private, cast(Path, argument)).state is State.INVALID_REQUEST
    )
    assert not calls


def test_wrong_private_root_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    assert (
        _review(proposal, tmp_path / "foreign", workspace).state
        is State.ROOT_UNQUALIFIED
    )
    assert not calls


@pytest.mark.parametrize(
    "native_state",
    [
        item
        for item in native.NativePrivatePreflightState
        if item is not native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    ],
)
def test_native_protection_denials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    native_state: native.NativePrivatePreflightState,
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace, native_state=native_state)
    assert (
        _review(proposal, private, workspace).state is State.NATIVE_PROTECTION_REFUSED
    )
    assert not calls


def test_owner_change_during_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    original: Callable[[], inspection.PrivateRootInspection] = (
        inspection.inspect_private_root
    )
    count = [0]

    def change() -> inspection.PrivateRootInspection:
        count[0] += 1
        result = original()
        if count[0] > 2:
            return inspection.PrivateRootInspection(
                result.state,
                inspection.EffectiveOSOwner(result.owner.kind, "2000")
                if result.owner is not None
                else None,
                result.candidate,
                result.message,
            )
        return result

    monkeypatch.setattr(inspection, "inspect_private_root", change)
    assert _review(proposal, private, workspace).state is State.OWNER_CHANGED
    assert calls.count("enter") == calls.count("exit") == 1


def test_invalid_owner_binding_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    monkeypatch.setattr(
        ordered, "_owner", lambda: inspection.EffectiveOSOwner("posix_euid", "1001")
    )
    assert _review(proposal, private, workspace).state is State.OWNER_CHANGED
    assert calls.count("exit") == 1


def test_guard_release_refusal_never_positive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    refusal = retained.RetainedDescriptorGuardError(
        retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
    )
    proposal, calls = _setup(monkeypatch, private, workspace, release_error=refusal)
    assert _review(proposal, private, workspace).state is State.GUARD_REFUSED
    assert calls.count("exit") == 1


def test_native_namespace_change_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    monkeypatch.setattr(operation, "_same_native_namespace", lambda *_: False)
    assert (
        _review(proposal, private, workspace).state is State.NAMESPACE_CONFLICT_PRESERVE
    )
    assert calls.count("exit") == 1


def test_protected_image_conflict_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    monkeypatch.setattr(
        scope,
        "_frame_state",
        lambda *_: scope.PrivateProtectedWriterScopeState.IMAGE_CONFLICT_PRESERVE,
    )
    assert (
        _review(proposal, private, workspace).state is State.EVIDENCE_CONFLICT_PRESERVE
    )
    assert calls.count("exit") == 1


def test_interrupt_preserves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)

    def stop(*_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(scope, "_observe", stop)
    assert _review(proposal, private, workspace).state is State.INTERRUPTED_PRESERVE
    assert calls.count("exit") == 1


def test_no_mutation_or_authorization_symbols() -> None:
    source = inspect.getsource(preflight)
    for forbidden in (
        "os.replace(",
        ".write_bytes(",
        ".write_text(",
        'open("wb"',
        "unlink(",
        "fsync(",
    ):
        assert forbidden not in source
    assert not any(
        hasattr(preflight, name)
        for name in (
            "admit_production_write",
            "commit_private_recovery",
            "retire_journal",
            "write_registry",
        )
    )


@pytest.mark.parametrize("state", list(State))
def test_sanitized_state_messages_and_fixed_unqualified_requirements(
    state: State,
) -> None:
    outcome = preflight._result(state)
    assert "/tmp/" not in outcome.message and "C:" not in outcome.message
    assert "synthetic" not in outcome.message
    assert outcome.unqualified_requirements == tuple(
        barrier.PrivateProductionWriteRequirement
    )


def test_metadata_owner_mismatch_rejected_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    bad = SimpleNamespace(
        owner=SimpleNamespace(kind="posix_euid", value="9999"),
        bindings=[SimpleNamespace(association_id=ASSOC, accepted_root=str(workspace))],
    )
    monkeypatch.setattr(metadata, "decode_private_registry", lambda *_: bad)
    monkeypatch.setattr(metadata, "encode_private_registry", lambda *_: BEFORE)
    assert _review(proposal, private, workspace).state is State.OWNER_MISMATCH
    assert not calls


def test_binding_root_mismatch_rejected_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    original = metadata.decode_private_registry

    def decoded(raw: bytes) -> object:
        item = cast(Any, original(raw))
        if raw == AFTER:
            item.bindings[0].accepted_root = str(tmp_path / "other-workspace")
        return item

    monkeypatch.setattr(metadata, "decode_private_registry", decoded)
    assert _review(proposal, private, workspace).state is State.BINDING_MISMATCH
    assert not calls


def test_protection_revoked_during_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    checks = [0]

    def protection() -> native.NativePrivatePreflight:
        checks[0] += 1
        return native.NativePrivatePreflight(
            native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
            if checks[0] == 1
            else native.NativePrivatePreflightState.REFUSED_ACL,
            "synthetic",
        )

    monkeypatch.setattr(native, "inspect_native_private_preflight", protection)
    assert (
        _review(proposal, private, workspace).state is State.NATIVE_PROTECTION_REFUSED
    )
    assert calls.count("enter") == calls.count("exit") == 1
    assert calls.count("frame") == 0


def test_canonical_intent_changes_inside_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    n = [0]

    altered = _intent()
    object.__setattr__(altered, "registry_after", b"different-synthetic-after")

    def decoder(_raw: bytes) -> intents.PrivateTransactionIntent:
        n[0] += 1
        return proposal if n[0] == 1 else altered

    monkeypatch.setattr(intents, "decode_private_transaction_intent", decoder)
    assert _review(proposal, private, workspace).state is State.INTENT_UNQUALIFIED
    assert calls.count("enter") == calls.count("exit") == 1
    assert calls.count("frame") == 0


def test_reject_nonbytes_serialization_before_decoding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: "not-bytes"
    )

    def forbidden(_raw: bytes) -> intents.PrivateTransactionIntent:
        raise AssertionError("malformed serialization reached decoder")

    monkeypatch.setattr(intents, "decode_private_transaction_intent", forbidden)
    assert _review(proposal, private, workspace).state is State.INTENT_UNQUALIFIED
    assert not calls


def test_wrong_native_preflight_shape_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    monkeypatch.setattr(native, "inspect_native_private_preflight", lambda: object())
    assert (
        _review(proposal, private, workspace).state is State.NATIVE_PROTECTION_REFUSED
    )
    assert not calls


def test_revision_refusal_is_propagated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private, workspace = tmp_path / "private", tmp_path / "workspace"
    proposal, calls = _setup(monkeypatch, private, workspace)
    monkeypatch.setattr(
        barrier,
        "review_private_production_write_barrier",
        lambda *_: barrier._result(
            barrier.PrivateProductionWriteBarrierState.REVISION_MISMATCH_REFUSED
        ),
    )
    assert (
        _review(proposal, private, workspace).state is State.REVISION_MISMATCH_REFUSED
    )
    assert not calls
