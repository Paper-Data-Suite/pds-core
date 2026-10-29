"""#238 Slice 3E4: bounded native read-only pending intent image snapshots."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator, Literal

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as snapshot
from pds_core import _teacher_private_journal_provision as provision
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_journal_guard as retained
from pds_core import _teacher_private_transaction_intent as intent
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_provision as windows
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _euid() -> int:
    getter = getattr(os, "geteuid", None)
    assert getter is not None
    uid: int = getter()
    return uid


TX_ID = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
OTHER_TX = "3b12f04a-9a5d-4c04-aa61-d8c67850fa4b"
ASSOC = "6fb32a62-83e2-43f6-9823-687801593c8b"


def _canonical(kind: Literal["windows_token_sid", "posix_euid"], owner: str) -> bytes:
    descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(ASSOC)
    )
    root = (
        "C:\\synthetic_workspace_a"
        if kind == "windows_token_sid"
        else "/synthetic_workspace_a"
    )
    registry = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner(kind, owner),
            1,
            (metadata.PrivateRegistryBinding(ASSOC, 1, root),),
        )
    )
    operation = witness.PrivateTransactionWitness(
        witness.PrivateBindingOperation.INITIALIZE,
        TX_ID,
        None,
        ASSOC,
        0,
        1,
        None,
        hashlib.sha256(descriptor).hexdigest(),
        None,
        hashlib.sha256(registry).hexdigest(),
    )
    return intent.encode_private_transaction_intent(
        intent.PrivateTransactionIntent(operation, None, descriptor, None, registry)
    )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "BAD",
        "A" * 36,
        "x" * 120,
        "00000000-0000-0000-0000-000000000000",
        "E3BA2E44-3F47-4588-9023-44CBB799D5A8",
        None,
        3,
        True,
        b"bytes",
    ],
    ids=[
        "empty",
        "bad",
        "letters",
        "oversized",
        "nil",
        "uppercase",
        "none",
        "integer",
        "bool",
        "bytes",
    ],
)
def test_invalid_transaction_ids_refused(value: object) -> None:
    assert not snapshot._valid_id(value)
    assert snapshot._valid_id(TX_ID)


def test_checked_canonical_bytes_only() -> None:
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    raw = _canonical("posix_euid", "1000")
    observed = snapshot._checked_image(raw, TX_ID, owner)
    assert observed.state is snapshot.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
    assert observed.image == raw
    assert repr(raw) not in repr(observed)
    assert TX_ID not in repr(observed)
    assert "/synthetic_workspace" not in repr(observed)
    with pytest.raises(FrozenInstanceError):
        setattr(observed, "state", snapshot.PrivateJournalImageState.IO_ERROR)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (b"", snapshot.PrivateJournalImageState.INVALID_JOURNAL),
        (b"not-json", snapshot.PrivateJournalImageState.INVALID_JOURNAL),
        (b"{}", snapshot.PrivateJournalImageState.INVALID_JOURNAL),
        (
            b"x" * (intent.MAX_INTENT_BYTES + 1),
            snapshot.PrivateJournalImageState.INVALID_JOURNAL,
        ),
    ],
    ids=["empty", "corrupt", "shape", "oversized"],
)
def test_invalid_images_rejected(
    mutation: bytes, expected: snapshot.PrivateJournalImageState
) -> None:
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    assert snapshot._checked_image(mutation, TX_ID, owner).state is expected


def test_mismatched_transaction_and_owner_refused() -> None:
    raw = _canonical("posix_euid", "1000")
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    assert (
        snapshot._checked_image(raw, OTHER_TX, owner).state
        is snapshot.PrivateJournalImageState.INVALID_JOURNAL
    )
    other = inspection.EffectiveOSOwner("posix_euid", "1001")
    assert (
        snapshot._checked_image(raw, TX_ID, other).state
        is snapshot.PrivateJournalImageState.REFUSED_PROTECTION
    )
    cross_kind = inspection.EffectiveOSOwner(
        "windows_token_sid", "S-1-5-21-11-22-33-44"
    )
    assert (
        snapshot._checked_image(raw, TX_ID, cross_kind).state
        is snapshot.PrivateJournalImageState.REFUSED_PROTECTION
    )


def test_invalid_request_before_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*_args: object) -> Iterator[None]:
        raise AssertionError("Guard reached for invalid request")
        yield

    monkeypatch.setattr(retained, "_hold_existing_retained_journal_guard", unexpected)
    assert snapshot.inspect_existing_private_transaction_image(
        tmp_path, tmp_path, "bad"
    ).state is (snapshot.PrivateJournalImageState.INVALID_REQUEST)


def test_no_new_capability_or_writer() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(snapshot, "commit_private_transaction")
    assert not hasattr(snapshot, "write_private_transaction_image")
    assert not hasattr(snapshot, "create_notes_store")
    for state in snapshot.PrivateJournalImageState:
        assert TX_ID not in snapshot._result(state).message
        assert "synthetic_workspace" not in snapshot._result(state).message


@pytest.fixture
def linux_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    if sys.platform != "linux" or getattr(os, "geteuid", None) is None or _euid() == 0:
        pytest.skip("requires native non-root Linux")
    directory = tmp_path / "private" / "transactions"
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    monkeypatch.setattr(
        posix,
        "_open_verified_parent",
        lambda path, _uid: (os.open(path, os.O_RDONLY | os.O_DIRECTORY), None),
    )
    monkeypatch.setattr(posix, "_acl_absent", lambda _fd: None)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return directory


def _native_linux_owner() -> inspection.EffectiveOSOwner:
    return inspection.EffectiveOSOwner("posix_euid", str(_euid()))


def test_linux_native_canonical_read_no_write(linux_directory: Path) -> None:
    raw = _canonical("posix_euid", str(_euid()))
    name = linux_directory / f"{TX_ID}.json"
    name.write_bytes(raw)
    name.chmod(0o600)
    before = name.stat().st_mtime_ns
    observed = snapshot._read_linux(linux_directory, TX_ID, _native_linux_owner())
    assert observed.state is snapshot.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
    assert observed.image == raw
    assert name.read_bytes() == raw and name.stat().st_mtime_ns == before
    assert stat.S_IMODE(name.stat().st_mode) == 0o600


def test_linux_native_missing_does_not_create(linux_directory: Path) -> None:
    observed = snapshot._read_linux(linux_directory, TX_ID, _native_linux_owner())
    assert observed.state is snapshot.PrivateJournalImageState.MISSING_REVIEW_REQUIRED
    assert not list(linux_directory.iterdir())


def test_linux_native_corrupt_preserved(linux_directory: Path) -> None:
    path = linux_directory / f"{TX_ID}.json"
    path.write_bytes(b"corrupt-but-preserved")
    path.chmod(0o600)
    assert snapshot._read_linux(
        linux_directory, TX_ID, _native_linux_owner()
    ).state is (snapshot.PrivateJournalImageState.INVALID_JOURNAL)
    assert path.read_bytes() == b"corrupt-but-preserved"


def test_linux_native_unprotected_refused(linux_directory: Path) -> None:
    path = linux_directory / f"{TX_ID}.json"
    path.write_bytes(b"private")
    path.chmod(0o644)
    assert snapshot._read_linux(
        linux_directory, TX_ID, _native_linux_owner()
    ).state is (snapshot.PrivateJournalImageState.REFUSED_PROTECTION)
    assert path.read_bytes() == b"private"


def test_linux_native_symlink_refused(linux_directory: Path) -> None:
    target = linux_directory / "secret"
    target.write_bytes(b"unchanged")
    (linux_directory / f"{TX_ID}.json").symlink_to(target)
    state = snapshot._read_linux(linux_directory, TX_ID, _native_linux_owner()).state
    assert state in {
        snapshot.PrivateJournalImageState.REFUSED_PROTECTION,
        snapshot.PrivateJournalImageState.IO_ERROR,
    }
    assert target.read_bytes() == b"unchanged"


def test_linux_native_replaced_during_read_refused(
    linux_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = linux_directory / f"{TX_ID}.json"
    path.write_bytes(_canonical("posix_euid", str(_euid())))
    path.chmod(0o600)
    original = os.read
    replaced = False

    def read_and_replace(fd: int, size: int) -> bytes:
        nonlocal replaced
        data = original(fd, size)
        if not replaced:
            replaced = True
            path.unlink()
            path.write_bytes(data)
            path.chmod(0o600)
        return data

    monkeypatch.setattr(os, "read", read_and_replace)
    assert snapshot._read_linux(
        linux_directory, TX_ID, _native_linux_owner()
    ).state is (snapshot.PrivateJournalImageState.CHANGED_DURING_READ)


def test_linux_native_other_owner_refused(linux_directory: Path) -> None:
    foreign = inspection.EffectiveOSOwner("posix_euid", str(_euid() + 1))
    assert snapshot._read_linux(linux_directory, TX_ID, foreign).state is (
        snapshot.PrivateJournalImageState.OWNER_CHANGED
    )


def test_guard_exit_refusal_overrides_matching_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(provision, "_requested_transactions_dir", lambda *_: True)
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    monkeypatch.setattr(ordered, "_owner", lambda: owner)
    raw = _canonical("posix_euid", "1000")
    monkeypatch.setattr(
        snapshot,
        "_read_linux",
        lambda *_: snapshot._result(
            snapshot.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED, raw
        ),
    )

    @contextmanager
    def fail_on_exit(*_args: object) -> Iterator[None]:
        yield
        raise retained.RetainedJournalGuardError(
            retained.RetainedJournalGuardCode.CHANGED_DURING_SCOPE
        )

    monkeypatch.setattr(retained, "_hold_existing_retained_journal_guard", fail_on_exit)
    observed = snapshot.inspect_existing_private_transaction_image(
        tmp_path, tmp_path, TX_ID
    )
    assert observed.state is snapshot.PrivateJournalImageState.RETAINED_GUARD_REFUSED
    assert observed.image is None


def test_owner_changed_inside_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(provision, "_requested_transactions_dir", lambda *_: True)
    first = inspection.EffectiveOSOwner("posix_euid", "1000")
    second = inspection.EffectiveOSOwner("posix_euid", "1001")
    owners = iter((first, second))
    monkeypatch.setattr(ordered, "_owner", lambda: next(owners))
    monkeypatch.setattr(
        snapshot,
        "_read_linux",
        lambda *_: snapshot._result(
            snapshot.PrivateJournalImageState.MISSING_REVIEW_REQUIRED
        ),
    )

    @contextmanager
    def guard(*_args: object) -> Iterator[None]:
        yield

    monkeypatch.setattr(retained, "_hold_existing_retained_journal_guard", guard)
    result = snapshot.inspect_existing_private_transaction_image(
        tmp_path, tmp_path, TX_ID
    )
    assert result.state is snapshot.PrivateJournalImageState.OWNER_CHANGED


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_native_protected_journal_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = inspection._effective_owner("win32")
    kernel, advapi = windows._windows_api()
    if not windows._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Requires fixed NTFS/ReFS")
    parent = tmp_path
    for segment in ("Paper Data Suite", "private", "notes", "v1", "transactions"):
        parent = parent / segment
        created, code = windows._create_directory_explicit_dacl(
            kernel, advapi, parent, owner.value
        )
        assert created, f"Protected fixture setup refused ({code})"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    raw = _canonical("windows_token_sid", owner.value)
    result = provision.create_private_transaction_intent_file(parent, raw)
    assert (
        result.state
        is provision.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    image = snapshot._read_windows(parent, TX_ID, owner)
    assert image.state is snapshot.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
    assert image.image == raw
    assert (parent / f"{TX_ID}.json").read_bytes() == raw
