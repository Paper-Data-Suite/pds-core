"""Installed-wheel Core #238 3G96 read-only persistence uncertainty gate."""

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
    from pds_core import _teacher_private_scratch_persistence_review as review

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or wheel.suffix != ".whl"
        or not wheel.is_file()
    ):
        raise RuntimeError("candidate_wheel_refused")
    for module in (pds_core, review):
        file = module.__file__
        if file is None:
            raise RuntimeError("installed_source_unavailable")
        location = Path(file).resolve(strict=True)
        if not location.is_relative_to(purelib) or location.is_relative_to(checkout):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_persistence_review as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    baseline = tuple(scratch.iterdir())
    expected = {
        "orphan_checkpoint_temp": "conflict_evidence_hold",
        "registry_rename_not_acknowledged": "uncertain_rename_hold",
        "descriptor_rename_not_acknowledged": "uncertain_rename_hold",
        "both_pending_manual_review": "pending_manual_review_hold",
        "corrupt_canonical_journal": "conflict_evidence_hold",
        "acknowledged_registry_image_mismatch": "conflict_evidence_hold",
        "linux_parent_directory_fsync": (
            "linux_directory_sync_request_observed_hold"
            if sys.platform == "linux"
            else "windows_directory_sync_unqualified"
        ),
    }
    observed: dict[str, str] = {}
    interpreters = 0
    for scenario in probe.PrivatePersistenceReviewScenario:
        review = probe.probe_disposable_persistence_review(scenario)
        if (
            type(review) is not probe.PrivatePersistenceReview
            or review.state.value != expected[scenario.value]
        ):
            raise RuntimeError("uncertain_state_not_held")
        for field in (
            "production_mutation_admitted",
            "automatic_replay_allowed",
            "automatic_retry_allowed",
            "journal_retirement_allowed",
            "notes_records_available",
            "directory_crash_durability_qualified",
            "multi_document_atomic_commit_qualified",
            "noncooperating_writer_exclusion_qualified",
            "atomic_content_compare_and_swap_qualified",
        ):
            if getattr(review, field) is not False:
                raise RuntimeError("production_authority_leaked")
        is_windows_directory_refusal = (
            sys.platform == "win32"
            and scenario
            is probe.PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC
        )
        if is_windows_directory_refusal:
            if (
                review.independent_interpreters != 0
                or review.parent_directory_fsync_requested
                or review.read_only_fresh_inspector_observed
            ):
                raise RuntimeError("unsupported_directory_fsync_was_attempted")
        else:
            sync = (
                scenario
                is probe.PrivatePersistenceReviewScenario.LINUX_PARENT_DIRECTORY_FSYNC
            )
            if not (
                review.independent_interpreters == 2
                and review.independent_producer_hard_exit_observed
                and review.read_only_fresh_inspector_observed
                and review.observed_images_unchanged_by_inspection
                and review.pending_journal_evidence_preserved
                and review.conflicting_or_uncertain_evidence_held
                and review.parent_directory_fsync_requested is sync
                and review.native_parent_directory_identity_rechecked is sync
            ):
                raise RuntimeError("scratch_evidence_not_preserved")
        interpreters += review.independent_interpreters
        observed[scenario.value] = review.state.value
    bad = probe.probe_disposable_persistence_review(
        cast(probe.PrivatePersistenceReviewScenario, "orphan_checkpoint_temp")
    )
    if (
        bad.state is not probe.PrivatePersistenceReviewState.INVALID_REQUEST_REFUSED
        or interpreters != (14 if sys.platform == "linux" else 12)
        or len(readiness._REQUIRED) != 9
        or tuple(scratch.iterdir()) != baseline
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("installed_negative_capability_gate_failed")
    return {
        "scenarios": observed,
        "independent_interpreters": interpreters,
        "read_only_inspection_only": True,
        "uncertain_rename_evidence_held": True,
        "conflict_evidence_held": True,
        "journal_remains_pending": True,
        "linux_parent_fsync_only": sys.platform == "linux",
        "power_loss_durability_qualified": False,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "automatic_retry_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "multi_document_atomic_commit_qualified": False,
        "noncooperating_writer_exclusion_qualified": False,
        "atomic_content_compare_and_swap_qualified": False,
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
        "schema": "pds.core.issue238.installed-persistence-review.v1",
        "result": "passed_synthetic_uncertain_persistence_evidence_holds_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_PERSISTENCE_REVIEW: PASS (scratch uncertain holds; no replay)"
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
        print("ISSUE238_INSTALLED_PERSISTENCE_REVIEW: STOP", file=sys.stderr)
        raise SystemExit(1)
