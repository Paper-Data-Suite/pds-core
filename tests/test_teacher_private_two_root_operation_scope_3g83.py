"""3G83: two-root read-only guard observation never exports write authority."""

from __future__ import annotations

import ast
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_operation_preconditions as preconditions
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_root_custody as custody
from pds_core import _teacher_private_two_root_operation_scope as scope
from pds_core.teacher_experience import get_teacher_experience_capabilities


@pytest.mark.parametrize("invalid", [None, "workspace", True, Path("relative")])
def test_invalid_workspace_never_opens_native_guard(
    invalid: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden() -> None:
        raise AssertionError("Invalid path must not inspect OS private root")

    monkeypatch.setattr(
        preconditions, "review_private_operation_preconditions", forbidden
    )
    if sys.platform in {"linux", "win32"}:
        assert scope.review_existing_two_root_operation_scope(
            cast(Path, invalid)
        ).state is (scope.PrivateTwoRootOperationState.INVALID_REQUEST_BLOCKED)


def _setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, list[str], inspection.EffectiveOSOwner]:
    owner = inspection.EffectiveOSOwner(
        "windows_token_sid" if sys.platform == "win32" else "posix_euid",
        "S-1-5-21-424242" if sys.platform == "win32" else "424242",
    )
    private = tmp_path / "imaginary-private"
    workspace = tmp_path / "imaginary-workspace"
    first = inspection.PrivateRootInspection(
        inspection.PrivateRootState.PRESENT_UNVERIFIED, owner, private, "synthetic"
    )
    prior = preconditions.PrivateOperationPreconditionReview(
        preconditions.PrivateOperationPreconditionState.PRODUCTION_BLOCKED,
        "unavailable",
        "present_unverified",
        True,
        readiness._REQUIRED,
    )
    monkeypatch.setattr(
        preconditions, "review_private_operation_preconditions", lambda: prior
    )
    monkeypatch.setattr(inspection, "inspect_private_root", lambda: first)
    monkeypatch.setattr(inspection, "_effective_owner", lambda _p: owner)
    monkeypatch.setattr(descriptor, "_valid_root", lambda p: p == workspace)
    history: list[str] = []

    @contextmanager
    def fake_guard(priv: Path, work: Path) -> Iterator[None]:
        assert priv == private and work == workspace
        history.append("entered")
        try:
            yield None
        finally:
            history.append("closed")

    monkeypatch.setattr(
        retained, "_hold_existing_retained_descriptor_guard", fake_guard
    )

    def fake_native_custody(
        priv: Path, same_owner: inspection.EffectiveOSOwner
    ) -> custody.PrivateRetainedRootState:
        assert priv == private and same_owner == owner
        history.append("native")
        return (
            custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
        )

    monkeypatch.setattr(custody, "_probe_existing", fake_native_custody)

    def fake_descriptor(work: Path) -> descriptor.PrivateDescriptorSnapshot:
        assert work == workspace
        history.append("descriptor")
        return descriptor.PrivateDescriptorSnapshot(
            descriptor.PrivateDescriptorSnapshotState.OBSERVED_UNQUALIFIED,
            "synthetic only",
            "f0000000-0000-4000-8000-000000000000",
            "0123456789abcdef",
        )

    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", fake_descriptor)
    return workspace, history, owner


def test_guarded_two_root_positive_still_nonauthorizing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    workspace, events, _ = _setup(monkeypatch, tmp_path)
    review = scope.review_existing_two_root_operation_scope(workspace)
    assert (
        review.state
        is scope.PrivateTwoRootOperationState.GUARDED_OBSERVED_PRODUCTION_BLOCKED
    )
    assert events == ["entered", "native", "descriptor", "descriptor", "closed"]
    assert review.read_only_guard_observed
    assert review.two_root_observations_rechecked
    assert (
        review.private_custody_observation
        == "retained_private_root_observed_unqualified"
    )
    assert review.descriptor_observation == "observed_unqualified"
    assert review.unqualified_requirements == readiness._REQUIRED
    assert not any(
        (
            review.operation_owned_write_guard_qualified,
            review.production_mutation_admitted,
            review.automatic_replay_allowed,
            review.journal_retirement_allowed,
            review.notes_records_available,
            review.directory_crash_durability_qualified,
            review.multi_document_atomic_commit_qualified,
            review.noncooperating_writer_exclusion_qualified,
        )
    )
    assert str(tmp_path) not in repr(review)
    assert "424242" not in repr(review)
    assert not tmp_path.joinpath("imaginary-private").exists()


