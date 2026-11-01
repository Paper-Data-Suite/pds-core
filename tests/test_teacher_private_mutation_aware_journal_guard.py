"""#238 3F7: bounded Linux mutation-aware journal scope; no commit authority."""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_image_snapshot as journal
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_mutation_aware_journal_guard as guard
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
RAW = b"synthetic-intent-image\n"


def _proposal() -> intents.PrivateTransactionIntent:
    proposed = object.__new__(intents.PrivateTransactionIntent)
    action = object.__new__(witness.PrivateTransactionWitness)
    for name, value in {
        "operation": witness.PrivateBindingOperation.FORK_COPY,
        "transaction_id": TX,
        "association_before": "6fb32a62-83e2-43f6-9823-687801593c8b",
        "association_after": "0e6ef6ea-e641-4b32-88ca-23d6d4932d1f",
        "registry_revision_before": 1,
        "registry_revision_after": 2,
        "descriptor_sha256_before": "a" * 64,
        "descriptor_sha256_after": "b" * 64,
        "registry_sha256_before": "c" * 64,
        "registry_sha256_after": "d" * 64,
    }.items():
        object.__setattr__(action, name, value)
    object.__setattr__(proposed, "witness", action)
    for name, value in {
        "registry_before": b"before-r",
        "descriptor_before": b"before-d",
        "registry_after": b"after-r",
        "descriptor_after": b"after-d",
    }.items():
        object.__setattr__(proposed, name, value)
    return proposed


def _stat(
    *,
    inode: int = 9,
    uid: int = 1000,
    mode: int = 0o700,
    ctime: int = 1,
    mtime: int = 1,
) -> os.stat_result:
    return cast(
        os.stat_result,
        SimpleNamespace(
            st_dev=2,
            st_ino=inode,
            st_mode=stat.S_IFDIR | mode,
            st_uid=uid,
            st_nlink=2,
            st_ctime_ns=ctime,
            st_mtime_ns=mtime,
        ),
    )


@pytest.mark.parametrize("change", ["ctime", "mtime"])
def test_identity_deliberately_ignores_namespace_timestamp_delta(change: str) -> None:
    before = _stat()
    after = _stat(ctime=99) if change == "ctime" else _stat(mtime=99)
    assert guard._directory_identity(before) == guard._directory_identity(after)


@pytest.mark.parametrize("change", ["inode", "uid", "mode"])
def test_identity_never_ignores_unsafe_native_change(change: str) -> None:
    before = _stat()
    after = {
        "inode": _stat(inode=10),
        "uid": _stat(uid=1001),
        "mode": _stat(mode=0o755),
    }[change]
    assert guard._directory_identity(before) != guard._directory_identity(after)


def _prepare(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda _i: RAW)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _r: _proposal()
    )

    @contextmanager
    def held(
        _private: Path,
        _workspace: Path,
        _proposal_arg: intents.PrivateTransactionIntent,
        raw: bytes,
    ) -> Iterator[None]:
        assert raw == RAW
        events.append("enter")
        try:
            yield
            events.append("validated")
        finally:
            events.append("exit")

    monkeypatch.setattr(guard, "_hold_linux_expected_journal_create", held)


def test_public_scope_yields_no_handle_or_commit_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _prepare(monkeypatch, events)
    with guard.hold_expected_private_journal_creation(
        _proposal(), tmp_path, tmp_path
    ) as token:
        assert token is None
        events.append("body")
    assert events == ["enter", "body", "validated", "exit"]
    assert not hasattr(guard, "commit_private_binding")
    assert not hasattr(guard, "replace_private_registry")
    assert not hasattr(guard, "admit_durable_transaction")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_scope_does_not_swallow_caller_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _prepare(monkeypatch, events)
    with pytest.raises(RuntimeError, match="synthetic fault"):
        with guard.hold_expected_private_journal_creation(
            _proposal(), tmp_path, tmp_path
        ):
            raise RuntimeError("synthetic fault")
    assert events == ["enter", "exit"]


def test_invalid_request_refused_before_any_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _prepare(monkeypatch, events)
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: False)
    with pytest.raises(guard.PrivateJournalMutationGuardError) as exc:
        with guard.hold_expected_private_journal_creation(
            _proposal(), tmp_path, tmp_path
        ):
            pytest.fail("entered")
    assert exc.value.code is guard.PrivateJournalMutationGuardCode.INVALID_REQUEST
    assert events == []


