"""Core #238 Slice 3C4: FILE_STANDARD_INFO ABI layout and checked file flags."""

from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_registry_bootstrap as bootstrap
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core._teacher_private_native_preflight import NativePrivatePreflightState
from pds_core.teacher_experience import get_teacher_experience_capabilities


def test_registry_standard_info_uses_byte_boolean_fields() -> None:
    fields = getattr(bootstrap._FileStandardInfo, "_fields_")
    assert fields[-2:] == [
        ("delete_pending", ctypes.c_ubyte),
        ("directory", ctypes.c_ubyte),
    ]
    assert ctypes.sizeof(ctypes.c_ubyte) == 1
    assert getattr(bootstrap._FileStandardInfo, "directory").offset == (
        getattr(bootstrap._FileStandardInfo, "delete_pending").offset + 1
    )
    assert fields == getattr(descriptor._FileStandardInfo, "_fields_")
    if sys.platform == "win32":
        assert ctypes.sizeof(wintypes.DWORD) == 4
        assert getattr(bootstrap._FileStandardInfo, "delete_pending").offset == 20
        assert getattr(bootstrap._FileStandardInfo, "directory").offset == 21
        assert ctypes.sizeof(bootstrap._FileStandardInfo) == 24


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native ABI only")
@pytest.mark.parametrize(
    ("delete_pending", "directory", "expected"),
    [(0, 0, True), (0, 1, False), (1, 0, False), (1, 1, False)],
    ids=["regular-file", "directory", "delete-pending", "both-refused"],
)
def test_windows_existing_lock_classification_from_raw_native_bytes(
    monkeypatch: pytest.MonkeyPatch,
    delete_pending: int,
    directory: int,
    expected: bool,
) -> None:
    """Model Windows' actual 24-byte FILE_STANDARD_INFO, not our structure."""
    raw = struct.pack("<qqIBBxx", 4096, 1, 1, delete_pending, directory)
    assert len(raw) == 24
    closed: list[int] = []

    class NativeKernel:
        def __init__(self) -> None:
            # Assign mutable function objects: ctypes bindings attach argtypes
            # and restype to these functions during the native helper call.
            def create_file(*_args: Any) -> int:
                return 23

            self.CreateFileW = create_file

            def information(
                _handle: Any, information_class: int, pointer: Any, size: int
            ) -> bool:
                if information_class == 9:
                    attrs = lock_provision._FileAttributeTagInfo()
                    attrs.attributes = 0x80  # FILE_ATTRIBUTE_NORMAL
                    ctypes.memmove(
                        pointer, ctypes.byref(attrs), min(size, ctypes.sizeof(attrs))
                    )
                    return True
                if information_class == 1:
                    assert size == 24
                    ctypes.memmove(pointer, raw, len(raw))
                    return True
                return False

            self.GetFileInformationByHandleEx = information

        def CloseHandle(self, handle: Any) -> bool:
            closed.append(int(handle.value or 0))
            return True

    kernel = NativeKernel()
    monkeypatch.setattr(wincheck, "_bind_api", lambda: (kernel, object()))
    monkeypatch.setattr(
        wincheck,
        "_handle_dacl_state",
        lambda *_args: NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
    )
    account = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-21-11-22-33-44")
    observed = bootstrap._qualified_existing_lock_windows(
        kernel, object(), Path(r"C:\synthetic-private-root"), account
    )
    assert observed is expected
    assert closed == [23]


def test_abi_fix_exposes_no_storage_or_notes_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(bootstrap, "write_private_registry")
    assert not hasattr(bootstrap, "create_notes_store")
