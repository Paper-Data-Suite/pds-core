"""Core #238 3G17: nonauthorizing admission and interruption review."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_recovery_operation_admission as admission
from pds_core import _teacher_private_recovery_operation_guard as guarded
from pds_core import _teacher_private_recovery_operation_postconditions as post
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

Kind = post.PrivateRecoveryOperationKind
Image = post.PrivateRecoveryOperationImage
GuardState = guarded.PrivateRecoveryOperationGuardState
AState = admission.PrivateRecoveryAdmissionState
Phase = admission.PrivateRecoveryReportedPhase
IState = admission.PrivateRecoveryInterruptionState

ENCODED = b"canonical-private-intent-v1"
BEFORE = b"registry-7"
AFTER = b"registry-8"
D0 = b"descriptor-7"
D1 = b"descriptor-8"
PREPARED = Image(ENCODED, BEFORE, D0, AFTER)
DESCRIPTOR_PENDING = Image(ENCODED, AFTER, D0, None)
JOURNAL_PENDING = Image(ENCODED, AFTER, D1, None)
JOURNAL_ABSENT = Image(None, AFTER, D1, None)
CASES = (
    (Kind.STAGE_TO_REGISTRY, 7, PREPARED, DESCRIPTOR_PENDING),
    (Kind.DESCRIPTOR_AFTER_IMAGE, 8, DESCRIPTOR_PENDING, JOURNAL_PENDING),
    (Kind.JOURNAL_RETIREMENT, 8, JOURNAL_PENDING, JOURNAL_ABSENT),
)


def _intent() -> intents.PrivateTransactionIntent:
    value = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        value,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            transaction_id="11111111-1111-4111-8111-111111111111",
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(value, "registry_before", BEFORE)
    object.__setattr__(value, "registry_after", AFTER)
    object.__setattr__(value, "descriptor_before", D0)
    object.__setattr__(value, "descriptor_after", D1)
    return value


PROPOSED = _intent()


@pytest.fixture(autouse=True)
def _codec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda _: ENCODED)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: PROPOSED
    )

    def decode(raw: bytes) -> SimpleNamespace:
        if raw == BEFORE:
            return SimpleNamespace(revision=7)
        if raw == AFTER:
            return SimpleNamespace(revision=8)
        raise metadata.PrivateMetadataError(
            metadata.PrivateMetadataErrorCode.INVALID_SHAPE
        )

    def encode(value: SimpleNamespace) -> bytes:
        return BEFORE if value.revision == 7 else AFTER

    monkeypatch.setattr(metadata, "decode_private_registry", decode)
    monkeypatch.setattr(metadata, "encode_private_registry", encode)


def _admit(
    kind: Kind,
    revision: int,
    root: Path,
    proposal: intents.PrivateTransactionIntent = PROPOSED,
) -> admission.PrivateRecoveryAdmissionReview:
    return admission.review_private_recovery_operation_admission(
        kind, revision, proposal, root, root
    )


def _triage(
    phase: Phase,
    kind: Kind,
    revision: int,
    before: Image,
    after: Image,
    proposal: intents.PrivateTransactionIntent = PROPOSED,
) -> admission.PrivateRecoveryInterruptionReview:
    return admission.classify_private_recovery_operation_interruption(
        phase, kind, revision, proposal, before, after
    )


@pytest.mark.parametrize(
    "kind,revision,guard_state",
    [
        (Kind.STAGE_TO_REGISTRY, 7, GuardState.PREPARED_ONE_SCOPE_REVIEW_REQUIRED),
        (
            Kind.DESCRIPTOR_AFTER_IMAGE,
            8,
            GuardState.DESCRIPTOR_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
        ),
    ],
)
def test_matching_guarded_preconditions_are_advisory_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: Kind,
    revision: int,
    guard_state: GuardState,
) -> None:
    calls: list[tuple[object, ...]] = []

    def observe(*args: object) -> guarded.PrivateRecoveryOperationGuardReview:
        calls.append(args)
        return guarded.PrivateRecoveryOperationGuardReview(guard_state, "synthetic")

    monkeypatch.setattr(
        guarded, "review_operation_owned_private_recovery_guard", observe
    )
    result = _admit(kind, revision, tmp_path)
    assert result.state is AState.STABLE_PRECONDITION_REVIEW_REQUIRED
    assert len(calls) == 1
    assert calls[0][1:] == (revision, PROPOSED, tmp_path, tmp_path)
    assert not any(
        hasattr(result, name) for name in ("token", "handle", "permit", "path")
    )
    assert "no execution" in result.message


def test_journal_retirement_rejected_before_native_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*_args: object) -> None:
        pytest.fail("retirement must not reach a native admission review")

    monkeypatch.setattr(
        guarded, "review_operation_owned_private_recovery_guard", forbidden
    )
    assert (
        _admit(Kind.JOURNAL_RETIREMENT, 8, tmp_path).state
        is AState.RETIREMENT_UNQUALIFIED
    )


@pytest.mark.parametrize(
    "guard_state,expected",
    [
        (GuardState.REVISION_MISMATCH_REFUSED, AState.REVISION_MISMATCH_REFUSED),
        (GuardState.ACTION_MISMATCH_REFUSED, AState.CHECKPOINT_CONFLICT_PRESERVE),
        (GuardState.CHECKPOINT_CONFLICT_PRESERVE, AState.CHECKPOINT_CONFLICT_PRESERVE),
        (GuardState.IMAGE_MISMATCH_PRESERVE, AState.IMAGE_CONFLICT_PRESERVE),
        (GuardState.IMAGE_DRIFT_PRESERVE, AState.IMAGE_CONFLICT_PRESERVE),
        (GuardState.NAMESPACE_CHANGED_PRESERVE, AState.NAMESPACE_CHANGED_PRESERVE),
        (GuardState.OWNER_CHANGED, AState.OWNER_CHANGED),
        (GuardState.GUARD_REFUSED, AState.GUARD_REFUSED),
        (GuardState.INTERRUPTED_PRESERVE, AState.INTERRUPTED_PRESERVE),
        (GuardState.INVALID_REQUEST, AState.INVALID_REQUEST),
        (GuardState.INITIALIZATION_REFUSED, AState.INITIALIZATION_REFUSED),
        (GuardState.UNSUPPORTED, AState.UNSUPPORTED),
        (GuardState.IO_ERROR, AState.IO_ERROR),
        (
            GuardState.JOURNAL_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
            AState.CHECKPOINT_CONFLICT_PRESERVE,
        ),
        (
            GuardState.DESCRIPTOR_PENDING_ONE_SCOPE_REVIEW_REQUIRED,
            AState.CHECKPOINT_CONFLICT_PRESERVE,
        ),
    ],
)
def test_native_guard_failures_never_promote_to_admission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    guard_state: GuardState,
    expected: AState,
) -> None:
    monkeypatch.setattr(
        guarded,
        "review_operation_owned_private_recovery_guard",
        lambda *_: guarded.PrivateRecoveryOperationGuardReview(guard_state, "native"),
    )
    assert _admit(Kind.STAGE_TO_REGISTRY, 7, tmp_path).state is expected


@pytest.mark.parametrize("bad", [None, 1, True, "stage", b"bytes", object()])
def test_invalid_kind_never_invokes_native_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(
        guarded,
        "review_operation_owned_private_recovery_guard",
        lambda *_: pytest.fail("invalid argument reached native guard"),
    )
    assert _admit(cast(Kind, bad), 7, tmp_path).state is AState.INVALID_REQUEST


@pytest.mark.parametrize("bad", [0, -1, True, "7", 7.0, None, object()])
def test_invalid_revision_never_invokes_native_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(
        guarded,
        "review_operation_owned_private_recovery_guard",
        lambda *_: pytest.fail("invalid argument reached native guard"),
    )
    assert (
        _admit(Kind.STAGE_TO_REGISTRY, cast(int, bad), tmp_path).state
        is AState.INVALID_REQUEST
    )


def test_invalid_proposal_type_refused(tmp_path: Path) -> None:
    assert (
        _admit(
            Kind.STAGE_TO_REGISTRY,
            7,
            tmp_path,
            cast(intents.PrivateTransactionIntent, object()),
        ).state
        is AState.INVALID_REQUEST
    )


@pytest.mark.parametrize(
    "fault",
    [KeyboardInterrupt(), PermissionError(), ValueError(), TypeError(), OSError()],
)
def test_native_review_interruption_and_errors_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fault: BaseException
) -> None:
    def fail(*_args: object) -> None:
        raise fault

    monkeypatch.setattr(guarded, "review_operation_owned_private_recovery_guard", fail)
    expected = (
        AState.INTERRUPTED_PRESERVE
        if isinstance(fault, KeyboardInterrupt)
        else AState.IO_ERROR
    )
    assert _admit(Kind.STAGE_TO_REGISTRY, 7, tmp_path).state is expected


@pytest.mark.parametrize("value", [None, object(), "review", True])
def test_malformed_native_review_preserves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: object
) -> None:
    monkeypatch.setattr(
        guarded, "review_operation_owned_private_recovery_guard", lambda *_: value
    )
    assert (
        _admit(Kind.STAGE_TO_REGISTRY, 7, tmp_path).state
        is AState.IMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("kind,revision,before,after", CASES)
def test_returned_phase_requires_exact_postimages(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    state = _triage(Phase.RETURNED, kind, revision, before, after).state
    expected = (
        IState.RETIREMENT_UNQUALIFIED
        if kind is Kind.JOURNAL_RETIREMENT
        else IState.POSTIMAGE_REVIEW_REQUIRED
    )
    assert state is expected


@pytest.mark.parametrize("kind,revision,before,after", CASES)
def test_reported_not_started_stable_images_only(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    del after
    expected = (
        IState.RETIREMENT_UNQUALIFIED
        if kind is Kind.JOURNAL_RETIREMENT
        else IState.UNCHANGED_BEFORE_REVIEW_REQUIRED
    )
    assert _triage(Phase.NOT_STARTED, kind, revision, before, before).state is expected


@pytest.mark.parametrize("kind,revision,before,after", CASES)
def test_reported_not_started_but_changed_images_preserves(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    expected = (
        IState.RETIREMENT_UNQUALIFIED
        if kind is Kind.JOURNAL_RETIREMENT
        else IState.UNEXPECTED_CHANGE_PRESERVE
    )
    assert _triage(Phase.NOT_STARTED, kind, revision, before, after).state is expected


@pytest.mark.parametrize("kind,revision,before,after", CASES)
@pytest.mark.parametrize("seen_after", [False, True])
def test_interrupted_or_unknown_never_promoted_even_with_matching_images(
    kind: Kind, revision: int, before: Image, after: Image, seen_after: bool
) -> None:
    observed = after if seen_after else before
    assert (
        _triage(Phase.INTERRUPTED_OR_UNKNOWN, kind, revision, before, observed).state
        is IState.INTERRUPTED_PRESERVE
    )


@pytest.mark.parametrize("kind,revision,before,after", CASES)
def test_returned_without_image_progress_preserves(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    del after
    expected = (
        IState.RETIREMENT_UNQUALIFIED
        if kind is Kind.JOURNAL_RETIREMENT
        else IState.NO_PROGRESS_PRESERVE
    )
    assert _triage(Phase.RETURNED, kind, revision, before, before).state is expected


@pytest.mark.parametrize("kind,revision,before,after", CASES)
def test_unexpected_postimage_is_conflict(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    del after
    wrong = Image(ENCODED, b"foreign", D0, None)
    expected = (
        IState.RETIREMENT_UNQUALIFIED
        if kind is Kind.JOURNAL_RETIREMENT
        else IState.CONFLICT_PRESERVE
    )
    assert _triage(Phase.RETURNED, kind, revision, before, wrong).state is expected


@pytest.mark.parametrize("kind,revision,before,after", CASES)
def test_wrong_before_image_refused_in_all_phases(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    del before
    wrong = Image(ENCODED, b"foreign", D0, None)
    for phase in Phase:
        assert (
            _triage(phase, kind, revision, wrong, after).state
            is IState.PRECONDITION_REFUSED
        )


@pytest.mark.parametrize("kind,revision,before,after", CASES)
@pytest.mark.parametrize("offset", [-10, -1, 1, 2])
def test_wrong_revision_refused_in_all_phases(
    kind: Kind, revision: int, before: Image, after: Image, offset: int
) -> None:
    wrong = revision + offset
    expected = IState.REVISION_MISMATCH_REFUSED if wrong > 0 else IState.INVALID_REQUEST
    for phase in Phase:
        assert _triage(phase, kind, wrong, before, after).state is expected


@pytest.mark.parametrize("kind,revision,before,after", CASES)
@pytest.mark.parametrize("bad", [None, True, "returned", 0, object()])
def test_phase_type_must_be_exact_enum(
    kind: Kind, revision: int, before: Image, after: Image, bad: object
) -> None:
    assert (
        _triage(cast(Phase, bad), kind, revision, before, after).state
        is IState.INVALID_REQUEST
    )


@pytest.mark.parametrize("kind,revision,before,after", CASES)
@pytest.mark.parametrize("bad", [None, False, "kind", 0])
def test_invalid_kind_cannot_gain_interruption_state(
    kind: Kind, revision: int, before: Image, after: Image, bad: object
) -> None:
    del kind
    assert (
        _triage(Phase.RETURNED, cast(Kind, bad), revision, before, after).state
        is IState.INVALID_REQUEST
    )


def test_noncanonical_proposal_stays_refused_in_interruption_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = _intent()
    object.__setattr__(other, "registry_before", b"unexpected")
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: other)
    assert (
        _triage(
            Phase.RETURNED, Kind.STAGE_TO_REGISTRY, 7, PREPARED, DESCRIPTOR_PENDING
        ).state
        is IState.INVALID_REQUEST
    )


def test_initialize_refused_by_transition_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = _intent()
    object.__setattr__(
        other,
        "witness",
        SimpleNamespace(operation=witness.PrivateBindingOperation.INITIALIZE),
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: other)
    assert (
        _triage(
            Phase.RETURNED,
            Kind.STAGE_TO_REGISTRY,
            7,
            PREPARED,
            DESCRIPTOR_PENDING,
            other,
        ).state
        is IState.INITIALIZATION_REFUSED
    )


def test_keyboard_interrupt_in_underlying_classifier_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupted(*_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        post, "classify_private_recovery_operation_postconditions", interrupted
    )
    assert (
        _triage(
            Phase.RETURNED, Kind.STAGE_TO_REGISTRY, 7, PREPARED, DESCRIPTOR_PENDING
        ).state
        is IState.INTERRUPTED_PRESERVE
    )


@pytest.mark.parametrize("malformed", [None, object(), False])
def test_malformed_classifier_result_is_refused(
    monkeypatch: pytest.MonkeyPatch, malformed: object
) -> None:
    monkeypatch.setattr(
        post, "classify_private_recovery_operation_postconditions", lambda *_: malformed
    )
    assert (
        _triage(
            Phase.RETURNED, Kind.STAGE_TO_REGISTRY, 7, PREPARED, DESCRIPTOR_PENDING
        ).state
        is IState.CONFLICT_PRESERVE
    )


def test_results_are_frozen_sanitized_and_not_exported_as_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guarded,
        "review_operation_owned_private_recovery_guard",
        lambda *_: guarded.PrivateRecoveryOperationGuardReview(
            GuardState.PREPARED_ONE_SCOPE_REVIEW_REQUIRED, "native"
        ),
    )
    first = _admit(Kind.STAGE_TO_REGISTRY, 7, tmp_path)
    second = _triage(
        Phase.RETURNED, Kind.STAGE_TO_REGISTRY, 7, PREPARED, DESCRIPTOR_PENDING
    )
    with pytest.raises(FrozenInstanceError):
        first.state = AState.IO_ERROR  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        second.state = IState.CONFLICT_PRESERVE  # type: ignore[misc]
    for result in (first, second):
        assert all(
            not hasattr(result, key)
            for key in ("bytes", "path", "handle", "write", "token", "revision")
        )
        assert "registry-" not in repr(result)
        assert "descriptor-" not in repr(result)
        assert "canonical-private" not in repr(result)
    assert "notes.records.v1" not in get_teacher_experience_capabilities()
    assert "notes.portability.v1" not in get_teacher_experience_capabilities()
