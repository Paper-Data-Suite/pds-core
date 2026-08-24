"''Installed-distribution acceptance for the additive pds-core v0.6.3 release."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import tempfile
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Final

EXPECTED_VERSION: Final[str] = "0.6.3"
EXPECTED_PACKS: Final[dict[str, tuple[int, int, int]]] = {
    "ap_csp_fall_2023": (95, 3, 1),
    "njsls_clks_2020": (301, 4, 1),
    "njsls_csdt_2020": (163, 2, 1),
    "njsls_ela_2023": (135, 3, 1),
}
EXPECTED_PACK_IDS: Final[tuple[str, ...]] = tuple(sorted(EXPECTED_PACKS))
ENGLISH11: Final[str] = "english11_2023_njsls_ela"
ENGLISH12: Final[str] = "english12_2023_njsls_ela"
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
    import pds_core.standards  # noqa: F401
    import pds_core.standards_selection  # noqa: F401
    import pds_core.starter_standards  # noqa: F401
    import pds_core.cli_support.roster_imports  # noqa: F401

    after = set(Path.cwd().iterdir())
    _require(before == after, "importing v0.6.3 surfaces created local state")


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


def _assert_starter_pack_surface(root: Path) -> None:
    from pds_core.standards import (
        StandardsLibrary,
        load_standards_library,
        standards_library_from_dict,
        standards_library_path,
        write_workspace_standards_library,
    )
    from pds_core.standards_selection import (
        list_profiles_for_selection,
        list_standards_for_selection,
    )
    from pds_core.starter_standards import (
        StarterStandardsInstallError,
        install_starter_standards_library,
        list_starter_standards_packs,
        load_starter_standards_library,
        validate_starter_standards_library,
    )

    metadata = list_starter_standards_packs()
    _require(
        tuple(item.pack_id for item in metadata) == EXPECTED_PACK_IDS,
        "installed starter pack IDs/order mismatch",
    )
    for item in metadata:
        expected = EXPECTED_PACKS[item.pack_id]
        _require(
            (item.standard_count, item.profile_count, item.framework_count) == expected,
            f"starter metadata count mismatch for {item.pack_id}",
        )
        library = validate_starter_standards_library(item.pack_id)
        _require(
            (len(library.standards), len(library.profiles), len(library.frameworks))
            == expected,
            f"starter library count mismatch for {item.pack_id}",
        )

    legacy = standards_library_from_dict({"standards": [], "profiles": []})
    _require(legacy.frameworks == (), "legacy framework-less library no longer loads")

    ap = load_starter_standards_library("ap_csp_fall_2023")
    ap_ids = tuple(item.standard_id for item in ap.standards)
    _require(
        sum(item.startswith("ap-csp-2023:big-idea:") for item in ap_ids) == 5,
        "AP CSP Big Idea reference count mismatch",
    )
    _require(
        sum(item.startswith("ap-csp-2023:lo:") for item in ap_ids) == 64,
        "AP CSP Learning Objective reference count mismatch",
    )
    _require(
        sum(item.startswith("ap-csp-2023:practice:") for item in ap_ids) == 6,
        "AP CSP practice reference count mismatch",
    )
    _require(
        sum(item.startswith("ap-csp-2023:skill:") for item in ap_ids) == 20,
        "AP CSP practice-skill reference count mismatch",
    )
    _require(
        all(item.grade_band is None for item in ap.standards),
        "AP CSP release data invented a source grade band",
    )

    ela = load_starter_standards_library("njsls_ela_2023")
    profiles = {item.profile_id: item for item in ela.profiles}
    _require(ENGLISH11 in profiles, "English 11 ELA profile missing")
    _require(ENGLISH12 in profiles, "English 12 ELA profile missing")
    _require(
        profiles[ENGLISH11].standards == profiles[ENGLISH12].standards,
        "English 11 and English 12 no longer share the source 11-12 IDs",
    )
    english11_profiles = list_profiles_for_selection(ela, course="English 11")
    _require(
        tuple(item.profile_id for item in english11_profiles) == (ENGLISH11,),
        "English 11 profile selection mismatch",
    )
    english11_items = list_standards_for_selection(
        ela,
        source="2023 NJSLS-ELA",
        course="English 11",
        available_module="pds-quillan",
    )
    _require(
        {item.standard_id for item in english11_items}
        == set(profiles[ENGLISH11].standards),
        "English 11 course selection does not resolve the shared 11-12 pool",
    )

    combined_root = root / "four-pack"
    library = StandardsLibrary(standards=())
    for pack_id in EXPECTED_PACK_IDS:
        result = install_starter_standards_library(combined_root, pack_id, library)
        _require(not result.has_conflicts, f"unexpected first-install conflict: {pack_id}")
        library = load_standards_library(standards_library_path(combined_root))

    _require(len(library.standards) == 694, "combined standard count mismatch")
    _require(len(library.profiles) == 12, "combined profile count mismatch")
    _require(len(library.frameworks) == 4, "combined framework count mismatch")
    _require(
        len({item.standard_id for item in library.standards}) == 694,
        "combined standard IDs are not unique",
    )
    _require(
        len({item.profile_id for item in library.profiles}) == 12,
        "combined profile IDs are not unique",
    )
    _require(
        len({item.framework_id for item in library.frameworks}) == 4,
        "combined framework IDs are not unique",
    )
    _require(
        len({item.source for item in library.frameworks}) == 4,
        "combined framework sources are not unique",
    )
    _require(
        not (combined_root / "standards" / "usage").exists(),
        "starter installation created standards usage events",
    )
    before_combined = standards_library_path(combined_root).read_bytes()
    for pack_id in EXPECTED_PACK_IDS:
        result = install_starter_standards_library(combined_root, pack_id, library)
        _require(result.changed_count == 0, f"reinstall changed pack {pack_id}")
        _require(not result.has_conflicts, f"reinstall conflicted for pack {pack_id}")
        library = load_standards_library(standards_library_path(combined_root))
    _require(
        standards_library_path(combined_root).read_bytes() == before_combined,
        "idempotent four-pack reinstall changed canonical bytes",
    )

    upgrade_root = root / "ela-v062-upgrade"
    previous = StandardsLibrary(
        standards=ela.standards,
        profiles=tuple(
            profile for profile in ela.profiles if profile.profile_id != ENGLISH11
        ),
        frameworks=(),
    )
    write_workspace_standards_library(upgrade_root, previous, overwrite=False)
    previous_loaded = load_standards_library(standards_library_path(upgrade_root))
    result = install_starter_standards_library(
        upgrade_root,
        "njsls_ela_2023",
        previous_loaded,
    )
    _require(result.standards_added == 0, "ELA upgrade unexpectedly added definitions")
    _require(result.standards_skipped == 135, "ELA upgrade definition skip count mismatch")
    _require(result.standards_overwritten == 0, "ELA upgrade overwrote definitions")
    _require(result.profiles_added == 1, "ELA upgrade profile add count mismatch")
    _require(result.profiles_skipped == 2, "ELA upgrade profile skip count mismatch")
    _require(result.profiles_overwritten == 0, "ELA upgrade overwrote profiles")
    _require(result.frameworks_added == 1, "ELA upgrade framework add count mismatch")
    _require(result.frameworks_skipped == 0, "ELA upgrade framework skip count mismatch")
    _require(result.frameworks_overwritten == 0, "ELA upgrade overwrote framework")
    _require(result.changed_count == 2, "ELA upgrade changed-count mismatch")
    upgraded = load_standards_library(standards_library_path(upgrade_root))
    _require(
        upgraded.standards == previous.standards,
        "ELA upgrade rewrote or reordered existing definitions",
    )
    _require(
        {item.profile_id for item in upgraded.profiles}
        == {"english10_2023_njsls_ela", ENGLISH11, ENGLISH12},
        "ELA upgrade profile set mismatch",
    )
    _require(
        {item.framework_id for item in upgraded.frameworks} == {"njsls_ela_2023"},
        "ELA upgrade framework set mismatch",
    )
    upgrade_before = standards_library_path(upgrade_root).read_bytes()
    again = install_starter_standards_library(
        upgrade_root,
        "njsls_ela_2023",
        upgraded,
    )
    _require(again.changed_count == 0, "ELA upgrade reinstall was not idempotent")
    _require(again.standards_skipped == 135, "ELA reinstall definition skip mismatch")
    _require(again.profiles_skipped == 3, "ELA reinstall profile skip mismatch")
    _require(again.frameworks_skipped == 1, "ELA reinstall framework skip mismatch")
    _require(
        standards_library_path(upgrade_root).read_bytes() == upgrade_before,
        "ELA idempotent reinstall changed canonical bytes",
    )

    conflict_root = root / "framework-conflict"
    conflict_framework = dataclass_replace(
        ap.frameworks[0],
        title=f"{ap.frameworks[0].title} — synthetic local conflict",
    )
    existing_conflict = StandardsLibrary(
        standards=(),
        frameworks=(conflict_framework,),
    )
    write_workspace_standards_library(
        conflict_root,
        existing_conflict,
        overwrite=False,
    )
    conflict_path = standards_library_path(conflict_root)
    conflict_before = conflict_path.read_bytes()
    try:
        install_starter_standards_library(
            conflict_root,
            "ap_csp_fall_2023",
            existing_conflict,
        )
    except StarterStandardsInstallError as error:
        result = error.result
    else:
        raise RuntimeError("framework-only starter conflict was not rejected")
    _require(result.has_conflicts, "framework-only conflict did not set has_conflicts")
    _require(
        result.framework_conflicts == ("ap_csp_fall_2023",),
        "framework-only conflict identity mismatch",
    )
    _require(result.standards_added == 95, "conflict fixture definition plan mismatch")
    _require(result.profiles_added == 3, "conflict fixture profile plan mismatch")
    _require(
        conflict_path.read_bytes() == conflict_before,
        "framework conflict partially modified canonical standards state",
    )


def main() -> int:
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="pds-core-v063-installed-") as temporary:
        temporary_root = Path(temporary)
        import_cwd = temporary_root / "import-cwd"
        import_cwd.mkdir()
        try:
            os.chdir(import_cwd)
            _assert_installed_distribution()
            _assert_imports_are_side_effect_free()
            _assert_operations_and_diagnostics_contracts()
            _assert_guarded_roster_import(temporary_root / "roster-workspace")
            _assert_starter_pack_surface(temporary_root / "standards-workspaces")
            _require(
                list(import_cwd.iterdir()) == [],
                "installed acceptance created working-directory residue",
            )
        finally:
            os.chdir(original_cwd)

    print("pds-core v0.6.3 installed acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
