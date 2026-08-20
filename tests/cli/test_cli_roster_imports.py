"""CLI coverage for guarded full-roster import preview and commit."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest

import pds_core.cli as cli_module
import pds_core.cli_support.roster_imports as roster_cli
import pds_core.roster_imports as roster_import_service
from pds_core._roster_write_lock import roster_write_lock_path
from pds_core.classes import load_class_roster, write_class_roster
from pds_core.cli import main
from pds_core.roster_imports import RosterImportWriteError
from pds_core.rosters import Roster, RosterReadError, create_roster
from pds_core.routes import class_roster_path
from pds_core.workspace import get_workspace_config_path


def _roster(
    class_id: str = "english9_p2",
    *,
    students: list[dict[str, str]] | None = None,
) -> Roster:
    rows = students or [
        {
            "student_id": "1001",
            "first_name": "Jane",
            "last_name": "Doe",
            "period": "2",
        }
    ]
    return create_roster(class_id, rows)


def _write_candidate(path: Path, candidate: Roster) -> None:
    lines = [",".join(candidate.columns)]
    for student in candidate.students:
        values = {
            "class_id": student.class_id,
            "student_id": student.student_id,
            "last_name": student.last_name,
            "first_name": student.first_name,
            "period": student.period,
            **dict(student.extra_fields),
        }
        lines.append(",".join(values.get(column, "") for column in candidate.columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _run_json(
    capsys: pytest.CaptureFixture[str],
    *args: str,
) -> tuple[int, dict[str, object], str]:
    code = main(list(args))
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out else {}
    assert isinstance(payload, dict)
    return code, payload, captured.err


def test_roster_preview_text_is_read_only_and_privacy_minimal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(
        candidate_path,
        _roster(
            students=[
                {
                    "student_id": "1002",
                    "first_name": "Marcus",
                    "last_name": "Smith",
                    "period": "2",
                },
                {
                    "student_id": "1001",
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "period": "2",
                },
            ]
        ),
    )

    code = main(
        [
            "--workspace",
            str(workspace),
            "roster",
            "import-preview",
            "english9_p2",
            str(candidate_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert captured.err == ""
    assert "Current roster: absent" in captured.out
    assert "Added: 2" in captured.out
    assert "Changed: 0" in captured.out
    assert "Added student IDs: 1001, 1002" in captured.out
    assert "Current state token: roster-state-v1:absent" in captured.out
    assert "Candidate state token: roster-state-v1:sha256:" in captured.out
    assert "PREVIEW ONLY - NO WRITE" in captured.out
    assert "Jane" not in captured.out
    assert "Marcus" not in captured.out
    assert not workspace.exists()


def test_roster_preview_json_is_deterministic_and_bounded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    current = _roster(
        students=[
            {
                "student_id": "3000",
                "first_name": "Three",
                "last_name": "Existing",
                "period": "2",
            },
            {
                "student_id": "1000",
                "first_name": "One",
                "last_name": "Existing",
                "period": "2",
            },
            {
                "student_id": "2000",
                "first_name": "Two",
                "last_name": "Existing",
                "period": "2",
            },
        ]
    )
    write_class_roster(workspace, current)
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(
        candidate_path,
        _roster(
            students=[
                {
                    "student_id": "4000",
                    "first_name": "Four",
                    "last_name": "New",
                    "period": "2",
                },
                {
                    "student_id": "2000",
                    "first_name": "TwoChanged",
                    "last_name": "Existing",
                    "period": "2",
                },
                {
                    "student_id": "1000",
                    "first_name": "One",
                    "last_name": "Existing",
                    "period": "2",
                },
            ]
        ),
    )

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )

    assert code == 0
    assert err == ""
    assert payload["schema_version"] == "1"
    assert payload["command"] == "roster import-preview"
    assert payload["ok"] is True
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["counts"] == {
        "added": 1,
        "changed": 1,
        "removed": 1,
        "unchanged": 1,
    }
    assert data["added_student_ids"] == ["4000"]
    assert data["changed_student_ids"] == ["2000"]
    assert data["removed_student_ids"] == ["3000"]
    assert data["unchanged_student_ids"] == ["1000"]
    assert str(data["current_state_token"]).startswith("roster-state-v1:sha256:")
    assert str(data["candidate_state_token"]).startswith("roster-state-v1:sha256:")
    serialized = json.dumps(payload, sort_keys=True)
    assert "TwoChanged" not in serialized
    assert "Existing" not in serialized


def test_roster_commands_do_not_load_standards_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    def _forbidden_standards_load(_root: object) -> object:
        raise AssertionError("roster command loaded standards library")

    monkeypatch.setattr(
        cli_module,
        "load_workspace_standards_library",
        _forbidden_standards_load,
    )

    code = main(
        [
            "--workspace",
            str(tmp_path / "workspace"),
            "roster",
            "import-preview",
            "english9_p2",
            str(candidate_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert captured.err == ""


def test_roster_commit_requires_both_reviewed_tokens(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    code = main(
        [
            "--workspace",
            str(tmp_path / "workspace"),
            "roster",
            "import-commit",
            "english9_p2",
            str(candidate_path),
            "--expected-current-state-token",
            "roster-state-v1:absent",
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "--expected-candidate-state-token" in captured.err


def test_roster_commit_first_import_uses_preview_tokens(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(
        candidate_path,
        _roster(
            students=[
                {
                    "student_id": "2000",
                    "first_name": "Marcus",
                    "last_name": "Smith",
                    "period": "2",
                },
                {
                    "student_id": "1000",
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "period": "2",
                },
            ]
        ),
    )

    preview_code, preview_payload, preview_err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    assert preview_err == ""
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)

    commit_code, commit_payload, commit_err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-commit",
        "english9_p2",
        str(candidate_path),
        "--expected-current-state-token",
        str(preview_data["current_state_token"]),
        "--expected-candidate-state-token",
        str(preview_data["candidate_state_token"]),
        "--format",
        "json",
    )

    assert commit_code == 0
    assert commit_err == ""
    commit_data = commit_payload["data"]
    assert isinstance(commit_data, dict)
    assert commit_data["student_count"] == 2
    assert commit_data["previous_state_token"] == preview_data["current_state_token"]
    assert commit_data["committed_state_token"] == preview_data["candidate_state_token"]
    loaded = load_class_roster(workspace, "english9_p2")
    assert [student.student_id for student in loaded.students] == ["2000", "1000"]


def test_roster_commit_rejects_changed_candidate_with_distinct_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())
    preview_code, preview_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)
    _write_candidate(
        candidate_path,
        _roster(
            students=[
                {
                    "student_id": "2000",
                    "first_name": "Changed",
                    "last_name": "Candidate",
                    "period": "2",
                }
            ]
        ),
    )

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-commit",
        "english9_p2",
        str(candidate_path),
        "--expected-current-state-token",
        str(preview_data["current_state_token"]),
        "--expected-candidate-state-token",
        str(preview_data["candidate_state_token"]),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.candidate_changed"
    assert not workspace.exists()


def test_roster_commit_rejects_changed_canonical_state_with_distinct_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    write_class_roster(workspace, _roster())
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(
        candidate_path,
        _roster(
            students=[
                {
                    "student_id": "2000",
                    "first_name": "Marcus",
                    "last_name": "Smith",
                    "period": "2",
                }
            ]
        ),
    )
    preview_code, preview_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)
    write_class_roster(
        workspace,
        _roster(
            students=[
                {
                    "student_id": "3000",
                    "first_name": "Alyssa",
                    "last_name": "Brown",
                    "period": "2",
                }
            ]
        ),
        overwrite=True,
    )

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-commit",
        "english9_p2",
        str(candidate_path),
        "--expected-current-state-token",
        str(preview_data["current_state_token"]),
        "--expected-candidate-state-token",
        str(preview_data["candidate_state_token"]),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.current_state_changed"
    assert [
        student.student_id for student in load_class_roster(workspace, "english9_p2").students
    ] == ["3000"]


def test_roster_preview_class_mismatch_is_handled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster("english9_p3"))

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(tmp_path / "workspace"),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.class_mismatch"


def test_roster_preview_malformed_candidate_is_handled_without_row_echo(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    candidate_path.write_text(
        "class_id,student_id,last_name,first_name,period\n"
        "english9_p2,1001,Doe,Jane,2,SECRET\n",
        encoding="utf-8",
        newline="",
    )

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(tmp_path / "workspace"),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.validation_failed"
    assert "SECRET" not in json.dumps(payload)

@pytest.mark.parametrize(
    "args",
    [
        ["roster", "--help"],
        ["roster", "import-preview", "--help"],
        ["roster", "import-commit", "--help"],
    ],
)
def test_roster_help_routes_are_discoverable(
    args: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert "roster" in captured.out.lower()
    if "import-preview" in args:
        assert "candidate_csv" in captured.out
        assert "--format" in captured.out
    if "import-commit" in args:
        assert "--expected-current-state-token" in captured.out
        assert "--expected-candidate-state-token" in captured.out
        assert "--format" in captured.out


def test_roster_preview_identical_candidate_is_valid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    current = _roster(
        students=[
            {
                "student_id": "1001",
                "first_name": "Jane",
                "last_name": "Doe",
                "period": "2",
            },
            {
                "student_id": "1002",
                "first_name": "Marcus",
                "last_name": "Smith",
                "period": "2",
            },
        ]
    )
    write_class_roster(workspace, current)
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, current)

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )

    assert code == 0
    assert err == ""
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["counts"] == {
        "added": 0,
        "changed": 0,
        "removed": 0,
        "unchanged": 2,
    }
    assert data["unchanged_student_ids"] == ["1001", "1002"]
    assert data["current_state_token"] == data["candidate_state_token"]


def test_roster_preview_json_output_is_byte_deterministic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())
    args = [
        "--workspace",
        str(tmp_path / "workspace"),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    ]

    first_code = main(args)
    first = capsys.readouterr()
    second_code = main(args)
    second = capsys.readouterr()

    assert first_code == second_code == 0
    assert first.err == second.err == ""
    assert first.out == second.out


def test_roster_preview_ignores_malformed_standards_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    standards = workspace / "standards"
    standards.mkdir(parents=True)
    (standards / "library.json").write_text("not-json", encoding="utf-8")
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    code = main(
        [
            "--workspace",
            str(workspace),
            "roster",
            "import-preview",
            "english9_p2",
            str(candidate_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert captured.err == ""
    assert "PREVIEW ONLY - NO WRITE" in captured.out
    assert (standards / "library.json").read_text(encoding="utf-8") == "not-json"


def test_roster_workspace_override_is_not_persisted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    if sys.platform == "win32":
        monkeypatch.setenv("APPDATA", str(config_root))
    elif sys.platform != "darwin":
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    code = main(
        [
            "--workspace",
            str(tmp_path / "explicit-workspace"),
            "roster",
            "import-preview",
            "english9_p2",
            str(candidate_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert captured.err == ""
    assert not get_workspace_config_path().exists()


def test_roster_commit_requires_current_state_token(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    code = main(
        [
            "--workspace",
            str(tmp_path / "workspace"),
            "roster",
            "import-commit",
            "english9_p2",
            str(candidate_path),
            "--expected-candidate-state-token",
            "roster-state-v1:sha256:" + "0" * 64,
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "--expected-current-state-token" in captured.err


@pytest.mark.parametrize(
    ("current_token", "candidate_token"),
    [
        ("not-a-token", "roster-state-v1:sha256:" + "0" * 64),
        ("roster-state-v1:absent", "not-a-token"),
    ],
)
def test_roster_commit_malformed_state_token_is_domain_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    current_token: str,
    candidate_token: str,
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(tmp_path / "workspace"),
        "roster",
        "import-commit",
        "english9_p2",
        str(candidate_path),
        "--expected-current-state-token",
        current_token,
        "--expected-candidate-state-token",
        candidate_token,
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.invalid_request"


def test_roster_commit_rejects_roster_created_after_absent_preview(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())
    preview_code, preview_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)
    assert preview_data["current_state_token"] == "roster-state-v1:absent"

    write_class_roster(
        workspace,
        _roster(
            students=[
                {
                    "student_id": "3000",
                    "first_name": "Alyssa",
                    "last_name": "Brown",
                    "period": "2",
                }
            ]
        ),
    )

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-commit",
        "english9_p2",
        str(candidate_path),
        "--expected-current-state-token",
        str(preview_data["current_state_token"]),
        "--expected-candidate-state-token",
        str(preview_data["candidate_state_token"]),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.current_state_changed"
    assert [
        student.student_id
        for student in load_class_roster(workspace, "english9_p2").students
    ] == ["3000"]


def test_roster_commit_rejects_candidate_removed_after_preview(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())
    preview_code, preview_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)
    candidate_path.unlink()

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-commit",
        "english9_p2",
        str(candidate_path),
        "--expected-current-state-token",
        str(preview_data["current_state_token"]),
        "--expected-candidate-state-token",
        str(preview_data["candidate_state_token"]),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.candidate_read_failed"
    assert not workspace.exists()


def test_roster_preview_missing_candidate_has_candidate_read_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "missing.csv"

    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(tmp_path / "workspace"),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.candidate_read_failed"
    assert str(candidate_path) not in json.dumps(payload)


def test_roster_canonical_read_failure_has_distinct_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    def _fail_plan(*_args: object, **_kwargs: object) -> object:
        raise RosterReadError(tmp_path / "workspace" / "classes" / "english9_p2" / "roster.csv", "synthetic")

    monkeypatch.setattr(roster_import_service, "plan_roster_import", _fail_plan)
    code, payload, err = _run_json(
        capsys,
        "--workspace",
        str(tmp_path / "workspace"),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.current_read_failed"


def test_roster_commit_reports_existing_write_lock_as_conflict(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    current = _roster()
    write_class_roster(workspace, current)
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(
        candidate_path,
        _roster(
            students=[
                {
                    "student_id": "2000",
                    "first_name": "Marcus",
                    "last_name": "Smith",
                    "period": "2",
                }
            ]
        ),
    )
    preview_code, preview_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)

    lock_path = roster_write_lock_path(class_roster_path(workspace, "english9_p2"))
    lock_path.write_text("", encoding="utf-8")
    try:
        code, payload, err = _run_json(
            capsys,
            "--workspace",
            str(workspace),
            "roster",
            "import-commit",
            "english9_p2",
            str(candidate_path),
            "--expected-current-state-token",
            str(preview_data["current_state_token"]),
            "--expected-candidate-state-token",
            str(preview_data["candidate_state_token"]),
            "--format",
            "json",
        )
    finally:
        lock_path.unlink(missing_ok=True)

    assert code == 1
    assert err == ""
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "roster_import.write_conflict"
    assert load_class_roster(workspace, "english9_p2").students == current.students


def test_roster_commit_write_failure_is_handled_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())

    def _fail_commit(*_args: object, **_kwargs: object) -> object:
        raise RosterImportWriteError(tmp_path / "roster.csv", "TOP SECRET DETAIL")

    monkeypatch.setattr(roster_import_service, "commit_roster_import", _fail_commit)
    code = main(
        [
            "--workspace",
            str(tmp_path / "workspace"),
            "roster",
            "import-commit",
            "english9_p2",
            str(candidate_path),
            "--expected-current-state-token",
            "roster-state-v1:absent",
            "--expected-candidate-state-token",
            "roster-state-v1:sha256:" + "0" * 64,
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == ""
    assert "roster_import.write_failed" in captured.err
    assert "TOP SECRET DETAIL" not in captured.err
    assert "Traceback" not in captured.err


def test_roster_handlers_delegate_once_and_do_not_use_private_token_helpers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate(candidate_path, _roster())
    original_plan = roster_import_service.plan_roster_import
    original_commit = roster_import_service.commit_roster_import
    calls = {"plan": 0, "commit": 0}

    def _plan(*args: Any, **kwargs: Any) -> object:
        calls["plan"] += 1
        return original_plan(*args, **kwargs)

    def _commit(*args: Any, **kwargs: Any) -> object:
        calls["commit"] += 1
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(roster_import_service, "plan_roster_import", _plan)
    monkeypatch.setattr(roster_import_service, "commit_roster_import", _commit)

    preview_code, preview_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)
    commit_code, _commit_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-commit",
        "english9_p2",
        str(candidate_path),
        "--expected-current-state-token",
        str(preview_data["current_state_token"]),
        "--expected-candidate-state-token",
        str(preview_data["candidate_state_token"]),
        "--format",
        "json",
    )

    assert commit_code == 0
    assert calls == {"plan": 1, "commit": 1}
    source_path = roster_cli.__file__
    assert source_path is not None
    source = Path(source_path).read_text(encoding="utf-8")
    assert "_roster_state_token" not in source
    assert "_canonical_roster_bytes" not in source
    assert "_write_roster_unlocked" not in source


def test_roster_commit_text_success_is_privacy_minimal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    candidate_path = tmp_path / "candidate.csv"
    candidate = create_roster(
        "english9_p2",
        [
            {
                "student_id": "1001",
                "first_name": "Jane",
                "last_name": "Doe",
                "period": "2",
                "email": "private@example.test",
            }
        ],
        columns=(
            "class_id",
            "student_id",
            "last_name",
            "first_name",
            "period",
            "email",
        ),
    )
    _write_candidate(candidate_path, candidate)
    preview_code, preview_payload, _ = _run_json(
        capsys,
        "--workspace",
        str(workspace),
        "roster",
        "import-preview",
        "english9_p2",
        str(candidate_path),
        "--format",
        "json",
    )
    assert preview_code == 0
    preview_data = preview_payload["data"]
    assert isinstance(preview_data, dict)

    code = main(
        [
            "--workspace",
            str(workspace),
            "roster",
            "import-commit",
            "english9_p2",
            str(candidate_path),
            "--expected-current-state-token",
            str(preview_data["current_state_token"]),
            "--expected-candidate-state-token",
            str(preview_data["candidate_state_token"]),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert captured.err == ""
    assert "Status: COMMITTED" in captured.out
    assert "Students: 1" in captured.out
    assert "Jane" not in captured.out
    assert "Doe" not in captured.out
    assert "private@example.test" not in captured.out
    assert str(class_roster_path(workspace, "english9_p2")) not in captured.out
