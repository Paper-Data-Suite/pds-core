"""Installed-Core two-document native restart drill, strictly disposable (#238 3G71).

Three independent canonical FORK_COPY synthetic transactions are exercised:
prepared, registry-only applied, and both metadata images applied. Each
exercise retains native identities across no more than two exact operations,
closes handles, and reopens every document under a new observation. The journal
MUST remain pending throughout. No producer paths, secrets, authorization,
replay, retirement, or durable-production claims are accepted or returned.
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
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any, Iterator, cast


FileIdentity = tuple[int, int] | tuple[int, bytes]


def _write_new(path: Path, data: bytes) -> None:
    """Only under TemporaryDirectory; O_EXCL prevents overwriting scratch."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        position = 0
        while position < len(data):
            written = os.write(fd, data[position:])
            if written <= 0:
                raise RuntimeError("scratch_create_short_write")
            position += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _linux_id(path: Path) -> FileIdentity:
    details = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RuntimeError("posix_native_identity_refused")
    return (details.st_dev, details.st_ino)


def _windows_open(kernel: Any, path: Path) -> int:
    import ctypes

    raw = kernel.CreateFileW(str(path), 0x80 | 0x20000, 7, None, 3, 0x00200000, None)
    handle = ctypes.cast(raw, ctypes.c_void_p).value
    if handle in (None, ctypes.c_void_p(-1).value):
        raise RuntimeError("windows_native_handle_refused")
    assert handle is not None
    return handle


def _windows_id(kernel: Any, handle: int) -> FileIdentity:
    from pds_core import _teacher_private_native_journal_anchor as anchor

    identity = anchor._windows_id(kernel, handle)
    if identity is None or not any(identity[1]):
        raise RuntimeError("windows_native_identity_refused")
    return identity


def _named_id(path: Path) -> FileIdentity:
    if path.is_symlink():
        raise RuntimeError("scratch_link_refused")
    if sys.platform == "linux":
        return _linux_id(path)
    from pds_core import _teacher_private_windows_preflight as wincheck

    kernel, _ = wincheck._bind_api()
    handle = _windows_open(kernel, path)
    try:
        return _windows_id(kernel, handle)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


@contextmanager
def _held_file_ids(paths: dict[str, Path]) -> Iterator[dict[str, FileIdentity]]:
    """Retain all original and stage identities while both replacements occur."""
    if set(paths) != {
        "registry",
        "registry_stage",
        "descriptor",
        "descriptor_stage",
        "journal",
    }:
        raise RuntimeError("unexpected_scratch_file_set")
    if sys.platform == "linux":
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if not nofollow:
            raise RuntimeError("posix_nofollow_missing")
        fds: dict[str, int] = {}
        try:
            for label, path in paths.items():
                fd = os.open(path, os.O_RDONLY | nofollow)
                fds[label] = fd
            identities: dict[str, FileIdentity] = {}
            for label, fd in fds.items():
                details = os.fstat(fd)
                if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                    raise RuntimeError("posix_retained_file_unqualified")
                identities[label] = (details.st_dev, details.st_ino)
            if len(set(identities.values())) != len(paths):
                raise RuntimeError("posix_alias_detected")
            for label, path in paths.items():
                if _linux_id(path) != identities[label]:
                    raise RuntimeError("posix_name_handle_mismatch")
            yield identities
            for label, fd in fds.items():
                details = os.fstat(fd)
                if (details.st_dev, details.st_ino) != identities[label]:
                    raise RuntimeError("posix_retained_identity_changed")
        finally:
            for fd in reversed(tuple(fds.values())):
                os.close(fd)
    elif sys.platform == "win32":
        from pds_core import _teacher_private_windows_preflight as wincheck

        kernel, _ = wincheck._bind_api()
        handles: dict[str, int] = {}
        try:
            for label, path in paths.items():
                handles[label] = _windows_open(kernel, path)
            identities = {
                label: _windows_id(kernel, handle) for label, handle in handles.items()
            }
            if len(set(identities.values())) != len(paths):
                raise RuntimeError("windows_native_alias_detected")
            for label, path in paths.items():
                if _named_id(path) != identities[label]:
                    raise RuntimeError("windows_name_handle_mismatch")
            yield identities
            for label, handle in handles.items():
                if _windows_id(kernel, handle) != identities[label]:
                    raise RuntimeError("windows_retained_identity_changed")
        finally:
            for handle in reversed(tuple(handles.values())):
                kernel.CloseHandle(wintypes.HANDLE(handle))
    else:
        raise RuntimeError("unsupported_native_platform")


