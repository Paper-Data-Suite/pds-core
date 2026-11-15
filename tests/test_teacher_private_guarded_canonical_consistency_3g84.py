"""3G84: canonical journal-derived images under retained native guard, no authority."""

from __future__ import annotations

import ast
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterator, Literal

import pytest

from pds_core import _teacher_private_guarded_canonical_consistency as review
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_operation_preconditions as preconditions
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import _teacher_private_postcrash_reconciliation as reconciliation
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_retained_root_custody as custody
from pds_core import _teacher_private_retained_stage_checkpoint_review as readers
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_transaction_intent as intents
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _canonical() -> tuple[
    str, inspection.EffectiveOSOwner, tuple[bytes, bytes, bytes, bytes]
]:
    checked = canon._canonical_fork_intent()
    assert checked.registry_before is not None
    assert checked.descriptor_before is not None
    return (
        checked.witness.transaction_id,
        inspection.EffectiveOSOwner("posix_euid", "1000"),
        (
            intents.encode_private_transaction_intent(checked),
            checked.registry_before,
            checked.descriptor_before,
            checked.registry_after,
        ),
    )


def test_exact_canonical_three_checkpoints_are_always_blocked() -> None:
    transaction, owner, (journal, before, sidecar_before, stage) = _canonical()
    checked = intents.decode_private_transaction_intent(journal)
    path = PurePosixPath("/synthetic_fork")
    status = review.PrivateGuardedCanonicalState
    assert (
        review._classify_canonical_images(
            (journal, before, sidecar_before, stage), transaction, owner, path, True
        )
        is status.PREPARED_CANONICAL_BLOCKED
    )
    assert (
        review._classify_canonical_images(
            (journal, stage, sidecar_before, None), transaction, owner, path, False
        )
        is status.DESCRIPTOR_PENDING_CANONICAL_BLOCKED
    )
    assert (
        review._classify_canonical_images(
            (journal, stage, checked.descriptor_after, None),
            transaction,
            owner,
            path,
            False,
        )
        is status.JOURNAL_PENDING_CANONICAL_BLOCKED
    )


def test_pure_path_binding_uses_explicit_platform_lexical_forms() -> None:
    # The canonical fixture records POSIX root bytes regardless of test OS.
    assert review._same_workspace(
        "/synthetic_fork", PurePosixPath("/synthetic_fork"), "posix_euid"
    )
    # Native Windows spelling must NOT masquerade as a POSIX binding.
    assert not review._same_workspace(
        "/synthetic_fork", PureWindowsPath(r"\synthetic_fork"), "posix_euid"
    )
    assert review._same_workspace(
        r"C:\Synthetic\Fork", PureWindowsPath(r"c:\synthetic\fork"), "windows_token_sid"
    )
    assert not review._same_workspace(
        r"C:\Synthetic\Fork",
        PureWindowsPath(r"C:\Synthetic\Different"),
        "windows_token_sid",
    )


def test_noncanonical_journal_cannot_be_a_production_intent() -> None:
    tx, owner, (journal, registry, sidecar, stage) = _canonical()
    status = review.PrivateGuardedCanonicalState
    assert (
        review._classify_canonical_images(
            (journal + b" ", registry, sidecar, stage),
            tx,
            owner,
            PurePosixPath("/synthetic_fork"),
            True,
        )
        is status.JOURNAL_INTENT_REFUSED_PRESERVE
    )
    assert (
        review._classify_canonical_images(
            (journal, registry, sidecar, stage),
            "f0000000-0000-4000-8000-000000000000",
            owner,
            PurePosixPath("/synthetic_fork"),
            True,
        )
        is status.JOURNAL_INTENT_REFUSED_PRESERVE
    )


def test_exact_owner_and_workspace_binding_required() -> None:
    tx, owner, image = _canonical()
    status = review.PrivateGuardedCanonicalState
    assert (
        review._classify_canonical_images(
            image,
            tx,
            inspection.EffectiveOSOwner("posix_euid", "999"),
            PurePosixPath("/synthetic_fork"),
            True,
        )
        is status.OWNER_BINDING_REFUSED_PRESERVE
    )
    assert (
        review._classify_canonical_images(
            image,
            tx,
            owner,
            PurePosixPath("/different-workspace"),
            True,
        )
        is status.OWNER_BINDING_REFUSED_PRESERVE
    )


def test_registry_and_descriptor_mismatch_never_converges() -> None:
    tx, owner, (journal, before, sidecar, stage) = _canonical()
    status = review.PrivateGuardedCanonicalState
    assert (
        review._classify_canonical_images(
            (journal, stage, sidecar, stage),
            tx,
            owner,
            PurePosixPath("/synthetic_fork"),
            True,
        )
        is status.IMAGE_MISMATCH_PRESERVE
    )
    assert (
        review._classify_canonical_images(
            (journal, before, sidecar, None),
            tx,
            owner,
            PurePosixPath("/synthetic_fork"),
            False,
        )
        is status.IMAGE_MISMATCH_PRESERVE
    )


