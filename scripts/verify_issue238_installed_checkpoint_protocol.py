"""Installed-wheel Core #238 3G94 synthetic checkpoint and interruption gate."""

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
    from pds_core import _teacher_private_scratch_checkpoint_protocol as probe

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or wheel.suffix != ".whl"
        or not wheel.is_file()
    ):
        raise RuntimeError("candidate_wheel_refused")
    for module in (pds_core, probe):
        origin = module.__file__
        if origin is None:
            raise RuntimeError("installed_module_origin_missing")
        path = Path(origin).resolve(strict=True)
        if not path.is_relative_to(purelib) or path.is_relative_to(source):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_checkpoint_protocol as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    outcomes: dict[str, str] = {}
    for scenario in probe.PrivateCheckpointScenario:
        review = probe.probe_disposable_checkpoint_protocol(scenario)
        if type(review) is not probe.PrivateCheckpointReview:
            raise RuntimeError("invalid_checkpoint_review")
        for key in (
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
            if getattr(review, key) is not False:
                raise RuntimeError("unexpected_production_authority")
        if scenario.value.startswith("conflict_"):
            if (
                review.state is not probe.PrivateCheckpointState.CONFLICT_PRESERVED_HOLD
                or not review.conflict_evidence_unchanged_until_scratch_cleanup
                or review.guarded_explicit_resume_invoked
                or not review.journal_remains_pending
            ):
                raise RuntimeError("checkpoint_conflict_preservation_failed")
        elif (
            review.state
            is not (
                probe.PrivateCheckpointState.ALREADY_COMPLETE_PENDING_HOLD
                if scenario is probe.PrivateCheckpointScenario.BOTH_PENDING_REVIEW
                else probe.PrivateCheckpointState.EXPLICIT_SYNTHETIC_RESUME_PENDING_HOLD
            )
            or not review.phase_inferred_from_journal_and_images
            or not review.guarded_explicit_resume_invoked
            or not review.exact_synthetic_afterimages_verified
            or not review.journal_remains_pending
            or review.resumptions_after_complete != 1
        ):
            raise RuntimeError("checkpoint_resume_failed")
        outcomes[scenario.value] = review.state.value
    invalid = probe.probe_disposable_checkpoint_protocol(
        cast(probe.PrivateCheckpointScenario, "prepared")
    )
    if (
        invalid.state is not probe.PrivateCheckpointState.INVALID_REQUEST_REFUSED
        or len(readiness._REQUIRED) != 9
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("negative_capability_gate_failed")
    return {
        "scenarios": outcomes,
        "interruption_checkpoints": 7,
        "conflict_cases": 4,
        "explicit_synthetic_resume_only": True,
        "pending_journal_retained": True,
        "invalid_scenario_refused": True,
        "scratch_root_unchanged": True,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "automatic_retry_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "multi_document_atomic_commit_qualified": False,
        "noncooperating_writer_exclusion_qualified": False,
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
        "schema": "pds.core.issue238.installed-synthetic-checkpoint-protocol.v1",
        "result": "passed_synthetic_checkpoint_interrupt_resume_holds_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_CHECKPOINT_PROTOCOL: PASS (explicit scratch resume; journal pending)"
    )
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
    ):
        print("ISSUE238_INSTALLED_CHECKPOINT_PROTOCOL: STOP", file=sys.stderr)
        raise SystemExit(1)
