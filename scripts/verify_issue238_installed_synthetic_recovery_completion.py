"""Core #238 3G76: complete canonical scratch recovery after hard process death.

A genuinely separate installed-wheel interpreter reacquires a cooperative lock,
retains native directory/file handles, infers the exact pending-journal checkpoint
WITHOUT a caller phase, and performs at most the missing one-shot native renames.
It rechecks exact identities/images under the same guard, requests file and
parent persistence, then a third interpreter independently verifies the final
both-after / journal-pending checkpoint. No production paths, teacher identities,
client transaction input, Notes, journal retirement, commit or authority exist.

This is synthetic process-death recovery ONLY: neither a power-loss durability
proof nor safe production replay; a post-attempt error is never retried.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from typing import Any, cast

SCRIPT_3G75 = "verify_issue238_installed_process_death_restart.py"
_PREFIX = "core238_3g74_3g75_3g76_"
_CONFLICT = "conflict_preserve"
_COMPLETE = "both_after_journal_pending_hold"
_COUNTS = {"prepared": 2, "registry": 1, "both": 0}
_STATES = {
    "prepared": "prepared_hold",
    "registry": "registry_after_descriptor_pending_hold",
    "both": _COMPLETE,
}


def _load_3g75(source: Path) -> ModuleType:
    path = source / "scripts" / SCRIPT_3G75
    if not path.is_file():
        raise RuntimeError("previous_synthetic_death_verifier_missing")
    spec = importlib.util.spec_from_file_location("core238_3g75_recovery_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("previous_synthetic_death_verifier_unavailable")
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
        raise RuntimeError("outside_disposable_synthetic_scope")


def _native_step(harness: ModuleType, stage: Path, target: Path) -> None:
    """Exactly one native scratch replace; never retry a failed/unknown syscall."""
    harness._replace_once(stage, target)


def _attempt_directory_persistence(directory: Path) -> bool:
    """Request native directory flush; even success is NOT crash durability."""
    from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable

    try:
        durable._directory_flush(directory)
        return True
    except durable._DirectoryFlushRefused:
        return False


def _recover_one(root: Path, source: Path) -> tuple[str, int, bool]:
    """Infer then complete only canonical scratch; retain all handles until exit.

    A conflict makes ZERO writes. Once any rename is attempted, a refusal is
    propagated rather than retried, so all surviving stages and journal remain
    available for an independent later review (never an automatic retry).
    """
    _scope(root, source)
    death = _load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_transaction_intent as intents
    from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable

    expected = canon._canonical_fork_intent()
    raw_journal = intents.encode_private_transaction_intent(expected)
    paths = reader._paths(root, expected.witness.transaction_id)
    with guard._operation_lock(root):
        pre = cast(str, triage._infer_read_only(root, source))
        if pre not in set(_STATES.values()):
            return _CONFLICT, 0, False
        # The synthetic *journal must remain present*: it is not a replay permit.
        if paths["journal"].read_bytes() != raw_journal:
            return _CONFLICT, 0, False
        originals = guard._expected_paths(root, source)
        with ExitStack() as handles:
            retained: dict[Path, tuple[bool, Any, Any]] = {}
            for index, path in enumerate(originals):
                directory = index < 5
                handle, identity = guard._open_native(handles, path, directory)
                if guard._named_id(path, directory, source) != identity:
                    raise RuntimeError("native_recovery_preimage_identity_conflict")
                if identity in {entry[2] for entry in retained.values()}:
                    raise RuntimeError("native_recovery_alias_refused")
                retained[path] = (directory, handle, identity)
            # Re-read while all original parent and file handles are retained.
            if cast(str, triage._infer_read_only(root, source)) != pre:
                return _CONFLICT, 0, False
            if set(guard._expected_paths(root, source)) != set(originals):
                return _CONFLICT, 0, False
            for path, (directory, handle, identity) in retained.items():
                if (
                    guard._retained_id(handle, directory) != identity
                    or guard._named_id(path, directory, source) != identity
                ):
                    raise RuntimeError("native_recovery_preimage_changed")
            steps = 0
            requested = True
            transitions: tuple[tuple[str, str, str], ...] = (
                ("registry_stage", "registry", _STATES["registry"]),
                ("descriptor_stage", "descriptor", _COMPLETE),
            )
            # No caller specifies an operation or phase: derive needed steps.
            if pre == _STATES["registry"]:
                transitions = transitions[1:]
            elif pre == _COMPLETE:
                transitions = ()
            for stage_key, target_key, new_state in transitions:
                stage = paths[stage_key]
                target = paths[target_key]
                if stage not in retained or target not in retained:
                    raise RuntimeError("native_recovery_stage_absent")
                stage_id = retained[stage][2]
                old_id = retained[target][2]
                if (
                    guard._named_id(stage, False, source) != stage_id
                    or guard._named_id(target, False, source) != old_id
                    or cast(str, triage._infer_read_only(root, source))
                    not in set(_STATES.values())
                ):
                    raise RuntimeError("native_recovery_stage_changed")
                # Single attempt. A crash or I/O refusal after this point MUST
                # preserve the pending journal; never blind-retry this stage.
                _native_step(harness, stage, target)
                steps += 1
                if (
                    stage.exists()
                    or guard._named_id(target, False, source) != stage_id
                    or guard._retained_id(retained[stage][1], False) != stage_id
                    or guard._retained_id(retained[target][1], False) != old_id
                    or cast(str, triage._infer_read_only(root, source)) != new_state
                    or paths["journal"].read_bytes() != raw_journal
                ):
                    raise RuntimeError("native_recovery_postcondition_conflict")
                # File flush is required; Windows directory flush may refuse.
                # A requested/successful directory flush is NOT power-loss proof.
                durable._file_flush(target)
                requested = _attempt_directory_persistence(target.parent) and requested
            if cast(str, triage._infer_read_only(root, source)) != _COMPLETE:
                raise RuntimeError("native_recovery_final_checkpoint_conflict")
            if paths["journal"].read_bytes() != raw_journal:
                raise RuntimeError("native_recovery_pending_journal_changed")
            for path, (directory, handle, identity) in retained.items():
                if guard._retained_id(handle, directory) != identity:
                    raise RuntimeError("native_recovery_retained_identity_changed")
                if path in (paths["registry_stage"], paths["descriptor_stage"]):
                    if path.exists() or path.is_symlink():
                        raise RuntimeError("native_recovery_unexpected_retained_stage")
                    continue
                if path == paths["registry"] and pre != _COMPLETE:
                    wanted = (
                        retained[paths["registry_stage"]][2]
                        if pre == _STATES["prepared"]
                        else identity
                    )
                    if guard._named_id(path, False, source) != wanted:
                        raise RuntimeError("native_recovery_final_registry_identity")
                elif path == paths["descriptor"] and pre != _COMPLETE:
                    if (
                        guard._named_id(path, False, source)
                        != retained[paths["descriptor_stage"]][2]
                    ):
                        raise RuntimeError("native_recovery_final_descriptor_identity")
                elif guard._named_id(path, directory, source) != identity:
                    raise RuntimeError(
                        "native_recovery_final_parent_or_journal_identity"
                    )
            return pre, steps, requested


def _ask_recovery(root: Path, source: Path, wheel: Path) -> tuple[str, int, bool]:
    _scope(root, source)
    command = [
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        "--source-checkout",
        str(source),
        "--wheel",
        str(wheel),
        "--expected-version",
        "0.6.6",
        "--child-recover",
        str(root),
    ]
    try:
        process = subprocess.run(
            command,
            cwd=root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("recovery_interpreter_unavailable") from exc
    prefix = "CORE238_SCRATCH_RECOVERY:"
    text = process.stdout.strip()
    allowed = set(_STATES.values()) | {_CONFLICT}
    fields = text.split(":")
    if (
        process.returncode != 0
        or process.stderr.strip()
        or len(fields) != 5
        or fields[0] != prefix[:-1]
        or fields[1] not in allowed
        or fields[2] not in {"0", "1", "2"}
        or fields[3] not in {"yes", "no"}
        or fields[4] != "PASS"
    ):
        raise RuntimeError("independent_scratch_recovery_refused")
    return fields[1], int(fields[2]), fields[3] == "yes"


def _snapshot(root: Path) -> str:
    """Private test-only digest; no metadata, handles or paths leave the verifier."""
    data = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("synthetic_snapshot_symlink_refused")
        data.update(str(path.relative_to(root)).encode("utf-8"))
        if path.is_file():
            data.update(path.read_bytes())
    return data.hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--child-recover", type=Path)
    args = parser.parse_args()
    if sys.platform not in {"linux", "win32"}:
        raise RuntimeError("unsupported_platform")
    sys.dont_write_bytecode = True
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    death = _load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    digest = harness._validate_installed(wheel, source, args.expected_version)
    harness._barrier()
    if args.child_recover is not None:
        if args.report is not None or args.scratch_root is not None:
            raise RuntimeError("unexpected_child_scope")
        root = args.child_recover.resolve(strict=True)
        before, count, directory_request = _recover_one(root, source)
        print(
            "CORE238_SCRATCH_RECOVERY:"
            + before
            + ":"
            + str(count)
            + ":"
            + ("yes" if directory_request else "no")
            + ":PASS"
        )
        return 0
    if args.report is None or args.scratch_root is None:
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
        raise RuntimeError("unsafe_synthetic_parent_scope")
    completions: dict[str, int] = {}
    directory_requests: dict[str, bool | None] = {}
    for mode, count in _COUNTS.items():
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "prepared") != _STATES["prepared"]:
                raise RuntimeError("synthetic_prepare_refused")
            death._force_death(root, source, wheel, mode)
            if guard._ask_child(root, source, wheel) != _STATES[mode]:
                raise RuntimeError("independent_postdeath_precheck_refused")
            before, performed, directory_requested = _ask_recovery(root, source, wheel)
            if before != _STATES[mode] or performed != count:
                raise RuntimeError("synthetic_recovery_count_refused")
            if guard._ask_child(root, source, wheel) != _COMPLETE:
                raise RuntimeError("independent_recovery_restart_refused")
            completions[mode] = performed
            directory_requests[mode] = directory_requested if count else None
        harness._barrier()
    conflicts: dict[str, str] = {}
    for fault, mode in (
        ("corrupt_journal", "registry"),
        ("unexpected_namespace", "both"),
        ("changed_descriptor", "prepared"),
        ("changed_stage", "registry"),
    ):
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "prepared") != _STATES["prepared"]:
                raise RuntimeError("synthetic_negative_prepare_refused")
            death._force_death(root, source, wheel, mode)
            if fault == "changed_stage":
                from pds_core import (
                    _teacher_private_recovery_canonical_journaled_restart as canonical,
                )

                paths = reader._paths(
                    root, canonical._canonical_fork_intent().witness.transaction_id
                )
                paths["descriptor_stage"].write_bytes(b"synthetic-stage-conflict")
            else:
                triage._damage_synthetic(root, fault, source)
            prior = _snapshot(root)
            before, count, _ = _ask_recovery(root, source, wheel)
            if before != _CONFLICT or count != 0 or _snapshot(root) != prior:
                raise RuntimeError("synthetic_conflict_mutated_or_was_admitted")
            conflicts[fault] = before
        harness._barrier()
    evidence = {
        "schema": "pds.core.issue238.installed-synthetic-recovery-completion.v1",
        "result": "passed_synthetic_bounded_recovery_completion_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "post_death_resume_steps": completions,
        "directory_flush_request_accepted": directory_requests,
        "conflict_cases": conflicts,
        "separate_recovery_interpreters": 7,
        "independent_native_restart_verifications": 6,
        "journal_preserved_after_recovery": True,
        "caller_phase_hint_accepted": False,
        "recovery_is_synthetic_only": True,
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
    print("ISSUE238_INSTALLED_SYNTHETIC_RECOVERY: PASS (bounded scratch only)")
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
            "ISSUE238_INSTALLED_SYNTHETIC_RECOVERY: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
