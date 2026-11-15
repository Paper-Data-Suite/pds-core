"""3G85: read-only stage pre-admission is always blocked and fail closed."""

from __future__ import annotations

import ast
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_guarded_canonical_consistency as canonical
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_operation_preconditions as preconditions
from pds_core import _teacher_private_postcrash_reconciliation as reconciliation
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_canonical_journaled_restart as seed
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_root_custody as custody
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_stage_to_registry_pre_admission as review
from pds_core import _teacher_private_transaction_intent as intents
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _setup(monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, list[str]]:
    checked = seed._canonical_fork_intent()
    assert checked.registry_before is not None and checked.descriptor_before is not None
    image = (
        intents.encode_private_transaction_intent(checked),
        checked.registry_before,
        checked.descriptor_before,
        checked.registry_after,
    )
    kind: Literal["posix_euid", "windows_token_sid"] = (
        "windows_token_sid" if sys.platform == "win32" else "posix_euid"
    )
    owner = inspection.EffectiveOSOwner(
        kind, "S-1-5-21-1000" if kind == "windows_token_sid" else "1000"
    )
    private = (
        Path("C:/Users/Synthetic/AppData/Local/Paper Data Suite/private/notes/v1")
        if kind == "windows_token_sid"
        else Path("/tmp/synthetic-private")
    )
    workspace = (
        Path("C:/Synthetic/Fork")
        if kind == "windows_token_sid"
        else Path("/synthetic_fork")
    )
    root = inspection.PrivateRootInspection(
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
    monkeypatch.setattr(inspection, "inspect_private_root", lambda: root)
    monkeypatch.setattr(inspection, "_effective_owner", lambda _platform: owner)
    monkeypatch.setattr(descriptor, "_valid_root", lambda path: path == workspace)
    monkeypatch.setattr(
        custody,
        "_probe_existing",
        lambda *_: (
            custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
        ),
    )
    monkeypatch.setattr(
        reconciliation,
        "_namespace",
        lambda *_: (
            frozenset({checked.witness.transaction_id + ".json"}),
            frozenset({"registry.json"}),
            True,
        ),
    )
    monkeypatch.setattr(
        readers,
        "_inventory",
        lambda *_: (
            inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
        ),
    )
    events: list[str] = []

    @contextmanager
    def held(r: Path, w: Path) -> Iterator[None]:
        assert r == private and w == workspace
        events.append("entered")
        try:
            yield None
        finally:
            events.append("released")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", held)
    # Pure 3G84 tests already check metadata owner and accepted-workspace binding;
    # native-scope tests here focus on preimage rounds under held handles.
    monkeypatch.setattr(
        canonical,
        "_classify_canonical_images",
        lambda *_: canonical.PrivateGuardedCanonicalState.PREPARED_CANONICAL_BLOCKED,
    )

    def native_images(*_args: object) -> tuple[bytes, bytes, bytes, bytes]:
        events.append("read")
        return image

    monkeypatch.setattr(exact, "_images", native_images)
    return workspace, checked.witness.transaction_id, events


def _assert_blocked(result: review.PrivateStagePreAdmissionReview) -> None:
    assert result.unqualified_requirements == review._REQUIRED
    assert not any(
        (
            result.production_mutation_admitted,
            result.operation_owned_write_guard_qualified,
            result.exclusive_noncooperating_writer_guard_qualified,
            result.native_replace_postimage_qualified,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.multi_document_atomic_commit_qualified,
        )
    )
    assert repr(result) == "PrivateStagePreAdmissionReview(non_authorizing=True)"


@pytest.mark.parametrize("bad", [None, True, 2.0, 0, -1, "2"])
def test_invalid_revision_never_enters_native_scope(bad: object) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native only")
    tx = seed._canonical_fork_intent().witness.transaction_id
    result = review.review_existing_stage_to_registry_pre_admission(
        Path("relative"), tx, cast(int, bad)
    )
    assert result.state is review.PrivateStagePreAdmissionState.INVALID_REQUEST_BLOCKED
    _assert_blocked(result)


def test_two_native_preimage_rounds_hold_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native only")
    root, tx, events = _setup(monkeypatch)
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 2)
    assert result.state is review.PrivateStagePreAdmissionState.PREPARED_REVIEW_BLOCKED
    assert events == ["entered", "read", "read", "released"]
    assert result.existing_two_root_read_guard_observed
    assert result.two_preimage_rounds_rechecked
    _assert_blocked(result)


