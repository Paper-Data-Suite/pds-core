"""Installed-wheel Core #238 production-readiness gap gate (3G79).

Non-mutating, sanitized. This gate certifies ONLY that the nine requirements
remain explicit and the currently installed Core refuses production mutation.
No amount of successful synthetic evidence can set READY or retire a journal.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path


def _installed_provenance(wheel: Path, source: Path, version: str) -> str:
    import pds_core

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    imported = Path(pds_core.__file__).resolve(strict=True)
    if (
        not imported.is_relative_to(purelib)
        or imported.is_relative_to(source)
        or not wheel.is_file()
        or wheel.suffix != ".whl"
        or version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
    ):
        raise RuntimeError("installed_wheel_provenance_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _readiness() -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier
    from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    review = readiness.review_private_production_readiness()
    if (
        review.state
        not in {
            readiness.PrivateProductionReadinessState.PRODUCTION_BLOCKED,
            readiness.PrivateProductionReadinessState.PROBE_REFUSED_PRODUCTION_BLOCKED,
        }
        or review.unqualified_requirements != readiness._REQUIRED
        or tuple(value.value for value in barrier._REQUIRED) != readiness._REQUIRED
        or len(review.unqualified_requirements) != 9
        or any(
            (
                review.production_mutation_admitted,
                review.automatic_replay_allowed,
                review.journal_retirement_allowed,
                review.notes_records_available,
                review.directory_crash_durability_qualified,
                review.multi_document_atomic_commit_qualified,
                review.noncooperating_writer_exclusion_qualified,
            )
        )
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("production_readiness_contract_refused")

    intent = canon._canonical_fork_intent()
    blocked = barrier.review_private_production_write_barrier(
        scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
        intent.witness.registry_revision_before,
        intent,
    )
    if (
        blocked.state
        is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        or tuple(item.value for item in blocked.unqualified_requirements)
        != readiness._REQUIRED
    ):
        raise RuntimeError("production_write_barrier_regressed")
    # Owner/principal, raw paths and metadata bytes are *never* serialized.
    return {
        "readiness": review.state.value,
        "unqualified_requirements": list(review.unqualified_requirements),
        "preliminary_root_observation": review.root_observation,
        "native_root_observation": review.native_root_observation,
        "os_owner_observed": review.owner_observed,
        "production_write_barrier": blocked.state.value,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
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
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
    ):
        raise RuntimeError("unsafe_evidence_scope")
    digest = _installed_provenance(wheel, source, args.expected_version)
    decision = _readiness()
    evidence = {
        "schema": "pds.core.issue238.installed-production-readiness-gaps.v1",
        "result": "passed_non_authorizing_production_gap_gate_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **decision,
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_PRODUCTION_GAPS: PASS (nine blockers; no authority)")
    print("QUALIFIED_WHEEL_SHA256: " + digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
        print(
            "ISSUE238_INSTALLED_PRODUCTION_GAPS: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
