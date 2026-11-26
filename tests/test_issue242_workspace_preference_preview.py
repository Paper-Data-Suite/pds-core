"""Core #242 C1: workspace-preference previews are authoritative and read-only."""

from __future__ import annotations

from pathlib import Path

import pytest

import pds_core.classroom_workspace_preference as preference
import pds_core.workspace as workspace
from pds_core.classroom_workspace_preference import (
    WorkspacePreferenceChange,
    WorkspacePreferencePlanError,
    plan_workspace_preference_change,
)


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "user-config" / "config.json"
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: path)
    monkeypatch.delenv(workspace.WORKSPACE_ROOT_ENV_VAR, raising=False)
    return path


def test_set_missing_target_is_only_a_preview(
    tmp_path: Path, config_path: Path
) -> None:
    candidate = tmp_path / "new" / "workspace"
    before = config_path.exists()
    preview = plan_workspace_preference_change(
        WorkspacePreferenceChange("set", candidate)
    )
    assert not before
    assert not config_path.exists()
    assert not candidate.exists()
    assert preview.operation == "set"
    assert preview.proposed_saved_root == candidate.resolve()
    assert preview.proposed_effective_root == candidate.resolve()
    assert preview.target_exists is False
    assert preview.target_would_be_created is True
    assert preview.no_change is False
    assert len(preview.config_state_token) == 64


def test_existing_target_preserves_config_bytes_before_confirmation(
    tmp_path: Path, config_path: Path
) -> None:
    old = tmp_path / "old-workspace"
    new = tmp_path / "new-workspace"
    old.mkdir()
    new.mkdir()
    workspace.save_workspace_root(old)
    before = config_path.read_bytes()

    preview = plan_workspace_preference_change(WorkspacePreferenceChange("set", new))
    assert preview.previous_saved_root == old.resolve()
    assert preview.current_effective_root == old.resolve()
    assert preview.current_resolution_source == "saved_config"
    assert preview.proposed_saved_root == new.resolve()
    assert preview.target_exists is True
    assert preview.target_would_be_created is False
    assert config_path.read_bytes() == before
    assert not list(new.iterdir())


def test_setting_same_existing_target_is_noop(
    tmp_path: Path, config_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    workspace.save_workspace_root(root)
    before = config_path.read_bytes()

    preview = plan_workspace_preference_change(WorkspacePreferenceChange("set", root))
    assert preview.no_change
    assert preview.current_effective_root == preview.proposed_effective_root
    assert config_path.read_bytes() == before


def test_reset_saved_preference_is_preview_only(
    tmp_path: Path, config_path: Path
) -> None:
    selected = tmp_path / "selected"
    workspace.save_workspace_root(selected)
    before = config_path.read_bytes()

    preview = plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    assert preview.operation == "reset"
    assert preview.previous_saved_root == selected.resolve()
    assert preview.proposed_saved_root is None
    assert preview.proposed_effective_root == workspace.get_default_workspace_root()
    assert not preview.no_change
    assert config_path.read_bytes() == before


def test_reset_missing_preference_reports_no_change(config_path: Path) -> None:
    preview = plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    assert preview.no_change
    assert preview.previous_saved_root is None
    assert not config_path.exists()


def test_environment_override_is_reported_not_silently_replaced(
    tmp_path: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overridden = tmp_path / "environment"
    target = tmp_path / "requested"
    monkeypatch.setenv(workspace.WORKSPACE_ROOT_ENV_VAR, str(overridden))
    before = config_path.exists()
    preview = plan_workspace_preference_change(WorkspacePreferenceChange("set", target))
    assert preview.environment_override_active
    assert preview.current_resolution_source == "environment"
    assert preview.current_effective_root == overridden.resolve()
    assert preview.proposed_saved_root == target.resolve()
    assert preview.proposed_effective_root == overridden.resolve()
    assert config_path.exists() == before
    assert not target.exists()


def test_config_token_changes_when_saved_content_changes(
    tmp_path: Path, config_path: Path
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    workspace.save_workspace_root(left)
    first = plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    workspace.save_workspace_root(right)
    second = plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    assert first.config_state_token != second.config_state_token
    assert config_path.exists()


def test_invalid_json_refused_without_replacing_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{", encoding="utf-8")
    before = config_path.read_bytes()
    with pytest.raises(WorkspacePreferencePlanError) as raised:
        plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    assert raised.value.reason == "invalid_config"
    assert str(config_path) not in str(raised.value)
    assert config_path.read_bytes() == before


def test_oversized_config_refused_without_loading(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True)
    config_path.write_bytes(b"x" * (16 * 1024 + 1))
    with pytest.raises(WorkspacePreferencePlanError) as raised:
        plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    assert raised.value.reason == "oversized_config"


def test_redirected_config_refused(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.is_symlink

    def synthetic_redirect(path: Path) -> bool:
        return path == config_path or original(path)

    monkeypatch.setattr(Path, "is_symlink", synthetic_redirect)
    with pytest.raises(WorkspacePreferencePlanError) as raised:
        plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    assert raised.value.reason == "redirected_config"
    assert not config_path.exists()


def test_stale_config_during_planning_is_refused(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = preference._config_fingerprint
    calls = 0

    def changing(path: Path) -> str:
        nonlocal calls
        calls += 1
        return original(path) if calls == 1 else "f" * 64

    monkeypatch.setattr(preference, "_config_fingerprint", changing)
    with pytest.raises(WorkspacePreferencePlanError) as raised:
        plan_workspace_preference_change(WorkspacePreferenceChange("reset"))
    assert raised.value.reason == "stale_config"
    assert calls == 2


@pytest.mark.parametrize(
    "candidate",
    ["", "/", "bad\0root"],
)
def test_invalid_target_is_refused_without_writes(
    candidate: str, config_path: Path
) -> None:
    with pytest.raises(WorkspacePreferencePlanError) as raised:
        plan_workspace_preference_change(WorkspacePreferenceChange("set", candidate))
    assert raised.value.reason == "invalid_target"
    assert not config_path.exists()


def test_non_directory_target_refused(tmp_path: Path, config_path: Path) -> None:
    file_path = tmp_path / "not-a-workspace"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(WorkspacePreferencePlanError) as raised:
        plan_workspace_preference_change(WorkspacePreferenceChange("set", file_path))
    assert raised.value.reason == "invalid_target"
    assert not config_path.exists()


@pytest.mark.parametrize(
    "change",
    [
        WorkspacePreferenceChange("reset"),
        WorkspacePreferenceChange("set", "somewhere"),
    ],
)
def test_previews_do_not_modify_existing_user_config(
    change: WorkspacePreferenceChange,
    tmp_path: Path,
    config_path: Path,
) -> None:
    existing = tmp_path / "workspace"
    existing.mkdir()
    workspace.save_workspace_root(existing)
    before = config_path.read_bytes()
    plan_workspace_preference_change(change)
    assert config_path.read_bytes() == before


def test_invalid_change_shape_rejected() -> None:
    with pytest.raises(ValueError):
        WorkspacePreferenceChange("set")
    with pytest.raises(ValueError):
        WorkspacePreferenceChange("reset", "unwanted")
    with pytest.raises(TypeError):
        plan_workspace_preference_change(object())  # type: ignore[arg-type]
