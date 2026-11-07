"""Core #238 Slice 3G46: one-shot guarded synthetic native attempt."""

from __future__ import annotations

import inspect
import os
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_one_shot_disposable_execution as single
from pds_core import _teacher_private_recovery_one_shot_transition_pair as one_shot
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_recovery_transition_registry_custody as native

State = single.PrivateDisposableOneShotState
Fault = single.PrivateDisposableOneShotFault
Step = admission.PrivateScratchWriterStep
Native = native.PrivateRegistryTransitionIdentityState


def _fake_pair(
    monkeypatch: pytest.MonkeyPatch,
    *,
    refuse_entry: bool = False,
    refuse_exit: bool = False,
    native_conflict: bool = False,
    events: list[str] | None = None,
) -> list[str]:
    calls = events if events is not None else []

    @contextmanager
    def held(
        root: Path, tx: str, _owner: object, before_size: int, after_size: int
    ) -> Iterator[one_shot._AttemptWindow]:
        calls.append("enter")
        if refuse_entry:
            raise one_shot._AttemptScopeRefused
        stage = root / ("." + tx + ".registry-stage")
        registry = root / "registry.json"
        assert stage.is_file() and registry.is_file()
        assert registry.stat().st_size == before_size
        assert stage.stat().st_size == after_size

        def check() -> Native:
            calls.append("check")
            if native_conflict:
                return Native.REGISTRY_FOREIGN_PRESERVE
            return (
                Native.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
                if stage.exists()
                else Native.EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED
            )

        window = one_shot._AttemptWindow(check)
        try:
            yield window
        finally:
            calls.append("exit")
            final = window._finish()
            if refuse_exit or not one_shot._terminal_permitted(window.attempted, final):
                raise one_shot._AttemptScopeRefused

    monkeypatch.setattr(one_shot, "_held_one_shot_transition_pair", held)
    return calls


@pytest.mark.parametrize("fault", list(Fault))
def test_one_shot_faults_are_conservative(
    monkeypatch: pytest.MonkeyPatch, fault: Fault
) -> None:
    events = _fake_pair(monkeypatch)
    result = single.rehearse_disposable_one_shot_native_replace(fault=fault)
    assert result.no_automatic_retry
    assert result.production_writes_blocked
    assert result.unqualified_requirements
    assert "non_authorizing=True" in repr(result)
    if fault is Fault.NONE:
        assert result.state is State.DISPOSABLE_REPLACEMENT_OBSERVED_UNQUALIFIED
        assert result.replacement_may_have_occurred
    elif fault in {Fault.AFTER_LOCK, Fault.AFTER_CUSTODY, Fault.BEFORE_ATTEMPT_MARK}:
        assert result.state is State.PRE_ATTEMPT_INTERRUPTED
        assert not result.replacement_may_have_occurred
    else:
        assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
        assert result.replacement_may_have_occurred
    if fault in {
        Fault.NONE,
        Fault.AFTER_CUSTODY,
        Fault.BEFORE_ATTEMPT_MARK,
        Fault.AFTER_ATTEMPT_MARK,
        Fault.AFTER_NATIVE_REPLACE,
        Fault.AFTER_POSTIMAGE,
    }:
        assert "enter" in events and "exit" in events


