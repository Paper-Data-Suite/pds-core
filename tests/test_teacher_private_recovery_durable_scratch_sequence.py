"""Synthetic, adversarial durability-ordering tests for #238 Slice 3G48."""

from __future__ import annotations

from dataclasses import fields
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_recovery_durable_scratch_sequence as drill

State = drill.PrivateDurableScratchState
Fault = drill.PrivateDurableScratchFault


@pytest.fixture
def portable(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Allow the transaction-order tests to isolate platform flush support."""
    if sys.platform not in {"win32", "linux"}:
        monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(drill, "_directory_flush", lambda path: None)
    yield


def test_real_native_directory_flush_probe() -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip("Native directory flush probe only on Windows/Linux")
    observed = drill.rehearse_synthetic_two_document_flush_order()
    assert observed.state in {
        State.SCRATCH_FLUSH_SEQUENCE_OBSERVED_UNQUALIFIED,
        State.DIRECTORY_FLUSH_UNQUALIFIED_PRESERVE,
    }
    assert observed.pending_evidence_must_remain
    assert observed.production_writes_blocked
    assert observed.journal_retirement_forbidden


def test_exact_sequence_and_pending_journal_kept(portable: None) -> None:
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert result.state is State.SCRATCH_FLUSH_SEQUENCE_OBSERVED_UNQUALIFIED
    assert result.flush_order == (
        "journal_file",
        "registry_stage_file",
        "descriptor_stage_file",
        "journal_directory",
        "registry_prepared_directory",
        "descriptor_prepared_directory",
        "registry_replace",
        "registry_file",
        "registry_directory",
        "descriptor_replace",
        "descriptor_file",
        "descriptor_directory",
    )
    assert result.replacement_may_have_occurred
    assert "Path" not in repr(result)
    assert "revision" not in repr(result)


@pytest.mark.parametrize("fault", list(Fault))
def test_interruption_classified_without_retry(
    portable: None, fault: Fault, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    replace = os.replace

    def counted(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        replace(source, destination)

    monkeypatch.setattr(os, "replace", counted)
    result = drill.rehearse_synthetic_two_document_flush_order(fault)
    expected_calls = (
        0
        if fault
        in {
            Fault.AFTER_PREPARED_FLUSH,
            Fault.BEFORE_REGISTRY_REPLACE,
        }
        else 1
        if fault
        in {
            Fault.AFTER_REGISTRY_REPLACE,
            Fault.AFTER_REGISTRY_FLUSH,
            Fault.AFTER_REGISTRY_DIRECTORY_FLUSH,
            Fault.BEFORE_DESCRIPTOR_REPLACE,
        }
        else 2
    )
    assert calls == expected_calls
    if fault is Fault.NONE:
        assert result.state is State.SCRATCH_FLUSH_SEQUENCE_OBSERVED_UNQUALIFIED
    elif expected_calls == 0:
        assert result.state is State.PRE_ATTEMPT_INTERRUPTED_PRESERVE
    else:
        assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert result.replacement_may_have_occurred == bool(calls)
    assert result.production_writes_blocked and result.journal_retirement_forbidden


def test_invalid_input_fails_before_temp_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected scratch setup")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbidden)
    for malformed in (None, "none", 4, True, object()):
        result = drill.rehearse_synthetic_two_document_flush_order(malformed)  # type: ignore[arg-type]
        assert result.state is State.INVALID_REQUEST


def test_unsupported_platform_refuses_without_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "other")
    assert (
        drill.rehearse_synthetic_two_document_flush_order().state is State.UNSUPPORTED
    )


def test_directory_failure_before_native_replace_prevents_attempt(
    monkeypatch: pytest.MonkeyPatch, portable: None
) -> None:
    calls = 0

    def reject_directory(_path: Path) -> None:
        raise drill._DirectoryFlushRefused

    def counted(_src: Path, _dst: Path) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(drill, "_directory_flush", reject_directory)
    monkeypatch.setattr(os, "replace", counted)
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert result.state is State.DIRECTORY_FLUSH_UNQUALIFIED_PRESERVE
    assert not result.replacement_may_have_occurred
    assert calls == 0


def test_directory_failure_after_registry_replace_is_not_success(
    monkeypatch: pytest.MonkeyPatch, portable: None
) -> None:
    count = 0

    def fail_second_parent(_path: Path) -> None:
        nonlocal count
        count += 1
        if count == 4:
            raise drill._DirectoryFlushRefused

    monkeypatch.setattr(drill, "_directory_flush", fail_second_parent)
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert result.state is State.DIRECTORY_FLUSH_UNQUALIFIED_PRESERVE
    assert result.replacement_may_have_occurred
    assert "registry_replace" in result.flush_order
    assert "descriptor_replace" not in result.flush_order


def test_file_flush_refusal_does_not_retry(
    monkeypatch: pytest.MonkeyPatch, portable: None
) -> None:
    original = drill._file_flush
    calls = 0

    def reject_after_registry(path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise drill._FileFlushRefused
        original(path)

    monkeypatch.setattr(drill, "_file_flush", reject_after_registry)
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert result.state is State.FILE_FLUSH_REFUSED_PRESERVE
    assert result.replacement_may_have_occurred
    assert "descriptor_replace" not in result.flush_order


def test_unknown_post_attempt_error_never_blind_retries(
    monkeypatch: pytest.MonkeyPatch, portable: None
) -> None:
    original = os.replace
    calls = 0

    def commit_then_raise(src: Path, dst: Path) -> None:
        nonlocal calls
        calls += 1
        original(src, dst)
        raise PermissionError("synthetic post-attempt error")

    monkeypatch.setattr(os, "replace", commit_then_raise)
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert calls == 1
    assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE
    assert result.replacement_may_have_occurred


def test_first_replace_refusal_does_not_blind_retry(
    monkeypatch: pytest.MonkeyPatch, portable: None
) -> None:
    calls = 0

    def reject(_src: Path, _dst: Path) -> None:
        nonlocal calls
        calls += 1
        raise PermissionError("synthetic refused")

    monkeypatch.setattr(os, "replace", reject)
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert calls == 1
    assert result.state is State.POST_ATTEMPT_UNKNOWN_PRESERVE


def test_changed_afterimage_preserves_pending_evidence(
    monkeypatch: pytest.MonkeyPatch, portable: None
) -> None:
    original = os.replace

    def corrupt_after(src: Path, dst: Path) -> None:
        original(src, dst)
        with dst.open("wb") as stream:
            stream.write(b"changed")

    monkeypatch.setattr(os, "replace", corrupt_after)
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert result.state is State.POSTIMAGE_CONFLICT_PRESERVE


def test_non_authorizing_result_cannot_expose_private_path(portable: None) -> None:
    result = drill.rehearse_synthetic_two_document_flush_order()
    assert result.state is State.SCRATCH_FLUSH_SEQUENCE_OBSERVED_UNQUALIFIED
    assert {item.name for item in fields(result)} == {
        "state",
        "message",
        "replacement_may_have_occurred",
        "pending_evidence_must_remain",
        "production_writes_blocked",
        "journal_retirement_forbidden",
        "flush_order",
    }
    assert "core238_" not in repr(result)
