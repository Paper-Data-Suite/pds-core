"""Core #238: isolated installed-wheel *non-authorizing* native boundary smoke.

Only synthetic absent paths under an existing caller-owned scratch directory are
inspected. This is not a private binding, a write permit, or durability proof.
Run under a fresh wheel-only venv, Python -I, and outside the source checkout.
The JSON evidence deliberately contains no SID, UID, owner path, or filename.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from unittest.mock import patch


class BoundaryFailure(RuntimeError):
    """Refusal code must be static and contain no private information."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise BoundaryFailure(code)


def outside_checkout(candidate: Path, source: Path) -> bool:
    try:
        candidate.resolve(strict=True).relative_to(source.resolve(strict=True))
    except ValueError:
        return True
    return False


def qualify_native_absent_inspection(scratch: Path) -> dict[str, str]:
    """Read-only native owner probes on a never-created private suffix."""
    from pds_core import _teacher_private_inspection as private
    from pds_core import _teacher_private_native_preflight as native
    from pds_core.workspace import inspect_workspace_root

    key = "LOCALAPPDATA" if sys.platform == "win32" else "XDG_DATA_HOME"
    before = frozenset(scratch.iterdir())
    with patch.dict(os.environ, {key: str(scratch)}):
        inspected = private.inspect_private_root()
        require(
            inspected.state is private.PrivateRootState.MISSING,
            "absent_root_not_reported_missing",
        )
        owner = inspected.owner
        if not isinstance(owner, private.EffectiveOSOwner):
            raise BoundaryFailure("native_owner_missing")
        if sys.platform == "win32":
            require(
                owner.kind == "windows_token_sid" and owner.value.startswith("S-1-"),
                "windows_token_owner_unqualified",
            )
        else:
            require(
                owner.kind == "posix_euid" and owner.value == str(os.geteuid()),
                "linux_effective_owner_unqualified",
            )
        native_result = native.inspect_native_private_preflight()
        require(
            native_result.state is native.NativePrivatePreflightState.MISSING,
            "native_absent_root_not_missing",
        )
        absent_workspace = scratch / "synthetic-workspace-never-created"
        workspace = inspect_workspace_root(absent_workspace)
        require(not workspace.exists, "workspace_inspection_promoted_missing")
        require(not absent_workspace.exists(), "workspace_inspection_wrote_files")
        require(not (scratch / "paper-data-suite").exists(), "linux_private_created")
        require(not (scratch / "Paper Data Suite").exists(), "windows_private_created")

    # An unqualified/hostile environment must never become an alternative
    # eligible root. Windows missing LOCALAPPDATA, Linux relative XDG root.
    with patch.dict(os.environ):
        if sys.platform == "win32":
            os.environ.pop(key, None)
        else:
            os.environ[key] = "relative-private-root-not-qualified"
        malformed = private.inspect_private_root()
        require(
            malformed.state is private.PrivateRootState.INVALID_CONFIGURATION,
            "invalid_location_did_not_refuse",
        )
    require(
        frozenset(scratch.iterdir()) == before,
        "read_only_probe_created_scratch_files",
    )
    return {
        "owner_proof": "native_effective_owner_observed_no_identity_recorded",
        "private_root": "missing_no_creation",
        "native_protection": "missing_no_write_authority",
        "invalid_location": "refused",
        "workspace_inspection": "read_only_unbound",
    }


def qualify_negative_features() -> list[str]:
    import pds_core.teacher_experience as experience
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier

    expected = frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    caps = experience.get_teacher_experience_capabilities()
    require(type(caps) is frozenset and caps == expected, "capability_boundary_drift")
    require(
        importlib.util.find_spec("pds_core.teacher_private_storage") is None,
        "premature_private_storage_public_api",
    )
    states = set(barrier.PrivateProductionWriteBarrierState)
    require(
        not any(
            "approved" in state.value or "ready" in state.value for state in states
        ),
        "positive_production_barrier_state",
    )
    refused = barrier.review_private_production_write_barrier(
        None,  # type: ignore[arg-type]
        0,
        None,  # type: ignore[arg-type]
    )
    require(
        refused.state is barrier.PrivateProductionWriteBarrierState.INVALID_REQUEST,
        "invalid_production_request_not_refused",
    )
    require(
        refused.unqualified_requirements
        == tuple(barrier.PrivateProductionWriteRequirement),
        "nine_requirement_barrier_drift",
    )
    require(
        len(refused.unqualified_requirements) == 9,
        "production_requirement_count_drift",
    )
    require(
        not any(
            hasattr(refused, item)
            for item in ("permit", "execute", "write", "path", "handle")
        ),
        "production_write_capability_leak",
    )
    return sorted(caps)


def execute() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    require(sys.platform in {"win32", "linux"}, "native_platform_unqualified")
    require(sys.flags.isolated == 1, "python_not_isolated")
    source = args.source_checkout.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    report = args.report.resolve()
    require(source.is_dir() and scratch.is_dir(), "source_or_scratch_invalid")
    require(wheel.is_file() and wheel.suffix == ".whl", "wheel_invalid")
    require(not report.exists(), "evidence_report_already_exists")
    require(
        outside_checkout(Path.cwd(), source)
        and outside_checkout(scratch, source)
        and outside_checkout(wheel, source),
        "artifact_or_cwd_in_checkout",
    )
    import pds_core
    from pds_core import _teacher_private_inspection as private
    from pds_core import _teacher_private_native_preflight as native
    from pds_core import _teacher_private_recovery_production_write_barrier as barrier

    installed_modules = (pds_core, private, native, barrier)
    for module in installed_modules:
        path = getattr(module, "__file__", None)
        if not isinstance(path, str):
            raise BoundaryFailure("installed_module_location_missing")
        require(
            outside_checkout(Path(path), source),
            "source_checkout_import_instead_of_wheel",
        )
    require(
        importlib.metadata.version("pds-core") == args.expected_version
        and pds_core.__version__ == args.expected_version,
        "installed_version_mismatch",
    )
    features = qualify_negative_features()
    native_result = qualify_native_absent_inspection(scratch)
    result: dict[str, object] = {
        "issue": 238,
        "slice": "3G64",
        "kind": "isolated_installed_wheel_native_no_write_smoke",
        "result": "passed_non_authorizing_checks_only",
        "wheel_file": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "version": args.expected_version,
        "host_os": platform.system(),
        "host_arch": platform.machine(),
        "python": platform.python_version(),
        "native": native_result,
        "capabilities": features,
        "production_mutation_admitted": False,
        "production_replay_admitted": False,
        "journal_retirement_admitted": False,
        "notes_records_available": False,
        "windows_power_loss_durability_qualified": False,
        "macos_qualified": False,
        "published_release_qualified": False,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print("ISSUE238_INSTALLED_NATIVE_BOUNDARY: PASS (no write authority)")
    print("QUALIFIED_WHEEL_SHA256:", result["wheel_sha256"])
    return 0


def main() -> int:
    try:
        return execute()
    except BoundaryFailure as exc:
        print(f"ISSUE238_INSTALLED_NATIVE_BOUNDARY: REFUSED ({exc})", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            "ISSUE238_INSTALLED_NATIVE_BOUNDARY: REFUSED (unexpected_failure)",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
