"""Synthetic D2 teacher-menu acceptance for guarded enrollment edits."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.roster_edits as service
import pds_core.teacher_menus as menus
from pds_core.class_metadata import (
    create_class_metadata,
    write_class_metadata_for_class,
)
from pds_core.classes import load_class_roster, write_class_roster
from pds_core.rosters import (
    Roster,
    RosterWriteError,
    _write_roster_unlocked,
    create_roster,
)
from pds_core.routes import class_dir
from pds_core.school_years import close_school_year, open_school_year
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
END = datetime(2027, 6, 30, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    location = tmp_path / "workspace"
    location.mkdir()
    open_school_year(location, YEAR, opened_at=START)
    write_class_metadata_for_class(
        location, create_class_metadata(CLASS, YEAR, created_at=START)
    )
    return location


def _row(student_id: str, **extra: str) -> dict[str, str]:
    return {
        "student_id": student_id,
        "first_name": "Ari",
        "last_name": "Rivera",
        "period": "2",
        "preferred_name": "",
        **extra,
    }


def _seed(root: Path, *, two: bool = True) -> Path:
    rows = [_row("0007", note="keep")]
    if two:
        rows.append(_row("0011", note="other"))
    return write_class_roster(root, create_roster(CLASS, rows))


def _invoke(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    *,
    enabled: bool = True,
    interactive: bool = True,
    before: Callable[[str], None] | None = None,
) -> tuple[SharedTeacherMenuResult, str, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_STUDENT_EDIT_PREVIEW_TEST_ONLY", enabled)
    request = SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="opaque-enrollment-return",
        context=TeacherContextHint(workspace_root=root, display_label="Synthetic"),
    )
    out, err = io.StringIO(), io.StringIO()
    choices = iter(answers)

    def read() -> str:
        choice = next(choices)
        if before is not None:
            before(choice)
        return choice

    result = run_workspace_classroom_menu(
        request, read_line=read, output=out, error_output=err, interactive=interactive
    )
    assert result.return_token == "opaque-enrollment-return"
    assert "opaque-enrollment-return" not in out.getvalue() + err.getvalue()
    assert "Revalidate workspace" in result.message
    return result, out.getvalue(), err.getvalue()


def _add(*answers: str) -> list[str]:
    return ["2", "1", "A", "0025", "Robin", "Stone", "2", *answers]


def _edit(*answers: str) -> list[str]:
    return ["2", "1", "2", "E", *answers]


def _remove(*answers: str) -> list[str]:
    return ["2", "1", "2", "R", *answers]


@pytest.mark.parametrize("enabled, interactive", [(False, True), (True, False)])
def test_public_gate(
    root: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool, interactive: bool
) -> None:
    receipt, out, err = _invoke(
        root, monkeypatch, [], enabled=enabled, interactive=interactive
    )
    assert receipt.exit is TeacherMenuExit.UNAVAILABLE
    assert receipt.durability is TeacherDurability.NO_CHANGE
    assert out == err == ""
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()


def test_first_enrollment(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, out, err = _invoke(root, monkeypatch, _add("DONE", "C"))
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.ROSTER})
    assert "PREVIEW ONLY" in out and "Enrollment count: 0 -> 1" in out
    assert "0025" in out and "Robin Stone" in out
    assert load_class_roster(root, CLASS).students[0].student_id == "0025"
    assert err == ""


def test_add_preserves_schema_and_existing_records(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(root)
    original = load_class_roster(root, CLASS)
    result, _, err = _invoke(
        root, monkeypatch, _add("preferred_name", "Rob", "note", "new", "DONE", "C")
    )
    saved = load_class_roster(root, CLASS)
    assert result.durability is TeacherDurability.COMMITTED
    assert saved.columns == original.columns
    assert saved.students[:2] == original.students
    assert saved.students[2].extra_fields["preferred_name"] == "Rob"
    assert saved.students[2].extra_fields["note"] == "new"
    assert err == ""


def test_duplicate_names_select_exact_id(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(root)
    original = load_class_roster(root, CLASS)
    result, out, err = _invoke(
        root, monkeypatch, _edit("period", "3", "note", "CLEAR", "DONE", "C")
    )
    saved = load_class_roster(root, CLASS)
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert saved.students[0] == original.students[0]
    assert saved.students[1].student_id == "0011"
    assert saved.students[1].period == "3"
    assert saved.students[1].extra_fields["note"] == ""
    assert saved.columns == original.columns
    assert "Ari Rivera (ID: 0007)" in out and "Ari Rivera (ID: 0011)" in out
    assert "Before:" in out and "After:" in out
    assert err == ""


def test_remove_only_enrollment_preserves_work(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(root)
    artifact = class_dir(root, CLASS) / "producer-work.txt"
    artifact.write_text("preserve", encoding="utf-8")
    result, out, err = _invoke(root, monkeypatch, _remove("C"))
    assert result.durability is TeacherDurability.COMMITTED
    assert "Enrollment count: 2 -> 1" in out
    assert [
        record.student_id for record in load_class_roster(root, CLASS).students
    ] == ["0007"]
    assert artifact.read_text(encoding="utf-8") == "preserve"
    assert err == ""


def test_final_student_removal_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _seed(root, two=False)
    original = path.read_bytes()
    result, _, err = _invoke(root, monkeypatch, ["2", "1", "1", "R"])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "final student" in err
    assert path.read_bytes() == original


def test_noop_preserves_bytes(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _seed(root)
    before = path.read_bytes()
    result, _, err = _invoke(root, monkeypatch, _edit("period", "2", "DONE", "C"))
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not result.change_scopes
    assert path.read_bytes() == before
    assert err == ""


@pytest.mark.parametrize(
    "answers, expected",
    [
        (["B", "B", "B", "B", "B"], TeacherMenuExit.BACK),
        (["M"], TeacherMenuExit.MAIN_MENU),
        (["Q"], TeacherMenuExit.QUIT),
        ([], TeacherMenuExit.CANCELLED),
        (["period", "3", "DONE", ":notes", "B", "B", "B", "B"], TeacherMenuExit.BACK),
    ],
)
def test_navigation(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    expected: TeacherMenuExit,
) -> None:
    path = _seed(root)
    before = path.read_bytes()
    result, _, _ = _invoke(root, monkeypatch, _edit(*answers))
    assert result.exit is expected
    assert result.durability is TeacherDurability.NO_CHANGE
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ["entry", "confirm", "year"])
def test_stale_state_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    _seed(root)

    def intervene(choice: str) -> None:
        if (kind == "entry" and choice == "DONE") or (
            kind == "confirm" and choice == "C"
        ):
            write_class_roster(
                root,
                create_roster(
                    CLASS, [_row("0007", note="external"), _row("0011", note="other")]
                ),
                overwrite=True,
            )
        elif kind == "year" and choice == "C":
            close_school_year(root, closed_at=END)

    result, _, _ = _invoke(
        root, monkeypatch, _edit("period", "3", "DONE", "C"), before=intervene
    )
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    saved = load_class_roster(root, CLASS)
    assert saved.students[1].period == "2"
    if kind != "year":
        assert saved.students[0].extra_fields["note"] == "external"


def test_immutable_identity_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _seed(root)
    before = path.read_bytes()
    result, _, err = _invoke(root, monkeypatch, _edit("student_id", "0099"))
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "not editable" in err
    assert path.read_bytes() == before


@pytest.mark.parametrize("published", [False, True])
def test_write_failure_receipt(
    root: Path, monkeypatch: pytest.MonkeyPatch, published: bool
) -> None:
    path = _seed(root)
    before = path.read_bytes()

    def fail(path: str | Path, roster: Roster, *, overwrite: bool = False) -> None:
        if published:
            _write_roster_unlocked(path, roster, overwrite=overwrite)
        raise RosterWriteError(path, "private injected detail")

    monkeypatch.setattr(service, "_write_roster_unlocked", fail)
    result, _, err = _invoke(root, monkeypatch, _edit("period", "3", "DONE", "C"))
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is (
        TeacherDurability.INDETERMINATE if published else TeacherDurability.NO_CHANGE
    )
    assert result.change_scopes == (
        frozenset({TeacherChangeScope.ROSTER}) if published else frozenset()
    )
    assert "private injected detail" not in err
    assert "before retry" in err
    if published:
        assert load_class_roster(root, CLASS).students[1].period == "3"
    else:
        assert path.read_bytes() == before
