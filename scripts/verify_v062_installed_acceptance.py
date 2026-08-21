"""Installed-distribution acceptance for the additive pds-core v0.6.2 surfaces."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import os
import tempfile
from pathlib import Path
from typing import Final

EXPECTED_VERSION: Final[str] = "0.6.2"
SIBLING_IMPORTS: Final[tuple[str, ...]] = (
    "scoreform",
    "quillan",
    "concord",
    "meridian",
    "vitrine",
    "portia",
    "paper_data_suite",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _assert_installed_distribution() -> None:
    import pds_core

    _require(
        importlib.metadata.version("pds-core") == EXPECTED_VERSION,
        "installed pds-core distribution version mismatch",
    )
    _require(
        pds_core.__version__ == EXPECTED_VERSION,
        "installed pds_core.__version__ mismatch",
    )

    checkout = Path(__file__).resolve().parents[1]
    if (checkout / "pyproject.toml").is_file() and (checkout / "pds_core").is_dir():
        package_path = Path(pds_core.__file__).resolve()
        _require(
            not package_path.is_relative_to(checkout),
            "pds_core resolved from the source checkout instead of the installed wheel",
        )

    for sibling in SIBLING_IMPORTS:
        _require(
            importlib.util.find_spec(sibling) is None,
            f"standalone environment unexpectedly contains sibling package {sibling}",
        )

    distribution = importlib.metadata.distribution("pds-core")
    scripts = {
        entry.name: entry.value
        for entry in distribution.entry_points
        if entry.group == "console_scripts"
    }
    _require(
        scripts.get("pds-core") == "pds_core.cli:main",
        "installed pds-core console script mismatch",
    )
    _require(
        scripts.get("core") == "pds_core.core_menu:main",
        "installed core console script mismatch",
    )


def _assert_imports_are_side_effect_free() -> None:
    before = set(Path.cwd().iterdir())
    import pds_core.module_operations  # noqa: F401
    import pds_core.provider_diagnostics  # noqa: F401
    import pds_core.roster_imports  # noqa: F401
    import pds_core.cli_support.roster_imports  # noqa: F401
    after = set(Path.cwd().iterdir())
    _require(before == after, "importing v0.6.2 surfaces created local state")


def _assert_operations_and_diagnostics_contracts() -> None:
    from pds_core.module_operations import (
        MODULE_OPERATIONS_CONTRACT_VERSION,
        MODULE_OPERATIONS_ENTRY_POINT_GROUP,
        ModuleAttentionReport,
        ModuleOperationsProfile,
        ModuleOperationsRequest,
        ModuleReadinessReport,
    )
    from pds_core.provider_diagnostics import (
        ProviderKind,
        diagnose_core_providers,
        inspect_core_provider_entry_points,
    )

    _require(
        MODULE_OPERATIONS_CONTRACT_VERSION == "1",
        "module-operations contract version mismatch",
    )
    _require(
        MODULE_OPERATIONS_ENTRY_POINT_GROUP == "paper_data_suite.module_operations",
        "module-operations entry-point group mismatch",
    )

    def readiness_provider(
        _request: ModuleOperationsRequest,
    ) -> ModuleReadinessReport:
        return ModuleReadinessReport(evaluation="evaluated", ready=True)

    def attention_provider(
        _request: ModuleOperationsRequest,
    ) -> ModuleAttentionReport:
        return ModuleAttentionReport(evaluation="evaluated")

    profile = ModuleOperationsProfile(
        module_id="synthetic",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=readiness_provider,
        attention_provider=attention_provider,
    )
    _require(profile.module_id == "synthetic", "module-operations profile failed")

    provider_kinds: tuple[ProviderKind, ...] = (
        "routing_module",
        "publication_producer",
        "module_operations",
    )
    for provider_kind in provider_kinds:
        _require(
            inspect_core_provider_entry_points(provider_kind=provider_kind) == (),
            f"Core-only environment unexpectedly exposes {provider_kind} metadata",
        )
        _require(
            diagnose_core_providers(provider_kind=provider_kind) == (),
            f"Core-only environment unexpectedly diagnoses {provider_kind} providers",
        )


def _assert_guarded_roster_import(workspace: Path) -> None:
    from pds_core.roster_imports import (
        RosterImportCandidateChangedError,
        RosterImportConflictError,
        commit_roster_import,
        plan_roster_import,
    )
    from pds_core.rosters import (
        ROSTER_REQUIRED_COLUMNS,
        validate_roster_rows,
        write_roster,
    )
    from pds_core.routes import class_roster_path

    class_id = "english10_p2"
    candidate = validate_roster_rows(
        ROSTER_REQUIRED_COLUMNS,
        (
            {
                "class_id": class_id,
                "student_id": "synthetic_001",
                "last_name": "Example",
                "first_name": "Avery",
                "period": "2",
            },
        ),
    )
    roster_path = class_roster_path(workspace, class_id)
    preview = plan_roster_import(workspace, class_id, candidate)
    _require(not roster_path.exists(), "roster preview unexpectedly wrote canonical state")
    _require(preview.addition_count == 1, "first-import preview addition count mismatch")
    _require(preview.change_count == 0, "first-import preview change count mismatch")
    _require(preview.removal_count == 0, "first-import preview removal count mismatch")

    committed = commit_roster_import(
        workspace,
        class_id,
        candidate,
        expected_current_state_token=preview.current_state_token,
        expected_candidate_state_token=preview.candidate_state_token,
    )
    _require(roster_path.is_file(), "guarded roster commit did not create canonical roster")
    _require(
        committed.committed_state_token == preview.candidate_state_token,
        "committed roster token mismatch",
    )

    current = plan_roster_import(workspace, class_id, candidate)
    _require(current.unchanged_count == 1, "identical roster was not unchanged")

    changed_candidate = validate_roster_rows(
        ROSTER_REQUIRED_COLUMNS,
        (
            {
                "class_id": class_id,
                "student_id": "synthetic_001",
                "last_name": "Example",
                "first_name": "Changed",
                "period": "2",
            },
        ),
    )
    try:
        commit_roster_import(
            workspace,
            class_id,
            changed_candidate,
            expected_current_state_token=current.current_state_token,
            expected_candidate_state_token=current.candidate_state_token,
        )
    except RosterImportCandidateChangedError:
        pass
    else:
        raise RuntimeError("changed candidate did not fail the reviewed-candidate guard")

    stale_preview = plan_roster_import(workspace, class_id, candidate)
    changed_current = validate_roster_rows(
        ROSTER_REQUIRED_COLUMNS,
        (
            {
                "class_id": class_id,
                "student_id": "synthetic_001",
                "last_name": "Example",
                "first_name": "CanonicalChange",
                "period": "2",
            },
        ),
    )
    write_roster(roster_path, changed_current, overwrite=True)
    try:
        commit_roster_import(
            workspace,
            class_id,
            candidate,
            expected_current_state_token=stale_preview.current_state_token,
            expected_candidate_state_token=stale_preview.candidate_state_token,
        )
    except RosterImportConflictError:
        pass
    else:
        raise RuntimeError("stale canonical roster did not fail the reviewed-state guard")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="pds-core-v062-installed-") as temporary:
        temporary_root = Path(temporary)
        import_cwd = temporary_root / "import-cwd"
        workspace = temporary_root / "workspace"
        import_cwd.mkdir()
        workspace.mkdir()
        try:
            os.chdir(import_cwd)
            _assert_installed_distribution()
            _assert_imports_are_side_effect_free()
            _assert_operations_and_diagnostics_contracts()
            _assert_guarded_roster_import(workspace)
        finally:
            os.chdir(original_cwd)

    print("pds-core v0.6.2 installed acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
