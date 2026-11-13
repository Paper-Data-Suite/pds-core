"""Core #238 3G32: typed, inert protected prepared-stage description."""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

Step = scratch.PrivateScratchWriterStep
State = prepared.PrivatePreparedWriteIntentState
TX = "11111111-1111-4111-8111-111111111111"
BEFORE = b"synthetic-canonical-registry-revision-7"
AFTER = b"synthetic-canonical-registry-revision-8"
DESCRIPTOR = b"synthetic-association-before"
DESCRIPTOR_AFTER = b"synthetic-association-after"
JOURNAL = b"synthetic-canonical-journal\n"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _intent(
    operation: witness.PrivateBindingOperation = witness.PrivateBindingOperation.REBIND_MOVE,
) -> intents.PrivateTransactionIntent:
    w = object.__new__(witness.PrivateTransactionWitness)
    values: dict[str, object] = {
        "operation": operation,
        "transaction_id": TX,
        "association_before": "22222222-2222-4222-8222-222222222222",
        "association_after": "22222222-2222-4222-8222-222222222222",
        "registry_revision_before": 7,
        "registry_revision_after": 8,
        "registry_sha256_before": _sha(BEFORE),
        "registry_sha256_after": _sha(AFTER),
        "descriptor_sha256_before": _sha(DESCRIPTOR),
        "descriptor_sha256_after": _sha(DESCRIPTOR_AFTER),
    }
    for key, value in values.items():
        object.__setattr__(w, key, value)
    item = object.__new__(intents.PrivateTransactionIntent)
    for key, value in {
        "witness": w,
        "registry_before": BEFORE,
        "registry_after": AFTER,
        "descriptor_before": DESCRIPTOR,
        "descriptor_after": DESCRIPTOR_AFTER,
    }.items():
        object.__setattr__(item, key, value)
    return item


@pytest.fixture
def canonical(monkeypatch: pytest.MonkeyPatch) -> intents.PrivateTransactionIntent:
    """Mock serialization only: do not make synthetic text a real registry."""
    item = _intent()

    def encode(_value: intents.PrivateTransactionIntent) -> bytes:
        return JOURNAL

    def decode(raw: bytes) -> intents.PrivateTransactionIntent:
        assert raw == JOURNAL
        return item

    monkeypatch.setattr(intents, "encode_private_transaction_intent", encode)
    monkeypatch.setattr(intents, "decode_private_transaction_intent", decode)
    return item


def _describe(
    item: intents.PrivateTransactionIntent,
    *,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
) -> prepared.PrivatePreparedWriteIntentReview:
    return prepared.describe_private_prepared_stage_write_intent(step, revision, item)


def test_exact_canonical_prepared_write_is_only_a_description(
    canonical: intents.PrivateTransactionIntent,
) -> None:
    result = _describe(canonical)
    assert result.state is State.DESCRIPTION_ONLY_REVIEW_REQUIRED
    assert result.description is not None
    entry = result.description
    assert entry.step is Step.STAGE_TO_REGISTRY
    assert entry.binding_operation is witness.PrivateBindingOperation.REBIND_MOVE
    assert (entry.expected_revision, entry.resulting_revision) == (7, 8)
    assert entry.transaction_id == TX
    assert entry.pending_intent_sha256 == _sha(JOURNAL)
    assert entry.registry_before_sha256 == _sha(BEFORE)
    assert entry.staged_registry_sha256 == _sha(AFTER)
    assert entry.descriptor_before_sha256 == _sha(DESCRIPTOR)
    assert entry.descriptor_after_sha256 == _sha(DESCRIPTOR_AFTER)
    assert "no write" in result.message


@pytest.mark.parametrize("step", [x for x in Step if x is not Step.STAGE_TO_REGISTRY])
def test_other_steps_refused_before_serialization(
    monkeypatch: pytest.MonkeyPatch,
    canonical: intents.PrivateTransactionIntent,
    step: Step,
) -> None:
    monkeypatch.setattr(
        intents,
        "encode_private_transaction_intent",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not serialize")),
    )
    result = _describe(canonical, step=step)
    assert result.state is State.OPERATION_NOT_ADMITTED
    assert result.description is None


