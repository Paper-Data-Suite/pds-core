"""Installed Core #238 3G75: abrupt process death with a pending synthetic journal.

The parent creates only fixed canonical FORK_COPY scratch and launches an isolated
writer subprocess. The writer holds the synthetic operation lock and five native
file identities, performs zero, one or two native renames, then calls os._exit
WITHOUT closing the handles. An unrelated fresh interpreter reacquires the
operation lock and native handles to classify the surviving exact checkpoint.

No producer path, private user data, transaction/replay authorization or journal
retirement is accepted. Process death is NOT filesystem or power-loss durability.
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

STATES = {
    "prepared": "prepared_hold",
    "registry": "registry_after_descriptor_pending_hold",
    "both": "both_after_journal_pending_hold",
}
DEATH_CODES = {"prepared": 71, "registry": 72, "both": 73}
CONFLICT = "conflict_preserve"
SCRIPT_3G74 = "verify_issue238_installed_guarded_recovery_custody.py"
_PREFIX = "core238_3g74_3g75_"


def _load_3g74(source: Path) -> ModuleType:
    script = source / "scripts" / SCRIPT_3G74
    if not script.is_file():
        raise RuntimeError("previous_guarded_verifier_missing")
    spec = importlib.util.spec_from_file_location("core238_3g74_death_reader", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("previous_guarded_verifier_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scope(root: Path, source: Path) -> None:
    """Never operate on an unqualified, noncanonical scratch namespace."""
    if (
        root.is_symlink()
        or not root.is_dir()
        or not root.name.startswith(_PREFIX)
        or root.is_relative_to(source)
    ):
        raise RuntimeError("not_disposable_synthetic_root")


def _run_child(root: Path, source: Path, mode: str) -> NoReturn:
    """Perform at most two exact scratch renames and die with handles held.

    The parent, never this child, owns scratch cleanup. There are no retries,
    exception-driven alternate renames, or permitted production paths.
    """
    if mode not in STATES:
        raise ValueError("invalid_forced_death_phase")
    _scope(root, source)
    guarded = _load_3g74(source)
    triage = guarded._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    from pds_core import (
        _teacher_private_recovery_canonical_journaled_restart as canonical,
    )
    from pds_core import _teacher_private_transaction_intent as intents

    checked = canonical._canonical_fork_intent()
    encoded = intents.encode_private_transaction_intent(checked)
    paths = reader._paths(root, checked.witness.transaction_id)
    if (
        reader._read_only_restart(root, "prepared", source) != STATES["prepared"]
        or paths["journal"].read_bytes() != encoded
    ):
        raise RuntimeError("synthetic_preimage_not_prepared")
    with guarded._operation_lock(root):
        with harness._held_file_ids(paths) as held:
            if (
                reader._read_only_restart(root, "prepared", source)
                != STATES["prepared"]
                or paths["journal"].read_bytes() != encoded
                or harness._named_id(paths["journal"]) != held["journal"]
            ):
                raise RuntimeError("native_preimage_changed")
            if mode in {"registry", "both"}:
                harness._replace_once(paths["registry_stage"], paths["registry"])
                if (
                    paths["registry_stage"].exists()
                    or paths["registry"].read_bytes() != checked.registry_after
                    or harness._named_id(paths["registry"]) != held["registry_stage"]
                ):
                    raise RuntimeError("registry_native_postcondition_refused")
            if mode == "both":
                harness._replace_once(paths["descriptor_stage"], paths["descriptor"])
                if (
                    paths["descriptor_stage"].exists()
                    or paths["descriptor"].read_bytes() != checked.descriptor_after
                    or harness._named_id(paths["descriptor"])
                    != held["descriptor_stage"]
                ):
                    raise RuntimeError("descriptor_native_postcondition_refused")
            if (
                paths["journal"].read_bytes() != encoded
                or harness._named_id(paths["journal"]) != held["journal"]
            ):
                raise RuntimeError("pending_journal_changed")
            # Intentional hard process termination INSIDE retained native scope.
            # No Python finally block runs; no journal retirement is attempted.
            os._exit(DEATH_CODES[mode])
    raise RuntimeError("hard_exit_unexpectedly_returned")


def _force_death(root: Path, source: Path, wheel: Path, mode: str) -> None:
    """Require exact hard-exit code without interpreting stderr as authorization."""
    if mode not in STATES:
        raise ValueError("invalid_forced_death_phase")
    _scope(root, source)
    try:
        child = subprocess.run(
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
                "--child-phase",
                mode,
            ],
            cwd=root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            timeout=35,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("synthetic_death_process_unavailable") from exc
    if (
        child.returncode != DEATH_CODES[mode]
        or child.stdout.strip()
        or child.stderr.strip()
    ):
        raise RuntimeError("synthetic_process_death_not_qualified")


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--child-root", type=Path)
    parser.add_argument("--child-phase", choices=tuple(STATES))
    args = parser.parse_args()
    if sys.platform not in {"linux", "win32"}:
        raise RuntimeError("native_platform_unavailable")
    sys.dont_write_bytecode = True
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    guarded = _load_3g74(source)
    triage = guarded._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    digest = harness._validate_installed(wheel, source, args.expected_version)
    harness._barrier()
    if args.child_root is not None:
        if (
            args.scratch_root is not None
            or args.report is not None
            or args.child_phase is None
        ):
            raise RuntimeError("invalid_child_arguments")
        root = args.child_root.resolve(strict=True)
        _run_child(root, source, args.child_phase)
        raise RuntimeError("hard_exit_returned")
    if args.child_phase is not None or args.scratch_root is None or args.report is None:
        raise RuntimeError("missing_parent_arguments")
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
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "prepared") != STATES["prepared"]:
                raise RuntimeError("failed_to_prepare_canonical_scratch")
            _force_death(root, source, wheel, mode)
            observed = guarded._ask_child(root, source, wheel)
            if observed != expected:
                raise RuntimeError("post_process_death_checkpoint_refused")
            checkpoints[mode] = observed
        harness._barrier()
    conflicts: dict[str, str] = {}
    for fault, mode in (
        ("corrupt_journal", "registry"),
        ("unexpected_namespace", "both"),
        ("changed_descriptor", "prepared"),
    ):
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "prepared") != STATES["prepared"]:
                raise RuntimeError("failed_to_prepare_adversarial_scratch")
            _force_death(root, source, wheel, mode)
            triage._damage_synthetic(root, fault, source)
            if guarded._ask_child(root, source, wheel) != CONFLICT:
                raise RuntimeError("corrupted_post_death_checkpoint_accepted")
            conflicts[fault] = CONFLICT
        harness._barrier()
    evidence = {
        "schema": "pds.core.issue238.installed-process-death-restart.v1",
        "result": "passed_synthetic_process_death_recovery_holds_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "post_death_checkpoints": checkpoints,
        "post_death_conflicts": conflicts,
        "forced_exit_codes": DEATH_CODES,
        "hard_terminated_writer_processes": 6,
        "independent_guarded_restart_processes": 6,
        "journal_preserved_each_checkpoint": True,
        "native_stage_identities_held_until_process_exit": True,
        "operation_lock_reacquired_after_process_exit": True,
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
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_PROCESS_DEATH_RESTART: PASS (synthetic holds only)")
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
            "ISSUE238_INSTALLED_PROCESS_DEATH_RESTART: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
