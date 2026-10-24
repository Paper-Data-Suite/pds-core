"""#238 Slice 2: strictly read-only owner and root inspection.

These tests explicitly do not qualify native ACLs, locking or private writes.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core.teacher_experience import get_teacher_experience_capabilities


_POSIX_NATIVE = pytest.mark.skipif(
    sys.platform == "win32", reason="native POSIX file modes/UIDs unavailable"
)


def _native_euid() -> int:
    """Read the native POSIX effective UID without a Windows-only type error."""
    getter = getattr(os, "geteuid", None)
    assert getter is not None
    return int(getter())


def test_existing_capabilities_remain_exactly_terminal_only() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_posix_effective_uid_is_used_not_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1872, raising=False)
    owner = inspection._effective_owner("linux")
    assert owner.kind == "posix_euid"
    assert owner.value == "1872"
    assert "1872" not in repr(owner)


@pytest.mark.parametrize("bad_uid", [-1, "1000", None, True])
def test_invalid_native_uid_is_refused(
    monkeypatch: pytest.MonkeyPatch, bad_uid: object
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: bad_uid, raising=False)
    with pytest.raises(inspection._OwnerUnverifiable):
        inspection._effective_owner("linux")


def test_unknown_platform_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "plan9")
    result = inspection.inspect_private_root()
    assert result.state is inspection.PrivateRootState.UNSUPPORTED
    assert result.owner is None
    assert result.candidate is None


def test_windows_principal_uses_sid_probe_not_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inspection, "_windows_effective_sid", lambda: "S-1-5-21-1234")
    owner = inspection._effective_owner("win32")
    assert owner.kind == "windows_token_sid"
    assert owner.value == "S-1-5-21-1234"
    assert "S-1-5-21-1234" not in repr(owner)


def test_unavailable_windows_native_probe_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> str:
        raise inspection._OwnerUnverifiable

    monkeypatch.setattr(inspection, "_windows_effective_sid", refuse)
    monkeypatch.setattr(sys, "platform", "win32")
    result = inspection.inspect_private_root()
    assert result.state is inspection.PrivateRootState.UNSUPPORTED
    assert result.candidate is None


def test_linux_xdg_root_is_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    candidate = inspection._candidate_private_root("linux")
    assert candidate == (
        tmp_path / "data" / "paper-data-suite" / "private" / "notes" / "v1"
    )


@pytest.mark.parametrize("bad_root", ["relative/data", "../bad", "", "."])
def test_invalid_xdg_roots_are_not_fallbacks(
    monkeypatch: pytest.MonkeyPatch, bad_root: str
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", bad_root)
    with pytest.raises(ValueError):
        inspection._candidate_private_root("linux")


def test_xdg_missing_uses_user_local_data_not_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert inspection._candidate_private_root("linux") == (
        tmp_path / ".local" / "share" / "paper-data-suite" / "private" / "notes" / "v1"
    )


def test_macos_uses_local_application_support(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert inspection._candidate_private_root("darwin") == (
        tmp_path
        / "Library"
        / "Application Support"
        / "Paper Data Suite"
        / "private"
        / "notes"
        / "v1"
    )


def test_absent_windows_localappdata_has_no_roaming_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("APPDATA", "untrusted-roaming-directory")
    with pytest.raises(ValueError):
        inspection._candidate_private_root("win32")


def test_windows_localappdata_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Synthetic absolute path supplies deterministic layout on Linux CI too.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert inspection._candidate_private_root("win32") == (
        tmp_path / "Paper Data Suite" / "private" / "notes" / "v1"
    )


@_POSIX_NATIVE
def test_no_creation_under_missing_private_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "not-created"))
    before = sorted(tmp_path.iterdir())
    result = inspection.inspect_private_root()
    assert result.state is inspection.PrivateRootState.MISSING
    assert result.candidate is not None
    assert not result.candidate.exists()
    assert sorted(tmp_path.iterdir()) == before
    assert "not-created" not in result.message


@_POSIX_NATIVE
def test_existing_0700_root_not_falsely_qualified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = inspection._candidate_private_root("linux")
    root.mkdir(parents=True)
    root.chmod(0o700)
    before = root.stat().st_mtime_ns
    result = inspection.inspect_private_root()
    assert result.state is inspection.PrivateRootState.PRESENT_UNVERIFIED
    assert root.stat().st_mtime_ns == before
    assert list(root.iterdir()) == []


@_POSIX_NATIVE
def test_unsafe_mode_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = inspection._candidate_private_root("linux")
    root.mkdir(parents=True)
    root.chmod(0o755)
    assert (
        inspection.inspect_private_root().state
        is inspection.PrivateRootState.UNSAFE_PATH
    )


@_POSIX_NATIVE
def test_foreign_os_owner_is_access_denied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    current_euid = _native_euid()
    monkeypatch.setattr(os, "geteuid", lambda: current_euid + 1, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    root = inspection._candidate_private_root("linux")
    root.mkdir(parents=True)
    root.chmod(0o700)
    assert (
        inspection.inspect_private_root().state
        is inspection.PrivateRootState.ACCESS_DENIED
    )


@_POSIX_NATIVE
def test_symlink_component_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX symlink fixture; native Windows junction checks are later")
    monkeypatch.setattr(sys, "platform", "linux")
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(linked))
    result = inspection.inspect_private_root()
    assert result.state is inspection.PrivateRootState.UNSAFE_PATH
    assert not (actual / "paper-data-suite").exists()


@_POSIX_NATIVE
def test_dangling_symlink_component_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX symlink fixture")
    monkeypatch.setattr(sys, "platform", "linux")
    linked = tmp_path / "dangling"
    linked.symlink_to(tmp_path / "absent", target_is_directory=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(linked))
    assert (
        inspection.inspect_private_root().state
        is inspection.PrivateRootState.UNSAFE_PATH
    )


@_POSIX_NATIVE
def test_file_component_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    blocked = tmp_path / "blocking-file"
    blocked.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(blocked))
    assert (
        inspection.inspect_private_root().state
        is inspection.PrivateRootState.UNSAFE_PATH
    )


def test_no_import_side_effects_or_public_storage_capability() -> None:
    import pds_core._teacher_private_inspection  # noqa: F401

    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


@_POSIX_NATIVE
def test_unsafe_path_mode_check_is_not_a_write(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir()
    root.chmod(0o700)
    owner = inspection.EffectiveOSOwner("posix_euid", str(_native_euid()))
    result = inspection._scan_existing_components(root, owner)
    assert result is inspection.PrivateRootState.PRESENT_UNVERIFIED
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
