"""Tests for standards workspace path and file helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
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
                domain="Reading Literature",
                tags=("close_reading", "textual_evidence"),
            ),
        ),
        profiles=(
            StandardsProfile(
                profile_id="english_12_njsls",
                standards=(standard_id,),
                title="English 12 NJSLS",
            ),
        ),
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
    assert not (tmp_path / "standards" / "library.json").exists()


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
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "settings").exists()
    assert not (tmp_path / "classes").exists()
    assert not (tmp_path / "assignments").exists()
    assert not (tmp_path / "rosters").exists()
    assert not (tmp_path / "reports").exists()
    assert not (tmp_path / "pds-scoreform").exists()
    assert not (tmp_path / "pds-quillan").exists()


def test_load_workspace_standards_library_returns_empty_library_when_missing(
    tmp_path: Path,
) -> None:
    library = load_workspace_standards_library(tmp_path)

    assert library == StandardsLibrary(standards=(), profiles=())
    assert list(tmp_path.iterdir()) == []


def test_load_workspace_standards_library_reads_canonical_library_file(
    tmp_path: Path,
) -> None:
    library = make_library()
    write_workspace_standards_library(tmp_path, library)

    assert load_workspace_standards_library(tmp_path) == library


def test_workspace_standards_library_round_trip_preserves_profiles(
    tmp_path: Path,
) -> None:
    library = make_library()

    write_workspace_standards_library(tmp_path, library)

    loaded = load_workspace_standards_library(tmp_path)
    assert loaded == library
    assert loaded.standards[0].domain == "Reading Literature"
    assert loaded.standards[0].tags == (
        "close_reading",
        "textual_evidence",
    )
    assert loaded.profiles == library.profiles


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
    path = tmp_path / "standards" / "library.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "standards": [],
                "profiles": [
                    {
                        "profile_id": "english_12_njsls",
                        "standards": ["unknown:standard"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StandardsReadError) as raised:
        load_workspace_standards_library(tmp_path)

    assert raised.value.path == path
