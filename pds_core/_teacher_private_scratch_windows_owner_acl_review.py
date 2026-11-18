"""Core #238 3G99: Windows token-SID and protected-DACL scratch review.

The public diagnostic accepts one fixed enum only; it creates at most one
explicitly protected DACL fixture in an owned disposable directory. A native
opened-handle DACL and SE_DACL_PROTECTED bit are inspected read-only. No user
path, owner SID, ACL, handle, identity, or write authority escapes. In
particular, ACL-shape observation is NOT a full Windows effective-access check.
"""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pds_core import _teacher_private_production_readiness as readiness


class PrivateWindowsOwnerAclScenario(str, Enum):
    PROTECTED_OWNER = "protected_owner"
    UNPROTECTED_DACL = "unprotected_dacl"
    EVERYONE_READ_DACL = "everyone_read_dacl"
    SPOOFED_OWNER = "spoofed_owner"
    MISSING_CHILD = "missing_child"


class PrivateWindowsOwnerAclState(str, Enum):
    PROTECTED_DACL_SHAPE_OBSERVED_HOLD = "protected_dacl_shape_observed_hold"
    UNPROTECTED_DACL_REFUSED = "unprotected_dacl_refused"
    EVERYONE_ACCESS_REFUSED = "everyone_access_refused"
    OWNER_MISMATCH_REFUSED = "owner_mismatch_refused"
    MISSING_CHILD_REFUSED = "missing_child_refused"
    WINDOWS_ONLY_REFUSED = "windows_only_refused"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    SCRATCH_CUSTODY_REFUSED = "scratch_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateWindowsOwnerAclReview:
    state: PrivateWindowsOwnerAclState
    scenario: str = "none"
    process_token_sid_reobserved: bool = False
    native_owner_sid_matches_token: bool = False
    dacl_read_from_native_handle: bool = False
    dacl_protection_control_observed: bool = False
    explicit_acl_shape_classified: bool = False
    negative_evidence_preserved: bool = False
    production_mutation_admitted: bool = False
    production_owner_acl_qualified: bool = False
    windows_effective_access_qualified: bool = False
    owner_binding_allowed: bool = False
    automatic_replay_allowed: bool = False
    automatic_retry_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateWindowsOwnerAclReview(scratch_only=True, non_authorizing=True)"


class _UnsafeScratch(Exception):
    """Sanitized refusal without identities, paths or security descriptors."""


# Win32 SECURITY_DESCRIPTOR_CONTROL.SE_DACL_PROTECTED.
_DACL_PROTECTED = 0x1000
_READ_CONTROL = 0x00020000
_READ_ATTRIBUTES = 0x00000080
_OPEN_EXISTING = 3
_FILE_SHARE_ALL = 0x00000007
_BACKUP_SEMANTICS = 0x02000000
_OPEN_REPARSE_POINT = 0x00200000
_INVALID_HANDLE = ctypes.c_void_p(-1).value


def _answer(
    state: PrivateWindowsOwnerAclState,
    *,
    scenario: str = "none",
    token: bool = False,
    owner: bool = False,
    dacl: bool = False,
    control: bool = False,
    classified: bool = False,
    preserved: bool = False,
) -> PrivateWindowsOwnerAclReview:
    return PrivateWindowsOwnerAclReview(
        state=state,
        scenario=scenario,
        process_token_sid_reobserved=token,
        native_owner_sid_matches_token=owner,
        dacl_read_from_native_handle=dacl,
        dacl_protection_control_observed=control,
        explicit_acl_shape_classified=classified,
        negative_evidence_preserved=preserved,
    )


