"""Standards definition workflow tests."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

import pytest

from pds_core.cli_support import screen
from pds_core.standards import load_standards_library
from tests.cli_menu.conftest import library_file, run_menu


def test_menu_add_standard_normalizes_common_dash_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = "\n".join(
        (
            "1",
            "4",
            "njsls-ela:L.VI.11\u201312.4",
            "L.VI.11-12.4",
            "",
            "Demonstrate understanding of figurative language.",
            "NJSLS-ELA 2023",
            "English Language Arts",
            "English 12",
            "Language",
            "no",
            "YES",
            "",
            "5",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Created standard njsls-ela:L.VI.11-12.4." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert library.standards[0].standard_id == "njsls-ela:L.VI.11-12.4"
    assert library.standards[0].description == (
        "Demonstrate understanding of figurative language."
    )


def test_menu_add_standard_creates_subpart_definitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = "\n".join(
        (
            "1",
            "4",
            "njsls-ela:L.VI.11-12.4",
            "L.VI.11-12.4",
            "Figurative Language and Word Relationships",
            "Demonstrate understanding of figurative language.",
            "NJSLS-ELA 2023",
            "English Language Arts",
            "English 12",
            "Language",
            "YES",
            "A",
            "Figures of Speech",
            "Interpret figures of speech in context.",
            "",
            "YES",
            "",
            "5",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert "Review Standard" in out
    assert "Subparts:" in out
    assert "L.VI.11-12.4.A - Figures of Speech" in out
    assert "Created standard njsls-ela:L.VI.11-12.4." in out
    assert "Created standard njsls-ela:L.VI.11-12.4.A." in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert tuple(definition.standard_id for definition in library.standards) == (
        "njsls-ela:L.VI.11-12.4",
        "njsls-ela:L.VI.11-12.4.A",
    )
    assert library.standards[1].description == (
        "Interpret figures of speech in context."
    )


def test_add_standard_clears_between_major_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mark_clear(stdout: TextIO) -> None:
        print("[clear]", file=stdout)

    monkeypatch.setattr(screen, "clear_screen", mark_clear)
    inputs = "\n".join(
        (
            "1",
            "4",
            "njsls-ela:L.VI.11-12.4",
            "L.VI.11-12.4",
            "Figurative Language and Word Relationships",
            "Demonstrate understanding of figurative language.",
            "NJSLS-ELA 2023",
            "English Language Arts",
            "English 12",
            "Language",
            "no",
            "YES",
            "",
            "5",
            "5",
            "",
        )
    )

    code, out, err = run_menu(tmp_path, monkeypatch, capsys, inputs)

    assert code == 0
    assert err == ""
    for prompt in (
        "Enter Durable Standard ID.",
        "Enter Display Code.",
        "Enter Short Name.",
        "Enter Standard Description.",
        "Enter Source.",
        "Enter Subject.",
        "Enter Course.",
        "Enter Domain or Category.",
    ):
        assert f"[clear]\nPDS Core\n\nAdd Standard\n\n{prompt}" in out
    assert "[clear]\nPDS Core\n\nReview Standard" in out
