"""Installed Core #238 3G93: Windows ReplaceFileW TOCTOU / Linux refusal."""

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
    from pds_core import _teacher_private_scratch_windows_postcheck_race as probe

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
            raise RuntimeError("module_origin_missing")
        resolved = Path(origin).resolve(strict=True)
        if not resolved.is_relative_to(purelib) or resolved.is_relative_to(source):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _exercise(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_scratch_windows_postcheck_race as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    first = tuple(scratch.iterdir())
    observed: dict[str, str] = {}
    for scenario in probe.PrivateWindowsPostcheckRaceScenario:
        result = probe.probe_windows_disposable_postcheck_race(scenario)
        if type(result) is not probe.PrivateWindowsPostcheckRaceReview:
            raise RuntimeError("invalid_review_type")
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
                "normal": "normal_backup_nonauthorizing",
                "live_swap_after_check": "live_postcheck_toctou_demonstrated",
                "stage_swap_after_check": "stage_postcheck_toctou_demonstrated",
            }[scenario.value]
            rival = scenario is not probe.PrivateWindowsPostcheckRaceScenario.NORMAL
            if (
                result.state.value != expected
                or not result.native_directory_handle_retained
                or not result.cooperative_lock_held_during_race
                or not result.final_exact_precheck_before_rival
                or result.independent_uncooperative_interpreter_observed is not rival
                or result.same_bytes_new_file_identity_after_precheck is not rival
                or not result.native_replacefile_called_after_race
                or not result.exact_backup_afterimage_verified
                or not result.exact_new_registry_afterimage_verified
                or not result.synthetic_pending_journal_preserved
            ):
                raise RuntimeError("windows_scratch_postcheck_race_unqualified")
        elif (
            result.state
            is not probe.PrivateWindowsPostcheckRaceState.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED
            or result.native_replacefile_called_after_race
        ):
            raise RuntimeError("linux_native_windows_refusal_missing")
        observed[scenario.value] = result.state.value
    invalid = probe.probe_windows_disposable_postcheck_race(
        cast(probe.PrivateWindowsPostcheckRaceScenario, "normal")
    )
    if (
        invalid.state
        is not probe.PrivateWindowsPostcheckRaceState.INVALID_REQUEST_REFUSED
        or tuple(scratch.iterdir()) != first
        or len(readiness._REQUIRED) != 9
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("negative_capability_gate_failed")
    return {
        "scenarios": observed,
        "native_windows_postcheck_race_scratch_only": sys.platform == "win32",
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
        "schema": "pds.core.issue238.installed-windows-postcheck-race.v1",
        "result": "passed_windows_postcheck_race_scratch_linux_refusal_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ISSUE238_INSTALLED_WINDOWS_POSTCHECK_RACE: PASS (Windows scratch / Linux refusal)"
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
        print("ISSUE238_INSTALLED_WINDOWS_POSTCHECK_RACE: STOP", file=sys.stderr)
        raise SystemExit(1)
