"""Tests for opening local paths in the system default application."""

from pathlib import Path
import subprocess
from typing import NoReturn

import pytest

from pds_core import local_open
from pds_core.local_open import LocalOpenError, open_local_path


def test_existing_file_is_opened_and_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "result.pdf"
    path.touch()
    calls: list[tuple[list[str], bool]] = []

    def record_run(command: list[str], *, check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr("pds_core.local_open.sys.platform", "linux")
    monkeypatch.setattr("pds_core.local_open.subprocess.run", record_run)

    result = open_local_path(str(path))

    assert result == path.resolve()
    assert calls == [(["xdg-open", str(path.resolve())], True)]


def test_existing_directory_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pds_core.local_open.sys.platform", "darwin")
    calls: list[tuple[list[str], bool]] = []

    def record_run(command: list[str], *, check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr("pds_core.local_open.subprocess.run", record_run)

    assert open_local_path(tmp_path) == tmp_path.resolve()
    assert calls == [(["open", str(tmp_path.resolve())], True)]


def test_missing_path_raises_local_open_error(tmp_path: Path) -> None:
    with pytest.raises(LocalOpenError, match="does not exist"):
        open_local_path(tmp_path / "missing.pdf")


@pytest.mark.parametrize("path", ["", "   "])
def test_empty_string_raises_local_open_error(path: str) -> None:
    with pytest.raises(LocalOpenError, match="must not be empty"):
        open_local_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "http://example.com/file.pdf",
        "https://example.com/file.pdf",
        "file:///tmp/file.pdf",
        " HTTPS://example.com/file.pdf ",
    ],
)
def test_url_like_string_raises_local_open_error(path: str) -> None:
    with pytest.raises(LocalOpenError, match="URLs"):
        open_local_path(path)


def test_non_file_or_directory_raises_local_open_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "special"
    path.touch()
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    monkeypatch.setattr(Path, "is_dir", lambda self: False)

    with pytest.raises(LocalOpenError, match="neither a file nor a directory"):
        open_local_path(path)


def test_windows_uses_startfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "result.pdf"
    path.touch()
    opened: list[Path] = []
    monkeypatch.setattr("pds_core.local_open.sys.platform", "win32")
    monkeypatch.setattr(local_open, "_open_on_windows", opened.append)

    assert open_local_path(path) == path.resolve()
    assert opened == [path.resolve()]


def test_windows_startfile_error_is_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "result.pdf"
    path.touch()

    def fail_to_open(unused_path: Path) -> NoReturn:
        raise OSError("startfile failed")

    monkeypatch.setattr("pds_core.local_open.sys.platform", "win32")
    monkeypatch.setattr(local_open, "_open_on_windows", fail_to_open)

    with pytest.raises(LocalOpenError, match="system viewer") as error:
        open_local_path(path)

    assert isinstance(error.value.__cause__, OSError)


@pytest.mark.parametrize("platform, command", [("darwin", "open"), ("linux", "xdg-open")])
def test_subprocess_failure_is_wrapped(
    platform: str,
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "result.pdf"
    path.touch()

    def fail_to_open(arguments: list[str], *, check: bool) -> NoReturn:
        raise subprocess.CalledProcessError(1, arguments)

    monkeypatch.setattr("pds_core.local_open.sys.platform", platform)
    monkeypatch.setattr("pds_core.local_open.subprocess.run", fail_to_open)

    with pytest.raises(LocalOpenError, match="system viewer") as error:
        open_local_path(path)

    assert isinstance(error.value.__cause__, subprocess.CalledProcessError)
    assert error.value.__cause__.cmd == [command, str(path.resolve())]


def test_missing_xdg_open_is_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "result.pdf"
    path.touch()

    def missing_command(arguments: list[str], *, check: bool) -> NoReturn:
        raise FileNotFoundError(arguments[0])

    monkeypatch.setattr("pds_core.local_open.sys.platform", "freebsd")
    monkeypatch.setattr("pds_core.local_open.subprocess.run", missing_command)

    with pytest.raises(LocalOpenError, match="system viewer") as error:
        open_local_path(path)

    assert isinstance(error.value.__cause__, FileNotFoundError)
