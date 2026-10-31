"""Core #238 Slice 3F4: stage-image exact bytes under retained native guards."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_registry_stage_image_snapshot as image
from pds_core import _teacher_private_registry_stage_inventory as inventory
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
AFTER = b"synthetic after image"


def _owner() -> inspection.EffectiveOSOwner:
    if sys.platform == "win32":
        return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _proposal() -> intents.PrivateTransactionIntent:
    proposal = object.__new__(intents.PrivateTransactionIntent)
    action = object.__new__(witness.PrivateTransactionWitness)
    values = {
        "transaction_id": TX,
        "operation": witness.PrivateBindingOperation.FORK_COPY,
        "association_before": "6fb32a62-83e2-43f6-9823-687801593c8b",
        "association_after": "e3c6f36c-2a12-4420-96ce-1f137a312c18",
        "registry_revision_before": 1,
        "registry_revision_after": 2,
        "descriptor_sha256_before": "a" * 64,
        "descriptor_sha256_after": "b" * 64,
        "registry_sha256_before": "c" * 64,
        "registry_sha256_after": "d" * 64,
    }
    for key, value in values.items():
        object.__setattr__(action, key, value)
    object.__setattr__(proposal, "witness", action)
    object.__setattr__(proposal, "descriptor_before", b"synthetic before")
    object.__setattr__(proposal, "descriptor_after", b"synthetic after")
    object.__setattr__(proposal, "registry_before", b"synthetic prior registry")
    object.__setattr__(proposal, "registry_after", AFTER)
    return proposal


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    first: bytes = AFTER,
    second: bytes = AFTER,
    scan: inventory.PrivateRegistryStageInventoryState = inventory.PrivateRegistryStageInventoryState.STAGES_PRESENT_RECOVERY_REQUIRED,
    second_scan: inventory.PrivateRegistryStageInventoryState | None = None,
    reader_state: image.PrivateRegistryStageImageState = image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED,
    exit_failure: retained.RetainedDescriptorGuardCode | None = None,
    enter_failure: retained.RetainedDescriptorGuardCode | None = None,
    change_owner: bool = False,
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda _: b"canonical"
    )
    proposed = _proposal()
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: proposed
    )

    @contextmanager
    def guarded(_private: Path, _workspace: Path) -> Iterator[None]:
        events.append("enter")
        if enter_failure is not None:
            raise retained.RetainedDescriptorGuardError(enter_failure)
        try:
            yield
            if exit_failure is not None:
                raise retained.RetainedDescriptorGuardError(exit_failure)
        finally:
            events.append("exit")

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guarded)
    owner_count = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal owner_count
        owner_count += 1
        events.append("owner")
        expected = _owner()
        if change_owner and owner_count > 1:
            return inspection.EffectiveOSOwner(expected.kind, "different")
        return expected

    scans = 0

    def census(
        _root: Path, current: inspection.EffectiveOSOwner
    ) -> inventory.PrivateRegistryStageInventoryState:
        nonlocal scans
        assert current == _owner()
        scans += 1
        events.append("inventory")
        return second_scan if second_scan is not None and scans == 2 else scan

    reads = 0

    def native(
        _root: Path, id_value: str, current: inspection.EffectiveOSOwner
    ) -> image.PrivateRegistryStageImageReview:
        nonlocal reads
        assert id_value == TX and current == _owner()
        reads += 1
        events.append("read")
        return image.PrivateRegistryStageImageReview(
            reader_state,
            "synthetic",
            (first if reads == 1 else second)
            if reader_state
            is image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
            else None,
        )

    monkeypatch.setattr(ordered, "_owner", owner)
    monkeypatch.setattr(image, "_inventory", census)
    monkeypatch.setattr(image, "_native_image", native)


def _call(tmp_path: Path) -> image.PrivateRegistryStageImageReview:
    return image.inspect_existing_private_registry_stage_image(
        _proposal(), tmp_path / "private", tmp_path / "workspace"
    )


def test_matching_stage_remains_non_authorizing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    result = _call(tmp_path)
    assert (
        result.state
        is image.PrivateRegistryStageImageState.MATCHING_AFTER_REVIEW_REQUIRED
    )
    assert result.image is None
    assert events == [
        "enter",
        "owner",
        "inventory",
        "read",
        "read",
        "inventory",
        "owner",
        "exit",
    ]
    assert list(tmp_path.iterdir()) == []
    assert TX not in repr(result) and str(tmp_path) not in result.message


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (AFTER, AFTER + b"x", image.PrivateRegistryStageImageState.IMAGES_CHANGED),
        (
            AFTER + b"x",
            AFTER + b"x",
            image.PrivateRegistryStageImageState.AFTER_IMAGE_MISMATCH,
        ),
    ],
)
def test_exact_byte_drift_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first: bytes,
    second: bytes,
    expected: image.PrivateRegistryStageImageState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, first=first, second=second)
    assert _call(tmp_path).state is expected
    assert "exit" in events


@pytest.mark.parametrize(
    "state",
    [
        image.PrivateRegistryStageImageState.MISSING,
        image.PrivateRegistryStageImageState.INVALID_STAGE,
        image.PrivateRegistryStageImageState.REFUSED_PROTECTION,
        image.PrivateRegistryStageImageState.ACCESS_DENIED,
        image.PrivateRegistryStageImageState.CHANGED_DURING_READ,
        image.PrivateRegistryStageImageState.REFUSED_BACKING,
    ],
)
def test_native_refusals_never_promote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: image.PrivateRegistryStageImageState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, reader_state=state)
    assert _call(tmp_path).state is state
    assert events.count("read") == 1


@pytest.mark.parametrize(
    "scan",
    [
        inventory.PrivateRegistryStageInventoryState.EMPTY_REVIEW_REQUIRED,
        inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
        inventory.PrivateRegistryStageInventoryState.ENTRIES_CHANGED,
        inventory.PrivateRegistryStageInventoryState.ACCESS_DENIED,
    ],
)
def test_inventory_refusals_stop_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scan: inventory.PrivateRegistryStageInventoryState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, scan=scan)
    assert (
        _call(tmp_path).state
        is image.PrivateRegistryStageImageState.INVENTORY_UNQUALIFIED
    )
    assert "read" not in events


def test_second_inventory_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        second_scan=inventory.PrivateRegistryStageInventoryState.UNQUALIFIED_STAGE_ENTRY,
    )
    assert (
        _call(tmp_path).state
        is image.PrivateRegistryStageImageState.INVENTORY_UNQUALIFIED
    )
    assert events.count("read") == 2


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
            image.PrivateRegistryStageImageState.OWNER_CHANGED,
        ),
        (
            retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE,
            image.PrivateRegistryStageImageState.OWNER_UNAVAILABLE,
        ),
        (
            retained.RetainedDescriptorGuardCode.UNSUPPORTED,
            image.PrivateRegistryStageImageState.UNSUPPORTED,
        ),
        (
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
            image.PrivateRegistryStageImageState.GUARD_REFUSED,
        ),
    ],
)
def test_guard_exit_refusal_overrides_matching_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: retained.RetainedDescriptorGuardCode,
    expected: image.PrivateRegistryStageImageState,
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, exit_failure=code)
    assert _call(tmp_path).state is expected
    assert events[-1] == "exit"


def test_guard_entry_refusal_prevents_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        enter_failure=retained.RetainedDescriptorGuardCode.REFUSED_PATH,
    )
    assert _call(tmp_path).state is image.PrivateRegistryStageImageState.GUARD_REFUSED
    assert events == ["enter"]


def test_owner_change_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, change_owner=True)
    assert _call(tmp_path).state is image.PrivateRegistryStageImageState.OWNER_CHANGED


def test_stage_name_must_be_canonical_uuid4() -> None:
    assert image._stage_name(TX) == f".{TX}.registry-stage"
    assert image._stage_name(TX.upper()) is None
    assert image._stage_name("../../registry.json") is None
    assert image._stage_name("not-a-uuid") is None


def test_invalid_and_initialize_refuse_before_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    proposal = _proposal()
    object.__setattr__(
        proposal.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _: proposal
    )
    assert (
        image.inspect_existing_private_registry_stage_image(
            proposal, tmp_path / "private", tmp_path / "workspace"
        ).state
        is image.PrivateRegistryStageImageState.INITIALIZATION_REFUSED
    )
    assert (
        image.inspect_existing_private_registry_stage_image(
            cast(intents.PrivateTransactionIntent, "foreign"),
            tmp_path / "private",
            tmp_path / "workspace",
        ).state
        is image.PrivateRegistryStageImageState.INVALID_REQUEST
    )
    assert events == []


def test_unsupported_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert _call(tmp_path).state is image.PrivateRegistryStageImageState.UNSUPPORTED
    assert events == []


def test_canonical_image_maps_owner_and_schema_refusals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def checked(
        _raw: bytes, _owner: inspection.EffectiveOSOwner
    ) -> registry_image.PrivateRegistryImageReview:
        return registry_image.PrivateRegistryImageReview(
            registry_image.PrivateRegistryImageState.REFUSED_PROTECTION, "synthetic"
        )

    monkeypatch.setattr(registry_image, "_checked_image", checked)
    assert (
        image._canonical_image(AFTER, _owner()).state
        is image.PrivateRegistryStageImageState.REFUSED_PROTECTION
    )


def test_no_published_notes_or_write_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(image, "replace_registry")
    assert not hasattr(image, "commit_private_binding")
    assert not hasattr(image, "admit_durable_transaction")
    assert not hasattr(image, "recover_private_transaction")
