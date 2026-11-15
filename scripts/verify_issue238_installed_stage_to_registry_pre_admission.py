"""Installed-wheel #238 3G85: fail-closed stage pre-admission inventory only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path


def _provenance(wheel: Path, source: Path, version: str) -> str:
    import pds_core
    from pds_core import _teacher_private_stage_to_registry_pre_admission as gate

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or not wheel.is_file()
        or wheel.suffix != ".whl"
    ):
        raise RuntimeError("candidate_wheel_refused")
    for module in (pds_core, gate):
        origin = module.__file__
        if origin is None:
            raise RuntimeError("installed_module_origin_missing")
        resolved = Path(origin).resolve(strict=True)
        if not resolved.is_relative_to(purelib) or resolved.is_relative_to(source):
            raise RuntimeError("installed_candidate_provenance_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _review(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_stage_to_registry_pre_admission as gate
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    refused = gate.review_existing_stage_to_registry_pre_admission(
        Path("relative-workspace"), "not-a-transaction", 0
    )
    if (
        type(refused) is not gate.PrivateStagePreAdmissionReview
        or refused.state
        is not gate.PrivateStagePreAdmissionState.INVALID_REQUEST_BLOCKED
        or refused.unqualified_requirements != readiness._REQUIRED
        or len(refused.unqualified_requirements) != 9
        or any(
            (
                refused.existing_two_root_read_guard_observed,
                refused.two_preimage_rounds_rechecked,
                refused.production_mutation_admitted,
                refused.operation_owned_write_guard_qualified,
                refused.exclusive_noncooperating_writer_guard_qualified,
                refused.native_replace_postimage_qualified,
                refused.automatic_replay_allowed,
                refused.journal_retirement_allowed,
                refused.notes_records_available,
                refused.directory_crash_durability_qualified,
                refused.multi_document_atomic_commit_qualified,
            )
        )
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("unqualified_pre_admission_inventory")
    return {
        "invalid_request_refusal": refused.state.value,
        "unqualified_requirements": list(refused.unqualified_requirements),
        "no_scratch_mutation": True,
        "operation_owned_write_guard_qualified": False,
        "exclusive_noncooperating_writer_guard_qualified": False,
        "native_replace_postimage_qualified": False,
        "production_mutation_admitted": False,
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
    detail = _review(scratch)
    evidence = {
        "schema": "pds.core.issue238.installed-stage-pre-admission.v1",
        "result": "passed_non_authorizing_stage_pre_admission_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **detail,
    }
    report.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_STAGE_PRE_ADMISSION: PASS (no write authority)")
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
            "ISSUE238_INSTALLED_STAGE_PRE_ADMISSION: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