def test_descriptor_change_refused_while_guard_held(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    workspace, events, _ = _setup(monkeypatch, tmp_path)
    real = descriptor.inspect_workspace_descriptor
    calls = 0

    def drift(path: Path) -> descriptor.PrivateDescriptorSnapshot:
        nonlocal calls
        calls += 1
        found = real(path)
        if calls == 2:
            return descriptor.PrivateDescriptorSnapshot(
                found.state, found.message, found.association_id, "changed"
            )
        return found

    monkeypatch.setattr(descriptor, "inspect_workspace_descriptor", drift)
    outcome = scope.review_existing_two_root_operation_scope(workspace)
    assert (
        outcome.state is scope.PrivateTwoRootOperationState.DESCRIPTOR_CHANGED_BLOCKED
    )
    assert events[-1] == "closed"
    assert not outcome.production_mutation_admitted


def test_root_changed_inside_guard_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    workspace, events, _ = _setup(monkeypatch, tmp_path)
    original = inspection.inspect_private_root
    calls = 0

    def changed() -> inspection.PrivateRootInspection:
        nonlocal calls
        calls += 1
        first = original()
        if calls >= 2:
            return inspection.PrivateRootInspection(
                first.state, first.owner, first.candidate, "changed"
            )
        return first

    monkeypatch.setattr(inspection, "inspect_private_root", changed)
    outcome = scope.review_existing_two_root_operation_scope(workspace)
    assert (
        outcome.state
        is scope.PrivateTwoRootOperationState.OWNER_OR_ROOT_CHANGED_BLOCKED
    )
    assert events == ["entered", "closed"]


def test_platform_inconsistent_owner_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    workspace, events, _ = _setup(monkeypatch, tmp_path)
    wrong = (
        inspection.EffectiveOSOwner("posix_euid", "424242")
        if sys.platform == "win32"
        else inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-999999")
    )
    monkeypatch.setattr(
        inspection,
        "inspect_private_root",
        lambda: inspection.PrivateRootInspection(
            inspection.PrivateRootState.PRESENT_UNVERIFIED,
            wrong,
            tmp_path / "imaginary-private",
            "synthetic",
        ),
    )
    result = scope.review_existing_two_root_operation_scope(workspace)
    assert (
        result.state is scope.PrivateTwoRootOperationState.PRIVATE_ROOT_REFUSED_BLOCKED
    )
    assert events == []


def test_refused_native_custody_stays_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    workspace, events, _ = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        custody,
        "_probe_existing",
        lambda *_: custody.PrivateRetainedRootState.NATIVE_PROTECTION_REFUSED,
    )
    outcome = scope.review_existing_two_root_operation_scope(workspace)
    assert (
        outcome.state
        is scope.PrivateTwoRootOperationState.NATIVE_CUSTODY_REFUSED_BLOCKED
    )
    assert events == ["entered", "closed"]


def test_guard_refusal_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    workspace, _, _ = _setup(monkeypatch, tmp_path)

    @contextmanager
    def denied(_a: Path, _b: Path) -> Iterator[None]:
        raise retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.REGISTRY_GUARD_REFUSED
        )
        yield None

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", denied)
    result = scope.review_existing_two_root_operation_scope(workspace)
    assert (
        result.state is scope.PrivateTwoRootOperationState.NATIVE_GUARD_REFUSED_BLOCKED
    )
    assert "imaginary" not in repr(result)


def test_missing_private_root_never_enters_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    workspace, events, owner = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        inspection,
        "inspect_private_root",
        lambda: inspection.PrivateRootInspection(
            inspection.PrivateRootState.MISSING, owner, None, "missing"
        ),
    )
    result = scope.review_existing_two_root_operation_scope(workspace)
    assert (
        result.state is scope.PrivateTwoRootOperationState.PRIVATE_ROOT_MISSING_BLOCKED
    )
    assert not events


def test_requirement_drift_refused_before_native_probes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native guard only")
    monkeypatch.setattr(barrier, "_REQUIRED", tuple(barrier._REQUIRED[:-1]))
    monkeypatch.setattr(descriptor, "_valid_root", lambda _p: True)
    monkeypatch.setattr(
        preconditions,
        "review_private_operation_preconditions",
        lambda: (_ for _ in ()).throw(AssertionError("must not probe")),
    )
    result = scope.review_existing_two_root_operation_scope(tmp_path)
    assert result.state is scope.PrivateTwoRootOperationState.REQUIREMENTS_DRIFT_BLOCKED


def test_no_public_notes_authority_or_source_mutations() -> None:
    origin = scope.__file__
    assert origin is not None
    source = Path(origin).read_text(encoding="utf-8")
    ast.parse(source)
    for forbidden in (
        "os.replace(",
        "os.unlink(",
        "os.chmod(",
        "shutil.rmtree(",
        "retire_private_journal(",
        "activate_notes(",
        "commit_private_workspace_binding(",
    ):
        assert forbidden not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
