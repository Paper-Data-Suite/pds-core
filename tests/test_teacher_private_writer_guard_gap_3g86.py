"""3G86: read-only stage review does not convey exclusive writer authority."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_stage_to_registry_pre_admission as stage
from pds_core import _teacher_private_writer_guard_gap as review
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _assert_blocked(result: review.PrivateWriterGuardGapReview) -> None:
    assert result.unqualified_requirements == readiness._REQUIRED
    assert not any(
        (
            result.cooperative_lock_exclusion_is_production_exclusion,
            result.operation_owned_guard_qualified,
            result.noncooperating_writer_exclusion_qualified,
            result.native_parent_custody_for_write_qualified,
            result.exact_preimage_cas_for_write_qualified,
            result.native_replace_postimage_qualified,
            result.production_mutation_admitted,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.multi_document_atomic_commit_qualified,
        )
    )
    assert repr(result) == "PrivateWriterGuardGapReview(non_authorizing=True)"


def _stage_result(*, prepared: bool) -> stage.PrivateStagePreAdmissionReview:
    return stage.PrivateStagePreAdmissionReview(
        stage.PrivateStagePreAdmissionState.PREPARED_REVIEW_BLOCKED
        if prepared
        else stage.PrivateStagePreAdmissionState.STAGE_NOT_PREPARED_PRESERVE,
        existing_two_root_read_guard_observed=prepared,
        two_preimage_rounds_rechecked=prepared,
    )


def test_prepared_still_requires_exclusive_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        stage,
        "review_existing_stage_to_registry_pre_admission",
        lambda *_: _stage_result(prepared=True),
    )
    result = review.review_private_writer_owned_exclusivity_gap(
        Path("untrusted"), "tx", 1
    )
    assert (
        result.state
        is review.PrivateWriterGuardGapState.PREPARED_BUT_EXCLUSIVITY_UNQUALIFIED
    )
    assert result.stage_read_review_only
    _assert_blocked(result)


def test_unprepared_preserves_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stage,
        "review_existing_stage_to_registry_pre_admission",
        lambda *_: _stage_result(prepared=False),
    )
    result = review.review_private_writer_owned_exclusivity_gap(
        Path("untrusted"), "tx", 1
    )
    assert (
        result.state is review.PrivateWriterGuardGapState.STAGE_REVIEW_REFUSED_PRESERVE
    )
    assert not result.stage_read_review_only
    _assert_blocked(result)


def test_forged_positive_review_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    forged = replace(
        _stage_result(prepared=True), operation_owned_write_guard_qualified=True
    )
    monkeypatch.setattr(
        stage, "review_existing_stage_to_registry_pre_admission", lambda *_: forged
    )
    result = review.review_private_writer_owned_exclusivity_gap(
        Path("untrusted"), "tx", 1
    )
    assert result.state is review.PrivateWriterGuardGapState.REVIEW_FAILURE_PRESERVE
    _assert_blocked(result)


def test_prepared_without_two_rounds_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    forged = replace(_stage_result(prepared=True), two_preimage_rounds_rechecked=False)
    monkeypatch.setattr(
        stage, "review_existing_stage_to_registry_pre_admission", lambda *_: forged
    )
    result = review.review_private_writer_owned_exclusivity_gap(
        Path("untrusted"), "tx", 1
    )
    assert result.state is review.PrivateWriterGuardGapState.REVIEW_FAILURE_PRESERVE
    _assert_blocked(result)


@pytest.mark.parametrize("bad", [None, True, 0, 2.2, -5, "2"])
def test_invalid_inputs_propagate_only_refusal(bad: object) -> None:
    result = review.review_private_writer_owned_exclusivity_gap(
        Path("relative"), "not-a-transaction", cast(int, bad)
    )
    assert (
        result.state is review.PrivateWriterGuardGapState.STAGE_REVIEW_REFUSED_PRESERVE
    )
    _assert_blocked(result)


def test_requirement_drift_refuses_before_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])

    def should_not_call(*_args: object) -> stage.PrivateStagePreAdmissionReview:
        raise AssertionError("unexpected stage review")

    monkeypatch.setattr(
        stage, "review_existing_stage_to_registry_pre_admission", should_not_call
    )
    result = review.review_private_writer_owned_exclusivity_gap(
        Path("relative"), "tx", 1
    )
    assert result.state is review.PrivateWriterGuardGapState.REQUIREMENT_DRIFT_BLOCKED
    assert not result.production_mutation_admitted


def test_reader_exception_preserves_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object) -> stage.PrivateStagePreAdmissionReview:
        raise OSError("private data that must not escape")

    monkeypatch.setattr(stage, "review_existing_stage_to_registry_pre_admission", fail)
    result = review.review_private_writer_owned_exclusivity_gap(
        Path("relative"), "tx", 1
    )
    assert result.state is review.PrivateWriterGuardGapState.REVIEW_FAILURE_PRESERVE
    assert "private data" not in repr(result)
    _assert_blocked(result)


def test_no_mutation_surface_or_notes_capability() -> None:
    file = review.__file__
    assert file is not None
    source = Path(file).read_text(encoding="utf-8")
    ast.parse(source)
    for forbidden in (
        "os.replace(",
        "os.unlink(",
        "os.makedirs(",
        "os.mkdir(",
        "subprocess.run(",
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "activate_notes(",
    ):
        assert forbidden not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
