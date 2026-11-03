"""Core #238 3G18: fail-closed reported writer-scope sequencing contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import cast

import pytest

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_recovery_operation_admission as admission
from pds_core import _teacher_private_recovery_operation_postconditions as post
from pds_core import _teacher_private_recovery_writer_sequence as sequence
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

Kind = post.PrivateRecoveryOperationKind
Image = post.PrivateRecoveryOperationImage
Phase = sequence.PrivateRecoveryWriterPhase
State = sequence.PrivateRecoveryWriterSequenceState
Report = admission.PrivateRecoveryReportedPhase

ENCODED = b"canonical-private-intent-v1"
BEFORE = b"registry-7"
AFTER = b"registry-8"
D0 = b"descriptor-7"
D1 = b"descriptor-8"
PREPARED = Image(ENCODED, BEFORE, D0, AFTER)
DESCRIPTOR_PENDING = Image(ENCODED, AFTER, D0, None)
JOURNAL_PENDING = Image(ENCODED, AFTER, D1, None)
JOURNAL_ABSENT = Image(None, AFTER, D1, None)


def _intent() -> intents.PrivateTransactionIntent:
    result = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        result,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            transaction_id="11111111-1111-4111-8111-111111111111",
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(result, "registry_before", BEFORE)
    object.__setattr__(result, "registry_after", AFTER)
    object.__setattr__(result, "descriptor_before", D0)
    object.__setattr__(result, "descriptor_after", D1)
    return result


PROPOSED = _intent()
GOOD_PREFIX = (Phase.GUARD_ACQUIRED, Phase.PREIMAGE_REVALIDATED)
GOOD_RETURN = GOOD_PREFIX + (
    Phase.OPERATION_INVOKED,
    Phase.OPERATION_RETURNED,
    Phase.POSTIMAGE_REVALIDATED,
)


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


def _review(
    phases: tuple[Phase, ...] = GOOD_RETURN,
    reported: Report = Report.RETURNED,
    kind: Kind = Kind.STAGE_TO_REGISTRY,
    revision: int = 7,
    before: Image = PREPARED,
    after: Image = DESCRIPTOR_PENDING,
    proposed: intents.PrivateTransactionIntent = PROPOSED,
) -> sequence.PrivateRecoveryWriterSequenceReview:
    return sequence.review_private_recovery_writer_sequence(
        kind, revision, proposed, phases, reported, before, after
    )


@pytest.mark.parametrize(
    "kind,revision,before,after",
    [
        (Kind.STAGE_TO_REGISTRY, 7, PREPARED, DESCRIPTOR_PENDING),
        (Kind.DESCRIPTOR_AFTER_IMAGE, 8, DESCRIPTOR_PENDING, JOURNAL_PENDING),
    ],
)
def test_exact_reported_return_remains_advisory(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    result = _review(GOOD_RETURN, Report.RETURNED, kind, revision, before, after)
    assert result.state is State.RETURNED_POSTIMAGE_REVIEW_REQUIRED
    assert not any(
        hasattr(result, name)
        for name in ("write", "token", "path", "handle", "permit", "revision")
    )
    assert "unproved" in result.message


@pytest.mark.parametrize(
    "phases",
    [
        GOOD_PREFIX,
        GOOD_PREFIX + (Phase.GUARD_RELEASED,),
        (Phase.GUARD_ACQUIRED, Phase.PREIMAGE_REVALIDATED),
    ],
)
def test_preflight_does_not_grant_execution(phases: tuple[Phase, ...]) -> None:
    result = _review(phases, Report.NOT_STARTED, after=PREPARED)
    assert result.state is State.PRECHECK_REVIEW_REQUIRED
    assert "not been qualified" in result.message


@pytest.mark.parametrize(
    "phases",
    [
        GOOD_RETURN + (Phase.PERSISTENCE_REQUESTED,),
        GOOD_RETURN + (Phase.PERSISTENCE_REQUESTED, Phase.GUARD_RELEASED),
    ],
)
def test_caller_reported_persistence_cannot_qualify_durability(
    phases: tuple[Phase, ...],
) -> None:
    assert _review(phases).state is State.PERSISTENCE_UNQUALIFIED


@pytest.mark.parametrize(
    "phases",
    [
        (Phase.GUARD_ACQUIRED,),
    ],
)
def test_preflight_without_checkpoint_is_incomplete(phases: tuple[Phase, ...]) -> None:
    assert (
        _review(phases, Report.NOT_STARTED, after=PREPARED).state
        is State.INCOMPLETE_PRESERVE
    )


@pytest.mark.parametrize(
    "phases",
    [
        (),
        (Phase.PREIMAGE_REVALIDATED,),
        (Phase.GUARD_ACQUIRED, Phase.GUARD_ACQUIRED),
        (Phase.GUARD_ACQUIRED, Phase.OPERATION_INVOKED),
        (Phase.GUARD_ACQUIRED, Phase.OPERATION_RETURNED),
        (Phase.GUARD_ACQUIRED, Phase.POSTIMAGE_REVALIDATED),
        (Phase.GUARD_ACQUIRED, Phase.PERSISTENCE_REQUESTED),
        GOOD_PREFIX + (Phase.OPERATION_RETURNED,),
        GOOD_PREFIX + (Phase.POSTIMAGE_REVALIDATED,),
        GOOD_PREFIX + (Phase.PERSISTENCE_REQUESTED,),
        GOOD_PREFIX + (Phase.GUARD_RELEASED, Phase.OPERATION_INVOKED),
        GOOD_PREFIX + (Phase.OPERATION_INVOKED, Phase.GUARD_RELEASED),
        GOOD_RETURN + (Phase.GUARD_RELEASED, Phase.PERSISTENCE_REQUESTED),
        GOOD_RETURN + (Phase.POSTIMAGE_REVALIDATED,),
        GOOD_RETURN + (Phase.GUARD_RELEASED, Phase.GUARD_RELEASED),
        GOOD_RETURN + (Phase.PREIMAGE_REVALIDATED,),
    ],
)
def test_invalid_reported_phase_order_fail_closed(phases: tuple[Phase, ...]) -> None:
    expected = (
        State.INVALID_REQUEST if not phases or len(phases) > 7 else State.ORDER_REFUSED
    )
    assert _review(phases).state is expected


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        (),
        "guard_acquired",
        [Phase.GUARD_ACQUIRED],
        ("guard_acquired",),
        (None,),
        (True,),
        (1,),
    ],
)
def test_invalid_trace_shape_rejected(bad: object) -> None:
    assert _review(cast(tuple[Phase, ...], bad)).state is State.INVALID_REQUEST


@pytest.mark.parametrize("bad", [None, object(), "returned", True, 1, 0])
def test_invalid_report_state_rejected(bad: object) -> None:
    assert _review(reported=cast(Report, bad)).state is State.INVALID_REQUEST


@pytest.mark.parametrize("bad", [None, object(), "stage_to_registry", True, 1, 0])
def test_invalid_operation_kind_rejected(bad: object) -> None:
    assert _review(kind=cast(Kind, bad)).state is State.INVALID_REQUEST


@pytest.mark.parametrize("bad", [None, object(), "7", True, 7.0, 0, -1])
def test_invalid_revision_rejected(bad: object) -> None:
    assert _review(revision=cast(int, bad)).state is State.INVALID_REQUEST


def test_invalid_transaction_type_rejected() -> None:
    assert (
        _review(proposed=cast(intents.PrivateTransactionIntent, object())).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("bad", [None, object(), True, "snapshot", (b"x", b"y")])
def test_invalid_before_image_type_rejected(bad: object) -> None:
    assert _review(before=cast(Image, bad)).state is State.INVALID_REQUEST


@pytest.mark.parametrize("bad", [None, object(), True, "snapshot", (b"x", b"y")])
def test_invalid_after_image_type_rejected(bad: object) -> None:
    assert _review(after=cast(Image, bad)).state is State.INVALID_REQUEST


@pytest.mark.parametrize(
    "reported,phases,expected",
    [
        (Report.NOT_STARTED, GOOD_RETURN, State.REPORTED_PHASE_CONFLICT_PRESERVE),
        (
            Report.NOT_STARTED,
            GOOD_PREFIX + (Phase.OPERATION_INVOKED,),
            State.REPORTED_PHASE_CONFLICT_PRESERVE,
        ),
        (Report.RETURNED, GOOD_PREFIX, State.REPORTED_PHASE_CONFLICT_PRESERVE),
        (
            Report.RETURNED,
            GOOD_PREFIX + (Phase.OPERATION_INVOKED,),
            State.REPORTED_PHASE_CONFLICT_PRESERVE,
        ),
        (
            Report.RETURNED,
            GOOD_PREFIX + (Phase.OPERATION_INVOKED, Phase.OPERATION_RETURNED),
            State.INCOMPLETE_PRESERVE,
        ),
        (Report.INTERRUPTED_OR_UNKNOWN, GOOD_PREFIX, State.INTERRUPTED_PRESERVE),
        (
            Report.INTERRUPTED_OR_UNKNOWN,
            GOOD_PREFIX + (Phase.OPERATION_INVOKED,),
            State.INTERRUPTED_PRESERVE,
        ),
        (Report.INTERRUPTED_OR_UNKNOWN, GOOD_RETURN, State.INTERRUPTED_PRESERVE),
        (
            Report.INTERRUPTED_OR_UNKNOWN,
            GOOD_RETURN + (Phase.GUARD_RELEASED,),
            State.INTERRUPTED_PRESERVE,
        ),
    ],
)
def test_interruption_and_reported_phase_consistency(
    reported: Report, phases: tuple[Phase, ...], expected: State
) -> None:
    assert _review(phases, reported).state is expected


@pytest.mark.parametrize(
    "kind,revision,before,after",
    [
        (Kind.STAGE_TO_REGISTRY, 7, PREPARED, PREPARED),
        (Kind.DESCRIPTOR_AFTER_IMAGE, 8, DESCRIPTOR_PENDING, DESCRIPTOR_PENDING),
    ],
)
def test_return_without_transition_preserves(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    assert (
        _review(GOOD_RETURN, Report.RETURNED, kind, revision, before, after).state
        is State.NO_PROGRESS_PRESERVE
    )


@pytest.mark.parametrize(
    "kind,revision,before,after",
    [
        (Kind.STAGE_TO_REGISTRY, 7, DESCRIPTOR_PENDING, JOURNAL_PENDING),
        (Kind.DESCRIPTOR_AFTER_IMAGE, 8, PREPARED, DESCRIPTOR_PENDING),
    ],
)
def test_wrong_starting_checkpoint_preserved(
    kind: Kind, revision: int, before: Image, after: Image
) -> None:
    assert (
        _review(GOOD_RETURN, Report.RETURNED, kind, revision, before, after).state
        is State.PREIMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize(
    "after",
    [
        Image(ENCODED, AFTER, D1, None),
        Image(ENCODED, BEFORE, D0, None),
        Image(ENCODED, AFTER, D0, AFTER),
        Image(None, AFTER, D0, None),
        Image(ENCODED, AFTER, D0, b"unexpected"),
    ],
)
def test_partial_postimages_preserved(after: Image) -> None:
    assert _review(after=after).state is State.POSTIMAGE_CONFLICT_PRESERVE


def test_changed_image_and_reported_nonexecution_preserved() -> None:
    assert (
        _review(GOOD_PREFIX, Report.NOT_STARTED).state
        is State.REPORTED_PHASE_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize(
    "report", [Report.RETURNED, Report.NOT_STARTED, Report.INTERRUPTED_OR_UNKNOWN]
)
def test_retirement_is_unqualified_without_journal_absence_custody(
    report: Report,
) -> None:
    assert (
        _review(
            GOOD_RETURN,
            report,
            Kind.JOURNAL_RETIREMENT,
            8,
            JOURNAL_PENDING,
            JOURNAL_ABSENT,
        ).state
        is State.RETIREMENT_UNQUALIFIED
    )


def test_expected_revision_mismatch() -> None:
    assert _review(revision=8).state is State.REVISION_MISMATCH_REFUSED


def test_initialization_refused() -> None:
    prior = PROPOSED.witness.operation
    try:
        object.__setattr__(
            PROPOSED.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
        )
        assert _review().state is State.INITIALIZATION_REFUSED
    finally:
        object.__setattr__(PROPOSED.witness, "operation", prior)


@pytest.mark.parametrize(
    "error",
    [
        KeyboardInterrupt(),
        OSError(),
        ValueError(),
        TypeError(),
        AttributeError(),
        OverflowError(),
    ],
)
def test_classifier_errors_preserve_without_write(
    monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    def fail(*_args: object) -> None:
        raise error

    monkeypatch.setattr(
        admission, "classify_private_recovery_operation_interruption", fail
    )
    expected = (
        State.INTERRUPTED_PRESERVE
        if isinstance(error, KeyboardInterrupt)
        else State.POSTIMAGE_CONFLICT_PRESERVE
    )
    assert _review().state is expected


@pytest.mark.parametrize("bad", [None, object(), "review", True, 123])
def test_malformed_classifier_result_preserved(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    monkeypatch.setattr(
        admission, "classify_private_recovery_operation_interruption", lambda *_: bad
    )
    assert _review().state is State.POSTIMAGE_CONFLICT_PRESERVE


def test_review_is_frozen_and_does_not_expose_private_images() -> None:
    result = _review()
    with pytest.raises(FrozenInstanceError):
        result.message = "changed"  # type: ignore[misc]
    assert ENCODED.decode() not in repr(result)
    assert BEFORE.decode() not in repr(result)
    assert D0.decode() not in repr(result)
    assert not hasattr(result, "phases")


def test_no_notes_capability_advertised() -> None:
    names = get_teacher_experience_capabilities()
    assert not any(str(item).startswith("notes.") for item in names)
