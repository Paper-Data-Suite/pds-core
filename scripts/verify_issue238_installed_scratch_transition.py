"""Installed-wheel native SCRATCH replacement acceptance for Core issue #238.

Only synthetic files under an explicitly supplied disposable root are touched.
This is not production binding, persistence qualification, journal retirement,
or Notes authority. Run with a clean installed candidate wheel and Python -I.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import stat
import sys
import sysconfig
import tempfile
from pathlib import Path


_AFTER = b"issue238-synthetic-after-v1"
_BEFORE = b"issue238-synthetic-before-v1"


def _native_posix_replace(root: Path) -> None:
    """One POSIX scratch replace with retained before/stage inode custody."""
    source, target = root / "stage", root / "registry.json"
    source.write_bytes(_AFTER)
    target.write_bytes(_BEFORE)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("posix_nofollow_unavailable")
    flags = os.O_RDONLY | nofollow
    original_fd: int | None = None
    stage_fd: int | None = None
    try:
        original_fd = os.open(target, flags)
        stage_fd = os.open(source, flags)
        before = os.fstat(original_fd)
        stage = os.fstat(stage_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(stage.st_mode)
            or (before.st_dev, before.st_ino) == (stage.st_dev, stage.st_ino)
            or before.st_dev != stage.st_dev
            or target.read_bytes() != _BEFORE
            or source.read_bytes() != _AFTER
        ):
            raise RuntimeError("posix_preimage_unqualified")
        # Exactly one native replacement attempt, never a fallback or retry.
        os.replace(source, target)
        named = os.stat(target, follow_symlinks=False)
        retained_before = os.fstat(original_fd)
        retained_stage = os.fstat(stage_fd)
        if (
            source.exists()
            or target.read_bytes() != _AFTER
            or (named.st_dev, named.st_ino) != (stage.st_dev, stage.st_ino)
            or (retained_before.st_dev, retained_before.st_ino)
            != (before.st_dev, before.st_ino)
            or (retained_stage.st_dev, retained_stage.st_ino)
            != (stage.st_dev, stage.st_ino)
        ):
            raise RuntimeError("posix_postimage_unqualified")
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        if original_fd is not None:
            os.close(original_fd)


def _native_windows_replace(root: Path) -> None:
    """One actual installed Core FileRenameInfoEx on controlled scratch names."""
    import ctypes
    from ctypes import wintypes

    from pds_core import _teacher_private_native_journal_anchor as anchor
    from pds_core import _teacher_private_windows_preflight as wincheck
    from pds_core import (
        _teacher_private_windows_registry_replace_attempt as replacement,
    )

    source, target = root / "stage", root / "registry.json"
    source.write_bytes(_AFTER)
    target.write_bytes(_BEFORE)
    kernel, _advapi = wincheck._bind_api()
    original_handle: int | None = None
    stage_handle: int | None = None
    reopened_handle: int | None = None
    bad = ctypes.c_void_p(-1).value
    try:
        for role, path in (("original", target), ("stage", source)):
            raw = kernel.CreateFileW(
                str(path), 0x80 | 0x20000, 7, None, 3, 0x00200000, None
            )
            handle = ctypes.cast(raw, ctypes.c_void_p).value
            if handle in (None, bad):
                raise RuntimeError("windows_handle_open_refused")
            if role == "original":
                original_handle = handle
            else:
                stage_handle = handle
        assert original_handle is not None and stage_handle is not None
        original_id = anchor._windows_id(kernel, original_handle)
        stage_id = anchor._windows_id(kernel, stage_handle)
        if (
            original_id is None
            or stage_id is None
            or original_id == stage_id
            or target.read_bytes() != _BEFORE
            or source.read_bytes() != _AFTER
        ):
            raise RuntimeError("windows_preimage_unqualified")
        # One and only one installed Core native replacement. Never retry.
        moved = replacement._replace_open_target_posix(source, target)
        if not moved:
            raise RuntimeError("windows_rename_refused_preserve")
        try:
            named = target.read_bytes()
        except OSError as exc:
            raise RuntimeError("windows_target_unavailable_preserve") from exc
        if source.exists() or named != _AFTER:
            raise RuntimeError("windows_named_postimage_unqualified_preserve")
        raw_reopened = kernel.CreateFileW(
            str(target), 0x80 | 0x20000, 7, None, 3, 0x00200000, None
        )
        reopened_handle = ctypes.cast(raw_reopened, ctypes.c_void_p).value
        if reopened_handle in (None, bad):
            reopened_handle = None
            raise RuntimeError("windows_target_reopen_refused_preserve")
        if (
            anchor._windows_id(kernel, reopened_handle) != stage_id
            or anchor._windows_id(kernel, original_handle) != original_id
            or anchor._windows_id(kernel, stage_handle) != stage_id
        ):
            raise RuntimeError("windows_identity_postimage_unqualified_preserve")
    finally:
        for handle in (reopened_handle, stage_handle, original_handle):
            if handle is not None:
                kernel.CloseHandle(wintypes.HANDLE(handle))


def _validate_installed(wheel: Path, version: str, source: Path) -> tuple[str, str]:
    import pds_core

    expected_root = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    installed = Path(pds_core.__file__).resolve(strict=True)
    if (
        not installed.is_relative_to(expected_root)
        or installed.is_relative_to(source)
        or importlib.metadata.version("pds-core") != version
    ):
        raise RuntimeError("installed_wheel_provenance_unqualified")
    if not wheel.is_file() or not wheel.name.endswith(".whl"):
        raise RuntimeError("candidate_wheel_missing")
    return hashlib.sha256(wheel.read_bytes()).hexdigest(), str(installed.parent.name)


def _verify_permanent_barrier() -> None:
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier
    from pds_core import (
        _teacher_private_recovery_synthetic_canonical_replace as canonical,
    )
    from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    intent = canonical._canonical()
    review = barrier.review_private_production_write_barrier(
        scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
        intent.witness.registry_revision_before,
        intent,
    )
    if (
        review.state
        is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        or tuple(review.unqualified_requirements) != barrier._REQUIRED
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("production_write_barrier_changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", type=str, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_checkout.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        sys.platform not in {"win32", "linux"}
        or not scratch.is_dir()
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
        or type(args.expected_version) is not str
        or args.expected_version != "0.6.6"
    ):
        raise RuntimeError("unsupported_or_unsafe_probe_scope")
    digest, _package_name = _validate_installed(wheel, args.expected_version, source)
    _verify_permanent_barrier()
    with tempfile.TemporaryDirectory(
        prefix="core238_3g70_disposable_", dir=scratch
    ) as tmp:
        root = Path(tmp)
        if sys.platform == "win32":
            _native_windows_replace(root)
        else:
            _native_posix_replace(root)
    _verify_permanent_barrier()
    evidence = {
        "schema": "pds.core.issue238.installed-scratch-transition.v1",
        "result": "passed_disposable_native_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": args.expected_version,
        "scratch_replacement_observed": True,
        "content_and_native_identity_postconditions": True,
        "production_mutation_admitted": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "transaction_commit_qualified": False,
        "journal_retirement_qualified": False,
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_SCRATCH_TRANSITION: PASS (scratch only; production blocked)"
    )
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
        AssertionError,
    ) as exc:
        # Never render filesystem paths, owner names, handle IDs or data bytes.
        print(
            "ISSUE238_INSTALLED_SCRATCH_TRANSITION: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
