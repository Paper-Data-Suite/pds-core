"""Tests for explicit-path standards library JSON file helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsReadError,
    StandardsWriteError,
    load_standards_library,
    write_standards_library,
)


def make_library(
    *,
    standard_id: str = "njsls-ela:RL.CR.11-12.1",
    code: str = "RL.CR.11-12.1",
) -> StandardsLibrary:
    definition = StandardDefinition(
        standard_id=standard_id,
        code=code,
        source="NJSLS-ELA",
        short_name="Close Reading Evidence",
        description="Cite strong and thorough textual evidence.",
        subject="English Language Arts",
        category_path=(
            "English Language Arts",
            "Reading Literature",
            "Close Reading",
        ),
    )
    profile = StandardsProfile(
        profile_id="english_12_njsls",
        standards=(standard_id,),
        subject="English Language Arts",
    )
    return StandardsLibrary(
        standards=(definition,),
        profiles=(profile,),
    )


def test_load_standards_library_reads_valid_json_file(tmp_path: Path) -> None:
    path = tmp_path / "library.json"
    path.write_text(
        json.dumps(
            {
                "standards": [
                    {
                        "standard_id": "njsls-ela:RL.CR.11-12.1",
                        "code": "RL.CR.11-12.1",
                        "source": "NJSLS-ELA",
                        "short_name": "Close Reading Evidence",
                        "description": "Cite strong and thorough evidence.",
                        "category_path": [
                            "English Language Arts",
                            "Reading Literature",
                            "Close Reading",
                        ],
                    }
                ],
                "profiles": [
                    {
                        "profile_id": "english_12_njsls",
                        "standards": ["njsls-ela:RL.CR.11-12.1"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    library = load_standards_library(path)

    assert isinstance(library, StandardsLibrary)
    assert library.standards[0].code == "RL.CR.11-12.1"
    assert library.standards[0].category_path == (
        "English Language Arts",
        "Reading Literature",
        "Close Reading",
    )
    assert library.profiles[0].standards == (
        "njsls-ela:RL.CR.11-12.1",
    )


def test_write_standards_library_writes_readable_json_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "library.json"

    write_standards_library(path, make_library())

    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    assert content.endswith("\n")
    assert set(data) == {"profiles", "standards"}
    assert isinstance(data["standards"][0]["category_path"], list)
    assert isinstance(data["profiles"][0]["standards"], list)


def test_standards_library_file_round_trips(tmp_path: Path) -> None:
    library = make_library()
    path = tmp_path / "library.json"

    write_standards_library(path, library)

    assert load_standards_library(path) == library


def test_load_standards_library_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(StandardsReadError) as raised:
        load_standards_library(path)

    assert raised.value.path == path


def test_load_standards_library_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "library.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(StandardsReadError, match="invalid JSON"):
        load_standards_library(path)


@pytest.mark.parametrize("content", ["[]", '"not a library"'])
def test_load_standards_library_rejects_non_mapping_json(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "library.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(StandardsReadError, match="top-level.*mapping"):
        load_standards_library(path)


def test_load_standards_library_wraps_validation_errors(
    tmp_path: Path,
) -> None:
    path = tmp_path / "library.json"
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

    with pytest.raises(
        StandardsReadError,
        match="unknown standard IDs",
    ):
        load_standards_library(path)


def test_write_standards_library_rejects_existing_file_by_default(
    tmp_path: Path,
) -> None:
    path = tmp_path / "library.json"
    path.write_text("original", encoding="utf-8")

    with pytest.raises(StandardsWriteError) as raised:
        write_standards_library(path, make_library())

    assert raised.value.path == path
    assert path.read_text(encoding="utf-8") == "original"


def test_write_standards_library_allows_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "library.json"
    original = make_library()
    replacement = make_library(
        standard_id="njsls-ela:W.AW.11-12.1",
        code="W.AW.11-12.1",
    )
    write_standards_library(path, original)

    write_standards_library(path, replacement, overwrite=True)

    assert load_standards_library(path) == replacement


def test_write_standards_library_creates_parent_directories(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "standards" / "library.json"

    write_standards_library(path, make_library())

    assert load_standards_library(path) == make_library()


def test_write_standards_library_wraps_invalid_library(
    tmp_path: Path,
) -> None:
    path = tmp_path / "library.json"

    with pytest.raises(StandardsWriteError, match="StandardsLibrary"):
        write_standards_library(path, cast(Any, object()))

    assert not path.exists()


def test_write_standards_library_preserves_target_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "library.json"
    path.write_text("original", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("pds_core.standards.os.replace", fail_replace)

    with pytest.raises(StandardsWriteError, match="replace failed"):
        write_standards_library(path, make_library(), overwrite=True)

    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".library.json.*.tmp")) == []
