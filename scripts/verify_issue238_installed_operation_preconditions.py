"""Installed Core #238 3G82 operation-boundary non-authorizing review.

No private path, OS principal, native HANDLE, synthetic registry image,
operation guard, transaction intent or Notes data enters the report.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path


_REQUIRED = (
    "effective_os_owner_and_private_acl",
    "workspace_descriptor_binding",
    "two_root_native_parent_custody",
    "exclusive_operation_owned_guard",
    "canonical_intent_recheck_in_guard",
    "exact_registry_journal_stage_images",
    "native_replace_sharing_and_postimage",
    "directory_durability_and_crash_recovery",
    "recovery_and_journal_retirement_protocol",
)


def _installed_wheel_provenance(wheel: Path, source: Path, version: str) -> str:
    import pds_core
    from pds_core import _teacher_private_operation_preconditions as operation

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    for module in (pds_core, operation):
        location = module.__file__
        if location is None:
            raise RuntimeError("installed_module_origin_unavailable")
        item = Path(location).resolve(strict=True)
        if not item.is_relative_to(purelib) or item.is_relative_to(source):
            raise RuntimeError("installed_module_origin_not_isolated")
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or not wheel.is_file()
        or wheel.suffix != ".whl"
    ):
        raise RuntimeError("installed_wheel_provenance_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _blocked_preconditions() -> dict[str, object]:
    from pds_core import _teacher_private_operation_preconditions as operation
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_retained_root_custody as custody
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    review = operation.review_private_operation_preconditions()
    allowed_retained = {item.value for item in custody.PrivateRetainedRootState}
    allowed_root = {
        "missing",
        "present_unverified",
        "invalid_configuration",
        "unsafe_path",
        "access_denied",
        "unsupported",
        "unavailable",
    }
    if (
        type(review) is not operation.PrivateOperationPreconditionReview
        or review.state
        not in {
            operation.PrivateOperationPreconditionState.PRODUCTION_BLOCKED,
            operation.PrivateOperationPreconditionState.OBSERVATION_REFUSED_BLOCKED,
            operation.PrivateOperationPreconditionState.ROOT_CHANGED_BLOCKED,
            operation.PrivateOperationPreconditionState.CANONICAL_DESCRIPTION_REFUSED_BLOCKED,
        }
        or review.root_observation not in allowed_root
        or review.retained_root_observation not in allowed_retained | {"unavailable"}
        or review.unqualified_requirements != _REQUIRED
        or tuple(item.value for item in barrier._REQUIRED) != _REQUIRED
        or readiness._REQUIRED != _REQUIRED
        or any(
            (
                review.operation_owned_guard_qualified,
                review.production_mutation_admitted,
                review.automatic_replay_allowed,
                review.journal_retirement_allowed,
                review.notes_records_available,
                review.directory_crash_durability_qualified,
                review.transaction_commit_qualified,
                review.noncooperating_writer_exclusion_qualified,
            )
        )
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("operation_preconditions_not_non_authorizing")
    return {
        "operation_preconditions": review.state.value,
        "retained_root_observation": review.retained_root_observation,
        "root_observation": review.root_observation,
        "os_owner_observed": review.owner_observed,
        "root_rechecked_in_review": review.root_rechecked_in_review,
        "synthetic_canonical_intent_description_checked": review.canonical_intent_description_checked,
        "unqualified_requirements": list(review.unqualified_requirements),
        "operation_owned_guard_qualified": False,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "transaction_commit_qualified": False,
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
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.parent != scratch.parent
        or report.exists()
    ):
        raise RuntimeError("unsafe_sanitized_report_scope")
    digest = _installed_wheel_provenance(wheel, source, args.expected_version)
    evidence = {
        "schema": "pds.core.issue238.installed-operation-preconditions.v1",
        "result": "passed_non_authorizing_operation_preconditions_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_blocked_preconditions(),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_OPERATION_PRECONDITIONS: PASS (all nine blockers retained)"
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
    ) as exc:
        print(
            "ISSUE238_INSTALLED_OPERATION_PRECONDITIONS: STOP ("
            + type(exc).__name__
            + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
