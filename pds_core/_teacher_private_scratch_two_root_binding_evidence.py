"""Core #238 Slice 3G98: synthetic two-root association/ownership evidence holds.

A single fixed enum selects one newly created, disposable two-root fixture.
No caller path, principal, credential, workspace metadata, write payload or
callback is accepted. The effective OS owner and ACL of production roots are
NOT qualified. Even coherent evidence cannot admit a production binding.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from pds_core import _teacher_private_file_lock as locking
from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_native_writer_window as custody


class PrivateTwoRootEvidenceScenario(str, Enum):
    CONSISTENT = "consistent"
    ASSOCIATION_MISMATCH = "association_mismatch"
    OWNER_MARKER_MISMATCH = "owner_marker_mismatch"
    DUPLICATE_WORKSPACE_COPY = "duplicate_workspace_copy"
    UNSUPPORTED_DESCRIPTOR_VERSION = "unsupported_descriptor_version"
    REGISTRY_EXTRA_FIELD = "registry_extra_field"
    POSIX_PRIVATE_ROOT_MODE_DRIFT = "posix_private_root_mode_drift"


class PrivateTwoRootEvidenceState(str, Enum):
    CONSISTENT_BUT_UNQUALIFIED_HOLD = "consistent_but_unqualified_hold"
    ASSOCIATION_CONFLICT_HOLD = "association_conflict_hold"
    SYNTHETIC_OWNER_MARKER_CONFLICT_HOLD = "synthetic_owner_marker_conflict_hold"
    DUPLICATE_ASSOCIATION_HOLD = "duplicate_association_hold"
    MALFORMED_METADATA_HOLD = "malformed_metadata_hold"
    POSIX_PROTECTION_REFUSED = "posix_protection_refused"
    WINDOWS_DACL_UNQUALIFIED = "windows_dacl_unqualified"
    INVALID_REQUEST_REFUSED = "invalid_request_refused"
    REQUIREMENT_DRIFT_REFUSED = "requirement_drift_refused"
    UNSUPPORTED_REFUSED = "unsupported_refused"
    NATIVE_CUSTODY_REFUSED = "native_custody_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateTwoRootEvidenceReview:
    state: PrivateTwoRootEvidenceState
    native_workspace_parent_retained: bool = False
    native_private_parent_retained: bool = False
    cooperative_private_lock_held: bool = False
    two_root_file_images_checked: bool = False
    native_two_root_identities_rechecked: bool = False
    posix_owner_mode_observed_scratch_only: bool = False
    duplicate_association_detected: bool = False
    journal_or_notes_touched: bool = False
    production_mutation_admitted: bool = False
    explicit_binding_allowed: bool = False
    effective_os_owner_acl_qualified: bool = False
    copied_descriptor_authorizes_binding: bool = False
    automatic_replay_allowed: bool = False
    automatic_retry_allowed: bool = False
    journal_retirement_allowed: bool = False
    notes_records_available: bool = False
    directory_crash_durability_qualified: bool = False
    multi_document_atomic_commit_qualified: bool = False
    noncooperating_writer_exclusion_qualified: bool = False
    atomic_content_compare_and_swap_qualified: bool = False

    def __repr__(self) -> str:
        return "PrivateTwoRootEvidenceReview(scratch_only=True, non_authorizing=True)"


class _UnsafeScratch(Exception):
    """Refusal does not disclose synthetic paths or native identities."""


_DESCRIPTOR = "teacher-private-association.json"
_REGISTRY = "binding-registry.json"
_LOCK = ".binding.lock"
_SCHEMA = "pds.core.issue238.synthetic-binding-evidence.v1"
_ASSOCIATION = "fixed-synthetic-association-3g98"
_OTHER_ASSOCIATION = "fixed-different-association-3g98"
_OWNER_MARKER = "synthetic-owner-marker-not-an-os-principal"
_OTHER_OWNER_MARKER = "different-synthetic-owner-marker"
_ROOT_NAMES = ("workspace", "private")


def _json_bytes(value: dict[str, str]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )


def _descriptor(*, association: str = _ASSOCIATION, schema: str = _SCHEMA) -> bytes:
    return _json_bytes(
        {"schema": schema, "association": association, "kind": "workspace_descriptor"}
    )


def _registry(
    *, association: str = _ASSOCIATION, owner_marker: str = _OWNER_MARKER
) -> bytes:
    return _json_bytes(
        {
            "schema": _SCHEMA,
            "association": association,
            "owner_marker": owner_marker,
            "kind": "local_private_binding",
        }
    )


def _exclusive_file(path: Path, payload: bytes) -> None:
    # Correct POSIX protection at creation, not after a permissive window.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if sys.platform == "win32":
        flags |= getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # The disposable fixture owns its files; never repair an unrelated tree.
        raise


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    info = path.lstat()
    if path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400):
        raise _UnsafeScratch
    if directory != stat.S_ISDIR(info.st_mode):
        raise _UnsafeScratch
    if info.st_ino <= 0:
        raise _UnsafeScratch
    if sys.platform == "linux":
        getter = getattr(os, "geteuid", None)
        if getter is None or info.st_uid != getter():
            raise _UnsafeScratch
        if stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
            raise _UnsafeScratch
    elif not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise _UnsafeScratch
    return int(info.st_dev), int(info.st_ino)


def _read_file(path: Path) -> bytes:
    initial = _identity(path, directory=False)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if sys.platform == "linux":
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if not nofollow:
            raise _UnsafeScratch
        flags |= nofollow
    else:
        flags |= getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        current = os.fstat(fd)
        if (int(current.st_dev), int(current.st_ino)) != initial:
            raise _UnsafeScratch
        if current.st_size < 1 or current.st_size > 2048:
            raise _UnsafeScratch
        payload = os.read(fd, 2049)
        if len(payload) != current.st_size or len(payload) > 2048:
            raise _UnsafeScratch
        if _identity(path, directory=False) != initial:
            raise _UnsafeScratch
        return payload
    finally:
        os.close(fd)


def _parse(payload: bytes, keys: frozenset[str]) -> dict[str, str] | None:
    try:
        data: Any = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    if type(data) is not dict or set(data) != keys:
        return None
    if any(type(value) is not str or len(value) > 128 for value in data.values()):
        return None
    return cast(dict[str, str], data)


def _result(
    state: PrivateTwoRootEvidenceState,
    *,
    observed: bool = False,
    duplicate: bool = False,
) -> PrivateTwoRootEvidenceReview:
    return PrivateTwoRootEvidenceReview(
        state=state,
        native_workspace_parent_retained=observed,
        native_private_parent_retained=observed,
        cooperative_private_lock_held=observed,
        two_root_file_images_checked=observed,
        native_two_root_identities_rechecked=observed,
        posix_owner_mode_observed_scratch_only=observed and sys.platform == "linux",
        duplicate_association_detected=duplicate,
    )


def _windows_posix_mode_requires_refusal(
    scenario: PrivateTwoRootEvidenceScenario,
) -> bool:
    """Keep the pre-scratch Windows refusal without narrowing the later enum branch."""
    return (
        sys.platform == "win32"
        and scenario is PrivateTwoRootEvidenceScenario.POSIX_PRIVATE_ROOT_MODE_DRIFT
    )


def probe_disposable_two_root_binding_evidence(
    scenario: PrivateTwoRootEvidenceScenario,
) -> PrivateTwoRootEvidenceReview:
    """Classify only fixed synthetic two-root evidence; authorize nothing.

    On Windows, an effective DACL check is not supplied. On Linux, 0600/0700
    and UID observation of disposable fixtures is not an ACL qualification of
    a real private root. Identical association IDs never authorize a clone.
    """
    state = PrivateTwoRootEvidenceState
    if type(scenario) is not PrivateTwoRootEvidenceScenario:
        return _result(state.INVALID_REQUEST_REFUSED)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED_REFUSED)
    if len(readiness._REQUIRED) != 9:
        return _result(state.REQUIREMENT_DRIFT_REFUSED)
    if _windows_posix_mode_requires_refusal(scenario):
        return _result(state.WINDOWS_DACL_UNQUALIFIED)
    try:
        with tempfile.TemporaryDirectory(prefix="pds238_3g98_binding_") as base:
            root = Path(base)
            workspace = root / _ROOT_NAMES[0]
            private = root / _ROOT_NAMES[1]
            workspace.mkdir(mode=0o700)
            private.mkdir(mode=0o700)
            _exclusive_file(workspace / _DESCRIPTOR, _descriptor())
            _exclusive_file(private / _REGISTRY, _registry())
            _exclusive_file(private / _LOCK, b"0")
            clone = root / "workspace-copy"
            if scenario is PrivateTwoRootEvidenceScenario.ASSOCIATION_MISMATCH:
                (private / _REGISTRY).write_bytes(
                    _registry(association=_OTHER_ASSOCIATION)
                )
            elif scenario is PrivateTwoRootEvidenceScenario.OWNER_MARKER_MISMATCH:
                (private / _REGISTRY).write_bytes(
                    _registry(owner_marker=_OTHER_OWNER_MARKER)
                )
            elif scenario is PrivateTwoRootEvidenceScenario.DUPLICATE_WORKSPACE_COPY:
                clone.mkdir(mode=0o700)
                _exclusive_file(clone / _DESCRIPTOR, _descriptor())
            elif (
                scenario
                is PrivateTwoRootEvidenceScenario.UNSUPPORTED_DESCRIPTOR_VERSION
            ):
                (workspace / _DESCRIPTOR).write_bytes(_descriptor(schema="v999"))
            elif scenario is PrivateTwoRootEvidenceScenario.REGISTRY_EXTRA_FIELD:
                data = json.loads(_registry())
                data["unexpected"] = "untrusted-extra-field"
                (private / _REGISTRY).write_bytes(_json_bytes(data))
            elif (
                scenario is PrivateTwoRootEvidenceScenario.POSIX_PRIVATE_ROOT_MODE_DRIFT
            ):
                private.chmod(0o755)
                try:
                    _identity(private, directory=True)
                except _UnsafeScratch:
                    return _result(state.POSIX_PROTECTION_REFUSED)
                raise _UnsafeScratch
            with locking.hold_existing_private_lock(private / _LOCK):
                with custody._retain_native_parent(workspace):
                    with custody._retain_native_parent(private):
                        roots_before = (
                            _identity(workspace, directory=True),
                            _identity(private, directory=True),
                        )
                        description = _read_file(workspace / _DESCRIPTOR)
                        binding = _read_file(private / _REGISTRY)
                        observed_names = {
                            "workspace": {x.name for x in workspace.iterdir()},
                            "private": {x.name for x in private.iterdir()},
                        }
                        if observed_names != {
                            "workspace": {_DESCRIPTOR},
                            "private": {_REGISTRY, _LOCK},
                        }:
                            raise _UnsafeScratch
                        if clone.is_dir():
                            if {x.name for x in clone.iterdir()} != {_DESCRIPTOR}:
                                raise _UnsafeScratch
                            if _read_file(clone / _DESCRIPTOR) != description:
                                raise _UnsafeScratch
                        d = _parse(
                            description, frozenset({"schema", "association", "kind"})
                        )
                        b = _parse(
                            binding,
                            frozenset(
                                {"schema", "association", "owner_marker", "kind"}
                            ),
                        )
                        if (
                            not d
                            or not b
                            or d.get("schema") != _SCHEMA
                            or b.get("schema") != _SCHEMA
                        ):
                            selected = state.MALFORMED_METADATA_HOLD
                        elif (
                            d["kind"] != "workspace_descriptor"
                            or b["kind"] != "local_private_binding"
                        ):
                            selected = state.MALFORMED_METADATA_HOLD
                        elif d["association"] != b["association"]:
                            selected = state.ASSOCIATION_CONFLICT_HOLD
                        elif b["owner_marker"] != _OWNER_MARKER:
                            selected = state.SYNTHETIC_OWNER_MARKER_CONFLICT_HOLD
                        elif clone.is_dir():
                            selected = state.DUPLICATE_ASSOCIATION_HOLD
                        else:
                            selected = state.CONSISTENT_BUT_UNQUALIFIED_HOLD
                        if (
                            _read_file(workspace / _DESCRIPTOR) != description
                            or _read_file(private / _REGISTRY) != binding
                            or (
                                _identity(workspace, directory=True),
                                _identity(private, directory=True),
                            )
                            != roots_before
                        ):
                            raise _UnsafeScratch
                        return _result(
                            selected,
                            observed=True,
                            duplicate=selected is state.DUPLICATE_ASSOCIATION_HOLD,
                        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        _UnsafeScratch,
        locking.PrivateExistingFileLockError,
        custody._UnsafeScratch,
    ):
        return _result(state.NATIVE_CUSTODY_REFUSED)
