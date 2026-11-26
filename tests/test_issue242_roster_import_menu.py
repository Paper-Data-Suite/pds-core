"""Synthetic D1 full-roster menu acceptance."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.roster_imports as service
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
    write_roster,
)
from pds_core.routes import class_dir, class_roster_path
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


def _row(student_id: str, name: str = "Ari", **extra: str) -> dict[str, str]:
    return {
        "student_id": student_id,
        "first_name": name,
        "last_name": "Rivera",
        "period": "2",
        **extra,
    }


def _csv(root: Path, rows: list[dict[str, str]], *, class_id: str = CLASS) -> Path:
    path = root.parent / "candidate.csv"
    write_roster(path, create_roster(class_id, rows), overwrite=path.exists())
    return path


def _invoke(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    *,
    enabled: bool = True,
    interactive: bool = True,
    before_confirm: Callable[[], None] | None = None,
) -> tuple[SharedTeacherMenuResult, str, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_ROSTER_IMPORT_PREVIEW_TEST_ONLY", enabled)
    request = SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="opaque-roster-return",
        context=TeacherContextHint(workspace_root=root, display_label="Synthetic"),
    )
    out, err = io.StringIO(), io.StringIO()
    choices = iter(answers)

    def read() -> str:
        choice = next(choices)
        if choice == "C" and before_confirm is not None:
            before_confirm()
        return choice

    receipt = run_workspace_classroom_menu(
        request, read_line=read, output=out, error_output=err, interactive=interactive
    )
    assert receipt.return_token == "opaque-roster-return"
    assert "opaque-roster-return" not in out.getvalue() + err.getvalue()
    assert "Revalidate workspace" in receipt.message
    return receipt, out.getvalue(), err.getvalue()


def _go(path: Path, *answers: str) -> list[str]:
    return ["2", "1", "I", str(path), *answers]


@pytest.mark.parametrize("enabled, interactive", [(False, True), (True, False)])
def test_public_gate(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    interactive: bool,
) -> None:
    result, out, err = _invoke(
        root, monkeypatch, [], enabled=enabled, interactive=interactive
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()
    assert out == err == ""
    assert not class_roster_path(root, CLASS).exists()


def test_first_import_preserves_leading_zero_and_optional_field(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _csv(root, [_row("0007", preferred_name="Ari")])
    result, out, err = _invoke(root, monkeypatch, _go(path, "C"))
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.ROSTER})
    assert "0007" in out and "Ari Rivera" in out
    assert "PREVIEW ONLY" in out and "Added: 1" in out
    saved = load_class_roster(root, CLASS)
    assert saved.students[0].student_id == "0007"
    assert saved.students[0].extra_fields["preferred_name"] == "Ari"
    assert err == ""


def test_mixed_import_requires_all_pages_and_preserves_producer_data(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_class_roster(
        root,
        create_roster(
            CLASS,
            [
                _row("0007", note="old"),
                _row("0008", note="preserve historical work"),
            ],
        ),
    )
    artifact = class_dir(root, CLASS) / "producer-work.txt"
    artifact.write_text("historical", encoding="utf-8")
    path = _csv(root, [_row("0007", note="new"), _row("0009", note="added")])
    result, out, err = _invoke(root, monkeypatch, _go(path, "N", "C"))
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert "Added: 1; changed: 1; removed: 1" in out
    assert "CHANGE before" in out and "CHANGE after" in out
    assert "REMOVE" in out and "0008" in out
    assert "page 2/2" in out
    assert artifact.read_text(encoding="utf-8") == "historical"
    assert [s.student_id for s in load_class_roster(root, CLASS).students] == [
        "0007",
        "0009",
    ]
    assert err == ""


def test_early_confirm_cannot_skip_review_pages(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = write_class_roster(
        root, create_roster(CLASS, [_row("0007", note="old")])
    )
    before = canonical.read_bytes()
    path = _csv(root, [_row("0007", note="new")])
    result, _, _ = _invoke(root, monkeypatch, _go(path, "C", "B", "B", "B"))
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert canonical.read_bytes() == before


@pytest.mark.parametrize(
    "answers, expected",
    [
        (["B", "B", "B", "B"], TeacherMenuExit.BACK),
        (["M"], TeacherMenuExit.MAIN_MENU),
        (["Q"], TeacherMenuExit.QUIT),
        ([], TeacherMenuExit.CANCELLED),
        ([":notes", "B", "B", "B"], TeacherMenuExit.BACK),
    ],
)
def test_cancel_navigation(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    expected: TeacherMenuExit,
) -> None:
    path = _csv(root, [_row("0007")])
    result, _, _ = _invoke(root, monkeypatch, _go(path, *answers))
    assert result.exit is expected
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not class_roster_path(root, CLASS).exists()


def test_noop_preserves_bytes(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canonical = write_class_roster(root, create_roster(CLASS, [_row("0007")]))
    before = canonical.read_bytes()
    path = _csv(root, [_row("0007")])
    result, _, err = _invoke(root, monkeypatch, _go(path, "C"))
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert canonical.read_bytes() == before
    assert err == ""


def test_dropped_column_refused(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canonical = write_class_roster(
        root, create_roster(CLASS, [_row("0007", note="keep")])
    )
    before = canonical.read_bytes()
    path = _csv(root, [_row("0007")])
    result, _, err = _invoke(root, monkeypatch, _go(path, "C"))
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "omits existing columns" in err
    assert canonical.read_bytes() == before


@pytest.mark.parametrize("kind", ["candidate", "canonical", "year", "metadata"])
def test_stale_review(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    path = _csv(root, [_row("0007")])

    def intervene() -> None:
        if kind == "candidate":
            _csv(root, [_row("0008")])
        elif kind == "canonical":
            write_class_roster(root, create_roster(CLASS, [_row("0009")]))
        elif kind == "year":
            close_school_year(root, closed_at=END)
        else:
            from pds_core.routes import class_metadata_path

            target = class_metadata_path(root, CLASS)
            target.write_bytes(target.read_bytes() + b"\n")

    result, _, err = _invoke(
        root, monkeypatch, _go(path, "C"), before_confirm=intervene
    )
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "review again" in err or "active school year" in err
    if kind == "canonical":
        assert load_class_roster(root, CLASS).students[0].student_id == "0009"
    else:
        assert not class_roster_path(root, CLASS).exists()


def test_class_mismatch_refused(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _csv(root, [_row("0007")], class_id="other")
    result, _, err = _invoke(root, monkeypatch, _go(path, "C"))
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "0007" not in err
    assert not class_roster_path(root, CLASS).exists()


def test_uncertain_write_receipt(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _csv(root, [_row("0007")])
    actual = _write_roster_unlocked

    def write_then_fail(
        path: str | Path, roster: Roster, *, overwrite: bool = False
    ) -> None:
        actual(path, roster, overwrite=overwrite)
        raise RosterWriteError(path, "private injected detail")

    monkeypatch.setattr(service, "_write_roster_unlocked", write_then_fail)
    result, _, err = _invoke(root, monkeypatch, _go(path, "C"))
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.INDETERMINATE
    assert result.change_scopes == frozenset({TeacherChangeScope.ROSTER})
    assert "before retry" in err and "private injected detail" not in err
    assert load_class_roster(root, CLASS).students[0].student_id == "0007"
