"""#238 Slice 3C7: lock-scoped, non-authorizing transaction-currentness review."""

from __future__ import annotations

import hashlib
import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_currentness_review as currentness
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_snapshot as registry_snapshot
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witnesses

ASSOC = "0b283e11-b17b-42ac-8c96-79037b1ea4d9"
NEW = "ea867513-59c5-4cf2-b7d1-a5c9b203c734"
TX = "c0bbda1f-41fc-45c8-ab52-94601b2abe9d"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def registry_bytes(
    principal: inspection.EffectiveOSOwner,
    revision: int,
    bindings: tuple[metadata.PrivateRegistryBinding, ...],
) -> bytes:
    if principal.kind == "windows_token_sid":
        who = metadata.PrivateRegistryOwner("windows_token_sid", principal.value)
    else:
        who = metadata.PrivateRegistryOwner("posix_euid", principal.value)
    return metadata.encode_private_registry(
        metadata.PrivateRegistry(who, revision, bindings)
    )


def sample(
    tmp_path: Path, principal: inspection.EffectiveOSOwner | None = None
) -> tuple[
    intents.PrivateTransactionIntent,
    paired.PrivatePairObservation,
    Path,
    Path,
    bytes,
    bytes,
]:
    who = principal or owner()
    source = tmp_path / "source"
    workspace = tmp_path / "destination"
    private_root = tmp_path / "private"
    before_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(ASSOC)
    )
    after_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(NEW)
    )
    before_registry = registry_bytes(
        who, 5, (metadata.PrivateRegistryBinding(ASSOC, 3, str(source)),)
    )
    after_registry = registry_bytes(
        who,
        6,
        (
            metadata.PrivateRegistryBinding(ASSOC, 3, str(source)),
            metadata.PrivateRegistryBinding(NEW, 1, str(workspace)),
        ),
    )
    witness = witnesses.PrivateTransactionWitness(
        witnesses.PrivateBindingOperation.FORK_COPY,
        TX,
        ASSOC,
        NEW,
        5,
        6,
        digest(before_descriptor),
        digest(after_descriptor),
        digest(before_registry),
        digest(after_registry),
    )
    proposal = intents.PrivateTransactionIntent(
        witness, before_descriptor, after_descriptor, before_registry, after_registry
    )
    prior = paired.PrivatePairObservation(
        paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED,
        "previous observation, not authority",
        5,
        1,
        ASSOC,
        digest(before_registry),
        digest(before_descriptor),
    )
    return proposal, prior, private_root, workspace, before_registry, before_descriptor


def synthetic_locked_reads(
    monkeypatch: pytest.MonkeyPatch,
    prior: paired.PrivatePairObservation,
    log: list[str],
    *,
    native_owner: inspection.EffectiveOSOwner | None = None,
    owner_second: inspection.EffectiveOSOwner | None = None,
    registry_second: registry_snapshot.PrivateRegistrySnapshot | None = None,
    descriptor_second: descriptor.PrivateDescriptorSnapshot | None = None,
) -> None:
    """Synthetic lock records exact read order, no actual filesystem authority."""
    who = native_owner or owner()
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def held(_path: Path) -> Iterator[None]:
        log.append("lock")
        try:
            yield
        finally:
            log.append("unlock")

    monkeypatch.setattr(locking, "hold_existing_private_lock", held)
    readings = 0

    def effective(_platform: str) -> inspection.EffectiveOSOwner:
        nonlocal readings
        readings += 1
        log.append("owner")
        return owner_second if readings == 2 and owner_second is not None else who

    def reg(_root: Path) -> registry_snapshot.PrivateRegistrySnapshot:
        log.append("registry")
        if log.count("registry") == 2 and registry_second is not None:
            return registry_second
        return registry_snapshot.PrivateRegistrySnapshot(
            registry_snapshot.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
            "native synthetic observation",
            prior.registry_revision,
            prior.registry_binding_count,
            prior.registry_sha256,
        )

    def desc(_root: Path) -> descriptor.PrivateDescriptorSnapshot:
        log.append("descriptor")
        if log.count("descriptor") == 2 and descriptor_second is not None:
            return descriptor_second
        return descriptor.PrivateDescriptorSnapshot(
            descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic workspace observation",
            prior.association_id,
            prior.descriptor_sha256,
        )

    monkeypatch.setattr(inspection, "_effective_owner", effective)
    monkeypatch.setattr(paired, "_registry_read", reg)
    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", desc)


def test_ordered_lock_scoped_review_does_not_grant_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)
    result = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, workspace
    )
    assert (
        result.state
        is currentness.PrivateCurrentnessReviewState.RECHECKED_REVIEW_REQUIRED
    )
    assert log == [
        "lock",
        "owner",
        "registry",
        "descriptor",
        "descriptor",
        "registry",
        "owner",
        "unlock",
    ]
    assert result.precondition_state is None
    assert "ready" not in result.state.value
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "write_handle")
    assert not hasattr(result, "commit_token")
    assert ASSOC not in repr(result)
    assert str(workspace) not in repr(result)
    assert owner().value not in repr(result)
    assert list(tmp_path.iterdir()) == []


