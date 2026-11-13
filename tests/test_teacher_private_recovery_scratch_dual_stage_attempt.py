"""Core #238 3G57: one-shot canonical scratch dual-stage native handles."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import (
    _teacher_private_recovery_canonical_native_parent_restart as parents,
)
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as restart
from pds_core import _teacher_private_recovery_scratch_dual_stage_attempt as drill


ST = drill.PrivateScratchDualStageState
F = drill.PrivateScratchDualStageFault
CP = canonical.PrivateCanonicalRestartCheckpoint


def _unavailable(result: drill.PrivateScratchDualStageReview) -> bool:
    return result.state in {
        ST.PARENT_NATIVE_CUSTODY_REFUSED,
        ST.STAGE_NATIVE_CUSTODY_REFUSED,
        ST.PREPARATION_FLUSH_REFUSED_HOLD,
    }


def test_real_scratch_two_stages_retain_native_identity_across_replacements() -> None:
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if _unavailable(result):
        pytest.skip("Native scratch parent/stage or flush unavailable")
    assert result.state is ST.SCRATCH_BOTH_STAGE_IDENTITIES_REOBSERVED_UNQUALIFIED
    assert result.checkpoint is CP.BOTH_AFTER_JOURNAL_PENDING_HOLD
    assert result.journal_seen_at_restart
    assert result.attempted_registry and result.attempted_descriptor
    assert result.phases == (
        "both_stage_file_handles_held",
        "registry_attempt_marked_once",
        "registry_replace_returned",
        "registry_flush_requested",
        "descriptor_attempt_marked_once",
        "descriptor_replace_returned",
        "descriptor_flush_requested",
        "operation_handles_released",
        "fresh_restart_native_parents_held",
    )
    assert result.production_writes_blocked and result.automatic_retry_forbidden
    assert result.automatic_replay_forbidden and result.journal_retirement_forbidden
    assert result.durability_unqualified and result.pending_evidence_must_remain


@pytest.mark.parametrize("invalid", [None, False, 0, "none", object()])
def test_invalid_fault_rejected_before_tempfile(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Invalid request reached scratch storage")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", fail)
    result = drill.rehearse_canonical_dual_stage_one_shot(
        cast(drill.PrivateScratchDualStageFault, invalid)
    )
    assert result.state is ST.INVALID_REQUEST
    assert not result.replacement_may_have_occurred
    assert not result.journal_seen_at_restart


def test_unsupported_os_never_prepares(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = drill.rehearse_canonical_dual_stage_one_shot()
    assert result.state is ST.UNSUPPORTED
    assert not result.attempted_registry and not result.attempted_descriptor


@pytest.mark.parametrize(
    "fault,checkpoint,registry_marked,descriptor_marked",
    [
        (F.AFTER_PREPARED, CP.PREPARED_HOLD, False, False),
        (F.AFTER_REGISTRY_MARK, CP.PREPARED_HOLD, True, False),
        (
            F.AFTER_REGISTRY_REPLACE,
            CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
            True,
            False,
        ),
        (
            F.AFTER_REGISTRY_FLUSH,
            CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
            True,
            False,
        ),
        (
            F.AFTER_DESCRIPTOR_MARK,
            CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD,
            True,
            True,
        ),
        (F.AFTER_DESCRIPTOR_REPLACE, CP.BOTH_AFTER_JOURNAL_PENDING_HOLD, True, True),
        (F.AFTER_DESCRIPTOR_FLUSH, CP.BOTH_AFTER_JOURNAL_PENDING_HOLD, True, True),
        (F.AFTER_RELEASE, CP.BOTH_AFTER_JOURNAL_PENDING_HOLD, True, True),
    ],
)
def test_each_interrupted_boundary_holds_pending_journal(
    fault: drill.PrivateScratchDualStageFault,
    checkpoint: canonical.PrivateCanonicalRestartCheckpoint,
    registry_marked: bool,
    descriptor_marked: bool,
) -> None:
    result = drill.rehearse_canonical_dual_stage_one_shot(fault)
    if _unavailable(result):
        pytest.skip("Native scratch handle or flush unavailable")
    assert result.state is ST.INJECTED_INTERRUPTION_HOLD
    assert result.checkpoint is checkpoint
    assert result.attempted_registry is registry_marked
    assert result.attempted_descriptor is descriptor_marked
    assert result.journal_seen_at_restart
    assert result.automatic_retry_forbidden and result.automatic_replay_forbidden


def test_restart_handle_interruption_overrides_after_images() -> None:
    result = drill.rehearse_canonical_dual_stage_one_shot(F.AFTER_RESTART_HANDLES)
    if _unavailable(result):
        pytest.skip("Native scratch handle or flush unavailable")
    assert result.state is ST.INJECTED_INTERRUPTION_HOLD
    assert result.checkpoint is CP.OBSERVATION_REFUSED
    assert not result.journal_seen_at_restart
    assert result.attempted_registry and result.attempted_descriptor


def test_linux_retained_stage_file_identity_moves_to_destination(
    tmp_path: Path,
) -> None:
    if sys.platform != "linux":
        pytest.skip("POSIX native stat/dirfd test")
    stage = tmp_path / ".stage"
    destination = tmp_path / "target"
    stage.write_bytes(b"after-stage-image")
    destination.write_bytes(b"before-image")
    with drill._hold_stage(stage, b"after-stage-image") as retained:
        assert retained.check_prepared()
        os.replace(stage, destination)
        assert retained.check_installed(destination)
        assert not retained.check_prepared()
        assert retained.check_retained()


def test_retained_stage_refuses_wrong_bytes(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.write_bytes(b"unrelated-image")
    with pytest.raises(drill._StageRefused):
        with drill._hold_stage(stage, b"expected-image"):
            pytest.fail("Unqualified native stage handle was exposed")


def test_retained_stage_refuses_missing_path(tmp_path: Path) -> None:
    with pytest.raises(drill._StageRefused):
        with drill._hold_stage(tmp_path / "missing", b"expected"):
            pytest.fail("Missing stage was treated as prepared")


def test_retained_stage_refuses_symlink(tmp_path: Path) -> None:
    original = tmp_path / "real"
    original.write_bytes(b"expected")
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("Native symlink creation not permitted")
    with pytest.raises(drill._StageRefused):
        with drill._hold_stage(alias, b"expected"):
            pytest.fail("Alias stage was admitted")


def test_retained_stage_rejects_foreign_destination(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("POSIX native stat/dirfd test")
    stage = tmp_path / "stage"
    dest = tmp_path / "destination"
    stage.write_bytes(b"expected")
    dest.write_bytes(b"other")
    with pytest.raises(drill._StageChanged):
        with drill._hold_stage(stage, b"expected") as held:
            assert not held.check_installed(dest)
            stage.unlink()
            assert not held.check_installed(dest)
            assert not held.check_retained()


def test_prepared_image_changed_in_place_refused(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("POSIX retained-inode mutation test")
    stage = tmp_path / "stage"
    stage.write_bytes(b"expected")
    with drill._hold_stage(stage, b"expected") as held:
        assert held.check_prepared()
        stage.write_bytes(b"changed!")
        assert not held.check_prepared()
        assert held.check_retained()  # Identity alone is insufficient.


def test_native_stage_refuses_hardlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"expected")
    stage = tmp_path / "stage"
    try:
        os.link(source, stage)
    except OSError:
        pytest.skip("Hardlink creation not allowed")
    with pytest.raises(drill._StageRefused):
        with drill._hold_stage(stage, b"expected"):
            pytest.fail("Multi-linked stage was admitted")


def test_native_stage_refuses_wrong_size(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.write_bytes(b"expected plus trailing data")
    with pytest.raises(drill._StageRefused):
        with drill._hold_stage(stage, b"expected"):
            pytest.fail("Wrong native image size was admitted")


def test_native_stage_acquisition_refusal_prevents_any_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def reject(_path: Path, _expected: bytes) -> Iterator[drill._NativeStage]:
        raise drill._StageRefused
        yield  # pragma: no cover

    def forbidden(_source: Path, _dest: Path) -> None:
        pytest.fail("No replacement permitted after native stage refusal")

    monkeypatch.setattr(drill, "_hold_stage", reject)
    monkeypatch.setattr(os, "replace", forbidden)
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if result.state is ST.PARENT_NATIVE_CUSTODY_REFUSED:
        pytest.skip("Native scratch parent unavailable")
    assert result.state is ST.STAGE_NATIVE_CUSTODY_REFUSED
    assert not result.attempted_registry


def test_first_replace_failure_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def refuse(_source: Path, _dest: Path) -> None:
        nonlocal calls
        calls += 1
        raise PermissionError("disposable replacement refused")

    monkeypatch.setattr(os, "replace", refuse)
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if _unavailable(result):
        pytest.skip("Native scratch handle or flush unavailable")
    assert calls == 1
    assert result.state is ST.REPLACEMENT_OUTCOME_UNKNOWN_HOLD
    assert result.checkpoint is CP.PREPARED_HOLD
    assert result.journal_seen_at_restart
    assert result.attempted_registry and not result.attempted_descriptor


def test_second_replace_failure_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    actual = os.replace
    calls = 0

    def second(source: Path, dest: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("second disposable replacement refused")
        actual(source, dest)

    monkeypatch.setattr(os, "replace", second)
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if _unavailable(result):
        pytest.skip("Native scratch handle or flush unavailable")
    assert calls == 2
    assert result.state is ST.REPLACEMENT_OUTCOME_UNKNOWN_HOLD
    assert result.checkpoint is CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
    assert result.attempted_registry and result.attempted_descriptor
    assert result.journal_seen_at_restart


def test_flush_failure_never_reaches_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_path: Path) -> None:
        raise durable._DirectoryFlushRefused

    monkeypatch.setattr(durable, "_directory_flush", refuse)
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if result.state is ST.PARENT_NATIVE_CUSTODY_REFUSED:
        pytest.skip("Native scratch parent unavailable")
    assert result.state is ST.PREPARATION_FLUSH_REFUSED_HOLD
    assert result.checkpoint is CP.PREPARED_HOLD
    assert result.journal_seen_at_restart
    assert not result.replacement_may_have_occurred


def test_restart_lock_refusal_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def refuse(_path: Path) -> Iterator[None]:
        raise restart._RestartGuardRefused
        yield  # pragma: no cover

    monkeypatch.setattr(restart, "_held_existing_restart_lock", refuse)
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if _unavailable(result):
        pytest.skip("Native scratch handle or flush unavailable")
    assert result.state is ST.RESTART_GUARD_REFUSED
    assert not result.journal_seen_at_restart
    assert result.automatic_retry_forbidden


def test_restart_parent_refusal_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    real = parents._hold_four_parents
    calls = 0

    @contextmanager
    def reject_on_restart(
        paths: tuple[Path, ...],
    ) -> Iterator[tuple[parents._Check, ...]]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise parents._ParentDrift
        with real(paths) as checks:
            yield checks

    monkeypatch.setattr(parents, "_hold_four_parents", reject_on_restart)
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if _unavailable(result):
        pytest.skip("Native scratch handle or flush unavailable")
    assert calls == 2
    assert result.state is ST.RESTART_NATIVE_PARENT_REFUSED
    assert not result.journal_seen_at_restart


def test_conflicting_journal_cannot_be_claimed_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = durable._exact

    def refuse_journal(path: Path, image: bytes) -> bool:
        if path.parent.name == "transactions":
            return False
        return real(path, image)

    monkeypatch.setattr(durable, "_exact", refuse_journal)
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if _unavailable(result):
        pytest.skip("Native scratch handle or flush unavailable")
    assert result.state is ST.CANONICAL_CHECKPOINT_CONFLICT_PRESERVE
    assert result.automatic_replay_forbidden
    assert result.journal_retirement_forbidden


def test_no_public_mutation_or_retry_token() -> None:
    signature = inspect.signature(drill.rehearse_canonical_dual_stage_one_shot)
    assert tuple(signature.parameters) == ("interruption",)
    review = drill._result(ST.SCRATCH_BOTH_STAGE_IDENTITIES_REOBSERVED_UNQUALIFIED)
    assert not hasattr(review, "commit")
    assert not hasattr(review, "retry")
    assert not hasattr(review, "path")
    assert review.production_writes_blocked and review.durability_unqualified
    assert review.journal_retirement_forbidden
    assert "non_authorizing" in repr(review)