def _replace_once(source: Path, destination: Path) -> None:
    if source.parent != destination.parent or source == destination:
        raise RuntimeError("cross_directory_scratch_rename_refused")
    if sys.platform == "win32":
        from pds_core import (
            _teacher_private_windows_registry_replace_attempt as windows,
        )

        if not windows._replace_open_target_posix(source, destination):
            raise RuntimeError("windows_native_rename_refused_preserve")
    elif sys.platform == "linux":
        os.replace(source, destination)
    else:
        raise RuntimeError("unsupported_native_platform")


def _run_case(root: Path, mode: str) -> str:
    """Run one canonical two-document checkpoint, then independently reopen."""
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_transaction_intent as intents

    if mode not in {"prepared", "registry", "both"}:
        raise ValueError("unexpected_scratch_phase")
    checked = canon._canonical_fork_intent()
    encoded = intents.encode_private_transaction_intent(checked)
    if intents.decode_private_transaction_intent(encoded) != checked:
        raise RuntimeError("scratch_canonical_intent_refused")
    if (
        checked.registry_before == checked.registry_after
        or checked.descriptor_before == checked.descriptor_after
    ):
        raise RuntimeError("scratch_distinct_images_required")
    private = root / "private"
    transactions = private / "transactions"
    descriptor_dir = root / "workspace" / ".pds"
    transactions.mkdir(parents=True)
    descriptor_dir.mkdir(parents=True)
    tx = checked.witness.transaction_id
    paths = {
        "registry": private / "registry.json",
        "registry_stage": private / ("." + tx + ".registry-stage"),
        "descriptor": descriptor_dir / "teacher-private-association.json",
        "descriptor_stage": descriptor_dir / ("." + tx + ".descriptor-stage"),
        "journal": transactions / (tx + ".json"),
    }
    described = (
        checked.registry_before,
        checked.registry_after,
        checked.descriptor_before,
        checked.descriptor_after,
    )
    if any(type(raw) is not bytes or not raw for raw in described):
        raise RuntimeError("scratch_image_not_bytes")
    images: dict[str, bytes] = {
        "registry": cast(bytes, checked.registry_before),
        "registry_stage": checked.registry_after,
        "descriptor": cast(bytes, checked.descriptor_before),
        "descriptor_stage": checked.descriptor_after,
        "journal": encoded,
    }
    for label, path in paths.items():
        _write_new(path, images[label])
    if any(paths[label].read_bytes() != raw for label, raw in images.items()):
        raise RuntimeError("scratch_prepared_image_conflict")
    observed_ids: dict[str, FileIdentity]
    with _held_file_ids(paths) as held:
        observed_ids = dict(held)
        if mode != "prepared":
            _replace_once(paths["registry_stage"], paths["registry"])
            if (
                paths["registry_stage"].exists()
                or paths["registry"].read_bytes() != checked.registry_after
                or _named_id(paths["registry"]) != held["registry_stage"]
            ):
                raise RuntimeError("scratch_registry_postimage_refused")
        if mode == "both":
            _replace_once(paths["descriptor_stage"], paths["descriptor"])
            if (
                paths["descriptor_stage"].exists()
                or paths["descriptor"].read_bytes() != checked.descriptor_after
                or _named_id(paths["descriptor"]) != held["descriptor_stage"]
            ):
                raise RuntimeError("scratch_descriptor_postimage_refused")
        # Neither successful image replacement authorizes journal retirement.
        if (
            paths["journal"].read_bytes() != encoded
            or _named_id(paths["journal"]) != held["journal"]
        ):
            raise RuntimeError("scratch_pending_journal_changed")
    # Restart observation: original retained handles have all been closed.
    expected_registry = (
        checked.registry_before if mode == "prepared" else checked.registry_after
    )
    expected_descriptor = (
        checked.descriptor_after if mode == "both" else checked.descriptor_before
    )
    wanted_private = {"transactions", "registry.json"}
    if mode == "prepared":
        wanted_private.add(paths["registry_stage"].name)
    wanted_descriptor = {"teacher-private-association.json"}
    if mode != "both":
        wanted_descriptor.add(paths["descriptor_stage"].name)
    if (
        {p.name for p in private.iterdir()} != wanted_private
        or {p.name for p in descriptor_dir.iterdir()} != wanted_descriptor
        or {p.name for p in transactions.iterdir()} != {paths["journal"].name}
        or paths["journal"].read_bytes() != encoded
        or _named_id(paths["journal"]) != observed_ids["journal"]
        or paths["registry"].read_bytes() != expected_registry
        or paths["descriptor"].read_bytes() != expected_descriptor
        or _named_id(paths["registry"])
        != observed_ids["registry" if mode == "prepared" else "registry_stage"]
        or _named_id(paths["descriptor"])
        != observed_ids["descriptor_stage" if mode == "both" else "descriptor"]
    ):
        raise RuntimeError("scratch_restart_checkpoint_conflict_preserve")
    for label in ("registry_stage", "descriptor_stage"):
        exists = paths[label].exists()
        should_exist = (
            mode == "prepared" if label == "registry_stage" else mode != "both"
        )
        if exists != should_exist:
            raise RuntimeError("scratch_restart_stage_namespace_conflict")
        if exists and _named_id(paths[label]) != observed_ids[label]:
            raise RuntimeError("scratch_restart_stage_identity_changed")
    if mode == "prepared":
        return "prepared_hold"
    if mode == "registry":
        return "registry_after_descriptor_pending_hold"
    return "both_after_journal_pending_hold"


