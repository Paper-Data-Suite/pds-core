"""Bundled starter standards library discovery and installation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Final

from pds_core.standards import (
    StandardDefinition,
    StandardsFrameworkMetadata,
    StandardsLibrary,
    StandardsProfile,
    StandardsValidationError,
    load_standards_library,
    standards_library_path,
    validate_standards_library,
    write_workspace_standards_library,
)


_STARTER_STANDARDS_PACKAGE: Final[str] = "pds_core.starter_data.standards"
_NJSLS_CLKS_2020_PACK_ID: Final[str] = "njsls_clks_2020"
_NJSLS_CSDT_2020_PACK_ID: Final[str] = "njsls_csdt_2020"
_NJSLS_ELA_2023_PACK_ID: Final[str] = "njsls_ela_2023"


@dataclass(frozen=True, slots=True)
class StarterStandardsPackConfig:
    """Static starter standards pack configuration."""

    pack_id: str
    title: str
    description: str
    source: str
    grade_bands: tuple[str, ...]
    courses: tuple[str, ...]
    resource_name: str


@dataclass(frozen=True, slots=True)
class StarterStandardsPackMetadata:
    """Display-ready starter standards pack metadata."""

    pack_id: str
    title: str
    description: str
    source: str
    grade_bands: tuple[str, ...]
    courses: tuple[str, ...]
    standard_count: int
    profile_count: int
    profile_ids: tuple[str, ...]
    framework_count: int = 0
    framework_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StarterStandardsInstallResult:
    """Summary of a starter standards install or dry merge."""

    pack_id: str
    target_path: Path
    standards_added: int
    standards_skipped: int
    standards_overwritten: int
    profiles_added: int
    profiles_skipped: int
    profiles_overwritten: int
    standard_conflicts: tuple[str, ...] = ()
    profile_conflicts: tuple[str, ...] = ()
    frameworks_added: int = 0
    frameworks_skipped: int = 0
    frameworks_overwritten: int = 0
    framework_conflicts: tuple[str, ...] = ()

    @property
    def has_conflicts(self) -> bool:
        return bool(
            self.standard_conflicts
            or self.profile_conflicts
            or self.framework_conflicts
        )

    @property
    def changed_count(self) -> int:
        return (
            self.standards_added
            + self.standards_overwritten
            + self.profiles_added
            + self.profiles_overwritten
            + self.frameworks_added
            + self.frameworks_overwritten
        )


_STARTER_PACKS: Final[dict[str, StarterStandardsPackConfig]] = {
    _NJSLS_CLKS_2020_PACK_ID: StarterStandardsPackConfig(
        pack_id=_NJSLS_CLKS_2020_PACK_ID,
        title=(
            "2020 NJSLS Career Readiness, Life Literacies and Key Skills "
            "Starter Standards"
        ),
        description=(
            "Complete coded Performance Expectations from 2020 NJSLS-CLKS "
            "Standards 9.1, 9.2, and 9.4, with reusable grades 9-12 "
            "source-area and combined CLKS profiles."
        ),
        source="2020 NJSLS-CLKS",
        grade_bands=("K-2", "3-5", "6-8", "9-12"),
        courses=(
            "Personal Financial Literacy",
            "Career Awareness, Exploration, Preparation and Training",
            "Life Literacies and Key Skills",
        ),
        resource_name="njsls_clks_2020_library.json",
    ),
    _NJSLS_CSDT_2020_PACK_ID: StarterStandardsPackConfig(
        pack_id=_NJSLS_CSDT_2020_PACK_ID,
        title=(
            "2020 NJSLS Computer Science and Design Thinking "
            "Starter Standards"
        ),
        description=(
            "Complete coded Performance Expectations from the 2020 New Jersey "
            "Student Learning Standards for Computer Science and Design Thinking, "
            "with reusable grades 9-12 Computer Science and Design Thinking "
            "profiles."
        ),
        source="2020 NJSLS-CS&DT",
        grade_bands=("K-2", "3-5", "6-8", "9-12"),
        courses=("Computer Science", "Design Thinking"),
        resource_name="njsls_csdt_2020_library.json",
    ),
    _NJSLS_ELA_2023_PACK_ID: StarterStandardsPackConfig(
        pack_id=_NJSLS_ELA_2023_PACK_ID,
        title="2023 NJSLS ELA High School Starter Standards",
        description=(
            "Grades 9-10 and 11-12 English Language Arts standards from the "
            "2023 New Jersey Student Learning Standards, with English 10 and "
            "English 12 reusable standards profiles."
        ),
        source="2023 NJSLS-ELA",
        grade_bands=("9-10", "11-12"),
        courses=("English 10", "English 12"),
        resource_name="njsls_ela_2023_library.json",
    ),
}


class StarterStandardsInstallError(StandardsValidationError):
    """Raised when a starter standards install cannot be completed safely."""

    result: StarterStandardsInstallResult

    def __init__(self, message: str, result: StarterStandardsInstallResult) -> None:
        self.result = result
        super().__init__(message)


def list_starter_standards_packs() -> tuple[StarterStandardsPackMetadata, ...]:
    """Return metadata for bundled starter standards packs."""
    return tuple(
        starter_standards_pack_metadata(pack_id)
        for pack_id in sorted(_STARTER_PACKS)
    )


def starter_standards_pack_metadata(
    pack_id: str,
) -> StarterStandardsPackMetadata:
    """Return metadata for one bundled starter standards pack."""
    config = _starter_pack_config(pack_id)
    library = load_starter_standards_library(config.pack_id)
    return StarterStandardsPackMetadata(
        pack_id=config.pack_id,
        title=config.title,
        description=config.description,
        source=config.source,
        grade_bands=config.grade_bands,
        courses=config.courses,
        standard_count=len(library.standards),
        profile_count=len(library.profiles),
        profile_ids=tuple(profile.profile_id for profile in library.profiles),
        framework_count=len(library.frameworks),
        framework_ids=tuple(
            framework.framework_id for framework in library.frameworks
        ),
    )


def load_starter_standards_library(pack_id: str) -> StandardsLibrary:
    """Load and validate one bundled starter standards library."""
    config = _starter_pack_config(pack_id)
    resource = files(_STARTER_STANDARDS_PACKAGE).joinpath(config.resource_name)
    with as_file(resource) as path:
        return load_standards_library(path)


def validate_starter_standards_library(pack_id: str) -> StandardsLibrary:
    """Validate and return one bundled starter standards library."""
    return validate_standards_library(load_starter_standards_library(pack_id))


def install_starter_standards_library(
    workspace_root: str | Path,
    pack_id: str,
    existing_library: StandardsLibrary,
    *,
    overwrite_conflicts: bool = False,
) -> StarterStandardsInstallResult:
    """Merge a bundled starter standards library into a workspace library."""
    starter_library = validate_starter_standards_library(pack_id)
    updated_library, result = merge_standards_libraries(
        pack_id,
        standards_library_path(workspace_root),
        existing_library,
        starter_library,
        overwrite_conflicts=overwrite_conflicts,
    )
    if result.has_conflicts:
        raise StarterStandardsInstallError(
            _install_conflict_message(result),
            result,
        )

    if result.changed_count == 0:
        return result

    write_workspace_standards_library(
        workspace_root,
        updated_library,
        overwrite=standards_library_path(workspace_root).exists(),
    )
    return result


def merge_standards_libraries(
    pack_id: str,
    target_path: str | Path,
    existing_library: StandardsLibrary,
    starter_library: StandardsLibrary,
    *,
    overwrite_conflicts: bool = False,
) -> tuple[StandardsLibrary, StarterStandardsInstallResult]:
    """Return the safe merge of existing and starter standards libraries."""
    existing = validate_standards_library(existing_library)
    starter = validate_standards_library(starter_library)

    standards, standards_added, standards_skipped, standards_overwritten = (
        _merge_standard_definitions(
            existing.standards,
            starter.standards,
            overwrite_conflicts=overwrite_conflicts,
        )
    )
    profiles, profiles_added, profiles_skipped, profiles_overwritten = (
        _merge_standards_profiles(
            existing.profiles,
            starter.profiles,
            overwrite_conflicts=overwrite_conflicts,
        )
    )
    frameworks, frameworks_added, frameworks_skipped, frameworks_overwritten = (
        _merge_standards_frameworks(
            existing.frameworks,
            starter.frameworks,
            overwrite_conflicts=overwrite_conflicts,
        )
    )

    standard_conflicts = _conflicting_ids(
        existing.standards,
        starter.standards,
        key_name="standard_id",
    )
    profile_conflicts = _conflicting_ids(
        existing.profiles,
        starter.profiles,
        key_name="profile_id",
    )
    framework_conflicts = _conflicting_ids(
        existing.frameworks,
        starter.frameworks,
        key_name="framework_id",
    )
    if overwrite_conflicts:
        standard_conflicts = ()
        profile_conflicts = ()
        framework_conflicts = ()

    result = StarterStandardsInstallResult(
        pack_id=pack_id,
        target_path=Path(target_path),
        standards_added=standards_added,
        standards_skipped=standards_skipped,
        standards_overwritten=standards_overwritten,
        profiles_added=profiles_added,
        profiles_skipped=profiles_skipped,
        profiles_overwritten=profiles_overwritten,
        standard_conflicts=standard_conflicts,
        profile_conflicts=profile_conflicts,
        frameworks_added=frameworks_added,
        frameworks_skipped=frameworks_skipped,
        frameworks_overwritten=frameworks_overwritten,
        framework_conflicts=framework_conflicts,
    )
    if result.has_conflicts:
        return existing, result

    return StandardsLibrary(
        standards=standards,
        profiles=profiles,
        frameworks=frameworks,
    ), result


def _starter_pack_config(pack_id: str) -> StarterStandardsPackConfig:
    normalized = _required_pack_id(pack_id)
    config = _STARTER_PACKS.get(normalized)
    if config is None:
        available = ", ".join(sorted(_STARTER_PACKS))
        raise StandardsValidationError(
            f"unknown starter standards pack {normalized!r}; "
            f"available packs: {available}"
        )
    return config


def _required_pack_id(value: object) -> str:
    if not isinstance(value, str):
        raise StandardsValidationError("pack_id must be a string.")
    normalized = value.strip()
    if not normalized:
        raise StandardsValidationError("pack_id must not be blank.")
    return normalized


def _merge_standard_definitions(
    existing: tuple[StandardDefinition, ...],
    incoming: tuple[StandardDefinition, ...],
    *,
    overwrite_conflicts: bool,
) -> tuple[tuple[StandardDefinition, ...], int, int, int]:
    added = 0
    skipped = 0
    overwritten = 0
    merged = list(existing)
    by_id = {
        definition.standard_id: index for index, definition in enumerate(existing)
    }

    for definition in incoming:
        index = by_id.get(definition.standard_id)
        if index is None:
            by_id[definition.standard_id] = len(merged)
            merged.append(definition)
            added += 1
        elif merged[index] == definition:
            skipped += 1
        elif overwrite_conflicts:
            merged[index] = definition
            overwritten += 1

    return tuple(merged), added, skipped, overwritten


def _merge_standards_frameworks(
    existing: tuple[StandardsFrameworkMetadata, ...],
    incoming: tuple[StandardsFrameworkMetadata, ...],
    *,
    overwrite_conflicts: bool,
) -> tuple[tuple[StandardsFrameworkMetadata, ...], int, int, int]:
    added = 0
    skipped = 0
    overwritten = 0
    merged = list(existing)
    by_id = {
        framework.framework_id: index
        for index, framework in enumerate(existing)
    }
    by_source = {framework.source: framework for framework in existing}

    for framework in incoming:
        source_match = by_source.get(framework.source)
        if (
            source_match is not None
            and source_match.framework_id != framework.framework_id
        ):
            raise StandardsValidationError(
                f"framework source {framework.source!r} already belongs to "
                f"framework_id {source_match.framework_id!r}."
            )

        framework_id = framework.framework_id
        index = by_id.get(framework_id)
        if index is None:
            by_id[framework_id] = len(merged)
            by_source[framework.source] = framework
            merged.append(framework)
            added += 1
        elif merged[index] == framework:
            skipped += 1
        elif overwrite_conflicts:
            merged[index] = framework
            overwritten += 1

    return tuple(merged), added, skipped, overwritten


def _merge_standards_profiles(
    existing: tuple[StandardsProfile, ...],
    incoming: tuple[StandardsProfile, ...],
    *,
    overwrite_conflicts: bool,
) -> tuple[tuple[StandardsProfile, ...], int, int, int]:
    added = 0
    skipped = 0
    overwritten = 0
    merged = list(existing)
    by_id = {profile.profile_id: index for index, profile in enumerate(existing)}

    for profile in incoming:
        index = by_id.get(profile.profile_id)
        if index is None:
            by_id[profile.profile_id] = len(merged)
            merged.append(profile)
            added += 1
        elif merged[index] == profile:
            skipped += 1
        elif overwrite_conflicts:
            merged[index] = profile
            overwritten += 1

    return tuple(merged), added, skipped, overwritten


def _conflicting_ids(
    existing: Iterable[object],
    incoming: Iterable[object],
    *,
    key_name: str,
) -> tuple[str, ...]:
    existing_by_id = {
        str(getattr(item, key_name)): item
        for item in existing
    }
    conflicts: list[str] = []
    for item in incoming:
        item_id = str(getattr(item, key_name))
        existing_item = existing_by_id.get(item_id)
        if existing_item is not None and existing_item != item:
            conflicts.append(item_id)
    return tuple(conflicts)


def _install_conflict_message(result: StarterStandardsInstallResult) -> str:
    parts = [
        f"starter standards pack {result.pack_id!r} conflicts with existing "
        "workspace standards data"
    ]
    if result.standard_conflicts:
        parts.append(
            "standard_id conflict(s): "
            + ", ".join(result.standard_conflicts)
        )
    if result.profile_conflicts:
        parts.append(
            "profile_id conflict(s): "
            + ", ".join(result.profile_conflicts)
        )
    if result.framework_conflicts:
        parts.append(
            "framework_id conflict(s): "
            + ", ".join(result.framework_conflicts)
        )
    parts.append("rerun with --overwrite to replace conflicting starter records")
    return "; ".join(parts)
