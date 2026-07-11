"""CLI tests for teacher-facing workspace management commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import pds_core.workspace as workspace
from pds_core.cli import main


def _patch_user_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    config_path = tmp_path / "config" / "config.json"
    monkeypatch.setattr(
        workspace,
        "get_workspace_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr(
        workspace,
        "get_default_workspace_root",
        lambda: tmp_path / "Paper Data Suite",
    )
    return config_path


def _run_cli(
    args: list[str],
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_workspace_show_displays_status_without_creating_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_user_paths(monkeypatch, tmp_path)
    workspace_root = tmp_path / "missing-workspace"

    code, out, err = _run_cli(
        ["--workspace", str(workspace_root), "workspace", "show"],
        capsys,
    )

    assert code == 0
    assert "Resolved workspace root:" in out
    assert str(workspace_root) in out
    assert "Resolution source:" in out
    assert "explicit" in out
    assert "Exists:\nno" in out
    assert "Is directory:\nno" in out
    assert "Writable:" in out
    assert "Default workspace root:" in out
    assert "Saved config path:" in out
    assert "Workspace marker:\nmissing" in out
    assert err == ""
    assert not workspace_root.exists()


def test_workspace_set_creates_baseline_saves_config_and_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _patch_user_paths(monkeypatch, tmp_path)
    workspace_root = tmp_path / "saved-workspace"

    code, out, err = _run_cli(["workspace", "set", str(workspace_root)], capsys)

    assert code == 0
    assert "Workspace root saved:" in out
    assert str(workspace_root) in out
    assert "does not move or delete existing files" in out
    assert "PDS_WORKSPACE_ROOT" in out
    assert (workspace_root / ".pds" / "workspace.json").is_file()
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "workspace_root": str(workspace_root.resolve())
    }
    assert not (workspace_root / "standards").exists()
    assert (workspace_root / "classes").is_dir()
    assert (workspace_root / "scans_inbox").is_dir()
    assert (workspace_root / "scans" / "source").is_dir()
    assert (workspace_root / "scans" / "review").is_dir()
    assert not (workspace_root / "ScoreForm").exists()
    assert not (workspace_root / "Quillan").exists()
    assert err == ""


def test_workspace_validate_creates_current_root_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_user_paths(monkeypatch, tmp_path)
    workspace_root = tmp_path / "validated-workspace"

    for _ in range(2):
        code, out, err = _run_cli(
            ["--workspace", str(workspace_root), "workspace", "validate"],
            capsys,
        )
        assert code == 0
        assert "Workspace validated successfully:" in out
        assert str(workspace_root) in out
        assert err == ""

    assert (workspace_root / ".pds" / "workspace.json").is_file()
    assert not (workspace_root / "standards").exists()
    assert (workspace_root / "classes").is_dir()
    assert (workspace_root / "scans_inbox").is_dir()
    assert (workspace_root / "scans" / "source").is_dir()
    assert (workspace_root / "scans" / "review").is_dir()
    assert not (workspace_root / "ScoreForm").exists()
    assert not (workspace_root / "Quillan").exists()


def test_workspace_reset_clears_config_without_deleting_workspace_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _patch_user_paths(monkeypatch, tmp_path)
    workspace_root = tmp_path / "workspace"
    data_file = workspace_root / "classes" / "demo.txt"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("keep me\n", encoding="utf-8")
    workspace.save_workspace_root(workspace_root)

    code, out, err = _run_cli(["workspace", "reset"], capsys)

    assert code == 0
    assert "Saved PDS workspace preference cleared." in out
    assert "No workspace files were deleted." in out
    assert "Current resolved PDS workspace root:" in out
    assert str(tmp_path / "Paper Data Suite") in out
    assert "PDS_WORKSPACE_ROOT" in out
    assert not config_path.exists()
    assert data_file.read_text(encoding="utf-8") == "keep me\n"
    assert err == ""


def test_workspace_reset_reports_when_no_saved_preference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_user_paths(monkeypatch, tmp_path)

    code, out, err = _run_cli(["workspace", "reset"], capsys)

    assert code == 0
    assert "No saved PDS workspace preference was set." in out
    assert "No workspace files were deleted." in out
    assert err == ""


def test_workspace_paths_displays_precedence_without_creating_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _patch_user_paths(monkeypatch, tmp_path)

    code, out, err = _run_cli(["workspace", "paths"], capsys)

    assert code == 0
    assert "Workspace resolution precedence:" in out
    assert "1. Explicit path supplied to a command" in out
    assert "2. PDS_WORKSPACE_ROOT environment variable" in out
    assert "3. Saved user configuration" in out
    assert "4. Default workspace root" in out
    assert str(config_path) in out
    assert str(tmp_path / "Paper Data Suite") in out
    assert "separate from source checkouts" in out
    assert err == ""
    assert not (tmp_path / "Paper Data Suite").exists()
    assert not config_path.exists()


def test_workspace_reset_respects_environment_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_user_paths(monkeypatch, tmp_path)
    environment_root = tmp_path / "env-workspace"
    monkeypatch.setenv("PDS_WORKSPACE_ROOT", str(environment_root))
    workspace.save_workspace_root(tmp_path / "saved-workspace")

    code, out, err = _run_cli(["workspace", "reset"], capsys)

    assert code == 0
    assert str(environment_root) in out
    assert "PDS_WORKSPACE_ROOT" in out
    assert err == ""
