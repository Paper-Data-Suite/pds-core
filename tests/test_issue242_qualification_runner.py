"""Regression tests for the Git-tracked Core #242 qualification runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import qualify_core242_candidate as runner

SOURCE = b"import os\n\ndef answer( ):\n    return 42\n"
NAME = "example.py"


@pytest.fixture
def working(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["F"]\n', encoding="utf-8"
    )

    def original(*args: str) -> bytes:
        assert args == ("git", "show", f"HEAD:{NAME}")
        return SOURCE

    monkeypatch.setattr(runner, "capture", original)
    return tmp_path / NAME


def test_safe_fix_reproduces_format_and_unused_import_removal(
    working: Path,
) -> None:
    formatted, fixed, final = runner.ruff_states(NAME, SOURCE)
    assert b"import os" in formatted
    assert b"import os" not in fixed
    assert b"import os" not in final
    assert b"def answer():" in final
    assert b"return 42" in final
    working.write_bytes(final)
    runner.verify_ruff_only({NAME})


def test_interrupted_formatting_is_recoverable_but_not_publishable(
    working: Path,
) -> None:
    formatted, _, final = runner.ruff_states(NAME, SOURCE)
    assert formatted != final
    working.write_bytes(formatted.replace(b"\n", b"\r\n"))
    runner.verify_ruff_only({NAME}, recovering=True)
    with pytest.raises(SystemExit, match="beyond permitted Ruff fixes"):
        runner.verify_ruff_only({NAME})


def test_interrupted_safe_fix_is_recoverable(working: Path) -> None:
    _, fixed, _ = runner.ruff_states(NAME, SOURCE)
    working.write_bytes(fixed)
    runner.verify_ruff_only({NAME}, recovering=True)


def test_unrelated_edit_is_not_recoverable(working: Path) -> None:
    _, _, final = runner.ruff_states(NAME, SOURCE)
    working.write_bytes(final.replace(b"42", b"43"))
    with pytest.raises(SystemExit, match="beyond permitted Ruff fixes"):
        runner.verify_ruff_only({NAME}, recovering=True)


def test_unsafe_fix_not_enabled_even_with_project_setting(
    working: Path,
) -> None:
    (working.parent / "pyproject.toml").write_text(
        '[tool.ruff]\nunsafe-fixes = true\n[tool.ruff.lint]\nselect = ["F"]\n',
        encoding="utf-8",
    )
    source = b"def answer():\n    unused = 1\n    return 42\n"
    _, _, final = runner.ruff_states(NAME, source)
    assert b"unused = 1" in final
    assert b"return 42" in final
