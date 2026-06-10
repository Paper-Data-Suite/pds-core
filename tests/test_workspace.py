"""Tests for Paper Data Suite workspace root handling."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from pds_core import workspace
from pds_core.workspace import (
    WorkspaceConfig,
    WorkspaceRootError,
    ensure_workspace_root,
    get_default_workspace_root,
    get_workspace_config_path,
    load_workspace_config,
    resolve_workspace_root,
    save_workspace_root,
)


@pytest.fixture(autouse=True)
def isolate_user_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("PDS_WORKSPACE_ROOT", raising=False)


def test_default_workspace_root_uses_user_home(
    tmp_path: Path,
) -> None:
    assert get_default_workspace_root() == (tmp_path / "Paper Data Suite").resolve()


def test_windows_config_path_uses_appdata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))

    assert get_workspace_config_path() == (
        appdata / "Paper Data Suite" / "config.json"
    ).resolve()


def test_windows_config_path_falls_back_below_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("APPDATA", raising=False)

    assert get_workspace_config_path() == (
        tmp_path
        / "AppData"
        / "Roaming"
        / "Paper Data Suite"
        / "config.json"
    ).resolve()


def test_linux_config_path_uses_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_home = tmp_path / "xdg-config"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    assert get_workspace_config_path() == (
        config_home / "paper-data-suite" / "config.json"
    ).resolve()


def test_linux_config_path_falls_back_below_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert get_workspace_config_path() == (
        tmp_path / ".config" / "paper-data-suite" / "config.json"
    ).resolve()


def test_macos_config_path_uses_application_support(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert get_workspace_config_path() == (
        tmp_path
        / "Library"
        / "Application Support"
        / "Paper Data Suite"
        / "config.json"
    ).resolve()


def test_missing_config_returns_empty_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config_path)

    assert load_workspace_config() == WorkspaceConfig()


def test_config_without_workspace_root_returns_empty_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"other_setting": true}', encoding="utf-8")
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config_path)

    assert load_workspace_config() == WorkspaceConfig()


def test_config_with_workspace_root_loads_normalized_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    configured_root = tmp_path / "configured"
    config_path.write_text(
        json.dumps({"workspace_root": str(configured_root)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config_path)

    assert load_workspace_config() == WorkspaceConfig(configured_root.resolve())


def test_save_workspace_root_creates_parent_and_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings" / "config.json"
    workspace_root = tmp_path / "workspace"
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config_path)

    saved_root = save_workspace_root(workspace_root)

    assert saved_root == workspace_root.resolve()
    assert config_path.read_text(encoding="utf-8") == (
        json.dumps(
            {"workspace_root": str(workspace_root.resolve())},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    assert list(config_path.parent.glob(".config.json.*.tmp")) == []


def test_invalid_json_raises_workspace_root_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config_path)

    with pytest.raises(WorkspaceRootError, match="invalid JSON"):
        load_workspace_config()


@pytest.mark.parametrize(
    "config_value",
    [
        "[]",
        '"workspace"',
        '{"workspace_root": 123}',
        '{"workspace_root": ""}',
    ],
)
def test_malformed_config_raises_workspace_root_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_value: str,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(config_value, encoding="utf-8")
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: config_path)

    with pytest.raises(WorkspaceRootError):
        load_workspace_config()


def test_explicit_root_has_highest_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_root = tmp_path / "explicit"
    monkeypatch.setenv("PDS_WORKSPACE_ROOT", str(tmp_path / "environment"))

    def fail_if_config_loaded() -> WorkspaceConfig:
        raise AssertionError("Saved config must not be loaded for an explicit root")

    monkeypatch.setattr(workspace, "load_workspace_config", fail_if_config_loaded)

    assert resolve_workspace_root(explicit_root) == explicit_root.resolve()


def test_environment_root_precedes_saved_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment_root = tmp_path / "environment"
    monkeypatch.setenv("PDS_WORKSPACE_ROOT", str(environment_root))

    def fail_if_config_loaded() -> WorkspaceConfig:
        raise AssertionError("Saved config must not be loaded for an environment root")

    monkeypatch.setattr(workspace, "load_workspace_config", fail_if_config_loaded)

    assert resolve_workspace_root() == environment_root.resolve()


def test_empty_environment_root_raises_workspace_root_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PDS_WORKSPACE_ROOT", "")

    with pytest.raises(WorkspaceRootError, match="cannot be empty"):
        resolve_workspace_root()


def test_saved_config_precedes_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    saved_root = tmp_path / "saved"
    monkeypatch.delenv("PDS_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr(
        workspace,
        "load_workspace_config",
        lambda: WorkspaceConfig(saved_root),
    )
    monkeypatch.setattr(
        workspace,
        "get_default_workspace_root",
        lambda: tmp_path / "default",
    )

    assert resolve_workspace_root() == saved_root


def test_default_is_used_when_no_override_or_config_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_root = tmp_path / "default"
    monkeypatch.delenv("PDS_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr(workspace, "load_workspace_config", WorkspaceConfig)
    monkeypatch.setattr(
        workspace,
        "get_default_workspace_root",
        lambda: default_root,
    )

    assert resolve_workspace_root() == default_root


def test_explicit_override_does_not_save_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_if_called(path: str | Path) -> Path:
        raise AssertionError(f"Unexpected save for {path}")

    monkeypatch.setattr(workspace, "save_workspace_root", fail_if_called)

    assert resolve_workspace_root(tmp_path / "explicit") == (
        tmp_path / "explicit"
    ).resolve()


def test_ensure_workspace_root_creates_directory_and_marker(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "new-workspace"

    ensured_root = ensure_workspace_root(workspace_root)

    marker_path = workspace_root / ".pds" / "workspace.json"
    assert ensured_root == workspace_root.resolve()
    assert marker_path.is_file()
    assert marker_path.read_text(encoding="utf-8") == (
        json.dumps(
            {
                "created_by": "pds-core",
                "workspace_version": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    assert list(marker_path.parent.glob(".workspace.json.*.tmp")) == []
    assert list(workspace_root.glob(".pds_write_test.*.tmp")) == []


def test_ensure_workspace_root_fails_for_missing_path_without_create(
    tmp_path: Path,
) -> None:
    with pytest.raises(WorkspaceRootError, match="does not exist"):
        ensure_workspace_root(tmp_path / "missing", create=False)


def test_ensure_workspace_root_accepts_existing_writable_directory(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "existing"
    workspace_root.mkdir()

    assert ensure_workspace_root(workspace_root, create=False) == (
        workspace_root.resolve()
    )
    assert not (workspace_root / ".pds").exists()
    assert list(workspace_root.glob(".pds_write_test.*.tmp")) == []


def test_ensure_workspace_root_does_not_overwrite_legacy_probe_name(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "existing"
    workspace_root.mkdir()
    legacy_probe_path = workspace_root / ".pds_write_test"
    legacy_probe_path.write_text("user content", encoding="utf-8")

    ensure_workspace_root(workspace_root, create=False)

    assert legacy_probe_path.read_text(encoding="utf-8") == "user content"
    assert list(workspace_root.glob(".pds_write_test.*.tmp")) == []


def test_ensure_workspace_root_fails_for_existing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("content", encoding="utf-8")

    with pytest.raises(WorkspaceRootError, match="not a directory"):
        ensure_workspace_root(file_path)


def test_ensure_workspace_root_rejects_filesystem_root() -> None:
    filesystem_root = Path.cwd().anchor

    with pytest.raises(WorkspaceRootError, match="filesystem root"):
        ensure_workspace_root(filesystem_root)


def test_workspace_root_rejects_empty_string() -> None:
    with pytest.raises(WorkspaceRootError, match="cannot be empty"):
        resolve_workspace_root("")


def test_workspace_root_expands_user_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        os.path,
        "expanduser",
        lambda value: value.replace("~", str(tmp_path), 1),
    )

    assert resolve_workspace_root("~/workspace") == (tmp_path / "workspace").resolve()


def test_workspace_root_expands_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PDS_TEST_ROOT", str(tmp_path))

    assert resolve_workspace_root("$PDS_TEST_ROOT/workspace") == (
        tmp_path / "workspace"
    ).resolve()
