"""Installed Core #238 3G73: infer pending-journal checkpoint without phase hints.

Only synthetic transaction roots created here are inspected. A fresh interpreter
classifies the actual registry/descriptor/journal images and native identities;
it never accepts a claimed phase, retries a mutation, or retires a journal.
Classification is advisory, not a production writer, durable commit, or replay.
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

STATES = {
    "prepared": "prepared_hold",
    "registry": "registry_after_descriptor_pending_hold",
    "both": "both_after_journal_pending_hold",
}
CONFLICT = "conflict_preserve"
SCRIPT_3G72 = "verify_issue238_installed_separate_process_restart.py"


def _load_previous(source: Path) -> ModuleType:
    candidate = source / "scripts" / SCRIPT_3G72
    if not candidate.is_file():
        raise RuntimeError("previous_restart_verifier_missing")
    spec = importlib.util.spec_from_file_location("core238_3g72_reader", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError("previous_restart_verifier_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _infer_read_only(root: Path, source: Path) -> str:
    """Require exactly one complete independent native/image/namespace match.

    Never trust a supplied checkpoint, filesystem path spelling or journal
    contents as authorization. Every candidate runs 3G72's strict full-file
    inspection independently; any ambiguity or nonmatch is a HOLD/refusal.
    """
    reader = _load_previous(source)
    matches: list[str] = []
    for mode, expected in STATES.items():
        try:
            observed = reader._read_only_restart(root, mode, source)
        except (
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            OverflowError,
        ):
            continue
        if observed == expected:
            matches.append(expected)
        else:
            return CONFLICT
    return matches[0] if len(matches) == 1 else CONFLICT


def _child(root: Path, source: Path, wheel: Path, expected_version: str) -> str:
    """Read-only recovery observation in an independent installed interpreter."""
    reader = _load_previous(source)
    harness = reader._load_3g71(source)
    harness._validate_installed(wheel, source, expected_version)
    harness._barrier()
    return _infer_read_only(root, source)


def _ask_fresh_interpreter(root: Path, source: Path, wheel: Path) -> str:
    arguments = [
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
        observed = subprocess.run(
            arguments,
            cwd=root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("independent_triage_process_unavailable") from exc
    prefix = "CORE238_RECOVERY_TRIAGE:"
    candidate = observed.stdout.strip()
    allowed = set(STATES.values()) | {CONFLICT}
    if (
        observed.returncode != 0
        or not candidate.startswith(prefix)
        or not candidate.endswith(":PASS")
        or candidate[len(prefix) : -len(":PASS")] not in allowed
    ):
        raise RuntimeError("independent_triage_refused")
    return candidate[len(prefix) : -len(":PASS")]


def _damage_synthetic(root: Path, fault: str, source: Path) -> None:
    """Inject bad evidence ONLY in an internally generated scratch namespace."""
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon

    if fault not in {"corrupt_journal", "unexpected_namespace", "changed_descriptor"}:
        raise ValueError("unsupported_scratch_fault")
    reader = _load_previous(source)
    tx = canon._canonical_fork_intent().witness.transaction_id
    paths = reader._paths(root, tx)
    if fault == "corrupt_journal":
        paths["journal"].write_bytes(b"injected-synthetic-invalid-journal")
    elif fault == "unexpected_namespace":
        (root / "private" / "unrecognized-synthetic").write_bytes(b"foreign")
    else:
        paths["descriptor"].write_bytes(b"injected-synthetic-invalid-descriptor")


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--child-root", type=Path)
    args = parser.parse_args()
    if sys.platform not in {"win32", "linux"}:
        raise RuntimeError("unsupported_native_platform")
    sys.dont_write_bytecode = True
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    reader = _load_previous(source)
    harness = reader._load_3g71(source)
    digest = harness._validate_installed(wheel, source, args.expected_version)
    harness._barrier()
    if args.child_root is not None:
        if args.scratch_root is not None or args.report is not None:
            raise RuntimeError("unexpected_child_arguments")
        root = args.child_root.resolve(strict=True)
        if root.is_relative_to(source) or not root.name.startswith("core238_3g73_"):
            raise RuntimeError("child_outside_disposable_scope")
        state = _child(root, source, wheel, args.expected_version)
        print("CORE238_RECOVERY_TRIAGE:" + state + ":PASS")
        return 0
    if args.scratch_root is None or args.report is None:
        raise RuntimeError("missing_parent_scratch_arguments")
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
    checkpoints: dict[str, str] = {}
    for mode, expected in STATES.items():
        with tempfile.TemporaryDirectory(prefix="core238_3g73_", dir=scratch) as tmp:
            root = Path(tmp)
            if harness._run_case(root, mode) != expected:
                raise RuntimeError("prepared_synthetic_checkpoint_refused")
            reader._request_persistence(root, mode)
            outcome = _ask_fresh_interpreter(root, source, wheel)
            if outcome != expected:
                raise RuntimeError("autonomous_checkpoint_mismatch")
            checkpoints[mode] = outcome
        harness._barrier()
    negative_cases: dict[str, str] = {}
    for fault, mode in (
        ("corrupt_journal", "prepared"),
        ("unexpected_namespace", "registry"),
        ("changed_descriptor", "both"),
    ):
        with tempfile.TemporaryDirectory(prefix="core238_3g73_", dir=scratch) as tmp:
            root = Path(tmp)
            if harness._run_case(root, mode) != STATES[mode]:
                raise RuntimeError("prepared_fault_fixture_refused")
            _damage_synthetic(root, fault, source)
            state = _ask_fresh_interpreter(root, source, wheel)
            if state != CONFLICT:
                raise RuntimeError("tamper_mistaken_for_recovery_checkpoint")
            negative_cases[fault] = state
        harness._barrier()
    evidence = {
        "schema": "pds.core.issue238.installed-recovery-triage.v1",
        "result": "passed_synthetic_read_only_triage_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "inferred_checkpoints": checkpoints,
        "conflict_cases": negative_cases,
        "separate_python_interpreters": 6,
        "requires_caller_claimed_checkpoint": False,
        "journal_preserved_each_checkpoint": True,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "automatic_retry_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "transaction_commit_qualified": False,
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_RECOVERY_TRIAGE: PASS (synthetic; advisory holds only)")
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
            "ISSUE238_INSTALLED_RECOVERY_TRIAGE: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
