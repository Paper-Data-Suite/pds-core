"""Core #238 3G77: hard termination *during* bounded synthetic recovery.

A fresh installed-wheel interpreter reacquires native operation custody after
an earlier synthetic writer death, then itself dies before or after one of its
single-attempt renames. The parent independently reopens the surviving pending
journal checkpoint. Only after that explicit synthetic review does another
isolated test process complete the still-pending recovery steps.

No production paths, user data, caller-supplied transaction, automatic replay,
blind retry, journal retirement, Notes or crash-durability claim is admitted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import NoReturn

_PREVIOUS = "verify_issue238_installed_synthetic_recovery_completion.py"
_PREFIX = "core238_3g74_3g75_3g76_3g77_"
_CASES = {
    "before_registry": (81, "prepared_hold", 2),
    "after_registry": (82, "registry_after_descriptor_pending_hold", 1),
    "after_descriptor": (83, "both_after_journal_pending_hold", 0),
}
_CONFLICT = "conflict_preserve"
_COMPLETE = "both_after_journal_pending_hold"


def _load_previous(source: Path) -> ModuleType:
    path = source / "scripts" / _PREVIOUS
    if not path.is_file():
        raise RuntimeError("previous_synthetic_recovery_verifier_missing")
    spec = importlib.util.spec_from_file_location("core238_3g76_reinterruption", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("previous_synthetic_recovery_verifier_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scope(root: Path, source: Path) -> None:
    if (
        root.is_symlink()
        or not root.is_dir()
        or not root.name.startswith(_PREFIX)
        or root.is_relative_to(source)
    ):
        raise RuntimeError("non_disposable_recovery_scope")


def _die_in_recovery(root: Path, source: Path, fault: str) -> NoReturn:
    """Single fixed crash point while 3G76 holds native recovery custody.

    The scratch-only callback is injected inside this test subprocess, never
    into a production writer. os._exit bypasses 3G76's lock/handle cleanup.
    """
    if fault not in _CASES:
        raise ValueError("invalid_synthetic_recovery_fault")
    _scope(root, source)
    recovery = _load_previous(source)
    original = recovery._native_step
    calls = 0

    def _interrupted_step(harness: ModuleType, stage: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        expected = "registry.json" if calls == 1 else "teacher-private-association.json"
        if (
            calls not in {1, 2}
            or target.name != expected
            or stage.parent != target.parent
            or not stage.name.endswith("-stage")
        ):
            raise RuntimeError("unexpected_synthetic_recovery_operation")
        if fault == "before_registry" and calls == 1:
            os._exit(_CASES[fault][0])
        original(harness, stage, target)
        if (fault == "after_registry" and calls == 1) or (
            fault == "after_descriptor" and calls == 2
        ):
            os._exit(_CASES[fault][0])

    setattr(recovery, "_native_step", _interrupted_step)
    try:
        recovery._recover_one(root, source)
    finally:
        setattr(recovery, "_native_step", original)
    raise RuntimeError("required_recovery_crash_not_observed")


def _force_crash(root: Path, source: Path, wheel: Path, fault: str) -> None:
    if fault not in _CASES:
        raise ValueError("invalid_synthetic_recovery_fault")
    _scope(root, source)
    try:
        completed = subprocess.run(
            [
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
                "--child-fault",
                fault,
            ],
            cwd=root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("recovery_death_process_unavailable") from exc
    if (
        completed.returncode != _CASES[fault][0]
        or completed.stdout.strip()
        or completed.stderr.strip()
    ):
        raise RuntimeError("recovery_death_not_qualified")


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--child-root", type=Path)
    parser.add_argument("--child-fault", choices=tuple(_CASES))
    args = parser.parse_args()
    if sys.platform not in {"linux", "win32"}:
        raise RuntimeError("unsupported_native_platform")
    sys.dont_write_bytecode = True
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    recovery = _load_previous(source)
    death = recovery._load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    digest = harness._validate_installed(wheel, source, args.expected_version)
    harness._barrier()
    if args.child_root is not None:
        if (
            args.child_fault is None
            or args.report is not None
            or args.scratch_root is not None
        ):
            raise RuntimeError("invalid_child_scope")
        root = args.child_root.resolve(strict=True)
        _die_in_recovery(root, source, args.child_fault)
    if args.child_fault is not None or args.scratch_root is None or args.report is None:
        raise RuntimeError("invalid_parent_scope")
    scratch = args.scratch_root.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        not scratch.is_dir()
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
    ):
        raise RuntimeError("unsafe_synthetic_scope")
    surviving: dict[str, str] = {}
    remaining: dict[str, int] = {}
    for fault, (_, checkpoint, count) in _CASES.items():
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "prepared") != "prepared_hold":
                raise RuntimeError("initial_scratch_not_prepared")
            # First process dies during initial transaction; independent review.
            death._force_death(root, source, wheel, "prepared")
            if guard._ask_child(root, source, wheel) != "prepared_hold":
                raise RuntimeError("initial_process_death_not_recovered")
            # Second process dies inside recovery with native custody retained.
            _force_crash(root, source, wheel, fault)
            observed = guard._ask_child(root, source, wheel)
            if observed != checkpoint:
                raise RuntimeError("interrupted_recovery_checkpoint_conflict")
            # Explicitly scoped synthetic continuation AFTER independent review.
            prior, performed, _ = recovery._ask_recovery(root, source, wheel)
            if prior != observed or performed != count:
                raise RuntimeError("recovery_reinterruption_step_count_refused")
            if guard._ask_child(root, source, wheel) != _COMPLETE:
                raise RuntimeError("reinterrupted_recovery_not_converged")
            surviving[fault] = observed
            remaining[fault] = performed
        harness._barrier()
    conflicts: dict[str, str] = {}
    for fault in ("corrupt_journal", "unexpected_namespace", "changed_descriptor"):
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "prepared") != "prepared_hold":
                raise RuntimeError("negative_scratch_not_prepared")
            death._force_death(root, source, wheel, "prepared")
            _force_crash(root, source, wheel, "after_registry")
            triage._damage_synthetic(root, fault, source)
            if guard._ask_child(root, source, wheel) != _CONFLICT:
                raise RuntimeError("post_reinterruption_conflict_not_observed")
            snapshot = recovery._snapshot(root)
            prior, performed, _ = recovery._ask_recovery(root, source, wheel)
            if (
                prior != _CONFLICT
                or performed != 0
                or recovery._snapshot(root) != snapshot
            ):
                raise RuntimeError("ambiguous_second_recovery_mutated")
            conflicts[fault] = prior
        harness._barrier()
    evidence = {
        "schema": "pds.core.issue238.installed-recovery-reinterruption.v1",
        "result": "passed_synthetic_recovery_reinterruption_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "hard_recovery_exit_codes": {fault: row[0] for fault, row in _CASES.items()},
        "post_crash_recovery_checkpoints": surviving,
        "remaining_explicit_scratch_steps": remaining,
        "post_crash_conflicts": conflicts,
        "interrupted_recovery_processes": 6,
        "independently_reviewed_before_resume": True,
        "journal_preserved_after_second_recovery": True,
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
    print("ISSUE238_INSTALLED_RECOVERY_REINTERRUPTION: PASS (synthetic only)")
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
            "ISSUE238_INSTALLED_RECOVERY_REINTERRUPTION: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
