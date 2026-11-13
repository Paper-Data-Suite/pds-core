"""Core #238 3G35: production write remains denied after canonical scratch 3G34."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = barrier.PrivateProductionWriteBarrierState
Step = scratch.PrivateScratchWriterStep
Requirement = barrier.PrivateProductionWriteRequirement


def _intent() -> intents.PrivateTransactionIntent:
    # Synthetic instance: this suite exercises the admission boundary and
    # independently stubs the already-qualified 3G32 pure codec.
    return object.__new__(intents.PrivateTransactionIntent)


def _description(
    step: Step = Step.STAGE_TO_REGISTRY, revision: int = 7
) -> prepared.PrivatePreparedWriteDescription:
    return prepared.PrivatePreparedWriteDescription(
        step=step,
        binding_operation=witness.PrivateBindingOperation.REBIND_MOVE,
        expected_revision=revision,
        resulting_revision=revision + 1,
        transaction_id="11111111-1111-4111-8111-111111111111",
        pending_intent_sha256="1" * 64,
        registry_before_sha256="2" * 64,
        staged_registry_sha256="3" * 64,
        descriptor_before_sha256="4" * 64,
        descriptor_after_sha256="5" * 64,
    )


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    state: prepared.PrivatePreparedWriteIntentState = (
        prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
    ),
    description: prepared.PrivatePreparedWriteDescription | None = None,
) -> list[tuple[object, object, object]]:
    calls: list[tuple[object, object, object]] = []

    def reviewed(
        step: object, revision: object, proposed: object
    ) -> prepared.PrivatePreparedWriteIntentReview:
        calls.append((step, revision, proposed))
        return prepared.PrivatePreparedWriteIntentReview(
            state,
            "only synthetic metadata",
            _description()
            if description is None
            and state
            is prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
            else description,
        )

    monkeypatch.setattr(
        prepared, "describe_private_prepared_stage_write_intent", reviewed
    )
    return calls


def _review(
    intent: intents.PrivateTransactionIntent,
    step: Step = Step.STAGE_TO_REGISTRY,
    revision: int = 7,
) -> barrier.PrivateProductionWriteBarrierReview:
    return barrier.review_private_production_write_barrier(step, revision, intent)


def test_matching_description_is_still_production_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _setup(monkeypatch)
    value = _intent()
    review = _review(value)
    assert review.state is State.PRODUCTION_BLOCKED
    assert calls == [(Step.STAGE_TO_REGISTRY, 7, value)]
    assert review.unqualified_requirements == tuple(Requirement)
    assert len(review.unqualified_requirements) == 9
    assert not any(
        hasattr(review, item)
        for item in (
            "permit",
            "handle",
            "path",
            "write",
            "token",
            "approved",
            "execute",
        )
    )
    assert repr(review) == "PrivateProductionWriteBarrierReview(non_authorizing=True)"
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.INVALID_REQUEST)


@pytest.mark.parametrize("invalid", [None, True, 0, -1, 7.0, "7", {}, object()])
def test_invalid_revision_never_reaches_description(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    calls = _setup(monkeypatch)
    assert (
        _review(_intent(), revision=cast(int, invalid)).state is State.INVALID_REQUEST
    )
    assert calls == []


@pytest.mark.parametrize("invalid", [None, False, 0, "stage_to_registry", {}, object()])
def test_invalid_step_never_reaches_description(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    calls = _setup(monkeypatch)
    assert _review(_intent(), step=cast(Step, invalid)).state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize(
    "step", [entry for entry in Step if entry is not Step.STAGE_TO_REGISTRY]
)
def test_other_operations_refused_before_description(
    monkeypatch: pytest.MonkeyPatch, step: Step
) -> None:
    calls = _setup(monkeypatch)
    assert _review(_intent(), step=step).state is State.OPERATION_NOT_ADMITTED
    assert calls == []


@pytest.mark.parametrize("invalid", [None, False, 0, {}, [], object(), "intent"])
def test_invalid_intent_never_reaches_description(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    calls = _setup(monkeypatch)
    assert (
        _review(cast(intents.PrivateTransactionIntent, invalid)).state
        is State.INVALID_REQUEST
    )
    assert calls == []


@pytest.mark.parametrize(
    "source,target",
    [
        (
            prepared.PrivatePreparedWriteIntentState.INVALID_REQUEST,
            State.INVALID_REQUEST,
        ),
        (
            prepared.PrivatePreparedWriteIntentState.OPERATION_NOT_ADMITTED,
            State.OPERATION_NOT_ADMITTED,
        ),
        (
            prepared.PrivatePreparedWriteIntentState.INITIALIZATION_REFUSED,
            State.INITIALIZATION_REFUSED,
        ),
        (
            prepared.PrivatePreparedWriteIntentState.REVISION_MISMATCH_REFUSED,
            State.REVISION_MISMATCH_REFUSED,
        ),
        (
            prepared.PrivatePreparedWriteIntentState.NONCANONICAL_INTENT_REFUSED,
            State.NONCANONICAL_INTENT_REFUSED,
        ),
        (
            prepared.PrivatePreparedWriteIntentState.IO_ERROR,
            State.DESCRIPTION_UNQUALIFIED,
        ),
    ],
)
def test_refusals_are_preserved_without_authorizing(
    monkeypatch: pytest.MonkeyPatch,
    source: prepared.PrivatePreparedWriteIntentState,
    target: State,
) -> None:
    _setup(monkeypatch, state=source)
    assert _review(_intent()).state is target


@pytest.mark.parametrize(
    "description",
    [
        None,
        _description(revision=8),
        _description(step=Step.DESCRIPTOR_COMPLETION),
    ],
)
def test_malformed_or_other_description_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    description: prepared.PrivatePreparedWriteDescription | None,
) -> None:
    calls = _setup(monkeypatch, description=description)
    if description is None:
        # Force an invalid positive result with no description, not default fixture.
        monkeypatch.setattr(
            prepared,
            "describe_private_prepared_stage_write_intent",
            lambda *_: prepared.PrivatePreparedWriteIntentReview(
                prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED,
                "synthetic",
                None,
            ),
        )
    assert _review(_intent()).state is State.DESCRIPTION_UNQUALIFIED
    assert len(calls) == (0 if description is None else 1)


@pytest.mark.parametrize(
    "exception",
    [
        OSError(),
        ValueError(),
        TypeError(),
        AttributeError(),
        OverflowError(),
        KeyboardInterrupt(),
    ],
)
def test_description_exception_fails_closed(
    monkeypatch: pytest.MonkeyPatch, exception: BaseException
) -> None:
    def boom(*_args: object) -> object:
        raise exception

    monkeypatch.setattr(prepared, "describe_private_prepared_stage_write_intent", boom)
    assert _review(_intent()).state is State.DESCRIPTION_UNQUALIFIED


def test_malformed_response_type_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        prepared,
        "describe_private_prepared_stage_write_intent",
        lambda *_: _description(),
    )
    assert _review(_intent()).state is State.DESCRIPTION_UNQUALIFIED


def test_no_positive_or_transferable_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(monkeypatch)
    result = _review(_intent())
    assert {entry for entry in State if entry.name.startswith("PRODUCTION_")} == {
        State.PRODUCTION_BLOCKED
    }
    assert "ready" not in {entry.name.lower() for entry in State}
    assert not any(
        name in {item.name for item in fields(result)}
        for name in (
            "authorized",
            "permit",
            "token",
            "path",
            "callback",
            "guard",
            "native_handle",
        )
    )
    assert (
        len(
            inspect.signature(
                barrier.review_private_production_write_barrier
            ).parameters
        )
        == 3
    )
    assert not any(
        hasattr(barrier, symbol)
        for symbol in (
            "commit_registry",
            "write_intent",
            "execute_private_writer",
            "allow_production_writer",
        )
    )


@pytest.mark.parametrize("state", list(State))
def test_messages_are_static_and_private_metadata_free(state: State) -> None:
    result = barrier._result(state)
    assert result.state is state
    assert all(item in result.unqualified_requirements for item in Requirement)
    assert not any(
        fragment in result.message
        for fragment in (
            "C:",
            "/tmp/",
            "teacher-synthetic",
            "11111111",
            "registry.json",
        )
    )


def test_source_has_no_filesystem_or_mutation_primitives() -> None:
    source = inspect.getsource(barrier)
    for fragment in (
        "os.replace(",
        "os.open(",
        "Path(",
        ".open(",
        "unlink(",
        "fsync(",
        "TemporaryDirectory(",
        "_hold_existing_retained_descriptor_guard(",
    ):
        assert fragment not in source


def test_import_has_no_filesystem_side_effects(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    before = tuple(tmp_path.iterdir())
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import pds_core._teacher_private_recovery_production_write_barrier",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert tuple(tmp_path.iterdir()) == before
