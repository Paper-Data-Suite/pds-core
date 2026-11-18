"""Installed-wheel Core #238 3G97 native custody and identity drift hold gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path
from typing import cast


def _provenance(wheel: Path, checkout: Path, version: str) -> str:
    import pds_core
    from pds_core import _teacher_private_scratch_custody_reentry as probe

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
            raise RuntimeError("installed_source_unavailable")
        origin = Path(location).resolve(strict=True)
        if not origin.is_relative_to(purelib) or origin.is_relative_to(checkout):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_custody_reentry as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    original = tuple(scratch.iterdir())
    expected = {
        "stable_registry_installed": "stable_uncertain_hold",
        "stable_both_pending": "stable_pending_manual_hold",
        "equal_bytes_live_substitution": "same_bytes_identity_drift_hold",
        "equal_bytes_stage_substitution": "same_bytes_identity_drift_hold",
        "equal_bytes_journal_substitution": "same_bytes_identity_drift_hold",
        "changed_registry_bytes": "content_conflict_hold",
    }
    observed: dict[str, str] = {}
    processes = 0
    for scenario in probe.PrivateCustodyReentryScenario:
        review = probe.probe_disposable_custody_reentry(scenario)
        if (
            type(review) is not probe.PrivateCustodyReentryReview
            or review.state.value != expected[scenario.value]
            or review.scenario != scenario.value
        ):
            raise RuntimeError("native_custody_review_unqualified")
        if not (
            review.native_parent_handle_retained_across_inspection
            and review.independent_producer_hard_exit_observed
            and review.independent_read_only_inspector_observed
            and review.exact_bytes_inspector_unchanged
            and review.watched_entry_identity_checked
            and review.pending_journal_retained
        ):
            raise RuntimeError("native_parent_custody_missing")
        rival = (
            scenario.value.startswith("equal_bytes_")
            or scenario.value == "changed_registry_bytes"
        )
        if (
            review.independent_interpreters != (3 if rival else 2)
            or review.equal_bytes_identity_substitution_detected
            is not scenario.value.startswith("equal_bytes_")
            or review.content_conflict_detected
            is not (
                scenario is probe.PrivateCustodyReentryScenario.CHANGED_REGISTRY_BYTES
            )
        ):
            raise RuntimeError("native_identity_vs_contents_detection_failed")
        for attribute in (
            "production_mutation_admitted",
            "automatic_replay_allowed",
            "automatic_retry_allowed",
            "journal_retirement_allowed",
            "notes_records_available",
            "atomic_content_compare_and_swap_qualified",
            "noncooperating_writer_exclusion_qualified",
            "native_handle_relative_replace_qualified",
            "directory_crash_durability_qualified",
            "multi_document_atomic_commit_qualified",
        ):
            if getattr(review, attribute) is not False:
                raise RuntimeError("production_authority_leaked")
        observed[scenario.value] = review.state.value
        processes += review.independent_interpreters
    bad = probe.probe_disposable_custody_reentry(
        cast(probe.PrivateCustodyReentryScenario, "stable_registry_installed")
    )
    if (
        bad.state is not probe.PrivateCustodyReentryState.INVALID_REQUEST_REFUSED
        or processes != 16
        or len(readiness._REQUIRED) != 9
        or tuple(scratch.iterdir()) != original
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("installed_negative_capability_gate_failed")
    return {
        "scenarios": observed,
        "independent_python_interpreters": processes,
        "native_parent_retained": True,
        "same_byte_substitution_detected": True,
        "read_only_fresh_inspection": True,
        "journal_remains_pending": True,
        "invalid_scenario_refused": True,
        "scratch_root_unchanged": True,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "automatic_retry_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "noncooperating_writer_exclusion_qualified": False,
        "atomic_content_compare_and_swap_qualified": False,
        "native_handle_relative_replace_qualified": False,
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
    checkout = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        not scratch.is_dir()
        or scratch.is_symlink()
        or scratch.name != "scratch"
        or scratch.is_relative_to(checkout)
        or report.is_relative_to(checkout)
        or report.exists()
        or report.parent != scratch.parent
    ):
        raise RuntimeError("unsafe_report_scope")
    digest = _provenance(wheel, checkout, args.expected_version)
    evidence = {
        "schema": "pds.core.issue238.installed-custody-reentry.v1",
        "result": "passed_native_custody_identity_holds_without_recovery_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_CUSTODY_REENTRY: PASS (native scratch identity holds; no replay)"
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
        print("ISSUE238_INSTALLED_CUSTODY_REENTRY: STOP", file=sys.stderr)
        raise SystemExit(1)
