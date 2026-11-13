"""Core #238 3F9: Windows registry-stage namespace mutation, synthetic native mocks."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_image_snapshot as stage_image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_stage_mutation_guard as guard
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
JOURNAL = b"synthetic-canonical-journal"
REGISTRY_BEFORE = b"synthetic-registry-before"
DESCRIPTOR_BEFORE = b"synthetic-descriptor-before"
REGISTRY_AFTER = b"synthetic-registry-after"
Code = guard.PrivateWindowsStageMutationCode
Error = guard.PrivateWindowsStageMutationError


def _intent() -> intents.PrivateTransactionIntent:
    proposal = object.__new__(intents.PrivateTransactionIntent)
    op = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(op, "transaction_id", TX)
    object.__setattr__(op, "operation", witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(proposal, "witness", op)
    object.__setattr__(proposal, "registry_before", REGISTRY_BEFORE)
    object.__setattr__(proposal, "descriptor_before", DESCRIPTOR_BEFORE)
    object.__setattr__(proposal, "registry_after", REGISTRY_AFTER)
    return proposal


def _principal() -> inspection.EffectiveOSOwner:
    return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "private"
    private.mkdir()
    (private / "registry.json").write_bytes(REGISTRY_BEFORE)
    directory = private / "transactions"
    directory.mkdir()
    (directory / (TX + ".json")).write_bytes(JOURNAL)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return private, workspace


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    owner_drift: bool = False,
    journal_bytes: bytes = JOURNAL,
    registry_bytes: bytes = REGISTRY_BEFORE,
    descriptor_bytes: bytes = DESCRIPTOR_BEFORE,
    stage_bytes: bytes = REGISTRY_AFTER,
    anchor_refusal: bool = False,
    inventory_refusal: bool = False,
) -> None:
    calls = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal calls
        calls += 1
        events.append("owner")
        if owner_drift and calls > 1:
            return inspection.EffectiveOSOwner("windows_token_sid", "different")
        return _principal()

    monkeypatch.setattr(ordered, "_owner", owner)

    def hold(label: str, *, fail: bool = False) -> object:
        @contextmanager
        def scope(*_args: object) -> Iterator[None]:
            events.append(label + "-enter")
            try:
                yield
                if fail:
                    raise journal_guard.RetainedJournalGuardError(
                        journal_guard.RetainedJournalGuardCode.CHANGED_DURING_SCOPE
                    )
            finally:
                events.append(label + "-exit")

        return scope

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", hold("locks"))
    monkeypatch.setattr(registry_guard, "_held_windows_registry", hold("registry"))
    monkeypatch.setattr(
        descriptor_guard, "_held_windows_descriptor", hold("descriptor")
    )
    monkeypatch.setattr(
        journal_guard, "_held_windows", hold("journal", fail=anchor_refusal)
    )
    monkeypatch.setattr(guard, "_hold_native_root", hold("private-root"))

    def journal_read(
        _directory: Path, _tx: str, _owner: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        events.append("journal-read")
        assert _tx == TX and _owner == _principal()
        return journal.PrivateJournalImageReview(
            journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            journal_bytes,
        )

    def registry_read(
        _root: Path, _owner: inspection.EffectiveOSOwner
    ) -> registry_image.PrivateRegistryImageReview:
        events.append("registry-read")
        return registry_image.PrivateRegistryImageReview(
            registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            registry_bytes,
        )

    def descriptor_read(_root: Path) -> descriptor_image.PrivateDescriptorImageReview:
        events.append("descriptor-read")
        return descriptor_image.PrivateDescriptorImageReview(
            descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            descriptor_bytes,
        )

    def stage_read(
        _root: Path, _tx: str, _owner: inspection.EffectiveOSOwner
    ) -> stage_image.PrivateRegistryStageImageReview:
        events.append("stage-read")
        return stage_image.PrivateRegistryStageImageReview(
            stage_image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED,
            "synthetic",
            stage_bytes,
        )

    def inventory_scan(
        root: Path, _owner: inspection.EffectiveOSOwner
    ) -> inventory.PrivateRegistryStageInventoryState:
        events.append("inventory-read")
        if inventory_refusal:
            return inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        entries = {entry.name for entry in root.iterdir()}
        stages = {name for name in entries if "registry-stage" in name.casefold()}
        if stages == {"." + TX + ".registry-stage"}:
            return inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED
        if stages:
            return inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY
        return inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED

    monkeypatch.setattr(journal, "_read_windows", journal_read)
    monkeypatch.setattr(registry_image, "_read_windows", registry_read)
    monkeypatch.setattr(descriptor_image, "_read_windows", descriptor_read)
    monkeypatch.setattr(stage_image, "_read_windows", stage_read)
    monkeypatch.setattr(inventory, "_scan_windows", inventory_scan)


def test_matching_journal_and_exact_one_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    private, workspace = _roots(tmp_path)
    with guard._hold_windows_expected_stage_create(
        private, workspace, _intent(), JOURNAL
    ):
        (private / ("." + TX + ".registry-stage")).write_bytes(REGISTRY_AFTER)
        events.append("created")
    assert events.index("created") > events.index("journal-read")
    assert events.count("journal-read") == 4
    assert events.count("stage-read") == 2
    assert events.count("registry-read") == 4
    assert events.count("descriptor-read") == 4
    assert events[0] == "locks-enter"
    assert events[-1] == "locks-exit"
    assert (private / ("." + TX + ".registry-stage")).read_bytes() == REGISTRY_AFTER


@pytest.mark.parametrize(
    "preexisting", [".bad.registry-stage", "." + TX + ".registry-stage"]
)
def test_pending_stage_refused_before_yield(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preexisting: str
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    private, workspace = _roots(tmp_path)
    (private / preexisting).write_bytes(b"preserve")
    with pytest.raises(Error) as exc:
        with guard._hold_windows_expected_stage_create(
            private, workspace, _intent(), JOURNAL
        ):
            pytest.fail("Must not permit pre-existing stages")
    assert exc.value.code in {
        Code.STAGE_INVENTORY_UNQUALIFIED,
        Code.UNEXPECTED_MUTATION,
    }
    assert (private / preexisting).read_bytes() == b"preserve"


@pytest.mark.parametrize("which", ["none", "wrong-name", "extra", "removed-existing"])
def test_exact_one_new_entry_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    private, workspace = _roots(tmp_path)
    stage = private / ("." + TX + ".registry-stage")
    with pytest.raises(Error) as exc:
        with guard._hold_windows_expected_stage_create(
            private, workspace, _intent(), JOURNAL
        ):
            if which != "none":
                stage.write_bytes(REGISTRY_AFTER)
            if which == "wrong-name":
                stage.unlink()
                (private / ".other.registry-stage").write_bytes(REGISTRY_AFTER)
            elif which == "extra":
                (private / "extraneous.txt").write_bytes(b"preserve")
            elif which == "removed-existing":
                (private / "registry.json").unlink()
    assert exc.value.code is (
        Code.MISSING_EXPECTED_STAGE if which == "none" else Code.UNEXPECTED_MUTATION
    )
    if which == "extra":
        assert (private / "extraneous.txt").read_bytes() == b"preserve"


@pytest.mark.parametrize("what", ["journal", "registry", "descriptor", "stage"])
def test_bytes_mismatch_refuses_and_preserves_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, what: str
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        journal_bytes=b"wrong" if what == "journal" else JOURNAL,
        registry_bytes=b"wrong" if what == "registry" else REGISTRY_BEFORE,
        descriptor_bytes=b"wrong" if what == "descriptor" else DESCRIPTOR_BEFORE,
        stage_bytes=b"wrong" if what == "stage" else REGISTRY_AFTER,
    )
    private, workspace = _roots(tmp_path)
    stage = private / ("." + TX + ".registry-stage")
    with pytest.raises(Error) as exc:
        with guard._hold_windows_expected_stage_create(
            private, workspace, _intent(), JOURNAL
        ):
            stage.write_bytes(REGISTRY_AFTER)
    expected = {
        "journal": Code.JOURNAL_UNQUALIFIED,
        "registry": Code.BEFORE_IMAGE_MISMATCH,
        "descriptor": Code.BEFORE_IMAGE_MISMATCH,
        "stage": Code.STAGE_UNQUALIFIED,
    }
    assert exc.value.code is expected[what]
    if what == "stage":
        assert stage.read_bytes() == REGISTRY_AFTER


def test_pending_unrelated_journal_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    private, workspace = _roots(tmp_path)
    (private / "transactions" / "other.json").write_bytes(b"preserve")
    with pytest.raises(Error) as exc:
        with guard._hold_windows_expected_stage_create(
            private, workspace, _intent(), JOURNAL
        ):
            pytest.fail("Pending recovery must refuse")
    assert exc.value.code is Code.PENDING_RECOVERY_REQUIRED
    assert (private / "transactions" / "other.json").read_bytes() == b"preserve"


@pytest.mark.parametrize("failure", ["owner", "inventory", "anchor"])
def test_fail_closed_without_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        owner_drift=failure == "owner",
        inventory_refusal=failure == "inventory",
        anchor_refusal=failure == "anchor",
    )
    private, workspace = _roots(tmp_path)
    stage = private / ("." + TX + ".registry-stage")
    with pytest.raises((Error, journal_guard.RetainedJournalGuardError)):
        with guard._hold_windows_expected_stage_create(
            private, workspace, _intent(), JOURNAL
        ):
            if failure == "anchor":
                stage.write_bytes(REGISTRY_AFTER)
            elif failure == "owner":
                pytest.fail("Owner drift must block")
            else:
                pytest.fail("Inventory must block")
    if failure == "anchor":
        assert stage.read_bytes() == REGISTRY_AFTER


def test_unsupported_platform_before_native_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _roots(tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(Error) as exc:
        with guard.hold_expected_windows_private_registry_stage_creation(
            _intent(), private, workspace
        ):
            pytest.fail("Unsupported platform")
    assert exc.value.code is Code.UNSUPPORTED


def test_bad_intent_refused_before_native_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _roots(tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(Error) as exc:
        with guard.hold_expected_windows_private_registry_stage_creation(
            cast(intents.PrivateTransactionIntent, object()), private, workspace
        ):
            pytest.fail("Bad intent must refuse")
    assert exc.value.code is Code.INVALID_REQUEST


def test_notes_capability_not_exposed() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(guard, "commit_private_binding")
    assert not hasattr(guard, "replace_registry")
    assert not hasattr(guard, "delete_stale_stage")
    assert not hasattr(guard, "create_notes_record")
