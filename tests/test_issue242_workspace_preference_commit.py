"""Core #242 C2A: guarded workspace preference commit acceptance."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import pds_core.classroom_workspace_commit as commit
import pds_core.workspace as workspace
from pds_core.classroom_workspace_commit import (
    WorkspacePreferenceCommitError,
    WorkspacePreferenceConflictError,
    WorkspacePreferenceWriteError,
    commit_guarded_workspace_preference_change,
    plan_guarded_workspace_preference_change,
)
from pds_core.classroom_workspace_preference import WorkspacePreferenceChange


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "private-config" / "config.json"
    monkeypatch.setattr(workspace, "get_workspace_config_path", lambda: path)
    monkeypatch.delenv(workspace.WORKSPACE_ROOT_ENV_VAR, raising=False)
    return path


def _commit(
    change: WorkspacePreferenceChange,
    *,
    confirmed: bool = True,
) -> commit.WorkspacePreferenceCommitResult:
    review = plan_guarded_workspace_preference_change(change)
    return commit_guarded_workspace_preference_change(
        change,
        expected_current_state_token=review.current_state_token,
        expected_candidate_state_token=review.candidate_state_token,
        confirmed=confirmed,
    )


def test_review_is_read_only_and_has_distinct_tokens(
    tmp_path: Path, isolated_config: Path
) -> None:
    choice = WorkspacePreferenceChange("set", tmp_path / "new-workspace")
    preview = plan_guarded_workspace_preference_change(choice)
    assert preview.proposal.target_would_be_created
    assert len(preview.current_state_token) == 64
    assert len(preview.candidate_state_token) == 64
    assert preview.current_state_token != preview.candidate_state_token
    assert not isolated_config.exists()
    assert not (tmp_path / "new-workspace").exists()


def test_confirmed_set_creates_only_selected_workspace_and_preference(
    tmp_path: Path, isolated_config: Path
) -> None:
    root = tmp_path / "new-workspace"
    change = WorkspacePreferenceChange("set", root)
    review = plan_guarded_workspace_preference_change(change)
    result = _commit(change)
    assert result.operation == "set"
    assert result.outcome == "committed"
    assert result.previous_state_token == review.current_state_token
    assert result.committed_state_token != result.previous_state_token
    assert result.saved_root == root.resolve()
    assert workspace.load_workspace_config().workspace_root == root.resolve()
    assert (root / ".pds" / "workspace.json").is_file()
    assert not (isolated_config.parent / ".workspace-preference.write.lock").exists()


def test_confirmed_reset_preserves_existing_workspace_data(
    tmp_path: Path, isolated_config: Path
) -> None:
    original = tmp_path / "workspace"
    original.mkdir()
    private = original / "producer-owned.txt"
    private.write_text("unchanged", encoding="utf-8")
    workspace.save_workspace_root(original)
    result = _commit(WorkspacePreferenceChange("reset"))
    assert result.outcome == "committed"
    assert result.saved_root is None
    assert workspace.load_workspace_config().workspace_root is None
    assert private.read_text(encoding="utf-8") == "unchanged"
    assert not isolated_config.exists()


def test_noop_reset_does_not_create_config_directory(
    isolated_config: Path,
) -> None:
    result = _commit(WorkspacePreferenceChange("reset"))
    assert result.outcome == "no_change"
    assert result.previous_state_token == result.committed_state_token
    assert not isolated_config.parent.exists()


def test_noop_set_never_rewrites_or_initializes_existing_root(
    tmp_path: Path, isolated_config: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    workspace.save_workspace_root(root)
    before = isolated_config.read_bytes()
    result = _commit(WorkspacePreferenceChange("set", root))
    assert result.outcome == "no_change"
    assert isolated_config.read_bytes() == before
    assert not (root / ".pds").exists()


def test_confirmation_is_required_before_any_write(
    tmp_path: Path, isolated_config: Path
) -> None:
    root = tmp_path / "workspace"
    change = WorkspacePreferenceChange("set", root)
    with pytest.raises(WorkspacePreferenceCommitError) as raised:
        _commit(change, confirmed=False)
    assert raised.value.reason == "not_confirmed"
    assert not root.exists()
    assert not isolated_config.exists()


def test_stale_saved_config_refuses_without_rewrite(
    tmp_path: Path, isolated_config: Path
) -> None:
    choice = WorkspacePreferenceChange("set", tmp_path / "selected")
    review = plan_guarded_workspace_preference_change(choice)
    other = tmp_path / "other"
    workspace.save_workspace_root(other)
    before = isolated_config.read_bytes()
    with pytest.raises(WorkspacePreferenceConflictError) as raised:
        commit_guarded_workspace_preference_change(
            choice,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "current_state_changed"
    assert isolated_config.read_bytes() == before
    assert not (tmp_path / "selected").exists()


def test_different_candidate_refused_even_with_same_current_token(
    tmp_path: Path, isolated_config: Path
) -> None:
    first = WorkspacePreferenceChange("set", tmp_path / "one")
    second = WorkspacePreferenceChange("set", tmp_path / "two")
    review = plan_guarded_workspace_preference_change(first)
    with pytest.raises(WorkspacePreferenceConflictError) as raised:
        commit_guarded_workspace_preference_change(
            second,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "candidate_changed"
    assert not (tmp_path / "two").exists()
    assert not isolated_config.exists()


def test_invalid_state_tokens_are_refused_without_writing(
    tmp_path: Path, isolated_config: Path
) -> None:
    change = WorkspacePreferenceChange("set", tmp_path / "workspace")
    review = plan_guarded_workspace_preference_change(change)
    with pytest.raises(WorkspacePreferenceCommitError) as raised:
        commit_guarded_workspace_preference_change(
            change,
            expected_current_state_token="bad",
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "invalid_token"
    assert not isolated_config.exists()


def test_existing_local_writer_lock_refuses_without_mutation(
    tmp_path: Path, isolated_config: Path
) -> None:
    isolated_config.parent.mkdir()
    lock = isolated_config.parent / ".workspace-preference.write.lock"
    lock.write_text("other writer", encoding="utf-8")
    choice = WorkspacePreferenceChange("set", tmp_path / "workspace")
    with pytest.raises(WorkspacePreferenceConflictError) as raised:
        _commit(choice)
    assert raised.value.reason == "write_conflict"
    assert lock.read_text(encoding="utf-8") == "other writer"
    assert not isolated_config.exists()
    assert not (tmp_path / "workspace").exists()


def test_config_changed_before_locked_revalidation_fails_closed(
    tmp_path: Path,
    isolated_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "selected"
    other = tmp_path / "other"
    choice = WorkspacePreferenceChange("set", target)

    @contextmanager
    def tamper(_path: Path) -> Iterator[None]:
        workspace.save_workspace_root(other)
        yield

    monkeypatch.setattr(commit, "_local_lock", tamper)
    review = plan_guarded_workspace_preference_change(choice)
    with pytest.raises(WorkspacePreferenceConflictError) as raised:
        commit_guarded_workspace_preference_change(
            choice,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "current_state_changed"
    assert workspace.load_workspace_config().workspace_root == other.resolve()
    assert not target.exists()


def test_exception_after_config_replace_is_uncertain(
    tmp_path: Path, isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    choice = WorkspacePreferenceChange("set", root)
    real_save = workspace.save_workspace_root

    def write_then_fail(path: str | Path) -> Path:
        real_save(path)
        raise workspace.WorkspaceRootError("injected failure after replacement")

    monkeypatch.setattr(workspace, "save_workspace_root", write_then_fail)
    with pytest.raises(WorkspacePreferenceWriteError) as raised:
        _commit(choice)
    assert raised.value.reason == "write_outcome_uncertain"
    assert isolated_config.exists()
    assert workspace.load_workspace_config().workspace_root == root.resolve()


def test_lock_is_released_after_staged_write_failure(
    tmp_path: Path, isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"

    def fail(_path: str | Path) -> Path:
        raise workspace.WorkspaceRootError("injected mkdir failure")

    monkeypatch.setattr(workspace, "ensure_workspace_root", fail)
    with pytest.raises(WorkspacePreferenceWriteError) as raised:
        _commit(WorkspacePreferenceChange("set", root))
    assert raised.value.reason == "write_outcome_uncertain"
    assert not (isolated_config.parent / ".workspace-preference.write.lock").exists()
    assert not isolated_config.exists()


def test_redirected_config_parent_refused_at_commit(
    tmp_path: Path, isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    choice = WorkspacePreferenceChange("set", tmp_path / "workspace")
    review = plan_guarded_workspace_preference_change(choice)
    real_symlink = Path.is_symlink

    def redirected(path: Path) -> bool:
        return path == isolated_config.parent or real_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", redirected)
    with pytest.raises(WorkspacePreferenceCommitError) as raised:
        commit_guarded_workspace_preference_change(
            choice,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    assert raised.value.reason == "unsafe_path"
    assert not isolated_config.exists()
