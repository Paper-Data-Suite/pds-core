"""Core #238 3G81: native Windows protected-DACL scratch fixture, installed wheel.

The only created paths are uniquely owned scratch children. Windows uses the
current process token SID and creates four nested directories with explicit
inheritance-protected owner/SYSTEM/Administrators DACLs in the first native
CreateDirectoryW call. Retained-handle custody is then verified and refused
for a deliberately over-permissive control fixture. No PDS private store is
created or modified; the live user-local candidate root is never used.

Linux runs a no-fixture negative gate so both CI OS legs remain meaningful.
Neither successful case authorizes production writes or Notes.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import Any

_EXPECTED = "retained_private_root_observed_unqualified"
_REJECTED = "native_protection_refused"
_NOT_OWNER = "owner_unavailable"
_MISSING = "missing"


def _wheel_provenance(wheel: Path, source: Path, version: str) -> str:
    import pds_core
    from pds_core import _teacher_private_retained_root_custody as custody

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    modules = (pds_core, custody)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or not wheel.is_file()
        or wheel.suffix != ".whl"
        or any(
            module.__file__ is None
            or not Path(module.__file__).resolve(strict=True).is_relative_to(purelib)
            or Path(module.__file__).resolve(strict=True).is_relative_to(source)
            for module in modules
        )
    ):
        raise RuntimeError("candidate_wheel_provenance_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _create_explicit_acl_directory(
    kernel: Any, advapi: Any, path: Path, sid: str, *, extra_world: bool
) -> None:
    """One-shot scratch-only mkdir; never repair permissions after creation."""
    from pds_core import _teacher_private_windows_provision as provision

    if path.exists() or path.is_symlink() or not provision._SID.fullmatch(sid):
        raise RuntimeError("scratch_directory_already_exists_or_sid_invalid")
    if not extra_world:
        created, error = provision._create_directory_explicit_dacl(
            kernel, advapi, path, sid
        )
    else:
        # Deliberately unsafe fixture: add Everyone READ in the ORIGINAL DACL,
        # without exposing an inherited-permission interval.
        # Even the negative Everyone-readable control has the correct owner.
        # Its refusal must result from the extra ACL grant, not owner mismatch.
        sddl = (
            f"O:{sid}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
            f"(A;OICI;FA;;;{sid})(A;OICI;GR;;;WD)"
        )
        sd = ctypes.c_void_p()
        if (
            not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, 1, ctypes.byref(sd), None
            )
            or not sd.value
        ):
            raise RuntimeError("scratch_bad_acl_description_refused")
        try:
            attrs = provision._SecurityAttributes(
                ctypes.sizeof(provision._SecurityAttributes), sd, False
            )
            created = bool(kernel.CreateDirectoryW(str(path), ctypes.byref(attrs)))
            error = 0 if created else int(getattr(ctypes, "get_last_error")())
        finally:
            kernel.LocalFree(sd)
    if not created:
        # Never include the created path or account SID in routine output.
        raise RuntimeError("scratch_explicit_acl_creation_refused_" + str(error))


def _qualified_windows_fixture_parent(
    scratch: Path, kernel: Any, provision: Any
) -> Path:
    """Select only supported fixed NTFS/ReFS scratch, never a production root.

    Hosted CI may place RUNNER_TEMP on an unqualified D: ephemeral volume.
    Preserve the existing strict backing check; fall back solely to the
    current OS user's existing, ordinary LOCALAPPDATA/Temp directory. No
    fallback location is created, repaired, or trusted as a Notes store.
    """
    if provision._known_fixed_local_volume(kernel, scratch):
        return scratch
    local_text = os.environ.get("LOCALAPPDATA")
    if not local_text:
        raise RuntimeError("no_qualified_local_fixture_volume")
    local = Path(local_text)
    candidate = local / "Temp"
    home = Path.home()
    if (
        not local.is_absolute()
        or not candidate.is_relative_to(home)
        or candidate == home
        or any(part in {".", ".."} for part in local.parts)
        or not candidate.is_dir()
    ):
        raise RuntimeError("local_fixture_parent_unqualified")
    # Reject existing junctions, symlinks and untrusted name substitutions.
    segment = candidate
    while segment != home:
        try:
            info = segment.lstat()
        except OSError as exc:
            raise RuntimeError("local_fixture_ancestry_unverifiable") from exc
        if (
            not segment.is_dir()
            or segment.is_symlink()
            or (getattr(info, "st_file_attributes", 0) & 0x400)
        ):
            raise RuntimeError("local_fixture_ancestry_unqualified")
        segment = segment.parent
    if not provision._known_fixed_local_volume(kernel, candidate):
        raise RuntimeError("no_qualified_local_fixture_volume")
    return candidate


def _windows_fixture(scratch: Path) -> dict[str, object]:
    """All native CREATE operations are constrained to one own temp subtree."""
    if sys.platform != "win32":
        raise RuntimeError("windows_fixture_on_unsupported_platform")
    from pds_core import _teacher_private_inspection as inspection
    from pds_core import _teacher_private_native_preflight as native_preflight
    from pds_core import _teacher_private_retained_root_custody as custody
    from pds_core import _teacher_private_windows_preflight as wincheck
    from pds_core import _teacher_private_windows_provision as provision

    owner = inspection._effective_owner("win32")
    if owner.kind != "windows_token_sid":
        raise RuntimeError("windows_process_token_owner_unavailable")
    kernel, advapi = provision._windows_api()
    selected = _qualified_windows_fixture_parent(scratch, kernel, provision)
    with tempfile.TemporaryDirectory(prefix="core238_3g81_", dir=selected) as dirname:
        base = Path(dirname)
        if base.is_symlink() or base.parent.resolve(strict=True) != selected.resolve(
            strict=True
        ):
            raise RuntimeError("scratch_child_scope_refused")
        secure = base
        for name in ("owner", "private", "notes", "v1"):
            secure = secure / name
            _create_explicit_acl_directory(
                kernel, advapi, secure, owner.value, extra_world=False
            )
        preflight_state = wincheck._native_windows_walk(secure, owner).value
        first_state = custody._probe_existing(secure, owner).value
        second_state = custody._probe_existing(secure, owner).value
        if (
            preflight_state != "restrictive_unqualified"
            or first_state != _EXPECTED
            or second_state != _EXPECTED
        ):
            # Three enum values only; no SID, private path, handle or ACL bytes.
            allowed_preflight = {
                state.value for state in native_preflight.NativePrivatePreflightState
            }
            allowed_custody = {
                state.value for state in custody.PrivateRetainedRootState
            }
            if (
                preflight_state not in allowed_preflight
                or first_state not in allowed_custody
                or second_state not in allowed_custody
            ):
                raise RuntimeError("protected_native_custody_fixture_unknown_state")
            raise RuntimeError(
                "protected_native_custody_fixture_refused:"
                + preflight_state
                + "/"
                + first_state
                + "/"
                + second_state
            )
        if custody._probe_existing(secure / "absent", owner).value != _MISSING:
            raise RuntimeError("missing_native_leaf_not_refused")
        spoofed_owner = inspection.EffectiveOSOwner("windows_token_sid", "S-1-5-999999")
        if custody._probe_existing(secure, spoofed_owner).value != _NOT_OWNER:
            raise RuntimeError("spoofed_owner_not_refused")
        unprotected = base
        for index, name in enumerate(("foreign", "private", "notes", "v1")):
            unprotected = unprotected / name
            _create_explicit_acl_directory(
                kernel, advapi, unprotected, owner.value, extra_world=index == 3
            )
        if custody._probe_existing(unprotected, owner).value != _REJECTED:
            raise RuntimeError("everyone_read_acl_was_not_refused")
        # Check both independent native-identity passes have released handles;
        # TemporaryDirectory will remove ONLY children it just created.
        if not secure.is_dir() or not unprotected.is_dir():
            raise RuntimeError("fixture_changed_unexpectedly")
    return {
        "protected_owner_dacl_fixture": _EXPECTED,
        "missing_protected_leaf": _MISSING,
        "forged_effective_owner": _NOT_OWNER,
        "everyone_read_dacl_fixture": _REJECTED,
        "native_identity_rechecked_with_retained_handles": True,
        "fixed_local_ntfs_or_refs_qualified_for_fixture": True,
    }


def _linux_negative_fixture(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_retained_root_custody as custody

    if sys.platform != "linux" or not scratch.is_dir():
        raise RuntimeError("linux_negative_fixture_scope_refused")
    before = tuple(scratch.iterdir())
    # This gate has NO Linux fixture creation: the 3G80 Linux dirfd test is
    # already executed by the earlier installed/native test suite.
    review = custody.review_existing_private_root_native_custody()
    if not isinstance(review.state, custody.PrivateRetainedRootState):
        raise RuntimeError("linux_custody_enum_refused")
    if tuple(scratch.iterdir()) != before:
        raise RuntimeError("linux_no_fixture_modified_scratch")
    return {
        "windows_native_fixture": "not_applicable_linux",
        "linux_no_fixture_writes": True,
    }


def _production_barrier() -> None:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier
    from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    observed = readiness.review_private_production_readiness()
    intent = canon._canonical_fork_intent()
    result = barrier.review_private_production_write_barrier(
        scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
        intent.witness.registry_revision_before,
        intent,
    )
    if (
        observed.state.value
        not in {"production_blocked", "probe_refused_production_blocked"}
        or observed.unqualified_requirements != readiness._REQUIRED
        or len(observed.unqualified_requirements) != 9
        or result.state.value != "production_blocked"
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("fixture_must_not_grant_production_authority")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform not in {"linux", "win32"}:
        raise RuntimeError("unsupported_native_platform")
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        not scratch.is_dir()
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
        or scratch.is_symlink()
        or scratch.name != "scratch"
        or not os.access(scratch, os.W_OK)
    ):
        raise RuntimeError("unsafe_scratch_or_report_scope")
    digest = _wheel_provenance(wheel, source, args.expected_version)
    _production_barrier()
    platform_evidence = (
        _windows_fixture(scratch)
        if sys.platform == "win32"
        else _linux_negative_fixture(scratch)
    )
    _production_barrier()
    evidence: dict[str, object] = {
        "schema": "pds.core.issue238.installed-windows-protected-fixture.v1",
        "result": "passed_non_authorizing_protected_windows_fixture_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        "native_fixture": platform_evidence,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "transaction_commit_qualified": False,
        "noncooperating_writer_exclusion_qualified": False,
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_WINDOWS_PROTECTED_FIXTURE: PASS (scratch DACL only)")
    print("QUALIFIED_WHEEL_SHA256: " + digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ) as exc:
        print(
            "ISSUE238_INSTALLED_WINDOWS_PROTECTED_FIXTURE: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
