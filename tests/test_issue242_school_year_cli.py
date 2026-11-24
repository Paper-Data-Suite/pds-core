"""C3B3 synthetic CLI parity tests for guarded school-year transitions."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import pds_core.classroom_school_year_commit as guarded
import pds_core.school_years as years
import pds_core.workspace as workspace
from pds_core.classes import ensure_class_folder
from pds_core.cli import _run
from pds_core.cli_support.school_year_commands import (
    EXIT_INPUT,
    EXIT_STALE,
    EXIT_STORAGE,
    EXIT_UNCERTAIN,
)

YEAR = "2026-2027"
START = "2026-09-01T08:00:00+00:00"
END = "2027-06-30T18:00:00+00:00"
START_TIME = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
END_TIME = datetime(2027, 6, 30, 18, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    location = tmp_path / "synthetic-workspace"
    location.mkdir()
    monkeypatch.setattr(
        workspace, "get_default_workspace_root", lambda: tmp_path / "default-root"
    )
    monkeypatch.setattr(
        workspace,
        "get_workspace_config_path",
        lambda: tmp_path / "private-config" / "config.json",
    )
    monkeypatch.delenv(workspace.WORKSPACE_ROOT_ENV_VAR, raising=False)
    return location


def _run_cli(*args: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = _run(args, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _json(*args: str) -> tuple[int, dict[str, Any], str]:
    code, out, error = _run_cli(*args, "--format", "json")
    payload: dict[str, Any] = json.loads(out)
    return code, payload, error


def _preview(
    root: Path,
    action: str,
    *,
    year: str | None = None,
    timestamp: str = START,
) -> dict[str, Any]:
    parts = ["--workspace", str(root), "workspace", "year-preview", action]
    if year is not None:
        parts.append(year)
    parts.extend(["--effective-at", timestamp])
    code, payload, error = _json(*parts)
    assert code == 0 and error == ""
    assert payload["ok"] is True
    assert payload["scope"] == "school_year"
    assert payload["command"] == "workspace year-preview"
    data: dict[str, Any] = payload["data"]
    assert data["saved"] is False
    return data


def _commit(
    root: Path,
    action: str,
    preview: dict[str, Any],
    *,
    year: str | None = None,
    timestamp: str = START,
    confirm: bool = True,
) -> tuple[int, dict[str, Any], str]:
    parts = ["--workspace", str(root), "workspace", "year-commit", action]
    if year is not None:
        parts.append(year)
    parts.extend(
        [
            "--effective-at",
            timestamp,
            "--expected-current-state-token",
            preview["current_state_token"],
            "--expected-candidate-state-token",
            preview["candidate_state_token"],
        ]
    )
    if confirm:
        parts.append("--confirm")
    return _json(*parts)


def test_first_year_preview_never_creates_any_state(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    assert preview["operation"] == "open"
    assert preview["previous_record_status"] == "missing"
    assert preview["proposed_active_year"] == YEAR
    assert preview["no_change"] is False
    assert preview["workspace_root"] == str(root.resolve())
    assert preview["effective_at"] == START
    assert len(preview["current_state_token"]) == 64
    assert len(preview["candidate_state_token"]) == 64
    assert preview["current_state_token"] != preview["candidate_state_token"]
    assert not years.school_year_state_path(root).exists()
    assert not (root / ".school-year.write.lock").exists()


def test_explicit_open_then_stale_replay_refused(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    code, result, err = _commit(root, "open", preview, year=YEAR)
    assert code == 0 and err == ""
    assert result["data"]["status"] == "committed"
    assert result["data"]["active_school_year"] == YEAR
    assert result["data"]["changed_scopes"] == ["SCHOOL_YEAR"]
    assert result["data"]["committed_state_token"] != preview["current_state_token"]
    state = years.load_school_year_state(root)
    assert state is not None and state.opened_at == START_TIME
    code, result, err = _commit(root, "open", preview, year=YEAR)
    assert code == EXIT_STALE and err == ""
    assert result["error"]["code"] == "school_year.current_state_changed"
    assert years.load_school_year_state(root) == state


def test_same_year_noop_preserves_canonical_record(root: Path) -> None:
    years.open_school_year(root, YEAR, opened_at=START_TIME)
    before = years.school_year_state_path(root).read_bytes()
    preview = _preview(root, "open", year=YEAR, timestamp=END)
    assert preview["no_change"] is True
    code, receipt, err = _commit(
        root, "open", preview, year=YEAR, timestamp=END
    )
    assert code == 0 and err == ""
    assert receipt["data"]["status"] == "no_change"
    assert receipt["data"]["changed_scopes"] == []
    assert years.school_year_state_path(root).read_bytes() == before
    assert not (root / ".school-year.write.lock").exists()


def test_confirmed_close_preserves_classroom_files(root: Path) -> None:
    years.open_school_year(root, YEAR, opened_at=START_TIME)
    folder = ensure_class_folder(root, "english12_p2")
    sentinel = folder.class_dir / "producer-owned.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    preview = _preview(root, "close", timestamp=END)
    assert preview["previous_school_year"] == YEAR
    assert preview["proposed_active_year"] is None
    code, result, err = _commit(root, "close", preview, timestamp=END)
    assert code == 0 and err == ""
    assert result["data"]["status"] == "committed"
    assert result["data"]["changed_scopes"] == ["SCHOOL_YEAR"]
    state = years.load_school_year_state(root)
    assert state is not None and state.closed_at == END_TIME
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_missing_confirmation_is_structured_without_writes(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    code, result, err = _commit(root, "open", preview, year=YEAR, confirm=False)
    assert code == EXIT_INPUT and err == ""
    assert result["error"]["code"] == "school_year.not_confirmed"
    assert not years.school_year_state_path(root).exists()


def test_changed_candidate_year_is_refused(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    code, result, err = _commit(root, "open", preview, year="2027-2028")
    assert code == EXIT_STALE and err == ""
    assert result["error"]["code"] == "school_year.candidate_changed"
    assert not years.school_year_state_path(root).exists()


def test_changed_timestamp_is_refused(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    code, result, err = _commit(
        root, "open", preview, year=YEAR, timestamp=END
    )
    assert code == EXIT_STALE and err == ""
    assert result["error"]["code"] == "school_year.candidate_changed"
    assert not years.school_year_state_path(root).exists()


def test_invalid_review_token_is_refused(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    preview["current_state_token"] = "bogus"
    code, result, err = _commit(root, "open", preview, year=YEAR)
    assert code == EXIT_INPUT and err == ""
    assert result["error"]["code"] == "school_year.invalid_token"
    assert not years.school_year_state_path(root).exists()


def test_uncoordinated_state_change_refuses_stale_commit(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    years.open_school_year(root, "2027-2028", opened_at=START_TIME)
    before = years.school_year_state_path(root).read_bytes()
    code, result, err = _commit(root, "open", preview, year=YEAR)
    assert code == EXIT_STALE and err == ""
    assert result["error"]["code"] == "school_year.current_state_changed"
    assert years.school_year_state_path(root).read_bytes() == before


def test_closed_year_record_cannot_be_replaced(root: Path) -> None:
    years.open_school_year(root, YEAR, opened_at=START_TIME)
    years.close_school_year(root, closed_at=END_TIME)
    before = years.school_year_state_path(root).read_bytes()
    code, result, err = _json(
        "--workspace", str(root), "workspace", "year-preview",
        "open", "2027-2028", "--effective-at", END
    )
    assert code == EXIT_STALE and err == ""
    assert result["error"]["code"] == "school_year.year_history_policy_required"
    assert years.school_year_state_path(root).read_bytes() == before


def test_live_writer_lock_refused_without_removal(root: Path) -> None:
    preview = _preview(root, "open", year=YEAR)
    lock = root / ".school-year.write.lock"
    lock.write_text("another owner", encoding="utf-8")
    code, result, err = _commit(root, "open", preview, year=YEAR)
    assert code == EXIT_STALE and err == ""
    assert result["error"]["code"] == "school_year.write_conflict"
    assert lock.read_text(encoding="utf-8") == "another owner"
    assert not years.school_year_state_path(root).exists()


def test_uncertain_write_has_own_exit_code(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preview = _preview(root, "open", year=YEAR)
    real_open = years.open_school_year

    def replace_then_fail(
        selected: str | Path,
        year: str,
        *,
        opened_at: datetime,
        overwrite: bool = False,
    ) -> years.SchoolYearState:
        real_open(selected, year, opened_at=opened_at, overwrite=overwrite)
        raise years.SchoolYearStateError("synthetic after replacement")

    monkeypatch.setattr(guarded, "open_school_year", replace_then_fail)
    code, result, err = _commit(root, "open", preview, year=YEAR)
    assert code == EXIT_UNCERTAIN and err == ""
    assert result["error"]["code"] == "school_year.write_outcome_uncertain"
    assert years.get_active_school_year(root) == YEAR


def test_malformed_state_reports_safe_structured_error(root: Path) -> None:
    state = years.school_year_state_path(root)
    state.parent.mkdir(parents=True)
    state.write_text("{not-json", encoding="utf-8")
    code, result, err = _json(
        "--workspace", str(root), "workspace", "year-preview",
        "open", YEAR, "--effective-at", START
    )
    assert code == EXIT_STORAGE and err == ""
    assert result["ok"] is False
    assert result["error"]["code"] == "school_year.invalid_school_year"
    assert str(root) not in json.dumps(result)
    assert state.read_text(encoding="utf-8") == "{not-json"


def test_invalid_workspace_is_reported_without_raw_bootstrap_error(
    tmp_path: Path,
) -> None:
    file = tmp_path / "file-not-directory"
    file.write_text("data", encoding="utf-8")
    code, result, err = _json(
        "--workspace", str(file), "workspace", "year-preview",
        "open", YEAR, "--effective-at", START
    )
    assert code == EXIT_STORAGE and err == ""
    assert result["error"]["code"] == "school_year.invalid_workspace"
    assert str(file) not in json.dumps(result)
    assert file.read_text(encoding="utf-8") == "data"


def test_text_preview_is_read_only_and_does_not_prompt(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbid_prompt(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("CLI must never prompt")

    monkeypatch.setattr("builtins.input", forbid_prompt)
    code, output, errors = _run_cli(
        "--workspace", str(root), "workspace", "year-preview",
        "open", YEAR, "--effective-at", START
    )
    assert code == 0 and errors == ""
    assert "PREVIEW ONLY - NO WRITE" in output
    assert "Current state token:" in output
    assert "Candidate state token:" in output
    assert not years.school_year_state_path(root).exists()


def test_parse_rejects_missing_or_naive_timestamp_without_write(
    root: Path,
) -> None:
    for tail in ([], ["--effective-at", "2026-09-01T08:00:00"]):
        code, _out, _errors = _run_cli(
            "--workspace", str(root), "workspace", "year-preview",
            "open", YEAR, *tail
        )
        assert code == 2
        assert not years.school_year_state_path(root).exists()


def test_legacy_workspace_show_retains_existing_behavior(root: Path) -> None:
    code, out, err = _run_cli("--workspace", str(root), "workspace", "show")
    assert code == 0 and err == ""
    assert "Resolved workspace root:" in out
    assert str(root) in out
    assert not years.school_year_state_path(root).exists()
