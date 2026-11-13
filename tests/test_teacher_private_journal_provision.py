"""#238 Slice 3C0: protected immutable intent candidate, no live commit."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path
from typing import Literal

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_provision as provision
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_transaction_intent as intent
from pds_core import _teacher_private_transaction_witness as witness
from pds_core import _teacher_private_windows_provision as windows
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX_ID = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
ASSOC = "6fb32a62-83e2-43f6-9823-687801593c8b"


def _raw(
    kind: Literal["windows_token_sid", "posix_euid"], owner: str, workspace: str
) -> bytes:
    descriptor = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(ASSOC)
    )
    registry = metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner(kind, owner),
            1,
            (metadata.PrivateRegistryBinding(ASSOC, 1, workspace),),
        )
    )
    proposed = witness.PrivateTransactionWitness(
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
        intent.PrivateTransactionIntent(proposed, None, descriptor, None, registry)
    )


@pytest.fixture
def linux_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    geteuid = getattr(os, "geteuid", None)
    if sys.platform != "linux" or geteuid is None or geteuid() == 0:
        pytest.skip("Linux non-root required")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = (
        tmp_path / "paper-data-suite" / "private" / "notes" / "v1" / "transactions"
    )
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    return directory


def _native_raw() -> bytes:
    if sys.platform == "win32":
        owner = inspection._effective_owner("win32").value
        return _raw("windows_token_sid", owner, "C:\\synthetic_workspace_a")
    getter = getattr(os, "geteuid", None)
    owner = str(getter()) if getter is not None else "1000"
    return _raw("posix_euid", owner, "/synthetic_workspace_a")


def test_valid_canonical_transaction_bytes() -> None:
    source = _raw("posix_euid", "1000", "/synthetic_workspace_a")
    result = provision._validated_content(source)
    assert result == (source, TX_ID, "posix_euid", "1000")
    assert provision._validated_content(source + b" ") is None
    assert provision._validated_content(source.replace(b"\n", b" ", 1)) is None


@pytest.mark.parametrize(
    "invalid",
    [b"", b"BAD", b'{"schema":"future"}', b"\xff", b"x" * 3000000, None, 42],
    ids=["empty", "bad", "future", "invalid-utf8", "oversized", "none", "integer"],
)
def test_invalid_payload_refused_without_any_io(
    invalid: object, tmp_path: Path
) -> None:
    result = provision.create_private_transaction_intent_file(
        tmp_path,
        invalid,  # type: ignore[arg-type]
    )
    assert result.state is provision.PrivateJournalProvisionState.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == []


def test_refuses_wrong_directory_without_changes(tmp_path: Path) -> None:
    outcome = provision.create_private_transaction_intent_file(tmp_path, _native_raw())
    assert outcome.state is provision.PrivateJournalProvisionState.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == []


def test_rejects_wrong_native_owner_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        content = _raw("posix_euid", "1000", "/synthetic_workspace_a")
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        content = _raw(
            "windows_token_sid", "S-1-5-21-11-22-33-44", "C:\\synthetic_workspace_a"
        )
    result = provision.create_private_transaction_intent_file(tmp_path, content)
    assert result.state in {
        provision.PrivateJournalProvisionState.REFUSED_OWNER,
        provision.PrivateJournalProvisionState.UNSUPPORTED,
    }
    assert list(tmp_path.iterdir()) == []


def test_refusal_messages_hide_principal_and_workspace() -> None:
    for state in provision.PrivateJournalProvisionState:
        result = provision._result(state)
        assert ASSOC not in repr(result)
        assert "synthetic_workspace" not in repr(result)
        assert "S-1-5-" not in repr(result)
        assert "1000" not in repr(result)


def test_no_public_service_or_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(provision, "commit_private_transaction")
    assert not hasattr(provision, "create_notes_store")


def test_linux_create_then_preserve_duplicate(linux_directory: Path) -> None:
    raw = _native_raw()
    first = provision.create_private_transaction_intent_file(linux_directory, raw)
    assert (
        first.state
        is provision.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    journal = linux_directory / f"{TX_ID}.json"
    assert journal.read_bytes() == raw
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600
    assert journal.stat().st_nlink == 1
    second = provision.create_private_transaction_intent_file(linux_directory, raw)
    assert second.state is provision.PrivateJournalProvisionState.ALREADY_EXISTS
    assert journal.read_bytes() == raw
    assert sorted(item.name for item in linux_directory.iterdir()) == [f"{TX_ID}.json"]


def test_linux_preserves_existing_conflicting_content(linux_directory: Path) -> None:
    journal = linux_directory / f"{TX_ID}.json"
    journal.write_bytes(b"preserve-even-if-corrupt")
    outcome = provision.create_private_transaction_intent_file(
        linux_directory, _native_raw()
    )
    assert outcome.state is provision.PrivateJournalProvisionState.ALREADY_EXISTS
    assert journal.read_bytes() == b"preserve-even-if-corrupt"


def test_linux_refuses_other_owner_before_create(linux_directory: Path) -> None:
    geteuid = getattr(os, "geteuid", None)
    assert geteuid is not None
    other = str(geteuid() + 1)
    outcome = provision.create_private_transaction_intent_file(
        linux_directory, _raw("posix_euid", other, "/synthetic_workspace_a")
    )
    assert outcome.state is provision.PrivateJournalProvisionState.REFUSED_OWNER
    assert list(linux_directory.iterdir()) == []


def test_linux_refuses_insecure_directory(linux_directory: Path) -> None:
    linux_directory.chmod(0o755)
    outcome = provision.create_private_transaction_intent_file(
        linux_directory, _native_raw()
    )
    assert outcome.state is provision.PrivateJournalProvisionState.REFUSED_PROTECTION
    assert list(linux_directory.iterdir()) == []


def test_linux_refuses_unknown_locality(
    linux_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: False)
    outcome = provision.create_private_transaction_intent_file(
        linux_directory, _native_raw()
    )
    assert outcome.state is provision.PrivateJournalProvisionState.REFUSED_BACKING
    assert list(linux_directory.iterdir()) == []


def test_linux_umask_partial_retained(linux_directory: Path) -> None:
    before = os.umask(0o777)
    try:
        outcome = provision.create_private_transaction_intent_file(
            linux_directory, _native_raw()
        )
    finally:
        os.umask(before)
    assert outcome.state is provision.PrivateJournalProvisionState.CREATION_UNVERIFIED
    journal = linux_directory / f"{TX_ID}.json"
    assert journal.is_file()
    assert stat.S_IMODE(journal.stat().st_mode) == 0


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_synthetic_protected_journal_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = inspection._effective_owner("win32")
    kernel, advapi = windows._windows_api()
    if not windows._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Test volume is not fixed NTFS or ReFS")
    parent = tmp_path
    for segment in ("Paper Data Suite", "private", "notes", "v1", "transactions"):
        parent = parent / segment
        created, error = windows._create_directory_explicit_dacl(
            kernel, advapi, parent, owner.value
        )
        assert created, f"Synthetic protected fixture creation failed {error}"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    content = _native_raw()
    first = provision.create_private_transaction_intent_file(parent, content)
    assert (
        first.state
        is provision.PrivateJournalProvisionState.CREATED_RESTRICTIVE_UNQUALIFIED
    )
    journal = parent / f"{TX_ID}.json"
    assert journal.read_bytes() == content
    assert provision.create_private_transaction_intent_file(parent, content).state is (
        provision.PrivateJournalProvisionState.ALREADY_EXISTS
    )
    assert journal.read_bytes() == content


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_owner_mismatch_is_refused_before_file_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    claimed = _raw(
        "windows_token_sid", "S-1-5-21-11-22-33-44", "C:\\synthetic_workspace_a"
    )
    candidate = (
        tmp_path / "Paper Data Suite" / "private" / "notes" / "v1" / "transactions"
    )
    result = provision.create_private_transaction_intent_file(candidate, claimed)
    assert result.state is provision.PrivateJournalProvisionState.REFUSED_OWNER
    assert not candidate.exists()


def test_linux_preserves_dangling_journal_symlink(linux_directory: Path) -> None:
    journal = linux_directory / f"{TX_ID}.json"
    journal.symlink_to(linux_directory / "missing")
    outcome = provision.create_private_transaction_intent_file(
        linux_directory, _native_raw()
    )
    assert outcome.state is provision.PrivateJournalProvisionState.ALREADY_EXISTS
    assert journal.is_symlink()
    assert not (linux_directory / "missing").exists()


def test_linux_refuses_symlink_directory(linux_directory: Path) -> None:
    other = linux_directory.parent / "real_transactions"
    other.mkdir(mode=0o700)
    other.chmod(0o700)
    linux_directory.rmdir()
    linux_directory.symlink_to(other, target_is_directory=True)
    outcome = provision.create_private_transaction_intent_file(
        linux_directory, _native_raw()
    )
    assert outcome.state is provision.PrivateJournalProvisionState.REFUSED_PROTECTION
    assert list(other.iterdir()) == []


def test_unsupported_platform_never_creates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    outcome = provision.create_private_transaction_intent_file(
        tmp_path, _raw("posix_euid", "1000", "/synthetic_workspace_a")
    )
    assert outcome.state is provision.PrivateJournalProvisionState.UNSUPPORTED
    assert list(tmp_path.iterdir()) == []
