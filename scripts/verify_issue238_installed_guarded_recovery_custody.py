"""Core #238 Slice 3G74: installed-wheel, operation-owned recovery custody.

All paths are internally created disposable synthetic scratch. In an independent
interpreter, retain a cooperative lock and native parent/file handles for the
ENTIRE inferred pending-journal recovery decision, then repeat the observation
and compare the same native identities before releasing handles. An unexpected
change is CONFLICT_PRESERVE. No replay, journal retirement or production writes.

A synthetic advisory lock is not an OS-enforced barrier against noncooperating
processes and a successful directory flush is not power-loss durability.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, cast

STATES = {
    "prepared": "prepared_hold",
    "registry": "registry_after_descriptor_pending_hold",
    "both": "both_after_journal_pending_hold",
}
CONFLICT = "conflict_preserve"
LOCKED = "lock_contended_preserve"
TRIAGE = "verify_issue238_installed_recovery_triage.py"


class _CustodyRefused(Exception):
    pass


class _LockBusy(Exception):
    pass


def _load_triage(source: Path) -> ModuleType:
    candidate = source / "scripts" / TRIAGE
    if not candidate.is_file():
        raise _CustodyRefused
    spec = importlib.util.spec_from_file_location("core238_3g73_guarded", candidate)
    if spec is None or spec.loader is None:
        raise _CustodyRefused
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _operation_lock(root: Path) -> Iterator[None]:
    """Own a nonblocking, cooperative scratch lock until postcheck completes."""
    name = root.name
    if not name.startswith("core238_3g74_") or root.is_symlink():
        raise _CustodyRefused
    lock = root.parent / (name + ".operation-lock")
    if lock.is_symlink():
        raise _CustodyRefused
    try:
        with lock.open("x+b") as created:
            created.write(b"0")
            created.flush()
            os.fsync(created.fileno())
    except FileExistsError:
        pass
    with lock.open("r+b") as stream:
        initial = os.fstat(stream.fileno())
        named = lock.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or initial.st_size != 1
            or (initial.st_dev, initial.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise _CustodyRefused
        try:
            if sys.platform == "win32":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            elif sys.platform == "linux":
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                raise _CustodyRefused
        except (BlockingIOError, PermissionError) as exc:
            raise _LockBusy from exc
        try:
            yield
            current = os.fstat(stream.fileno())
            after = lock.stat(follow_symlinks=False)
            if (
                (current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino)
                or (after.st_dev, after.st_ino) != (initial.st_dev, initial.st_ino)
                or current.st_size != 1
            ):
                raise _CustodyRefused
        finally:
            if sys.platform == "win32":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _expected_paths(root: Path, source: Path) -> tuple[Path, ...]:
    """Paths are fixed by installed canonical intent, never an input list."""
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon

    reader = _load_triage(source)._load_previous(source)
    tx = canon._canonical_fork_intent().witness.transaction_id
    paths = reader._paths(root, tx)
    directories = (
        root,
        root / "private",
        root / "private" / "transactions",
        root / "workspace",
        root / "workspace" / ".pds",
    )
    files = tuple(
        paths[key]
        for key in (
            "registry",
            "descriptor",
            "journal",
            "registry_stage",
            "descriptor_stage",
        )
        if paths[key].exists() or paths[key].is_symlink()
    )
    return directories + files


def _open_native(stack: ExitStack, path: Path, directory: bool) -> tuple[Any, Any]:
    """Retain original native FD/HANDLE; require matching named identity."""
    if path.is_symlink() or not path.exists():
        raise _CustodyRefused
    if sys.platform == "linux":
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if not nofollow:
            raise _CustodyRefused
        flags = os.O_RDONLY | nofollow
        if directory:
            flags |= getattr(os, "O_DIRECTORY", 0)
        fd = os.open(path, flags)
        stack.callback(os.close, fd)
        details = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        if (
            (directory and not stat.S_ISDIR(details.st_mode))
            or (
                not directory
                and (not stat.S_ISREG(details.st_mode) or details.st_nlink != 1)
            )
            or (details.st_dev, details.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise _CustodyRefused
        return fd, (details.st_dev, details.st_ino)
    if sys.platform == "win32":
        from pds_core import _teacher_private_native_journal_anchor as anchor
        from pds_core import _teacher_private_windows_preflight as wincheck
        from pds_core import _teacher_private_descriptor_snapshot as desc

        kernel, _ = wincheck._bind_api()
        if directory:
            handle, error = anchor._windows_open(kernel, path)
        else:
            handle, error = desc._windows_open(kernel, str(path), directory=False)
        if handle is None or error:
            raise _CustodyRefused
        stack.callback(kernel.CloseHandle, wintypes.HANDLE(handle))
        ident = anchor._windows_id(kernel, handle)
        info = desc._windows_info(kernel, handle)
        if (
            ident is None
            or not any(ident[1])
            or info is None
            or bool(info[1].directory) != directory
            or bool(info[0] & 0x400)
            or (not directory and info[1].number_of_links != 1)
        ):
            raise _CustodyRefused
        return (kernel, handle), ident
    raise _CustodyRefused


def _retained_id(opened: Any, directory: bool) -> Any:
    if sys.platform == "linux":
        details = os.fstat(opened)
        if (directory and not stat.S_ISDIR(details.st_mode)) or (
            not directory and not stat.S_ISREG(details.st_mode)
        ):
            raise _CustodyRefused
        return (details.st_dev, details.st_ino)
    from pds_core import _teacher_private_native_journal_anchor as anchor

    kernel, handle = opened
    return anchor._windows_id(kernel, handle)


def _named_id(path: Path, directory: bool, source: Path) -> Any:
    if sys.platform == "linux":
        entry = os.stat(path, follow_symlinks=False)
        if (directory and not stat.S_ISDIR(entry.st_mode)) or (
            not directory and (not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1)
        ):
            raise _CustodyRefused
        return (entry.st_dev, entry.st_ino)
    reader = _load_triage(source)._load_previous(source)
    if not directory:
        return reader._load_3g71(source)._named_id(path)
    from pds_core import _teacher_private_native_journal_anchor as anchor
    from pds_core import _teacher_private_windows_preflight as wincheck

    kernel, _ = wincheck._bind_api()
    handle, error = anchor._windows_open(kernel, path)
    if handle is None or error:
        raise _CustodyRefused
    try:
        return anchor._windows_id(kernel, handle)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def _guarded_infer(root: Path, source: Path) -> str:
    """Inferred checkpoint only while lock and all native identities are held."""
    try:
        with _operation_lock(root):
            paths = _expected_paths(root, source)
            with ExitStack() as stack:
                retained: list[tuple[Path, bool, Any, Any]] = []
                for index, path in enumerate(paths):
                    directory = index < 5
                    opened, identity = _open_native(stack, path, directory)
                    if _named_id(path, directory, source) != identity:
                        raise _CustodyRefused
                    retained.append((path, directory, opened, identity))
                initial = _load_triage(source)._infer_read_only(root, source)
                second = _load_triage(source)._infer_read_only(root, source)
                if initial != second:
                    raise _CustodyRefused
                if set(_expected_paths(root, source)) != set(paths):
                    raise _CustodyRefused
                for path, directory, opened, identity in retained:
                    if (
                        _retained_id(opened, directory) != identity
                        or _named_id(path, directory, source) != identity
                    ):
                        raise _CustodyRefused
                if initial not in set(STATES.values()):
                    return CONFLICT
                return cast(str, initial)
    except _LockBusy:
        return LOCKED
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        _CustodyRefused,
    ):
        return CONFLICT


def _ask_child(root: Path, source: Path, wheel: Path) -> str:
    argv = [
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        "--source-checkout",
        str(source),
        "--wheel",
        str(wheel),
        "--expected-version",
        "0.6.6",
        "--child-root",
        str(root),
    ]
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            check=False,
            timeout=40,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("native_custody_child_unavailable") from exc
    prefix = "CORE238_GUARDED_RECOVERY:"
    observed = completed.stdout.strip()
    allowed = set(STATES.values()) | {CONFLICT, LOCKED}
    if (
        completed.returncode
        or not observed.startswith(prefix)
        or not observed.endswith(":PASS")
        or observed[len(prefix) : -len(":PASS")] not in allowed
    ):
        raise RuntimeError("native_custody_child_refused")
    return observed[len(prefix) : -len(":PASS")]


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--child-root", type=Path)
    args = parser.parse_args()
    if sys.platform not in {"linux", "win32"}:
        raise RuntimeError("unsupported_platform")
    sys.dont_write_bytecode = True
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    triage = _load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    digest = harness._validate_installed(wheel, source, args.expected_version)
    harness._barrier()
    if args.child_root is not None:
        if args.report is not None or args.scratch_root is not None:
            raise RuntimeError("unexpected_child_scope")
        root = args.child_root.resolve(strict=True)
        if root.is_relative_to(source) or not root.name.startswith("core238_3g74_"):
            raise RuntimeError("invalid_child_scope")
        result = _guarded_infer(root, source)
        print("CORE238_GUARDED_RECOVERY:" + result + ":PASS")
        return 0
    if args.report is None or args.scratch_root is None:
        raise RuntimeError("parent_scope_missing")
    scratch = args.scratch_root.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        not scratch.is_dir()
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
    ):
        raise RuntimeError("unsafe_parent_scope")
    checkpoints: dict[str, str] = {}
    for mode, expected in STATES.items():
        with tempfile.TemporaryDirectory(prefix="core238_3g74_", dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, mode) != expected:
                raise RuntimeError("scratch_prepare_refused")
            reader._request_persistence(root, mode)
            observed = _ask_child(root, source, wheel)
            if observed != expected:
                raise RuntimeError("native_guarded_checkpoint_mismatch")
            checkpoints[mode] = observed
        harness._barrier()
    negative: dict[str, str] = {}
    for fault, mode in (
        ("corrupt_journal", "prepared"),
        ("unexpected_namespace", "registry"),
        ("changed_descriptor", "both"),
    ):
        with tempfile.TemporaryDirectory(prefix="core238_3g74_", dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, mode) != STATES[mode]:
                raise RuntimeError("scratch_fault_prepare_refused")
            triage._damage_synthetic(root, fault, source)
            if _ask_child(root, source, wheel) != CONFLICT:
                raise RuntimeError("native_guarded_conflict_accepted")
            negative[fault] = CONFLICT
        harness._barrier()
    with tempfile.TemporaryDirectory(prefix="core238_3g74_", dir=scratch) as name:
        root = Path(name)
        if harness._run_case(root, "prepared") != STATES["prepared"]:
            raise RuntimeError("scratch_lock_prepare_refused")
        with _operation_lock(root):
            lock_result = _ask_child(root, source, wheel)
        if lock_result != LOCKED:
            raise RuntimeError("cooperative_lock_conflict_not_refused")
        if _ask_child(root, source, wheel) != STATES["prepared"]:
            raise RuntimeError("cooperative_lock_release_not_observed")
    evidence = {
        "schema": "pds.core.issue238.installed-guarded-recovery-custody.v1",
        "result": "passed_synthetic_guarded_recovery_holds_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "guarded_checkpoints": checkpoints,
        "conflict_cases": negative,
        "cooperative_lock_contention": LOCKED,
        "cooperative_lock_release": STATES["prepared"],
        "separate_python_interpreters": 8,
        "retained_native_parents_and_files": True,
        "verified_twice_inside_guard": True,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "automatic_retry_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "transaction_commit_qualified": False,
        "noncooperating_writer_exclusion_qualified": False,
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_GUARDED_RECOVERY: PASS (synthetic guarded holds only)")
    print("QUALIFIED_WHEEL_SHA256: " + digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ) as exc:
        print(
            "ISSUE238_INSTALLED_GUARDED_RECOVERY: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
