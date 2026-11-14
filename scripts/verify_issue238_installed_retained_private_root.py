"""Installed-wheel #238 3G80 native PRIVATE-root custody, read-only and blocked.

A read-only probe retains directory identities and checks OS owner/security only
when Core's actual prospective private root exists. Its absence is a bounded
negative observation, not permission to create. No caller root is admitted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path


def _installed_wheel(wheel: Path, source: Path, version: str) -> str:
    import pds_core
    from pds_core import _teacher_private_retained_root_custody as custody

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    locations = (
        Path(pds_core.__file__).resolve(strict=True),
        Path(custody.__file__).resolve(strict=True),
    )
    if (
        any(
            not location.is_relative_to(purelib) or location.is_relative_to(source)
            for location in locations
        )
        or version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or not wheel.is_file()
        or wheel.suffix != ".whl"
    ):
        raise RuntimeError("candidate_wheel_not_isolated")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _blocked_review() -> dict[str, object]:
    from pds_core import _teacher_private_retained_root_custody as custody
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_recovery_canonical_journaled_restart as canon
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier
    from pds_core import _teacher_private_recovery_synthetic_writer_admission as scratch
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    native = custody.review_existing_private_root_native_custody()
    prior = readiness.review_private_production_readiness()
    intent = canon._canonical_fork_intent()
    blocked = barrier.review_private_production_write_barrier(
        scratch.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
        intent.witness.registry_revision_before,
        intent,
    )
    if (
        not isinstance(native.state, custody.PrivateRetainedRootState)
        or len(prior.unqualified_requirements) != 9
        or prior.unqualified_requirements != readiness._REQUIRED
        or blocked.state
        is not barrier.PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED
        or tuple(x.value for x in blocked.unqualified_requirements)
        != readiness._REQUIRED
        or any(
            (
                native.production_mutation_admitted,
                native.automatic_replay_allowed,
                native.journal_retirement_allowed,
                native.notes_records_available,
                native.directory_crash_durability_qualified,
                native.noncooperating_writer_exclusion_qualified,
            )
        )
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("native_custody_production_barrier_regressed")
    return {
        "retained_root_native_observation": native.state.value,
        "production_readiness": prior.state.value,
        "production_write_barrier": blocked.state.value,
        "required_production_qualifications": list(prior.unqualified_requirements),
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "noncooperating_writer_exclusion_qualified": False,
        "qualified_for_production_private_store": False,
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
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
    ):
        raise RuntimeError("unsafe_sanitized_report_scope")
    digest = _installed_wheel(wheel, source, args.expected_version)
    evidence = {
        "schema": "pds.core.issue238.installed-retained-private-root-custody.v1",
        "result": "passed_non_authorizing_native_root_custody_review_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_blocked_review(),
    }
    # No private path, SID, UID, native handle, lock ID, or raw metadata in JSON.
    report.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_RETAINED_ROOT: PASS (read-only; no production authority)")
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
            "ISSUE238_INSTALLED_RETAINED_ROOT: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
