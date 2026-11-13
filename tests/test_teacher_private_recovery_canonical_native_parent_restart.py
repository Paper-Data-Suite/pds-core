"""#238 Slice 3G53: canonical scratch transaction under four native parent handles."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import _teacher_private_recovery_canonical_native_parent_restart as drill
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as restart
from pds_core import _teacher_private_recovery_synthetic_owned_scope as owned


_ST = drill.PrivateCanonicalNativeParentState
_CP = canonical.PrivateCanonicalRestartCheckpoint
_F = drill.PrivateCanonicalNativeParentFault


def _unavailable(result: drill.PrivateCanonicalNativeParentReview) -> bool:
    return result.state in {
        _ST.FLUSH_REFUSED_HOLD,
        _ST.OPERATION_NATIVE_PARENT_REFUSED,
    }


def test_real_native_parents_retain_canonical_fork_replacements() -> None:
    result = drill.rehearse_canonical_native_parent_restart()
    if _unavailable(result):
        pytest.skip("Native scratch handle or directory-flush capability unavailable")
    assert result.state is _ST.SCRATCH_NATIVE_CUSTODY_RESTART_UNQUALIFIED
    assert result.checkpoint is _CP.BOTH_AFTER_JOURNAL_PENDING_HOLD
    assert result.journal_seen_at_restart
    assert result.replacement_may_have_occurred
    assert result.phases == (
        "four_native_parents_held",
        "prepared_images_and_parents_flushed",
        "registry_replaced",
        "registry_flush_requested",
        "descriptor_replaced",
        "descriptor_flush_requested",
        "operation_handles_released",
        "fresh_restart_native_parents_held",
    )


@pytest.mark.parametrize("bad", [None, False, 0, "none", object()])
def test_invalid_request_never_creates_scratch(
    bad: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Invalid request entered filesystem")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", fail)
    result = drill.rehearse_canonical_native_parent_restart(bad)  # type: ignore[arg-type]
    assert result.state is _ST.INVALID_REQUEST
    assert not result.replacement_may_have_occurred
    assert result.production_writes_blocked


def test_unsupported_platform_has_zero_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = drill.rehearse_canonical_native_parent_restart()
    assert result.state is _ST.UNSUPPORTED
    assert not result.replacement_may_have_occurred


@pytest.mark.parametrize(
    "fault,checkpoint,attempted",
    [
        (_F.AFTER_PARENTS_RETAINED, _CP.PREPARED_HOLD, False),
        (_F.AFTER_PREPARED_FLUSH, _CP.PREPARED_HOLD, False),
        (_F.AFTER_REGISTRY_REPLACE, _CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD, True),
        (_F.AFTER_REGISTRY_FLUSH, _CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD, True),
        (_F.AFTER_DESCRIPTOR_REPLACE, _CP.BOTH_AFTER_JOURNAL_PENDING_HOLD, True),
        (_F.AFTER_DESCRIPTOR_FLUSH, _CP.BOTH_AFTER_JOURNAL_PENDING_HOLD, True),
        (_F.AFTER_OPERATION_RELEASE, _CP.BOTH_AFTER_JOURNAL_PENDING_HOLD, True),
    ],
)
def test_interruption_keeps_journal_and_fresh_restart(
    fault: drill.PrivateCanonicalNativeParentFault,
    checkpoint: canonical.PrivateCanonicalRestartCheckpoint,
    attempted: bool,
) -> None:
    result = drill.rehearse_canonical_native_parent_restart(fault)
    if _unavailable(result):
        pytest.skip("Native scratch handle or directory-flush capability unavailable")
    if fault is _F.AFTER_PARENTS_RETAINED:
        # This injected interruption occurs *before* scratch files are written.
        assert result.state is _ST.CANONICAL_IMAGE_CONFLICT_PRESERVE
        assert not result.journal_seen_at_restart
        return
    assert result.state is _ST.INJECTED_INTERRUPTION_HOLD
    assert result.checkpoint is checkpoint
    assert result.replacement_may_have_occurred is attempted
    assert result.journal_seen_at_restart
    assert result.automatic_replay_forbidden


def test_restart_parent_interruption_fails_closed() -> None:
    result = drill.rehearse_canonical_native_parent_restart(
        _F.AFTER_RESTART_PARENTS_RETAINED
    )
    if _unavailable(result):
        pytest.skip("Native scratch handle or directory-flush capability unavailable")
    assert result.state is _ST.INJECTED_INTERRUPTION_HOLD
    assert result.checkpoint is _CP.OBSERVATION_REFUSED
    assert not result.journal_seen_at_restart
    assert result.replacement_may_have_occurred


def test_distinct_four_parent_roots(tmp_path: Path) -> None:
    private = tmp_path / "private"
    association = tmp_path / "workspace" / ".pds"
    assert drill._parent_roots(private, association) == (
        private,
        private / "transactions",
        tmp_path / "workspace",
        association,
    )


@pytest.mark.parametrize("checks", [(), (lambda: True,), (lambda: False,) * 4])
def test_refuse_missing_or_changed_handle_census(checks: tuple[object, ...]) -> None:
    assert not drill._still_held(checks)  # type: ignore[arg-type]


def test_holding_scope_refuses_false_native_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def fake(_path: Path) -> Iterator[object]:
        yield lambda: False

    monkeypatch.setattr(owned, "_held_native_parent", fake)
    with pytest.raises(drill._ParentDrift):
        with drill._hold_four_parents(
            (
                tmp_path / "a",
                tmp_path / "b",
                tmp_path / "c",
                tmp_path / "d",
            )
        ):
            pytest.fail("Invalid native handle was exposed")


def test_release_drift_is_not_a_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    counter = 0

    @contextmanager
    def fake(_path: Path) -> Iterator[object]:
        def check() -> bool:
            nonlocal counter
            counter += 1
            return counter <= 7

        yield check

    monkeypatch.setattr(owned, "_held_native_parent", fake)
    with pytest.raises(drill._ParentDrift):
        with drill._hold_four_parents(
            (
                tmp_path / "a",
                tmp_path / "b",
                tmp_path / "c",
                tmp_path / "d",
            )
        ):
            pass


def test_native_parent_acquisition_refusal_does_not_attempt_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def refuse(_path: Path) -> Iterator[object]:
        raise owned._ParentUnqualified
        yield  # pragma: no cover

    def replace(_source: Path, _target: Path) -> None:
        pytest.fail("Native replacement reached despite refused parent handle")

    monkeypatch.setattr(owned, "_held_native_parent", refuse)
    monkeypatch.setattr(os, "replace", replace)
    result = drill.rehearse_canonical_native_parent_restart()
    assert result.state in {
        _ST.OPERATION_NATIVE_PARENT_REFUSED,
        _ST.RESTART_NATIVE_PARENT_REFUSED,
    }
    assert not result.replacement_may_have_occurred
    assert result.production_writes_blocked


def test_first_native_replace_refusal_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path]] = []

    def refuse(source: Path, target: Path) -> None:
        calls.append((source, target))
        raise PermissionError("injected scratch refusal")

    monkeypatch.setattr(os, "replace", refuse)
    result = drill.rehearse_canonical_native_parent_restart()
    if _unavailable(result):
        pytest.skip("Native scratch handle or directory-flush capability unavailable")
    assert len(calls) == 1
    assert result.state is _ST.REPLACE_OUTCOME_UNKNOWN_HOLD
    assert result.checkpoint is _CP.PREPARED_HOLD
    assert result.journal_seen_at_restart
    assert result.automatic_replay_forbidden


def test_second_native_replace_refusal_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_replace = os.replace
    calls = 0

    def refuse_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("second scratch rename refused")
        original_replace(source, target)

    monkeypatch.setattr(os, "replace", refuse_second)
    result = drill.rehearse_canonical_native_parent_restart()
    if _unavailable(result):
        pytest.skip("Native scratch handle or directory-flush capability unavailable")
    assert calls == 2
    assert result.state is _ST.REPLACE_OUTCOME_UNKNOWN_HOLD
    assert result.checkpoint is _CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
    assert result.journal_seen_at_restart


def test_prepared_directory_flush_refusal_never_upgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_path: Path) -> None:
        raise durable._DirectoryFlushRefused

    monkeypatch.setattr(durable, "_directory_flush", refuse)
    result = drill.rehearse_canonical_native_parent_restart()
    if result.state is _ST.OPERATION_NATIVE_PARENT_REFUSED:
        pytest.skip("Native parent unavailable")
    assert result.state is _ST.FLUSH_REFUSED_HOLD
    assert result.checkpoint is _CP.PREPARED_HOLD
    assert result.journal_seen_at_restart
    assert not result.replacement_may_have_occurred


def test_restart_lock_failure_overrides_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def refuse(_path: Path) -> Iterator[None]:
        raise restart._RestartGuardRefused
        yield  # pragma: no cover

    monkeypatch.setattr(restart, "_held_existing_restart_lock", refuse)
    result = drill.rehearse_canonical_native_parent_restart()
    if _unavailable(result):
        pytest.skip("Native parent or flush unavailable")
    assert result.state is _ST.RESTART_GUARD_REFUSED
    assert not result.journal_seen_at_restart
    assert result.automatic_replay_forbidden


def test_native_restart_parent_failure_overrides_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = drill._hold_four_parents
    calls = 0

    @contextmanager
    def refuse_fresh(roots: tuple[Path, ...]) -> Iterator[tuple[drill._Check, ...]]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise drill._ParentDrift
        with original(roots) as held:
            yield held

    monkeypatch.setattr(drill, "_hold_four_parents", refuse_fresh)
    result = drill.rehearse_canonical_native_parent_restart()
    if _unavailable(result):
        pytest.skip("Native parent or flush unavailable")
    assert calls == 2
    assert result.state is _ST.RESTART_NATIVE_PARENT_REFUSED
    assert not result.journal_seen_at_restart
    assert result.automatic_replay_forbidden


def test_after_image_conflict_is_not_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    original = canonical._checkpoint
    checks = 0

    def corrupt_fresh(
        private: Path,
        association: Path,
        checked: object,
    ) -> canonical.PrivateCanonicalRestartCheckpoint:
        nonlocal checks
        checks += 1
        if checks >= 6:
            return _CP.CONFLICT_PRESERVE
        return original(private, association, checked)  # type: ignore[arg-type]

    monkeypatch.setattr(canonical, "_checkpoint", corrupt_fresh)
    result = drill.rehearse_canonical_native_parent_restart()
    if _unavailable(result):
        pytest.skip("Native parent or flush unavailable")
    assert result.state is _ST.CANONICAL_IMAGE_CONFLICT_PRESERVE
    assert result.automatic_replay_forbidden
    assert result.journal_retirement_forbidden


def test_no_external_path_or_write_capability() -> None:
    signature = inspect.signature(drill.rehearse_canonical_native_parent_restart)
    assert tuple(signature.parameters) == ("interruption",)
    review = drill._result(_ST.SCRATCH_NATIVE_CUSTODY_RESTART_UNQUALIFIED)
    assert review.pending_evidence_must_remain
    assert review.production_writes_blocked
    assert review.journal_retirement_forbidden
    assert review.durability_unqualified
    assert not hasattr(review, "commit")
    assert not hasattr(review, "retire")
    assert not hasattr(review, "write")
    assert "private" not in repr(review)
