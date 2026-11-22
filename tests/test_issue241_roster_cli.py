"""Core #241 Slice C: noninteractive student roster CLI acceptance."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

import pds_core.roster_edits as roster_service
from pds_core.cli import _run
from pds_core.class_metadata import (
    create_class_metadata,
    write_class_metadata_for_class,
)
from pds_core.classes import write_class_roster
from pds_core.rosters import (
    Roster,
    RosterWriteError,
    create_roster,
    load_roster,
    write_roster,
)
from pds_core.routes import class_roster_path

CLASS = "english12_p2"


def _invoke(root: Path, *args: str) -> tuple[int, str, str]:
    output, errors = io.StringIO(), io.StringIO()
    status = _run(
        ["--workspace", str(root), "roster", *args],
        stdout=output,
        stderr=errors,
    )
    return status, output.getvalue(), errors.getvalue()


def _seed(root: Path, *, one_student: bool = False) -> Path:
    students = [
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
    ]
    if one_student:
        students = students[:1]
    return write_class_roster(root, create_roster(CLASS, students))


def _source(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "change.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _change(
    operation: str = "update",
    student_id: str = "0007",
    fields: dict[str, str] | None = None,
) -> dict[str, object]:
    if fields is None:
        fields = {"period": "3"} if operation == "update" else {}
    return {
        "schema_version": "1",
        "operation": operation,
        "student_id": student_id,
        "fields": fields,
    }


def _preview(root: Path, file: Path) -> dict[str, object]:
    status, output, errors = _invoke(
        root, "student-preview", CLASS,
        "--change-file", str(file), "--format", "json",
    )
    assert status == 0 and errors == ""
    payload: dict[str, object] = json.loads(output)
    assert payload["ok"] is True
    data = payload["data"]
    assert isinstance(data, dict)
    return data


def _commit(
    root: Path, file: Path, preview: dict[str, object]
) -> tuple[int, dict[str, object], str]:
    status, output, errors = _invoke(
        root,
        "student-commit",
        CLASS,
        "--change-file",
        str(file),
        "--expected-current-state-token",
        str(preview["current_state_token"]),
        "--expected-candidate-state-token",
        str(preview["candidate_state_token"]),
        "--confirm",
        "--format",
        "json",
    )
    payload: dict[str, object] = json.loads(output)
    return status, payload, errors


def test_preview_is_read_only_and_displays_only_selected_change(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    source = _source(tmp_path, _change())
    original = path.read_bytes()

    data = _preview(root, source)
    assert data["student_id"] == "0007"
    assert data["changed_fields"] == ["period"]
    assert data["before"] == {"period": "2"}
    assert data["after"] == {"period": "3"}
    assert data["counts"] == {"before": 2, "after": 2}
    assert data["saved"] is False
    assert path.read_bytes() == original
    assert not (path.parent / ".roster.write.lock").exists()
    assert "0011" not in json.dumps(data)
    assert "Casey" not in json.dumps(data)


def test_preview_and_confirm_commit_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    source = _source(tmp_path, _change())
    preview = _preview(root, source)

    status, payload, errors = _commit(root, source, preview)
    assert status == 0 and errors == ""
    assert payload["schema_version"] == "1"
    assert payload["command"] == "roster student-commit"
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["status"] == "committed"
    assert data["committed_state_token"] == preview["candidate_state_token"]
    records = load_roster(path).students
    assert [record.student_id for record in records] == ["0007", "0011"]
    assert records[0].period == "3"
    assert records[1].period == "2"


def test_cli_add_update_remove_with_exact_service(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    add = _source(
        tmp_path,
        _change(
            "add", "0025",
            {"first_name": "Robin", "last_name": "Stone", "period": "2"},
        ),
    )
    status, payload, _ = _commit(root, add, _preview(root, add))
    assert status == 0 and payload["ok"] is True
    assert [r.student_id for r in load_roster(path).students] == [
        "0007", "0011", "0025"
    ]

    remove = _source(tmp_path, _change("remove", "0007"))
    preview = _preview(root, remove)
    assert preview["before"] == {
        "first_name": "Ari",
        "last_name": "Rivera",
        "period": "2",
    }
    assert preview["after"] is None
    status, payload, _ = _commit(root, remove, preview)
    assert status == 0 and payload["ok"] is True
    assert [r.student_id for r in load_roster(path).students] == [
        "0011", "0025"
    ]


def test_commit_cannot_omit_confirm_or_state_tokens(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    source = _source(tmp_path, _change())
    before = path.read_bytes()
    preview = _preview(root, source)

    status, _output, _errors = _invoke(
        root, "student-commit", CLASS,
        "--change-file", str(source),
        "--expected-current-state-token", str(preview["current_state_token"]),
        "--expected-candidate-state-token", str(preview["candidate_state_token"]),
    )
    assert status == 2
    status, _output, _errors = _invoke(
        root, "student-commit", CLASS, "--change-file", str(source), "--confirm"
    )
    assert status == 2
    assert path.read_bytes() == before


def test_changed_candidate_refuses_stale_tokens(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    source = _source(tmp_path, _change())
    preview = _preview(root, source)
    before = path.read_bytes()
    source.write_text(json.dumps(_change(fields={"period": "4"})), encoding="utf-8")

    status, payload, errors = _commit(root, source, preview)
    assert status == 4 and errors == ""
    assert payload["error"] == {
        "code": "roster_student.candidate_changed",
        "message": "Proposed change differs from the reviewed preview.",
    }
    assert path.read_bytes() == before


def test_changed_canonical_roster_refuses_commit(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    source = _source(tmp_path, _change())
    preview = _preview(root, source)
    newer = create_roster(
        CLASS,
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
                "period": "4",
                "preferred_name": "",
            },
        ],
    )
    write_class_roster(root, newer, overwrite=True)
    before = path.read_bytes()
    status, payload, errors = _commit(root, source, preview)
    assert status == 4 and errors == ""
    assert payload["error"]["code"] == "roster_student.current_state_changed"
    assert path.read_bytes() == before


def test_no_change_has_successful_no_write_receipt(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    source = _source(tmp_path, _change(fields={"period": "2"}))
    preview = _preview(root, source)
    before = path.read_bytes()
    assert preview["no_change"] is True
    status, payload, errors = _commit(root, source, preview)
    assert status == 0 and errors == ""
    assert payload["data"]["status"] == "no_change"
    assert path.read_bytes() == before


def test_last_student_remove_is_refused_without_write(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    path = _seed(root, one_student=True)
    before = path.read_bytes()
    source = _source(tmp_path, _change("remove", "0007"))
    status, output, errors = _invoke(
        root,
        "student-preview",
        CLASS,
        "--change-file",
        str(source),
        "--format",
        "json",
    )
    assert status == 2 and errors == ""
    assert json.loads(output)["error"]["code"] == "roster_student.empty_roster"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff\xfe",
        b"{" + b"a" * 16_384 + b"}",
        b"[]",
        b'{"schema_version":"1","operation":"remove","student_id":"0007",'
        b'"fields":{},"fields":{}}',
        b'{"schema_version":"1","operation":"update",'
        b'"student_id":"0007","fields":{"period":NaN}}',
        b'{"schema_version":1,"operation":"remove","student_id":"0007"}',
        b'{"schema_version":"1","operation":"remove","student_id":"0007",'
        b'"unexpected":true}',
        b'{"schema_version":"1","operation":"update","student_id":"0007"}',
        b'{"schema_version":"1","operation":"remove","student_id":"0007",'
        b'"fields":[]}',
    ],
)
def test_malformed_change_files_are_bounded_and_nonmutating(
    tmp_path: Path, raw: bytes
) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    before = path.read_bytes()
    source = tmp_path / "invalid.json"
    source.write_bytes(raw)
    status, output, errors = _invoke(
        root, "student-preview", CLASS,
        "--change-file", str(source), "--format", "json",
    )
    assert status == 2 and errors == ""
    assert json.loads(output)["error"]["code"] == "roster_student.invalid_change_file"
    assert path.read_bytes() == before


def test_redirected_stdin_and_interactive_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    before = path.read_bytes()
    change = json.dumps(_change())

    monkeypatch.setattr(sys, "stdin", io.StringIO(change))
    status, output, errors = _invoke(
        root, "student-preview", CLASS,
        "--change-file", "-", "--format", "json",
    )
    assert status == 0 and errors == ""
    assert json.loads(output)["data"]["student_id"] == "0007"

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", Tty(change))
    status, output, errors = _invoke(
        root, "student-preview", CLASS,
        "--change-file", "-", "--format", "json",
    )
    assert status == 2 and errors == ""
    assert json.loads(output)["error"]["code"] == "roster_student.invalid_change_file"
    assert path.read_bytes() == before


def test_text_preview_sanitizes_control_characters(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _seed(root)
    source = _source(tmp_path, _change(fields={"preferred_name": "A\x1b[31m"}))
    status, output, errors = _invoke(
        root, "student-preview", CLASS,
        "--change-file", str(source),
    )
    assert status == 0 and errors == ""
    assert "PREVIEW ONLY - NO WRITE" in output
    assert "\x1b" not in output


def test_class_missing_is_nonwriting_and_stable_exit(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    source = _source(tmp_path, _change())
    status, output, errors = _invoke(
        root, "student-preview", CLASS,
        "--change-file", str(source), "--format", "json",
    )
    assert status == 3 and errors == ""
    assert json.loads(output)["error"]["code"] == "roster_student.missing_class"
    assert not root.exists()


def test_indeterminate_write_outcome_uses_distinct_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    path = _seed(root)
    source = _source(tmp_path, _change())
    preview = _preview(root, source)

    original = roster_service._write_roster_unlocked

    def write_then_raise(
        target: str | Path, roster: Roster, *, overwrite: bool = False
    ) -> None:
        original(target, roster, overwrite=overwrite)
        raise RosterWriteError(target, "PRIVATE_AFTER_REPLACE")

    monkeypatch.setattr(roster_service, "_write_roster_unlocked", write_then_raise)
    status, payload, errors = _commit(root, source, preview)
    assert status == 7 and errors == ""
    assert payload["error"]["code"] == "roster_student.write_outcome_uncertain"
    assert "PRIVATE_AFTER_REPLACE" not in json.dumps(payload)
    assert load_roster(path).students[0].period == "3"


def test_first_add_and_legacy_import_command_compatibility(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    metadata = create_class_metadata(
        CLASS,
        "2026-2027",
        created_at=__import__("datetime").datetime(
            2026, 9, 1, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    write_class_metadata_for_class(root, metadata)
    source = _source(
        tmp_path,
        _change(
            "add", "0007",
            {"first_name": "Ari", "last_name": "Rivera", "period": "2"},
        ),
    )
    status, payload, _ = _commit(root, source, _preview(root, source))
    assert status == 0 and payload["ok"] is True
    assert load_roster(class_roster_path(root, CLASS)).students[0].student_id == "0007"

    candidate = tmp_path / "full.csv"
    write_roster(candidate, load_roster(class_roster_path(root, CLASS)))
    status, output, errors = _invoke(
        root, "import-preview", CLASS, str(candidate), "--format", "json"
    )
    assert status == 0 and errors == ""
    assert json.loads(output)["command"] == "roster import-preview"
