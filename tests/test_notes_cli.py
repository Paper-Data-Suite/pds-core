"""Core #240-C: noninteractive Notes CLI end-to-end against real #239 services."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from pds_core.cli import _run
from pds_core.notes_storage import get_note, list_notes, notes_dir


def invoke(root: Path, *args: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = _run(
        ["--workspace", str(root), "notes", *args], stdout=stdout, stderr=stderr
    )
    return code, stdout.getvalue(), stderr.getvalue()


def capture(root: Path, tmp_path: Path, text: str, category: str = "task") -> str:
    source = tmp_path / "text.txt"
    source.write_text(text, encoding="utf-8")
    status, output, errors = invoke(
        root,
        "create",
        "--category",
        category,
        "--text-file",
        str(source),
        "--format",
        "json",
    )
    assert status == 0 and errors == ""
    result = json.loads(output)
    assert result["text"] == text and result["revision"] == 1
    note_id: object = result["note_id"]
    assert isinstance(note_id, str)
    return note_id


def test_task_lifecycle_all_mutation_verbs(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = capture(root, tmp_path, "Prepare lesson")
    assert invoke(root, "show", note, "--format", "json")[0] == 0
    status, output, _ = invoke(root, "list", "--status", "open", "--format", "json")
    assert status == 0 and json.loads(output)["count"] == 1
    status, output, _ = invoke(root, "search", "LESSON", "--format", "json")
    assert status == 0 and json.loads(output)["notes"][0]["note_id"] == note
    source = tmp_path / "edited.txt"
    source.write_text("Prepare two lessons", encoding="utf-8")
    assert (
        invoke(
            root, "edit", note, "--expected-revision", "1", "--text-file", str(source)
        )[0]
        == 0
    )
    assert invoke(root, "complete", note, "--expected-revision", "2")[0] == 0
    assert invoke(root, "reopen", note, "--expected-revision", "3")[0] == 0
    assert invoke(root, "archive", note, "--expected-revision", "4")[0] == 0
    assert json.loads(invoke(root, "list", "--format", "json")[1])["count"] == 0
    assert (
        json.loads(invoke(root, "list", "--status", "archived", "--format", "json")[1])[
            "count"
        ]
        == 1
    )
    assert invoke(root, "unarchive", note, "--expected-revision", "5")[0] == 0
    assert get_note(note, root).revision == 6
    assert get_note(note, root).text == "Prepare two lessons"


def test_stale_missing_and_invalid_id_codes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = capture(root, tmp_path, "Mark as finished")
    assert invoke(root, "complete", note, "--expected-revision", "1")[0] == 0
    assert invoke(root, "archive", note, "--expected-revision", "1")[0] == 4
    assert not get_note(note, root).archived
    assert invoke(root, "show", "note_" + "0" * 32)[0] == 3
    assert invoke(root, "show", "../../invalid")[0] == 2
    assert invoke(root, "complete", note, "--expected-revision", "0")[0] == 2


def test_cannot_complete_idea(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = capture(root, tmp_path, "Idea only", category="idea")
    assert invoke(root, "complete", note, "--expected-revision", "1")[0] == 6
    assert get_note(note, root).revision == 1


def test_exact_context_and_filters(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    text = tmp_path / "note.txt"
    text.write_text("Fictional unit", encoding="utf-8")
    code, output, errors = invoke(
        root,
        "create",
        "--category",
        "reflection",
        "--text-file",
        str(text),
        "--module-id",
        "meridian",
        "--class-id",
        "English12_P2",
        "--work-id",
        "Unit_1",
        "--format",
        "json",
    )
    assert code == 0 and errors == ""
    assert json.loads(output)["context"]["class_id"] == "English12_P2"
    results = invoke(root, "list", "--module-id", "meridian", "--format", "json")
    assert json.loads(results[1])["count"] == 1
    results = invoke(root, "list", "--class-id", "Other", "--format", "json")
    assert json.loads(results[1])["count"] == 0
    assert invoke(root, "list", "--module-id", "UPPER")[0] == 2


def test_no_read_side_effects_and_bad_text(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert invoke(root, "list")[0] == 0
    assert invoke(root, "search", "none")[0] == 0
    assert not notes_dir(root).exists()
    source = tmp_path / "invalid.bin"
    source.write_bytes(b"\xff\xfe")
    assert (
        invoke(root, "create", "--category", "idea", "--text-file", str(source))[0] == 2
    )
    source.write_bytes(b"a" * 40_000)
    assert (
        invoke(root, "create", "--category", "idea", "--text-file", str(source))[0] == 2
    )
    assert not notes_dir(root).exists()


def test_redirected_stdin_preserves_literal_notes_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(sys, "stdin", io.StringIO(":notes\nN\n"))
    code, _, error = invoke(root, "create", "--category", "idea", "--text-file", "-")
    assert code == 0 and error == "" and list_notes(root)[0].text == ":notes\nN\n"


def test_refuse_interactive_stdin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(sys, "stdin", Tty("NOT READ"))
    code, stdout, _ = invoke(root, "create", "--category", "task", "--text-file", "-")
    assert code == 2 and stdout == "" and not notes_dir(root).exists()


def test_conflict_preserves_evidence_and_sanitizes_errors(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = capture(root, tmp_path, "PRIVATE DATA")
    conflict = notes_dir(root) / "conflicted copy.json"
    conflict.write_text("PRIVATE DATA", encoding="utf-8")
    status, stdout, stderr = invoke(root, "show", note)
    assert status == 5 and stdout == ""
    assert "PRIVATE DATA" not in stderr and str(root) not in stderr
    assert conflict.exists()


def test_terminal_control_sanitization_for_text_show(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = capture(root, tmp_path, "Safe\x1b[31m content", category="reflection")
    code, text, _ = invoke(root, "show", note)
    assert code == 0 and "\x1b" not in text
    code, data, _ = invoke(root, "show", note, "--format", "json")
    assert code == 0 and json.loads(data)["text"].endswith("content")