def test_mismatched_revision_preserves_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    root, tx, events = _setup(monkeypatch)
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 3)
    assert (
        result.state is review.PrivateStagePreAdmissionState.REVISION_MISMATCH_REFUSED
    )
    assert events == ["entered", "read", "released"]
    _assert_blocked(result)


def test_nonprepared_stage_refused_under_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    root, tx, events = _setup(monkeypatch)
    monkeypatch.setattr(
        reconciliation, "_namespace", lambda *_: (frozenset(), frozenset(), False)
    )
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 2)
    assert (
        result.state is review.PrivateStagePreAdmissionState.STAGE_NOT_PREPARED_PRESERVE
    )
    assert events == ["entered", "released"]
    _assert_blocked(result)


def test_preimage_drift_refused_before_release(monkeypatch: pytest.MonkeyPatch) -> None:
    root, tx, events = _setup(monkeypatch)
    checked = seed._canonical_fork_intent()
    assert checked.descriptor_before is not None and checked.registry_before is not None
    calls = 0

    def drift(*_args: object) -> tuple[bytes, bytes, bytes, bytes]:
        nonlocal calls
        calls += 1
        events.append("read")
        registry_before = checked.registry_before
        descriptor_before = checked.descriptor_before
        assert isinstance(registry_before, bytes) and isinstance(
            descriptor_before, bytes
        )
        return (
            intents.encode_private_transaction_intent(checked),
            registry_before if calls == 1 else registry_before + b"x",
            descriptor_before,
            checked.registry_after,
        )

    monkeypatch.setattr(exact, "_images", drift)
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 2)
    assert result.state is review.PrivateStagePreAdmissionState.IMAGE_DRIFT_PRESERVE
    assert events == ["entered", "read", "read", "released"]
    _assert_blocked(result)


def test_canonical_refusal_remains_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    root, tx, events = _setup(monkeypatch)
    monkeypatch.setattr(
        canonical,
        "_classify_canonical_images",
        lambda *_: (
            canonical.PrivateGuardedCanonicalState.OWNER_BINDING_REFUSED_PRESERVE
        ),
    )
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 2)
    assert (
        result.state
        is review.PrivateStagePreAdmissionState.CANONICAL_IMAGE_REFUSED_PRESERVE
    )
    assert events == ["entered", "read", "released"]
    _assert_blocked(result)


def test_owner_or_private_root_drift_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    root, tx, events = _setup(monkeypatch)
    monkeypatch.setattr(
        inspection,
        "_effective_owner",
        lambda _platform: inspection.EffectiveOSOwner("posix_euid", "999"),
    )
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 2)
    assert (
        result.state
        is review.PrivateStagePreAdmissionState.ROOT_OR_OWNER_REFUSED_BLOCKED
    )
    assert events == ["entered", "released"]
    _assert_blocked(result)


def test_guard_refusal_returns_only_sanitized_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, tx, _ = _setup(monkeypatch)

    @contextmanager
    def refuse(_r: Path, _w: Path) -> Iterator[None]:
        raise retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.REGISTRY_GUARD_REFUSED
        )
        yield None

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", refuse)
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 2)
    assert result.state is review.PrivateStagePreAdmissionState.GUARD_REFUSED_PRESERVE
    assert "Synthetic" not in repr(result)
    _assert_blocked(result)


def test_requirement_drift_refuses_before_owner_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, tx, _ = _setup(monkeypatch)
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = review.review_existing_stage_to_registry_pre_admission(root, tx, 2)
    assert (
        result.state is review.PrivateStagePreAdmissionState.REQUIREMENT_DRIFT_BLOCKED
    )
    _assert_blocked(result)


def test_source_has_no_mutation_surface() -> None:
    origin = review.__file__
    assert origin is not None
    source = Path(origin).read_text(encoding="utf-8")
    ast.parse(source)
    for forbidden in (
        "os.replace(",
        "os.unlink(",
        "os.mkdir(",
        "os.makedirs(",
        "retire_private_journal(",
        "activate_notes(",
        "commit_private_workspace_binding(",
        "subprocess.run(",
    ):
        assert forbidden not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
