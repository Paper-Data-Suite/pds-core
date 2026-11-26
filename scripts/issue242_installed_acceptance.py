"""Core #242 installed capability acceptance; run with isolated installed Python."""

from __future__ import annotations

import importlib.metadata
import io
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pds_core
from pds_core.class_metadata import create_class_metadata, write_class_metadata_for_class
from pds_core.classes import load_class_roster, write_class_roster
from pds_core.rosters import create_roster
from pds_core.school_years import open_school_year
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.teacher_menus import run_workspace_classroom_menu

CLASS = "english12_p2"
YEAR = "2026-2027"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _visit(root: Path, choices: list[str], *, interactive: bool = True) -> tuple[SharedTeacherMenuResult, str]:
    token = "installed-synthetic-continuation"
    out, err = io.StringIO(), io.StringIO()
    values = iter(choices)
    receipt = run_workspace_classroom_menu(
        SharedTeacherMenuRequest("Synthetic installed caller", token, TeacherContextHint(workspace_root=root)),
        read_line=lambda: next(values),
        output=out, error_output=err, interactive=interactive,
    )
    assert receipt.return_token == token
    assert token not in out.getvalue() + err.getvalue()
    assert err.getvalue() == ""
    assert "Revalidate workspace" in receipt.message
    return receipt, out.getvalue()


def main() -> None:
    assert sys.flags.isolated, "Use Python -I"
    assert sys.prefix != sys.base_prefix
    package_file = Path(pds_core.__file__).resolve()
    assert package_file.is_relative_to(Path(sys.prefix).resolve())
    distribution = importlib.metadata.distribution("pds-core")
    entries = {entry.name: entry.value for entry in distribution.entry_points if entry.group == "console_scripts"}
    assert entries.get("core") == "pds_core.core_menu:main"
    assert entries.get("pds-core") == "pds_core.cli:main"
    assert {"classroom.menu.v1", "classroom.roster_edits.v1", "notes.menu.v1"}.issubset(get_teacher_experience_capabilities())
    with tempfile.TemporaryDirectory(prefix="core242-installed-") as directory:
        root = Path(directory) / "workspace"
        receipt, text = _visit(root, [], interactive=False)
        assert receipt.exit is TeacherMenuExit.UNAVAILABLE
        assert receipt.durability is TeacherDurability.NO_CHANGE
        assert text == "" and not root.exists()
        root.mkdir()
        open_school_year(root, YEAR, opened_at=START)
        write_class_metadata_for_class(root, create_class_metadata(CLASS, YEAR, created_at=START))
        rows = [
            {"student_id": "0007", "first_name": "Ari", "last_name": "Rivera", "period": "2", "note": "keep"},
            {"student_id": "0011", "first_name": "Ari", "last_name": "Rivera", "period": "2", "note": "other"},
        ]
        roster_path = write_class_roster(root, create_roster(CLASS, rows))
        original = roster_path.read_bytes()
        work = roster_path.parent / "synthetic-producer-work.txt"
        work.write_bytes(b"preserve")
        receipt, text = _visit(root, ["2", "1", "2", "E", "period", "3", "DONE", "B", "B", "B", "B", "B"])
        assert receipt.durability is TeacherDurability.NO_CHANGE
        assert roster_path.read_bytes() == original
        assert "Ari Rivera (ID: 0011)" in text
        receipt, text = _visit(root, ["2", "1", "2", "E", "period", "3", "DONE", "C"])
        assert receipt.exit is TeacherMenuExit.BACK
        assert receipt.durability is TeacherDurability.COMMITTED
        assert receipt.change_scopes == frozenset({TeacherChangeScope.ROSTER})
        saved = load_class_roster(root, CLASS)
        assert saved.students[0].period == "2"
        assert saved.students[1].student_id == "0011"
        assert saved.students[1].period == "3"
        assert saved.students[1].extra_fields["note"] == "other"
        assert work.read_bytes() == b"preserve"
        assert "PREVIEW ONLY" in text
        # Installed Core menu and CLI routes must be reachable, without using
        # the user's configured workspace or pretending redirected CLI is TTY.
        core = subprocess.run(
            [sys.executable, "-I", "-m", "pds_core.core_menu", "--workspace", str(root)],
            input="6\nB\n4\n", cwd=directory, capture_output=True, text=True,
            encoding="utf-8", timeout=30, check=False,
        )
        assert core.returncode == 0, core.stderr
        assert "6. Workspace & Classroom Management" in core.stdout
        assert "Classes and rosters" in core.stdout
        assert "not yet available" not in core.stdout
        cli = subprocess.run(
            [sys.executable, "-I", "-m", "pds_core.cli", "--workspace", str(root / "unused"), "workspace", "menu"],
            input="", cwd=directory, capture_output=True, text=True,
            encoding="utf-8", timeout=30, check=False,
        )
        assert cli.returncode == 5
        assert "interactive session" in cli.stderr
        assert cli.stdout == "" and not (root / "unused").exists()
    print(f"ISSUE #242 INSTALLED ACCEPTANCE PASSED: {distribution.version}")


if __name__ == "__main__":
    main()
