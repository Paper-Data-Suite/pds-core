"""Regression checks for installable release metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pds_core


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


def project_metadata() -> dict[str, object]:
    with PYPROJECT_PATH.open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)


def test_release_version_declarations_match_v050() -> None:
    metadata = project_metadata()
    project = metadata["project"]

    assert isinstance(project, dict)
    assert project["version"] == "0.5.0"
    assert pds_core.__version__ == "0.5.0"
    assert pds_core.__version__ == project["version"]


def test_project_identity_and_runtime_metadata_remain_stable() -> None:
    project = project_metadata()["project"]

    assert isinstance(project, dict)
    assert project["name"] == "pds-core"
    assert project["requires-python"] == ">=3.11"
    assert project["dependencies"] == []


def test_setuptools_build_backend_is_explicit() -> None:
    build_system = project_metadata()["build-system"]

    assert isinstance(build_system, dict)
    assert build_system["build-backend"] == "setuptools.build_meta"
    assert "setuptools>=61" in build_system["requires"]


def test_console_scripts_remain_stable() -> None:
    project = project_metadata()["project"]

    assert isinstance(project, dict)
    scripts = project["scripts"]
    assert isinstance(scripts, dict)
    assert scripts["pds-core"] == "pds_core.cli:main"
    assert scripts["core"] == "pds_core.core_menu:main"


def test_starter_standards_remain_package_data() -> None:
    tool = project_metadata()["tool"]

    assert isinstance(tool, dict)
    setuptools = tool["setuptools"]
    assert isinstance(setuptools, dict)
    package_data = setuptools["package-data"]
    assert isinstance(package_data, dict)
    assert package_data["pds_core"] == ["starter_data/standards/*.json"]
