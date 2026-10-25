"""Core #238 Slice 3B2: no-write Windows DACL and reparse refusal tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_native_preflight as native
from pds_core import _teacher_private_windows_preflight as windows
from pds_core._teacher_private_inspection import EffectiveOSOwner

_ACCOUNT = "S-1-5-21-10-20-30-40"  # synthetic SID, not a real owner
_ALLOW = 0
_DENY = 1
_DIRECTORY_RIGHTS = 0x00020003


def test_restrictive_dacl_is_still_unqualified() -> None:
    entries = (
        (_ALLOW, _DIRECTORY_RIGHTS, _ACCOUNT),
        (_ALLOW, 0x1F01FF, "S-1-5-18"),
        (_ALLOW, 0x1F01FF, "S-1-5-32-544"),
    )
    assert windows._classify_dacl(_ACCOUNT, _ACCOUNT, entries) is (
        native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    )


@pytest.mark.parametrize(
    "principal",
    [
        "S-1-1-0",  # Everyone
        "S-1-5-11",  # Authenticated Users
        "S-1-5-32-545",  # Users
        "S-1-15-2-1",  # All Application Packages
        "S-1-5-21-99-88-77-66",  # Another local user
        "S-1-3-0",  # Creator Owner
    ],
)
def test_foreign_or_group_access_grants_are_refused(principal: str) -> None:
    entries = ((_ALLOW, _DIRECTORY_RIGHTS, _ACCOUNT), (_ALLOW, 1, principal))
    assert windows._classify_dacl(_ACCOUNT, _ACCOUNT, entries) is (
        native.NativePrivatePreflightState.REFUSED_ACL
    )


@pytest.mark.parametrize("ace_type", [1, 5, 6, 9, 11, -1])
def test_deny_object_callback_and_unknown_aces_are_refused(ace_type: int) -> None:
    entries = ((_ALLOW, _DIRECTORY_RIGHTS, _ACCOUNT), (ace_type, 1, _ACCOUNT))
    assert windows._classify_dacl(_ACCOUNT, _ACCOUNT, entries) is (
        native.NativePrivatePreflightState.REFUSED_ACL
    )


def test_dacl_owner_does_not_follow_a_caller_supplied_label() -> None:
    assert (
        windows._classify_dacl(
            _ACCOUNT,
            "S-1-5-21-99-88-77-66",
            ((_ALLOW, _DIRECTORY_RIGHTS, _ACCOUNT),),
        )
        is native.NativePrivatePreflightState.REFUSED_OWNER
    )


@pytest.mark.parametrize("mask", [0, 1, 2, 0x00020000, 0x00010003])
def test_missing_owner_permissions_are_refused(mask: int) -> None:
    assert (
        windows._classify_dacl(_ACCOUNT, _ACCOUNT, ((_ALLOW, mask, _ACCOUNT),))
        is native.NativePrivatePreflightState.REFUSED_ACL
    )


@pytest.mark.parametrize(
    "path",
    [
        r"\\server\share\Paper Data Suite\private\notes\v1",
        r"\\?\C:\Users\a\Paper Data Suite\private\notes\v1",
        r"C:relative\Paper Data Suite\private\notes\v1",
        r"C:\a\..\Paper Data Suite\private\notes\v1",
        r"C:\a\.\Paper Data Suite\private\notes\v1",
        r"C:\a\bad:stream\Paper Data Suite\private\notes\v1",
    ],
)
def test_windows_dangerous_path_syntax_is_refused(path: str) -> None:
    assert windows._windows_drive_components(path) is None


def test_regular_windows_drive_components_parse_without_resolving() -> None:
    path = r"C:\Users\Teacher\AppData\Local\Paper Data Suite\private\notes\v1"
    assert windows._windows_drive_components(path) == (
        "C:\\",
        "Users",
        "Teacher",
        "AppData",
        "Local",
        "Paper Data Suite",
        "private",
        "notes",
        "v1",
    )


def test_linux_execution_cannot_claim_windows_native_preflight() -> None:
    if sys.platform == "win32":
        pytest.skip("native Windows execution exercised in separate test")
    result = windows._native_windows_walk(
        Path("/synthetic/Paper Data Suite/private/notes/v1"),
        EffectiveOSOwner("windows_token_sid", _ACCOUNT),
    )
    assert result is native.NativePrivatePreflightState.UNSUPPORTED


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows API only")
def test_real_windows_preflight_is_nonmutating_and_never_ready(
    tmp_path: Path,
) -> None:
    from pds_core import _teacher_private_inspection as initial

    owner = initial._effective_owner("win32")
    root = tmp_path / "Paper Data Suite" / "private" / "notes" / "v1"
    # The missing directory cannot be created as a side effect of preflight.
    assert windows._native_windows_walk(root, owner) is not (
        native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    )
    assert not root.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows API only")
def test_windows_native_existing_directory_is_still_unqualified(
    tmp_path: Path,
) -> None:
    from pds_core import _teacher_private_inspection as initial

    owner = initial._effective_owner("win32")
    root = tmp_path / "Paper Data Suite" / "private" / "notes" / "v1"
    root.mkdir(parents=True)
    before = list(root.iterdir())
    result = windows._native_windows_walk(root, owner)
    assert result in set(native.NativePrivatePreflightState)
    assert result is not native.NativePrivatePreflightState.MISSING
    assert list(root.iterdir()) == before


def test_no_new_teacher_experience_capabilities() -> None:
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_windows_platform_dispatches_native_refusal_without_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pds_core import _teacher_private_inspection as initial

    owner = EffectiveOSOwner("windows_token_sid", _ACCOUNT)
    candidate = tmp_path / "never-create"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        initial,
        "inspect_private_root",
        lambda: initial.PrivateRootInspection(
            initial.PrivateRootState.PRESENT_UNVERIFIED, owner, candidate, "synthetic"
        ),
    )
    observed: list[tuple[Path, EffectiveOSOwner]] = []

    def native_refusal(
        path: Path, actual_owner: EffectiveOSOwner
    ) -> native.NativePrivatePreflightState:
        observed.append((path, actual_owner))
        return native.NativePrivatePreflightState.REFUSED_ACL

    monkeypatch.setattr(windows, "_native_windows_walk", native_refusal)
    result = native.inspect_native_private_preflight()
    assert result.state is native.NativePrivatePreflightState.REFUSED_ACL
    assert observed == [(candidate, owner)]
    assert not candidate.exists()
