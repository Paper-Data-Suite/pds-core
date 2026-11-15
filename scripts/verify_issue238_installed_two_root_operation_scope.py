"""Isolated-wheel 3G83 native two-root guard refusal (no production authority)."""

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
    from pds_core import _teacher_private_two_root_operation_scope as scope

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or wheel.suffix != ".whl"
        or not wheel.is_file()
    ):
        raise RuntimeError("invalid_candidate_wheel")
    for module in (pds_core, scope):
        origin = module.__file__
        if origin is None:
            raise RuntimeError("installed_module_missing_origin")
        actual = Path(origin).resolve(strict=True)
        if not actual.is_relative_to(purelib) or actual.is_relative_to(source):
            raise RuntimeError("candidate_module_not_from_wheel")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _review(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_two_root_operation_scope as scope
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    # Invalid root is deliberate: no current owner/private root is touched.
    invalid = scope.review_existing_two_root_operation_scope(Path("relative-workspace"))
    observed = scope.PrivateTwoRootOperationState
    expected = (
        observed.INVALID_REQUEST_BLOCKED
        if sys.platform in {"linux", "win32"}
        else observed.UNSUPPORTED_BLOCKED
    )
    if (
        type(invalid) is not scope.PrivateTwoRootOperationReview
        or invalid.state is not expected
        or invalid.unqualified_requirements != readiness._REQUIRED
        or len(invalid.unqualified_requirements) != 9
        or any(
            (
                invalid.read_only_guard_observed,
                invalid.two_root_observations_rechecked,
                invalid.operation_owned_write_guard_qualified,
                invalid.production_mutation_admitted,
                invalid.automatic_replay_allowed,
                invalid.journal_retirement_allowed,
                invalid.notes_records_available,
                invalid.directory_crash_durability_qualified,
                invalid.multi_document_atomic_commit_qualified,
                invalid.noncooperating_writer_exclusion_qualified,
            )
        )
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("two_root_scope_not_safely_blocked")
    # Never serialize a principal, workspace path, descriptor or native handle.
    return {
        "invalid_workspace_refusal": invalid.state.value,
        "unqualified_requirements": list(invalid.unqualified_requirements),
        "no_scratch_mutation": True,
        "operation_owned_write_guard_qualified": False,
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
    result = _review(scratch)
    evidence = {
        "schema": "pds.core.issue238.installed-two-root-operation-scope.v1",
        "result": "passed_non_authorizing_two_root_operation_scope_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **result,
    }
    report.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_TWO_ROOT_OPERATION_SCOPE: PASS (no production authority)")
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
            "ISSUE238_INSTALLED_TWO_ROOT_OPERATION_SCOPE: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
