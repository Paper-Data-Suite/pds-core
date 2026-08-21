"""Inspect exact pds-core v0.6.2 wheel and source-distribution artifacts."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from dataclasses import dataclass
from email import message_from_bytes
from pathlib import Path
from typing import Final

VERSION: Final[str] = "0.6.2"
WHEEL_NAME: Final[str] = "pds_core-0.6.2-py3-none-any.whl"
SDIST_NAME: Final[str] = "pds_core-0.6.2.tar.gz"
REQUIRED_MODULES: Final[frozenset[str]] = frozenset(
    {
        "pds_core/grouping_signals.py",
        "pds_core/grouping_signal_csv.py",
        "pds_core/grouping_signal_storage.py",
        "pds_core/grouping_signal_diagnostics.py",
        "pds_core/roster_imports.py",
        "pds_core/provider_diagnostics.py",
        "pds_core/module_operations.py",
        "pds_core/cli_support/roster_imports.py",
    }
)
CORE_CONSOLE_SCRIPTS: Final[dict[str, str]] = {
    "pds-core": "pds_core.cli:main",
    "core": "pds_core.core_menu:main",
}
SIBLING_PREFIXES: Final[tuple[str, ...]] = (
    "scoreform/",
    "quillan/",
    "concord/",
    "portia/",
    "meridian/",
    "vitrine/",
    "paper_data_suite/",
)
WORKSPACE_PREFIXES: Final[tuple[str, ...]] = (
    "classes/",
    "exchange/",
    "registry/",
    "scans/",
    "settings/",
)


@dataclass(frozen=True, slots=True)
class ReleaseArtifactIdentity:
    """Bounded identity for one inspected release distribution."""

    filename: str
    distribution: str
    version: str
    requires_python: str


def _assert_metadata(data: bytes, source: str) -> ReleaseArtifactIdentity:
    metadata = message_from_bytes(data)
    distribution = metadata.get("Name")
    version = metadata.get("Version")
    requires_python = metadata.get("Requires-Python")
    if distribution != "pds-core":
        raise ValueError(f"{source}: package name is not pds-core.")
    if version != VERSION:
        raise ValueError(f"{source}: package version is not {VERSION}.")
    if requires_python != ">=3.11":
        raise ValueError(f"{source}: Requires-Python must be >=3.11.")

    runtime_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if 'extra == "dev"' not in requirement and "extra == 'dev'" not in requirement
    ]
    if runtime_requirements:
        raise ValueError(
            f"{source}: unexpected runtime dependencies: {runtime_requirements!r}"
        )

    if metadata.get("License-Expression") != "MIT":
        raise ValueError(f"{source}: License-Expression must be MIT.")
    license_files = metadata.get_all("License-File", [])
    if "LICENSE" not in license_files:
        raise ValueError(f"{source}: LICENSE must be declared as License-File.")

    return ReleaseArtifactIdentity(
        filename="",
        distribution=distribution,
        version=version,
        requires_python=requires_python,
    )


def _parse_console_scripts(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("wheel entry_points.txt must be UTF-8.") from error
    current_group: str | None = None
    scripts: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1]
            continue
        if current_group != "console_scripts" or "=" not in line:
            continue
        name, target = (part.strip() for part in line.split("=", maxsplit=1))
        if not name or not target:
            raise ValueError("wheel contains an empty console-script entry.")
        if name in scripts:
            raise ValueError(f"wheel contains duplicate console script {name!r}.")
        scripts[name] = target
    return scripts


def verify_wheel(path: Path) -> ReleaseArtifactIdentity:
    """Verify exact v0.6.2 wheel identity and required packaged surfaces."""
    candidate = path.resolve()
    if candidate.name != WHEEL_NAME:
        raise ValueError(f"Unexpected wheel filename: {candidate.name}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)

    try:
        with zipfile.ZipFile(candidate) as archive:
            names = set(archive.namelist())
            metadata_paths = [
                name for name in names if name.endswith(".dist-info/METADATA")
            ]
            entry_points_paths = [
                name for name in names if name.endswith(".dist-info/entry_points.txt")
            ]
            if len(metadata_paths) != 1:
                raise ValueError("Wheel must contain exactly one METADATA file.")
            if len(entry_points_paths) != 1:
                raise ValueError("Wheel must contain exactly one entry_points.txt file.")

            identity = _assert_metadata(archive.read(metadata_paths[0]), "wheel")
            try:
                init_text = archive.read("pds_core/__init__.py").decode("utf-8")
            except (KeyError, UnicodeDecodeError) as error:
                raise ValueError("Wheel is missing a readable pds_core/__init__.py.") from error
            if f'__version__ = "{VERSION}"' not in init_text:
                raise ValueError("Wheel runtime version does not match release metadata.")

            missing = sorted(REQUIRED_MODULES - names)
            if missing:
                raise ValueError(f"Wheel is missing required Core modules: {missing}")

            if not any(
                name.startswith("pds_core/starter_data/standards/")
                and name.endswith(".json")
                for name in names
            ):
                raise ValueError("Wheel is missing starter standards package data.")

            license_paths = [
                name
                for name in names
                if name.endswith(".dist-info/licenses/LICENSE")
            ]
            if len(license_paths) != 1:
                raise ValueError("Wheel must contain exactly one packaged LICENSE file.")

            if any(name.startswith("tests/") for name in names):
                raise ValueError("Wheel unexpectedly contains tests/.")
            for prefix in SIBLING_PREFIXES + WORKSPACE_PREFIXES:
                if any(name.startswith(prefix) for name in names):
                    raise ValueError(f"Wheel unexpectedly contains {prefix}")
            if any(
                "/.git/" in f"/{name}" or "__pycache__" in name or name.endswith(".pyc")
                for name in names
            ):
                raise ValueError("Wheel contains Git/cache/bytecode residue.")

            scripts = _parse_console_scripts(archive.read(entry_points_paths[0]))
            if scripts != CORE_CONSOLE_SCRIPTS:
                raise ValueError(
                    "Wheel console scripts do not match the exact Core release surface."
                )
    except zipfile.BadZipFile as error:
        raise ValueError("Wheel is not a readable ZIP archive.") from error

    return ReleaseArtifactIdentity(
        filename=candidate.name,
        distribution=identity.distribution,
        version=identity.version,
        requires_python=identity.requires_python,
    )


def verify_sdist(path: Path) -> ReleaseArtifactIdentity:
    """Verify exact v0.6.2 source-distribution identity and required source files."""
    candidate = path.resolve()
    if candidate.name != SDIST_NAME:
        raise ValueError(f"Unexpected sdist filename: {candidate.name}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)

    try:
        with tarfile.open(candidate, mode="r:gz") as archive:
            members = archive.getmembers()
            names = {member.name for member in members}
            roots = {name.split("/", maxsplit=1)[0] for name in names if name}
            if len(roots) != 1:
                raise ValueError("sdist must contain exactly one archive root.")
            archive_root = next(iter(roots))
            if archive_root != f"pds_core-{VERSION}":
                raise ValueError(
                    f"Unexpected sdist archive root: {archive_root!r}."
                )

            pkg_info_name = f"{archive_root}/PKG-INFO"
            try:
                pkg_info_member = archive.getmember(pkg_info_name)
            except KeyError as error:
                raise ValueError("sdist is missing PKG-INFO.") from error
            extracted = archive.extractfile(pkg_info_member)
            if extracted is None:
                raise ValueError("Could not read sdist PKG-INFO.")
            identity = _assert_metadata(extracted.read(), "sdist")

            init_name = f"{archive_root}/pds_core/__init__.py"
            try:
                init_member = archive.getmember(init_name)
            except KeyError as error:
                raise ValueError("sdist is missing pds_core/__init__.py.") from error
            init_file = archive.extractfile(init_member)
            if init_file is None:
                raise ValueError("Could not read sdist pds_core/__init__.py.")
            try:
                init_text = init_file.read().decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("sdist pds_core/__init__.py must be UTF-8.") from error
            if f'__version__ = "{VERSION}"' not in init_text:
                raise ValueError("sdist runtime version does not match release metadata.")

            for required in REQUIRED_MODULES:
                if f"{archive_root}/{required}" not in names:
                    raise ValueError(f"sdist is missing {required}.")
            if f"{archive_root}/LICENSE" not in names:
                raise ValueError("sdist is missing LICENSE.")
            if not any(
                name.startswith(
                    f"{archive_root}/pds_core/starter_data/standards/"
                )
                and name.endswith(".json")
                for name in names
            ):
                raise ValueError("sdist is missing starter standards package data.")

            prohibited_components = {
                ".git",
                ".venv",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
            }
            for name in names:
                parts = Path(name).parts
                if any(part in prohibited_components for part in parts):
                    raise ValueError(f"sdist contains prohibited residue: {name}")
                if len(parts) > 1 and parts[1] == "dist":
                    raise ValueError(f"sdist recursively contains dist output: {name}")
                if len(parts) > 1 and parts[1] in {
                    "classes",
                    "exchange",
                    "registry",
                    "scans",
                    "settings",
                }:
                    raise ValueError(f"sdist contains workspace residue: {name}")
    except tarfile.TarError as error:
        raise ValueError("sdist is not a readable gzip tar archive.") from error

    return ReleaseArtifactIdentity(
        filename=candidate.name,
        distribution=identity.distribution,
        version=identity.version,
        requires_python=identity.requires_python,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args()

    verify_wheel(args.wheel)
    verify_sdist(args.sdist)
    print("pds-core v0.6.2 release artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
