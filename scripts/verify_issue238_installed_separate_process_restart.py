"""Installed Core #238 3G72: fresh-process, read-only restart checkpoints.

Use only 3G71's own synthetic, disposable, two-document operation generator.
Request file and parent flushes; a separate Python interpreter reopens each
pending-journal checkpoint. No replay, retry, retirement, production authority
or crash/power-loss durability is proved or performed by this tool.
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
from typing import Any

MODES = {
    "prepared": "prepared_hold",
    "registry": "registry_after_descriptor_pending_hold",
    "both": "both_after_journal_pending_hold",
}
ORIGINAL = "verify_issue238_installed_two_document_restart.py"


def _load_3g71(source: Path) -> ModuleType:
    harness = source / "scripts" / ORIGINAL
    if not harness.is_file():
        raise RuntimeError("prior_installed_verifier_missing")
    spec = importlib.util.spec_from_file_location("core238_g71_harness", harness)
    if spec is None or spec.loader is None:
        raise RuntimeError("prior_installed_verifier_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _paths(root: Path, tx: str) -> dict[str, Path]:
    private = root / "private"
    descriptor = root / "workspace" / ".pds"
    return {
        "registry": private / "registry.json",
        "registry_stage": private / ("." + tx + ".registry-stage"),
        "descriptor": descriptor / "teacher-private-association.json",
        "descriptor_stage": descriptor / ("." + tx + ".descriptor-stage"),
        "journal": private / "transactions" / (tx + ".json"),
    }


def _exact_directory(directory: Path, expected: set[str]) -> None:
    entries = list(directory.iterdir())
    if len(entries) != len(expected) or {p.name for p in entries} != expected:
        raise RuntimeError("restarted_namespace_conflict_preserve")
    if any(p.is_symlink() for p in entries):
        raise RuntimeError("restarted_reparse_or_symlink_refused")


def _read_only_restart(root: Path, mode: str, source: Path) -> str:
    """Open named files independently. Only scratch content, never user data."""
    if mode not in MODES:
        raise ValueError("invalid_restart_checkpoint")
    harness = _load_3g71(source)
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_transaction_intent as intents

    intent = canon._canonical_fork_intent()
    raw = intents.encode_private_transaction_intent(intent)
    if intents.decode_private_transaction_intent(raw) != intent:
        raise RuntimeError("canonical_intent_refused")
    paths = _paths(root, intent.witness.transaction_id)
    expected_files = {
        "registry": intent.registry_before
        if mode == "prepared"
        else intent.registry_after,
        "descriptor": intent.descriptor_after
        if mode == "both"
        else intent.descriptor_before,
        "journal": raw,
    }
    if mode == "prepared":
        expected_files["registry_stage"] = intent.registry_after
    if mode != "both":
        expected_files["descriptor_stage"] = intent.descriptor_after
    if any(type(value) is not bytes or not value for value in expected_files.values()):
        raise RuntimeError("invalid_synthetic_checkpoint_images")
    _exact_directory(root, {"private", "workspace"})
    _exact_directory(root / "workspace", {".pds"})
    _exact_directory(
        paths["registry"].parent,
        {"registry.json", "transactions"}
        | ({paths["registry_stage"].name} if mode == "prepared" else set()),
    )
    _exact_directory(
        paths["descriptor"].parent,
        {"teacher-private-association.json"}
        | ({paths["descriptor_stage"].name} if mode != "both" else set()),
    )
    _exact_directory(paths["journal"].parent, {paths["journal"].name})
    observed_ids: set[Any] = set()
    for label, expected in expected_files.items():
        named = paths[label]
        if named.is_symlink() or not named.is_file() or named.read_bytes() != expected:
            raise RuntimeError("restarted_image_conflict_preserve")
        ident = harness._named_id(named)
        if ident in observed_ids:
            raise RuntimeError("restarted_native_alias_conflict_preserve")
        observed_ids.add(ident)
    if len(observed_ids) != len(expected_files):
        raise RuntimeError("restarted_identity_conflict_preserve")
    # Synthetic checkpoint is a HOLD. Journal is deliberately NEVER retired.
    harness._barrier()
    return MODES[mode]


def _request_persistence(root: Path, mode: str) -> dict[str, str]:
    """Request file flush + directory flush; unsupported directory flush is named.

    A completed flush request is not proof of power-loss survival. On Windows,
    directory FlushFileBuffers commonly refuses; record that truthfully rather
    than quietly substituting a weaker file-only operation.
    """
    from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon

    paths = _paths(root, canon._canonical_fork_intent().witness.transaction_id)
    names = ["registry", "descriptor", "journal"]
    if mode == "prepared":
        names.append("registry_stage")
    if mode != "both":
        names.append("descriptor_stage")
    for name in names:
        durable._file_flush(paths[name])
    directories = {
        "registry_parent": paths["registry"].parent,
        "descriptor_parent": paths["descriptor"].parent,
        "journal_parent": paths["journal"].parent,
    }
    results: dict[str, str] = {}
    for label, directory in directories.items():
        try:
            durable._directory_flush(directory)
            results[label] = "request_completed_unqualified"
        except durable._DirectoryFlushRefused:
            results[label] = "unsupported_not_durable"
    if sys.platform == "linux" and any(
        state != "request_completed_unqualified" for state in results.values()
    ):
        raise RuntimeError("linux_directory_flush_unqualified")
    return results


def _fresh_process(root: Path, mode: str, source: Path, wheel: Path) -> None:
    args = [
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        "--source-checkout",
        str(source),
        "--wheel",
        str(wheel),
        "--expected-version",
        "0.6.6",
        "--child-checkpoint",
        mode,
        "--child-root",
        str(root),
    ]
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        observed = subprocess.run(
            args,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("fresh_process_restart_unavailable") from exc
    if observed.returncode != 0 or observed.stdout.strip() != (
        "CORE238_FRESH_PROCESS_RESTART:" + MODES[mode] + ":PASS"
    ):
        raise RuntimeError("fresh_process_checkpoint_refused")


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--child-checkpoint", choices=tuple(MODES))
    parser.add_argument("--child-root", type=Path)
    args = parser.parse_args()
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    if sys.platform not in {"win32", "linux"}:
        raise RuntimeError("unsupported_native_platform")
    sys.dont_write_bytecode = True
    harness = _load_3g71(source)
    digest = harness._validate_installed(wheel, source, args.expected_version)
    harness._barrier()
    if args.child_checkpoint is not None:
        if (
            args.child_root is None
            or args.scratch_root is not None
            or args.report is not None
        ):
            raise RuntimeError("invalid_child_scope")
        root = args.child_root.resolve(strict=True)
        if root.is_relative_to(source) or not root.name.startswith("core238_3g72_"):
            raise RuntimeError("invalid_scratch_child_directory")
        checkpoint = _read_only_restart(root, args.child_checkpoint, source)
        print("CORE238_FRESH_PROCESS_RESTART:" + checkpoint + ":PASS")
        return 0
    if args.child_root is not None or args.scratch_root is None or args.report is None:
        raise RuntimeError("invalid_parent_scope")
    scratch = args.scratch_root.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        scratch.is_relative_to(source)
        or not scratch.is_dir()
        or report.parent != scratch.parent
        or report.is_relative_to(source)
        or report.exists()
    ):
        raise RuntimeError("unsafe_report_or_scratch_path")
    checkpoints: list[str] = []
    flush_modes: dict[str, dict[str, str]] = {}
    for mode in MODES:
        with tempfile.TemporaryDirectory(prefix="core238_3g72_", dir=scratch) as tmp:
            root = Path(tmp)
            if harness._run_case(root, mode) != MODES[mode]:
                raise RuntimeError("parent_native_checkpoint_refused")
            flush_modes[mode] = _request_persistence(root, mode)
            _fresh_process(root, mode, source, wheel)
            checkpoints.append(MODES[mode])
        harness._barrier()
    report_obj = {
        "schema": "pds.core.issue238.installed-fresh-process-restart.v1",
        "result": "passed_synthetic_fresh_process_holds_only",
        "platform": sys.platform,
        "wheel_sha256": digest,
        "installed_version": "0.6.6",
        "restart_checkpoints": checkpoints,
        "flush_requests": flush_modes,
        "separate_python_interpreters": 3,
        "journal_preserved_each_checkpoint": True,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "transaction_commit_qualified": False,
    }
    report.write_text(
        json.dumps(report_obj, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_FRESH_PROCESS_RESTART: PASS (synthetic holds only)")
    print("QUALIFIED_WHEEL_SHA256: " + digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ) as exc:
        print(
            "ISSUE238_INSTALLED_FRESH_PROCESS_RESTART: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
