"""Core #238 3G78: repeated scratch recovery must be an exact native no-op.

A genuine installed-wheel 3G76 recovery is invoked explicitly after the 3G75
writer has died. Two additional independent installed interpreters must then
perform ZERO replacements, preserve the canonical pending journal, and retain
identical file IDs and all metadata bytes. Cooperative lock contention and
corrupt post-completion evidence refuse recovery without mutation.

All paths/metadata are internally generated canonical synthetic scratch. A
successful idempotence observation NEVER authorizes production replay, commit,
retirement, owner/ACL qualification, Notes, or crash-power-loss durability.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import cast

_PREVIOUS = "verify_issue238_installed_synthetic_recovery_completion.py"
_PREFIX = "core238_3g74_3g75_3g76_3g77_3g78_"
_COMPLETE = "both_after_journal_pending_hold"
_CONFLICT = "conflict_preserve"
_COUNTS = {"prepared": 2, "registry": 1, "both": 0}
_STATES = {
    "prepared": "prepared_hold",
    "registry": "registry_after_descriptor_pending_hold",
    "both": _COMPLETE,
}
_FAULTS = (
    "corrupt_journal",
    "unexpected_namespace",
    "changed_descriptor",
    "changed_registry",
)


def _load_previous(source: Path) -> ModuleType:
    script = source / "scripts" / _PREVIOUS
    if not script.is_file():
        raise RuntimeError("previous_synthetic_recovery_missing")
    spec = importlib.util.spec_from_file_location("core238_3g76_idempotence", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("previous_synthetic_recovery_unavailable")
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
        raise RuntimeError("unqualified_disposable_scratch_root")


def _canonical_snapshot(
    root: Path, source: Path
) -> tuple[tuple[object, ...], str, str]:
    """Capture native IDs of ALL surviving files, canonical journal, and bytes.

    Snapshot is test-only, never returned in CI evidence. No caller names,
    external paths or arbitrary transaction IDs enter this function.
    """
    _scope(root, source)
    recovery = _load_previous(source)
    death = recovery._load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_transaction_intent as intents

    checked = canon._canonical_fork_intent()
    paths = reader._paths(root, checked.witness.transaction_id)
    journal_raw = intents.encode_private_transaction_intent(checked)
    if paths["journal"].read_bytes() != journal_raw:
        raise RuntimeError("noncanonical_pending_journal")
    identities: list[object] = []
    for key in ("registry", "descriptor", "journal"):
        identities.append(harness._named_id(paths[key]))
    return (
        tuple(identities),
        cast(str, recovery._snapshot(root)),
        hashlib.sha256(journal_raw).hexdigest(),
    )


def _assert_unchanged(
    root: Path, source: Path, expected: tuple[tuple[object, ...], str, str]
) -> None:
    if _canonical_snapshot(root, source) != expected:
        raise RuntimeError("repeat_recovery_changed_native_id_or_bytes")


def _damage_completed(root: Path, source: Path, fault: str) -> None:
    """Deliberate fault injection into fixed synthetic, completed scratch."""
    if fault not in _FAULTS:
        raise ValueError("unsupported_completed_scratch_fault")
    _scope(root, source)
    recovery = _load_previous(source)
    death = recovery._load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    reader = triage._load_previous(source)
    if fault != "changed_registry":
        triage._damage_synthetic(root, fault, source)
        return
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon

    paths = reader._paths(root, canon._canonical_fork_intent().witness.transaction_id)
    paths["registry"].write_bytes(b"synthetic-invalid-registry-image")


def _run_gate(
    source: Path, wheel: Path, scratch: Path
) -> tuple[dict[str, int], dict[str, list[int]], dict[str, str]]:
    recovery = _load_previous(source)
    death = recovery._load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    counts: dict[str, int] = {}
    repeats: dict[str, list[int]] = {}
    for mode, expected_steps in _COUNTS.items():
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "prepared") != _STATES["prepared"]:
                raise RuntimeError("idempotence_prepared_fixture_refused")
            death._force_death(root, source, wheel, mode)
            if guard._ask_child(root, source, wheel) != _STATES[mode]:
                raise RuntimeError("idempotence_independent_precheck_refused")
            prior, steps, _ = recovery._ask_recovery(root, source, wheel)
            if prior != _STATES[mode] or steps != expected_steps:
                raise RuntimeError("first_recovery_exact_steps_refused")
            if guard._ask_child(root, source, wheel) != _COMPLETE:
                raise RuntimeError("first_recovery_postcondition_refused")
            original = _canonical_snapshot(root, source)
            observed: list[int] = []
            for _index in range(2):
                previous, performed, _ = recovery._ask_recovery(root, source, wheel)
                if previous != _COMPLETE or performed != 0:
                    raise RuntimeError("repeat_recovery_attempted_unneeded_replace")
                if guard._ask_child(root, source, wheel) != _COMPLETE:
                    raise RuntimeError("repeat_recovery_checkpoint_changed")
                _assert_unchanged(root, source, original)
                observed.append(performed)
            counts[mode] = steps
            repeats[mode] = observed
        harness._barrier()
    # Contention must refuse before writes; after release the same scratch
    # can be completed explicitly, then another process must perform ZERO steps.
    with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
        root = Path(name)
        if harness._run_case(root, "prepared") != _STATES["prepared"]:
            raise RuntimeError("lock_scratch_prepare_refused")
        before = cast(str, recovery._snapshot(root))
        with guard._operation_lock(root):
            try:
                recovery._ask_recovery(root, source, wheel)
            except RuntimeError:
                pass  # The child MUST refuse because the lock is held.
            else:
                raise RuntimeError("concurrent_recovery_not_refused")
            if recovery._snapshot(root) != before:
                raise RuntimeError("contended_recovery_modified_scratch")
        prior, steps, _ = recovery._ask_recovery(root, source, wheel)
        if prior != _STATES["prepared"] or steps != 2:
            raise RuntimeError("released_lock_recovery_refused")
        original = _canonical_snapshot(root, source)
        prior, steps, _ = recovery._ask_recovery(root, source, wheel)
        if prior != _COMPLETE or steps != 0:
            raise RuntimeError("released_lock_repeat_wrote_again")
        _assert_unchanged(root, source, original)
    harness._barrier()
    conflicts: dict[str, str] = {}
    for fault in _FAULTS:
        with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=scratch) as name:
            root = Path(name)
            if harness._run_case(root, "both") != _COMPLETE:
                raise RuntimeError("completed_conflict_fixture_refused")
            _damage_completed(root, source, fault)
            if guard._ask_child(root, source, wheel) != _CONFLICT:
                raise RuntimeError("completed_corruption_not_detected")
            previous = cast(str, recovery._snapshot(root))
            for _index in range(2):
                state, count, _ = recovery._ask_recovery(root, source, wheel)
                if (
                    state != _CONFLICT
                    or count != 0
                    or recovery._snapshot(root) != previous
                ):
                    raise RuntimeError("repeated_corrupt_recovery_mutated_scratch")
            conflicts[fault] = _CONFLICT
        harness._barrier()
    return counts, repeats, conflicts


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform not in {"linux", "win32"}:
        raise RuntimeError("unsupported_native_platform")
    sys.dont_write_bytecode = True
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
    ):
        raise RuntimeError("unsafe_installed_scratch_scope")
    recovery = _load_previous(source)
    death = recovery._load_3g75(source)
    guard = death._load_3g74(source)
    triage = guard._load_triage(source)
    reader = triage._load_previous(source)
    harness = reader._load_3g71(source)
    digest = harness._validate_installed(wheel, source, args.expected_version)
    harness._barrier()
    counts, repeats, conflicts = _run_gate(source, wheel, scratch)
    evidence = {
        "schema": "pds.core.issue238.installed-recovery-idempotence.v1",
        "result": "passed_synthetic_recovery_idempotence_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "first_explicit_recovery_steps": counts,
        "post_completion_repeated_recovery_steps": repeats,
        "completed_checkpoint_corruption_cases": conflicts,
        "cooperative_lock_contention_prevented_mutation": True,
        "released_lock_recovery_steps": 2,
        "post_release_repeat_steps": 0,
        "post_completion_native_identities_unchanged": True,
        "post_completion_metadata_bytes_unchanged": True,
        "canonical_journal_preserved": True,
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
    print("ISSUE238_INSTALLED_RECOVERY_IDEMPOTENCE: PASS (synthetic no-op only)")
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
            "ISSUE238_INSTALLED_RECOVERY_IDEMPOTENCE: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
