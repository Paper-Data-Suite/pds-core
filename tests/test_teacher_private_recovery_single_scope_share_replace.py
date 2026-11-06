"""Core #238 3G40: held share-safe handles + synthetic canonical replacement."""

from __future__ import annotations

import inspect
import os
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import BinaryIO, Iterator

import pytest

from pds_core import _teacher_private_recovery_single_scope_share_replace as single
from pds_core import _teacher_private_recovery_synthetic_canonical_replace as canonical
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_recovery_synthetic_windows_share as sharing
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_recovery_synthetic_two_root_replace as two

State = single.PrivateSingleScopeReplaceState
Fault = single.PrivateSingleScopeReplaceFault
Step = admission.PrivateScratchWriterStep


@pytest.mark.parametrize(
    "step", [None, "stage_to_registry", 0, False, object(), Step.INITIALIZE.value]
)
def test_invalid_step_is_refused(step: object) -> None:
    review = single.rehearse_synthetic_share_safe_single_scope_replace(step)  # type: ignore[arg-type]
    assert review.state is State.INVALID_REQUEST
    assert not review.replacement_may_have_occurred
    assert review.pending_evidence_must_remain


@pytest.mark.parametrize("fault", [None, "none", 1, True, object()])
def test_invalid_fault_is_refused(fault: object) -> None:
    review = single.rehearse_synthetic_share_safe_single_scope_replace(
        Step.STAGE_TO_REGISTRY,
        fault,  # type: ignore[arg-type]
    )
    assert review.state is State.INVALID_REQUEST


@pytest.mark.parametrize(
    "step", [Step.INITIALIZE, Step.DESCRIPTOR_COMPLETION, Step.JOURNAL_RETIREMENT]
)
def test_non_stage_operation_is_refused(step: Step) -> None:
    result = single.rehearse_synthetic_share_safe_single_scope_replace(step)
    assert result.state is State.OPERATION_NOT_ADMITTED
    assert result.pending_evidence_must_remain


@pytest.mark.parametrize("fault", list(Fault))
def test_disposable_rehearsal_is_fail_closed_across_injections(fault: Fault) -> None:
    result = single.rehearse_synthetic_share_safe_single_scope_replace(
        interruption=fault
    )
    assert type(result) is single.PrivateSingleScopeReplaceReview
    assert type(result.state) is State
    assert result.pending_evidence_must_remain is True
    assert result.unqualified_requirements == barrier._REQUIRED
    assert "non_authorizing" in repr(result)
    assert "private" not in result.message.lower() or "writer" in result.message.lower()
    if sys.platform == "linux":
        if fault is Fault.NONE:
            assert result.state is State.SCRATCH_SHARE_SAFE_REPLACEMENT_UNQUALIFIED
            assert result.replacement_may_have_occurred
        elif fault is Fault.AFTER_GUARD_RELEASE:
            assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
        elif fault.value.startswith("after_replace") or fault in {
            Fault.AFTER_POSTIMAGE,
            Fault.AFTER_FILE_SYNC,
        }:
            assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
            assert result.replacement_may_have_occurred
        else:
            assert result.state is State.PRE_ATTEMPT_INTERRUPTED_PRESERVE
            assert not result.replacement_may_have_occurred
    elif sys.platform == "win32":
        # A real Windows sharing refusal is a permitted outcome, NOT a retry.
        if fault is Fault.NONE:
            assert result.state in {
                State.SCRATCH_SHARE_SAFE_REPLACEMENT_UNQUALIFIED,
                State.NATIVE_REPLACE_REFUSED_PRESERVE,
                State.SHARING_OPEN_REFUSED_PRESERVE,
            }
        else:
            assert result.state in {
                State.PRE_ATTEMPT_INTERRUPTED_PRESERVE,
                State.POST_ATTEMPT_UNKNOWN_PRESERVE,
                State.NATIVE_REPLACE_REFUSED_PRESERVE,
                State.SHARING_OPEN_REFUSED_PRESERVE,
            }
    else:
        assert result.state is State.UNSUPPORTED


def test_platform_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.state is State.UNSUPPORTED
    assert not result.replacement_may_have_occurred