def _fixture_parent(scratch: Path, kernel: Any, provision: Any) -> Path:
    """Use only an existing fixed local volume, with no production-root writes.

    CI's RUNNER_TEMP may be on an ephemeral volume. The fallback is an existing
    user-local Temp directory on a supported NTFS/ReFS volume, not Notes data.
    """
    if provision._known_fixed_local_volume(kernel, scratch):
        return scratch
    local_text = os.environ.get("LOCALAPPDATA")
    if not local_text:
        raise _UnsafeScratch
    local = Path(local_text)
    candidate = local / "Temp"
    home = Path.home()
    if (
        not local.is_absolute()
        or not candidate.is_relative_to(home)
        or candidate == home
        or not candidate.is_dir()
        or any(part in {".", ".."} for part in local.parts)
    ):
        raise _UnsafeScratch
    segment = candidate
    while segment != home:
        try:
            info = segment.lstat()
        except OSError as exc:
            raise _UnsafeScratch from exc
        if (
            not segment.is_dir()
            or segment.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise _UnsafeScratch
        segment = segment.parent
    if not provision._known_fixed_local_volume(kernel, candidate):
        raise _UnsafeScratch
    return candidate


def _make_native_fixture(
    kernel: Any,
    advapi: Any,
    target: Path,
    sid: str,
    scenario: PrivateWindowsOwnerAclScenario,
    provision: Any,
) -> None:
    """One native CREATE with all DACL attributes specified at creation time."""
    if target.exists() or target.is_symlink() or not provision._SID.fullmatch(sid):
        raise _UnsafeScratch
    if scenario in {
        PrivateWindowsOwnerAclScenario.PROTECTED_OWNER,
        PrivateWindowsOwnerAclScenario.SPOOFED_OWNER,
    }:
        created, _error = provision._create_directory_explicit_dacl(
            kernel, advapi, target, sid
        )
        if not created:
            raise _UnsafeScratch
        return
    if scenario is PrivateWindowsOwnerAclScenario.UNPROTECTED_DACL:
        # Create with a protected DACL first: the negative control must never
        # have an unexpectedly permissive inherited-ACL creation interval.
        created, _error = provision._create_directory_explicit_dacl(
            kernel, advapi, target, sid
        )
        if not created:
            raise _UnsafeScratch
        # Explicitly clear SE_DACL_PROTECTED on this ONE owned scratch child.
        # CreateDirectoryW alone cannot prove the resulting protection bit.
        _unprotect_scratch_dacl(target, sid)
        return
    if scenario is PrivateWindowsOwnerAclScenario.EVERYONE_READ_DACL:
        sddl = (
            f"O:{sid}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
            f"(A;OICI;FA;;;{sid})(A;OICI;GR;;;WD)"
        )
    else:
        raise _UnsafeScratch
    descriptor = ctypes.c_void_p()
    if (
        not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None
        )
        or not descriptor.value
    ):
        raise _UnsafeScratch
    try:
        attributes = provision._SecurityAttributes(
            ctypes.sizeof(provision._SecurityAttributes), descriptor, False
        )
        if not kernel.CreateDirectoryW(str(target), ctypes.byref(attributes)):
            raise _UnsafeScratch
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)