def test_stale_prior_digest_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)
    changed = replace(prior, registry_sha256="f" * 64)
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed, changed, private_root, workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.OBSERVATION_STALE
    )


def test_changed_registry_inside_read_pair_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    changed = registry_snapshot.PrivateRegistrySnapshot(
        registry_snapshot.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
        "synthetic revision change",
        6,
        1,
        "f" * 64,
    )
    synthetic_locked_reads(monkeypatch, prior, log, registry_second=changed)
    outcome = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, workspace
    )
    assert (
        outcome.state
        is currentness.PrivateCurrentnessReviewState.CURRENT_OBSERVATION_UNQUALIFIED
    )


def test_changed_descriptor_inside_read_pair_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    changed = descriptor.PrivateDescriptorSnapshot(
        descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
        "synthetic descriptor change",
        NEW,
        "0" * 64,
    )
    synthetic_locked_reads(monkeypatch, prior, log, descriptor_second=changed)
    outcome = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, workspace
    )
    assert (
        outcome.state
        is currentness.PrivateCurrentnessReviewState.CURRENT_OBSERVATION_UNQUALIFIED
    )


def test_missing_descriptor_refused_without_creating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    missing = descriptor.PrivateDescriptorSnapshot(
        descriptor.PrivateDescriptorSnapshotState.MISSING_DESCRIPTOR,
        "synthetic missing descriptor",
    )
    synthetic_locked_reads(monkeypatch, prior, log, descriptor_second=missing)
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed, prior, private_root, workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.CURRENT_OBSERVATION_UNQUALIFIED
    )
    assert list(tmp_path.iterdir()) == []


def test_native_owner_change_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    other = inspection.EffectiveOSOwner(owner().kind, "changed-native-owner")
    synthetic_locked_reads(monkeypatch, prior, log, owner_second=other)
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed, prior, private_root, workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.OWNER_CHANGED
    )


def test_native_owner_mismatch_with_proposal_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    other = inspection.EffectiveOSOwner(owner().kind, "different-native-principal")
    synthetic_locked_reads(monkeypatch, prior, log, native_owner=other)
    outcome = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, workspace
    )
    assert (
        outcome.state is currentness.PrivateCurrentnessReviewState.PRECONDITION_REFUSED
    )
    assert (
        outcome.precondition_state
        is preconditions.PrivateBindingPreconditionState.OWNER_MISMATCH
    )
    assert other.value not in repr(outcome)


def test_changed_destination_refused_under_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, _workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)
    outcome = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, tmp_path / "unexpected_destination"
    )
    assert (
        outcome.state is currentness.PrivateCurrentnessReviewState.PRECONDITION_REFUSED
    )
    assert (
        outcome.precondition_state
        is preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH
    )


def test_previously_missing_state_never_qualifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    prior = replace(prior, state=paired.PrivatePairObservationState.MISSING_DESCRIPTOR)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed, prior, private_root, workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.PRIOR_OBSERVATION_UNQUALIFIED
    )
    assert log == []


def test_initialization_is_never_rechecked_as_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    after_registry = registry_bytes(
        owner(), 1, (metadata.PrivateRegistryBinding(NEW, 1, str(workspace)),)
    )
    new_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(NEW)
    )
    witness = witnesses.PrivateTransactionWitness(
        witnesses.PrivateBindingOperation.INITIALIZE,
        TX,
        None,
        NEW,
        0,
        1,
        None,
        digest(new_descriptor),
        None,
        digest(after_registry),
    )
    proposal = intents.PrivateTransactionIntent(
        witness, None, new_descriptor, None, after_registry
    )
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)
    assert (
        currentness.review_current_private_binding_preconditions(
            proposal, prior, private_root, workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.INITIALIZATION_ABSENCE_REVIEW
    )
    assert log == []


def test_busy_lock_refused_without_observing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)

    @contextmanager
    def busy(_path: Path) -> Iterator[None]:
        raise locking.PrivateExistingFileLockError(
            locking.PrivateExistingFileLockCode.BUSY
        )
        yield

    monkeypatch.setattr(locking, "hold_existing_private_lock", busy)
    outcome = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, workspace
    )
    assert (
        outcome.state
        is currentness.PrivateCurrentnessReviewState.COORDINATION_UNAVAILABLE
    )
    assert log == []