def test_public_api_has_no_paths_bytes_or_callbacks() -> None:
    parameters = inspect.signature(
        single.rehearse_synthetic_share_safe_single_scope_replace
    ).parameters
    assert tuple(parameters) == ("step", "interruption")
    assert not any(
        hasattr(single, name)
        for name in (
            "write_private_registry",
            "authorize_production",
            "commit_private_intent",
            "retire_private_journal",
            "open_notes",
            "replace_production_registry",
        )
    )


def test_status_never_contains_handles_or_paths() -> None:
    for state in State:
        review = single._result(state, attempted=True)
        assert review.pending_evidence_must_remain
        assert review.replacement_may_have_occurred
        assert len(review.unqualified_requirements) == len(barrier._REQUIRED)
        assert "Handle(" not in repr(review)
        assert "C:\\" not in repr(review)
        assert "/home/" not in repr(review)


def test_immutable_review() -> None:
    finding = single._result(State.PREIMAGE_REFUSED)
    with pytest.raises(FrozenInstanceError):
        setattr(finding, "state", State.IO_ERROR)


def test_native_share_open_requires_delete_sharing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[sharing.PrivateSyntheticWindowsShareMode] = []

    @contextmanager
    def fake_native_target(
        path: Path, mode: sharing.PrivateSyntheticWindowsShareMode
    ) -> Iterator[BinaryIO]:
        assert path == tmp_path / "synthetic"
        seen.append(mode)
        with path.open("rb") as stream:
            yield stream

    path = tmp_path / "synthetic"
    path.write_bytes(b"mock\n")
    monkeypatch.setattr(sharing, "_native_target", fake_native_target)
    monkeypatch.setattr(sys, "platform", "win32")
    with single._share_safe_reader(path) as stream:
        assert stream.read() == b"mock\n"
    assert seen == [sharing.PrivateSyntheticWindowsShareMode.ALLOW_DELETE_SHARE]


def test_posix_open_is_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "synthetic"
    path.write_bytes(b"read-only\n")
    monkeypatch.setattr(sys, "platform", "linux")
    with single._share_safe_reader(path) as stream:
        assert stream.read() == b"read-only\n"
        assert not stream.writable()


@pytest.mark.parametrize("wrong", [b"different", b"x", b"", b"test\x00"])
def test_retained_handle_refuses_different_bytes(tmp_path: Path, wrong: bytes) -> None:
    path = tmp_path / "exact"
    path.write_bytes(b"test")
    with path.open("rb") as stream:
        stat = os.fstat(stream.fileno())
        assert not single._held_exact(stream, (stat.st_dev, stat.st_ino), wrong)


def test_retained_handle_refuses_different_identity(tmp_path: Path) -> None:
    path = tmp_path / "exact"
    path.write_bytes(b"test")
    with path.open("rb") as stream:
        stat = os.fstat(stream.fileno())
        assert not single._held_exact(stream, (stat.st_dev, stat.st_ino + 1), b"test")
        assert single._held_exact(stream, (stat.st_dev, stat.st_ino), b"test")


