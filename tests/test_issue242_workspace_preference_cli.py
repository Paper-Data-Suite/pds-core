"""Core #242 C2B: noninteractive workspace-preference CLI acceptance."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

import pds_core.workspace as workspace
from pds_core.cli import _run
from pds_core.cli_support.workspace_preference_commands import (
    EXIT_INPUT,
    EXIT_STALE,
    EXIT_STORAGE,
    EXIT_UNCERTAIN,
)


@pytest.fixture
def private_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "user-settings" / "config.json"
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: path)
    monkeypatch.setattr(
        workspace,
        "get_default_workspace_root",
        lambda: tmp_path / "synthetic-default-workspace",
    )
    monkeypatch.delenv(workspace.WORKSPACE_ROOT_ENV_VAR, raising=False)
    return path


def _run_cli(*tokens: str) -> tuple[int, str, str]:
    output, errors = io.StringIO(), io.StringIO()
    code = _run(tokens, stdout=output, stderr=errors)
    return code, output.getvalue(), errors.getvalue()


def _json(*tokens: str) -> tuple[int, dict[str, Any], str]:
    code, output, errors = _run_cli(*tokens, "--format", "json")
    payload: dict[str, Any] = json.loads(output)
    return code, payload, errors


def _preview(action: str, path: Path | None = None) -> dict[str, Any]:
    args = ["workspace", "preference-preview", action]
    if path is not None:
        args.append(str(path))
    code, payload, errors = _json(*args)
    assert code == 0 and errors == ""
    assert payload["schema_version"] == "1"
    assert payload["command"] == "workspace preference-preview"
    assert payload["scope"] == "user_workspace_preference"
    assert payload["ok"] is True
    data: dict[str, Any] = payload["data"]
    assert data["saved"] is False
    return data


def _commit(
    action: str,
    preview: dict[str, Any],
    path: Path | None = None,
    *,
    confirm: bool = True,
) -> tuple[int, dict[str, Any], str]:
    args = ["workspace", "preference-commit", action]
    if path is not None:
        args.append(str(path))
    args.extend(
        [
            "--expected-current-state-token",
            preview["current_state_token"],
            "--expected-candidate-state-token",
            preview["candidate_state_token"],
        ]
    )
    if confirm:
        args.append("--confirm")
    return _json(*args)


def test_preview_set_is_read_only_and_binds_both_tokens(
    tmp_path: Path, private_config: Path
) -> None:
    target = tmp_path / "classroom"
    proposal = _preview("set", target)
    assert proposal["operation"] == "set"
    assert proposal["target_exists"] is False
    assert proposal["target_would_be_created"] is True
    assert proposal["proposed_saved_root"] == str(target.resolve())
    assert len(proposal["current_state_token"]) == 64
    assert len(proposal["candidate_state_token"]) == 64
    assert proposal["current_state_token"] != proposal["candidate_state_token"]
    assert not private_config.exists()
    assert not target.exists()


def test_preview_then_commit_and_replay_refusal(
    tmp_path: Path, private_config: Path
) -> None:
    target = tmp_path / "classroom"
    proposal = _preview("set", target)
    code, result, errors = _commit("set", proposal, target)
    assert code == 0 and errors == ""
    assert result["ok"] is True
    assert result["data"]["status"] == "committed"
    assert result["data"]["saved_root"] == str(target.resolve())
    assert result["data"]["committed_state_token"] != proposal["current_state_token"]
    assert workspace.load_workspace_config().workspace_root == target.resolve()
    assert (target / ".pds" / "workspace.json").is_file()
    assert private_config.exists()

    code, replay, errors = _commit("set", proposal, target)
    assert code == EXIT_STALE
    assert replay["ok"] is False
    assert replay["error"]["code"] == "workspace_preference.current_state_changed"
    assert errors == ""


def test_reset_commits_without_deleting_workspace(
    tmp_path: Path, private_config: Path
) -> None:
    target = tmp_path / "classroom"
    target.mkdir()
    student_data = target / "synthetic-producer-artifact.txt"
    student_data.write_text("preserve", encoding="utf-8")
    workspace.save_workspace_root(target)
    proposal = _preview("reset")
    assert proposal["previous_saved_root"] == str(target.resolve())
    assert proposal["proposed_saved_root"] is None
    code, result, errors = _commit("reset", proposal)
    assert code == 0 and errors == ""
    assert result["data"]["status"] == "committed"
    assert result["data"]["saved_root"] is None
    assert workspace.load_workspace_config().workspace_root is None
    assert student_data.read_text(encoding="utf-8") == "preserve"
    assert not private_config.exists()


def test_reset_noop_creates_neither_lock_nor_preference(private_config: Path) -> None:
    proposal = _preview("reset")
    assert proposal["no_change"] is True
    code, result, errors = _commit("reset", proposal)
    assert code == 0 and errors == ""
    assert result["data"]["status"] == "no_change"
    assert not private_config.parent.exists()


def test_missing_confirm_refused_without_writes(
    tmp_path: Path, private_config: Path
) -> None:
    target = tmp_path / "classroom"
    proposal = _preview("set", target)
    code, result, errors = _commit("set", proposal, target, confirm=False)
    assert code == EXIT_INPUT and errors == ""
    assert result["error"]["code"] == "workspace_preference.not_confirmed"
    assert not target.exists()
    assert not private_config.exists()


def test_proposed_target_changed_refuses_even_with_valid_current_token(
    tmp_path: Path, private_config: Path
) -> None:
    proposal = _preview("set", tmp_path / "first")
    code, result, errors = _commit("set", proposal, tmp_path / "second")
    assert code == EXIT_STALE and errors == ""
    assert result["error"]["code"] == "workspace_preference.candidate_changed"
    assert not (tmp_path / "second").exists()
    assert not private_config.exists()


def test_invalid_review_token_refused(tmp_path: Path, private_config: Path) -> None:
    proposal = _preview("set", tmp_path / "classroom")
    proposal["current_state_token"] = "invalid"
    code, payload, errors = _commit("set", proposal, tmp_path / "classroom")
    assert code == EXIT_INPUT and errors == ""
    assert payload["error"]["code"] == "workspace_preference.invalid_token"
    assert not private_config.exists()


def test_explicit_workspace_override_is_rejected_before_bootstrap(
    tmp_path: Path, private_config: Path
) -> None:
    target = tmp_path / "classroom"
    code, result, errors = _json(
        "--workspace",
        str(tmp_path / "unsupported"),
        "workspace",
        "preference-preview",
        "set",
        str(target),
    )
    assert code == EXIT_INPUT and errors == ""
    assert result["error"]["code"] == "workspace_preference.explicit_workspace"
    assert not private_config.exists()
    assert not target.exists()


def test_malformed_saved_config_produces_structured_failure(
    tmp_path: Path, private_config: Path
) -> None:
    private_config.parent.mkdir()
    private_config.write_text("{ invalid JSON", encoding="utf-8")
    code, payload, errors = _json("workspace", "preference-preview", "reset")
    assert code == EXIT_STORAGE and errors == ""
    assert payload["ok"] is False
    assert payload["error"]["code"] == "workspace_preference.invalid_config"
    assert str(tmp_path) not in json.dumps(payload)
    assert private_config.read_text(encoding="utf-8") == "{ invalid JSON"


def test_stale_config_refuses_commit_without_silent_refresh(
    tmp_path: Path, private_config: Path
) -> None:
    proposed = tmp_path / "intended"
    preview = _preview("set", proposed)
    workspace.save_workspace_root(tmp_path / "intervening")
    before = private_config.read_bytes()
    code, payload, errors = _commit("set", preview, proposed)
    assert code == EXIT_STALE and errors == ""
    assert payload["error"]["code"] == "workspace_preference.current_state_changed"
    assert private_config.read_bytes() == before
    assert not proposed.exists()


def test_environment_override_is_explicit_in_preview(
    tmp_path: Path, private_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = tmp_path / "active-env"
    selected = tmp_path / "proposed"
    monkeypatch.setenv(workspace.WORKSPACE_ROOT_ENV_VAR, str(environment))
    proposal = _preview("set", selected)
    assert proposal["environment_override_active"] is True
    assert proposal["proposed_effective_root"] == str(environment.resolve())
    assert proposal["proposed_saved_root"] == str(selected.resolve())
    assert not private_config.exists()


def test_uncertain_write_maps_to_dedicated_exit_code(
    tmp_path: Path, private_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "classroom"
    preview = _preview("set", selected)
    real = workspace.save_workspace_root

    def save_then_raise(root: str | Path) -> Path:
        real(root)
        raise workspace.WorkspaceRootError("injected after replacement")

    monkeypatch.setattr(workspace, "save_workspace_root", save_then_raise)
    code, result, errors = _commit("set", preview, selected)
    assert code == EXIT_UNCERTAIN and errors == ""
    assert result["error"]["code"] == "workspace_preference.write_outcome_uncertain"
    assert workspace.load_workspace_config().workspace_root == selected.resolve()


def test_text_preview_and_no_confirm_are_noninteractive(
    tmp_path: Path, private_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbid_input(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("CLI must not prompt")

    monkeypatch.setattr("builtins.input", forbid_input)
    selected = tmp_path / "classroom"
    code, text, errors = _run_cli(
        "workspace", "preference-preview", "set", str(selected)
    )
    assert code == 0 and errors == ""
    assert "Status: PREVIEW ONLY - NO WRITE" in text
    assert "Current state token:" in text
    assert not selected.exists()
    assert not private_config.exists()


def test_parser_missing_required_token_rejects_without_writes(
    tmp_path: Path, private_config: Path
) -> None:
    code, _text, errors = _run_cli(
        "workspace", "preference-commit", "set", str(tmp_path / "target")
    )
    assert code == 2
    assert "required" in errors.lower()
    assert not private_config.exists()


def test_old_workspace_set_reset_still_operate(
    tmp_path: Path, private_config: Path
) -> None:
    target = tmp_path / "legacy-workspace"
    code, output, errors = _run_cli("workspace", "set", str(target))
    assert code == 0 and errors == ""
    assert "Workspace root saved" in output
    assert workspace.load_workspace_config().workspace_root == target.resolve()
    code, output, errors = _run_cli("workspace", "reset")
    assert code == 0 and errors == ""
    assert "No workspace files were deleted." in output
    assert target.is_dir()
    assert not private_config.exists()
