"""Core #238 Slice 3G34: canonical intent drives disposable two-root replacement."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_recovery_synthetic_two_root_replace as two
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness

State = canonical.PrivateCanonicalReplaceState
Fault = canonical.PrivateCanonicalReplaceFault
Step = admission.PrivateScratchWriterStep


def _run(
    *,
    step: Step = Step.STAGE_TO_REGISTRY,
    interruption: Fault = Fault.NONE,
) -> canonical.PrivateCanonicalReplaceReview:
    return canonical.rehearse_synthetic_canonical_two_root_replace(step, interruption)


def test_fixed_canonical_intent_roundtrip_and_revision() -> None:
    checked = canonical._canonical()
    raw = intents.encode_private_transaction_intent(checked)
    assert intents.decode_private_transaction_intent(raw) == checked
    assert checked.witness.operation is witness.PrivateBindingOperation.REBIND_MOVE
    assert (
        checked.witness.registry_revision_before,
        checked.witness.registry_revision_after,
    ) == (2, 3)
    assert checked.descriptor_before == checked.descriptor_after
    assert (
        metadata.decode_private_registry(checked.registry_before or b"").revision == 2
    )
    assert metadata.decode_private_registry(checked.registry_after).revision == 3
    result = prepared.describe_private_prepared_stage_write_intent(
        Step.STAGE_TO_REGISTRY, 2, checked
    )
    assert (
        result.state
        is prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
    )
    assert result.description is not None
    assert result.description.pending_intent_sha256 == canonical._sha(raw)


def test_single_real_scratch_replace_succeeds_on_supported_native_os() -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )
    review = _run()
    assert review.state is State.SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED
    assert review.message == canonical._MESSAGES[review.state]
    assert "non_authorizing=True" in repr(review)
    for field in (
        "path",
        "root",
        "bytes",
        "handle",
        "intent",
        "token",
        "permit",
        "writer",
    ):
        assert not hasattr(review, field)
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.IO_ERROR)


@pytest.mark.parametrize("fault", [item for item in Fault if item is not Fault.NONE])
def test_all_interruption_points_fail_closed(fault: Fault) -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )
    assert _run(interruption=fault).state is State.INTERRUPTED_PRESERVE


@pytest.mark.parametrize(
    "step", [value for value in Step if value is not Step.STAGE_TO_REGISTRY]
)
def test_only_one_bounded_step_supported(step: Step) -> None:
    assert _run(step=step).state is State.OPERATION_NOT_ADMITTED


@pytest.mark.parametrize("value", [None, 0, False, "stage_to_registry", object(), {}])
def test_invalid_operation_refused_before_scratch(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_scratch(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Unexpected scratch setup")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", no_scratch)
    assert _run(step=cast(Step, value)).state is State.INVALID_REQUEST


@pytest.mark.parametrize("value", [None, 1, True, "after_lock", object(), {}])
def test_invalid_fault_refused_before_scratch(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_scratch(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Unexpected scratch setup")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", no_scratch)
    assert _run(interruption=cast(Fault, value)).state is State.INVALID_REQUEST


def test_unsupported_platform_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _run().state is State.UNSUPPORTED


def test_native_replace_called_only_with_module_owned_two_root_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )
    replace_native = os.replace
    replacements: list[tuple[Path, Path]] = []

    def observe(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        source, target = Path(src), Path(dst)
        replacements.append((source, target))
        assert source.parent == target.parent
        assert source.name == scratch._STAGE
        assert target.name == scratch._REGISTRY
        assert source.parent.name == "private"
        assert source.parent.parent.name.startswith("core238_3g34_canonical_")
        replace_native(src, dst)

    monkeypatch.setattr(os, "replace", observe)
    assert _run().state is State.SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED
    assert len(replacements) == 1
    assert not replacements[0][0].exists()  # TemporaryDirectory cleaned after guard


def test_deny_canonical_description_before_creating_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prepared,
        "describe_private_prepared_stage_write_intent",
        lambda *_args: prepared.PrivatePreparedWriteIntentReview(
            prepared.PrivatePreparedWriteIntentState.NONCANONICAL_INTENT_REFUSED,
            "synthetic refusal",
            None,
        ),
    )
    assert _run().state is State.CANONICAL_INTENT_REFUSED


def test_reader_refusal_blocks_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )
    monkeypatch.setattr(canonical, "_reader", lambda *_: False)
    assert _run().state is State.READER_CONFLICT_PRESERVE


def test_preimage_drift_blocks_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )
    original = canonical._observe
    count = [0]

    def changed(
        paths: two._Paths,
        checked: intents.PrivateTransactionIntent,
        raw: bytes,
        *,
        stage: bool,
    ) -> canonical._Census:
        count[0] += 1
        snapshot = original(paths, checked, raw, stage=stage)
        return replace(snapshot, registry=(99, 999)) if count[0] == 2 else snapshot

    monkeypatch.setattr(canonical, "_observe", changed)
    assert _run().state is State.ADMISSION_DRIFT_PRESERVE


def test_native_replacement_refusal_preserves(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )

    def deny(*_args: object) -> None:
        raise PermissionError("synthetic deny")

    monkeypatch.setattr(os, "replace", deny)
    assert _run().state is State.REPLACEMENT_REFUSED_PRESERVE


def test_postimage_conflict_preserves(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )
    monkeypatch.setattr(canonical, "_post", lambda *_: False)
    assert _run().state is State.POSTIMAGE_CONFLICT_PRESERVE


def test_lock_failure_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip(
            "Native two-root scratch custody only qualified on Linux or Windows"
        )
    from contextlib import contextmanager
    from collections.abc import Iterator

    @contextmanager
    def deny(_path: Path) -> Iterator[None]:
        raise scratch._GuardRefused
        yield

    monkeypatch.setattr(scratch, "_scratch_lock", deny)
    assert _run().state is State.GUARD_REFUSED


@pytest.mark.parametrize("status", list(State))
def test_fixed_status_messages_and_no_secret_leaks(status: State) -> None:
    review = canonical._result(status)
    assert review.message == canonical._MESSAGES[status]
    assert "C:\\" not in review.message
    assert "/tmp" not in review.message
    assert "/synthetic" not in review.message
    assert "6fb32a" not in repr(review)
    assert not hasattr(review, "path")


def test_surface_has_no_paths_or_writer_permit() -> None:
    signature = inspect.signature(
        canonical.rehearse_synthetic_canonical_two_root_replace
    )
    assert set(signature.parameters) == {"step", "interruption"}
    for name in (
        "write_private_registry",
        "commit_private_recovery",
        "retire_private_journal",
    ):
        assert not hasattr(canonical, name)
    assert "TemporaryDirectory" in inspect.getsource(canonical)
    assert "os.replace(" in inspect.getsource(canonical)
