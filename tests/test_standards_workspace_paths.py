"""Tests for standards workspace path and file helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsReadError,
    StandardsWriteError,
    ensure_standards_dir,
    load_workspace_standards_library,
    standards_dir,
    standards_library_path,
    write_workspace_standards_library,
)


def make_library(
    *,
    standard_id: str = "njsls-ela:RL.CR.11-12.1",
    code: str = "RL.CR.11-12.1",
) -> StandardsLibrary:
    return StandardsLibrary(
        standards=(
            StandardDefinition(
                standard_id=standard_id,
                code=code,
                source="NJSLS-ELA",
                short_name="Close Reading Evidence",
                description="Cite strong and thorough textual evidence.",
            ),
        )
    )


def test_standards_dir_returns_canonical_workspace_standards_directory(
    tmp_path: Path,
) -> None:
    assert standards_dir(tmp_path) == tmp_path / "standards"


def test_standards_library_path_returns_canonical_library_json_path(
    tmp_path: Path,
) -> None:
    assert (
        standards_library_path(tmp_path)
        == tmp_path / "standards" / "library.json"
    )


def test_standards_path_helpers_do_not_create_directories(
    tmp_path: Path,
) -> None:
    standards_dir(tmp_path)
    standards_library_path(tmp_path)

    assert not (tmp_path / "standards").exists()


def test_ensure_standards_dir_creates_only_directory(tmp_path: Path) -> None:
    directory = ensure_standards_dir(tmp_path)

    assert directory == tmp_path / "standards"
    assert directory.is_dir()
    assert not (directory / "library.json").exists()


def test_write_workspace_standards_library_writes_canonical_library_file(
    tmp_path: Path,
) -> None:
    write_workspace_standards_library(tmp_path, make_library())

    assert (tmp_path / "standards" / "library.json").is_file()


def test_load_workspace_standards_library_reads_canonical_library_file(
    tmp_path: Path,
) -> None:
    library = make_library()
    write_workspace_standards_library(tmp_path, library)

    assert load_workspace_standards_library(tmp_path) == library


def test_write_workspace_standards_library_preserves_overwrite_behavior(
    tmp_path: Path,
) -> None:
    original = make_library()
    replacement = make_library(
        standard_id="njsls-ela:W.AW.11-12.1",
        code="W.AW.11-12.1",
    )
    write_workspace_standards_library(tmp_path, original)

    with pytest.raises(StandardsWriteError):
        write_workspace_standards_library(tmp_path, replacement)

    write_workspace_standards_library(tmp_path, replacement, overwrite=True)

    assert load_workspace_standards_library(tmp_path) == replacement


def test_load_workspace_standards_library_propagates_read_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(StandardsReadError) as raised:
        load_workspace_standards_library(tmp_path)

    assert raised.value.path == tmp_path / "standards" / "library.json"
