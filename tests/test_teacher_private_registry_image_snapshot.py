"""Core #238 3E6: guarded exact-byte registry read, never CAS authority."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_provision
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_registry_image_snapshot as images
from pds_core import _teacher_private_retained_registry_guard as retained
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_registry_bootstrap as bootstrap
from pds_core import _teacher_private_windows_provision as windows
from pds_core.teacher_experience import get_teacher_experience_capabilities

ASSOCIATION = "6fb32a62-83e2-43f6-9823-687801593c8b"
ROOT = "/synthetic_workspace"


def _owner() -> inspection.EffectiveOSOwner:
    return inspection.EffectiveOSOwner("posix_euid", "1000")


def _registry(owner: inspection.EffectiveOSOwner | None = None) -> bytes:
    owner = owner or _owner()
    accepted_root = (
        "C:\\synthetic_workspace" if owner.kind == "windows_token_sid" else ROOT
    )
    return metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner(owner.kind, owner.value),
            1,
            (metadata.PrivateRegistryBinding(ASSOCIATION, 1, accepted_root),),
        )
    )


def test_canonical_exact_bytes_returned_without_reencoding() -> None:
    source = _registry()
    result = images._checked_image(source, _owner())
    assert result.state is images.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
    assert result.image == source
    assert result.image is source
    assert source not in repr(result).encode()
    assert ROOT not in repr(result)
    assert "1000" not in repr(result)


@pytest.mark.parametrize(
    "untrusted",
    [
        b"",
        b"garbage",
        b"{}",
        b"\xff",
        b"{" + b" " * 100,
        b"x" * (metadata.MAX_REGISTRY_BYTES + 1),
    ],
    ids=["empty", "garbage", "empty-object", "invalid-utf8", "incomplete", "oversize"],
)
def test_malformed_or_oversized_registry_refused(untrusted: bytes) -> None:
    outcome = images._checked_image(untrusted, _owner())
    assert outcome.state is images.PrivateRegistryImageState.INVALID_REGISTRY
    assert outcome.image is None
    assert "garbage" not in repr(outcome)


def test_wrong_owner_refused_even_when_bytes_are_valid() -> None:
    other = inspection.EffectiveOSOwner("posix_euid", "1001")
    outcome = images._checked_image(_registry(other), _owner())
    assert outcome.state is images.PrivateRegistryImageState.REFUSED_PROTECTION
    assert outcome.image is None


def test_noncanonical_bytes_refused() -> None:
    outcome = images._checked_image(_registry() + b" ", _owner())
    assert outcome.state is images.PrivateRegistryImageState.INVALID_REGISTRY


def test_frozen_image_review_and_sanitized_outcomes() -> None:
    result = images._result(images.PrivateRegistryImageState.MISSING)
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", images.PrivateRegistryImageState.IO_ERROR)
    assert result.image is None
    for state in images.PrivateRegistryImageState:
        review = images._result(state)
        assert "synthetic_workspace" not in repr(review)
        assert ASSOCIATION not in repr(review)
        assert "1000" not in repr(review)


@pytest.mark.parametrize(
    "code,expected",
    [
        (
            retained.RetainedRegistryGuardCode.OWNER_CHANGED,
            images.PrivateRegistryImageState.OWNER_CHANGED,
        ),
        (
            retained.RetainedRegistryGuardCode.OWNER_UNAVAILABLE,
            images.PrivateRegistryImageState.OWNER_UNAVAILABLE,
        ),
        (
            retained.RetainedRegistryGuardCode.UNSUPPORTED,
            images.PrivateRegistryImageState.UNSUPPORTED,
        ),
        (
            retained.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE,
            images.PrivateRegistryImageState.GUARD_REFUSED,
        ),
    ],
)
def test_guard_failure_mapping(
    code: retained.RetainedRegistryGuardCode, expected: images.PrivateRegistryImageState
) -> None:
    assert images._guard_refusal(code) is expected


def test_public_request_rejects_invalid_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    result = images.inspect_existing_private_registry_image(tmp_path, Path("relative"))
    assert result.state is images.PrivateRegistryImageState.INVALID_REQUEST
    assert result.image is None


def test_public_refuses_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "plan9")
    result = images.inspect_existing_private_registry_image(tmp_path, tmp_path)
    assert result.state is images.PrivateRegistryImageState.UNSUPPORTED


@contextmanager
def _held() -> Iterator[None]:
    yield


def test_public_returns_verified_image_only_under_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        retained, "_hold_existing_retained_registry_guard", lambda *_: _held()
    )
    monkeypatch.setattr(ordered, "_owner", _owner)
    monkeypatch.setattr(
        images, "_read_linux", lambda *_: images._checked_image(_registry(), _owner())
    )
    result = images.inspect_existing_private_registry_image(tmp_path, tmp_path)
    assert result.state is images.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
    assert result.image == _registry()


def test_public_guard_exit_failure_overrides_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @contextmanager
    def failing() -> Iterator[None]:
        yield
        raise retained.RetainedRegistryGuardError(
            retained.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE
        )

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        retained, "_hold_existing_retained_registry_guard", lambda *_: failing()
    )
    monkeypatch.setattr(ordered, "_owner", _owner)
    monkeypatch.setattr(
        images, "_read_linux", lambda *_: images._checked_image(_registry(), _owner())
    )
    result = images.inspect_existing_private_registry_image(tmp_path, tmp_path)
    assert result.state is images.PrivateRegistryImageState.GUARD_REFUSED
    assert result.image is None


def test_public_owner_change_drops_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    count = iter([_owner(), inspection.EffectiveOSOwner("posix_euid", "1001")])
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_provision, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        retained, "_hold_existing_retained_registry_guard", lambda *_: _held()
    )
    monkeypatch.setattr(ordered, "_owner", lambda: next(count))
    monkeypatch.setattr(
        images, "_read_linux", lambda *_: images._checked_image(_registry(), _owner())
    )
    result = images.inspect_existing_private_registry_image(tmp_path, tmp_path)
    assert result.state is images.PrivateRegistryImageState.OWNER_CHANGED
    assert result.image is None


@pytest.fixture
def linux_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    getter = getattr(os, "geteuid", None)
    if sys.platform != "linux" or getter is None or getter() == 0:
        pytest.skip("non-root native Linux only")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    # Control the isolated fixture filesystem classification; the production
    # reader never makes this substitution on actual user data.
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda _fd: True)
    monkeypatch.setattr(bootstrap, "_qualified_existing_lock_linux", lambda *_: True)
    return root


def _current_linux() -> inspection.EffectiveOSOwner:
    getter = getattr(os, "geteuid", None)
    assert getter is not None
    return inspection.EffectiveOSOwner("posix_euid", str(getter()))


def test_linux_exact_bytes_and_modes(linux_root: Path) -> None:
    raw = _registry(_current_linux())
    registry = linux_root / "registry.json"
    registry.write_bytes(raw)
    registry.chmod(0o600)
    result = images._read_linux(linux_root, _current_linux())
    assert result.state is images.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
    assert result.image == raw


def test_linux_missing_registry(linux_root: Path) -> None:
    result = images._read_linux(linux_root, _current_linux())
    assert result.state is images.PrivateRegistryImageState.MISSING
    assert result.image is None


def test_linux_refuses_permissive_registry(linux_root: Path) -> None:
    registry = linux_root / "registry.json"
    registry.write_bytes(_registry(_current_linux()))
    registry.chmod(0o644)
    result = images._read_linux(linux_root, _current_linux())
    assert result.state is images.PrivateRegistryImageState.REFUSED_PROTECTION


def test_linux_refuses_registry_symlink(linux_root: Path) -> None:
    target = linux_root / "target.json"
    target.write_bytes(_registry(_current_linux()))
    target.chmod(0o600)
    (linux_root / "registry.json").symlink_to(target)
    result = images._read_linux(linux_root, _current_linux())
    assert result.state is not images.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
    assert target.read_bytes() == _registry(_current_linux())


def test_linux_refuses_owner_mismatch(linux_root: Path) -> None:
    registry = linux_root / "registry.json"
    registry.write_bytes(_registry(inspection.EffectiveOSOwner("posix_euid", "1000")))
    registry.chmod(0o600)
    result = images._read_linux(linux_root, _current_linux())
    # This case can coincide with the fixture UID on uncommon hosts.
    if _current_linux().value != "1000":
        assert result.state is images.PrivateRegistryImageState.REFUSED_PROTECTION


def test_linux_preserves_corrupt_registry(linux_root: Path) -> None:
    registry = linux_root / "registry.json"
    registry.write_bytes(b"corrupt-preserve")
    registry.chmod(0o600)
    result = images._read_linux(linux_root, _current_linux())
    assert result.state is images.PrivateRegistryImageState.INVALID_REGISTRY
    assert registry.read_bytes() == b"corrupt-preserve"


def test_linux_wrong_owner_fails_before_file_open(linux_root: Path) -> None:
    wrong = inspection.EffectiveOSOwner(
        "posix_euid", str(int(_current_linux().value) + 1)
    )
    assert (
        images._read_linux(linux_root, wrong).state
        is images.PrivateRegistryImageState.OWNER_CHANGED
    )


def test_no_notes_capability_or_write_api() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(images, "commit_private_transaction")
    assert not hasattr(images, "write_registry")


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_native_protected_registry_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = inspection._effective_owner("win32")
    kernel, advapi = windows._windows_api()
    if not windows._known_fixed_local_volume(kernel, tmp_path):
        pytest.skip("Native fixed NTFS/ReFS volume required")
    root = tmp_path
    for part in ("Paper Data Suite", "private", "notes", "v1"):
        root = root / part
        created, error = windows._create_directory_explicit_dacl(
            kernel, advapi, root, owner.value
        )
        assert created, f"Protected synthetic directory failure {error}"
    monkeypatch.setattr(bootstrap, "_qualified_existing_lock_windows", lambda *_: True)
    handle_value, error = lock_provision._create_file_explicit_dacl_windows(
        kernel, advapi, root / "registry.json", owner.value
    )
    assert handle_value is not None, f"Protected synthetic file failure {error}"
    raw = _registry(owner)
    try:
        handle = wintypes.HANDLE(handle_value)
        kernel.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel.WriteFile.restype = wintypes.BOOL
        kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        kernel.FlushFileBuffers.restype = wintypes.BOOL
        contents = ctypes.create_string_buffer(raw)
        written = wintypes.DWORD()
        assert kernel.WriteFile(handle, contents, len(raw), ctypes.byref(written), None)
        assert written.value == len(raw)
        assert kernel.FlushFileBuffers(handle)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle_value))
    result = images._read_windows(root, owner)
    assert result.state is images.PrivateRegistryImageState.OBSERVED_REVIEW_REQUIRED
    assert result.image == raw