def _validate_installed(wheel: Path, source: Path, version: str) -> str:
    import pds_core

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    installed = Path(pds_core.__file__).resolve(strict=True)
    if (
        not installed.is_relative_to(purelib)
        or installed.is_relative_to(source)
        or importlib.metadata.version("pds-core") != version
        or version != "0.6.6"
        or not wheel.is_file()
        or wheel.suffix != ".whl"
    ):
        raise RuntimeError("installed_source_provenance_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _barrier() -> None:
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier
    from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    intent = canon._canonical_fork_intent()
    decision = barrier.review_private_production_write_barrier(
        scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
        intent.witness.registry_revision_before,
        intent,
    )
    if (
        decision.state
        is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        or tuple(decision.unqualified_requirements) != barrier._REQUIRED
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
    wheel = args.wheel.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        sys.platform not in {"win32", "linux"}
        or not scratch.is_dir()
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
    ):
        raise RuntimeError("unsupported_or_unsafe_native_scope")
    digest = _validate_installed(wheel, source, args.expected_version)
    _barrier()
    checkpoints: list[str] = []
    for mode in ("prepared", "registry", "both"):
        with tempfile.TemporaryDirectory(
            prefix="core238_3g71_disposable_", dir=scratch
        ) as temp:
            checkpoints.append(_run_case(Path(temp), mode))
        _barrier()
    required = [
        "prepared_hold",
        "registry_after_descriptor_pending_hold",
        "both_after_journal_pending_hold",
    ]
    if checkpoints != required:
        raise RuntimeError("scratch_restart_sequence_unqualified")
    evidence = {
        "schema": "pds.core.issue238.installed-two-document-restart.v1",
        "result": "passed_synthetic_native_restart_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "restart_checkpoints": checkpoints,
        "exact_registry_and_descriptor_images": True,
        "retained_native_and_reopened_identities": True,
        "canonical_pending_journal_preserved": True,
        "automatic_replay_allowed": False,
        "journal_retirement_allowed": False,
        "production_mutation_admitted": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "transaction_commit_qualified": False,
    }
    report.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_TWO_DOCUMENT_RESTART: PASS (synthetic; journal pending)")
    print("QUALIFIED_WHEEL_SHA256: " + digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
        AssertionError,
    ) as exc:
        # No paths, user identities, raw bytes, transaction IDs, or file IDs.
        print(
            "ISSUE238_INSTALLED_TWO_DOCUMENT_RESTART: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
