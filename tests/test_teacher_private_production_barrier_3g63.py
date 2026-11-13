"""Core #238 Slice 3G63: sanitized failure of non-authorizing review.

All inputs are synthetic.  No production filesystem access or writer.
"""

from __future__ import annotations

from typing import cast

import pytest

from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("C:\\synthetic-private\\registry.json: hostile diagnostic"),
        NotImplementedError("synthetic teacher identifier MUST NOT LEAK"),
    ],
)
def test_unexpected_review_runtime_error_is_a_sanitized_refusal(
    monkeypatch: pytest.MonkeyPatch, failure: RuntimeError
) -> None:
    """No exception text or authority may escape a failed inert review."""

    def raise_failure(*_args: object) -> object:
        raise failure

    monkeypatch.setattr(
        prepared, "describe_private_prepared_stage_write_intent", raise_failure
    )
    synthetic = object.__new__(intents.PrivateTransactionIntent)
    result = barrier.review_private_production_write_barrier(
        scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
        7,
        synthetic,
    )
    assert type(result) is barrier.PrivateProductionWriteBarrierReview
    assert (
        result.state
        is barrier.PrivateProductionWriteBarrierState.DESCRIPTION_UNQUALIFIED
    )
    assert result.message == (
        "The inert prepared write description could not be qualified."
    )
    assert str(failure) not in result.message
    assert result.unqualified_requirements == tuple(
        barrier.PrivateProductionWriteRequirement
    )
    assert len(result.unqualified_requirements) == 9
    assert repr(result) == "PrivateProductionWriteBarrierReview(non_authorizing=True)"
    assert not any(
        hasattr(result, key)
        for key in ("permit", "execute", "write", "path", "native_handle")
    )


def test_invalid_request_does_not_call_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid typed requests still short-circuit before the faulting dependency."""
    called = False

    def raise_failure(*_args: object) -> object:
        nonlocal called
        called = True
        raise RuntimeError("unreachable")

    monkeypatch.setattr(
        prepared, "describe_private_prepared_stage_write_intent", raise_failure
    )
    result = barrier.review_private_production_write_barrier(
        scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
        7,
        cast(intents.PrivateTransactionIntent, object()),
    )
    assert result.state is barrier.PrivateProductionWriteBarrierState.INVALID_REQUEST
    assert not called
