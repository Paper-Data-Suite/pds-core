"""Core #238 Slice 3G15: pure, nonauthorizing recovery operation transitions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import cast

import pytest

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_recovery_operation_postconditions as post
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

Kind = post.PrivateRecoveryOperationKind
State = post.PrivateRecoveryPostconditionState
Image = post.PrivateRecoveryOperationImage

ENCODED = b"canonical-private-intent-v1"
BEFORE = b"registry-7"
AFTER = b"registry-8"
D0 = b"descriptor-7"
D1 = b"descriptor-8"


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


_PROPOSED = _intent()
_PREPARED = Image(ENCODED, BEFORE, D0, AFTER)
_DESCRIPTOR = Image(ENCODED, AFTER, D0, None)
_JOURNAL = Image(ENCODED, AFTER, D1, None)
_RETIRED = Image(None, AFTER, D1, None)
_CASES = (
    (
        Kind.STAGE_TO_REGISTRY,
        7,
        _PREPARED,
        _DESCRIPTOR,
        State.TRANSITION_OBSERVED_REVIEW_REQUIRED,
    ),
    (
        Kind.DESCRIPTOR_AFTER_IMAGE,
        8,
        _DESCRIPTOR,
        _JOURNAL,
        State.TRANSITION_OBSERVED_REVIEW_REQUIRED,
    ),
    (Kind.JOURNAL_RETIREMENT, 8, _JOURNAL, _RETIRED, State.JOURNAL_ABSENCE_UNQUALIFIED),
)


@pytest.fixture(autouse=True)
def _codec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda _: ENCODED)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: _PROPOSED
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
    kind: Kind,
    revision: int,
    before: Image,
    after: Image,
    proposed: intents.PrivateTransactionIntent = _PROPOSED,
) -> post.PrivateRecoveryPostconditionReview:
    return post.classify_private_recovery_operation_postconditions(
        kind, revision, proposed, before, after
    )


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
def test_exact_transition_is_observation_only(
    kind: Kind, revision: int, before: Image, after: Image, state: State
) -> None:
    actual = _review(kind, revision, before, after)
    assert actual.state is state
    assert "durab" in actual.message


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
def test_no_progress_is_preserved(
    kind: Kind, revision: int, before: Image, after: Image, state: State
) -> None:
    del after, state
    assert _review(kind, revision, before, before).state is State.NO_PROGRESS_PRESERVE


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
@pytest.mark.parametrize("revision_delta", [-3, -1, 1, 10])
def test_expected_revision_cannot_be_substituted(
    kind: Kind,
    revision: int,
    before: Image,
    after: Image,
    state: State,
    revision_delta: int,
) -> None:
    del state
    wrong = revision + revision_delta
    result = _review(kind, wrong, before, after)
    expected = State.REVISION_MISMATCH_REFUSED if wrong > 0 else State.INVALID_REQUEST
    assert result.state is expected


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
@pytest.mark.parametrize("index", range(4))
def test_changed_after_image_preserves_evidence(
    kind: Kind, revision: int, before: Image, after: Image, state: State, index: int
) -> None:
    del state
    payload = [after.journal, after.registry, after.descriptor, after.stage]
    if index == 0:
        payload[index] = b"different-journal"
    elif index == 3:
        payload[index] = b"different-stage"
    else:
        payload[index] = b"different-metadata"
    wrong = Image(
        payload[0], cast(bytes, payload[1]), cast(bytes, payload[2]), payload[3]
    )
    assert (
        _review(kind, revision, before, wrong).state
        is State.POSTCONDITION_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
@pytest.mark.parametrize("index", range(4))
def test_changed_precondition_is_refused(
    kind: Kind, revision: int, before: Image, after: Image, state: State, index: int
) -> None:
    del state
    payload = [before.journal, before.registry, before.descriptor, before.stage]
    payload[index] = b"different-before"
    wrong = Image(
        payload[0], cast(bytes, payload[1]), cast(bytes, payload[2]), payload[3]
    )
    assert _review(kind, revision, wrong, after).state is State.PRECONDITION_REFUSED


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
@pytest.mark.parametrize("alternate", [0, 1, 2])
def test_cross_phase_after_images_cannot_complete_another_step(
    kind: Kind, revision: int, before: Image, after: Image, state: State, alternate: int
) -> None:
    del state
    foreign = (_DESCRIPTOR, _JOURNAL, _RETIRED)[alternate]
    if foreign != before and foreign != after:
        assert (
            _review(kind, revision, before, foreign).state
            is State.POSTCONDITION_CONFLICT_PRESERVE
        )


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
@pytest.mark.parametrize("wrong", [None, "strings", True, 7, b"bytes"])
def test_invalid_operation_kind_fails_closed(
    kind: Kind, revision: int, before: Image, after: Image, state: State, wrong: object
) -> None:
    del kind, state
    assert (
        _review(cast(Kind, wrong), revision, before, after).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("kind,revision,before,after,state", _CASES)
@pytest.mark.parametrize("wrong", [True, 0, -1, "7", 7.0])
def test_invalid_revision_type_fails_closed(
    kind: Kind, revision: int, before: Image, after: Image, state: State, wrong: object
) -> None:
    del revision, state
    assert _review(kind, cast(int, wrong), before, after).state is State.INVALID_REQUEST


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("wrong", ["not-bytes", 44, bytearray(b"mutable")])
def test_unqualified_image_fields_refused(index: int, wrong: object) -> None:
    contents: list[object] = [
        _PREPARED.journal,
        _PREPARED.registry,
        _PREPARED.descriptor,
        _PREPARED.stage,
    ]
    contents[index] = wrong
    malformed = Image(*contents)  # type: ignore[arg-type]
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, malformed, _DESCRIPTOR).state
        is State.INVALID_REQUEST
    )
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, _PREPARED, malformed).state
        is State.INVALID_REQUEST
    )


def test_bounded_image_size_rejects_oversized_journal() -> None:
    wrong = Image(ENCODED + b"!", BEFORE, D0, AFTER)
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, wrong, _DESCRIPTOR).state
        is State.INVALID_REQUEST
    )


def test_bounded_registry_and_descriptor_reject_oversized_raw_values() -> None:
    wrong_registry = Image(ENCODED, b"x" * (metadata.MAX_REGISTRY_BYTES + 1), D0, AFTER)
    wrong_descriptor = Image(
        ENCODED, BEFORE, b"x" * (metadata.MAX_ASSOCIATION_BYTES + 1), AFTER
    )
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, wrong_registry, _DESCRIPTOR).state
        is State.INVALID_REQUEST
    )
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, wrong_descriptor, _DESCRIPTOR).state
        is State.INVALID_REQUEST
    )


def test_foreign_image_object_is_rejected() -> None:
    assert (
        _review(
            Kind.STAGE_TO_REGISTRY,
            7,
            cast(Image, (ENCODED, BEFORE, D0, AFTER)),
            _DESCRIPTOR,
        ).state
        is State.INVALID_REQUEST
    )


def test_initialize_never_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    other = _intent()
    object.__setattr__(
        other,
        "witness",
        SimpleNamespace(operation=witness.PrivateBindingOperation.INITIALIZE),
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: other)
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, _PREPARED, _DESCRIPTOR, other).state
        is State.INITIALIZATION_REFUSED
    )


def test_wrong_proposal_type_refused() -> None:
    assert (
        _review(
            Kind.STAGE_TO_REGISTRY,
            7,
            _PREPARED,
            _DESCRIPTOR,
            cast(intents.PrivateTransactionIntent, object()),
        ).state
        is State.INVALID_REQUEST
    )


def test_noncanonical_codec_roundtrip_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    other = _intent()
    object.__setattr__(other, "registry_before", b"different")
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: other)
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, _PREPARED, _DESCRIPTOR).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("offset", [0, 2, -1])
def test_noncanonical_witness_revision_refused(
    monkeypatch: pytest.MonkeyPatch, offset: int
) -> None:
    other = _intent()
    object.__setattr__(
        other,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            registry_revision_before=7,
            registry_revision_after=8 + offset,
        ),
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda _: other)
    expected = (
        State.INVALID_REQUEST
        if offset != 0
        else State.TRANSITION_OBSERVED_REVIEW_REQUIRED
    )
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, _PREPARED, _DESCRIPTOR, other).state
        is expected
    )


def test_metadata_codec_exception_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_: bytes) -> None:
        raise metadata.PrivateMetadataError(
            metadata.PrivateMetadataErrorCode.INVALID_SHAPE
        )

    monkeypatch.setattr(metadata, "decode_private_registry", fail)
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, _PREPARED, _DESCRIPTOR).state
        is State.INVALID_REQUEST
    )


def test_interrupted_codec_preserves_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    def stop(_: object) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(intents, "encode_private_transaction_intent", stop)
    assert (
        _review(Kind.STAGE_TO_REGISTRY, 7, _PREPARED, _DESCRIPTOR).state
        is State.INTERRUPTED_PRESERVE
    )


def test_never_accept_absence_of_journal_as_durable_retirement() -> None:
    result = _review(Kind.JOURNAL_RETIREMENT, 8, _JOURNAL, _RETIRED)
    assert result.state is State.JOURNAL_ABSENCE_UNQUALIFIED
    assert cast(State, result.state) is not State.TRANSITION_OBSERVED_REVIEW_REQUIRED


def test_dataclasses_are_frozen_and_private_bytes_not_printed() -> None:
    assert ENCODED.decode() not in repr(_PREPARED)
    with pytest.raises(FrozenInstanceError):
        _PREPARED.journal = b"rewrite"  # type: ignore[misc]
    result = _review(Kind.STAGE_TO_REGISTRY, 7, _PREPARED, _DESCRIPTOR)
    with pytest.raises(FrozenInstanceError):
        result.state = State.INVALID_REQUEST  # type: ignore[misc]


def test_no_notes_activation_or_writer_export() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for name in (
        "commit_private_workspace_binding",
        "retire_private_journal",
        "open_notes",
    ):
        assert not hasattr(post, name)
