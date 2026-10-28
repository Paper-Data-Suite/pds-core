"""#238 Slice 3D0: two-lock local currentness review, never a write gate."""

from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_binding_preconditions as preconditions
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_ordered_review as review
from pds_core import _teacher_private_pair_observation as paired
from pds_core import _teacher_private_registry_snapshot as registry
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

_ASSOC = "0b283e11-b17b-42ac-8c96-79037b1ea4d9"
_NEW = "ea867513-59c5-4cf2-b7d1-a5c9b203c734"
_TX = "c0bbda1f-41fc-45c8-ab52-94601b2abe9d"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _sample(
    root: Path,
) -> tuple[intents.PrivateTransactionIntent, paired.PrivatePairObservation, Path, Path]:
    principal = _owner()
    origin = root / "source"
    target = root / "destination"
    private = root / "private"
    who = metadata.PrivateRegistryOwner(principal.kind, principal.value)
    desc_before = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_ASSOC)
    )
    desc_after = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_NEW)
    )
    reg_before = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            who, 5, (metadata.PrivateRegistryBinding(_ASSOC, 3, str(origin)),)
        )
    )
    reg_after = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            who,
            6,
            (
                metadata.PrivateRegistryBinding(_ASSOC, 3, str(origin)),
                metadata.PrivateRegistryBinding(_NEW, 1, str(target)),
            ),
        )
    )
    proposed = intents.PrivateTransactionIntent(
        witness.PrivateTransactionWitness(
            witness.PrivateBindingOperation.FORK_COPY,
            _TX,
            _ASSOC,
            _NEW,
            5,
            6,
            _sha(desc_before),
            _sha(desc_after),
            _sha(reg_before),
            _sha(reg_after),
        ),
        desc_before,
        desc_after,
        reg_before,
        reg_after,
    )
    prior = paired.PrivatePairObservation(
        paired.PrivatePairObservationState.OBSERVED_UNQUALIFIED,
        "previous review, not authorization",
        5,
        1,
        _ASSOC,
        _sha(reg_before),
        _sha(desc_before),
    )
    return proposed, prior, private, target


def _fakes(
    monkeypatch: pytest.MonkeyPatch,
    prior: paired.PrivatePairObservation,
    events: list[str],
    *,
    registry_second: registry.PrivateRegistrySnapshot | None = None,
    descriptor_second: descriptor.PrivateDescriptorSnapshot | None = None,
    reviewer_owner_second: inspection.EffectiveOSOwner | None = None,
    lock_failure: bool = False,
) -> None:
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def holding(private: Path, workspace: Path) -> Iterator[None]:
        events.append("registry_lock")
        if lock_failure:
            raise ordered.PrivateOrderedCoordinationError(
                ordered.PrivateOrderedCoordinationCode.COORDINATION_UNAVAILABLE
            )
        events.append("workspace_lock")
        try:
            yield
        finally:
            events.append("workspace_unlock")
            events.append("registry_unlock")

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", holding)
    owner_calls = 0

    def current_owner() -> inspection.EffectiveOSOwner:
        nonlocal owner_calls
        owner_calls += 1
        events.append("owner")
        if owner_calls == 2 and reviewer_owner_second is not None:
            return reviewer_owner_second
        return _owner()

    monkeypatch.setattr(ordered, "_owner", current_owner)
    registry_calls = 0
    descriptor_calls = 0

    def read_reg(_root: Path) -> registry.PrivateRegistrySnapshot:
        nonlocal registry_calls
        registry_calls += 1
        events.append("registry")
        if registry_calls == 2 and registry_second is not None:
            return registry_second
        return registry.PrivateRegistrySnapshot(
            registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic registry",
            prior.registry_revision,
            prior.registry_binding_count,
            prior.registry_sha256,
        )

    def read_desc(_root: Path) -> descriptor.PrivateDescriptorSnapshot:
        nonlocal descriptor_calls
        descriptor_calls += 1
        events.append("descriptor")
        if descriptor_calls == 2 and descriptor_second is not None:
            return descriptor_second
        return descriptor.PrivateDescriptorSnapshot(
            descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic sidecar",
            prior.association_id,
            prior.descriptor_sha256,
        )

    monkeypatch.setattr(paired, "_registry_read", read_reg)
    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", read_desc)


def test_valid_recheck_in_both_locks_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fakes(monkeypatch, prior, events)
    result = review.review_ordered_private_binding_preconditions(
        proposal, prior, private, workspace
    )
    assert result.state is review.PrivateOrderedReviewState.RECHECKED_REVIEW_REQUIRED
    assert events == [
        "registry_lock",
        "workspace_lock",
        "owner",
        "registry",
        "descriptor",
        "descriptor",
        "registry",
        "owner",
        "workspace_unlock",
        "registry_unlock",
    ]
    assert result.precondition_state is None
    assert not hasattr(result, "commit_token")
    assert not hasattr(result, "authorized")
    assert _ASSOC not in repr(result)
    assert str(workspace) not in repr(result)
    assert _owner().value not in repr(result)
    assert list(tmp_path.iterdir()) == []


def test_stale_prior_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fakes(monkeypatch, prior, events)
    stale = replace(prior, registry_sha256="f" * 64)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, stale, private, workspace
        ).state
        is review.PrivateOrderedReviewState.OBSERVATION_STALE
    )
    assert events[-2:] == ["workspace_unlock", "registry_unlock"]