@pytest.mark.parametrize("invalid", [None, True, 1, 0, "none", {}, object()])
def test_invalid_fault_never_reaches_native_pair(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    events = _fake_pair(monkeypatch)
    result = single.rehearse_disposable_one_shot_native_replace(
        fault=cast(Fault, invalid)
    )
    assert result.state is State.INVALID_REQUEST
    assert not events


@pytest.mark.parametrize("invalid", [None, True, 0, "stage_to_registry", {}, object()])
def test_invalid_step_never_reaches_native_pair(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    events = _fake_pair(monkeypatch)
    result = single.rehearse_disposable_one_shot_native_replace(
        step=cast(Step, invalid)
    )
    assert result.state is State.INVALID_REQUEST
    assert not events


@pytest.mark.parametrize(
    "other", [item for item in Step if item is not Step.STAGE_TO_REGISTRY]
)
def test_other_step_refused(monkeypatch: pytest.MonkeyPatch, other: Step) -> None:
    events = _fake_pair(monkeypatch)
    assert (
        single.rehearse_disposable_one_shot_native_replace(step=other).state
        is State.OPERATION_NOT_ADMITTED
    )
    assert not events


@pytest.mark.parametrize("where", ["entry", "exit", "native"])
def test_scope_and_identity_refusals_never_authorize(
    monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    _fake_pair(
        monkeypatch,
        refuse_entry=where == "entry",
        refuse_exit=where == "exit",
        native_conflict=where == "native",
    )
    result = single.rehearse_disposable_one_shot_native_replace()
    expected = (
        {State.POST_ATTEMPT_UNKNOWN_PRESERVE}
        if where == "exit"
        else {State.NATIVE_CUSTODY_REFUSED, State.NATIVE_PREIMAGE_CHANGED_PRESERVE}
    )
    assert result.state in expected
    assert result.replacement_may_have_occurred is (where == "exit")


def test_native_replace_is_one_attempt_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pair(monkeypatch)
    original = os.replace
    calls: list[tuple[Path, Path]] = []

    def tracked(src: Path, dst: Path) -> None:
        calls.append((src, dst))
        original(src, dst)

    monkeypatch.setattr(os, "replace", tracked)
    outcome = single.rehearse_disposable_one_shot_native_replace()
    assert outcome.state is State.DISPOSABLE_REPLACEMENT_OBSERVED_UNQUALIFIED
    assert len(calls) == 1
    assert calls[0][0].parent == calls[0][1].parent
    assert calls[0][1].name == "registry.json"
    assert calls[0][0].name.endswith(".registry-stage")
    assert not calls[0][0].parent.exists()  # scratch disposed after scope exit


def test_refusal_after_mark_never_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pair(monkeypatch)
    calls = [0]

    def refuse(_src: Path, _dst: Path) -> None:
        calls[0] += 1
        raise PermissionError(13, "injected scratch refusal")

    monkeypatch.setattr(os, "replace", refuse)
    outcome = single.rehearse_disposable_one_shot_native_replace()
    assert calls[0] == 1
    assert outcome.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert outcome.replacement_may_have_occurred
    assert outcome.no_automatic_retry


def test_replace_then_error_is_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pair(monkeypatch)
    original = os.replace
    calls = [0]

    def ambiguous(src: Path, dst: Path) -> None:
        calls[0] += 1
        original(src, dst)
        raise OSError(5, "injected error after rename")

    monkeypatch.setattr(os, "replace", ambiguous)
    outcome = single.rehearse_disposable_one_shot_native_replace()
    assert calls[0] == 1
    assert outcome.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert outcome.replacement_may_have_occurred


def test_native_postimage_conflict_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pair(monkeypatch)
    original = os.replace

    def mutate_after(src: Path, dst: Path) -> None:
        original(src, dst)
        dst.write_bytes(b"unexpected synthetic postimage")

    monkeypatch.setattr(os, "replace", mutate_after)
    outcome = single.rehearse_disposable_one_shot_native_replace()
    assert outcome.state is State.POSTIMAGE_CONFLICT_PRESERVE
    assert outcome.replacement_may_have_occurred


def test_native_preimage_conflict_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pair(monkeypatch)
    original = canonical._exact

    def mismatch(path: Path, image: bytes) -> bool:
        if path.name == "registry.json":
            return False
        return original(path, image)

    monkeypatch.setattr(canonical, "_exact", mismatch)
    outcome = single.rehearse_disposable_one_shot_native_replace()
    assert outcome.state is State.SCRATCH_PREIMAGE_REFUSED
    assert not outcome.replacement_may_have_occurred


def test_result_is_immutable_and_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pair(monkeypatch)
    outcome = single.rehearse_disposable_one_shot_native_replace()
    with pytest.raises(FrozenInstanceError):
        setattr(outcome, "state", State.IO_ERROR)
    assert "core238_3g46" not in repr(outcome)
    assert "registry.json" not in outcome.message


def test_source_has_no_production_mutation_entrypoint() -> None:
    source = inspect.getsource(single)
    assert source.count("os.replace(") == 1
    assert "TemporaryDirectory" in source
    assert "_held_one_shot_transition_pair" in source
    assert "window.mark_attempt()" in source
    assert "rehearse_disposable_one_shot_native_replace" in source
    assert "--repo" not in source
    assert "def commit_" not in source
    assert "activate_notes" not in source


@pytest.mark.skipif(
    sys.platform not in {"win32", "linux"}, reason="Native scratch only"
)
def test_native_scratch_scope_succeeds_or_refuses_protection() -> None:
    """Never mistake an unqualified tempfile ACL/owner context for success."""
    observed = single.rehearse_disposable_one_shot_native_replace()
    assert observed.state in {
        State.DISPOSABLE_REPLACEMENT_OBSERVED_UNQUALIFIED,
        State.NATIVE_CUSTODY_REFUSED,
    }
    assert observed.production_writes_blocked
