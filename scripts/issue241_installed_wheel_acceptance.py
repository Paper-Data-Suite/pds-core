"""Core #241: installed-wheel acceptance in a disposable synthetic workspace.

This script must run using the Python interpreter of a fresh isolated venv
after installing the exact wheel built from the chosen Git commit. It never
reads or writes the user's configured PDS workspace.
"""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pds_core
from pds_core.classes import write_class_roster
from pds_core.rosters import create_roster, load_roster
from pds_core.teacher_experience import get_teacher_experience_capabilities

CLASS_ID = "english12_p2"


def _assert_installed_package() -> None:
    package_file = Path(pds_core.__file__).resolve()
    environment = Path(sys.prefix).resolve()
    assert sys.prefix != sys.base_prefix, "Requires a separate virtual environment"
    assert package_file.is_relative_to(environment), (
        "Core was not imported from the isolated installed-wheel environment"
    )
    distribution = importlib.metadata.distribution("pds-core")
    scripts = {
        entry.name: entry.value
        for entry in distribution.entry_points
        if entry.group == "console_scripts"
    }
    assert scripts.get("pds-core") == "pds_core.cli:main"
    assert "classroom.roster_edits.v1" not in get_teacher_experience_capabilities()
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()
    print(f"Installed Core location: {package_file}")
    print(f"Installed Core version: {distribution.version}")


def _invoke(root: Path, *arguments: str) -> tuple[int, dict[str, Any], str]:
    """Run the installed CLI from a disposable cwd with Python isolated mode."""
    command = [
        sys.executable,
        "-I",
        "-m",
        "pds_core.cli",
        "--workspace",
        str(root),
        "roster",
        *arguments,
    ]
    result = subprocess.run(
        command,
        cwd=root.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    payload: dict[str, Any] = json.loads(result.stdout) if result.stdout else {}
    assert isinstance(payload, dict), "CLI did not return a JSON object"
    return result.returncode, payload, result.stderr


def _preview(root: Path, source: Path) -> dict[str, Any]:
    status, payload, errors = _invoke(
        root,
        "student-preview",
        CLASS_ID,
        "--change-file",
        str(source),
        "--format",
        "json",
    )
    assert (status, errors) == (0, ""), (status, errors)
    assert payload["ok"] is True
    assert payload["schema_version"] == "1"
    assert payload["command"] == "roster student-preview"
    return payload["data"]


def _commit(
    root: Path, source: Path, preview: dict[str, Any]
) -> tuple[int, dict[str, Any], str]:
    return _invoke(
        root,
        "student-commit",
        CLASS_ID,
        "--change-file",
        str(source),
        "--expected-current-state-token",
        preview["current_state_token"],
        "--expected-candidate-state-token",
        preview["candidate_state_token"],
        "--confirm",
        "--format",
        "json",
    )


def _save_change(source: Path, *, period: str) -> None:
    source.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "operation": "update",
                "student_id": "0007",
                "fields": {"period": period},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def main() -> int:
    _assert_installed_package()

    with tempfile.TemporaryDirectory(prefix="core241-installed-") as temporary:
        scratch = Path(temporary)
        workspace = scratch / "synthetic_workspace"
        source = scratch / "change.json"
        roster_path = write_class_roster(
            workspace,
            create_roster(
                CLASS_ID,
                [
                    {
                        "student_id": "0007",
                        "first_name": "Ari",
                        "last_name": "Rivera",
                        "period": "2",
                        "preferred_name": "Ari",
                    },
                    {
                        "student_id": "0011",
                        "first_name": "Casey",
                        "last_name": "Park",
                        "period": "2",
                        "preferred_name": "",
                    },
                ],
            ),
        )
        before = roster_path.read_bytes()
        _save_change(source, period="3")

        preview = _preview(workspace, source)
        assert preview["current_roster_present"] is True
        assert preview["before"] == {"period": "2"}
        assert preview["after"] == {"period": "3"}
        assert preview["counts"] == {"before": 2, "after": 2}
        assert preview["saved"] is False
        assert preview["student_id"] == "0007"
        assert "0011" not in json.dumps(preview)
        assert roster_path.read_bytes() == before
        print("PASS installed CLI read-only preview and selected-student scope")

        status, result, errors = _commit(workspace, source, preview)
        assert (status, errors) == (0, "")
        assert result["data"]["status"] == "committed"
        assert (
            result["data"]["committed_state_token"]
            == preview["candidate_state_token"]
        )
        revised = load_roster(roster_path)
        assert [s.student_id for s in revised.students] == ["0007", "0011"]
        assert revised.students[0].period == "3"
        assert revised.students[1].period == "2"
        assert revised.columns[-1] == "preferred_name"
        committed_bytes = roster_path.read_bytes()
        print("PASS installed CLI guarded commit and optional-column fidelity")

        status, result, errors = _commit(workspace, source, preview)
        assert (status, errors) == (4, "")
        assert result["error"]["code"] == "roster_student.current_state_changed"
        assert roster_path.read_bytes() == committed_bytes
        print("PASS stale token replay refused without write")

        no_confirm = [
            "student-commit",
            CLASS_ID,
            "--change-file",
            str(source),
            "--expected-current-state-token",
            preview["current_state_token"],
            "--expected-candidate-state-token",
            preview["candidate_state_token"],
            "--format",
            "json",
        ]
        status, _result, _errors = _invoke(workspace, *no_confirm)
        assert status == 2
        assert roster_path.read_bytes() == committed_bytes
        print("PASS explicit confirmation required")

        no_change = _preview(workspace, source)
        assert no_change["no_change"] is True
        status, result, errors = _commit(workspace, source, no_change)
        assert (status, errors) == (0, "")
        assert result["data"]["status"] == "no_change"
        assert roster_path.read_bytes() == committed_bytes
        print("PASS idempotent no-change receipt without rewrite")

        source.write_text(
            '{"schema_version":"1","operation":"update",'
            '"student_id":"0007","fields":{"period":"4","period":"5"}}',
            encoding="utf-8",
        )
        status, result, errors = _invoke(
            workspace,
            "student-preview",
            CLASS_ID,
            "--change-file",
            str(source),
            "--format",
            "json",
        )
        assert (status, errors) == (2, "")
        assert result["error"]["code"] == "roster_student.invalid_change_file"
        assert roster_path.read_bytes() == committed_bytes
        print("PASS malformed duplicate-key JSON rejected")

        status, result, errors = _invoke(
            workspace,
            "import-preview",
            CLASS_ID,
            str(roster_path),
            "--format",
            "json",
        )
        assert (status, errors) == (0, "")
        assert result["command"] == "roster import-preview"
        assert result["ok"] is True
        print("PASS existing full-roster import preview compatibility")

    print("CORE #241 INSTALLED-WHEEL ACCEPTANCE PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