@pytest.mark.parametrize(
    "invalid", [None, True, False, 0, 7, 7.0, "stage_to_registry", object(), {}, []]
)
def test_invalid_operation_exact_type_is_refused(
    canonical: intents.PrivateTransactionIntent, invalid: object
) -> None:
    assert (
        prepared.describe_private_prepared_stage_write_intent(
            cast(Step, invalid), 7, canonical
        ).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("invalid", [None, -1, 0, 1, 8, 7.0, True, False, "7", [], {}])
def test_invalid_or_wrong_revision_is_refused(
    canonical: intents.PrivateTransactionIntent, invalid: object
) -> None:
    result = prepared.describe_private_prepared_stage_write_intent(
        Step.STAGE_TO_REGISTRY, cast(int, invalid), canonical
    )
    assert result.state is (
        State.REVISION_MISMATCH_REFUSED
        if type(invalid) is int and invalid in (1, 8)
        else State.INVALID_REQUEST
    )
    assert result.description is None


@pytest.mark.parametrize("invalid", [None, False, 7, b"bytes", object(), {}, []])
def test_invalid_proposal_type_refused(invalid: object) -> None:
    result = prepared.describe_private_prepared_stage_write_intent(
        Step.STAGE_TO_REGISTRY, 7, cast(intents.PrivateTransactionIntent, invalid)
    )
    assert result.state is State.INVALID_REQUEST
    assert result.description is None


def test_initialization_refused_after_canonical_roundtrip(
    canonical: intents.PrivateTransactionIntent,
) -> None:
    object.__setattr__(
        canonical.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    result = _describe(canonical)
    assert result.state is State.INITIALIZATION_REFUSED
    assert result.description is None


def test_fork_copy_is_still_described_not_executed(
    canonical: intents.PrivateTransactionIntent,
) -> None:
    object.__setattr__(
        canonical.witness, "operation", witness.PrivateBindingOperation.FORK_COPY
    )
    assert _describe(canonical).state is State.DESCRIPTION_ONLY_REVIEW_REQUIRED


@pytest.mark.parametrize(
    "name, altered",
    [
        ("registry_before", b"tampered-before"),
        ("registry_after", b"tampered-after"),
        ("descriptor_before", b"tampered-descriptor-before"),
        ("descriptor_after", b"tampered-descriptor-after"),
        ("registry_before", None),
        ("registry_after", None),
        ("descriptor_before", None),
        ("descriptor_after", None),
        ("registry_after", "not bytes"),
        ("registry_before", bytearray(BEFORE)),
    ],
)
def test_tampered_or_missing_images_rejected(
    canonical: intents.PrivateTransactionIntent, name: str, altered: object
) -> None:
    object.__setattr__(canonical, name, altered)
    result = _describe(canonical)
    assert result.state is State.NONCANONICAL_INTENT_REFUSED
    assert result.description is None


@pytest.mark.parametrize(
    "field, invalid",
    [
        ("registry_revision_before", 0),
        ("registry_revision_before", "7"),
        ("registry_revision_after", 9),
        ("registry_revision_after", True),
        ("transaction_id", None),
        ("operation", "rebind_move"),
    ],
)
def test_forged_witness_rejected(
    canonical: intents.PrivateTransactionIntent, field: str, invalid: object
) -> None:
    object.__setattr__(canonical.witness, field, invalid)
    assert _describe(canonical).state is State.NONCANONICAL_INTENT_REFUSED


def test_decode_different_intent_refused(
    canonical: intents.PrivateTransactionIntent, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = _intent()
    object.__setattr__(other, "registry_after", b"different")
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda *_: other)
    assert _describe(canonical).state is State.NONCANONICAL_INTENT_REFUSED


def test_decode_wrong_type_refused(
    canonical: intents.PrivateTransactionIntent, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda *_: object()
    )
    assert _describe(canonical).state is State.NONCANONICAL_INTENT_REFUSED


@pytest.mark.parametrize("raw", [None, 4, "journal", bytearray(JOURNAL)])
def test_nonbyte_serialization_refused(
    canonical: intents.PrivateTransactionIntent,
    monkeypatch: pytest.MonkeyPatch,
    raw: object,
) -> None:
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda *_: raw)
    assert _describe(canonical).state is State.NONCANONICAL_INTENT_REFUSED


def test_noncanonical_second_encoding_refused(
    canonical: intents.PrivateTransactionIntent, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = [0]

    def unequal(_value: intents.PrivateTransactionIntent) -> bytes:
        calls[0] += 1
        return JOURNAL if calls[0] == 1 else b"alternate"

    monkeypatch.setattr(intents, "encode_private_transaction_intent", unequal)
    assert _describe(canonical).state is State.NONCANONICAL_INTENT_REFUSED


@pytest.mark.parametrize(
    "exception", [intents.PrivateIntentError(), witness.PrivateTransactionError()]
)
def test_canonical_refusal_is_sanitized(
    canonical: intents.PrivateTransactionIntent,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    def refused(_value: intents.PrivateTransactionIntent) -> bytes:
        raise exception

    monkeypatch.setattr(intents, "encode_private_transaction_intent", refused)
    result = _describe(canonical)
    assert result.state is State.NONCANONICAL_INTENT_REFUSED
    assert result.description is None


@pytest.mark.parametrize(
    "exception",
    [OSError(), ValueError(), TypeError(), AttributeError(), OverflowError()],
)
def test_unexpected_pure_inspection_failure_is_sanitized(
    canonical: intents.PrivateTransactionIntent,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    def refused(_value: intents.PrivateTransactionIntent) -> bytes:
        raise exception

    monkeypatch.setattr(intents, "encode_private_transaction_intent", refused)
    result = _describe(canonical)
    assert result.state is State.IO_ERROR
    assert result.description is None


def test_interrupt_is_non_authorizing(
    canonical: intents.PrivateTransactionIntent, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(_value: intents.PrivateTransactionIntent) -> bytes:
        raise KeyboardInterrupt

    monkeypatch.setattr(intents, "encode_private_transaction_intent", interrupted)
    assert _describe(canonical).state is State.IO_ERROR


@pytest.mark.parametrize("state", list(State))
def test_refused_statuses_never_contain_description(state: State) -> None:
    result = prepared._result(state)
    assert result.description is None
    assert "C:" not in result.message and "\\\\" not in result.message
    assert "/home/" not in result.message


def test_frozen_description_no_capabilities(
    canonical: intents.PrivateTransactionIntent,
) -> None:
    review = _describe(canonical)
    assert review.description is not None
    item = review.description
    for name in (
        "path",
        "root",
        "bytes",
        "payload",
        "native_handle",
        "handle",
        "token",
        "permit",
        "callback",
        "execute",
        "commit",
        "retire",
        "write",
        "replace",
    ):
        assert not hasattr(item, name)
        assert not hasattr(review, name)
    assert repr(item) == "PrivatePreparedWriteDescription(non_authorizing=True)"
    assert repr(review) == "PrivatePreparedWriteIntentReview(non_authorizing=True)"
    assert TX not in repr(item)
    with pytest.raises(FrozenInstanceError):
        setattr(item, "expected_revision", 9)
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.IO_ERROR)


def test_description_values_are_not_authorization(
    canonical: intents.PrivateTransactionIntent,
) -> None:
    outcome = _describe(canonical)
    assert outcome.description is not None
    forged = replace(outcome.description, pending_intent_sha256="0" * 64)
    assert forged != outcome.description  # descriptions are plain data, forgeable
    assert not any(
        callable(getattr(forged, name, None)) for name in ("execute", "apply", "write")
    )


def test_pure_description_module_never_opens_native_production_storage() -> None:
    source = inspect.getsource(prepared)
    for fragment in (
        "os.replace(",
        "CreateFileW(",
        "open(",
        "unlink(",
        "_hold_existing_retained",
        "TemporaryDirectory(",
    ):
        assert fragment not in source
    assert not hasattr(prepared, "authorize_private_writer")
    assert not hasattr(prepared, "commit_private_recovery")


def test_input_is_not_a_path(canonical: intents.PrivateTransactionIntent) -> None:
    assert not any(
        field
        in inspect.signature(
            prepared.describe_private_prepared_stage_write_intent
        ).parameters
        for field in (
            "existing_private_root",
            "existing_workspace_root",
            "path",
            "callback",
            "token",
        )
    )
    assert isinstance(Path(".").name, str)


def test_no_native_state_from_previous_review(
    canonical: intents.PrivateTransactionIntent,
) -> None:
    observed = _describe(canonical)
    assert observed.description is not None
    assert not hasattr(prepared, "review_protected_native_writer_scope_dry_run")
    assert not hasattr(prepared, "_hold_existing_retained_descriptor_guard")