def test_retained_handle_after_unlink_is_readable_linux(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("POSIX unlink handle check")
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.write_bytes(b"before")
    new.write_bytes(b"after")
    with old.open("rb") as old_stream, new.open("rb") as new_stream:
        st = os.fstat(old_stream.fileno())
        other = os.fstat(new_stream.fileno())
        os.replace(new, old)
        assert single._held_exact(
            old_stream, (st.st_dev, st.st_ino), b"before", after_target=True
        )
        assert single._held_exact(new_stream, (other.st_dev, other.st_ino), b"after")
        assert old.read_bytes() == b"after"
        assert not new.exists()


def test_unavailable_native_target_handle_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def fail(path: Path) -> Iterator[BinaryIO]:
        raise PermissionError("synthetic refused")
        yield  # pragma: no cover

    monkeypatch.setattr(single, "_share_safe_reader", fail)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.state is State.SHARING_OPEN_REFUSED_PRESERVE
    assert not result.replacement_may_have_occurred


@pytest.mark.parametrize("errno_value", [5, 13, 32, 33])
def test_native_refusal_without_mutation_preserves_stage(
    monkeypatch: pytest.MonkeyPatch, errno_value: int
) -> None:
    def refuse(_src: Path, _dst: Path) -> None:
        error = PermissionError(errno_value, "scratch refusal")
        raise error

    monkeypatch.setattr(os, "replace", refuse)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.state in {
        State.NATIVE_REPLACE_REFUSED_PRESERVE,
        State.POST_ATTEMPT_UNKNOWN_PRESERVE,
    }
    assert result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain


def test_unknown_oserror_after_attempt_is_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unknown(_src: Path, _dst: Path) -> None:
        raise OSError(999, "synthetic error")

    monkeypatch.setattr(os, "replace", unknown)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert result.replacement_may_have_occurred


def test_replace_then_error_is_never_classified_safe_to_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = os.replace
    calls = 0
    native_replaced = False

    def ambiguous(src: Path, dst: Path) -> None:
        nonlocal calls, native_replaced
        calls += 1
        # Windows can refuse replacement while share-safe read handles are
        # retained. In that case this native operation did NOT complete and
        # the subsequent synthetic post-rename error is never raised.
        original(src, dst)
        native_replaced = True
        raise PermissionError(13, "post-rename error")

    monkeypatch.setattr(os, "replace", ambiguous)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert calls == 1
    if native_replaced:
        assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    else:
        assert result.state in {
            State.NATIVE_REPLACE_REFUSED_PRESERVE,
            State.POST_ATTEMPT_UNKNOWN_PRESERVE,
        }
    assert result.replacement_may_have_occurred
    assert result.pending_evidence_must_remain


def test_final_admission_drift_refuses_before_native_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = canonical._observe
    count = 0
    attempts = 0

    def observe(
        paths: two._Paths,
        checked: intents.PrivateTransactionIntent,
        raw: bytes,
        *,
        stage: bool,
    ) -> canonical._Census:
        nonlocal count
        count += 1
        result = original(paths, checked, raw, stage=stage)
        if count == 2:
            return canonical._Census(
                result.parents,
                (result.registry[0], result.registry[1] + 1),
                result.journal,
                result.descriptor,
                result.guard,
                result.stage,
            )
        return result

    def unexpected(_src: Path, _dst: Path) -> None:
        nonlocal attempts
        attempts += 1
        raise AssertionError("must not attempt replace")

    monkeypatch.setattr(canonical, "_observe", observe)
    monkeypatch.setattr(os, "replace", unexpected)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.state is State.ADMISSION_DRIFT_PRESERVE
    assert attempts == 0


def test_retained_handle_check_refuses_before_native_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fail(*args: object, **kwargs: object) -> bool:
        return False

    def unexpected(_src: Path, _dst: Path) -> None:
        nonlocal attempts
        attempts += 1
        raise AssertionError("must not attempt replace")

    monkeypatch.setattr(single, "_holds", fail)
    monkeypatch.setattr(os, "replace", unexpected)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.state is State.NATIVE_HANDLE_CONFLICT_PRESERVE
    assert attempts == 0


def test_released_lock_failure_never_produces_positive_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = scratch._scratch_lock

    @contextmanager
    def late_fail(path: Path) -> Iterator[None]:
        with original(path):
            yield
        raise scratch._GuardRefused

    monkeypatch.setattr(scratch, "_scratch_lock", late_fail)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.state is State.GUARD_REFUSED_PRESERVE
    assert result.pending_evidence_must_remain


def test_scratch_root_is_module_created_and_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = canonical._make_layout
    roots: list[Path] = []

    def tracking(
        root: Path, checked: intents.PrivateTransactionIntent, raw: bytes
    ) -> two._Paths:
        roots.append(root)
        return original(root, checked, raw)

    monkeypatch.setattr(canonical, "_make_layout", tracking)
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert result.pending_evidence_must_remain
    assert len(roots) == 1
    assert not roots[0].exists()
    assert roots[0].name.startswith("core238_3g40_share_")


def test_staged_private_intent_not_exposed_by_review() -> None:
    result = single.rehearse_synthetic_share_safe_single_scope_replace()
    assert not hasattr(result, "path")
    assert not hasattr(result, "transaction")
    assert not hasattr(result, "handle")
    assert not hasattr(result, "writer_permit")
    assert not hasattr(result, "commit_token")