def _unprotect_scratch_dacl(target: Path, expected_sid: str) -> None:
    """Unprotect one owned disposable directory DACL via a retained HANDLE.

    The initial directory is restrictive at birth. For this intentionally
    negative test ONLY, ask Windows to re-enable inheritance. Read the native
    control bit before and after; if Windows does not do so, refuse rather
    than mislabel protected ACL evidence as an unprotected fixture. Never
    accepts a caller path; called solely with our newly created scratch child.
    """
    from pds_core import _teacher_private_windows_preflight as wincheck

    if target.is_symlink() or getattr(target.lstat(), "st_file_attributes", 0) & 0x400:
        raise _UnsafeScratch
    kernel, advapi = wincheck._bind_api()
    # WRITE_DAC is used exclusively inside the owned disposable negative
    # fixture. The production ACL preflight remains strictly read-only.
    write_dac = 0x00040000
    handle = kernel.CreateFileW(
        str(target),
        _READ_ATTRIBUTES | _READ_CONTROL | write_dac,
        _FILE_SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _BACKUP_SEMANTICS | _OPEN_REPARSE_POINT,
        None,
    )
    value = ctypes.cast(handle, ctypes.c_void_p).value
    if value is None or value == _INVALID_HANDLE:
        raise _UnsafeScratch
    try:
        matches, protected = _read_security_control(
            kernel, advapi, int(value), expected_sid, wincheck
        )
        if not matches or not protected:
            raise _UnsafeScratch
        dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        # SE_FILE_OBJECT=1, DACL_SECURITY_INFORMATION=4.
        status = advapi.GetSecurityInfo(
            wintypes.HANDLE(value),
            1,
            4,
            None,
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if status != 0:
            raise _UnsafeScratch
        try:
            if not descriptor.value or not dacl.value:
                raise _UnsafeScratch
            advapi.SetSecurityInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                wintypes.DWORD,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            advapi.SetSecurityInfo.restype = wintypes.DWORD
            # UNPROTECTED_DACL_SECURITY_INFORMATION=0x20000000, plus DACL=4.
            # Pass the actual existing DACL. NEVER pass a NULL DACL (which
            # would mean full access for everyone).
            changed = advapi.SetSecurityInfo(
                wintypes.HANDLE(value), 1, 0x20000004, None, None, dacl, None
            )
            if changed != 0:
                raise _UnsafeScratch
        finally:
            if descriptor.value:
                kernel.LocalFree(descriptor)
        matches, protected = _read_security_control(
            kernel, advapi, int(value), expected_sid, wincheck
        )
        if not matches or protected:
            raise _UnsafeScratch
    finally:
        kernel.CloseHandle(wintypes.HANDLE(value))


def _read_security_control(
    kernel: Any, advapi: Any, handle: int, token_sid: str, wincheck: Any
) -> tuple[bool, bool]:
    """Opened-handle owner SID and protected-DACL control; no ACL mutation."""
    from pds_core import _teacher_private_inspection as inspection

    owner_ptr = ctypes.c_void_p()
    dacl_ptr = ctypes.c_void_p()
    sd_ptr = ctypes.c_void_p()
    code = advapi.GetSecurityInfo(
        wintypes.HANDLE(handle),
        1,
        5,
        ctypes.byref(owner_ptr),
        None,
        ctypes.byref(dacl_ptr),
        None,
        ctypes.byref(sd_ptr),
    )
    if code != 0:
        raise _UnsafeScratch
    try:
        if not sd_ptr.value or not owner_ptr.value or not dacl_ptr.value:
            raise _UnsafeScratch
        native_sid = wincheck._sid_string(kernel, advapi, owner_ptr.value)
        advapi.GetSecurityDescriptorControl.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.WORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not advapi.GetSecurityDescriptorControl(
            sd_ptr, ctypes.byref(control), ctypes.byref(revision)
        ):
            raise _UnsafeScratch
        if not revision.value or not native_sid.startswith("S-1-"):
            raise _UnsafeScratch
        # Token SID may not be supplied by a caller. It was acquired from the
        # same running process with impersonation rejection by inspection.
        if type(token_sid) is not str or not token_sid.startswith("S-1-"):
            raise _UnsafeScratch
        if not inspection._effective_owner("win32").value == token_sid:
            raise _UnsafeScratch
        return native_sid == token_sid, bool(control.value & _DACL_PROTECTED)
    finally:
        if sd_ptr.value:
            kernel.LocalFree(sd_ptr)


def probe_disposable_windows_owner_acl(
    scenario: PrivateWindowsOwnerAclScenario,
) -> PrivateWindowsOwnerAclReview:
    """Observe protected DACL control and owner SID in disposable Win32 data.

    Does not grant production ACL, full effective-access, binding or Notes
    authority, even if every native scratch evidence check succeeds.
    """
    state = PrivateWindowsOwnerAclState
    if type(scenario) is not PrivateWindowsOwnerAclScenario:
        return _answer(state.INVALID_REQUEST_REFUSED)
    if sys.platform == "linux":
        return _answer(state.WINDOWS_ONLY_REFUSED)
    if sys.platform != "win32":
        return _answer(state.WINDOWS_ONLY_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _answer(state.REQUIREMENT_DRIFT_REFUSED)
    try:
        from pds_core import _teacher_private_inspection as inspection
        from pds_core import _teacher_private_native_preflight as native
        from pds_core import _teacher_private_windows_preflight as wincheck
        from pds_core import _teacher_private_windows_provision as provision

        first = inspection._effective_owner("win32")
        if first.kind != "windows_token_sid" or not provision._SID.fullmatch(
            first.value
        ):
            raise _UnsafeScratch
        kernel, advapi = provision._windows_api()
        check_kernel, check_advapi = wincheck._bind_api()
        with tempfile.TemporaryDirectory(prefix="pds238_3g99_acl_") as scratch_name:
            initial_parent = Path(scratch_name)
            selected = _fixture_parent(initial_parent, kernel, provision)
            # A second owned temporary root may be on LOCALAPPDATA/Temp when
            # the current scratch volume lacks supported native ACL semantics.
            with tempfile.TemporaryDirectory(
                prefix="pds238_3g99_native_", dir=selected
            ) as dirname:
                base = Path(dirname)
                target = base / "acl-review"
                if base.is_symlink() or base.parent.resolve(
                    strict=True
                ) != selected.resolve(strict=True):
                    raise _UnsafeScratch
                if scenario is PrivateWindowsOwnerAclScenario.MISSING_CHILD:
                    if target.exists() or target.is_symlink():
                        raise _UnsafeScratch
                    return _answer(
                        state.MISSING_CHILD_REFUSED,
                        scenario=scenario.value,
                        token=True,
                        preserved=True,
                    )
                _make_native_fixture(
                    kernel, advapi, target, first.value, scenario, provision
                )
                if (
                    target.is_symlink()
                    or getattr(target.lstat(), "st_file_attributes", 0) & 0x400
                ):
                    raise _UnsafeScratch
                handle = check_kernel.CreateFileW(
                    str(target),
                    _READ_ATTRIBUTES | _READ_CONTROL,
                    _FILE_SHARE_ALL,
                    None,
                    _OPEN_EXISTING,
                    _BACKUP_SEMANTICS | _OPEN_REPARSE_POINT,
                    None,
                )
                handle_value = ctypes.cast(handle, ctypes.c_void_p).value
                if handle_value is None or handle_value == _INVALID_HANDLE:
                    raise _UnsafeScratch
                try:
                    matches, protected = _read_security_control(
                        check_kernel,
                        check_advapi,
                        int(handle_value),
                        first.value,
                        wincheck,
                    )
                    owner_for_acl = (
                        inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-999999")
                        if scenario is PrivateWindowsOwnerAclScenario.SPOOFED_OWNER
                        else first
                    )
                    shape = wincheck._handle_dacl_state(
                        check_kernel, check_advapi, int(handle_value), owner_for_acl
                    )
                    if inspection._effective_owner("win32") != first:
                        raise _UnsafeScratch
                finally:
                    check_kernel.CloseHandle(wintypes.HANDLE(handle_value))
                if scenario is PrivateWindowsOwnerAclScenario.PROTECTED_OWNER:
                    if (
                        not matches
                        or not protected
                        or shape
                        is not native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
                    ):
                        raise _UnsafeScratch
                    selected_state = state.PROTECTED_DACL_SHAPE_OBSERVED_HOLD
                elif scenario is PrivateWindowsOwnerAclScenario.UNPROTECTED_DACL:
                    if not matches or protected:
                        raise _UnsafeScratch
                    # Do not rely on ACE shape as proof when DACL is not
                    # inheritance-protected (even if no extra ACE currently).
                    selected_state = state.UNPROTECTED_DACL_REFUSED
                elif scenario is PrivateWindowsOwnerAclScenario.EVERYONE_READ_DACL:
                    if (
                        not matches
                        or not protected
                        or shape is not native.NativePrivatePreflightState.REFUSED_ACL
                    ):
                        raise _UnsafeScratch
                    selected_state = state.EVERYONE_ACCESS_REFUSED
                elif scenario is PrivateWindowsOwnerAclScenario.SPOOFED_OWNER:
                    if (
                        not matches
                        or not protected
                        or shape is not native.NativePrivatePreflightState.REFUSED_OWNER
                    ):
                        raise _UnsafeScratch
                    selected_state = state.OWNER_MISMATCH_REFUSED
                else:
                    raise _UnsafeScratch
                return _answer(
                    selected_state,
                    scenario=scenario.value,
                    token=True,
                    owner=matches,
                    dacl=True,
                    control=True,
                    classified=True,
                    preserved=True,
                )
    except (
        OSError,
        RuntimeError,
        ValueError,
        AttributeError,
        TypeError,
        OverflowError,
        _UnsafeScratch,
        ctypes.ArgumentError,
    ):
        return _answer(state.SCRATCH_CUSTODY_REFUSED)
