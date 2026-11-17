"""Installed-wheel Core #238 3G92 Windows ReplaceFileW backup / Linux refusal."""

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
    from pds_core import _teacher_private_scratch_windows_replace_backup as probe

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
        resolved = Path(origin).resolve(strict=True)
        if not resolved.is_relative_to(purelib) or resolved.is_relative_to(source):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_windows_replace_backup as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    observed: dict[str, str] = {}
    for scenario in probe.PrivateWindowsReplaceBackupScenario:
        result = probe.probe_windows_disposable_replace_backup(scenario)
        if type(result) is not probe.PrivateWindowsReplaceBackupReview:
            raise RuntimeError("invalid_scratch_review")
        for field in (
            "production_mutation_admitted",
            "windows_handle_relative_replace_qualified",
            "noncooperating_writer_exclusion_qualified",
            "atomic_content_compare_and_swap_qualified",
            "automatic_replay_allowed",
            "journal_retirement_allowed",
            "notes_records_available",
            "directory_crash_durability_qualified",
            "multi_document_atomic_commit_qualified",
        ):
            if getattr(result, field) is not False:
                raise RuntimeError("unexpected_production_authority")
        if sys.platform == "win32":
            expected = {
                "normal_backup": "native_backup_preserved_scratch_only",
                "live_preimage_drift": "live_drift_refused",
                "stage_preimage_drift": "stage_drift_refused",
            }[scenario.value]
            if (
                result.state.value != expected
                or not result.native_parent_retained_during_operation
                or not result.cooperative_lock_held
                or not result.exact_preimages_rechecked
                or not result.synthetic_journal_preserved
            ):
                raise RuntimeError("windows_native_backup_semantics_unqualified")
            if scenario is probe.PrivateWindowsReplaceBackupScenario.NORMAL_BACKUP:
                if not (
                    result.native_replacefile_called
                    and result.original_backup_verified
                    and result.new_registry_verified
                ):
                    raise RuntimeError("windows_native_backup_postimages_refused")
            elif (
                result.native_replacefile_called
                or result.original_backup_verified
                or result.new_registry_verified
            ):
                raise RuntimeError("windows_drift_must_refuse_before_replace")
        elif (
            result.state
            is not probe.PrivateWindowsReplaceBackupState.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED
            or result.native_replacefile_called
        ):
            raise RuntimeError("linux_windows_protocol_must_refuse")
        observed[scenario.value] = result.state.value
    bad = probe.probe_windows_disposable_replace_backup(
        cast(probe.PrivateWindowsReplaceBackupScenario, "normal_backup")
    )
    if (
        bad.state is not probe.PrivateWindowsReplaceBackupState.INVALID_REQUEST_REFUSED
        or tuple(scratch.iterdir()) != before
        or len(readiness._REQUIRED) != 9
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("negative_capability_gate_failed")
    return {
        "scenarios": observed,
        "native_windows_replacefile_backup_scratch_only": sys.platform == "win32",
        "atomic_content_cas_qualified": False,
        "invalid_scenario_refused": True,
        "scratch_root_unchanged": True,
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
        "schema": "pds.core.issue238.installed-windows-replacefile-backup.v1",
        "result": "passed_windows_replacefile_backup_scratch_linux_refusal_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_WINDOWS_REPLACEFILE_BACKUP: PASS (Windows scratch / Linux refusal)"
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
        print("ISSUE238_INSTALLED_WINDOWS_REPLACEFILE_BACKUP: STOP", file=sys.stderr)
        raise SystemExit(1)
