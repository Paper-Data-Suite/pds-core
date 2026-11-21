"""Opt-in Core #240 isolated candidate-wheel smoke; synthetic data only.

Example: python scripts/notes_240_wheel_smoke.py --wheel dist/pds_core-0.6.6-py3-none-any.whl
This does not publish Core or modify the current Python environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path
from typing import Sequence, cast


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    timeout: int = 90,
) -> str:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Isolated command exited {completed.returncode}: {completed.stderr[-700:]}"
        )
    if "\x1b[" in completed.stdout:
        raise RuntimeError("Non-TTY output unexpectedly contains ANSI sequences.")
    return completed.stdout


def _record(raw: str) -> dict[str, object]:
    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise AssertionError("Expected a JSON object from installed Notes CLI")
    return cast(dict[str, object], payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    args = parser.parse_args(argv)
    wheel: Path = args.wheel.resolve(strict=True)
    raw = wheel.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    required = (
        "pds_core/teacher_context.py",
        "pds_core/teacher_menus.py",
        "pds_core/notes_menu_controller.py",
        "pds_core/cli_support/notes.py",
    )
    with zipfile.ZipFile(wheel) as package:
        available = set(package.namelist())
        absent = [name for name in required if name not in available]
        if absent:
            raise RuntimeError(f"Candidate wheel lacks {', '.join(absent)}")

    with tempfile.TemporaryDirectory(prefix="core240-wheel-") as folder:
        base = Path(folder)
        installed = base / "installed"
        workspace = base / "synthetic-workspace"
        workspace.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(installed)
        python = (
            installed / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else installed / "bin" / "python"
        )
        _run(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            cwd=base,
            timeout=180,
        )
        path = _run(
            [str(python), "-I", "-c", "import pds_core; print(pds_core.__file__)"],
            cwd=base,
        ).strip()
        if not Path(path).resolve().is_relative_to(installed.resolve()):
            raise RuntimeError("Core was imported outside the isolated wheel venv.")

        def menu(input_text: str) -> str:
            return _run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pds_core.core_menu",
                    "--workspace",
                    str(workspace),
                ],
                cwd=base,
                input_text=input_text,
            )

        def cli(*args_cli: str) -> str:
            return _run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pds_core.cli",
                    "--workspace",
                    str(workspace),
                    "notes",
                    *args_cli,
                ],
                cwd=base,
            )

        first = menu("5\n1\n1\nSynthetic planning Idea\n:save\nB\n4\n")
        if "Saved." not in first or "Notes & Tasks" not in first:
            raise AssertionError("Core installed quick capture did not confirm Save.")

        source = base / "synthetic-task.txt"
        source.write_text("Synthetic follow-up Task", encoding="utf-8")
        task = _record(
            cli(
                "create",
                "--category",
                "task",
                "--text-file",
                str(source),
                "--format",
                "json",
            )
        )
        note_id = task.get("note_id")
        if not isinstance(note_id, str) or task.get("revision") != 1:
            raise AssertionError("Invalid Task receipt from installed CLI.")

        second = menu("5\n2\n1\n2\nB\nB\nB\n4\n")
        if "Open Tasks" not in second or "Saved." not in second:
            raise AssertionError("Installed menu could not complete a Task.")
        completed = _record(cli("show", note_id, "--format", "json"))
        if completed.get("completed") is not True or completed.get("revision") != 2:
            raise AssertionError("Installed Task completion did not persist.")

        reopened = _record(
            cli("reopen", note_id, "--expected-revision", "2", "--format", "json")
        )
        if reopened.get("completed") is not False or reopened.get("revision") != 3:
            raise AssertionError("CLI Task reopen did not persist.")
        archived = _record(
            cli("archive", note_id, "--expected-revision", "3", "--format", "json")
        )
        if archived.get("archived") is not True:
            raise AssertionError("CLI archive did not persist.")
        unarchived = _record(
            cli("unarchive", note_id, "--expected-revision", "4", "--format", "json")
        )
        if unarchived.get("archived") is not False:
            raise AssertionError("CLI unarchive did not persist.")

        producer = """import io, sys
from pathlib import Path
from pds_core.teacher_context import SharedTeacherMenuRequest, TeacherContextHint, TeacherMenuExit, TeacherDurability
from pds_core.teacher_menus import run_notes_tasks_menu
stream = iter(['1', '3', 'Synthetic Reflection', ':save', 'B'])
out = io.StringIO()
result = run_notes_tasks_menu(SharedTeacherMenuRequest('Fictional Producer', 'local-token', TeacherContextHint(workspace_root=Path(sys.argv[1]))), read_line=lambda: next(stream), output=out, interactive=True)
assert result.exit is TeacherMenuExit.BACK and result.durability is TeacherDurability.COMMITTED
assert result.return_token == 'local-token' and 'local-token' not in out.getvalue()
print('synthetic producer-like return: BACK, COMMITTED')
"""
        producer_result = _run(
            [str(python), "-I", "-c", producer, str(workspace)], cwd=base
        )
        if "synthetic producer-like return" not in producer_result:
            raise AssertionError("Installed public caller-return interface failed.")

        summary = _record(cli("list", "--format", "json"))
        if summary.get("count") != 3:
            raise AssertionError("Installed Notes list did not find three records.")
        shortcut = menu(":notes\nB\n4\n")
        if "Notes & Tasks" not in shortcut:
            raise AssertionError("Qualified :notes choice did not open Notes.")
        print(f"Candidate wheel SHA-256: {digest}")
        print(f"Installed module: {path}")
        print(
            "PASS: clean isolated wheel, Core capture, Core Task completion, CLI lifecycle"
        )
        print(
            "PASS: synthetic in-process caller return, :notes menu choice, no ANSI in non-TTY"
        )
        print(
            "LIMITATION: synthetic Core-only test; no real producer adoption or cross-device sync"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
