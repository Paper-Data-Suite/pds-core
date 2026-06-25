"""Basic pds-core CLI behavior tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.cli import main
from tests.cli.conftest import run_cli

def test_console_script_is_declared() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in pyproject
    assert 'pds-core = "pds_core.cli:main"' in pyproject


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["standards", "--help"],
        ["standards", "validate", "--help"],
        ["standards", "validate-file", "--help"],
        ["standards", "menu", "--help"],
        ["standards", "import", "--help"],
        ["standards", "export", "--help"],
        ["standards", "show", "--help"],
        ["standards", "add", "--help"],
        ["standards", "replace", "--help"],
        ["standards", "upsert", "--help"],
        ["standards", "retire", "--help"],
        ["standards", "reactivate", "--help"],
        ["standards", "profile", "create", "--help"],
        ["standards", "profile", "replace", "--help"],
        ["standards", "profile", "add-standard", "--help"],
        ["standards", "profile", "remove-standard", "--help"],
        ["standards", "profile", "validate", "--help"],
        ["standards", "profile", "show", "--help"],
        ["standards", "profile", "import", "--help"],
        ["standards", "profile", "export", "--help"],
    ],
)
def test_help_text_exists_and_distinguishes_ids(
    args: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert "standards" in captured.out
    assert "standard_id" in captured.out or "profile_id" in captured.out
    if "show" in args or "export" in args:
        assert "code" in captured.out or "title" in captured.out
    if "import" in args:
        assert "--replace" in captured.out or "--add" in captured.out
    if "export" in args:
        assert "--overwrite" in captured.out
    if (
        len(args) >= 3
        and args[0] == "standards"
        and args[1] in ("add", "replace", "upsert")
    ):
        assert "--code" in captured.out
        assert "--description" in captured.out
    if any(command in args for command in ("retire", "reactivate")):
        normalized_help = " ".join(captured.out.split())
        assert "non-destructive" in normalized_help
        assert "deletion is not supported" in normalized_help
    if "profile" in args and any(
        command in args
        for command in (
            "create",
            "replace",
            "add-standard",
            "remove-standard",
            "validate",
        )
    ):
        normalized_help = " ".join(captured.out.split())
        assert "profile_id" in normalized_help
        assert "standard_id" in normalized_help
        assert "profile deletion is not supported" in normalized_help


def test_missing_library_loads_as_empty_without_creating_directories(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(tmp_path, "standards", "list", capsys=capsys)

    assert code == 0
    assert out == "No standards found.\n"
    assert err == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (("standards", "subjects"), "No subjects found."),
        (("standards", "sources"), "No sources found."),
        (("standards", "domains"), "No domains found."),
        (("standards", "categories"), "No categories found."),
        (("standards", "profiles"), "No standards profiles found."),
    ],
)
def test_empty_library_messages(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, ...],
    message: str,
) -> None:
    code, out, err = run_cli(tmp_path, *command, capsys=capsys)

    assert code == 0
    assert out == f"{message}\n"
    assert err == ""
