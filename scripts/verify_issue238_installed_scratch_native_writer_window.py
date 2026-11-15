"""Installed Core #238 3G87: real scratch replacement inside native parent guard.

Everything written is created by the installed module in one disposable OS temp
folder. No live Notes/private registry/workspace is used. No write permit exists.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path
from typing import cast


def _provenance(wheel: Path, source: Path, version: str) -> str:
    import pds_core
    from pds_core import _teacher_private_scratch_native_writer_window as probe
    from pds_core import _teacher_private_file_lock as lock

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or not wheel.is_file()
        or wheel.suffix != ".whl"
    ):
        raise RuntimeError("candidate_wheel_refused")
    for module in (pds_core, probe, lock):
        if module.__file__ is None:
            raise RuntimeError("installed_module_origin_missing")
        path = Path(module.__file__).resolve(strict=True)
        if not path.is_relative_to(purelib) or path.is_relative_to(source):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_native_writer_window as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    cases = (
        (
            probe.PrivateScratchWindowScenario.NORMAL,
            probe.PrivateScratchWindowState.SCRATCH_REPLACED_NONAUTHORIZING,
        ),
        (
            probe.PrivateScratchWindowScenario.PREIMAGE_DRIFT,
            probe.PrivateScratchWindowState.PREIMAGE_DRIFT_REFUSED,
        ),
        (
            probe.PrivateScratchWindowScenario.STAGE_DRIFT,
            probe.PrivateScratchWindowState.STAGE_DRIFT_REFUSED,
        ),
    )
    before = tuple(scratch.iterdir())
    for mode, wanted in cases:
        review = probe.probe_disposable_native_writer_window(mode)
        if (
            type(review) is not probe.PrivateScratchWindowReview
            or review.state is not wanted
            or not review.synthetic_parent_retained_during_window
            or not review.cooperative_lock_held_during_window
            or not review.preimage_rechecked_during_window
            or not review.pending_synthetic_journal_preserved
            or review.synthetic_replace_attempted
            != (mode is probe.PrivateScratchWindowScenario.NORMAL)
            or review.synthetic_postimage_verified
            != (mode is probe.PrivateScratchWindowScenario.NORMAL)
            or any(
                (
                    review.production_mutation_admitted,
                    review.operation_owned_production_guard_qualified,
                    review.noncooperating_writer_exclusion_qualified,
                    review.native_replace_postimage_production_qualified,
                    review.automatic_replay_allowed,
                    review.journal_retirement_allowed,
                    review.notes_records_available,
                    review.directory_crash_durability_qualified,
                    review.multi_document_atomic_commit_qualified,
                )
            )
        ):
            raise RuntimeError("synthetic_native_window_unqualified")
    invalid = probe.probe_disposable_native_writer_window(
        cast(probe.PrivateScratchWindowScenario, "normal")
    )
    if (
        invalid.state is not probe.PrivateScratchWindowState.INVALID_REQUEST_REFUSED
        or invalid.synthetic_replace_attempted
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
        or len(readiness._REQUIRED) != 9
    ):
        raise RuntimeError("failed_closed_native_window_unqualified")
    return {
        "native_scratch_replace_verified": True,
        "preimage_drift_refused_without_replace": True,
        "stage_drift_refused_without_replace": True,
        "native_parent_retained_in_all_scenarios": True,
        "pending_synthetic_journal_preserved": True,
        "scratch_root_unchanged": True,
        "invalid_scenario_refusal": invalid.state.value,
        "unqualified_requirements": list(readiness._REQUIRED),
        "production_mutation_admitted": False,
        "operation_owned_production_guard_qualified": False,
        "noncooperating_writer_exclusion_qualified": False,
        "native_replace_postimage_production_qualified": False,
        "automatic_replay_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "multi_document_atomic_commit_qualified": False,
    }


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
        or scratch.is_symlink()
        or scratch.name != "scratch"
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.exists()
        or report.parent != scratch.parent
    ):
        raise RuntimeError("unsafe_evidence_scope")
    digest = _provenance(wheel, source, args.expected_version)
    detail = _exercise(scratch)
    evidence = {
        "schema": "pds.core.issue238.installed-native-scratch-writer-window.v1",
        "result": "passed_native_scratch_writer_window_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **detail,
    }
    report.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_SCRATCH_WRITER_WINDOW: PASS (scratch only; no authority)")
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
            "ISSUE238_INSTALLED_SCRATCH_WRITER_WINDOW: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