@pytest.mark.parametrize(
    "name",
    [
        "",
        "not-a-transaction",
        "0" * 36,
        "../bad",
        "F0000000-0000-4000-8000-000000000000",
    ],
)
def test_transaction_hint_must_be_canonical_uuid4(name: str) -> None:
    assert not review._valid_tx(name)


def _held_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, str, list[str], tuple[bytes, bytes, bytes, bytes]]:
    tx, _, image = _canonical()
    kind: Literal["windows_token_sid", "posix_euid"] = (
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
    original = inspection.PrivateRootInspection(
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
    monkeypatch.setattr(inspection, "inspect_private_root", lambda: original)
    monkeypatch.setattr(inspection, "_effective_owner", lambda _platform: owner)
    monkeypatch.setattr(descriptor, "_valid_root", lambda root: root == workspace)
    monkeypatch.setattr(
        custody,
        "_probe_existing",
        lambda *_: (
            custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
        ),
    )
    monkeypatch.setattr(
        reconciliation, "_namespace", lambda *_: (frozenset(), frozenset(), True)
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
    def protected(_private: Path, _workspace: Path) -> Iterator[None]:
        assert _private == private and _workspace == workspace
        events.append("entered")
        try:
            yield None
        finally:
            events.append("closed")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", protected)
    # The full held-operation test verifies scope/order rather than synthetic
    # POSIX owner bytes on Windows: pure classifier above verifies exact owner.
    monkeypatch.setattr(
        review,
        "_classify_canonical_images",
        lambda *_: review.PrivateGuardedCanonicalState.PREPARED_CANONICAL_BLOCKED,
    )

    def image_read(*_args: object) -> tuple[bytes, bytes, bytes, bytes]:
        events.append("image")
        return image

    monkeypatch.setattr(exact, "_images", image_read)
    return workspace, tx, events, image


def test_read_only_native_guard_encloses_both_image_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native only")
    workspace, tx, events, _ = _held_setup(monkeypatch)
    result = review.review_existing_guarded_canonical_consistency(workspace, tx)
    assert (
        result.state is review.PrivateGuardedCanonicalState.PREPARED_CANONICAL_BLOCKED
    )
    assert events == ["entered", "image", "image", "closed"]
    assert result.read_only_guard_observed and result.exact_images_rechecked
    assert result.unqualified_requirements == readiness._REQUIRED
    assert not any(
        (
            result.production_mutation_admitted,
            result.operation_owned_write_guard_qualified,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.multi_document_atomic_commit_qualified,
            result.noncooperating_writer_exclusion_qualified,
        )
    )
    assert "Synthetic" not in repr(result)


def test_image_drift_refused_before_guard_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native only")
    workspace, tx, events, image = _held_setup(monkeypatch)
    calls = 0

    def drift(*_args: object) -> tuple[bytes, bytes, bytes, bytes]:
        nonlocal calls
        calls += 1
        events.append("image")
        return image if calls == 1 else (image[0], image[1] + b"x", image[2], image[3])

    monkeypatch.setattr(exact, "_images", drift)
    result = review.review_existing_guarded_canonical_consistency(workspace, tx)
    assert result.state is review.PrivateGuardedCanonicalState.IMAGE_DRIFT_PRESERVE
    assert events[-1] == "closed"


def test_guard_refusal_cannot_escape_as_path_or_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native only")
    workspace, tx, _, _ = _held_setup(monkeypatch)

    @contextmanager
    def deny(_private: Path, _workspace: Path) -> Iterator[None]:
        raise retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.REGISTRY_GUARD_REFUSED
        )
        yield None

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", deny)
    result = review.review_existing_guarded_canonical_consistency(workspace, tx)
    assert result.state is review.PrivateGuardedCanonicalState.GUARD_REFUSED_PRESERVE
    assert "Synthetic" not in repr(result)


def test_bad_transaction_refused_before_native_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("native only")

    def no_probe() -> preconditions.PrivateOperationPreconditionReview:
        raise AssertionError("invalid hint must not probe")

    monkeypatch.setattr(
        preconditions, "review_private_operation_preconditions", no_probe
    )
    result = review.review_existing_guarded_canonical_consistency(
        Path("relative"), "bad"
    )
    assert result.state is review.PrivateGuardedCanonicalState.INVALID_REQUEST_BLOCKED


def test_no_mutation_source_and_teacher_capability() -> None:
    origin = review.__file__
    assert origin is not None
    source = Path(origin).read_text(encoding="utf-8")
    ast.parse(source)
    for bad in (
        "os.replace(",
        "os.unlink(",
        "os.mkdir(",
        "os.makedirs(",
        "retire_private_journal(",
        "activate_notes(",
        "commit_private_workspace_binding(",
    ):
        assert bad not in source
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
