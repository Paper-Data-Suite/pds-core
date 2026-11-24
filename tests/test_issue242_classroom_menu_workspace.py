"""Core #242 C3A: staged teacher workspace preference acceptance."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

import pytest

import pds_core.classroom_menu_workspace as flow
import pds_core.teacher_menus as menus
import pds_core.workspace as workspace
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


@pytest.fixture
def isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    config = tmp_path / "user-config" / "config.json"
    hint = tmp_path / "currently-selected-workspace"
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config)
    monkeypatch.setattr(
        workspace,
        "get_default_workspace_root",
        lambda: tmp_path / "synthetic-default",
    )
    monkeypatch.delenv(workspace.WORKSPACE_ROOT_ENV_VAR, raising=False)
    monkeypatch.setattr(menus, "_CLASSROOM_WORKSPACE_PREVIEW_TEST_ONLY", False)
    monkeypatch.setattr(menus, "_CLASSROOM_READONLY_PREVIEW_TEST_ONLY", False)
    return hint, config


def _request(hint: Path) -> SharedTeacherMenuRequest:
    return SharedTeacherMenuRequest(
        caller_application="Quillan",
        return_token="opaque-classroom-reentry",
        context=TeacherContextHint(
            workspace_root=hint,
            class_id="english12_p2",
            display_label="Synthetic English 12",
        ),
    )


def _run(
    hint: Path,
    monkeypatch: pytest.MonkeyPatch,
    inputs: list[str],
    *,
    enabled: bool = True,
    interactive: bool = True,
) -> tuple[SharedTeacherMenuResult, str, str]:
    monkeypatch.setattr(menus, "_CLASSROOM_WORKSPACE_PREVIEW_TEST_ONLY", enabled)
    out, err = io.StringIO(), io.StringIO()
    values = iter(inputs)
    result = run_workspace_classroom_menu(
        _request(hint),
        read_line=lambda: next(values),
        output=out,
        error_output=err,
        interactive=interactive,
    )
    assert result.return_token == "opaque-classroom-reentry"
    assert "Revalidate workspace" in result.message
    assert "opaque-classroom-reentry" not in out.getvalue()
    assert "opaque-classroom-reentry" not in err.getvalue()
    return result, out.getvalue(), err.getvalue()


def test_public_boundary_stays_unavailable(
    isolated: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    hint, config = isolated
    result, out, _errors = _run(hint, monkeypatch, ["4", "2", "c"], enabled=False)
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "classroom.menu.v1" not in get_teacher_experience_capabilities()
    assert not config.exists()
    assert out == ""


def test_noninteractive_refuses_even_with_private_gate(
    isolated: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    hint, config = isolated
    result, out, _ = _run(hint, monkeypatch, [], interactive=False)
    assert result.exit is TeacherMenuExit.UNAVAILABLE
    assert result.change_scopes == frozenset()
    assert out == ""
    assert not config.exists()


def test_confirmed_set_reports_committed_workspace_scope(
    isolated: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint, config = isolated
    target = tmp_path / "new-root"
    result, out, errors = _run(hint, monkeypatch, ["4", "1", str(target), "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.WORKSPACE})
    assert "Saved preference before: (none)" in out
    assert f"Saved preference after: {target.resolve()}" in out
    assert "Selected workspace would be initialized" in out
    assert "PREVIEW ONLY" in out
    assert "Saved workspace preference changed." in out
    assert workspace.load_workspace_config().workspace_root == target.resolve()
    assert (target / ".pds" / "workspace.json").exists()
    assert config.exists()
    assert not hint.exists()
    assert errors == ""


def test_reset_preserves_classroom_files_and_reports_scope(
    isolated: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint, config = isolated
    hint.mkdir()
    file = hint / "synthetic-class-data.txt"
    file.write_text("keep", encoding="utf-8")
    workspace.save_workspace_root(hint)
    result, out, errors = _run(hint, monkeypatch, ["4", "2", "c"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.COMMITTED
    assert result.change_scopes == frozenset({TeacherChangeScope.WORKSPACE})
    assert "Saved preference after: (none)" in out
    assert file.read_text(encoding="utf-8") == "keep"
    assert workspace.load_workspace_config().workspace_root is None
    assert not config.exists()
    assert errors == ""


def test_reset_noop_reports_no_change_without_creating_config(
    isolated: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint, config = isolated
    result, out, errors = _run(hint, monkeypatch, ["4", "2", "C"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert "Saved preference already matches" in out
    assert not config.parent.exists()
    assert errors == ""


@pytest.mark.parametrize(
    "inputs",
    [
        ["4", "1", "B", "B", "B"],
        ["4", "1", "new-root", "B", "B", "B"],
        ["4", "2", "B", "B", "B"],
        ["4", "2", "invalid-confirmation", "B", "B"],
    ],
)
def test_cancel_and_back_never_commit(
    isolated: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    inputs: list[str],
) -> None:
    hint, config = isolated
    result, _out, errors = _run(hint, monkeypatch, inputs)
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert not config.exists()
    assert errors == ""


@pytest.mark.parametrize(
    ("inputs", "exit_kind"),
    [
        (["4", "M"], TeacherMenuExit.MAIN_MENU),
        (["4", "Q"], TeacherMenuExit.QUIT),
        (["4", "2", "M"], TeacherMenuExit.MAIN_MENU),
        (["4", "2", "Q"], TeacherMenuExit.QUIT),
        (["4", "2"], TeacherMenuExit.CANCELLED),
    ],
)
def test_main_quit_and_eof_never_commit(
    isolated: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    inputs: list[str],
    exit_kind: TeacherMenuExit,
) -> None:
    hint, config = isolated
    result, _out, errors = _run(hint, monkeypatch, inputs)
    assert result.exit is exit_kind
    assert result.durability is TeacherDurability.NO_CHANGE
    assert not config.exists()
    assert errors == ""


def test_changed_reviewed_config_refuses_stale_commit(
    isolated: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint, config = isolated
    target = tmp_path / "proposal"
    external = tmp_path / "external-selection"
    original = flow.commit_guarded_workspace_preference_change

    def interposed(
        *args: object, **kwargs: object
    ) -> object:
        workspace.save_workspace_root(external)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(flow, "commit_guarded_workspace_preference_change", interposed)
    result, _out, errors = _run(hint, monkeypatch, ["4", "1", str(target), "C"])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.NO_CHANGE
    assert result.change_scopes == frozenset()
    assert "review it again" in errors
    assert workspace.load_workspace_config().workspace_root == external.resolve()
    assert not target.exists()
    assert config.exists()


def test_post_write_failure_reports_indeterminate_workspace(
    isolated: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint, config = isolated
    target = tmp_path / "target"
    original = workspace.save_workspace_root

    def replace_then_raise(root: str | Path) -> Path:
        original(root)
        raise workspace.WorkspaceRootError("synthetic failure after write")

    monkeypatch.setattr(workspace, "save_workspace_root", replace_then_raise)
    result, _out, errors = _run(hint, monkeypatch, ["4", "1", str(target), "C"])
    assert result.exit is TeacherMenuExit.FAILED
    assert result.durability is TeacherDurability.INDETERMINATE
    assert result.change_scopes == frozenset({TeacherChangeScope.WORKSPACE})
    assert "outcome uncertain" in errors
    assert config.exists()
    assert workspace.load_workspace_config().workspace_root == target.resolve()


def test_readonly_class_browsing_is_still_available(
    isolated: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint, config = isolated
    result, out, err = _run(hint, monkeypatch, ["2", "B", "4", "B", "B"])
    assert result.exit is TeacherMenuExit.BACK
    assert result.durability is TeacherDurability.NO_CHANGE
    assert "Classes found:" in out
    assert "Manage saved workspace preference" in out
    assert not config.exists()
    assert err == ""


def test_environment_override_stays_effective(
    isolated: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint, config = isolated
    override = tmp_path / "override"
    monkeypatch.setenv(workspace.WORKSPACE_ROOT_ENV_VAR, str(override))
    result, out, _err = _run(hint, monkeypatch, ["4", "2", "B", "B", "B"])
    assert result.exit is TeacherMenuExit.BACK
    assert "Environment override remains in effect." in out
    assert not config.exists()
