"""Core #237 Slice 3: stream, ANSI-policy and Windows VT conformance tests."""

from __future__ import annotations

import contextlib
import ctypes
import io
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, TextIO, cast

import pytest

from pds_core import _teacher_terminal, teacher_ui
from pds_core.teacher_ui import TeacherScreenHeader, print_teacher_header


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return 7


class BrokenTty(io.StringIO):
    def isatty(self) -> bool:
        raise OSError("unavailable")


HEADER = TeacherScreenHeader("Quillan", "Review", "English 12")
PLAIN = "Quillan\nReview\nEnglish 12\n"
GREEN = "\x1b[32mQuillan\x1b[0m\nReview\nEnglish 12\n"


def test_explicit_never_writes_exact_single_terminal_newline() -> None:
    output = TtyBuffer()
    print_teacher_header(HEADER, output=output, color="never")
    assert output.getvalue() == PLAIN
    assert output.getvalue().count("\n") == 3


def test_default_auto_is_plain_for_stringio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    output = io.StringIO()
    print_teacher_header(HEADER, output=output)
    assert output.getvalue() == PLAIN


@pytest.mark.parametrize("no_color", ["1", "0", "false", "yes", " "])
def test_no_color_nonempty_always_disables_ansi(
    monkeypatch: pytest.MonkeyPatch, no_color: str
) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("NO_COLOR", no_color)
    output = TtyBuffer()
    print_teacher_header(HEADER, output=output)
    assert output.getvalue() == PLAIN


@pytest.mark.parametrize("term", ["dumb", " DUMB ", "", "  "])
def test_posix_unknown_or_dumb_term_is_plain(
    monkeypatch: pytest.MonkeyPatch, term: str
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", term)
    monkeypatch.setattr(_teacher_terminal, "_is_windows", lambda: False)
    output = TtyBuffer()
    print_teacher_header(HEADER, output=output)
    assert output.getvalue() == PLAIN


def test_empty_no_color_does_not_disable_supported_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("NO_COLOR", "")
    monkeypatch.setattr(_teacher_terminal, "_is_windows", lambda: False)
    output = TtyBuffer()
    print_teacher_header(HEADER, output=output)
    assert output.getvalue() == GREEN


def test_no_color_absent_and_supported_posix_tty_is_green(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "vt100")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(_teacher_terminal, "_is_windows", lambda: False)
    output = TtyBuffer()
    print_teacher_header(HEADER, output=output)
    assert output.getvalue() == GREEN


@pytest.mark.parametrize("mode_enabled", [True, False])
def test_windows_only_allows_verified_vt_bit(
    monkeypatch: pytest.MonkeyPatch, mode_enabled: bool
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setattr(_teacher_terminal, "_is_windows", lambda: True)
    monkeypatch.setattr(
        _teacher_terminal, "_windows_vt_enabled", lambda output: mode_enabled
    )
    output = TtyBuffer()
    print_teacher_header(HEADER, output=output)
    assert output.getvalue() == (GREEN if mode_enabled else PLAIN)


def test_windows_probe_reads_mode_without_enabling_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class FakeGetConsoleMode:
        argtypes: object = None
        restype: object = None

        def __call__(self, handle: object, mode_ptr: Any) -> int:
            calls.append(handle)
            ctypes.cast(mode_ptr, ctypes.POINTER(ctypes.c_uint32)).contents.value = 4
            return 1

    mode_reader = FakeGetConsoleMode()
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        cast(ModuleType, SimpleNamespace(get_osfhandle=lambda fd: 1234)),
    )
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, use_last_error: SimpleNamespace(GetConsoleMode=mode_reader),
        raising=False,
    )
    output = TtyBuffer()
    assert _teacher_terminal._windows_vt_enabled(output)
    assert len(calls) == 1
    assert mode_reader.argtypes is not None
    assert mode_reader.restype is not None


def test_windows_invalid_handle_or_get_mode_failure_is_plain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        cast(ModuleType, SimpleNamespace(get_osfhandle=lambda fd: -1)),
    )
    assert not _teacher_terminal._windows_vt_enabled(TtyBuffer())


def test_missing_win32_api_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        cast(ModuleType, SimpleNamespace(get_osfhandle=lambda fd: 1234)),
    )
    monkeypatch.delattr(ctypes, "WinDLL", raising=False)
    assert not _teacher_terminal._windows_vt_enabled(TtyBuffer())


def test_isatty_exception_and_missing_method_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(_teacher_terminal, "_is_windows", lambda: False)
    for output in (BrokenTty(), SimpleNamespace(write=lambda value: None)):
        assert not _teacher_terminal.supports_teacher_ansi(cast(TextIO, output))


def test_print_writes_only_explicit_stream_and_preserves_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(_teacher_terminal, "_is_windows", lambda: False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    stdout, stderr, output = io.StringIO(), io.StringIO(), TtyBuffer()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        print_teacher_header(HEADER, output=output)
    assert output.getvalue() == GREEN
    assert stdout.getvalue() == stderr.getvalue() == ""


@pytest.mark.parametrize("bad_color", ["always", "AUTO", "", "on", "true"])
def test_invalid_color_mode_rejected_without_print(bad_color: str) -> None:
    output = io.StringIO()
    with pytest.raises(ValueError, match="color"):
        print_teacher_header(HEADER, output=output, color=cast(Any, bad_color))
    assert output.getvalue() == ""


@pytest.mark.parametrize("bad_color", [None, False, True, 1, object()])
def test_invalid_color_type_rejected_without_print(bad_color: object) -> None:
    output = io.StringIO()
    with pytest.raises(TypeError, match="color"):
        print_teacher_header(HEADER, output=output, color=cast(Any, bad_color))
    assert output.getvalue() == ""


@pytest.mark.parametrize("bad_output", [None, object(), 5])
def test_invalid_output_rejected_without_global_print(bad_output: object) -> None:
    with pytest.raises(TypeError, match="output"):
        print_teacher_header(HEADER, output=cast(TextIO, bad_output))


def test_printer_rejects_invalid_header_before_writing() -> None:
    output = io.StringIO()
    with pytest.raises(TypeError, match="TeacherScreenHeader"):
        print_teacher_header(cast(TeacherScreenHeader, object()), output=output)
    assert output.getvalue() == ""


def test_no_legacy_core_screen_mutation_or_command_parser() -> None:
    assert "print_teacher_header" in teacher_ui.__all__
    assert "parse_shared_teacher_command" not in teacher_ui.__all__