def test_unavailable_owner_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)

    def missing(_platform: str) -> inspection.EffectiveOSOwner:
        raise inspection._OwnerUnverifiable

    monkeypatch.setattr(inspection, "_effective_owner", missing)
    outcome = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, workspace
    )
    assert outcome.state is currentness.PrivateCurrentnessReviewState.OWNER_UNAVAILABLE
    assert log == ["lock", "unlock"]


def test_read_error_does_not_expose_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)

    def broken(_root: Path) -> registry_snapshot.PrivateRegistrySnapshot:
        raise OSError("private synthetic path shouldn't escape")

    monkeypatch.setattr(paired, "_registry_read", broken)
    outcome = currentness.review_current_private_binding_preconditions(
        proposed, prior, private_root, workspace
    )
    assert outcome.state is currentness.PrivateCurrentnessReviewState.IO_ERROR
    assert "private synthetic path" not in repr(outcome)
    assert log[-1] == "unlock"


@pytest.mark.parametrize(
    "state",
    [
        x
        for x in paired.PrivatePairObservationState
        if x is not paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
    ],
)
def test_unqualified_prior_never_acquires_lock(
    state: paired.PrivatePairObservationState,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    log: list[str] = []
    synthetic_locked_reads(monkeypatch, prior, log)
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed, replace(prior, state=state), private_root, workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.PRIOR_OBSERVATION_UNQUALIFIED
    )
    assert log == []


def test_invalid_platform_fails_without_touching_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed, prior, private_root, workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.UNSUPPORTED
    )
    assert list(tmp_path.iterdir()) == []


def test_invalid_paths_and_types_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed, prior, private_root, workspace, _, _ = sample(tmp_path)
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed, prior, Path("relative"), workspace
        ).state
        is currentness.PrivateCurrentnessReviewState.INVALID_REQUEST
    )
    assert (
        currentness.review_current_private_binding_preconditions(
            "wrong",  # type: ignore[arg-type]
            prior,
            private_root,
            workspace,
        ).state
        is currentness.PrivateCurrentnessReviewState.INVALID_REQUEST
    )
    assert (
        currentness.review_current_private_binding_preconditions(
            proposed,
            "wrong",  # type: ignore[arg-type]
            private_root,
            workspace,
        ).state
        is currentness.PrivateCurrentnessReviewState.INVALID_REQUEST
    )
    assert list(tmp_path.iterdir()) == []


def test_no_notes_activation_or_mutating_exports() -> None:
    assert not hasattr(currentness, "write_private_registry")
    assert not hasattr(currentness, "commit_private_transaction")
    assert not hasattr(currentness, "authorize_private_storage")


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux nonroot only")
def test_linux_existing_file_round_trip_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    getter = getattr(os, "geteuid", None)
    if getter is None or getter() == 0:
        pytest.skip("Requires nonroot Linux account")
    uid = str(getter())
    principal = inspection.EffectiveOSOwner("posix_euid", uid)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    private_root = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    private_root.mkdir(parents=True, mode=0o700)
    private_root.chmod(0o700)
    workspace = tmp_path / "destination"
    pds = workspace / ".pds"
    pds.mkdir(parents=True)
    original = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(ASSOC)
    )
    file = pds / "teacher-private-association.json"
    file.write_bytes(original)
    reg = registry_bytes(
        principal,
        5,
        (metadata.PrivateRegistryBinding(ASSOC, 3, str(tmp_path / "source")),),
    )
    registry = private_root / "registry.json"
    registry.write_bytes(reg)
    registry.chmod(0o600)
    lock = private_root / ".registry.lock"
    lock.write_bytes(b"\x00")
    lock.chmod(0o600)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    prior = paired.observe_private_registry_and_workspace_descriptor(
        private_root, workspace
    )
    assert prior.state is paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED
    _sample, _, _, _, _, _ = sample(tmp_path, principal)
    after = registry_bytes(
        principal,
        6,
        (
            metadata.PrivateRegistryBinding(ASSOC, 3, str(tmp_path / "source")),
            metadata.PrivateRegistryBinding(NEW, 1, str(workspace)),
        ),
    )
    new_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(NEW)
    )
    witness = witnesses.PrivateTransactionWitness(
        witnesses.PrivateBindingOperation.FORK_COPY,
        TX,
        ASSOC,
        NEW,
        5,
        6,
        digest(original),
        digest(new_descriptor),
        digest(reg),
        digest(after),
    )
    proposal = intents.PrivateTransactionIntent(
        witness, original, new_descriptor, reg, after
    )
    before = (lock.read_bytes(), registry.read_bytes(), file.read_bytes())
    outcome = currentness.review_current_private_binding_preconditions(
        proposal, prior, private_root, workspace
    )
    assert (
        outcome.state
        is currentness.PrivateCurrentnessReviewState.RECHECKED_REVIEW_REQUIRED
    )
    assert (lock.read_bytes(), registry.read_bytes(), file.read_bytes()) == before
