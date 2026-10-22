"""Core #237 Slice 2: H01-H04/H09 pure header contracts, not terminal printing."""

from __future__ import annotations

import contextlib
import io
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

import pds_core.teacher_ui as teacher_ui
from pds_core.teacher_ui import TeacherScreenHeader, render_teacher_header


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (None, "Quillan\nReview Student Work"),
        ("", "Quillan\nReview Student Work"),
        ("   ", "Quillan\nReview Student Work"),
        (
            "English 12 · Period 2",
            "Quillan\nReview Student Work\nEnglish 12 · Period 2",
        ),
    ],
)
def test_exact_plain_header_lines(context: str | None, expected: str) -> None:
    header = TeacherScreenHeader("Quillan", "Review Student Work", context)
    assert render_teacher_header(header) == expected
    assert not expected.endswith("\n")
    assert len(expected.split("\n")) in (2, 3)


def test_green_only_application_name_with_exact_sgr_bytes() -> None:
    header = TeacherScreenHeader(
        "Quillan", "Review Student Work", "English 12 · Period 2"
    )
    assert render_teacher_header(header, ansi=True) == (
        "\x1b[32mQuillan\x1b[0m\nReview Student Work\nEnglish 12 · Period 2"
    )
    assert render_teacher_header(header, ansi=False) == (
        "Quillan\nReview Student Work\nEnglish 12 · Period 2"
    )


@pytest.mark.parametrize(
    "module_name",
    [
        "Paper Data Suite",
        "PDS Core",
        "ScoreForm",
        "Quillan",
        "Concord",
        "Meridian",
        "Vitrine",
        "Portia",
        "New Approved Module",
    ],
)
def test_renderer_accepts_unrestricted_display_names(module_name: str) -> None:
    assert render_teacher_header(TeacherScreenHeader(module_name, "Home")) == (
        f"{module_name}\nHome"
    )


@pytest.mark.parametrize("required_field", ["application_name", "screen_title"])
@pytest.mark.parametrize("invalid", ["", "  ", "\u2003"])
def test_required_labels_must_be_nonblank(required_field: str, invalid: str) -> None:
    kwargs = {"application_name": "Quillan", "screen_title": "Home"}
    kwargs[required_field] = invalid
    with pytest.raises(ValueError, match="blank"):
        TeacherScreenHeader(**kwargs)


@pytest.mark.parametrize(
    "field_name", ["application_name", "screen_title", "context_line"]
)
@pytest.mark.parametrize("invalid", [None, 17, b"Quillan", object()])
def test_invalid_field_types_are_rejected(field_name: str, invalid: object) -> None:
    if invalid is None and field_name == "context_line":
        assert TeacherScreenHeader("Quillan", "Home", None).context_line is None
        return
    kwargs: dict[str, object] = {
        "application_name": "Quillan",
        "screen_title": "Home",
        "context_line": "English 12",
    }
    kwargs[field_name] = invalid
    with pytest.raises(TypeError, match=field_name):
        TeacherScreenHeader(**cast(dict[str, str], kwargs))


@pytest.mark.parametrize(
    "control",
    [
        "\n",
        "\r",
        "\x00",
        "\x1b",
        "\t",
        "\v",
        "\x7f",
        "\x85",
        "\u2028",
        "\u2029",
        "\u202e",
        "\u2066",
        "\ufeff",
        "\ud800",
    ],
)
@pytest.mark.parametrize(
    "field_name", ["application_name", "screen_title", "context_line"]
)
def test_control_codes_and_unicode_separators_rejected(
    field_name: str, control: str
) -> None:
    kwargs = {
        "application_name": "Quillan",
        "screen_title": "Home",
        "context_line": "English 12",
    }
    kwargs[field_name] = f"Before{control}After"
    with pytest.raises(ValueError, match="control or line separator"):
        TeacherScreenHeader(**kwargs)


def test_header_is_frozen_and_slotted() -> None:
    header = TeacherScreenHeader("Quillan", "Home")
    with pytest.raises(FrozenInstanceError):
        header.screen_title = "Changed"  # type: ignore[misc]
    assert not hasattr(header, "__dict__")


@pytest.mark.parametrize("invalid", [None, "Quillan", {"application_name": "Quillan"}])
def test_renderer_rejects_non_header_without_output(invalid: object) -> None:
    with pytest.raises(TypeError, match="TeacherScreenHeader"):
        render_teacher_header(cast(TeacherScreenHeader, invalid))


@pytest.mark.parametrize("invalid", [None, 1, "yes", object()])
def test_renderer_requires_exact_boolean_ansi(invalid: object) -> None:
    with pytest.raises(TypeError, match="ansi"):
        render_teacher_header(
            TeacherScreenHeader("Quillan", "Home"), ansi=cast(bool, invalid)
        )


def test_unicode_display_is_preserved_without_normalization_or_escaping() -> None:
    header = TeacherScreenHeader("Portia", "Résumé — Révision", "Español · 12º")
    assert render_teacher_header(header) == "Portia\nRésumé — Révision\nEspañol · 12º"


def test_renderer_is_pure_and_writes_nothing_to_global_streams() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        header = TeacherScreenHeader("Quillan", "Review", "English 12")
        assert render_teacher_header(header, ansi=True)
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_only_pure_public_symbols_are_exported_in_slice_2() -> None:
    assert set(teacher_ui.__all__) == {"TeacherScreenHeader", "render_teacher_header"}
    assert not hasattr(teacher_ui, "print_teacher_header")
