"""#238 Slice 3B1: native, no-write refusal gates; never authorizes storage."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_native_preflight as preflight
from pds_core.teacher_experience import get_teacher_experience_capabilities

_NATIVE_LINUX = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux O_NOFOLLOW and POSIX ACL probe"
)


def _candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    root = tmp_path / "xdg" / "paper-data-suite" / "private" / "notes" / "v1"
    return root


def _create_strict(candidate: Path) -> None:
    candidate.mkdir(parents=True)
    for directory in (candidate, candidate.parent, candidate.parent.parent):
        directory.chmod(0o700)


def test_preflight_does_not_export_or_advertise_notes() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(preflight, "create_private_root")
    assert not hasattr(preflight, "write_private_registry")
    assert not hasattr(preflight.NativePrivatePreflightState, "READY")


@_NATIVE_LINUX
def test_missing_location_is_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _candidate(monkeypatch, tmp_path)
    before = list(tmp_path.iterdir())
    result = preflight.inspect_native_private_preflight()
    assert result.state is preflight.NativePrivatePreflightState.MISSING
    assert list(tmp_path.iterdir()) == before
    assert not root.exists()


@_NATIVE_LINUX
def test_mode_0700_is_observation_not_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _candidate(monkeypatch, tmp_path)
    _create_strict(root)
    before = root.stat().st_mtime_ns
    result = preflight.inspect_native_private_preflight()
    assert result.state is preflight.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    assert root.stat().st_mtime_ns == before
    assert list(root.iterdir()) == []
    assert str(tmp_path) not in result.message


@_NATIVE_LINUX
@pytest.mark.parametrize("mode", [0o755, 0o750, 0o777, 0o500])
def test_target_rejects_inadequate_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int
) -> None:
    root = _candidate(monkeypatch, tmp_path)
    _create_strict(root)
    root.chmod(mode)
    result = preflight.inspect_native_private_preflight()
    assert result.state in (
        preflight.NativePrivatePreflightState.REFUSED_MODE,
        preflight.NativePrivatePreflightState.REFUSED_PATH,
    )
    assert root.stat().st_mode & 0o777 == mode


@_NATIVE_LINUX
def test_shared_nonsticky_ancestor_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _candidate(monkeypatch, tmp_path)
    _create_strict(root)
    (tmp_path / "xdg").chmod(0o777)
    result = preflight.inspect_native_private_preflight()
    assert result.state is preflight.NativePrivatePreflightState.REFUSED_PATH


@_NATIVE_LINUX
def test_link_in_candidate_path_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(linked))
    result = preflight.inspect_native_private_preflight()
    assert result.state is preflight.NativePrivatePreflightState.REFUSED_PATH
    assert list(real.iterdir()) == []


@_NATIVE_LINUX
def test_acl_bytes_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _candidate(monkeypatch, tmp_path)
    _create_strict(root)
    monkeypatch.setattr(os, "getxattr", lambda *_args: b"synthetic_acl", raising=False)
    result = preflight.inspect_native_private_preflight()
    assert result.state is preflight.NativePrivatePreflightState.REFUSED_ACL


@_NATIVE_LINUX
def test_unavailable_acl_probe_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _candidate(monkeypatch, tmp_path)
    _create_strict(root)

    def unavailable(*_args: object) -> bytes:
        raise OSError(errno.EOPNOTSUPP, "synthetic-unavailable")

    monkeypatch.setattr(os, "getxattr", unavailable, raising=False)
    assert (
        preflight.inspect_native_private_preflight().state
        is preflight.NativePrivatePreflightState.UNSUPPORTED
    )


@_NATIVE_LINUX
def test_access_acl_missing_is_not_a_security_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _candidate(monkeypatch, tmp_path)
    _create_strict(root)

    def absent(*_args: object) -> bytes:
        raise OSError(errno.ENODATA, "synthetic-no-acl")

    monkeypatch.setattr(os, "getxattr", absent, raising=False)
    assert (
        preflight.inspect_native_private_preflight().state
        is preflight.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    )


@_NATIVE_LINUX
def test_refuses_other_owner_without_actor_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _candidate(monkeypatch, tmp_path)
    _create_strict(root)
    observed = root.stat().st_uid
    from pds_core import _teacher_private_inspection as inspection

    monkeypatch.setattr(
        inspection,
        "_effective_owner",
        lambda _platform: inspection.EffectiveOSOwner("posix_euid", str(observed + 1)),
    )
    assert (
        preflight.inspect_native_private_preflight().state
        is preflight.NativePrivatePreflightState.ACCESS_DENIED
    )


def test_linux_fd_walk_refuses_on_non_linux_platform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pds_core import _teacher_private_inspection as inspection

    monkeypatch.setattr(sys, "platform", "win32")
    result = preflight._native_linux_walk(
        tmp_path, inspection.EffectiveOSOwner("posix_euid", "1000")
    )
    assert result is preflight.NativePrivatePreflightState.UNSUPPORTED


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_existing_root_on_other_os_remains_unqualified(
    platform: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pds_core import _teacher_private_inspection as inspection

    monkeypatch.setattr(sys, "platform", platform)
    owner_kind = "windows_token_sid" if platform == "win32" else "posix_euid"
    owner_value = "S-1-5-21-1234" if platform == "win32" else "1000"
    synthetic = inspection.PrivateRootInspection(
        inspection.PrivateRootState.PRESENT_UNVERIFIED,
        inspection.EffectiveOSOwner(owner_kind, owner_value),  # type: ignore[arg-type]
        tmp_path,
        "Synthetic inspection; does not establish security.",
    )
    monkeypatch.setattr(inspection, "inspect_private_root", lambda: synthetic)
    if platform == "win32":
        # Synthetic cross-platform test: native Windows ACL checks require
        # real Windows and must not be inferred from a mocked platform.
        from pds_core import _teacher_private_windows_preflight as windows

        monkeypatch.setattr(
            windows,
            "_native_windows_walk",
            lambda candidate, current_owner: (
                preflight.NativePrivatePreflightState.UNSUPPORTED
            ),
        )
    result = preflight.inspect_native_private_preflight()
    assert result.state is preflight.NativePrivatePreflightState.UNSUPPORTED


def test_preflight_messages_are_bounded_and_private() -> None:
    for state in preflight.NativePrivatePreflightState:
        result = preflight._outcome(state)
        assert len(result.message) < 128
        assert "S-1-5" not in result.message
        assert "/home/" not in result.message
        assert "C:\\Users\\" not in result.message
        assert "ready" not in state.value


def test_no_notes_capability_or_private_write_from_import() -> None:
    import pds_core._teacher_private_native_preflight  # noqa: F401

    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
