"""3G82: operation-boundary inventory never authorizes production mutation."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_operation_preconditions as operation
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_retained_root_custody as custody
from pds_core.teacher_experience import get_teacher_experience_capabilities

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_operation_preconditions.py"
)


def _fake_preliminary() -> inspection.PrivateRootInspection:
    return inspection.PrivateRootInspection(
        inspection.PrivateRootState.PRESENT_UNVERIFIED,
        inspection.EffectiveOSOwner("posix_euid", "424242"),
        Path("/sensitive/private/notes/v1"),
        "fake private metadata",
    )


def _positive_but_not_authorizing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspection, "inspect_private_root", _fake_preliminary)
    monkeypatch.setattr(
        readiness,
        "review_private_production_readiness",
        lambda: readiness.PrivateProductionReadinessReview(
            readiness.PrivateProductionReadinessState.PRODUCTION_BLOCKED,
            "present_unverified",
            "restrictive_unqualified",
            True,
            readiness._REQUIRED,
        ),
    )
    monkeypatch.setattr(
        custody,
        "review_existing_private_root_native_custody",
        lambda: custody.PrivateRetainedRootReview(
            custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
        ),
    )


def test_requirements_are_exact_unqualified_barrier() -> None:
    assert readiness._REQUIRED == tuple(item.value for item in barrier._REQUIRED)
    assert len(readiness._REQUIRED) == 9
    assert "exclusive_operation_owned_guard" in readiness._REQUIRED
    assert (
        tuple(
            inspect.signature(
                operation.review_private_operation_preconditions
            ).parameters
        )
        == ()
    )


def test_actual_read_only_observations_never_authorize() -> None:
    result = operation.review_private_operation_preconditions()
    assert isinstance(result, operation.PrivateOperationPreconditionReview)
    assert result.state in operation.PrivateOperationPreconditionState
    assert result.unqualified_requirements == readiness._REQUIRED
    assert not result.operation_owned_guard_qualified
    assert not result.production_mutation_admitted
    assert not result.automatic_replay_allowed
    assert not result.journal_retirement_allowed
    assert not result.notes_records_available
    assert not result.transaction_commit_qualified
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_positive_native_custody_and_canonical_intent_still_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _positive_but_not_authorizing(monkeypatch)
    result = operation.review_private_operation_preconditions()
    assert (
        result.state is operation.PrivateOperationPreconditionState.PRODUCTION_BLOCKED
    )
    assert result.root_observation == "present_unverified"
    assert (
        result.retained_root_observation == "retained_private_root_observed_unqualified"
    )
    assert result.root_rechecked_in_review
    assert result.canonical_intent_description_checked
    assert result.owner_observed
    assert not result.operation_owned_guard_qualified
    assert result.unqualified_requirements == readiness._REQUIRED
    for sensitive in ("424242", "sensitive", "private/notes/v1"):
        assert sensitive not in repr(result)
        assert sensitive not in str(result)


def test_root_change_between_observations_is_explicit_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _positive_but_not_authorizing(monkeypatch)
    calls = 0

    def changing() -> inspection.PrivateRootInspection:
        nonlocal calls
        calls += 1
        prior = _fake_preliminary()
        if calls == 1:
            return prior
        return inspection.PrivateRootInspection(
            inspection.PrivateRootState.MISSING,
            prior.owner,
            prior.candidate,
            "changed",
        )

    monkeypatch.setattr(inspection, "inspect_private_root", changing)
    result = operation.review_private_operation_preconditions()
    assert calls == 2
    assert (
        result.state is operation.PrivateOperationPreconditionState.ROOT_CHANGED_BLOCKED
    )
    assert not result.root_rechecked_in_review
    assert result.canonical_intent_description_checked
    assert not result.production_mutation_admitted


def test_intermediate_owner_root_disagreement_is_explicitly_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _positive_but_not_authorizing(monkeypatch)
    monkeypatch.setattr(
        readiness,
        "review_private_production_readiness",
        lambda: readiness.PrivateProductionReadinessReview(
            readiness.PrivateProductionReadinessState.PRODUCTION_BLOCKED,
            "missing",
            "restrictive_unqualified",
            True,
            readiness._REQUIRED,
        ),
    )
    result = operation.review_private_operation_preconditions()
    assert (
        result.state is operation.PrivateOperationPreconditionState.ROOT_CHANGED_BLOCKED
    )
    assert not result.root_rechecked_in_review
    assert not result.operation_owned_guard_qualified


def test_requirements_drift_prevents_all_native_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(barrier, "_REQUIRED", barrier._REQUIRED[:-1])

    def forbidden() -> inspection.PrivateRootInspection:
        raise AssertionError("native observation must not start on requirement drift")

    monkeypatch.setattr(inspection, "inspect_private_root", forbidden)
    result = operation.review_private_operation_preconditions()
    assert (
        result.state
        is operation.PrivateOperationPreconditionState.REQUIREMENT_DRIFT_BLOCKED
    )
    assert result.unqualified_requirements == readiness._REQUIRED
    assert not result.root_rechecked_in_review


def test_owner_or_native_failure_refuses_without_raw_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> inspection.PrivateRootInspection:
        raise PermissionError("/sensitive/owner/should_not_escape")

    monkeypatch.setattr(inspection, "inspect_private_root", refuse)
    result = operation.review_private_operation_preconditions()
    assert (
        result.state
        is operation.PrivateOperationPreconditionState.OBSERVATION_REFUSED_BLOCKED
    )
    assert "/sensitive" not in repr(result)
    assert not result.operation_owned_guard_qualified


def test_canonical_description_refusal_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _positive_but_not_authorizing(monkeypatch)
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon

    def refuse() -> None:
        raise ValueError("synthetic canonical intent rejected")

    monkeypatch.setattr(canon, "_canonical_fork_intent", refuse)
    result = operation.review_private_operation_preconditions()
    assert (
        result.state
        is operation.PrivateOperationPreconditionState.OBSERVATION_REFUSED_BLOCKED
    )
    assert not result.canonical_intent_description_checked
    assert not result.production_mutation_admitted


def test_installed_verifier_has_no_mutation_or_private_identity_leak() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    ast.parse(text)
    for required in (
        "review_private_operation_preconditions()",
        '"unqualified_requirements": list(review.unqualified_requirements)',
        '"operation_owned_guard_qualified": False',
        '"production_mutation_admitted": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
    ):
        assert required in text
    for forbidden in (
        "os.replace(",
        "os.mkdir(",
        "shutil.rmtree(",
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "activate_notes(",
        "subprocess.shell=True",
    ):
        assert forbidden not in text
