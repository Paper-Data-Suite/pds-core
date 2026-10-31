"""#238 Slice 3F0: Windows journal-only write-through, no durability claim."""

from __future__ import annotations

import ctypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_journal_provision as journal
from pds_core import _teacher_private_lock_file_provision as file_provision
from pds_core import _teacher_private_windows_preflight as preflight
from pds_core import _teacher_private_windows_provision as windows
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities

SID = "S-1-5-21-11-22-33-44"


class _NativeFn:
    """Mock callable that accepts ctypes argtypes/restype assignments."""

    def __init__(self, callback: Callable[..., Any]) -> None:
        self.callback = callback
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: Any) -> Any:
        return self.callback(*args)


def _fake_native_create() -> tuple[Any, Any, list[tuple[int, int]]]:
    flags: list[tuple[int, int]] = []

    def convert(_sddl: str, _revision: int, output: Any, _size: object) -> bool:
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(0x101)
        return True

    def create(
        _path: str,
        access: int,
        sharing: int,
        _security: Any,
        disposition: int,
        attributes: int,
        _template: object,
    ) -> ctypes.c_void_p:
        flags.append((int(access), int(attributes)))
        assert sharing == 0
        assert disposition == 1
        return ctypes.c_void_p(0x202)

    kernel = SimpleNamespace(
        CreateFileW=_NativeFn(create),
        LocalFree=_NativeFn(lambda _descriptor: None),
    )
    advapi = SimpleNamespace(
        ConvertStringSecurityDescriptorToSecurityDescriptorW=_NativeFn(convert)
    )
    return kernel, advapi, flags


@pytest.mark.parametrize("write_through", [False, True])
def test_private_create_explicit_dacl_flag_is_opt_in(write_through: bool) -> None:
    kernel, advapi, calls = _fake_native_create()
    handle, error = file_provision._create_file_explicit_dacl_windows(
        kernel,
        advapi,
        Path("C:/synthetic-test/transaction.json"),
        SID,
        write_through=write_through,
    )
    assert handle == 0x202
    assert error == 0
    assert calls == [
        (0x40000000 | 0x80 | 0x20000, 0x80 | (0x80000000 if write_through else 0))
    ]


def test_unrelated_lock_file_create_retains_legacy_flag_default() -> None:
    kernel, advapi, calls = _fake_native_create()
    handle, error = file_provision._create_file_explicit_dacl_windows(
        kernel, advapi, Path("C:/synthetic-test/.registry.lock"), SID
    )
    assert handle == 0x202 and error == 0
    assert calls[0][1] == 0x80


def test_invalid_sid_never_invokes_native_create() -> None:
    kernel, advapi, calls = _fake_native_create()
    with pytest.raises(windows._NativeUnavailable):
        file_provision._create_file_explicit_dacl_windows(
            kernel,
            advapi,
            Path("C:/synthetic-test/transaction.json"),
            "not-a-sid",
            write_through=True,
        )
    assert calls == []


def test_journal_windows_uses_write_through_without_touching_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel, advapi, _ = _fake_native_create()
    # Only execute the guarded dispatch up to the exclusive-create helper.
    # A simulated collision means no native file is changed by this test.
    kernel.WriteFile = _NativeFn(lambda *_args: True)
    kernel.FlushFileBuffers = _NativeFn(lambda *_args: True)
    kernel.GetFileInformationByHandleEx = _NativeFn(lambda *_args: True)
    monkeypatch.setattr(journal, "_requested_transactions_dir", lambda *_: True)
    monkeypatch.setattr(
        inspection,
        "_effective_owner",
        lambda _platform: inspection.EffectiveOSOwner("windows_token_sid", SID),
    )
    monkeypatch.setattr(windows, "_windows_api", lambda: (kernel, advapi))
    monkeypatch.setattr(windows, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(
        preflight,
        "_native_windows_walk",
        lambda *_: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    captured: list[bool] = []

    def collision(
        _kernel: Any,
        _advapi: Any,
        _target: Path,
        _sid: str,
        *,
        write_through: bool = False,
    ) -> tuple[None, int]:
        captured.append(write_through)
        return None, 80  # ERROR_FILE_EXISTS: preserve an existing journal

    monkeypatch.setattr(file_provision, "_create_file_explicit_dacl_windows", collision)
    directory = tmp_path / "transactions"
    result = journal._windows_create(directory, b"synthetic", "transaction.json", SID)
    assert result.state is journal.PrivateJournalProvisionState.ALREADY_EXISTS
    assert captured == [True]
    assert not directory.exists()


def test_windows_rejects_wrong_owner_without_attempted_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal, "_requested_transactions_dir", lambda *_: True)
    monkeypatch.setattr(
        inspection,
        "_effective_owner",
        lambda _platform: inspection.EffectiveOSOwner("windows_token_sid", SID),
    )
    result = journal._windows_create(
        tmp_path / "transactions",
        b"synthetic",
        "transaction.json",
        "S-1-5-21-99-88-77-66",
    )
    assert result.state is journal.PrivateJournalProvisionState.REFUSED_OWNER
    assert list(tmp_path.iterdir()) == []


def test_no_transaction_or_notes_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(journal, "commit_private_transaction")
    assert not hasattr(journal, "admit_durable_transaction")
    assert not hasattr(file_provision, "commit_private_binding")