def test_changed_registry_during_two_read_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    replacement = registry.PrivateRegistrySnapshot(
        registry.PrivateRegistrySnapshotState.OBSERVED_UNQUALIFIED,
        "changed",
        7,
        1,
        "f" * 64,
    )
    _fakes(monkeypatch, prior, events, registry_second=replacement)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateOrderedReviewState.CURRENT_OBSERVATION_UNQUALIFIED
    )


def test_changed_descriptor_during_two_read_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    replacement = descriptor.PrivateDescriptorSnapshot(
        descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
        "changed",
        _NEW,
        "f" * 64,
    )
    _fakes(monkeypatch, prior, events, descriptor_second=replacement)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateOrderedReviewState.CURRENT_OBSERVATION_UNQUALIFIED
    )


def test_owner_drift_inside_guard_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    old = _owner()
    changed = inspection.EffectiveOSOwner(
        old.kind, "2000" if old.kind == "posix_euid" else "S-1-5-21-44-33-22-11"
    )
    _fakes(monkeypatch, prior, events, reviewer_owner_second=changed)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateOrderedReviewState.OWNER_CHANGED
    )
    assert events[-2:] == ["workspace_unlock", "registry_unlock"]


def test_second_lock_contention_prevents_metadata_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fakes(monkeypatch, prior, events, lock_failure=True)
    result = review.review_ordered_private_binding_preconditions(
        proposal, prior, private, workspace
    )
    assert result.state is review.PrivateOrderedReviewState.COORDINATION_REFUSED
    assert events == ["registry_lock"]


def test_owner_unavailable_from_lower_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fakes(monkeypatch, prior, events)

    @contextmanager
    def unavailable(*_args: Path) -> Iterator[None]:
        raise ordered.PrivateOrderedCoordinationError(
            ordered.PrivateOrderedCoordinationCode.OWNER_UNAVAILABLE
        )
        yield  # pragma: no cover

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", unavailable)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateOrderedReviewState.OWNER_UNAVAILABLE
    )


def test_owner_changed_from_lower_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)

    @contextmanager
    def changed(*_args: Path) -> Iterator[None]:
        raise ordered.PrivateOrderedCoordinationError(
            ordered.PrivateOrderedCoordinationCode.OWNER_CHANGED
        )
        yield  # pragma: no cover

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", changed)
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateOrderedReviewState.OWNER_CHANGED
    )


def test_precondition_rejection_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fakes(monkeypatch, prior, events)
    wrong_destination = tmp_path / "alternative"
    monkeypatch.setattr(
        preconditions,
        "review_binding_preconditions",
        lambda *_args: preconditions.PrivateBindingPreconditionReview(
            preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH,
            "synthetic refusal",
        ),
    )
    result = review.review_ordered_private_binding_preconditions(
        proposal, prior, private, wrong_destination
    )
    assert result.state is review.PrivateOrderedReviewState.PRECONDITION_REFUSED
    assert (
        result.precondition_state
        is preconditions.PrivateBindingPreconditionState.WORKSPACE_MISMATCH
    )


def test_initialize_refused_before_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, prior, private, workspace = _sample(tmp_path)
    principal = _owner()
    after_descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_NEW)
    )
    after_registry = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner(principal.kind, principal.value),
            1,
            (metadata.PrivateRegistryBinding(_NEW, 1, str(workspace)),),
        )
    )
    proposal = intents.PrivateTransactionIntent(
        witness.PrivateTransactionWitness(
            witness.PrivateBindingOperation.INITIALIZE,
            _TX,
            None,
            _NEW,
            0,
            1,
            None,
            _sha(after_descriptor),
            None,
            _sha(after_registry),
        ),
        None,
        after_descriptor,
        None,
        after_registry,
    )
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    def never_lock(*_args: Path) -> None:
        raise AssertionError("initialization cannot acquire an advisory write gate")

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", never_lock)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateOrderedReviewState.INITIALIZATION_ABSENCE_REVIEW
    )


def test_unqualified_prior_prevents_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    unsafe = replace(prior, state=paired.PrivatePairObservationState.REFUSED_REGISTRY)
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, unsafe, private, workspace
        ).state
        is review.PrivateOrderedReviewState.PRIOR_UNQUALIFIED
    )


def test_invalid_request_prevents_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    assert (
        review.review_ordered_private_binding_preconditions(
            "incorrect",  # type: ignore[arg-type]
            prior,
            private,
            workspace,
        ).state
        is review.PrivateOrderedReviewState.INVALID_REQUEST
    )
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, Path("relative"), workspace
        ).state
        is review.PrivateOrderedReviewState.INVALID_REQUEST
    )


def test_bad_native_io_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    events: list[str] = []
    _fakes(monkeypatch, prior, events)

    def fail_read(_root: Path) -> registry.PrivateRegistrySnapshot:
        raise OSError("sensitive-private-path")

    monkeypatch.setattr(paired, "_registry_read", fail_read)
    result = review.review_ordered_private_binding_preconditions(
        proposal, prior, private, workspace
    )
    assert result.state is review.PrivateOrderedReviewState.IO_ERROR
    assert "sensitive-private-path" not in repr(result)
    assert events[-2:] == ["workspace_unlock", "registry_unlock"]


def test_unsupported_platform_is_nondestructive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal, prior, private, workspace = _sample(tmp_path)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert (
        review.review_ordered_private_binding_preconditions(
            proposal, prior, private, workspace
        ).state
        is review.PrivateOrderedReviewState.UNSUPPORTED
    )


def test_negative_capability_contract() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(review, "commit_binding")
    assert not hasattr(review, "write_registry")
    assert not hasattr(review, "create_private_transaction_intent_file")
