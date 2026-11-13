"""#238 Slice 3B8: Windows explicit DACL child creation; never Notes activation."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Any

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_windows_provision as provision
from pds_core._teacher_private_posix_provision import PrivateChildCreationState as State
from pds_core.teacher_experience import get_teacher_experience_capabilities

_ACCOUNT = "S-1-5-21-11-22-33-44"
_SCOPE = "C:\\Users\\Synthetic\\AppData\\Local\\Paper Data Suite\\private\\notes\\v1"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "..",
        ".",
        "../escape",
        "a/b",
        "a\\b",
        "name.txt",
        "name ",
        "a:b",
        "NUL",
        "CON",
        "com1",
        "LPT9",
        "😀",
        "x" * 65,
        None,
        True,
    ],
)
def test_invalid_child_names_refused(name: object) -> None:
    assert not provision._valid_child(name)


@pytest.mark.parametrize("name", ["x", "private", "notes_v1", "A-9", "z" * 64])
def test_bounded_child_names_accepted(name: str) -> None:
    assert provision._valid_child(name)


def test_windows_scope_is_case_insensitive_but_component_exact() -> None:
    assert provision._within_approved_root(_SCOPE, _SCOPE.lower())
    assert provision._within_approved_root(_SCOPE + "\\collections", _SCOPE)
    assert not provision._within_approved_root(_SCOPE + "-other", _SCOPE)
    assert not provision._within_approved_root("C:\\Unrelated\\private", _SCOPE)
    assert not provision._within_approved_root("\\\\server\\share\\private", _SCOPE)
    assert not provision._within_approved_root("C:\\a\\..\\private", _SCOPE)


@pytest.mark.parametrize(
    "id", ["", "actor", "S-1-5-21-1);(A;;FA;;;WD", "S-1-5-21-1\n", "s-1-5-21-3"]
)
def test_sddl_rejects_untrusted_sid_before_native_api(id: str) -> None:
    with pytest.raises(provision._NativeUnavailable):
        provision._create_directory_explicit_dacl(
            object(), object(), Path("unused"), id
        )


def test_sddl_contains_only_owner_system_and_administrators() -> None:
    created: list[str] = []
    released: list[bool] = []

    class Advapi:
        def ConvertStringSecurityDescriptorToSecurityDescriptorW(
            self, sddl: str, version: int, dest: Any, size: Any
        ) -> bool:
            assert version == 1 and size is None
            created.append(sddl)
            ctypes.cast(dest, ctypes.POINTER(ctypes.c_void_p)).contents.value = 6789
            return True

    class Kernel:
        def CreateDirectoryW(self, name: str, attrs: Any) -> bool:
            assert name == "synthetic"
            attributes = ctypes.cast(
                attrs, ctypes.POINTER(provision._SecurityAttributes)
            ).contents
            assert attributes.nLength == ctypes.sizeof(provision._SecurityAttributes)
            assert not attributes.bInheritHandle
            assert attributes.lpSecurityDescriptor == 6789
            return True

        def LocalFree(self, ptr: Any) -> None:
            released.append(True)

    success, error = provision._create_directory_explicit_dacl(
        Kernel(), Advapi(), Path("synthetic"), _ACCOUNT
    )
    assert success and error == 0
    assert len(created) == 1
    assert created[0].startswith("D:P")
    assert "(A;OICI;FA;;;SY)" in created[0]
    assert "(A;OICI;FA;;;BA)" in created[0]
    assert f"(A;OICI;FA;;;{_ACCOUNT})" in created[0]
    assert "WD" not in created[0] and "AU" not in created[0]
    assert released == [True]


def test_preflight_failure_mapping_is_fail_closed() -> None:
    from pds_core._teacher_private_native_preflight import (
        NativePrivatePreflightState as Preflight,
    )

    for prior in Preflight:
        mapped = provision._map_preflight_state(prior)
        assert mapped is not State.CREATED_RESTRICTIVE_UNQUALIFIED


def test_windows_creation_is_not_run_on_linux(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("non-Windows gate")
    result = provision.create_restrictive_child_windows(tmp_path, "notes")
    assert result.state is State.UNSUPPORTED
    assert list(tmp_path.iterdir()) == []


def test_no_capability_or_public_note_service() -> None:
    assert not hasattr(provision, "create_notes_store")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


@pytest.mark.skipif(
    sys.platform != "win32", reason="native Windows CreateDirectoryW/DACL"
)
def test_windows_synthetic_child_uses_protected_dacl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = inspection._effective_owner("win32")
    kernel, advapi = provision._windows_api()
    if not provision._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("host test volume is not a supported fixed NTFS/ReFS volume")
    parent = tmp_path
    for child in ("Paper Data Suite", "private", "notes", "v1"):
        parent = parent / child
        success, error = provision._create_directory_explicit_dacl(
            kernel, advapi, parent, owner.value
        )
        assert success, f"Fixture protected directory creation error {error}"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    result = provision.create_restrictive_child_windows(parent, "collections")
    assert result.state is State.CREATED_RESTRICTIVE_UNQUALIFIED
    assert (parent / "collections").is_dir()
    assert list((parent / "collections").iterdir()) == []
    assert provision.create_restrictive_child_windows(parent, "collections").state is (
        State.ALREADY_EXISTS
    )


@pytest.mark.skipif(
    sys.platform != "win32", reason="native Windows CreateDirectoryW/DACL"
)
def test_windows_rejects_external_parent_without_changes(tmp_path: Path) -> None:
    before = list(tmp_path.iterdir())
    result = provision.create_restrictive_child_windows(tmp_path, "notes")
    assert result.state is State.INVALID_REQUEST
    assert list(tmp_path.iterdir()) == before
