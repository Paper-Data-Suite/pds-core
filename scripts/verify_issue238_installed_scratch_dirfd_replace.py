"""3G88 isolated-wheel POSIX dirfd scratch gate; Windows denies this protocol."""

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
    from pds_core import _teacher_private_scratch_dirfd_replace as probe

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
    from pds_core import _teacher_private_scratch_dirfd_replace as probe
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    before = tuple(scratch.iterdir())
    scenarios: dict[str, str] = {}
    for scenario in probe.PrivateDirfdScratchScenario:
        result = probe.probe_linux_disposable_dirfd_replace(scenario)
        if type(result) is not probe.PrivateDirfdScratchReview:
            raise RuntimeError("invalid_scratch_review")
        for key in (
            "production_mutation_admitted",
            "noncooperating_writer_exclusion_qualified",
            "atomic_content_compare_and_swap_qualified",
            "native_windows_replace_qualified",
            "automatic_replay_allowed",
            "journal_retirement_allowed",
            "notes_records_available",
            "directory_crash_durability_qualified",
            "multi_document_atomic_commit_qualified",
        ):
            if getattr(result, key) is not False:
                raise RuntimeError("unexpected_production_authority")
        if sys.platform == "linux":
            expected = {
                "normal": "linux_dirfd_scratch_replaced_nonauthorizing",
                "live_entry_drift": "live_entry_drift_refused",
                "stage_entry_drift": "stage_entry_drift_refused",
                "parent_relink": "parent_relink_refused",
            }[scenario.value]
            if (
                result.state.value != expected
                or not result.linux_directory_fd_retained
                or result.replacement_called_dirfd_relative
                != (scenario is probe.PrivateDirfdScratchScenario.NORMAL)
                or result.exact_scratch_postimage_verified
                != (scenario is probe.PrivateDirfdScratchScenario.NORMAL)
                or not result.pending_synthetic_journal_preserved
            ):
                raise RuntimeError("linux_dirfd_scratch_unqualified")
        else:
            if (
                result.state
                is not probe.PrivateDirfdScratchState.WINDOWS_NATIVE_PROTOCOL_UNQUALIFIED
                or result.linux_directory_fd_retained
                or result.replacement_called_dirfd_relative
            ):
                raise RuntimeError("windows_protocol_must_refuse")
        scenarios[scenario.value] = result.state.value
    invalid = probe.probe_linux_disposable_dirfd_replace(
        cast(probe.PrivateDirfdScratchScenario, "normal")
    )
    if (
        invalid.state is not probe.PrivateDirfdScratchState.INVALID_REQUEST_REFUSED
        or tuple(scratch.iterdir()) != before
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
        or len(readiness._REQUIRED) != 9
    ):
        raise RuntimeError("negative_capability_gate_failed")
    return {
        "scenarios": scenarios,
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
        "schema": "pds.core.issue238.installed-native-scratch-dirfd-replace.v1",
        "result": "passed_linux_dirfd_scratch_windows_refusal_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **_exercise(scratch),
    }
    report.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_SCRATCH_DIRFD: PASS (Linux scratch / Windows refusal)")
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
        print("ISSUE238_INSTALLED_SCRATCH_DIRFD: STOP", file=sys.stderr)
        raise SystemExit(1)
