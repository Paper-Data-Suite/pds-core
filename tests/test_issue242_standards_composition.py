"""C4B synthetic CLI and private teacher-menu Standards acceptance."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import pds_core.classroom_standards_commit as guarded
import pds_core.teacher_menus as menus
from pds_core.cli import _run
from pds_core.standards import (
    StandardDefinition,
    StandardsLibrary,
    StandardsProfile,
    StandardsWriteError,
    load_standards_library,
    standards_library_path,
    write_standards_library,
)
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

pytestmark = pytest.mark.usefixtures("classroom_capability_disabled")

ONE = "synthetic:one"
TWO = "synthetic:two"
PROFILE = "english12"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    location = tmp_path / "synthetic-workspace"
    location.mkdir()
    return location


@pytest.fixture
def populated(root: Path) -> Path:
    library = StandardsLibrary(
        standards=(
            StandardDefinition(ONE, "ONE", "Synthetic", "One", "First standard"),
            StandardDefinition(TWO, "TWO", "Synthetic", "Two", "Second standard"),
        ),
        profiles=(StandardsProfile(PROFILE, (ONE,), title="English 12"),),
    )
    write_standards_library(standards_library_path(root), library)
    return root


def _cli(root: Path, *args: str) -> tuple[int, dict[str, Any], str]:
    out, err = io.StringIO(), io.StringIO()
    code = _run(
        ["--workspace", str(root), "workspace", *args, "--format", "json"],
        stdout=out,
        stderr=err,
    )
    payload: dict[str, Any] = json.loads(out.getvalue())
    return code, payload, err.getvalue()


def _preview(root: Path, *ids: str, action: str = "add") -> dict[str, Any]:
    code, payload, err = _cli(root, "standards-preview", action, PROFILE, *ids)
    assert code == 0 and err == ""
    assert payload["ok"] is True
    assert payload["scope"] == "standards"
    data: dict[str, Any] = payload["data"]
    assert data["saved"] is False
    return data


def _commit(
    root: Path,
    review: dict[str, Any],
    *ids: str,
    action: str = "add",
    confirmed: bool = True,
) -> tuple[int, dict[str, Any], str]:
    args = [
        "standards-commit",
        action,
        PROFILE,
        *ids,
        "--expected-current-state-token",
        review["current_state_token"],
        "--expected-candidate-state-token",
        review["candidate_state_token"],
    ]
    if confirmed:
        args.append("--confirm")
    return _cli(root, *args)


def _menu(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    *,
    enabled: bool = True,
    interactive: bool = True,
    before_confirm: Callable[[], None] | None = None,
) -> tuple[SharedTeacherMenuResult, str, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_STANDARDS_PREVIEW_TEST_ONLY", enabled)
    request = SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="opaque-standards-return",
        context=TeacherContextHint(workspace_root=root, display_label="Synthetic"),
    )
    iterator = iter(answers)
    out, err = io.StringIO(), io.StringIO()

    def read() -> str:
        answer = next(iterator)
        if answer == "C" and before_confirm is not None:
            before_confirm()
        return answer

    result = run_workspace_classroom_menu(
        request, read_line=read, output=out, error_output=err, interactive=interactive
    )
    assert result.return_token == "opaque-standards-return"
    assert "opaque-standards-return" not in out.getvalue() + err.getvalue()
    assert "Revalidate workspace" in result.message
    return result, out.getvalue(), err.getvalue()


def test_cli_empty_inspection_is_read_only(root: Path) -> None:
    code, payload, err = _cli(root, "standards-inspect")
    assert code == 0 and err == ""
    assert payload["data"]["present"] is False
    assert payload["data"]["library"]["standards"] == []
    assert not standards_library_path(root).parent.exists()


def test_cli_commit_and_replay(populated: Path) -> None:
    path = standards_library_path(populated)
    original = path.read_bytes()
    review = _preview(populated, TWO)
    assert review["before"] == [ONE]
    assert review["after"] == [ONE, TWO]
    assert path.read_bytes() == original
    code, result, err = _commit(populated, review, TWO)
    assert code == 0 and err == ""
    assert result["data"]["changed_scopes"] == ["STANDARDS"]
    assert result["data"]["status"] == "committed"
    assert result["data"]["revalidation_required"] is True
    assert load_standards_library(path).profiles[0].standards == (ONE, TWO)
    saved = path.read_bytes()
    code, result, err = _commit(populated, review, TWO)
    assert code == 4 and err == ""
    assert result["error"]["code"] == "standards.state_changed"
    assert path.read_bytes() == saved


def test_cli_missing_confirmation_and_changed_candidate(populated: Path) -> None:
    original = standards_library_path(populated).read_bytes()
    review = _preview(populated, TWO)
    code, result, err = _commit(populated, review, TWO, confirmed=False)
    assert code == 2 and err == ""
    assert result["error"]["code"] == "standards.not_confirmed"
    code, result, err = _commit(populated, review, TWO, action="set")
    assert code == 4 and err == ""
    assert result["error"]["code"] == "standards.candidate_changed"
    assert standards_library_path(populated).read_bytes() == original


def test_cli_empty_set_and_noop(populated: Path) -> None:
    review = _preview(populated, ONE, action="set")
    original = standards_library_path(populated).read_bytes()
    code, result, err = _commit(populated, review, ONE, action="set")
    assert code == 0 and err == ""
    assert result["data"]["status"] == "no_change"
    assert result["data"]["changed_scopes"] == []
    assert standards_library_path(populated).read_bytes() == original
    review = _preview(populated, action="set")
    code, result, err = _commit(populated, review, action="set")
    assert code == 0 and err == ""
    assert result["data"]["after"] == []
    assert len(load_standards_library(standards_library_path(populated)).standards) == 2


@pytest.mark.parametrize("enabled, interactive", [(False, True), (True, False)])
def test_public_gate(
    root: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool, interactive: bool
) -> None:
    result, out, err = _menu(
        root, monkeypatch, [], enabled=enabled, interactive=interactive
    )
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert out == err == ""
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()
    assert not standards_library_path(root).parent.exists()


def test_menu_browse_and_back(populated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = standards_library_path(populated).read_bytes()
    result, out, err = _menu(
        populated, monkeypatch, ["3", "1", "B", "2", "B", "B", "B"]
    )
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert ONE in out and TWO in out and PROFILE in out
    assert err == ""
    assert standards_library_path(populated).read_bytes() == original


def test_menu_commit(populated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, out, err = _menu(populated, monkeypatch, ["3", "3", "1", PROFILE, TWO, "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.STANDARDS})
    assert "PREVIEW ONLY" in out
    assert f'Before: ["{ONE}"]' in out
    assert f'After: ["{ONE}", "{TWO}"]' in out
    assert err == ""
    assert load_standards_library(standards_library_path(populated)).profiles[
        0
    ].standards == (ONE, TWO)


@pytest.mark.parametrize(
    "answers, expected",
    [
        (["3", "3", "1", PROFILE, TWO, "B", "B", "B"], TeacherMenuExit.BACK),
        (["3", "3", "1", PROFILE, TWO, "no", "B", "B"], TeacherMenuExit.BACK),
        (["3", "3", "1", PROFILE, TWO, ":notes", "B", "B"], TeacherMenuExit.BACK),
        (["3", "1", "M"], TeacherMenuExit.MAIN_MENU),
        (["3", "3", "1", PROFILE, "Q"], TeacherMenuExit.QUIT),
        (["3", "3", "1", PROFILE, TWO], TeacherMenuExit.CANCELLED),
    ],
)
def test_menu_navigation(
    populated: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    expected: TeacherMenuExit,
) -> None:
    original = standards_library_path(populated).read_bytes()
    result, _, _ = _menu(populated, monkeypatch, answers)
    assert result.exit is expected
    assert result.durability is TeacherDurability.NO_CHANGE
    assert standards_library_path(populated).read_bytes() == original


def test_menu_noop(populated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = standards_library_path(populated)
    before = path.read_bytes()
    result, _, _ = _menu(populated, monkeypatch, ["3", "3", "3", PROFILE, ONE, "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert path.read_bytes() == before


def test_menu_stale_preview(populated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = standards_library_path(populated)
    changed = path.read_bytes() + b"\n"

    def intervene() -> None:
        path.write_bytes(changed)

    result, _, err = _menu(
        populated,
        monkeypatch,
        ["3", "3", "1", PROFILE, TWO, "C"],
        before_confirm=intervene,
    )
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "refused" in err
    assert path.read_bytes() == changed


@pytest.mark.parametrize("via_menu", [True, False])
def test_uncertain_write(
    populated: Path,
    monkeypatch: pytest.MonkeyPatch,
    via_menu: bool,
) -> None:
    actual = write_standards_library

    def fail(
        path: str | Path, library: StandardsLibrary, *, overwrite: bool = False
    ) -> None:
        actual(path, library, overwrite=overwrite)
        raise StandardsWriteError(path, "private injected detail")

    monkeypatch.setattr(guarded, "write_standards_library", fail)
    if via_menu:
        receipt, _, err = _menu(
            populated, monkeypatch, ["3", "3", "1", PROFILE, TWO, "C"]
        )
        assert receipt.exit is TeacherMenuExit.FAILED
        assert receipt.durability is TeacherDurability.INDETERMINATE
        assert receipt.change_scopes == frozenset({TeacherChangeScope.STANDARDS})
        assert "private injected detail" not in err
    else:
        code, result, err = _commit(populated, _preview(populated, TWO), TWO)
        assert code == 7 and err == ""
        assert result["data"]["status"] == "indeterminate"
        assert result["data"]["changed_scopes"] == ["STANDARDS"]
        assert "private injected detail" not in json.dumps(result)
    assert load_standards_library(standards_library_path(populated)).profiles[
        0
    ].standards == (ONE, TWO)
