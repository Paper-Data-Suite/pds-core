"""Installed Core #238 3G99 native Windows SID / protected DACL scratch gate."""

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
    from pds_core import _teacher_private_scratch_windows_owner_acl_review as probe

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or not wheel.is_file()
        or wheel.suffix != ".whl"
    ):
        raise RuntimeError("candidate_wheel_refused")
    for module in (pds_core, probe):
        origin = module.__file__
        if origin is None:
            raise RuntimeError("missing_installed_module_origin")
        path = Path(origin).resolve(strict=True)
        if not path.is_relative_to(purelib) or path.is_relative_to(checkout):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_windows_owner_acl_review as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    expected = {
        "protected_owner": "protected_dacl_shape_observed_hold",
        "unprotected_dacl": "unprotected_dacl_refused",
        "everyone_read_dacl": "everyone_access_refused",
        "spoofed_owner": "owner_mismatch_refused",
        "missing_child": "missing_child_refused",
    }
    observed: dict[str, str] = {}
    for scenario in probe.PrivateWindowsOwnerAclScenario:
        review = probe.probe_disposable_windows_owner_acl(scenario)
        if type(review) is not probe.PrivateWindowsOwnerAclReview:
            raise RuntimeError("invalid_owner_acl_report")
        if sys.platform == "win32":
            if (
                review.state.value != expected[scenario.value]
                or review.scenario != scenario.value
                or not review.process_token_sid_reobserved
                or not review.negative_evidence_preserved
            ):
                raise RuntimeError("windows_acl_case_not_qualified")
            if scenario is probe.PrivateWindowsOwnerAclScenario.MISSING_CHILD:
                if any(
                    (
                        review.dacl_read_from_native_handle,
                        review.dacl_protection_control_observed,
                        review.explicit_acl_shape_classified,
                        review.native_owner_sid_matches_token,
                    )
                ):
                    raise RuntimeError("missing_child_misreported_as_acl")
            elif not all(
                (
                    review.dacl_read_from_native_handle,
                    review.dacl_protection_control_observed,
                    review.explicit_acl_shape_classified,
                    review.native_owner_sid_matches_token,
                )
            ):
                raise RuntimeError("native_owner_acl_evidence_incomplete")
        elif (
            review.state is not probe.PrivateWindowsOwnerAclState.WINDOWS_ONLY_REFUSED
            or review.scenario != "none"
            or review.process_token_sid_reobserved
            or review.dacl_read_from_native_handle
        ):
            raise RuntimeError("linux_must_refuse_windows_acl_fixture")
        for field in (
            "production_mutation_admitted",
            "production_owner_acl_qualified",
            "windows_effective_access_qualified",
            "owner_binding_allowed",
            "automatic_replay_allowed",
            "automatic_retry_allowed",
            "journal_retirement_allowed",
            "notes_records_available",
            "directory_crash_durability_qualified",
            "multi_document_atomic_commit_qualified",
            "noncooperating_writer_exclusion_qualified",
        ):
            if getattr(review, field) is not False:
                raise RuntimeError("unexpected_production_acl_authority")
        observed[scenario.value] = review.state.value
    invalid = probe.probe_disposable_windows_owner_acl(
        cast(probe.PrivateWindowsOwnerAclScenario, "protected_owner")
    )
    if (
        invalid.state is not probe.PrivateWindowsOwnerAclState.INVALID_REQUEST_REFUSED
        or len(readiness._REQUIRED) != 9
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("negative_production_boundary_refused")
    return {
        "scenarios": observed,
        "fixed_scenarios": 5,
        "token_sid_returned_or_logged": False,
        "native_acl_fixture_windows_only": sys.platform == "win32",
        "read_only_after_scratch_creation": True,
        "real_private_root_touched": False,
        "scratch_root_unchanged": True,
        "production_mutation_admitted": False,
        "production_owner_acl_qualified": False,
        "windows_effective_access_qualified": False,
        "owner_binding_allowed": False,
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
    if sys.platform not in {"win32", "linux"}:
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
        or report.parent != scratch.parent
        or report.exists()
    ):
        raise RuntimeError("unsafe_report_scope")
    digest = _provenance(wheel, checkout, args.expected_version)
    evidence = {
        "schema": "pds.core.issue238.installed-windows-owner-acl-review.v1",
        "result": "passed_windows_scratch_owner_acl_shape_holds_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_WINDOWS_OWNER_ACL_REVIEW: PASS (scratch SID/DACL shape; no authority)"
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
        print("ISSUE238_INSTALLED_WINDOWS_OWNER_ACL_REVIEW: STOP", file=sys.stderr)
        raise SystemExit(1)
