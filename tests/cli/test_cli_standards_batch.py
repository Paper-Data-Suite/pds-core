"""Tests for atomic standards batch and profile membership CLI routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.cli import main
from pds_core.cli_support.standards_io import load_standard_definitions_request
from pds_core.standards import (
    StandardsReadError,
    StandardsWriteError,
    load_workspace_standards_library,
    write_workspace_standards_library,
)
from tests.cli.conftest import make_cli_library, run_cli


def request_data() -> dict[str, object]:
    return {
        "standards": [
            {
                "standard_id": "local-reading:close_reading",
                "code": "CR.1",
                "source": "Local Reading",
                "short_name": "Close Reading",
                "description": "Use evidence from a text.",
            },
            {
                "standard_id": "local-reading:close_reading.A",
                "code": "CR.1.A",
                "source": "Local Reading",
                "short_name": "Select Evidence",
                "description": "Select supporting evidence.",
            },
        ]
    }


def write_request(path: Path, data: object | None = None) -> None:
    path.write_text(json.dumps(request_data() if data is None else data), encoding="utf-8")


def test_request_reader_validates_shape_and_applies_optional_defaults(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    write_request(path)
    definitions = load_standard_definitions_request(path)
    assert tuple(item.standard_id for item in definitions) == (
        "local-reading:close_reading",
        "local-reading:close_reading.A",
    )
    assert definitions[0].category_path == ()
    assert definitions[0].tags == ()
    assert definitions[0].active is True
    assert definitions[0].available_modules == ()
    assert definitions[0].subject is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "top-level"),
        ({"standards": [], "profiles": []}, "unknown top-level"),
        ({}, "missing required"),
        ({"standards": "bad"}, "must be an array"),
        ({"standards": []}, "must not be empty"),
        ({"standards": ["bad"]}, "must be an object"),
        ({"standards": [{"unknown": True}]}, "unknown key"),
        ({"standards": [{"standard_id": "only"}]}, "missing required"),
    ],
)
def test_request_reader_rejects_invalid_shapes(
    tmp_path: Path, data: object, message: str
) -> None:
    path = tmp_path / "request.json"
    write_request(path, data)
    with pytest.raises(StandardsReadError, match=message):
        load_standard_definitions_request(path)
    assert not (tmp_path / "standards").exists()


def test_request_reader_handles_file_failures_without_artifacts(tmp_path: Path) -> None:
    with pytest.raises(StandardsReadError):
        load_standard_definitions_request(tmp_path / "missing.json")
    with pytest.raises(StandardsReadError):
        load_standard_definitions_request(tmp_path)
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(StandardsReadError, match="invalid JSON"):
        load_standard_definitions_request(malformed)
    invalid_utf8 = tmp_path / "invalid.json"
    invalid_utf8.write_bytes(b"\xff")
    with pytest.raises(StandardsReadError):
        load_standard_definitions_request(invalid_utf8)
    assert not (tmp_path / "standards").exists()


def test_add_batch_cli_succeeds_once_and_reports_count_and_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "request.json"
    write_request(path)
    calls = 0
    real_writer = write_workspace_standards_library

    def counting_writer(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        real_writer(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "pds_core.cli_support.standards_mutation.write_workspace_standards_library",
        counting_writer,
    )
    code, out, err = run_cli(tmp_path, "standards", "add-batch", str(path), capsys=capsys)
    assert code == 0
    assert out == f"Added 2 standards from {path}.\n"
    assert err == ""
    assert calls == 1
    assert tuple(
        item.standard_id for item in load_workspace_standards_library(tmp_path).standards
    ) == ("local-reading:close_reading", "local-reading:close_reading.A")


@pytest.mark.parametrize(
    ("command", "arguments", "expected_membership", "expected_output"),
    [
        (
            "add-standards",
            ("local-misc:unfiled", "njsls-ela:RI.CR.11-12.1"),
            (
                "local-writing:evidence_explanation",
                "local-misc:unfiled",
                "njsls-ela:RI.CR.11-12.1",
            ),
            "Added 2 standards to profile english_12_local.\n",
        ),
        (
            "remove-standards",
            ("njsls-ela:RI.CR.11-12.1", "njsls-ela:RL.CR.11-12.1"),
            (),
            "Removed 2 standards from profile english_12_njsls.\n",
        ),
        (
            "set-standards",
            (
                "--standard",
                "local-misc:unfiled",
                "--standard",
                "njsls-ela:RL.CR.11-12.1",
            ),
            ("local-misc:unfiled", "njsls-ela:RL.CR.11-12.1"),
            "Set profile english_12_njsls membership to 2 standards.\n",
        ),
        (
            "set-standards",
            (),
            (),
            "Set profile english_12_njsls membership to 0 standards.\n",
        ),
    ],
)
def test_profile_batch_cli_routes_preserve_metadata_and_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    arguments: tuple[str, ...],
    expected_membership: tuple[str, ...],
    expected_output: str,
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    profile_id = "english_12_local" if command == "add-standards" else "english_12_njsls"
    before = load_workspace_standards_library(tmp_path)
    old_profile = next(item for item in before.profiles if item.profile_id == profile_id)
    code, out, err = run_cli(
        tmp_path, "standards", "profile", command, profile_id, *arguments, capsys=capsys
    )
    assert code == 0
    assert out == expected_output
    assert err == ""
    after = load_workspace_standards_library(tmp_path)
    new_profile = next(item for item in after.profiles if item.profile_id == profile_id)
    assert new_profile.standards == expected_membership
    assert new_profile.title == old_profile.title
    assert new_profile.description == old_profile.description
    assert new_profile.subject == old_profile.subject
    assert new_profile.course == old_profile.course
    assert new_profile.source == old_profile.source


def test_batch_cli_prewrite_failure_has_no_output_write_or_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def counting_writer(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(
        "pds_core.cli_support.standards_mutation.write_workspace_standards_library",
        counting_writer,
    )
    code, out, err = run_cli(
        tmp_path, "standards", "add-batch", str(tmp_path / "missing.json"), capsys=capsys
    )
    assert code == 1
    assert out == ""
    assert err.startswith("Error: ")
    assert calls == 0
    assert not (tmp_path / "standards").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ("standards", "add-batch", "{request}"),
        (
            "standards",
            "profile",
            "add-standards",
            "english_12_local",
            "local-misc:unfiled",
        ),
        (
            "standards",
            "profile",
            "remove-standards",
            "english_12_njsls",
            "njsls-ela:RI.CR.11-12.1",
        ),
        (
            "standards",
            "profile",
            "set-standards",
            "english_12_njsls",
            "--standard",
            "local-misc:unfiled",
        ),
    ],
)
def test_batch_cli_write_failure_attempts_once_and_preserves_existing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    canonical = tmp_path / "standards" / "library.json"
    before = canonical.read_bytes()
    request = tmp_path / "request.json"
    write_request(request)
    calls = 0

    def failing_writer(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise StandardsWriteError(canonical, "synthetic failure")

    monkeypatch.setattr(
        "pds_core.cli_support.standards_mutation.write_workspace_standards_library",
        failing_writer,
    )
    resolved = tuple(str(request) if item == "{request}" else item for item in arguments)
    code = main(["--workspace", str(tmp_path), *resolved])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "synthetic failure" in captured.err
    assert calls == 1
    assert canonical.read_bytes() == before
    assert not tuple(canonical.parent.glob("*.tmp"))


def test_real_writer_replace_failure_preserves_file_and_cleans_temp_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    canonical = tmp_path / "standards" / "library.json"
    before = canonical.read_bytes()

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr("pds_core.standards.os.replace", fail_replace)
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "set-standards",
        "english_12_njsls",
        "--standard",
        "local-misc:unfiled",
        capsys=capsys,
    )
    assert code == 1
    assert out == ""
    assert "synthetic replace failure" in err
    assert canonical.read_bytes() == before
    assert not tuple(canonical.parent.glob(".*.tmp"))


@pytest.mark.parametrize(
    "args",
    [
        ("standards", "add-batch", "--help"),
        ("standards", "profile", "add-standards", "--help"),
        ("standards", "profile", "remove-standards", "--help"),
        ("standards", "profile", "set-standards", "--help"),
    ],
)
def test_batch_cli_help_exits_zero(args: tuple[str, ...]) -> None:
    assert main(args) == 0


@pytest.mark.parametrize(
    "args",
    [
        ("standards", "add-batch"),
        ("standards", "profile", "add-standards", "profile"),
        ("standards", "profile", "remove-standards", "profile"),
        ("standards", "profile", "set-standards"),
        ("standards", "profile", "set-standards", "profile", "--unknown"),
    ],
)
def test_batch_cli_parser_failures_exit_two(args: tuple[str, ...]) -> None:
    assert main(args) == 2