def test_unsupported_platform_refused_before_any_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _prepare(monkeypatch, events)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(guard.PrivateJournalMutationGuardError) as exc:
        with guard.hold_expected_private_journal_creation(
            _proposal(), tmp_path, tmp_path
        ):
            pytest.fail("entered")
    assert exc.value.code is guard.PrivateJournalMutationGuardCode.UNSUPPORTED
    assert events == []


def test_initialize_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _prepare(monkeypatch, events)
    action = _proposal().witness
    object.__setattr__(action, "operation", witness.PrivateBindingOperation.INITIALIZE)
    proposed = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(proposed, "witness", action)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _r: proposed
    )
    with pytest.raises(guard.PrivateJournalMutationGuardError) as exc:
        with guard.hold_expected_private_journal_creation(proposed, tmp_path, tmp_path):
            pytest.fail("entered")
    assert exc.value.code is guard.PrivateJournalMutationGuardCode.INVALID_REQUEST
    assert events == []


@pytest.mark.skipif(
    sys.platform != "linux", reason="Requires Linux directory-descriptor native test"
)
@pytest.mark.parametrize(
    "scenario",
    ["create", "missing", "foreign", "collision", "mode", "hardlink", "drift"],
)
def test_linux_native_guard_exact_single_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """Synthetic isolated native directory, never private real user data."""
    uid_fn = getattr(os, "geteuid", None)
    if uid_fn is None or uid_fn() == 0:
        pytest.skip("Non-root Linux native test required")
    uid = uid_fn()
    root = tmp_path / "private"
    directory = root / "transactions"
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(intents, "encode_private_transaction_intent", lambda _i: RAW)
    monkeypatch.setattr(
        intents, "decode_private_transaction_intent", lambda _r: _proposal()
    )
    monkeypatch.setattr(
        ordered, "_owner", lambda: inspection.EffectiveOSOwner("posix_euid", str(uid))
    )

    @contextmanager
    def fake_lock(*_args: Path) -> Iterator[None]:
        yield

    monkeypatch.setattr(ordered, "_hold_existing_ordered_coordination", fake_lock)
    monkeypatch.setattr(registry_guard, "_held_linux_registry", lambda *_: fake_lock())
    monkeypatch.setattr(
        descriptor_guard, "_held_linux_descriptor", lambda *_: fake_lock()
    )
    monkeypatch.setattr(
        posix,
        "_open_verified_parent",
        lambda path, _uid: (
            os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)),
            None,
        ),
    )
    monkeypatch.setattr(posix, "_acl_absent", lambda _fd: None)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)

    def image(
        _directory: Path, tx: str, _owner: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        assert tx == TX
        content = (directory / (TX + ".json")).read_bytes()
        return journal.PrivateJournalImageReview(
            journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED,
            "synthetic",
            content,
        )

    monkeypatch.setattr(journal, "_read_linux", image)
    expected_code = {
        "missing": guard.PrivateJournalMutationGuardCode.MISSING_EXPECTED_ENTRY,
        "foreign": guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION,
        "collision": guard.PrivateJournalMutationGuardCode.PENDING_RECOVERY_REQUIRED,
        "mode": guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED,
        "hardlink": guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED,
        "drift": guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION,
    }
    if scenario == "collision":
        (directory / (TX + ".json")).write_bytes(RAW)

    def exercise() -> None:
        with guard.hold_expected_private_journal_creation(_proposal(), root, workspace):
            if scenario in ("missing", "collision"):
                return
            if scenario == "foreign":
                (directory / "other.json").write_bytes(b"foreign")
            elif scenario == "hardlink":
                foreign = tmp_path / "foreign"
                foreign.write_bytes(RAW)
                os.link(foreign, directory / (TX + ".json"))
            else:
                path = directory / (TX + ".json")
                path.write_bytes(RAW)
                path.chmod(0o644 if scenario == "mode" else 0o600)
                if scenario == "drift":
                    (directory / "unexpected").write_bytes(b"x")

    if scenario in expected_code:
        with pytest.raises(guard.PrivateJournalMutationGuardError) as caught:
            exercise()
        assert caught.value.code is expected_code[scenario]
    else:
        exercise()
    assert not hasattr(guard, "create_notes_record")


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        ("", None),
        ("extra", guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION),
        ("list-drift", guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION),
        ("owner", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
        ("mode", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
        ("hardlink", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
        ("different-device", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
        ("short", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
        ("wrong-bytes", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
        ("second-read-drift", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
        ("native-refusal", guard.PrivateJournalMutationGuardCode.FILE_UNQUALIFIED),
    ],
)
def test_exact_entry_refuses_unexpected_namespace_or_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    expected: guard.PrivateJournalMutationGuardCode | None,
) -> None:
    """Cross-platform, synthetic native observation of one expected entry."""
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    calls = 0

    def listdir(_fd: int) -> list[str]:
        nonlocal calls
        calls += 1
        if fault == "extra":
            return [TX + ".json", "foreign.json"]
        if fault == "list-drift" and calls > 1:
            return ["new-after-read"]
        return [TX + ".json"]

    linked = SimpleNamespace(
        st_mode=stat.S_IFREG | (0o644 if fault == "mode" else 0o600),
        st_nlink=2 if fault == "hardlink" else 1,
        st_dev=13 if fault == "different-device" else 11,
        st_uid=1001 if fault == "owner" else 1000,
        st_size=len(RAW) - 1 if fault == "short" else len(RAW),
    )
    parent = SimpleNamespace(st_dev=11)
    reads = 0

    def read(
        _directory: Path, _tx: str, _owner: inspection.EffectiveOSOwner
    ) -> journal.PrivateJournalImageReview:
        nonlocal reads
        reads += 1
        image = (
            RAW + b"foreign"
            if fault == "wrong-bytes" or (fault == "second-read-drift" and reads == 2)
            else RAW
        )
        state = (
            journal.PrivateJournalImageState.OBSERVED_REVIEW_REQUIRED
            if fault != "native-refusal"
            else journal.PrivateJournalImageState.MISSING_REVIEW_REQUIRED
        )
        return journal.PrivateJournalImageReview(state, "synthetic", image)

    with monkeypatch.context() as patch:
        patch.setattr(os, "listdir", listdir)
        patch.setattr(os, "stat", lambda *_args, **_kwargs: linked)
        patch.setattr(os, "fstat", lambda _fd: parent)
        patch.setattr(journal, "_read_linux", read)
        if expected is not None:
            with pytest.raises(guard.PrivateJournalMutationGuardError) as exc:
                guard._expected_entry(7, tmp_path, TX, RAW, owner)
            assert exc.value.code is expected
        else:
            guard._expected_entry(7, tmp_path, TX, RAW, owner)
            assert reads == 2 and calls == 2


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        ("", None),
        ("timestamps", None),
        ("inode", guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION),
        ("owner", guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION),
        ("unsafe-mode", guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION),
        ("symlink", guard.PrivateJournalMutationGuardCode.UNEXPECTED_MUTATION),
        ("acl", guard.PrivateJournalMutationGuardCode.REFUSED_PROTECTION),
        ("remote", guard.PrivateJournalMutationGuardCode.REFUSED_BACKING),
        ("owner-drift", guard.PrivateJournalMutationGuardCode.OWNER_CHANGED),
    ],
)
def test_retained_directory_rechecks_native_identity_and_protection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    expected: guard.PrivateJournalMutationGuardCode | None,
) -> None:
    beginning = _stat()
    candidate = {
        "timestamps": _stat(ctime=101, mtime=105),
        "inode": _stat(inode=10),
        "owner": _stat(uid=1001),
        "unsafe-mode": _stat(mode=0o755),
        "symlink": cast(
            os.stat_result,
            SimpleNamespace(
                st_dev=2,
                st_ino=9,
                st_mode=stat.S_IFLNK | 0o700,
                st_uid=1000,
                st_nlink=2,
            ),
        ),
    }.get(fault, beginning)
    with monkeypatch.context() as patch:
        patch.setattr(
            os,
            "geteuid",
            lambda: 1001 if fault == "owner-drift" else 1000,
            raising=False,
        )
        patch.setattr(os, "fstat", lambda _fd: candidate)
        patch.setattr(os, "lstat", lambda _path: candidate)
        patch.setattr(
            posix, "_acl_absent", lambda _fd: b"acl" if fault == "acl" else None
        )
        patch.setattr(
            posix, "_is_known_local_filesystem", lambda _fd: fault != "remote"
        )
        if expected is not None:
            with pytest.raises(guard.PrivateJournalMutationGuardError) as exc:
                guard._verified_directory(
                    7, tmp_path, guard._directory_identity(beginning), 1000
                )
            assert exc.value.code is expected
        else:
            guard._verified_directory(
                7, tmp_path, guard._directory_identity(beginning), 1000
            )
