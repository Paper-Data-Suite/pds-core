"""Installed Core wheel: fresh-process synthetic checkpoint/recovery gate."""

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
    from pds_core import _teacher_private_scratch_fresh_process_checkpoints as probe

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or wheel.suffix != ".whl"
        or not wheel.is_file()
    ):
        raise RuntimeError("candidate_wheel_refused")
    for module in (pds_core, probe):
        location = module.__file__
        if location is None:
            raise RuntimeError("installed_module_origin_missing")
        path = Path(location).resolve(strict=True)
        if not path.is_relative_to(purelib) or path.is_relative_to(source):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_fresh_process_checkpoints as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    observed: dict[str, str] = {}
    total = 0
    for scenario in probe.PrivateFreshCheckpointScenario:
        result = probe.probe_disposable_fresh_process_checkpoints(scenario)
        if type(result) is not probe.PrivateFreshCheckpointReview:
            raise RuntimeError("invalid_fresh_checkpoint_review")
        for field in (
            "production_mutation_admitted",
            "automatic_replay_allowed",
            "automatic_retry_allowed",
            "journal_retirement_allowed",
            "notes_records_available",
            "noncooperating_writer_exclusion_qualified",
            "atomic_content_compare_and_swap_qualified",
            "directory_crash_durability_qualified",
            "multi_document_atomic_commit_qualified",
        ):
            if getattr(result, field) is not False:
                raise RuntimeError("unexpected_production_authority")
        if not (
            result.independent_producer_hard_exit_observed
            and result.independent_read_only_inspector_observed
            and result.inspector_left_evidence_unchanged
            and result.independent_explicit_recovery_observed
            and result.journal_remains_pending
        ):
            raise RuntimeError("fresh_process_checkpoint_custody_failed")
        if scenario.value.startswith("conflict_"):
            if (
                result.state
                is not probe.PrivateFreshCheckpointState.CONFLICT_EVIDENCE_PRESERVED_HOLD
                or not result.conflict_evidence_preserved
                or result.exact_synthetic_afterimages_verified
                or result.second_recovery_noop
                or result.independent_python_interpreters != 3
            ):
                raise RuntimeError("fresh_process_conflict_preservation_failed")
        elif (
            result.state
            is not (
                probe.PrivateFreshCheckpointState.ALREADY_COMPLETE_PENDING_HOLD
                if scenario is probe.PrivateFreshCheckpointScenario.BOTH_PENDING_REVIEW
                else probe.PrivateFreshCheckpointState.EXPLICIT_FRESH_PROCESS_RESUMED_PENDING_HOLD
            )
            or not result.exact_synthetic_afterimages_verified
            or not result.second_recovery_noop
            or result.conflict_evidence_preserved
            or result.independent_python_interpreters != 4
        ):
            raise RuntimeError("fresh_process_resume_failed")
        total += result.independent_python_interpreters
        observed[scenario.value] = result.state.value
    bad = probe.probe_disposable_fresh_process_checkpoints(
        cast(probe.PrivateFreshCheckpointScenario, "prepared")
    )
    if (
        total != 40
        or bad.state is not probe.PrivateFreshCheckpointState.INVALID_REQUEST_REFUSED
        or len(readiness._REQUIRED) != 9
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("negative_capability_gate_failed")
    return {
        "scenarios": observed,
        "interruption_checkpoints": 7,
        "conflict_cases": 4,
        "independent_python_interpreters": total,
        "inspector_read_only": True,
        "explicit_recovery_process_only": True,
        "pending_journal_retained": True,
        "invalid_scenario_refused": True,
        "scratch_root_unchanged": True,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "automatic_retry_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "noncooperating_writer_exclusion_qualified": False,
        "atomic_content_compare_and_swap_qualified": False,
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
        raise RuntimeError("unsupported_platform")
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
        raise RuntimeError("unsafe_report_scope")
    digest = _provenance(wheel, source, args.expected_version)
    evidence = {
        "schema": "pds.core.issue238.installed-fresh-process-checkpoints.v1",
        "result": "passed_synthetic_fresh_process_checkpoint_recovery_holds_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_FRESH_CHECKPOINTS: PASS (fresh-process scratch; journal pending)"
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
    ):
        print("ISSUE238_INSTALLED_FRESH_CHECKPOINTS: STOP", file=sys.stderr)
        raise SystemExit(1)
