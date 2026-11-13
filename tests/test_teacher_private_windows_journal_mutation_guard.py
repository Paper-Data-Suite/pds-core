"""Core #238 3F8: Windows expected-journal mutation scope, synthetic native mocks."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_image_snapshot as descriptor_image
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_mutation_aware_journal_guard as common
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_journal_mutation_guard as win_guard
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
RAW = b"synthetic-journal-intent"
Code = common.PrivateJournalMutationGuardCode
Error = common.PrivateJournalMutationGuardError


def _proposed() -> intents.PrivateTransactionIntent:
    intent = object.__new__(intents.PrivateTransactionIntent)
    action = object.__new__(witness.PrivateTransactionWitness)
    object.__setattr__(action, "transaction_id", TX)
    object.__setattr__(action, "operation", witness.PrivateBindingOperation.FORK_COPY)
    object.__setattr__(intent, "witness", action)
    object.__setattr__(intent, "registry_before", b"registry-before")
    object.__setattr__(intent, "descriptor_before", b"descriptor-before")
    return intent


def _owner() -> inspection.EffectiveOSOwner:
    return inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    journal_image: bytes = RAW,
    registry_before: bytes = b"registry-before",
    descriptor_before: bytes = b"descriptor-before",
    owner_drift: bool = False,
    journal_guard_exit: bool = False,
) -> None:
    calls = 0

    def owner() -> inspection.EffectiveOSOwner:
        nonlocal calls
        calls += 1
        events.append("owner")
        if owner_drift and calls > 1:
            return inspection.EffectiveOSOwner("windows_token_sid", "different")
        return _owner()

    monkeypatch.setattr(ordered, "_owner", owner)

    def holder(label: str, fail_on_exit: bool = False) -> object:
        @contextmanager
        def scope(*_args: object) -> Iterator[None]:
            events.append(label + "-open")
            try:
                yield
                if fail_on_exit:
                    raise journal_guard.RetainedJournalGuardError(
                        journal_guard.RetainedJournalGuardCode.CHANGED_DURING_SCOPE
                    )
            finally:
                events.append(label + "-close")

        return scope

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", holder("locks"))
    monkeypatch.setattr(registry_guard, "_held_windows_registry", holder("registry"))
    monkeypatch.setattr(
        descriptor_guard, "_held_windows_descriptor", holder("descriptor")
    )
    monkeypatch.setattr(
        journal_guard,
        "_held_windows",
        holder("journal", fail_on_exit=journal_guard_exit),
    )

    def read_registry(
        _root: Path, _principal: inspection.EffectiveOSOwner
    ) -> registry_image.PrivateRegistryImageReview:
        events.append("registry-read")
        assert _principal == _owner()
        return registry_image.PrivateRegistryImageReview(
            registry_image.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            registry_before,
        )

    def read_descriptor(_root: Path) -> descriptor_image.PrivateDescriptorImageReview:
        events.append("descriptor-read")
        return descriptor_image.PrivateDescriptorImageReview(
            descriptor_image.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            descriptor_before,
        )

    def read_journal(
        _root: Path, _tx: str, _principal: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        events.append("journal-read")
        assert _tx == TX and _principal == _owner()
        return journal.PrivateJournalImageReview(
            journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            journal_image,
        )

    monkeypatch.setattr(registry_image, "_read_windows", read_registry)
    monkeypatch.setattr(descriptor_image, "_read_windows", read_descriptor)
    monkeypatch.setattr(journal, "_read_windows", read_journal)


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "private"
    directory = private / "transactions"
    directory.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return private, workspace


def test_expected_single_file_preserved_and_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    private, workspace = _roots(tmp_path)
    with win_guard._hold_windows_expected_journal_create(
        private, workspace, _proposed(), RAW
    ):
        (private / "transactions" / (TX + ".json")).write_bytes(RAW)
        events.append("created")
    assert events.index("created") > events.index("descriptor-read")
    assert events.count("journal-read") == 2
    assert events.count("registry-read") == 4
    assert events.count("descriptor-read") == 4
    assert events[-1] == "locks-close"
    assert (private / "transactions" / (TX + ".json")).read_bytes() == RAW


@pytest.mark.parametrize("initial", ["pending.json", ".bad", TX + ".json"])
def test_initial_entries_refuse_before_yield(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, initial: str
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    private, workspace = _roots(tmp_path)
    (private / "transactions" / initial).write_bytes(b"untouched")
    with pytest.raises(Error) as error:
        with win_guard._hold_windows_expected_journal_create(
            private, workspace, _proposed(), RAW
        ):
            pytest.fail("Must not yield with pending entries")
    assert error.value.code is Code.PENDING_RECOVERY_REQUIRED
    assert (private / "transactions" / initial).read_bytes() == b"untouched"
    assert "registry-read" not in events


@pytest.mark.parametrize("create", ["none", "extra", "wrong-name"])
def test_exact_one_new_name_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, create: str
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events)
    private, workspace = _roots(tmp_path)
    directory = private / "transactions"
    with pytest.raises(Error) as error:
        with win_guard._hold_windows_expected_journal_create(
            private, workspace, _proposed(), RAW
        ):
            if create != "none":
                (directory / (TX + ".json")).write_bytes(RAW)
            if create == "extra":
                (directory / "unrelated.json").write_bytes(b"uncleared")
            if create == "wrong-name":
                (directory / (TX + ".json")).unlink()
                (directory / "other.json").write_bytes(RAW)
    expected = (
        Code.MISSING_EXPECTED_ENTRY if create == "none" else Code.UNEXPECTED_MUTATION
    )
    assert error.value.code is expected
    if create == "extra":
        assert (directory / "unrelated.json").read_bytes() == b"uncleared"


def test_journal_bytes_mismatch_refused_without_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, journal_image=b"mismatch")
    private, workspace = _roots(tmp_path)
    with pytest.raises(Error) as error:
        with win_guard._hold_windows_expected_journal_create(
            private, workspace, _proposed(), RAW
        ):
            (private / "transactions" / (TX + ".json")).write_bytes(RAW)
    assert error.value.code is Code.FILE_UNQUALIFIED
    assert (private / "transactions" / (TX + ".json")).exists()


@pytest.mark.parametrize("wrong", ["registry", "descriptor"])
def test_before_image_mismatch_refused_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong: str
) -> None:
    events: list[str] = []
    _configure(
        monkeypatch,
        events,
        registry_before=b"wrong" if wrong == "registry" else b"registry-before",
        descriptor_before=b"wrong" if wrong == "descriptor" else b"descriptor-before",
    )
    private, workspace = _roots(tmp_path)
    with pytest.raises(Error) as error:
        with win_guard._hold_windows_expected_journal_create(
            private, workspace, _proposed(), RAW
        ):
            pytest.fail("Wrong before bytes must block")
    assert error.value.code is Code.RETAINED_ANCHOR_REFUSED
    assert list((private / "transactions").iterdir()) == []


def test_owner_changed_refuses_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, owner_drift=True)
    private, workspace = _roots(tmp_path)
    with pytest.raises(Error) as error:
        with win_guard._hold_windows_expected_journal_create(
            private, workspace, _proposed(), RAW
        ):
            pytest.fail("Owner drift before yield must refuse")
    assert error.value.code is Code.OWNER_CHANGED
    assert list((private / "transactions").iterdir()) == []


def test_native_guard_exit_failure_preserves_created_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _configure(monkeypatch, events, journal_guard_exit=True)
    private, workspace = _roots(tmp_path)
    with pytest.raises(journal_guard.RetainedJournalGuardError):
        with win_guard._hold_windows_expected_journal_create(
            private, workspace, _proposed(), RAW
        ):
            (private / "transactions" / (TX + ".json")).write_bytes(RAW)
    assert (private / "transactions" / (TX + ".json")).exists()


def test_unsupported_platform_refuses_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _roots(tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(Error) as error:
        with win_guard.hold_expected_windows_private_journal_creation(
            _proposed(), private, workspace
        ):
            pytest.fail("Unsupported platform must not enter")
    assert error.value.code is Code.UNSUPPORTED


def test_invalid_request_refuses_before_native_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, workspace = _roots(tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(Error) as error:
        with win_guard.hold_expected_windows_private_journal_creation(
            cast(intents.PrivateTransactionIntent, object()), private, workspace
        ):
            pytest.fail("Invalid intent must refuse")
    assert error.value.code is Code.INVALID_REQUEST


def test_no_notes_write_or_commit_capability() -> None:
    assert not hasattr(win_guard, "commit_private_binding")
    assert not hasattr(win_guard, "replace_registry")
    assert not hasattr(win_guard, "delete_journal")
    assert not hasattr(win_guard, "create_notes_record")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
