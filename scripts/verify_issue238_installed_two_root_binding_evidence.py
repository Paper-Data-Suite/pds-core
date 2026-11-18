"""Installed Core wheel: synthetic two-root association/owner evidence holds."""

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
    from pds_core import _teacher_private_scratch_two_root_binding_evidence as probe

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or wheel.suffix != ".whl"
        or not wheel.is_file()
    ):
        raise RuntimeError("candidate_wheel_refused")
    for module in (pds_core, probe):
        source = module.__file__
        if source is None:
            raise RuntimeError("installed_module_origin_missing")
        path = Path(source).resolve(strict=True)
        if not path.is_relative_to(purelib) or path.is_relative_to(checkout):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_two_root_binding_evidence as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    expected = {
        "consistent": "consistent_but_unqualified_hold",
        "association_mismatch": "association_conflict_hold",
        "owner_marker_mismatch": "synthetic_owner_marker_conflict_hold",
        "duplicate_workspace_copy": "duplicate_association_hold",
        "unsupported_descriptor_version": "malformed_metadata_hold",
        "registry_extra_field": "malformed_metadata_hold",
        "posix_private_root_mode_drift": (
            "posix_protection_refused"
            if sys.platform == "linux"
            else "windows_dacl_unqualified"
        ),
    }
    outcomes: dict[str, str] = {}
    for case in probe.PrivateTwoRootEvidenceScenario:
        result = probe.probe_disposable_two_root_binding_evidence(case)
        if (
            type(result) is not probe.PrivateTwoRootEvidenceReview
            or result.state.value != expected[case.value]
        ):
            raise RuntimeError("two_root_scratch_evidence_refused")
        for field in (
            "journal_or_notes_touched",
            "production_mutation_admitted",
            "explicit_binding_allowed",
            "effective_os_owner_acl_qualified",
            "copied_descriptor_authorizes_binding",
            "automatic_replay_allowed",
            "automatic_retry_allowed",
            "journal_retirement_allowed",
            "notes_records_available",
            "directory_crash_durability_qualified",
            "multi_document_atomic_commit_qualified",
            "noncooperating_writer_exclusion_qualified",
            "atomic_content_compare_and_swap_qualified",
        ):
            if getattr(result, field) is not False:
                raise RuntimeError("production_write_authority_leaked")
        if case is probe.PrivateTwoRootEvidenceScenario.POSIX_PRIVATE_ROOT_MODE_DRIFT:
            if (
                result.native_workspace_parent_retained
                or result.two_root_file_images_checked
            ):
                raise RuntimeError("unsafe_mode_admitted")
        elif not (
            result.native_workspace_parent_retained
            and result.native_private_parent_retained
            and result.cooperative_private_lock_held
            and result.two_root_file_images_checked
            and result.native_two_root_identities_rechecked
            and result.posix_owner_mode_observed_scratch_only
            is (sys.platform == "linux")
            and result.duplicate_association_detected
            is (case is probe.PrivateTwoRootEvidenceScenario.DUPLICATE_WORKSPACE_COPY)
        ):
            raise RuntimeError("two_root_native_evidence_unqualified")
        outcomes[case.value] = result.state.value
    invalid = probe.probe_disposable_two_root_binding_evidence(
        cast(probe.PrivateTwoRootEvidenceScenario, "consistent")
    )
    if (
        invalid.state is not probe.PrivateTwoRootEvidenceState.INVALID_REQUEST_REFUSED
        or len(readiness._REQUIRED) != 9
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("negative_capability_provenance_failed")
    return {
        "scenarios": outcomes,
        "synthetic_two_root_identity_held": True,
        "duplicate_association_refused": True,
        "linux_owner_mode_observed_scratch_only": sys.platform == "linux",
        "windows_effective_dacl_qualified": False,
        "production_os_owner_acl_qualified": False,
        "scratch_root_unchanged": True,
        "production_mutation_admitted": False,
        "explicit_binding_allowed": False,
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
        "schema": "pds.core.issue238.installed-two-root-binding-evidence.v1",
        "result": "passed_synthetic_two_root_binding_evidence_holds_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_TWO_ROOT_BINDING_EVIDENCE: PASS (synthetic two-root holds; no authority)"
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
        print("ISSUE238_INSTALLED_TWO_ROOT_BINDING_EVIDENCE: STOP", file=sys.stderr)
        raise SystemExit(1)
