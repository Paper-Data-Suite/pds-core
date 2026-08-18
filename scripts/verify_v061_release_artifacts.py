"""Inspect pds-core v0.6.1 distributions and grouping-signal fixture asset."""

from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
import zipfile
from email import message_from_bytes
from pathlib import Path

VERSION = "0.6.1"
WHEEL_NAME = "pds_core-0.6.1-py3-none-any.whl"
SDIST_NAME = "pds_core-0.6.1.tar.gz"
FIXTURE_ARCHIVE_NAME = "pds-core-0.6.1-grouping-signal-fixtures.zip"
REQUIRED_MODULES = {
    "pds_core/grouping_signals.py",
    "pds_core/grouping_signal_csv.py",
    "pds_core/grouping_signal_storage.py",
    "pds_core/grouping_signal_diagnostics.py",
}
SIBLING_PREFIXES = (
    "scoreform/",
    "quillan/",
    "concord/",
    "portia/",
    "meridian/",
    "paper_data_suite/",
)
WORKSPACE_PREFIXES = ("classes/", "exchange/", "registry/", "scans/", "settings/")


def _assert_metadata(data: bytes, source: str) -> None:
    metadata = message_from_bytes(data)
    if metadata.get("Name") != "pds-core":
        raise ValueError(f"{source}: package name is not pds-core.")
    if metadata.get("Version") != VERSION:
        raise ValueError(f"{source}: package version is not {VERSION}.")
    if metadata.get("Requires-Python") != ">=3.11":
        raise ValueError(f"{source}: Requires-Python must be >=3.11.")
    requires_dist = metadata.get_all("Requires-Dist", [])
    unconditional = [
        requirement
        for requirement in requires_dist
        if 'extra == "dev"' not in requirement and "extra == 'dev'" not in requirement
    ]
    if unconditional:
        raise ValueError(
            f"{source}: unexpected runtime dependencies: {unconditional!r}"
        )


def verify_wheel(path: Path) -> None:
    if path.name != WHEEL_NAME:
        raise ValueError(f"Unexpected wheel filename: {path.name}")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError("Wheel must contain exactly one METADATA file.")
        _assert_metadata(archive.read(metadata_paths[0]), "wheel")
        missing = sorted(REQUIRED_MODULES - names)
        if missing:
            raise ValueError(f"Wheel is missing grouping-signal modules: {missing}")
        if not any(
            name.startswith("pds_core/starter_data/standards/") and name.endswith(".json")
            for name in names
        ):
            raise ValueError("Wheel is missing starter standards package data.")
        if any(name.startswith("tests/") for name in names):
            raise ValueError("Wheel unexpectedly contains tests/.")
        for prefix in SIBLING_PREFIXES + WORKSPACE_PREFIXES:
            if any(name.startswith(prefix) for name in names):
                raise ValueError(f"Wheel unexpectedly contains {prefix}")
        if any("/.git/" in f"/{name}" or "__pycache__" in name for name in names):
            raise ValueError("Wheel contains Git/cache residue.")

        entry_points_paths = [
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(entry_points_paths) != 1:
            raise ValueError("Wheel must contain exactly one entry_points.txt.")
        entry_points = archive.read(entry_points_paths[0]).decode("utf-8")
        for required in (
            "pds-core = pds_core.cli:main",
            "core = pds_core.core_menu:main",
        ):
            if required not in entry_points:
                raise ValueError(f"Wheel is missing console script: {required}")


def verify_sdist(path: Path) -> None:
    if path.name != SDIST_NAME:
        raise ValueError(f"Unexpected sdist filename: {path.name}")
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        roots = {name.split("/", maxsplit=1)[0] for name in names if name}
        if len(roots) != 1:
            raise ValueError("sdist must contain exactly one archive root.")
        root = next(iter(roots))
        pkg_info_name = f"{root}/PKG-INFO"
        try:
            pkg_info_member = archive.getmember(pkg_info_name)
        except KeyError as error:
            raise ValueError("sdist is missing PKG-INFO.") from error
        extracted = archive.extractfile(pkg_info_member)
        if extracted is None:
            raise ValueError("Could not read sdist PKG-INFO.")
        _assert_metadata(extracted.read(), "sdist")

        for required in REQUIRED_MODULES:
            if f"{root}/{required}" not in names:
                raise ValueError(f"sdist is missing {required}.")
        prohibited_components = {".git", ".venv", "__pycache__", ".pytest_cache"}
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


def _parse_fixture_manifest(data: bytes) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, line in enumerate(data.decode("ascii").splitlines(), start=1):
        try:
            digest, relative_path = line.split("  ", maxsplit=1)
        except ValueError as error:
            raise ValueError(
                f"Malformed fixture checksum line {line_number}."
            ) from error
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"Malformed fixture digest at line {line_number}.")
        if relative_path in entries:
            raise ValueError(f"Duplicate fixture checksum path {relative_path!r}.")
        entries[relative_path] = digest
    return entries


def verify_fixture_archive(path: Path) -> None:
    if path.name != FIXTURE_ARCHIVE_NAME:
        raise ValueError(f"Unexpected fixture archive filename: {path.name}")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {info.filename for info in infos}
        prefix = "grouping_signals_v1/"
        if any(not name.startswith(prefix) for name in names):
            raise ValueError("Fixture archive contains an unexpected top-level path.")
        if any(".." in Path(name).parts or Path(name).is_absolute() for name in names):
            raise ValueError("Fixture archive contains unsafe paths.")
        if any("__pycache__" in name or ".pytest_cache" in name for name in names):
            raise ValueError("Fixture archive contains cache residue.")

        manifest_name = prefix + "SHA256SUMS.txt"
        if manifest_name not in names:
            raise ValueError("Fixture archive is missing SHA256SUMS.txt.")
        entries = _parse_fixture_manifest(archive.read(manifest_name))
        actual_payloads = {
            name[len(prefix) :]
            for name in names
            if name != manifest_name and not name.endswith("/")
        }
        if set(entries) != actual_payloads:
            raise ValueError("Fixture checksum manifest does not match archive payloads.")
        for relative_path, expected in entries.items():
            actual = hashlib.sha256(archive.read(prefix + relative_path)).hexdigest()
            if actual != expected:
                raise ValueError(f"Fixture checksum mismatch: {relative_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--fixtures-zip", type=Path, required=True)
    args = parser.parse_args()

    verify_wheel(args.wheel)
    verify_sdist(args.sdist)
    verify_fixture_archive(args.fixtures_zip)
    print("pds-core v0.6.1 release artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
